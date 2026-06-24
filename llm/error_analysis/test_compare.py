"""Deterministic unit tests for the Step-4 clause categorizer (no API needed).

Each case is a (pred, gold) pair that differs in exactly ONE clause; we assert
diff_categories flags precisely that clause and nothing else.
Run: python error_analysis/test_compare.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from error_analysis import sql_struct as S


CASES = [
    # (name, pred_sql, gold_sql, expected_diff_categories)
    ("where_value",
     "SELECT name FROM t WHERE age > 5",
     "SELECT name FROM t WHERE age > 10",
     {"WHERE"}),
    ("group_by_missing",
     "SELECT dept, COUNT(*) FROM t",
     "SELECT dept, COUNT(*) FROM t GROUP BY dept",
     {"GROUP_BY"}),
    ("aggregation_wrong",
     "SELECT SUM(x) FROM t",
     "SELECT COUNT(x) FROM t",
     {"AGGREGATION", "SELECT"}),
    ("order_direction",
     "SELECT name FROM t ORDER BY name ASC",
     "SELECT name FROM t ORDER BY name DESC",
     {"ORDER_BY"}),
    ("limit_diff",
     "SELECT name FROM t ORDER BY name LIMIT 5",
     "SELECT name FROM t ORDER BY name LIMIT 1",
     {"LIMIT"}),
    ("join_condition",
     "SELECT a.x FROM a JOIN b ON a.id = b.id",
     "SELECT a.x FROM a JOIN b ON a.fk = b.id",
     {"JOIN"}),
    ("distinct_missing",
     "SELECT city FROM t",
     "SELECT DISTINCT city FROM t",
     {"DISTINCT"}),
    ("wrong_table",
     "SELECT x FROM a",
     "SELECT x FROM b",
     {"FROM"}),
    ("identical",
     "SELECT x FROM a WHERE y = 1",
     "SELECT x FROM a WHERE y = 1",
     set()),
]


def run():
    failures = 0
    for name, pred, gold, expected in CASES:
        pfp = S.analyze(pred)["fingerprint"]
        gfp = S.analyze(gold)["fingerprint"]
        got = set(S.diff_categories(pfp, gfp))
        ok = got == expected
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: expected={sorted(expected)} got={sorted(got)}")
        if not ok:
            failures += 1
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if run() else 0)
