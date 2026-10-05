#!/usr/bin/env python3
"""Deterministic SQLite dialect normalisation for compiled M3 SQL.

The model's IR sometimes carries MySQL-style functions in raw expression fields
(YEAR(), DIVIDE(), SUBTRACT(), CURDATE()). ra_to_sql passes raw expressions
through verbatim, so they fail on SQLite. This module rewrites only those
calls into SQLite equivalents. It is opt-in: ra_to_sql itself is unchanged.
"""
import re

_CALL = r"\b{name}\s*\("


def _split_args(s):
    args, depth, cur = [], 0, ""
    quote = None
    for ch in s:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
            cur += ch
        elif ch == "(":
            depth += 1
            cur += ch
        elif ch == ")":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            args.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip() or args:
        args.append(cur.strip())
    return args


def _find_close(s, open_idx):
    depth, quote = 0, None
    for i in range(open_idx, len(s)):
        ch = s[i]
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


RULES = {
    "YEAR": (1, lambda a: f"CAST(strftime('%Y', {a[0]}) AS INTEGER)"),
    "MONTH": (1, lambda a: f"CAST(strftime('%m', {a[0]}) AS INTEGER)"),
    "CURDATE": (0, lambda a: "date('now')"),
    "DIVIDE": (2, lambda a: f"(({a[0]}) * 1.0 / ({a[1]}))"),
    "SUBTRACT": (2, lambda a: f"(({a[0]}) - ({a[1]}))"),
    "ADD": (2, lambda a: f"(({a[0]}) + ({a[1]}))"),
    "MULTIPLY": (2, lambda a: f"(({a[0]}) * ({a[1]}))"),
}


def normalize_sqlite(sql):
    """Return sql with MySQL-style function calls rewritten for SQLite."""
    out = sql
    changed = True
    while changed:
        changed = False
        for name, (arity, fn) in RULES.items():
            m = re.search(_CALL.format(name=name), out, re.I)
            if not m:
                continue
            open_idx = m.end() - 1
            close_idx = _find_close(out, open_idx)
            if close_idx < 0:
                continue
            args = _split_args(out[open_idx + 1:close_idx]) if arity else []
            if arity and len(args) != arity:
                continue
            out = out[:m.start()] + fn(args) + out[close_idx + 1:]
            changed = True
            break
    return out
