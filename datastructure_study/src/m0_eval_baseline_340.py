#!/usr/bin/env python3
"""Self-contained EX + VES evaluation of the FIRST 340 dev queries
(california_schools + financial + toxicology, clean DB boundaries),
for both the with-knowledge and without-knowledge baseline predictions.

Reuses the exact EX logic (set equality) and VES logic (sqrt(time_ratio)*100
with outlier trimming) from llm/src/evaluation.py and evaluation_ves.py.
No API calls — pure local sqlite execution. Run once; dumps results_340.json.
"""
import os, sys, json, time, math, sqlite3
import numpy as np
import multiprocessing as mp
from func_timeout import func_timeout, FunctionTimedOut

N = 340
ITER = 20  # VES iterations per query (official uses 100; 20 is stable enough and faster)
TIMEOUT = 30.0
NCPU = 8

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "llm")
DB_ROOT = os.path.join(ROOT, "data", "dev_databases")
DEV = os.path.join(ROOT, "data", "dev.json")
GOLD = os.path.join(ROOT, "data", "dev_gold.sql")
PRED_KG = os.path.join(ROOT, "exp_result", "gpt52_output_kg", "predict_dev.json")
PRED_NOKG = os.path.join(ROOT, "exp_result", "gpt52_output", "predict_dev.json")


def db_path(db_id):
    return os.path.join(DB_ROOT, db_id, db_id + ".sqlite")


def load_pred(path):
    d = json.load(open(path))
    out = {}
    for k, v in d.items():
        if isinstance(v, str) and "\t----- bird -----\t" in v:
            sql = v.split("\t----- bird -----\t")[0]
        else:
            sql = v if isinstance(v, str) else " "
        out[int(k)] = sql
    return out


# ---- EX ----
def ex_sql(pred, gold, dbp):
    conn = sqlite3.connect(dbp)
    cur = conn.cursor()
    cur.execute(pred)
    pr = cur.fetchall()
    cur.execute(gold)
    gr = cur.fetchall()
    return 1 if set(pr) == set(gr) else 0


def ex_one(args):
    idx, pred, gold, dbp = args
    try:
        return idx, func_timeout(TIMEOUT, ex_sql, args=(pred, gold, dbp))
    except (FunctionTimedOut, Exception):
        return idx, 0


# ---- VES ----
def _clean(inp):
    inp = np.asarray(inp)
    m, s = np.mean(inp), np.std(inp)
    return [x for x in inp if m - 3 * s < x < m + 3 * s]


def _exec_time(sql, dbp):
    conn = sqlite3.connect(dbp)
    cur = conn.cursor()
    t = time.time()
    cur.execute(sql)
    return time.time() - t


def ves_sql(pred, gold, dbp, it):
    conn = sqlite3.connect(dbp)
    cur = conn.cursor()
    cur.execute(pred); pr = cur.fetchall()
    cur.execute(gold); gr = cur.fetchall()
    if set(pr) != set(gr):
        return 0.0
    diffs = []
    for _ in range(it):
        pt = _exec_time(pred, dbp)
        gt = _exec_time(gold, dbp)
        diffs.append(gt / pt if pt > 0 else 0)
    cl = _clean(diffs)
    return sum(cl) / len(cl) if cl else 0.0


def ves_one(args):
    idx, pred, gold, dbp = args
    try:
        return idx, func_timeout(TIMEOUT * ITER, ves_sql, args=(pred, gold, dbp, ITER))
    except (FunctionTimedOut, Exception):
        return idx, 0.0


def main():
    dev = json.load(open(DEV))[:N]
    gold_lines = open(GOLD).read().splitlines()
    gold = {}
    for i, line in enumerate(gold_lines[:N]):
        sql, _db = line.strip().split("\t")
        gold[i] = sql
    pred_kg = load_pred(PRED_KG)
    pred_nokg = load_pred(PRED_NOKG)

    rows = []
    for i in range(N):
        d = dev[i]
        rows.append({
            "idx": i,
            "db_id": d["db_id"],
            "difficulty": d["difficulty"],
            "has_evidence": bool(d.get("evidence", "").strip()),
            "question": d["question"],
            "evidence": d.get("evidence", ""),
            "gold": gold[i],
            "pred_kg": pred_kg.get(i, ""),
            "pred_nokg": pred_nokg.get(i, ""),
        })

    for tag, predmap in [("kg", pred_kg), ("nokg", pred_nokg)]:
        ex_args = [(i, predmap.get(i, ""), gold[i], db_path(rows[i]["db_id"])) for i in range(N)]
        with mp.Pool(NCPU) as p:
            for idx, res in p.map(ex_one, ex_args):
                rows[idx]["ex_" + tag] = res
        print(f"EX {tag} done", file=sys.stderr)

        ves_args = [(i, predmap.get(i, ""), gold[i], db_path(rows[i]["db_id"])) for i in range(N)]
        with mp.Pool(NCPU) as p:
            for idx, res in p.map(ves_one, ves_args):
                rows[idx]["ves_" + tag] = res
        print(f"VES {tag} done", file=sys.stderr)

    out_dir = os.path.join(os.path.dirname(__file__), "..", "outputs")
    os.makedirs(out_dir, exist_ok=True)
    json.dump(rows, open(os.path.join(out_dir, "results_340.json"), "w"),
              indent=2, ensure_ascii=False)

    # ---- aggregates ----
    def agg(sub, tag):
        ex = sum(r["ex_" + tag] for r in sub) / len(sub) * 100
        ves = sum(math.sqrt(r["ves_" + tag]) * 100 for r in sub) / len(sub)
        return ex, ves

    def report():
        print("=" * 70)
        print(f"{'group':28} {'n':>4} {'EX_kg':>7} {'EX_no':>7} {'VES_kg':>7} {'VES_no':>7}")
        print("-" * 70)
        groups = [("ALL", rows)]
        for db in dict.fromkeys(r["db_id"] for r in rows):
            groups.append((db, [r for r in rows if r["db_id"] == db]))
        for diff in ["simple", "moderate", "challenging"]:
            groups.append(("diff:" + diff, [r for r in rows if r["difficulty"] == diff]))
        groups.append(("has_evidence", [r for r in rows if r["has_evidence"]]))
        groups.append(("no_evidence", [r for r in rows if not r["has_evidence"]]))
        for name, sub in groups:
            exk, vesk = agg(sub, "kg")
            exn, vesn = agg(sub, "nokg")
            print(f"{name:28} {len(sub):>4} {exk:>7.2f} {exn:>7.2f} {vesk:>7.2f} {vesn:>7.2f}")
        print("=" * 70)

    report()


if __name__ == "__main__":
    main()
