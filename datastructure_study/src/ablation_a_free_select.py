#!/usr/bin/env python3
"""Ablation A: same RA-IR JSON protocol as M3, but WITHOUT the minimal-projection
constraint (no "select ONLY what is asked" rule, select not forced minimal).
Isolates "structured JSON format helps" from "compiler physically cannot
over-project". Usage: ablation_a_free_select.py [N]  (default 10, resumable).
"""

import os
import sys
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "llm", "src"))
import openai
from gpt_request import connect_gpt
from ra_to_sql import ra_to_sql
from m3_ir_prompt import schema_block
from m3_run_340 import load_key, extract_json

DBR = os.path.join(HERE, "..", "..", "llm", "data", "dev_databases")
OUT = os.path.join(HERE, "..", "outputs")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
CKPT = os.path.join(OUT, f"ablA_free_select_{N}.json")
ENGINE = "gpt-5.2"
WORKERS = 8
lock = threading.Lock()

# Same JSON IR as m3_ir_prompt.IR_SPEC, minus the minimality language: "select" is
# just "the output columns", and the ONLY-asked-columns rule is removed.
IR_SPEC_FREE = """You must answer ONLY with a JSON object in this Relational-Algebra IR (no prose, no markdown):
{
  "from": "<table>",                       // base table (or a raw "(SELECT ...) AS x")
  "joins": [{"table":"<t>","on":["<t1.col>","<t2.col>"]}],   // [] if none; use the FK hints
  "select": [ "<table.col>",               // output columns
              {"fn":"COUNT","arg":"<table.col>|*","distinct":false},   // aggregate
              {"expr":"<raw scalar SQL>","as":"r"} ],          // ratio / CASE / CAST
  "where": "<raw SQL predicate>",          // optional
  "group_by": ["<table.col or raw expr>"], // optional
  "having": "<raw SQL>",                   // optional
  "order_by": [{"by":"<table.col or raw expr>","desc":true}], // optional
  "limit": <int>,                          // optional
  "distinct": false
}
RULES:
- Use the exact column names from the schema (quote-sensitive names go in expr/where as-is).
- Use the FK hints below for join keys. Match question phrases to real values via the value hints."""


def build_prompt(db_path, question, evidence=""):
    p = schema_block(db_path) + "\n\n" + IR_SPEC_FREE + "\n"
    if evidence and evidence.strip():
        p += f"\n-- External Knowledge: {evidence}"
    p += f"\n-- Question: {question}\nJSON IR:"
    return p


def gen_one(r):
    dbp = os.path.join(DBR, r["db_id"], r["db_id"] + ".sqlite")
    rec = {"idx": r["idx"], "ir_ok": False, "compile_ok": False, "sql": "", "ir": None}
    prompt = build_prompt(dbp, r["question"], r["evidence"])
    # transport/quota failures raise (connect_gpt returns 'error:...' strings)
    # so main() leaves them out of the checkpoint and a rerun retries them
    raw = connect_gpt(
        engine=ENGINE, prompt=prompt, max_tokens=900, temperature=0, stop=None
    )
    text = raw if isinstance(raw, str) else raw["choices"][0]["text"]
    if isinstance(text, str) and text.lstrip().lower().startswith("error:"):
        raise RuntimeError(text.strip()[:160])
    ir = extract_json(text)
    rec["ir"] = ir
    rec["ir_ok"] = ir is not None
    if ir is not None:
        try:
            rec["sql"] = ra_to_sql(ir)
            rec["compile_ok"] = True
        except Exception as e:
            rec["compile_err"] = str(e)[:120]
    return rec


def run_ex(db, pred, gold):
    try:
        c = sqlite3.connect(os.path.join(DBR, db, db + ".sqlite")).cursor()
        c.execute(pred)
        p = c.fetchall()
        c.execute(gold)
        g = c.fetchall()
        return 1 if set(p) == set(g) else 0
    except Exception:
        return 0


def main():
    openai.api_key = load_key()
    rows = json.load(open(os.path.join(OUT, "results_340.json")))[:N]
    m3ex = {
        int(k): v
        for k, v in json.load(open(os.path.join(OUT, "m3_eval_340.json")))["m3"].items()
    }
    ckpt = {}
    if os.path.exists(CKPT):
        ckpt = {int(k): v for k, v in json.load(open(CKPT)).items()}
    pending = [r for r in rows if r["idx"] not in ckpt]
    print(
        f"ablation A (free SELECT), N={N}: {len(ckpt)} done, {len(pending)} pending",
        flush=True,
    )

    done = errors = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(gen_one, r): r["idx"] for r in pending}
        for f in as_completed(futs):
            with lock:
                try:
                    rec = f.result()
                    ckpt[rec["idx"]] = rec
                except Exception as e:
                    errors += 1  # transport/quota: not checkpointed, rerun retries
                    if errors <= 3:
                        print(f"  ERR idx {futs[f]}: {str(e)[:100]}", flush=True)
                done += 1
                if done % 20 == 0 or done == len(pending):
                    json.dump(
                        {str(k): v for k, v in ckpt.items()},
                        open(CKPT, "w"),
                        ensure_ascii=False,
                    )
                    print(f"  generated {len(ckpt)}/{N}", flush=True)
    json.dump({str(k): v for k, v in ckpt.items()}, open(CKPT, "w"), ensure_ascii=False)
    if errors:
        print(
            f"!! {errors} transport errors not checkpointed — rerun to retry",
            flush=True,
        )

    print(f"\n{'idx':>4} {'base':>4} {'M3':>3} {'ablA':>4}  ncols(ablA sel)")
    a_sum = b_sum = m_sum = 0
    for r in rows:
        c = ckpt.get(r["idx"])
        if c is None:
            continue
        exa = run_ex(r["db_id"], c["sql"], r["gold"]) if c["sql"] else 0
        nsel = len(c["ir"].get("select", [])) if c.get("ir") else -1
        a_sum += exa
        b_sum += r["ex_kg"]
        m_sum += m3ex.get(r["idx"], 0)
        print(
            f"{r['idx']:>4} {r['ex_kg']:>4} {m3ex.get(r['idx'], 0):>3} {exa:>4}  {nsel}"
        )
    print(
        f"\nEX on first {N}: baseline {b_sum}/{N}  M3 {m_sum}/{N}  ablation-A {a_sum}/{N}"
    )
    print("(ablation-A vs M3 gap = contribution of the minimal-projection constraint;")
    print(" ablation-A vs baseline gap = contribution of the JSON/IR format itself)")


if __name__ == "__main__":
    main()
