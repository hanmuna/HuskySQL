"""Recompile every saved RA-IR with the current compiler and re-score EX.

Zero token: the IR is already on disk from the paid runs, only `ra_to_sql` changes.
Use after any compiler fix to measure what the fix is worth, per model.

Questions whose EX changes are re-executed serially before being reported, so a
timeout caused by parallel contention cannot be mistaken for a real flip.

Usage:  llm/.venv/bin/python src/m4_recompile_eval.py
Writes: outputs/m4_recompile_eval.json
"""

import json
import os
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor

from func_timeout import FunctionTimedOut, func_timeout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ra_to_sql import ra_to_sql  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_ROOT = os.path.join(os.path.dirname(ROOT), "llm", "data", "dev_databases")
OUT = os.path.join(ROOT, "outputs")
TIMEOUT = 30

FILES = {
    "gpt-5.2": "m3_predict_340.json",
    "gpt-4.1-mini": "xmodel_gpt-4.1-mini_m3_340.json",
    "claude-sonnet-4.5": "xmodel_claude-sonnet-4.5_m3_340.json",
    "deepseek-chat": "xmodel_deepseek-chat_m3_340.json",
    "qwen3-coder-480b-a35b-instruct": "xmodel_qwen3-coder-480b-a35b-instruct_m3_340.json",
}


def _rows(sql, dbp):
    con = sqlite3.connect(dbp)
    try:
        return con.cursor().execute(sql).fetchall()
    finally:
        con.close()


def ex(pred, gold, dbp):
    if not pred or not pred.strip():
        return 0
    try:
        pr = func_timeout(TIMEOUT, _rows, args=(pred, dbp))
        gr = func_timeout(TIMEOUT, _rows, args=(gold, dbp))
    except (FunctionTimedOut, Exception):
        return 0
    return 1 if set(pr) == set(gr) else 0


def main():
    meta = json.load(open(os.path.join(OUT, "results_340.json")))
    result = {}

    for model, fname in FILES.items():
        preds = json.load(open(os.path.join(OUT, fname)))

        def one(r):
            i, dbp = (
                str(r["idx"]),
                os.path.join(DB_ROOT, r["db_id"], f"{r['db_id']}.sqlite"),
            )
            rec = preds.get(i) or {}
            old = rec.get("sql", "")
            try:
                new = ra_to_sql(rec["ir"]) if rec.get("ir") else old
            except Exception:
                new = old
            return r["idx"], old, new, ex(old, r["gold"], dbp), ex(new, r["gold"], dbp)

        with ThreadPoolExecutor(max_workers=4) as pool:
            rows = list(pool.map(one, meta))

        gold = {r["idx"]: (r["gold"], r["db_id"]) for r in meta}
        changed = []
        for idx, old, new, eo, en in rows:
            if eo == en:
                continue
            g, db = gold[idx]
            dbp = os.path.join(DB_ROOT, db, f"{db}.sqlite")
            if ex(old, g, dbp) == eo and ex(new, g, dbp) == en:  # serial confirmation
                changed.append((idx, eo, en))

        n = len(rows)
        old_ex = sum(r[3] for r in rows) / n * 100
        gained = [i for i, a, b in changed if b > a]
        lost = [i for i, a, b in changed if b < a]
        new_ex = old_ex + (len(gained) - len(lost)) / n * 100
        print(
            f"{model:<32} EX {old_ex:5.2f} -> {new_ex:5.2f} ({new_ex - old_ex:+.2f})"
            f"   fixed {gained}  broke {lost}"
        )
        result[model] = {
            "ex_old": old_ex,
            "ex_new": new_ex,
            "fixed": gained,
            "broke": lost,
        }

    with open(os.path.join(OUT, "m4_recompile_eval.json"), "w") as f:
        json.dump(result, f, indent=1)
    print("\nwrote outputs/m4_recompile_eval.json")


if __name__ == "__main__":
    main()
