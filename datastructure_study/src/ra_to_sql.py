#!/usr/bin/env python3
"""M3 core: a small Relational-Algebra IR and a deterministic IR -> SQLite compiler.

The IR is what the model would emit instead of free-form SQL. Its whole point is
that the projection (`select`) is an explicit, minimal list -> the compiler cannot
emit extra descriptive columns, which is the 34% over-selection failure bucket.

IR (JSON):
{
  "from":   "schools",
  "joins":  [{"table":"satscores","on":["schools.CDSCode","satscores.cds"]}],
  "select": ["schools.School", {"fn":"COUNT","arg":"schools.CDSCode","as":"n"}],
  "where":  "schools.Magnet = 1 AND satscores.NumTstTakr > 500",   # raw predicate
  "group_by": ["schools.District"],
  "order_by": [{"by":"satscores.AvgScrRead","desc":true}],
  "limit": 1,
  "distinct": false
}
Only `from` and `select` are required. `where/group_by/order_by/limit` are passed
through (filters/values are the semantic part, not the structural one).
"""

import re


# SQLite keywords that BIRD schemas actually use as table or column names
# (financial.`order` is the one that bites: unquoted it is a syntax error).
RESERVED = {
    "order",
    "group",
    "table",
    "index",
    "key",
    "values",
    "check",
    "default",
    "references",
    "primary",
    "foreign",
    "unique",
    "select",
    "from",
    "where",
    "having",
    "limit",
    "offset",
    "union",
    "join",
    "left",
    "right",
    "natural",
    "cross",
    "inner",
    "outer",
    "on",
    "using",
    "as",
    "by",
    "asc",
    "desc",
    "distinct",
    "all",
    "and",
    "or",
    "not",
    "null",
    "is",
    "in",
    "like",
    "between",
    "case",
    "when",
    "then",
    "else",
    "end",
    "cast",
    "collate",
    "escape",
    "exists",
    "glob",
    "match",
    "regexp",
    "transaction",
    "commit",
    "rollback",
    "release",
    "savepoint",
    "begin",
    "add",
    "column",
    "constraint",
    "create",
    "drop",
    "alter",
    "insert",
    "update",
    "delete",
    "into",
    "set",
    "view",
    "trigger",
    "temp",
    "temporary",
    "if",
    "for",
    "each",
    "row",
    "before",
    "after",
    "instead",
    "of",
    "to",
    "with",
    "recursive",
    "window",
    "over",
    "partition",
    "filter",
    "range",
    "rows",
    "groups",
    "current",
    "following",
    "preceding",
    "unbounded",
    "exclude",
    "others",
    "ties",
    "no",
    "action",
    "cascade",
    "restrict",
    "deferrable",
    "initially",
    "deferred",
    "immediate",
    "conflict",
    "abort",
    "fail",
    "ignore",
    "replace",
    "do",
    "nothing",
    "returning",
}


def q(ident):
    """Quote one identifier part.

    Plain words are left bare for readability, EXCEPT SQLite keywords: a bare
    reserved word in an identifier position is a syntax error, and BIRD's
    financial schema really does have a table called `order`.
    """
    return (
        ident
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", ident)
        and ident.lower() not in RESERVED
        else '"' + ident.replace('"', '""') + '"'
    )


def quote_reserved_refs(sql, tables):
    """Quote bare reserved-word table names in the raw-passthrough clauses.

    `where` / `having` / `order_by` are emitted verbatim by design, so a model
    writing `order.order_id = 1` slips a syntax error past the quoted FROM.
    A keyword immediately followed by `.` is unambiguously an identifier, so
    it is safe to quote every such occurrence.
    """
    for t in tables:
        if t.lower() not in RESERVED:
            continue
        sql = re.sub(rf'(?<!["`\w.]){re.escape(t)}(?=\s*\.)', f'"{t}"', sql)
    return sql


def _q_part(p):
    """quote one identifier part, normalising any pre-existing `backtick`/"quote"."""
    p = p.strip()
    if len(p) >= 2 and p[0] in '`"[' and p[-1] in '`"]':
        p = p[1:-1]
    return q(p)


_SIMPLE = re.compile(
    r'(`[^`]+`|"[^"]+"|\[[^\]]+\]|[A-Za-z_]\w*)'
    r'(\.(`[^`]+`|"[^"]+"|\[[^\]]+\]|[A-Za-z_]\w*))?$'
)


def is_simple_ref(s):
    """True for `t.col` / `col` (optionally already quoted); False for any
    expression (ratios, function calls, parens) that must be emitted raw."""
    return bool(_SIMPLE.fullmatch(s.strip()))


def qcol(tabcol):
    """'table.col' -> "table"."col"; pass through anything that isn't a plain ref."""
    if not is_simple_ref(tabcol):
        return tabcol
    if "." in tabcol and tabcol[0] not in '`"[':
        t, c = tabcol.split(".", 1)
        return f"{_q_part(t)}.{_q_part(c)}"
    return _q_part(tabcol)


def _tbl_alias(spec, alias=None):
    """Render a table reference with optional alias / self-join support.
    Accepts a raw subquery ('(SELECT ...) x'), an inline 'atom AS atom2', a
    plain table name plus an optional separate alias, or a dict
    {"table": ..., "as": ...} (some models emit nested table objects)."""
    if isinstance(spec, dict):
        return _tbl_alias(
            spec.get("table") or spec.get("from"), spec.get("as") or alias
        )
    if "(" in spec:  # raw subquery / expression, pass through
        return spec
    m = re.split(r"\s+AS\s+|\s+", spec.strip(), maxsplit=1, flags=re.I)
    if len(m) == 2 and not alias:
        return f"{_q_part(m[0])} AS {_q_part(m[1])}"
    return _q_part(spec) + (f" AS {_q_part(alias)}" if alias else "")


def _expr(x):
    """A term in any expression position (GROUP BY / ORDER BY / join key / raw
    clause). Accepts a plain string or a select-item-style dict (fn/expr forms,
    which several models emit inside order_by/group_by); the alias is dropped
    because it is illegal mid-expression."""
    if isinstance(x, dict):
        x = dict(x)
        x.pop("as", None)
        return _sel_item(x)
    return _ref(x)


def _ref(s):
    """A GROUP BY / ORDER BY term: a plain table.col is quoted, anything with an
    operator/space/backtick (e.g. a ratio) is passed through raw -> stays general."""
    if isinstance(s, dict):
        return _expr(s)
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?", s):
        return qcol(s)
    return s


def _raw(x):
    """A raw-SQL clause (where/having). Some models emit a dict here instead of
    a string; unwrap its expr form."""
    if isinstance(x, dict):
        return x.get("expr") or _expr(x)
    return x


def _sel_item(it):
    if isinstance(it, str):
        return qcol(it)
    # raw scalar expression escape hatch: ratios, CASE/IIF, CAST, subqueries, etc.
    # keeps the IR general while projection stays an explicit, enumerated list.
    if "expr" in it:
        s = it["expr"]
        if it.get("as"):
            s += f" AS {q(it['as'])}"
        return s
    fn = it["fn"].upper()
    arg = "*" if it.get("arg", "*") == "*" else qcol(it["arg"])
    distinct = "DISTINCT " if it.get("distinct") else ""
    s = f"{fn}({distinct}{arg})"
    if it.get("as"):
        s += f" AS {q(it['as'])}"
    return s


def ra_to_sql(ir):
    if "from" not in ir or "select" not in ir:
        raise ValueError("IR needs 'from' and 'select'")
    distinct = "DISTINCT " if ir.get("distinct") else ""
    sel = ", ".join(_sel_item(s) for s in ir["select"])
    sql = f"SELECT {distinct}{sel} FROM {_tbl_alias(ir['from'])}"
    for j in ir.get("joins", []):
        on = j["on"]
        pairs = on if isinstance(on[0], list) else [on]  # support multi-key joins
        cond = " AND ".join(f"{_expr(l)} = {_expr(r)}" for l, r in pairs)
        sql += f" JOIN {_tbl_alias(j['table'], j.get('as'))} ON {cond}"
    if ir.get("where"):
        sql += f" WHERE {_raw(ir['where'])}"
    if ir.get("group_by"):
        sql += " GROUP BY " + ", ".join(_expr(c) for c in ir["group_by"])
    if ir.get("having"):
        sql += f" HAVING {_raw(ir['having'])}"
    if ir.get("order_by"):
        obs = []
        for o in ir["order_by"]:
            if not isinstance(o, dict) or "by" not in o:
                obs.append(_expr(o))
                continue
            obs.append(_expr(o["by"]) + (" DESC" if o.get("desc") else ""))
        sql += " ORDER BY " + ", ".join(obs)
    if ir.get("limit") is not None:
        sql += f" LIMIT {int(ir['limit'])}"
    tables = [ir["from"]] + [j.get("table") for j in ir.get("joins", [])]
    return quote_reserved_refs(
        sql, [t for t in tables if isinstance(t, str) and t.isidentifier()]
    )


# --- self-test: hand-encoded gold queries, compile -> execute -> compare to gold ---
if __name__ == "__main__":
    import os
    import sqlite3

    DBR = os.path.join(
        os.path.dirname(__file__), "..", "..", "llm", "data", "dev_databases"
    )

    def run(db, sql):
        c = sqlite3.connect(os.path.join(DBR, db, db + ".sqlite")).cursor()
        c.execute(sql)
        return set(c.fetchall())

    cases = [
        # idx6: magnet schools with >500 SAT takers
        (
            "california_schools",
            "SELECT T2.School FROM satscores AS T1 INNER JOIN schools AS T2 ON T1.cds = T2.CDSCode "
            "WHERE T2.Magnet = 1 AND T1.NumTstTakr > 500",
            {
                "from": "schools",
                "joins": [
                    {"table": "satscores", "on": ["schools.CDSCode", "satscores.cds"]}
                ],
                "select": ["schools.School"],
                "where": "schools.Magnet = 1 AND satscores.NumTstTakr > 500",
            },
        ),
        # idx16: count merged Alameda schools with <100 takers
        (
            "california_schools",
            "SELECT COUNT(T1.CDSCode) FROM schools AS T1 INNER JOIN satscores AS T2 ON T1.CDSCode = T2.cds "
            "WHERE T1.StatusType = 'Merged' AND T2.NumTstTakr < 100 AND T1.County = 'Alameda'",
            {
                "from": "schools",
                "joins": [
                    {"table": "satscores", "on": ["schools.CDSCode", "satscores.cds"]}
                ],
                "select": [{"fn": "COUNT", "arg": "schools.CDSCode"}],
                "where": "schools.StatusType = 'Merged' AND satscores.NumTstTakr < 100 AND schools.County = 'Alameda'",
            },
        ),
        # toxicology: distinct atoms that are carbon
        (
            "toxicology",
            "SELECT DISTINCT T1.atom_id FROM atom AS T1 WHERE T1.element = 'c'",
            {
                "from": "atom",
                "distinct": True,
                "select": ["atom.atom_id"],
                "where": "atom.element = 'c'",
            },
        ),
    ]
    ok = 0
    for db, gold, ir in cases:
        sql = ra_to_sql(ir)
        same = run(db, gold) == run(db, sql)
        ok += same
        print(f"[{'OK' if same else 'FAIL'}] {db}: {sql}")
    print(f"\nself-test: {ok}/{len(cases)} round-trips match gold")
