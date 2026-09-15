---
name: sqlglot-table-literal-diff-recipe
description: reusable zero-token recipe for diffing base tables and string literals between pred and gold SQL using sqlglot, for gating hypotheses before paid runs
metadata:
  type: reference
---

Pattern used repeatedly in this repo for zero-token failure-bucket gates
(e.g. [[ablation-c-gate-2026-09-07]], and `src/m2_ast_audit_repair.py`):

- **Base tables**: `sqlglot.parse_one(sql, read="sqlite").find_all(exp.Table)`,
  take `.name.lower()`, filter against `structures/<db>.json["tables"]` so
  CTE names / derived-table aliases picked up as `exp.Table` false-positives
  are dropped. No need for a full alias-resolution pass if you only need the
  *set* of real base tables touched, not per-column qualification.
- **String literals**: `ast.find_all(exp.Literal)`, filter `.is_string`,
  take `.this.strip().lower()`. This cleanly separates string/enum literals
  from numeric ones (numeric literal mismatches are usually a different kind
  of bug — off-by-one / wrong aggregation — not a "wrong value" bug the
  value_index would catch).
- Both parse cleanly on all three dev-slice DBs' predicted SQL (california_schools,
  financial, toxicology) with `read="sqlite"`; failures to parse should be
  bucketed separately (`pred_execution_error`-style), not silently skipped,
  or you'll undercount the very failures you're trying to gate.
- Cross-reference against `structures/<db>.json`'s `join_paths` (path length
  > 2 = multi-hop / not a direct FK) and `value_index` (literal exists
  somewhere in the DB) to turn a raw table/literal diff into an actionable
  "would a structural hint plausibly have fixed this" signal, rather than
  just "pred and gold differ" (which is true of almost every failure).

**Why:** this two-liner (`find_all(exp.Table)` / `find_all(exp.Literal)`)
plus a `structures/<db>.json` cross-reference is enough to build a fast,
honest (if rough) zero-token upper-bound classifier without writing a real
SQL-semantics diff tool. Good enough for a go/no-go gate on a paid run; not
precise enough to be cited as a final bucket count without manual spot-checks
of a handful of examples first.

**How to apply:** reuse this exact recipe for any future "does hypothesis X's
target bucket exist and how big is it" zero-token gate on this repo's
340-slice artifacts, instead of writing a bespoke SQL parser each time.
