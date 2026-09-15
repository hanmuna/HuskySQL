#!/usr/bin/env python3
"""Cross-model replication runner: run either the official BIRD baseline prompt
(free-form SQL) or the M3 RA-IR protocol on any AIML-served model, over the
first N dev-slice questions. One (engine, arm) pair per invocation; resumable
checkpoint per pair. Transport/quota errors are NOT checkpointed, so a rerun
retries them; parse/compile failures ARE results and get stored.

Usage: xmodel_run.py <engine> <baseline|m3> [N]
  e.g. xmodel_run.py Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8 m3 10
       xmodel_run.py zhipu/glm-4.7 baseline 340
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
from gpt_request import connect_gpt, generate_combined_prompts_one
from m3_ir_prompt import build_ir_prompt
from m3_run_340 import extract_json, load_key
from ra_to_sql import ra_to_sql

DBR = os.path.join(HERE, "..", "..", "llm", "data", "dev_databases")
OUT = os.path.join(HERE, "..", "outputs")
WORKERS = int(os.environ.get("XM_WORKERS", 8))
lock = threading.Lock()

ENGINE = sys.argv[1]
ARM = sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 340
assert ARM in ("baseline", "m3"), "arm must be baseline|m3"
TAG = re.sub(r"[^a-z0-9.-]+", "-", ENGINE.split("/")[-1].lower()).strip("-")
CKPT = os.path.join(OUT, f"xmodel_{TAG}_{ARM}_{N}.json")


def _extract_sql(text):
    """Chat models answer with prose + a ```sql fence; take the last fence,
    else fall back to the first SELECT."""
    fences = re.findall(r"```sql\s*(.*?)```", text, re.S | re.I)
    if fences:
        return fences[-1].strip().rstrip(";")
    m = re.search(r"\bSELECT\b", text, re.I)
    return text[m.start() :].strip().rstrip(";") if m else ""


def _text_of(raw):
    """connect_gpt returns 'error:...' strings instead of raising on API errors;
    surface those as exceptions so they are retried, not checkpointed."""
    text = raw if isinstance(raw, str) else raw["choices"][0]["text"]
    if isinstance(text, str) and text.lstrip().lower().startswith("error:"):
        raise RuntimeError(text.strip()[:160])
    return text


def gen_one(r):
    dbp = os.path.join(DBR, r["db_id"], r["db_id"] + ".sqlite")
    rec = {"idx": r["idx"], "sql": ""}
    if ARM == "baseline":
        prompt = generate_combined_prompts_one(
            db_path=dbp,
            question=r["question"],
            knowledge=r["evidence"] if r["evidence"].strip() else None,
        )
        # chat models emit prose+fenced SQL; no stop tokens, room to finish
        raw = connect_gpt(
            engine=ENGINE, prompt=prompt, max_tokens=900, temperature=0, stop=None
        )
        rec["sql"] = _extract_sql(_text_of(raw))
    else:
        prompt = build_ir_prompt(dbp, r["question"], r["evidence"])
        raw = connect_gpt(
            engine=ENGINE, prompt=prompt, max_tokens=900, temperature=0, stop=None
        )
        ir = extract_json(_text_of(raw))
        rec["ir"] = ir
        rec["ir_ok"] = ir is not None
        rec["compile_ok"] = False
        if ir is not None:
            try:
                rec["sql"] = ra_to_sql(ir)
                rec["compile_ok"] = True
            except Exception as e:
                rec["compile_err"] = str(e)[:120]
    return rec


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
    ckpt = {}
    if os.path.exists(CKPT):
        ckpt = {int(k): v for k, v in json.load(open(CKPT)).items()}
    pending = [r for r in rows if r["idx"] not in ckpt]
    print(
        f"[{TAG} | {ARM} | N={N}] {len(ckpt)} done, {len(pending)} pending", flush=True
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
                    print(
                        f"  progress {done}/{len(pending)} (errors {errors})",
                        flush=True,
                    )
    json.dump({str(k): v for k, v in ckpt.items()}, open(CKPT, "w"), ensure_ascii=False)
    if errors:
        print(
            f"!! {errors} transport errors not checkpointed — rerun to retry",
            flush=True,
        )

    n_ex = n_ir = n_comp = 0
    for r in rows:
        c = ckpt.get(r["idx"])
        if not c:
            continue
        if ARM == "m3":
            n_ir += bool(c.get("ir_ok"))
            n_comp += bool(c.get("compile_ok"))
        if c.get("sql"):
            n_ex += run_ex(r["db_id"], c["sql"], r["gold"])
    print(f"\n===== {TAG} | {ARM} | {len(ckpt)}/{N} generated =====")
    if ARM == "m3":
        print(f"IR-parse {n_ir}/{len(ckpt)}  compile {n_comp}/{len(ckpt)}")
    print(f"EX {n_ex}/{N} = {n_ex / N * 100:.2f}")

    other = os.path.join(
        OUT, f"xmodel_{TAG}_{'baseline' if ARM == 'm3' else 'm3'}_{N}.json"
    )
    if os.path.exists(other):
        oc = {int(k): v for k, v in json.load(open(other)).items()}
        o_ex = sum(
            run_ex(r["db_id"], oc[r["idx"]]["sql"], r["gold"])
            for r in rows
            if r["idx"] in oc and oc[r["idx"]].get("sql")
        )
        a, b = (o_ex, n_ex) if ARM == "m3" else (n_ex, o_ex)
        print(
            f"[{TAG}] baseline {a}/{N}  ->  M3 {b}/{N}  (delta {(b - a) / N * 100:+.2f})"
        )


if __name__ == "__main__":
    main()
