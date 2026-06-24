"""Deterministic SQL structure extraction via sqlglot.

Produces, for a single SQL string:
  - ast_repr: sqlglot AST (repr string) for human/markdown view
  - fingerprint: per-clause normalized representation used for Step-4 comparison
  - productions: list of grammar productions (AST node-type sequence) = the
    deterministic part of the retained "BNF" dimension.

Comparison categories surfaced to the Step-4 report:
  SELECT, DISTINCT, AGGREGATION, FROM, JOIN, WHERE, GROUP_BY, HAVING,
  ORDER_BY, LIMIT, SUBQUERY, SET_OP, FUNCTION, CAST
A failed-to-parse SQL is reported under the PARSE_ERROR pseudo-category.
"""
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers

DIALECT = "sqlite"

CATEGORIES = [
    "SELECT", "DISTINCT", "AGGREGATION", "FROM", "JOIN", "WHERE",
    "GROUP_BY", "HAVING", "ORDER_BY", "LIMIT", "SUBQUERY", "SET_OP",
    "FUNCTION", "CAST",
]


def _norm(node):
    """Normalized SQL string for a node (lowercased identifiers, stable)."""
    if node is None:
        return None
    n = node.copy()
    n = normalize_identifiers(n, dialect=DIALECT)
    return n.sql(dialect=DIALECT)


def _canonicalize(ast):
    """Semantics-preserving normalization so alias / equivalent-spelling noise
    does not masquerade as a clause difference:
      - strip table qualifiers from columns (ym.Date / T2.Date -> Date)
    Returns a copy; the original AST is untouched.
    """
    a = ast.copy()
    for col in a.find_all(exp.Column):
        col.set("table", None)
    return a


def _and_atoms(cond):
    """Split a boolean condition into top-level AND atoms (order-insensitive)."""
    if cond is None:
        return []
    atoms = []
    stack = [cond]
    while stack:
        c = stack.pop()
        if isinstance(c, exp.And):
            stack.append(c.left)
            stack.append(c.right)
        elif isinstance(c, exp.Paren):
            stack.append(c.this)
        else:
            atoms.append(_norm(c))
    return sorted(a for a in atoms if a)


def parse(sql):
    """Return (ast, error). ast is None on failure."""
    try:
        return sqlglot.parse_one(sql, read=DIALECT), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def productions(ast):
    if ast is None:
        return []
    return [type(node).__name__ for node in ast.walk()]


def fingerprint(ast):
    """Per-clause normalized fingerprint. Empty dict if ast is None."""
    if ast is None:
        return {}

    ast = _canonicalize(ast)
    selects = ast.find_all(exp.Select)
    select = ast if isinstance(ast, exp.Select) else (ast.find(exp.Select))

    fp = {}

    # SELECT projection (strip aliases so naming differences don't count)
    proj = []
    distinct = False
    if select is not None:
        distinct = select.args.get("distinct") is not None
        for e in select.expressions:
            inner = e.this if isinstance(e, exp.Alias) else e
            proj.append(_norm(inner))
    fp["SELECT"] = sorted(p for p in proj if p)
    fp["DISTINCT"] = distinct

    # Aggregation: which aggregate functions appear
    fp["AGGREGATION"] = sorted({a.sql_name() for a in ast.find_all(exp.AggFunc)})

    # FROM base tables
    fp["FROM"] = sorted({_norm(t.this) if isinstance(t, exp.Alias) else
                         (t.name.lower() if isinstance(t, exp.Table) else _norm(t))
                         for t in ast.find_all(exp.Table)})

    # JOIN: (kind, on-condition) pairs
    joins = []
    for j in ast.find_all(exp.Join):
        kind = ((j.args.get("side") or "") + " " + (j.args.get("kind") or "")).strip().lower()
        kind = kind or "inner"  # bare JOIN == INNER JOIN
        on = _norm(j.args.get("on")) if j.args.get("on") else None
        joins.append((kind, on))
    fp["JOIN"] = sorted(map(str, joins))

    # WHERE atoms
    where = select.args.get("where") if select is not None else None
    fp["WHERE"] = _and_atoms(where.this if isinstance(where, exp.Where) else where)

    # GROUP BY keys
    group = select.args.get("group") if select is not None else None
    fp["GROUP_BY"] = sorted(_norm(g) for g in (group.expressions if group else []))

    # HAVING
    having = select.args.get("having") if select is not None else None
    fp["HAVING"] = _and_atoms(having.this if isinstance(having, exp.Having) else having)

    # ORDER BY (expr + direction)
    order = select.args.get("order") if select is not None else None
    obs = []
    if order:
        for o in order.expressions:
            desc = bool(o.args.get("desc"))
            obs.append(f"{_norm(o.this)}|{'desc' if desc else 'asc'}")
    fp["ORDER_BY"] = obs

    # LIMIT
    limit = select.args.get("limit") if select is not None else None
    fp["LIMIT"] = _norm(limit.expression) if limit else None

    # SUBQUERY count (nested SELECTs beyond the outer one)
    fp["SUBQUERY"] = max(0, sum(1 for _ in selects) - 1)

    # SET operations
    fp["SET_OP"] = sorted({type(s).__name__ for s in ast.find_all((exp.Union, exp.Intersect, exp.Except))})

    # Scalar functions (non-aggregate, excluding boolean/comparison operators)
    fp["FUNCTION"] = sorted({f.sql_name() for f in ast.find_all(exp.Func)
                             if not isinstance(f, (exp.AggFunc, exp.Connector, exp.Binary))})

    # CAST target types
    fp["CAST"] = sorted({c.to.sql(dialect=DIALECT).lower() for c in ast.find_all(exp.Cast)})

    return fp


def analyze(sql):
    ast, err = parse(sql)
    return {
        "sql": sql,
        "parse_error": err,
        "ast_repr": repr(ast) if ast is not None else None,
        "fingerprint": fingerprint(ast),
        "productions": productions(ast),
    }


def diff_categories(pred_fp, gold_fp):
    """Return list of categories where pred and gold fingerprints differ."""
    diffs = []
    for cat in CATEGORIES:
        if pred_fp.get(cat) != gold_fp.get(cat):
            diffs.append(cat)
    return diffs
