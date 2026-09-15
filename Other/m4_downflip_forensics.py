"""Forensics on M3 down-flips, plus a zero-token literal-grounding repair pass.

Question: the two negative cross-model runs (deepseek, qwen) each lose ~38 questions
that their own free-SQL baseline got right. How many of those losses are detectable
*without* the gold query -- i.e. how much of the "format tax" is mechanical rather
than genuine semantic drift?

Detectors run on the compiled SQL only (no gold, no extra LLM call):
  exec_err        execution raises or times out
  empty           runs but returns zero rows
  lit_not_found   `table.col = 'value'` where that value does not occur in the column
  agg_no_group    aggregate mixed with a bare column and no GROUP BY
  type_mismatch   numeric column compared to a non-numeric quoted literal

lit_not_found also carries a repair: snap the literal to the unique existing value
that matches case-insensitively (or after trimming). Repaired SQL is re-executed so
the yield is measured, not assumed.

Usage:  llm/.venv/bin/python src/m4_downflip_forensics.py [--models a,b]
Writes: outputs/m4_downflip_forensics.json
"""

import json
import os
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor

from func_timeout import FunctionTimedOut, func_timeout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_ROOT = os.path.join(os.path.dirname(ROOT), "llm", "data", "dev_databases")
OUT = os.path.join(ROOT, "outputs")
TIMEOUT = 30
WORKERS = 8

# model -> (baseline predictions, m3 predictions); gpt-5.2 predates the xmodel runner
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

AGG = re.compile(r"\b(COUNT|SUM|AVG|MIN|MAX|TOTAL)\s*\(", re.I)
EQ_LIT = re.compile(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*(=|!=|<>)\s*'((?:[^']|'')*)'")


def dbpath(db_id):
    return os.path.join(DB_ROOT, db_id, f"{db_id}.sqlite")


def _rows(sql, dbp):
    con = sqlite3.connect(dbp)
    try:
        return con.cursor().execute(sql).fetchall()
    finally:
        con.close()


def run(sql, dbp):
    """(status, rows) where status is ok | err | timeout."""
    if not sql or not sql.strip():
        return "err", []
    try:
        return "ok", func_timeout(TIMEOUT, _rows, args=(sql, dbp))
    except FunctionTimedOut:
        return "timeout", []
    except Exception:
        return "err", []


def ex(pred, gold, dbp):
    ps, pr = run(pred, dbp)
    if ps != "ok":
        return 0
    gs, gr = run(gold, dbp)
    return 1 if gs == "ok" and set(pr) == set(gr) else 0


# ---------------------------------------------------------------- detectors


def split_top(s, sep=","):
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == sep and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def agg_no_group(sql):
    m = re.search(r"^\s*SELECT\s+(?:DISTINCT\s+)?(.*?)\s+FROM\s", sql, re.I | re.S)
    if not m or re.search(r"\bGROUP\s+BY\b", sql, re.I):
        return False
    items = [i.strip() for i in split_top(m.group(1)) if i.strip()]
    if len(items) < 2:
        return False
    has_agg = any(AGG.search(i) for i in items)
    has_bare = any(not AGG.search(i) for i in items)
    return has_agg and has_bare


def literals(sql):
    """[(table, column, op, value, matched_text)] for equality-on-string predicates."""
    return [
        (m.group(1), m.group(2), m.group(3), m.group(4).replace("''", "'"), m.group(0))
        for m in EQ_LIT.finditer(sql)
    ]


def col_type(profile, table, col):
    return (profile.get(f"{table}.{col}") or {}).get("type", "")


def type_mismatch(sql, profile):
    for table, col, _op, val, _txt in literals(sql):
        t = col_type(profile, table, col).upper()
        if t.startswith(("INT", "REAL", "NUM", "FLOAT", "DOUBLE", "DEC")):
            try:
                float(val)
            except ValueError:
                return True
    return False


def _exists(dbp, table, col, val):
    q = f'SELECT 1 FROM "{table}" WHERE "{col}" = ? LIMIT 1'
    con = sqlite3.connect(dbp)
    try:
        return con.cursor().execute(q, (val,)).fetchone() is not None
    except Exception:
        return None  # column/table unresolvable here (alias, subquery scope): skip
    finally:
        con.close()


def _snap(dbp, table, col, val):
    """Unique existing value matching case-insensitively / after trimming, else None."""
    con = sqlite3.connect(dbp)
    try:
        cur = con.cursor()
        for q in (
            f'SELECT DISTINCT "{col}" FROM "{table}" WHERE lower("{col}") = lower(?) LIMIT 3',
            f'SELECT DISTINCT "{col}" FROM "{table}" WHERE lower(trim("{col}")) = lower(trim(?)) LIMIT 3',
        ):
            try:
                hits = [r[0] for r in cur.execute(q, (val,)).fetchall()]
            except Exception:
                return None
            if len(hits) == 1 and isinstance(hits[0], str):
                return hits[0]
        return None
    finally:
        con.close()


def ground_literals(sql, dbp):
    """(repaired_sql, n_missing, n_repaired). Pure compiler pass, no gold, no LLM."""
    missing = repaired = 0
    out = sql
    for table, col, op, val, txt in literals(sql):
        found = _exists(dbp, table, col, val)
        if found is not False:
            continue
        missing += 1
        fix = _snap(dbp, table, col, val)
        if fix is not None:
            repaired += 1
            out = out.replace(txt, f"{table}.{col} {op} '{fix}'", 1)
    return out, missing, repaired


# ---------------------------------------------------------------- per model


def load(fname):
    d = json.load(open(os.path.join(OUT, fname)))
    if fname == "results_340.json":  # baseline for gpt-5.2 lives in the master file
        return {str(r["idx"]): {"sql": r["pred_kg"]} for r in d}
    return d


def analyse(model, meta, profiles):
    base, m3 = (load(f) for f in ARMS[model])
    recs = []

    def one(r):
        i = str(r["idx"])
        dbp = dbpath(r["db_id"])
        prof = profiles[r["db_id"]]
        bsql = (base.get(i) or {}).get("sql", "")
        rec3 = m3.get(i) or {}
        msql = rec3.get("sql", "")
        compiled = bool(rec3.get("compile_ok", True)) and bool(msql)

        ex_b = ex(bsql, r["gold"], dbp)
        ex_m = ex(msql, r["gold"], dbp)
        gstatus, grows = run(r["gold"], dbp)
        gold_n = len(grows) if gstatus == "ok" else -1
        status, rows = run(msql, dbp) if compiled else ("err", [])
        fixed, n_missing, n_fixed = (
            ground_literals(msql, dbp) if compiled else (msql, 0, 0)
        )
        ex_fix = ex(fixed, r["gold"], dbp) if n_fixed else ex_m

        return {
            "idx": r["idx"],
            "db": r["db_id"],
            "ex_base": ex_b,
            "ex_m3": ex_m,
            "ex_m3_grounded": ex_fix,
            "compiled": compiled,
            "exec_err": status != "ok",
            # kept separate: a timeout is a resource artifact, a syntax/schema error
            # is a real defect, and collapsing them hides which one a gain came from
            "exec_status": status,
            "empty": status == "ok" and len(rows) == 0,
            # gold's own row count -- without it, "an empty result is always wrong"
            # is an unfalsifiable claim about the benchmark
            "gold_rows": gold_n,
            "lit_missing": n_missing,
            "lit_repaired": n_fixed,
            "agg_no_group": compiled and agg_no_group(msql),
            "type_mismatch": compiled and type_mismatch(msql, prof),
        }

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        recs = list(pool.map(one, meta))
    recheck(recs, meta, base, m3)
    return recs


def recheck(recs, meta, base, m3):
    """Re-run every exec_err record serially.

    Running WORKERS-way parallel puts enough contention on SQLite that slow-but-
    valid queries hit the 30 s timeout and get scored as failures. Left in, those
    become free wins for any policy that falls back on exec_err. Re-run them one
    at a time and keep the flag only if it survives.
    """
    gold = {r["idx"]: (r["gold"], dbpath(r["db_id"])) for r in meta}
    for rec in recs:
        if not (rec["exec_err"] and rec["compiled"]):
            continue
        g, dbp = gold[rec["idx"]]
        msql = (m3.get(str(rec["idx"])) or {}).get("sql", "")
        if all(run(msql, dbp)[0] != "ok" for _ in range(3)):
            continue
        status, rows = run(msql, dbp)
        rec["exec_err"] = False
        rec["exec_status"] = status
        rec["empty"] = len(rows) == 0
        rec["ex_m3"] = ex(msql, g, dbp)
        if not rec["lit_repaired"]:
            rec["ex_m3_grounded"] = rec["ex_m3"]


def report(model, recs):
    n = len(recs)
    down = [r for r in recs if r["ex_base"] == 1 and r["ex_m3"] == 0]
    dsem = [r for r in down if r["compiled"]]
    dsem_idx = {r["idx"] for r in dsem}
    wrong = [r for r in recs if r["ex_m3"] == 0 and r["compiled"]]

    def stat(key):
        fires = [r for r in recs if r[key]]
        if not fires:
            return (0, 0.0, 0.0)
        bad = sum(1 for r in fires if r["ex_m3"] == 0)
        hit = sum(1 for r in fires if r["idx"] in dsem_idx)
        return (len(fires), bad / len(fires), hit / len(dsem) if dsem else 0.0)

    ex_b = sum(r["ex_base"] for r in recs) / n * 100
    ex_m = sum(r["ex_m3"] for r in recs) / n * 100
    ex_g = sum(r["ex_m3_grounded"] for r in recs) / n * 100

    lines = [
        f"\n### {model}",
        f"EX  baseline {ex_b:5.2f}  |  M3 {ex_m:5.2f}  ({ex_m - ex_b:+.2f})"
        f"  |  M3+grounding {ex_g:5.2f}  ({ex_g - ex_m:+.2f})",
        f"down-flips {len(down)} (compiled: {len(dsem)})   M3 wrong+compiled {len(wrong)}",
        f"{'detector':<16}{'fires':>6}{'precision':>11}{'downflip recall':>17}",
    ]
    for k in ("exec_err", "empty", "agg_no_group", "type_mismatch"):
        f, p, rc = stat(k)
        lines.append(f"{k:<16}{f:>6}{p:>10.2f}{rc:>16.2f}")
    fires = [r for r in recs if r["lit_missing"]]
    bad = sum(1 for r in fires if r["ex_m3"] == 0)
    hit = sum(1 for r in fires if r["idx"] in dsem_idx)
    lines.append(
        f"{'lit_not_found':<16}{len(fires):>6}"
        f"{(bad / len(fires) if fires else 0):>10.2f}"
        f"{(hit / len(dsem) if dsem else 0):>16.2f}"
    )
    rep = [r for r in recs if r["lit_repaired"]]
    gained = [r for r in rep if r["ex_m3"] == 0 and r["ex_m3_grounded"] == 1]
    lost = [r for r in rep if r["ex_m3"] == 1 and r["ex_m3_grounded"] == 0]
    lines.append(
        f"grounding repair: fired {len(rep)}  fixed {len(gained)}  broke {len(lost)}"
        f"  idx fixed {[r['idx'] for r in gained][:12]}"
    )
    return "\n".join(lines), {
        "ex_base": ex_b,
        "ex_m3": ex_m,
        "ex_m3_grounded": ex_g,
        "down": [r["idx"] for r in down],
        "down_compiled": [r["idx"] for r in dsem],
        "grounding_fixed": [r["idx"] for r in gained],
        "grounding_broke": [r["idx"] for r in lost],
    }


def main():
    models = list(ARMS)
    if len(sys.argv) > 2 and sys.argv[1] == "--models":
        models = sys.argv[2].split(",")
    meta = json.load(open(os.path.join(OUT, "results_340.json")))
    profiles = {}
    for db in {r["db_id"] for r in meta}:
        profiles[db] = json.load(open(os.path.join(ROOT, "structures", f"{db}.json")))[
            "profile"
        ]

    summary, per_model = [], {}
    for m in models:
        recs = analyse(m, meta, profiles)
        text, s = report(m, recs)
        print(text, flush=True)
        summary.append(text)
        per_model[m] = {"summary": s, "records": recs}

    with open(os.path.join(OUT, "m4_downflip_forensics.json"), "w") as f:
        json.dump(per_model, f, indent=1)
    print("\nwrote outputs/m4_downflip_forensics.json")


if __name__ == "__main__":
    main()
