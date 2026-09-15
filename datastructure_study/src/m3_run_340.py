#!/usr/bin/env python3
"""M3 run: for each question, build IR prompt -> model -> parse IR JSON ->
ra_to_sql -> SQL. Resumable checkpoint. Then evaluate EX vs gold and compare
to baseline. One generation run (~N calls).

Usage: m3_run_340.py [340|full]  (default: 340, legacy behavior, reads
results_340.json / writes m3_predict_340.json + m3_eval_340.json unchanged).
"full" reads results_full.json (produced by `m0_eval_baseline_340.py full`)
and writes m3_predict_full.json + m3_eval_full.json instead.
"""
import os, sys, json, re, sqlite3, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "llm", "src"))
import openai
from func_timeout import func_timeout, FunctionTimedOut
from gpt_request import connect_gpt
from ra_to_sql import ra_to_sql
from m3_ir_prompt import build_ir_prompt

EX_TIMEOUT = 30.0

DBR = os.path.join(HERE, "..", "..", "llm", "data", "dev_databases")
OUT = os.path.join(HERE, "..", "outputs")
ENGINE = "gpt-5.2"
WORKERS = 8
lock = threading.Lock()


def load_key():
    for line in open(os.path.join(HERE, "..", "..", "llm", "run", ".env")):
        if line.startswith("AIMLAPI_API_KEY"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")


def extract_json(text):
    t = re.sub(r"```(?:json)?", "", text, flags=re.I).strip()
    s = t.find("{")
    if s < 0:
        return None
    depth = 0
    for i in range(s, len(t)):
        if t[i] == "{":
            depth += 1
        elif t[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[s:i + 1])
                except Exception:
                    return None
    return None


def gen_one(r):
    dbp = os.path.join(DBR, r["db_id"], r["db_id"] + ".sqlite")
    rec = {"idx": r["idx"], "ir_ok": False, "compile_ok": False, "sql": "", "ir": None}
    try:
        prompt = build_ir_prompt(dbp, r["question"], r["evidence"])
        raw = connect_gpt(engine=ENGINE, prompt=prompt, max_tokens=900, temperature=0, stop=None)
        text = raw if isinstance(raw, str) else raw["choices"][0]["text"]
        ir = extract_json(text)
        rec["ir"] = ir
        rec["ir_ok"] = ir is not None
        if ir is not None:
            rec["sql"] = ra_to_sql(ir)
            rec["compile_ok"] = True
    except Exception as e:
        rec["err"] = str(e)[:120]
    return rec


def _run_ex(db, pred, gold):
    c = sqlite3.connect(os.path.join(DBR, db, db + ".sqlite")).cursor()
    c.execute(pred); p = c.fetchall()
    c.execute(gold); g = c.fetchall()
    return 1 if set(p) == set(g) else 0


def run_ex(db, pred, gold):
    try:
        return func_timeout(EX_TIMEOUT, _run_ex, args=(db, pred, gold))
    except (FunctionTimedOut, Exception):
        return 0


def main(tag="340"):
    assert tag in ("340", "full"), "usage: m3_run_340.py [340|full]"
    results_in = os.path.join(OUT, f"results_{tag}.json")
    ckpt_path = os.path.join(OUT, f"m3_predict_{tag}.json")
    eval_out = os.path.join(OUT, f"m3_eval_{tag}.json")

    openai.api_key = load_key()
    rows = json.load(open(results_in))
    N = len(rows)
    ckpt = {}
    if os.path.exists(ckpt_path):
        ckpt = {int(k): v for k, v in json.load(open(ckpt_path)).items()}
    pending = [r for r in rows if r["idx"] not in ckpt]
    print(f"resume: {len(ckpt)}/{N} done, {len(pending)} pending", flush=True)

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(gen_one, r): r["idx"] for r in pending}
        for f in as_completed(futs):
            rec = f.result()
            with lock:
                ckpt[rec["idx"]] = rec
                done += 1
                if done % 20 == 0 or done == len(pending):
                    json.dump({str(k): v for k, v in ckpt.items()},
                              open(ckpt_path, "w"), ensure_ascii=False)
                    print(f"  generated {len(ckpt)}/{N}", flush=True)
    json.dump({str(k): v for k, v in ckpt.items()}, open(ckpt_path, "w"), ensure_ascii=False)

    # ---- evaluate ----
    print(f"evaluating {N} questions (EX, {EX_TIMEOUT:.0f}s timeout each)...", flush=True)
    by = {r["idx"]: r for r in rows}
    n_ir = n_comp = 0
    m3, base = {}, {}
    for i, r in enumerate(rows):
        c = ckpt[r["idx"]]
        n_ir += c["ir_ok"]; n_comp += c["compile_ok"]
        ex1 = run_ex(r["db_id"], c["sql"], r["gold"]) if c["sql"] else 0
        m3[r["idx"]] = ex1
        base[r["idx"]] = r["ex_kg"]
        if (i + 1) % 100 == 0 or i + 1 == N:
            print(f"  evaluated {i + 1}/{N}", flush=True)
    EXm = sum(m3.values()) / N * 100
    EXb = sum(base.values()) / N * 100
    flip_up = sum(1 for i in m3 if base[i] == 0 and m3[i] == 1)
    flip_dn = sum(1 for i in m3 if base[i] == 1 and m3[i] == 0)
    print(f"\n===== M3 full run (N={N}) =====")
    print(f"IR-parse {n_ir}/{N}  compile {n_comp}/{N}")
    print(f"EX baseline {EXb:.2f}  ->  M3 {EXm:.2f}  (delta {EXm-EXb:+.2f})")
    print(f"flips wrong->right {flip_up}   right->wrong {flip_dn}   net {flip_up-flip_dn:+d}")
    # by difficulty / db
    for key in ["difficulty", "db_id"]:
        print(f"-- by {key}:")
        groups = {}
        for r in rows:
            groups.setdefault(r[key], []).append(r["idx"])
        for g, idxs in groups.items():
            b = sum(base[i] for i in idxs) / len(idxs) * 100
            m = sum(m3[i] for i in idxs) / len(idxs) * 100
            print(f"   {g:20} n={len(idxs):3}  base {b:5.1f} -> M3 {m:5.1f}  ({m-b:+.1f})")
    # over-selection bucket (optional; skip if the taxonomy file isn't present locally)
    tax_path = os.path.join(OUT, "kg_taxonomy.json")
    if os.path.exists(tax_path):
        tax = json.load(open(tax_path))
        over = tax.get("extra_columns_same_rowcount", []) + tax.get("extra_columns_diff_rowcount", [])
        fixed = sum(1 for i in over if m3[i] == 1)
        print(f"-- over-selection bucket: {fixed}/{len(over)} now correct")
    else:
        fixed, over = 0, []
        print("-- over-selection bucket: skipped (kg_taxonomy.json not found)")
    json.dump({"m3": m3, "base": base, "EXm3": EXm, "EXbase": EXb,
               "flip_up": flip_up, "flip_dn": flip_dn, "n_ir": n_ir, "n_comp": n_comp,
               "over_fixed": fixed, "over_total": len(over)},
              open(eval_out, "w"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "340")
