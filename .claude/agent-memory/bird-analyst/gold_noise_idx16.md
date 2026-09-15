---
name: gold-noise-idx16
description: dev-slice idx 16 (california_schools) has a gold/question mismatch — county in question does not match county in gold SQL
metadata:
  type: project
---

`results_340.json` idx 16, db `california_schools`: question is "How many
schools in merged Alameda have number of test takers less than 100?" but the
gold SQL filters `T1.County = 'Lake'` (not Alameda). This is BIRD dev-set
gold-label noise, not a model failure — the with-knowledge GPT-5.2 prediction
correctly used `County = 'Alameda'` per the question text and was scored
wrong only because gold disagrees with the question.

**Why:** discovered while building a zero-token join/value-literal failure
classifier over the 174 `ex_kg==0` failures (2026-09-07); this idx surfaced
as a spurious "value_mismatch" because the classifier flagged the
County-literal disagreement (`lake` present in [[gold_taxonomy... ]] value
index, `alameda` in pred) as a wrong-value guess. It is not — it's dataset
noise.

**How to apply:** when auditing EX failures on the 340 slice, do not count
idx 16 as evidence for any model-side fix (join hints, value hints,
projection, etc.) — no prompt/structured-generation change can flip a
question where gold itself is inconsistent with the NL question. If a future
EX aggregate looks off by roughly 1/340 ≈ 0.29 points, check whether idx 16 is
included/excluded consistently across comparisons.
