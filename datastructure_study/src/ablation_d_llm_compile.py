#!/usr/bin/env python3
"""Ablation D: keep the model's IR (from m3_predict_340.json) but replace the
deterministic ra_to_sql compiler with an LLM call that translates the IR to SQL.
Reuses saved IRs, so only one API call per question with a valid IR.
Resumable checkpoint. Compares EX against the deterministic M3 result.

Usage: ablation_d_llm_compile.py [340|full] [--dry-run]
"""
import json
import os
import re
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "llm", "src"))
import openai
from func_timeout import FunctionTimedOut, func_timeout
from gpt_request import connect_gpt, reconstruct_sql
from m3_ir_prompt import schema_block
from m3_run_340 import load_key

DBR = os.path.join(HERE, "..", "..", "llm", "data", "dev_databases")
OUT = os.path.join(HERE, "..", "outputs")
ENGINE = "gpt-5.2"
WORKERS = 8
EX_TIMEOUT = 30.0
TAG = "340"
lock = threading.Lock()


def set_tag(tag):
    global TAG, CKPT
    assert tag in ("340", "full"), "usage: ablation_d_llm_compile.py [340|full] [--dry-run]"
    TAG = tag
    CKPT = os.path.join(OUT, f"ablD_llm_compile_{tag}.json")


set_tag("340")

TASK = """Translate the JSON relational-algebra IR below into ONE SQLite query.
Rules:
- Use exactly the items in "select" as the SELECT list. Do not add columns, aggregates, DISTINCT, ORDER BY or LIMIT that the IR does not contain.
- Use "from", "joins" (with their "on" pairs), "where", "group_by", "having", "order_by", "limit", "distinct" exactly as given.
- Output only the SQL query, no prose, no markdown, no semicolon."""


def build_prompt(db_path, ir):
    return (
        schema_block(db_path)
        + "\n\n-- IR:\n"
        + json.dumps(ir, ensure_ascii=False, indent=1)
        + "\n\n"
        + TASK
        + "\nSELECT"
    )


def gen_one(idx, db, ir):
    dbp = os.path.join(DBR, db, db + ".sqlite")
    prompt = build_prompt(dbp, ir)
    raw = connect_gpt(engine=ENGINE, prompt=prompt, max_tokens=400, temperature=0, stop=None)
    text = raw if isinstance(raw, str) else raw["choices"][0]["text"]
    if isinstance(text, str) and text.lstrip().lower().startswith("error:"):
        raise RuntimeError(text.strip()[:160])
    fenced = re.findall(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    body = fenced[-1] if fenced else text
    sql = reconstruct_sql(body).strip().rstrip(";")
    return {"idx": idx, "sql": sql}


def run_ex(db, pred, gold):
    def _go():
        c = sqlite3.connect(os.path.join(DBR, db, db + ".sqlite")).cursor()
        c.execute(pred)
        p = c.fetchall()
        c.execute(gold)
        g = c.fetchall()
        return 1 if set(p) == set(g) else 0

    try:
        return func_timeout(EX_TIMEOUT, _go)
    except (FunctionTimedOut, Exception):
        return 0


def load_inputs():
    rows = json.load(open(os.path.join(OUT, f"results_{TAG}.json")))
    pred = json.load(open(os.path.join(OUT, f"m3_predict_{TAG}.json")))
    m3_eval = json.load(open(os.path.join(OUT, f"m3_eval_{TAG}.json")))
    jobs = []
    for r in rows:
        p = pred[str(r["idx"])]
        if p.get("ir_ok") and p.get("ir"):
            jobs.append((r, p["ir"]))
    return rows, jobs, {int(k): v for k, v in m3_eval["m3"].items()}


def dry_run():
    rows, jobs, _ = load_inputs()
    print(f"questions with valid IR (would call the model): {len(jobs)}")
    r, ir = jobs[0]
    print("--- example prompt (tail) ---")
    print(build_prompt(os.path.join(DBR, r["db_id"], r["db_id"] + ".sqlite"), ir)[-1200:])


def main():
    openai.api_key = load_key()
    rows, jobs, m3_det = load_inputs()
    ckpt = {}
    if os.path.exists(CKPT):
        ckpt = {int(k): v for k, v in json.load(open(CKPT)).items()}
    pending = [(r, ir) for r, ir in jobs if r["idx"] not in ckpt]
    print(f"ablation D: {len(ckpt)} done, {len(pending)} pending", flush=True)

    done = errors = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(gen_one, r["idx"], r["db_id"], ir): r["idx"] for r, ir in pending}
        for f in as_completed(futs):
            idx = futs[f]
            try:
                rec = f.result()
            except Exception as e:
                errors += 1
                rec = {"idx": idx, "sql": "", "err": str(e)[:160]}
            with lock:
                ckpt[rec["idx"]] = rec
                done += 1
                if done % 20 == 0 or done == len(pending):
                    json.dump({str(k): v for k, v in ckpt.items()}, open(CKPT, "w"), ensure_ascii=False)
                    print(f"  generated {len(ckpt)}/{len(jobs)} (errors {errors})", flush=True)
    json.dump({str(k): v for k, v in ckpt.items()}, open(CKPT, "w"), ensure_ascii=False)

    ex_llm = ex_det = flip_up = flip_dn = 0
    for r in rows:
        if r["idx"] not in ckpt or not ckpt[r["idx"]].get("sql"):
            continue
        e_llm = run_ex(r["db_id"], ckpt[r["idx"]]["sql"], r["gold"])
        e_det = m3_det[r["idx"]]
        ex_llm += e_llm
        ex_det += e_det
        flip_up += e_llm == 1 and e_det == 0
        flip_dn += e_llm == 0 and e_det == 1
    n = len(rows)
    print(f"\n===== Ablation D [{TAG}]: LLM compiler vs deterministic ra_to_sql (N={n}) =====")
    print(f"EX deterministic M3 {ex_det/n*100:.2f}   EX LLM compile {ex_llm/n*100:.2f}")
    print(f"LLM-compile vs deterministic: flips up {flip_up}  down {flip_dn}  net {flip_up-flip_dn:+d}")
    print(f"generation errors: {errors}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    set_tag(args[0] if args else "340")
    if "--dry-run" in sys.argv:
        dry_run()
    else:
        main()
