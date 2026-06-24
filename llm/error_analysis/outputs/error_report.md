# Clause-level error report

- Total questions evaluated: **10**
- Failed (EX=0): **5**  (50.0%)
- EX accuracy: **50.00%**

A failure can differ in multiple clauses, so percentages sum to >100%.

| Rank | Category | Failures w/ diff | % of failures | Example idx |
|------|----------|------------------|---------------|-------------|
| 1 | PARSE_ERROR | 3 | 60.0% | 2, 3, 6 |
| 2 | SELECT | 2 | 40.0% | 1, 9 |
| 3 | WHERE | 2 | 40.0% | 1, 9 |
| 4 | ORDER_BY | 1 | 20.0% | 1 |
| 5 | FROM | 1 | 20.0% | 9 |

## Category legend

`PARSE_ERROR` pred didn't parse · `EMPTY_PRED` no SQL produced · `SEMANTIC_EQUAL_STRUCT` same structure but wrong result (value/literal/semantics).
Others = the pred's clause structurally differs from gold (see error_analysis/METHODOLOGY.md for definitions).
