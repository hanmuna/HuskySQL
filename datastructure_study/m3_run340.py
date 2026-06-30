#!/usr/bin/env python3
"""M3 full run on the 340-question slice. For each question: build IR prompt ->
model -> parse IR JSON -> ra_to_sql -> SQL. Resumable checkpoint. Then evaluate EX
vs gold and compare to baseline (48.24). One generation run (~340 calls).
"""
import os, sys, json, re, sqlite3, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "llm", "src"))
import openai
from gpt_request import connect_gpt
from ra_to_sql import ra_to_sql
from m3_prompt import build_ir_prompt

DBR = os.path.join(HERE, "..", "llm", "data", "dev_databases")
OUT = os.path.join(HERE, "outputs")
CKPT = os.path.join(OUT, "m3_predict_340.json")
ENGINE = "gpt-5.2"
WORKERS = 8
lock = threading.Lock()


def load_key():
    for line in open(os.path.join(HERE, "..", "llm", "run", ".env")):
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


def run_ex(db, pred, gold):
    try:
        c = sqlite3.connect(os.path.join(DBR, db, db + ".sqlite")).cursor()
        c.execute(pred); p = c.fetchall()
        c.execute(gold); g = c.fetchall()
        return 1 if set(p) == set(g) else 0
    except Exception:
        return 0


def main():
    openai.api_key = load_key()
    rows = json.load(open(os.path.join(OUT, "results_340.json")))
    ckpt = {}
    if os.path.exists(CKPT):
        ckpt = {int(k): v for k, v in json.load(open(CKPT)).items()}
    pending = [r for r in rows if r["idx"] not in ckpt]
    print(f"resume: {len(ckpt)}/340 done, {len(pending)} pending", flush=True)

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
                              open(CKPT, "w"), ensure_ascii=False)
                    print(f"  generated {len(ckpt)}/340", flush=True)
    json.dump({str(k): v for k, v in ckpt.items()}, open(CKPT, "w"), ensure_ascii=False)

    # ---- evaluate ----
    by = {r["idx"]: r for r in rows}
    n_ir = n_comp = 0
    m3, base = {}, {}
    for r in rows:
        c = ckpt[r["idx"]]
        n_ir += c["ir_ok"]; n_comp += c["compile_ok"]
        ex1 = run_ex(r["db_id"], c["sql"], r["gold"]) if c["sql"] else 0
        m3[r["idx"]] = ex1
        base[r["idx"]] = r["ex_kg"]
    EXm = sum(m3.values()) / 340 * 100
    EXb = sum(base.values()) / 340 * 100
    flip_up = sum(1 for i in m3 if base[i] == 0 and m3[i] == 1)
    flip_dn = sum(1 for i in m3 if base[i] == 1 and m3[i] == 0)
    print("\n===== M3 full 340 =====")
    print(f"IR-parse {n_ir}/340  compile {n_comp}/340")
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
    # over-selection bucket
    tax = json.load(open(os.path.join(OUT, "kg_taxonomy.json")))
    over = tax.get("extra_columns_same_rowcount", []) + tax.get("extra_columns_diff_rowcount", [])
    fixed = sum(1 for i in over if m3[i] == 1)
    print(f"-- over-selection bucket: {fixed}/{len(over)} now correct")
    json.dump({"m3": m3, "base": base, "EXm3": EXm, "EXbase": EXb,
               "flip_up": flip_up, "flip_dn": flip_dn, "n_ir": n_ir, "n_comp": n_comp,
               "over_fixed": fixed, "over_total": len(over)},
              open(os.path.join(OUT, "m3_eval_340.json"), "w"))


if __name__ == "__main__":
    main()
