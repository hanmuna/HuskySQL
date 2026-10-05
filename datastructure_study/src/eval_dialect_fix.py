#!/usr/bin/env python3
"""Zero-token re-score of saved M3 SQL after deterministic dialect normalisation.
Only questions whose SQL changes are re-executed. Usage: eval_dialect_fix.py [340|full]
"""
import json
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dialect_fix import normalize_sqlite

OUT = os.path.join(HERE, "..", "outputs")
DBR = os.path.join(HERE, "..", "..", "llm", "data", "dev_databases")
TAG = sys.argv[1] if len(sys.argv) > 1 else "340"
assert TAG in ("340", "full")
LIMIT = 10.0


def ex(db, pred, gold):
    con = sqlite3.connect(os.path.join(DBR, db, db + ".sqlite"))
    t0 = time.time()
    con.set_progress_handler(lambda: 1 if time.time() - t0 > LIMIT else 0, 10000)
    try:
        cur = con.cursor()
        cur.execute(pred)
        a = set(cur.fetchall())
        cur.execute(gold)
        b = set(cur.fetchall())
        return int(a == b)
    except Exception:
        return 0
    finally:
        con.close()


def main():
    rows = json.load(open(os.path.join(OUT, f"results_{TAG}.json")))
    pred = json.load(open(os.path.join(OUT, f"m3_predict_{TAG}.json")))
    det = {int(k): v for k, v in json.load(open(os.path.join(OUT, f"m3_eval_{TAG}.json")))["m3"].items()}
    changed = fixed = broke = 0
    new_ex = 0
    for r in rows:
        i = r["idx"]
        sql = pred.get(str(i), {}).get("sql") or ""
        d = det.get(i, 0)
        if not sql:
            new_ex += d
            continue
        sql2 = normalize_sqlite(sql)
        if sql2 == sql:
            new_ex += d
            continue
        changed += 1
        e = ex(r["db_id"], sql2, r["gold"])
        new_ex += e
        if e == 1 and d == 0:
            fixed += 1
        if e == 0 and d == 1:
            broke += 1
            print("BROKE", i, r["db_id"])
        if e != d:
            print(f"idx {i} {r['db_id']} det={d} new={e}")
    n = len(rows)
    print(f"\n[{TAG}] SQL changed by normaliser: {changed}")
    print(f"[{TAG}] fixed {fixed}  broke {broke}  net {fixed - broke:+d}")
    print(f"[{TAG}] EX deterministic {sum(det.values())/n*100:.2f} -> with dialect fix {new_ex/n*100:.2f}")


if __name__ == "__main__":
    main()
