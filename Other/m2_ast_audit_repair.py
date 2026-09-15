#!/usr/bin/env python3
"""M2: AST/BNF coverage audit + schema-validity audit + gold-blind repair on the
340 with-knowledge predictions. Zero token (transforms existing outputs only).

- BNF coverage: can sqlglot parse it? (syntactic validity a grammar decoder guarantees)
- schema audit: references to non-existent table/column, ambiguous unqualified column
- repair (gold-blind, no gold used): non-existent qualified column -> nearest real
  column in the referenced table (what a schema-aware post-processor / PICARD does)
- re-run EX original vs repaired on 340; report delta + change log
"""
import os, json, sqlite3, math, difflib
import sqlglot
from sqlglot import exp

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "outputs")
DBR = os.path.join(HERE, "..", "..", "llm", "data", "dev_databases")
N = 340
DBS = ["california_schools", "financial", "toxicology"]

struct = {db: json.load(open(os.path.join(HERE, "..", "structures", db + ".json"))) for db in DBS}
# schema: {db: {table_lower: {col_lower: real_col}}}
schema = {}
for db, s in struct.items():
    schema[db] = {}
    for t, cols in s["columns_by_table"].items():
        schema[db][t.lower()] = {c.lower(): c for c in cols}


def db_path(db): return os.path.join(DBR, db, db + ".sqlite")


def alias_map(ast):
    m = {}
    for tbl in ast.find_all(exp.Table):
        real = tbl.name
        m[real.lower()] = real
        if tbl.alias:
            m[tbl.alias.lower()] = real
    return m


def audit_and_repair(sql, db):
    """returns dict(parseable, bad_cols, ambig_cols, repaired_sql or None, changes[])"""
    res = {"parseable": False, "bad_cols": [], "ambig_cols": [], "repaired": None, "changes": []}
    try:
        ast = sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return res
    res["parseable"] = True
    sch = schema[db]
    am = alias_map(ast)
    # output aliases (SELECT x AS foo) and derived-table names are NOT base columns;
    # excluding them avoids false "non-existent column" flags on ORDER BY/HAVING refs.
    defined = {a.alias.lower() for a in ast.find_all(exp.Alias) if a.alias}
    derived = {t.alias.lower() for t in ast.find_all(exp.Subquery) if t.alias}
    from_tables = [am.get(t.alias.lower() if t.alias else t.name.lower(), t.name)
                   for t in ast.find_all(exp.Table)]
    changed = False

    def fix(node):
        nonlocal changed
        if not isinstance(node, exp.Column):
            return node
        col = node.name
        qual = node.table  # alias or table string, '' if none
        if qual:
            if qual.lower() in derived:
                return node  # column from a subquery output, not a base column
            real_t = am.get(qual.lower())
            if real_t and real_t.lower() in sch:
                cols = sch[real_t.lower()]
                if col.lower() not in cols:
                    res["bad_cols"].append(f"{qual}.{col}")
                    cand = difflib.get_close_matches(col.lower(), list(cols.keys()), n=1, cutoff=0.6)
                    if cand:
                        newc = cols[cand[0]]
                        res["changes"].append(f"{qual}.{col} -> {qual}.{newc}")
                        changed = True
                        return exp.column(newc, table=qual)
        else:
            # unqualified: is it ambiguous / missing across FROM tables?
            if col.lower() in defined:
                return node  # references a SELECT output alias, not a base column
            owners = [t for t in from_tables if col.lower() in sch.get(t.lower(), {})]
            if len(owners) == 0:
                res["bad_cols"].append(col)
            elif len(owners) > 1:
                res["ambig_cols"].append(col)
        return node

    new_ast = ast.transform(fix)
    if changed:
        try:
            cand_sql = new_ast.sql(dialect="sqlite")
            res["repaired"] = cand_sql
        except Exception:
            res["repaired"] = None
    return res


def ex(pred, gold, dbp):
    try:
        c = sqlite3.connect(dbp).cursor()
        c.execute(pred); pr = c.fetchall()
        c.execute(gold); gr = c.fetchall()
        return 1 if set(pr) == set(gr) else 0
    except Exception:
        return 0


def main():
    rows = json.load(open(os.path.join(OUT, "results_340.json")))[:N]
    n_parse = 0; n_bad = 0; n_ambig = 0; n_repaired = 0
    flip_to_correct = 0; flip_to_wrong = 0
    changelog = []
    repaired_preds = {}
    for r in rows:
        db = r["db_id"]; sql = r["pred_kg"]; gold = r["gold"]; dbp = db_path(db)
        a = audit_and_repair(sql, db)
        n_parse += a["parseable"]
        n_bad += len(a["bad_cols"]); n_ambig += len(a["ambig_cols"])
        final = sql
        if a["repaired"]:
            n_repaired += 1
            before = r["ex_kg"]
            after = ex(a["repaired"], gold, dbp)
            if before == 0 and after == 1: flip_to_correct += 1
            if before == 1 and after == 0: flip_to_wrong += 1
            final = a["repaired"]
            changelog.append({"idx": r["idx"], "db": db, "ex_before": before,
                              "ex_after": after, "changes": a["changes"]})
        repaired_preds[str(r["idx"])] = final

    # EX after repair over all 340
    ex_before = sum(r["ex_kg"] for r in rows) / N * 100
    ex_after = sum(ex(repaired_preds[str(r["idx"])], r["gold"], db_path(r["db_id"]))
                   for r in rows) / N * 100

    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "m2_repaired_predict.json"), "w").write(
        json.dumps(repaired_preds, ensure_ascii=False, indent=1))
    open(os.path.join(OUT, "m2_changes.json"), "w").write(
        json.dumps(changelog, ensure_ascii=False, indent=1))

    print(f"=== M2 audit on {N} kg predictions ===")
    print(f"BNF/sqlglot parseable : {n_parse}/{N} ({n_parse/N*100:.1f}%)")
    print(f"non-existent col refs : {n_bad}")
    print(f"ambiguous unqual cols : {n_ambig}")
    print(f"queries auto-repaired : {n_repaired}")
    print(f"  flipped wrong->right: {flip_to_correct}")
    print(f"  flipped right->wrong: {flip_to_wrong}")
    print(f"EX_kg before repair   : {ex_before:.2f}")
    print(f"EX_kg after  repair   : {ex_after:.2f}  (delta {ex_after-ex_before:+.2f})")
    print("changes:")
    for c in changelog:
        print(f"  idx{c['idx']} [{c['db']}] ex {c['ex_before']}->{c['ex_after']} {c['changes']}")


if __name__ == "__main__":
    main()
