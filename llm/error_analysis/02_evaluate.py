"""Step 1b: per-instance execution-accuracy evaluation of the subset.

Reuses evaluation/evaluation_utils.py:execute_sql (run pred & gold, set-compare).
Output: outputs/eval_results.jsonl  (one row per question, with passed flag)
Prints overall EX + by-difficulty breakdown (target ~55%).
"""
import os
import sys
import json
from func_timeout import func_timeout, FunctionTimedOut

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from error_analysis import common
from evaluation import execute_sql  # llm/src/evaluation.py, already does set(pred) == set(gold)

TIMEOUT = 30.0


def score_one(pred_sql, gold_sql, db_path):
    try:
        return func_timeout(
            TIMEOUT, execute_sql,
            args=(pred_sql, gold_sql, db_path),
        )
    except FunctionTimedOut:
        return 0
    except Exception:
        return 0


def main():
    preds = json.load(open(os.path.join(common.OUT_DIR, "predictions.json")))
    data = common.load_dataset()

    rows = []
    for idx_str, val in preds.items():
        idx = int(idx_str)
        rec = data[idx]
        pred_sql = val.split(common.BIRD_SEP)[0].strip()
        gold_sql = rec["SQL"]
        passed = score_one(pred_sql, gold_sql, common.db_path(rec["db_id"]))
        rows.append({
            "idx": idx,
            "question_id": rec["question_id"],
            "db_id": rec["db_id"],
            "difficulty": rec["difficulty"],
            "passed": passed,
            "pred_sql": pred_sql,
            "gold_sql": gold_sql,
            "question": rec["question"],
            "evidence": rec.get("evidence", ""),
        })

    rows.sort(key=lambda r: r["idx"])
    common.write_jsonl(os.path.join(common.OUT_DIR, "eval_results.jsonl"), rows)

    def acc(subset):
        return 100.0 * sum(r["passed"] for r in subset) / len(subset) if subset else 0.0

    by = {d: [r for r in rows if r["difficulty"] == d] for d in ("simple", "moderate", "challenging")}
    print(f"Total: {len(rows)}  EX = {acc(rows):.2f}%")
    for d in ("simple", "moderate", "challenging"):
        print(f"  {d:12} n={len(by[d]):3}  EX = {acc(by[d]):.2f}%")
    print(f"Wrote eval_results.jsonl ({sum(1 for r in rows if not r['passed'])} failures)")


if __name__ == "__main__":
    main()
