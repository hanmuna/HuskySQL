"""Step 4b: per-question SIDE-BY-SIDE comparison of the three representations
(BNF / AST / relational algebra) between the WRONG prediction and its GOLD SQL.

Joins wrong_pred_analysis.jsonl and gold_analysis.jsonl by idx (no API calls).
Outputs:
  outputs/pairwise_comparison.md   human-readable pred-vs-gold per question
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from error_analysis import common, sql_struct


def _ast_node_diff(pred_prod, gold_prod):
    pc, gc = Counter(pred_prod), Counter(gold_prod)
    pred_only = pc - gc
    gold_only = gc - pc

    def fmt(counter):
        if not counter:
            return "—"
        return ", ".join(f"{k}×{v}" for k, v in counter.most_common())
    return fmt(pred_only), fmt(gold_only)


def main():
    wrong = common.read_jsonl(os.path.join(common.OUT_DIR, "wrong_pred_analysis.jsonl"))
    gold = {r["idx"]: r for r in common.read_jsonl(os.path.join(common.OUT_DIR, "gold_analysis.jsonl"))}

    path = os.path.join(common.OUT_DIR, "pairwise_comparison.md")
    with open(path, "w") as f:
        f.write(f"# Pred vs Gold — pairwise BNF / AST / relational-algebra comparison\n\n")
        f.write(f"{len(wrong)} failed questions. For each: the predicted (wrong) SQL on the left, "
                f"the gold SQL on the right, compared across all three representations.\n\n")

        for w in sorted(wrong, key=lambda r: r["idx"]):
            g = gold.get(w["idx"])
            if g is None:
                continue
            clause_diffs = sql_struct.diff_categories(w["fingerprint"], g["fingerprint"])
            pred_only, gold_only = _ast_node_diff(w["productions"], g["productions"])

            f.write(f"## idx {w['idx']}  ·  {w['db_id']}  ·  {w['difficulty']}\n\n")
            f.write(f"> {w.get('nl_note') or ''}\n\n")

            f.write("**SQL**\n\n")
            f.write(f"```sql\n-- PRED (wrong)\n{w['sql']}\n\n-- GOLD\n{g['sql']}\n```\n\n")

            f.write("**Relational algebra**\n\n")
            f.write(f"- PRED: `{w.get('relational_algebra')}`\n")
            f.write(f"- GOLD: `{g.get('relational_algebra')}`\n\n")

            f.write("**BNF derivation**\n\n")
            f.write(f"```\n# PRED\n{w.get('bnf_derivation')}\n\n# GOLD\n{g.get('bnf_derivation')}\n```\n\n")

            f.write("**AST node-type difference**\n\n")
            f.write(f"- only in PRED: {pred_only}\n")
            f.write(f"- only in GOLD: {gold_only}\n\n")

            f.write(f"**Clause-level diff:** {', '.join(clause_diffs) if clause_diffs else '(structurally equal — semantic/value error)'}\n\n")
            f.write("---\n\n")

    print(f"Wrote pairwise comparison for {len(wrong)} questions -> {path}")


if __name__ == "__main__":
    main()
