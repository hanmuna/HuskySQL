"""Step 4: automated clause-level comparison of wrong-prediction vs gold.

Deterministic. For every failed question, diff the pred fingerprint against the
gold fingerprint (recomputed from eval_results.jsonl via sqlglot) and tally which
SQL component differs most often. Outputs a ranked report + CSV.

Outputs:
  outputs/error_breakdown.csv   category,count,pct_of_failures
  outputs/error_report.md       ranked table + example questions per top category
"""
import os
import sys
import csv
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from error_analysis import common, sql_struct


def main():
    rows = common.read_jsonl(os.path.join(common.OUT_DIR, "eval_results.jsonl"))
    failed = [r for r in rows if not r["passed"]]
    n = len(failed)
    if n == 0:
        print("No failures to analyze.")
        return

    cat_count = Counter()
    cat_examples = defaultdict(list)

    for r in failed:
        pred_struct = sql_struct.analyze(r["pred_sql"])
        gold_struct = sql_struct.analyze(r["gold_sql"])

        cats = []
        if not r["pred_sql"].strip():
            cats = ["EMPTY_PRED"]
        elif pred_struct["parse_error"]:
            cats = ["PARSE_ERROR"]
        else:
            cats = sql_struct.diff_categories(pred_struct["fingerprint"], gold_struct["fingerprint"])
            if not cats:
                # executes-but-wrong with identical structure (e.g. value/semantics)
                cats = ["SEMANTIC_EQUAL_STRUCT"]

        for c in cats:
            cat_count[c] += 1
            if len(cat_examples[c]) < 5:
                cat_examples[c].append(r["idx"])

    ranked = cat_count.most_common()

    csv_path = os.path.join(common.OUT_DIR, "error_breakdown.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "count", "pct_of_failures"])
        for cat, c in ranked:
            w.writerow([cat, c, f"{100.0 * c / n:.1f}"])

    md_path = os.path.join(common.OUT_DIR, "error_report.md")
    with open(md_path, "w") as f:
        f.write("# Clause-level error report\n\n")
        f.write(f"- Total questions evaluated: **{len(rows)}**\n")
        f.write(f"- Failed (EX=0): **{n}**  ({100.0 * n / len(rows):.1f}%)\n")
        f.write(f"- EX accuracy: **{100.0 * (len(rows) - n) / len(rows):.2f}%**\n\n")
        f.write("A failure can differ in multiple clauses, so percentages sum to >100%.\n\n")
        f.write("| Rank | Category | Failures w/ diff | % of failures | Example idx |\n")
        f.write("|------|----------|------------------|---------------|-------------|\n")
        for i, (cat, c) in enumerate(ranked, 1):
            ex = ", ".join(str(x) for x in cat_examples[cat])
            f.write(f"| {i} | {cat} | {c} | {100.0 * c / n:.1f}% | {ex} |\n")
        f.write("\n## Category legend\n\n")
        f.write("`PARSE_ERROR` pred didn't parse · `EMPTY_PRED` no SQL produced · "
                "`SEMANTIC_EQUAL_STRUCT` same structure but wrong result (value/literal/semantics).\n")
        f.write("Others = the pred's clause structurally differs from gold "
                "(see error_analysis/METHODOLOGY.md for definitions).\n")

    print(f"Failures: {n}/{len(rows)}  (EX {100.0 * (len(rows) - n) / len(rows):.2f}%)")
    print("Top clause-level error categories:")
    for cat, c in ranked[:8]:
        print(f"  {cat:22} {c:4}  ({100.0 * c / n:.1f}%)")
    print(f"\nWrote {csv_path}\nWrote {md_path}")


if __name__ == "__main__":
    main()
