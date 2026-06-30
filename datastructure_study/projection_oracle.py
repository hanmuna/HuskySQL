#!/usr/bin/env python3
"""Zero-token upper-bound test of the M3 hypothesis.

Claim: many +kg failures are 'logic right, SELECT over-selects columns'. If the
structured pipeline emitted the *minimal* projection (RA's explicit π), those would
flip to correct. We can bound this WITHOUT any model run: for each failing query,
re-run the predicted SQL, and ask whether some column-subprojection of its result
set exactly equals gold's result set. If yes -> a minimal projection would fix it.

This is an UPPER BOUND (oracle picks the right columns); M3 still has to emit them.
"""
import os, json, sqlite3, itertools

HERE = os.path.dirname(__file__)
DBR = os.path.join(HERE, "..", "llm", "data", "dev_databases")
rows = json.load(open(os.path.join(HERE, "outputs", "results_340.json")))
tax = json.load(open(os.path.join(HERE, "outputs", "kg_taxonomy.json")))
bucket_of = {idx: b for b, idxs in tax.items() for idx in idxs}


def run(db, sql):
    try:
        c = sqlite3.connect(os.path.join(DBR, db, db + ".sqlite")).cursor()
        c.execute(sql)
        return c.fetchall(), (len(c.description) if c.description else 0)
    except Exception:
        return None, 0


def projection_fixable(pred_rows, gold_set, m, k):
    """does some ordered k-subset of the m pred columns reproduce gold's set?"""
    if pred_rows is None or m < k or m > 10 or k == 0:
        return False
    pred = pred_rows
    for cols in itertools.permutations(range(m), k):
        proj = {tuple(r[i] for i in cols) for r in pred}
        if proj == gold_set:
            return True
    return False


def main():
    from collections import Counter
    fixable_by_bucket = Counter()
    total_by_bucket = Counter()
    examples = []
    n_fail = 0
    n_fixable = 0
    for r in rows:
        if r["ex_kg"] == 1:
            continue
        n_fail += 1
        b = bucket_of.get(r["idx"], "?")
        total_by_bucket[b] += 1
        g, gk = run(r["db_id"], r["gold"])
        p, pm = run(r["db_id"], r["pred_kg"])
        if g is None or p is None:
            continue
        gold_set = set(g)
        if projection_fixable(p, gold_set, pm, gk):
            n_fixable += 1
            fixable_by_bucket[b] += 1
            if len(examples) < 8:
                examples.append((r["idx"], r["db_id"], b, f"pred {pm} cols -> gold {gk} cols"))

    print(f"=== Projection-oracle upper bound on {n_fail} +kg failures ===")
    print(f"projection-fixable (minimal π would flip to correct): {n_fixable}/{n_fail} "
          f"= {n_fixable/n_fail*100:.1f}% of failures")
    cur_correct = sum(r["ex_kg"] for r in rows)
    print(f"EX ceiling if all of them flipped: {cur_correct}/340 -> {cur_correct+n_fixable}/340 "
          f"({cur_correct/340*100:.2f}% -> {(cur_correct+n_fixable)/340*100:.2f}%)")
    print("\nby failure bucket (fixable / total):")
    for b in sorted(total_by_bucket, key=lambda x: -total_by_bucket[x]):
        print(f"  {fixable_by_bucket[b]:3}/{total_by_bucket[b]:<3}  {b}")
    print("\nexamples:")
    for e in examples:
        print(f"  idx{e[0]} [{e[1]}] {e[2]}: {e[3]}")


if __name__ == "__main__":
    main()
