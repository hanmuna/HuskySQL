#!/usr/bin/env python3
"""Ablation B: official baseline prompt + ONE added instruction line telling the
model to project only the asked-for columns. No IR, no compiler. Everything else
(engine, max_tokens, stop, temperature) is byte-identical to the run that
produced the 48.24 baseline, so the delta isolates what a soft prompt
instruction can do against the over-selection bucket.
Usage: ablation_b_prompt_only.py [N=340]  (resumable)
"""

import json
import os
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "llm", "src"))
import openai
from func_timeout import FunctionTimedOut, func_timeout
from gpt_request import connect_gpt, generate_combined_prompts_one, reconstruct_sql
from m3_run_340 import load_key

DBR = os.path.join(HERE, "..", "..", "llm", "data", "dev_databases")
OUT = os.path.join(HERE, "..", "outputs")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 340
CKPT = os.path.join(OUT, f"ablB_prompt_only_{N}.json")
ENGINE = "gpt-5.2"
WORKERS = 8
lock = threading.Lock()

INSTR = (
    "\n-- IMPORTANT: In the SELECT clause output ONLY the columns the question"
    "\n-- explicitly asks for. Do NOT add extra id/name/context columns."
)


def build_prompt(dbp, question, knowledge):
    base = generate_combined_prompts_one(
        db_path=dbp, question=question, knowledge=knowledge
    )
    # the official prompt ends with '...\nSELECT '; inject before that tail
    head, sep, tail = base.rpartition("\nSELECT ")
    return head + INSTR + sep + tail


def gen_one(r):
    dbp = os.path.join(DBR, r["db_id"], r["db_id"] + ".sqlite")
    prompt = build_prompt(
        dbp, r["question"], r["evidence"] if r["evidence"].strip() else None
    )
    raw = connect_gpt(
        engine=ENGINE,
        prompt=prompt,
        max_tokens=256,
        temperature=0,
        stop=["--", "\n\n", ";", "#"],
    )
    text = raw if isinstance(raw, str) else raw["choices"][0]["text"]
    if isinstance(text, str) and text.lstrip().lower().startswith("error:"):
        raise RuntimeError(text.strip()[:160])
    return {"idx": r["idx"], "sql": reconstruct_sql(text)}


def run_ex(db, pred, gold):
    def _go():
        c = sqlite3.connect(os.path.join(DBR, db, db + ".sqlite")).cursor()
        c.execute(pred)
        p = c.fetchall()
        c.execute(gold)
        g = c.fetchall()
        return 1 if set(p) == set(g) else 0

    try:
        return func_timeout(30.0, _go)
    except (FunctionTimedOut, Exception):
        return 0


def main():
    openai.api_key = load_key()
    rows = json.load(open(os.path.join(OUT, "results_340.json")))[:N]
    tax = json.load(open(os.path.join(OUT, "kg_taxonomy.json")))
    over = set(tax.get("extra_columns_same_rowcount", [])) | set(
        tax.get("extra_columns_diff_rowcount", [])
    )
    ckpt = {}
    if os.path.exists(CKPT):
        ckpt = {int(k): v for k, v in json.load(open(CKPT)).items()}
    pending = [r for r in rows if r["idx"] not in ckpt]
    print(
        f"ablation B (prompt-only), N={N}: {len(ckpt)} done, {len(pending)} pending",
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
                    errors += 1
                    if errors <= 3:
                        print(f"  ERR idx {futs[f]}: {str(e)[:100]}", flush=True)
                done += 1
                if done % 20 == 0 or done == len(pending):
                    json.dump(
                        {str(k): v for k, v in ckpt.items()},
                        open(CKPT, "w"),
                        ensure_ascii=False,
                    )
                    print(f"  generated {len(ckpt)}/{N} (errors {errors})", flush=True)
    json.dump({str(k): v for k, v in ckpt.items()}, open(CKPT, "w"), ensure_ascii=False)
    if errors:
        print(
            f"!! {errors} transport errors not checkpointed — rerun to retry",
            flush=True,
        )

    b_sum = a_sum = 0
    over_fixed, flip_up, flip_dn = [], 0, 0
    for r in rows:
        c = ckpt.get(r["idx"])
        if not c:
            continue
        exb = run_ex(r["db_id"], c["sql"], r["gold"]) if c.get("sql") else 0
        base = r["ex_kg"]
        a_sum += exb
        b_sum += base
        if exb > base:
            flip_up += 1
            if r["idx"] in over:
                over_fixed.append(r["idx"])
        elif base > exb:
            flip_dn += 1
    print("\n===== ablation B (baseline + minimal-projection instruction) =====")
    print(
        f"EX baseline {b_sum / N * 100:.2f}  ->  ablB {a_sum / N * 100:.2f}"
        f"  (delta {(a_sum - b_sum) / N * 100:+.2f})"
    )
    print(f"flips wrong->right {flip_up}   right->wrong {flip_dn}")
    print(
        f"over-selection bucket fixed by instruction: {len(over_fixed)}/{len(over)}"
        f"  (M3 compiler fixed 27)  idx={over_fixed[:20]}"
    )


if __name__ == "__main__":
    main()
