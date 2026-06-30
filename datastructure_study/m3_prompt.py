#!/usr/bin/env python3
"""M3 IR prompt protocol. General: schema DDL, FK hints, and enum value hints are
all derived live from the sqlite file, so it works for ANY database (not the 3 study
DBs). The model is asked to emit the RA IR (JSON) consumed by ra_to_sql.py, with the
projection forced to be MINIMAL — the structural lever against over-selection.
"""
import sqlite3

## TODO: Group by
IR_SPEC = '''You must answer ONLY with a JSON object in this Relational-Algebra IR (no prose, no markdown):
{
  "from": "<table>",                       // base table (or a raw "(SELECT ...) AS x")
  "joins": [{"table":"<t>","on":["<t1.col>","<t2.col>"]}],   // [] if none; use the FK hints
  "select": [ "<table.col>",               // EXPLICIT, MINIMAL projection
              {"fn":"COUNT","arg":"<table.col>|*","distinct":false},   // aggregate
              {"expr":"<raw scalar SQL>","as":"r"} ],          // ratio / CASE / CAST
  "where": "<raw SQL predicate>",          // optional
  "group_by": ["<table.col or raw expr>"], // optional
  "having": "<raw SQL>",                   // optional
  "order_by": [{"by":"<table.col or raw expr>","desc":true}], // optional
  "limit": <int>,                          // optional
  "distinct": false
}
RULES:
- "select" must contain ONLY the columns/expressions the question asks for — nothing
  extra (no id/name columns "for context"). This is the most important rule.
- Use the exact column names from the schema (quote-sensitive names go in expr/where as-is).
- Use the FK hints below for join keys. Match question phrases to real values via the value hints.'''


def schema_block(db_path):
    con = sqlite3.connect(db_path); cur = con.cursor()
    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name<>'sqlite_sequence'")]
    ddl = []
    for t in tables:
        ddl.append(cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()[0])
    fks = []
    for t in tables:
        for r in cur.execute(f"PRAGMA foreign_key_list('{t}')"):
            fks.append(f"{t}.{r[3]} -> {r[2]}.{r[4]}")
    # enum value hints: small-distinct text columns (live-computed, capped)
    hints = []
    for t in tables:
        for c in cur.execute(f"PRAGMA table_info('{t}')").fetchall():
            name, ctype = c[1], (c[2] or "").upper()
            if "CHAR" in ctype or "TEXT" in ctype or ctype == "":
                try:
                    nd = cur.execute(f'SELECT COUNT(DISTINCT "{name}") FROM "{t}"').fetchone()[0]
                except Exception:
                    continue
                if 0 < nd <= 15:
                    vals = [str(r[0]) for r in cur.execute(
                        f'SELECT DISTINCT "{name}" FROM "{t}" WHERE "{name}" IS NOT NULL LIMIT 15')]
                    hints.append(f"{t}.{name} in {{{', '.join(repr(v) for v in vals)}}}")
    con.close()
    out = "\n\n".join(ddl)
    if fks:
        out += "\n\n-- Foreign keys (join hints):\n" + "\n".join("-- " + f for f in fks)
    if hints:
        out += "\n\n-- Value hints (categorical columns):\n" + "\n".join("-- " + h for h in hints[:40])
    return out


def build_ir_prompt(db_path, question, evidence=""):
    p = schema_block(db_path) + "\n\n" + IR_SPEC + "\n"
    if evidence and evidence.strip():
        p += f"\n-- External Knowledge: {evidence}"
    p += f"\n-- Question: {question}\nJSON IR:"
    return p
