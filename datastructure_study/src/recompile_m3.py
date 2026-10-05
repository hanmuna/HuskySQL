#!/usr/bin/env python3
"""Zero-token recompile of saved M3 IRs with the current ra_to_sql.

Reads outputs/m3_predict_{tag}.json (IR per question, from the paid run),
recompiles every valid IR with the current compiler, re-executes only the SQL
that changed, and compares against the stored M3 correctness. No API calls.
Writes outputs/m3_recompiled_{tag}.json; existing m3_predict/m3_eval are left alone.

Usage: recompile_m3.py [340|full]
"""
import json
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ra_to_sql import ra_to_sql

OUT = os.path.join(HERE, "..", "outputs")
DBR = os.path.join(HERE, "..", "..", "llm", "data", "dev_databases")
TAG = sys.argv[1] if len(sys.argv) > 1 else "340"
assert TAG in ("340", "full"), "usage: recompile_m3.py [340|full]"
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
    stored = {int(k): v for k, v in json.load(open(os.path.join(OUT, f"m3_eval_{TAG}.json")))["m3"].items()}

    out, n_changed, n_compile_err, fixed, broke, new_ex = {}, 0, 0, 0, 0, 0
    for r in rows:
        i = r["idx"]
        p = pred.get(str(i), {})
        old_sql = p.get("sql") or ""
        old = stored.get(i, 0)
        new_sql, err = "", None
        if p.get("ir"):
            try:
                new_sql = ra_to_sql(p["ir"])
            except Exception as e:
                err = str(e)[:120]
                n_compile_err += 1
        if new_sql and new_sql != old_sql:
            n_changed += 1
            e = ex(r["db_id"], new_sql, r["gold"])
        else:
            e = old
        new_ex += e
        fixed += e == 1 and old == 0
        broke += e == 0 and old == 1
        out[str(i)] = {"sql": new_sql, "sql_changed": new_sql != old_sql and bool(new_sql),
                       "ex": e, "ex_stored": old, "err": err}

    with open(os.path.join(OUT, f"m3_recompiled_{TAG}.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    n = len(rows)
    print(f"[{TAG}] IRs recompiled: {sum(1 for v in pred.values() if v.get('ir'))}")
    print(f"[{TAG}] SQL changed vs stored: {n_changed}   compile errors: {n_compile_err}")
    print(f"[{TAG}] flips vs stored M3: fixed {fixed}  broke {broke}  net {fixed - broke:+d}")
    print(f"[{TAG}] EX stored M3 {sum(stored.values())/n*100:.2f} -> recompiled {new_ex/n*100:.2f}")


if __name__ == "__main__":
    main()
