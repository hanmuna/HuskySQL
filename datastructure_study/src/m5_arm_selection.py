"""Where the remaining headroom is: choosing between the two arms, per question.

The router (m4) only fires on gold-free error signals and captures 1-3 EX points,
while the per-question arm oracle sits 3-10 points above it. This measures the
structure of that gap before any selector is built.

Three questions, all answered from saved runs (zero token):
  1. How often do the free-SQL arm and the compiled-IR arm return the same result?
     When they agree, how often are they right? Agreement that implies correctness
     means the whole decision problem collapses onto the disagreement set.
  2. On disagreements, who is right -- and how much is actually winnable.
  3. Do two tiebreaks derived from this project's own findings work:
       narrower  -- prefer the result with fewer columns (over-selection is the
                    dominant failure mode, so the wider result is the suspect)
       shape     -- the IR declares its intent, so the compiled result can be
                    checked against it: a lone aggregate must yield 1 row x 1 col.
                    The free-SQL arm has no declaration to check against.

Usage:  llm/.venv/bin/python src/m5_arm_selection.py
Writes: outputs/m5_arm_selection.json
"""

import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from func_timeout import FunctionTimedOut, func_timeout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_ROOT = os.path.join(os.path.dirname(ROOT), "llm", "data", "dev_databases")
OUT = os.path.join(ROOT, "outputs")
TIMEOUT = 30

ARMS = {
    "gpt-5.2": ("results_340.json", "m3_predict_340.json"),
    "gpt-4.1-mini": (
        "xmodel_gpt-4.1-mini_baseline_340.json",
        "xmodel_gpt-4.1-mini_m3_340.json",
    ),
    "claude-sonnet-4.5": (
        "xmodel_claude-sonnet-4.5_baseline_340.json",
        "xmodel_claude-sonnet-4.5_m3_340.json",
    ),
    "deepseek-chat": (
        "xmodel_deepseek-chat_baseline_340.json",
        "xmodel_deepseek-chat_m3_340.json",
    ),
    "qwen3-coder-480b-a35b-instruct": (
        "xmodel_qwen3-coder-480b-a35b-instruct_baseline_340.json",
        "xmodel_qwen3-coder-480b-a35b-instruct_m3_340.json",
    ),
}

AGGS = ("COUNT", "SUM", "AVG", "MIN", "MAX", "TOTAL")


def _rows(sql, dbp):
    con = sqlite3.connect(dbp)
    try:
        return con.cursor().execute(sql).fetchall()
    finally:
        con.close()


def result(sql, dbp):
    """(ok, rows) -- rows is None when the query cannot be executed."""
    if not sql or not sql.strip():
        return False, None
    try:
        return True, func_timeout(TIMEOUT, _rows, args=(sql, dbp))
    except (FunctionTimedOut, Exception):
        return False, None


def ncols(rows):
    return len(rows[0]) if rows else 0


def declares_scalar(ir):
    """IR says the answer is a single aggregate: exactly one select item, that item
    is an aggregate, and nothing partitions the output."""
    if not isinstance(ir, dict):
        return False
    sel = ir.get("select") or []
    if len(sel) != 1 or ir.get("group_by"):
        return False
    it = sel[0]
    if isinstance(it, dict):
        return str(it.get("fn", "")).upper() in AGGS
    return isinstance(it, str) and any(
        it.strip().upper().startswith(a + "(") for a in AGGS
    )


def load(fname):
    d = json.load(open(os.path.join(OUT, fname)))
    if fname == "results_340.json":
        return {str(r["idx"]): {"sql": r["pred_kg"]} for r in d}
    return d


def analyse(model, meta):
    base, m3 = (load(f) for f in ARMS[model])

    def one(r):
        i = str(r["idx"])
        dbp = os.path.join(DB_ROOT, r["db_id"], f"{r['db_id']}.sqlite")
        bok, brows = result((base.get(i) or {}).get("sql", ""), dbp)
        rec = m3.get(i) or {}
        mok, mrows = result(rec.get("sql", ""), dbp)
        gok, grows = result(r["gold"], dbp)
        gset = set(grows) if gok else None

        return {
            "idx": r["idx"],
            "ex_base": int(bok and gset is not None and set(brows) == gset),
            "ex_m3": int(mok and gset is not None and set(mrows) == gset),
            "both_ran": bok and mok,
            "agree": bool(bok and mok and set(brows) == set(mrows)),
            "cols_base": ncols(brows) if bok else -1,
            "cols_m3": ncols(mrows) if mok else -1,
            "ir_scalar": declares_scalar(rec.get("ir")),
            "m3_is_scalar": bool(mok and len(mrows) == 1 and ncols(mrows) == 1),
        }

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(one, meta))


def main():
    meta = json.load(open(os.path.join(OUT, "results_340.json")))
    out = {}

    for model in ARMS:
        recs = analyse(model, meta)
        n = len(recs)
        agree = [r for r in recs if r["agree"]]
        dis = [r for r in recs if r["both_ran"] and not r["agree"]]
        only_b = [r for r in dis if r["ex_base"] and not r["ex_m3"]]
        only_m = [r for r in dis if r["ex_m3"] and not r["ex_base"]]
        neither = [r for r in dis if not r["ex_base"] and not r["ex_m3"]]

        # tiebreak 1: on disagreement prefer the narrower result. Equal arity decides
        # nothing, but an algorithm still has to commit, so it keeps M3. Scoring
        # max() on those would award the rule oracle credit on exactly the cases it
        # cannot call -- which is how a useless rule comes out looking strong.
        narrower = sum(
            r["ex_m3"] if r["cols_m3"] <= r["cols_base"] else r["ex_base"] for r in dis
        )
        ties = sum(1 for r in dis if r["cols_m3"] == r["cols_base"])
        # tiebreak 2: the IR declared a scalar but the compiled result is not one
        shape_bad = [r for r in recs if r["ir_scalar"] and not r["m3_is_scalar"]]
        shape_bad_wrong = sum(1 for r in shape_bad if not r["ex_m3"])

        out[model] = {
            "agree_n": len(agree),
            "agree_correct": sum(1 for r in agree if r["ex_m3"]),
            "dis_n": len(dis),
            "only_base": len(only_b),
            "only_m3": len(only_m),
            "neither": len(neither),
            "tiebreak_narrower_correct": narrower,
            "tiebreak_narrower_ties": ties,
            "shape_violation_n": len(shape_bad),
            "shape_violation_wrong": shape_bad_wrong,
        }
        print(
            f"\n### {model}"
            f"\nagree {len(agree):>3}/{n}  -> correct {out[model]['agree_correct']:>3}"
            f"  ({out[model]['agree_correct'] / max(1, len(agree)) * 100:.1f}%)"
            f"\ndisagree {len(dis):>3}   base-only {len(only_b):<4}m3-only {len(only_m):<4}"
            f"neither {len(neither)}"
            f"\n  winnable on disagreement: {len(only_b) + len(only_m)}"
            f"  (= {(len(only_b) + len(only_m)) / n * 100:.2f} EX points)"
            f"\n  tiebreak 'narrower result': {narrower}/{len(only_b) + len(only_m)}"
            f" of the winnable  (undecided by width: {ties}, kept M3)"
            f"  [always-M3 scores {len(only_m)}]"
            f"\n  IR declared scalar but result is not: {len(shape_bad)} fired,"
            f" {shape_bad_wrong} of them wrong"
        )

    with open(os.path.join(OUT, "m5_arm_selection.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("\nwrote outputs/m5_arm_selection.json")


if __name__ == "__main__":
    main()
