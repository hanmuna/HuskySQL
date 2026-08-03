"""Per-question arm routing from gold-free signals.

The cross-model result says the IR constraint helps some models and hurts others.
That is a *model-level* prescription. This asks whether the same decision can be
made per question, using only signals available at inference time.

Policy: emit the compiled M3 query unless a gold-free detector fires on it
(execution error, empty result, aggregate mixed with a bare column, numeric column
compared to a non-numeric literal, literal absent from the column); in that case
fall back to the model's own free-SQL baseline. Costs two generations per question,
no gold, no judge model.

Reads outputs/m4_downflip_forensics.json (records carry ex_base, ex_m3 and every
detector flag per question), so this is pure arithmetic over saved runs.

Usage:  llm/.venv/bin/python src/m4_router_policy.py
"""

import json
import os
from itertools import combinations

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "outputs")

DETECTORS = ["exec_err", "empty", "agg_no_group", "type_mismatch", "lit_missing"]


def fires(rec, keys):
    return any(bool(rec[k]) for k in keys)


def policy_ex(recs, keys):
    return (
        sum(r["ex_base"] if fires(r, keys) else r["ex_m3"] for r in recs)
        / len(recs)
        * 100
    )


def main():
    data = json.load(open(os.path.join(OUT, "m4_downflip_forensics.json")))

    # which detector subset routes best on average -- reported honestly as a
    # selected-on-the-same-data number, not a held-out one
    subsets = [
        c for n in range(1, len(DETECTORS) + 1) for c in combinations(DETECTORS, n)
    ]

    print(
        f"{'model':<32}{'base':>7}{'M3':>7}{'router':>8}{'vs M3':>7}{'vs base':>8}{'oracle':>8}"
    )
    rows = {}
    for model, blob in data.items():
        recs = blob["records"]
        n = len(recs)
        base = sum(r["ex_base"] for r in recs) / n * 100
        m3 = sum(r["ex_m3"] for r in recs) / n * 100
        oracle = sum(max(r["ex_base"], r["ex_m3"]) for r in recs) / n * 100
        rout = policy_ex(recs, DETECTORS)
        rows[model] = {
            "base": base,
            "m3": m3,
            "router": rout,
            "oracle": oracle,
            "n_routed": sum(1 for r in recs if fires(r, DETECTORS)),
        }
        print(
            f"{model:<32}{base:>7.2f}{m3:>7.2f}{rout:>8.2f}"
            f"{rout - m3:>+7.2f}{rout - base:>+8.2f}{oracle:>8.2f}"
        )

    print("\nper-detector contribution (mean delta over M3, all five models)")
    for d in DETECTORS:
        deltas = [policy_ex(b["records"], [d]) - rows[m]["m3"] for m, b in data.items()]
        print(f"  {d:<16}{sum(deltas) / len(deltas):>+7.2f}")

    best, best_gain = None, -99
    for sub in subsets:
        g = sum(
            policy_ex(b["records"], sub) - rows[m]["m3"] for m, b in data.items()
        ) / len(data)
        if g > best_gain:
            best, best_gain = sub, g
    print(
        f"\nbest subset (fit on these same 5 models): {'+'.join(best)}  mean {best_gain:+.2f}"
    )

    with open(os.path.join(OUT, "m4_router_policy.json"), "w") as f:
        json.dump({"rows": rows, "best_subset": list(best)}, f, indent=1)
    print("wrote outputs/m4_router_policy.json")


if __name__ == "__main__":
    main()
