---
name: ablation-c-gate-2026-09-07
description: zero-token upper-bound estimate for ablation C (FK join-path + value-index prompt hints) over the 174 ex_kg==0 failures on the 340 dev slice
metadata:
  type: project
---

Before the paid ~340-call ablation-C run (`src/ablation_c_m1_hints.py`, FK
multi-hop join paths + cross-table value index injected into the baseline
prompt), ran a zero-token local classifier over the 174 `ex_kg==0` failures
in `outputs/results_340.json` (executed pred_kg + gold via sqlite, no LLM
calls). Bucket counts (mutually exclusive, priority order
pred_execution_error > over_selection > join_mismatch > value_mismatch >
other_logic):

| bucket | count/174 | % |
|---|---|---|
| other_logic | 110 | 63.2% |
| over_selection | 39 | 22.4% |
| join_mismatch | 13 | 7.5% |
| value_mismatch | 7 | 4.0% |
| pred_execution_error | 5 | 2.9% |

Heuristics used (see script, saved only in scratchpad, not the repo —
rewrite if needed rather than hunting for it):
- `over_selection`: strict `m_pred_cols > k_gold_cols` AND some k-column
  permutation-subset of pred's result set (as row tuples) equals gold's row
  set (same idea as `oracle_projection.py::projection_fixable`, but gated on
  `m > k`, not `m >= k`, so pure column-reorder cases don't get double
  counted here).
- `join_mismatch`: base tables referenced by pred (sqlglot `exp.Table`,
  resolved via alias map, filtered to `structures/<db>.json["tables"]`)
  differ from gold's; gold uses a table pred doesn't, AND
  `structures/<db>.json["join_paths"]["tableA|tableB"]` between some table
  pred used and the missing table has length > 2 (i.e. requires an
  intermediate table not visible from a direct FK).
- `value_mismatch`: string literals in gold (sqlglot `exp.Literal.is_string`)
  not present in pred's literal set, AND that literal (lowercased) is a key
  in `structures/<db>.json["value_index"]` (i.e. a real enum/string value
  that exists in some column, so it's not just gold-evidence wording noise).
- Only 4/110 `other_logic` cases have a *direct-FK* (path length ≤ 2) table
  mismatch that the join heuristic deliberately excludes — so the
  multi-hop-specific `join_mismatch` count (13) is not hiding a much larger
  simple-join-gap population.

**Why this matters:** `join_mismatch + value_mismatch = 20/174 (11.5%)`,
roughly half the size of `over_selection` (39/174 here with the strict
oracle test; the earlier taxonomy reported ~60/176 using a different,
probably softer/LLM-assisted bucketing method — the two numbers aren't
directly comparable, don't average them). 20 failures is a much smaller
target than the 60ish that justified M3's RA-IR projection stage.

Also found idx 16 is gold-label noise (see [[gold-noise-idx16]]), which
happened to land in the value_mismatch bucket — the *real* actionable
value_mismatch count for ablation-C purposes is 6, not 7.

**How to apply:** when this ablation is later discussed or re-scoped, cite
this 13+7(-1 noise)=~19/174 (~11%) zero-token ceiling rather than re-deriving
it. Recommendation given to the user: the combined bucket is real but small
relative to over-selection; ablation C is a plausible next step only if
scoped cheaply (e.g. run on just the ~35-40 idx in these two buckets rather
than all 340) or bundled with another hypothesis — spending the full 340
paid calls on this bucket alone is a weak bet on the zero-token evidence.
If ablation C is later actually run, update this memory with the observed
in-bucket flip rate so the next gate estimate can calibrate the heuristic's
precision.
