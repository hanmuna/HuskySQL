# Project Status

Updated: 2026-09-08

One-line status: on top of the existing 3-database, 340-question "clean slice" findings, this round (1) independently reproduced the 340-slice results and flip-verified M3, (2) ran a zero-token feasibility gate for a new hypothesis (injecting M1 preprocessing), and (3) extended the M3 pipeline to the full 1534-question dev set across all 11 databases and confirmed M3's gain generalizes.

---

## 1. Established results (do not re-derive)

340-question slice = california_schools(89) + financial(106) + toxicology(145), clean DB boundary.

| Stage | EX (with knowledge) | Note |
|---|---|---|
| Baseline GPT-5.2 (original record) | **48.24** (no-kg 25.59) | VES tracks EX; efficiency not the bottleneck |
| Baseline GPT-5.2 (this round's independent reproduction) | **48.82** (no-kg 26.47) | <1pt from the original record; normal run-to-run variance |
| M2 AST repair | +0.00 | 335/340 already parse -> AST/schema-layer ceiling is 0 |
| M3 RA-IR -> SQL (original record) | **57.94** (+9.71) | net flips +33 (49 up / 16 down); over-selection bucket 27/60 fixed |
| M3 RA-IR -> SQL (this round, single reproduction run) | **61.76** (+12.94 vs. 48.82) | net flips +44 (56 up / 12 down); IR-parse/compile 338/340; flip-verification confirms 0/68 flips show timeout-boundary risk |
| Ablation A (IR format only, no minimality) | 49.12 (+0.88) | format alone ~ nothing; the constraint is what matters |
| Ablation B (baseline + one prompt line) | 54.71 (+6.47) | soft instruction recovers 1/3 of over-selection, but 3.24 behind hard enforcement |
| Projection oracle | 61.76 upper bound | 46/176 failures fixable by minimal projection |

> Note: this round's 340-slice M3 reproduction (61.76) numerically matches the projection-oracle ceiling exactly - confirmed coincidental. Audited every "gold" reference in `m3_run_340.py`/`ra_to_sql.py`/`m3_ir_prompt.py`; the generation path never touches gold, ruling out leakage.

Cross-model (5 models, each vs. its own baseline): GPT-4.1-mini +12.35, GPT-5.2 +9.71, Sonnet 4.5 +6.47 (best absolute 61.18), DeepSeek-chat -3.53, Qwen3-Coder -2.94. Not a monotone law (DeepSeek falsifies it); net effect = in-bucket benefit minus a model-specific "format tax."

### New: full 1534-question (11-database) results

No longer limited to the 3-db slice - `m0_eval_baseline_340_or_full.py` / `m3_run_340.py` were generalized to accept a `[340|full]` tag (default `340`, behavior unchanged; `full` processes all 1534 dev.json rows, writing to separate `results_full.json` / `m3_predict_full.json` / `m3_eval_full.json` files that never overwrite the 340-slice artifacts).

| Metric | Baseline (with-kg) | M3 |
|---|---|---|
| EX (full 1534, weighted) | 52.41 | **59.58** (+7.17) |
| VES (baseline only; M3 run has no VES step) | 51.46 | - |
| EX no-kg (baseline only) | 35.14 (VES 34.17) | - |
| Net flips | - | +110 (171 up / 61 down) |
| IR-parse + compile rate | - | 1529/1534 (99.7%; 5 IR-parse failures: toxicology x2, card_games x2, formula_1 x1 - no error, just unparseable JSON) |

By database (all positive, none regressed):

| db_id | n | base | M3 | delta |
|---|---|---|---|---|
| california_schools | 89 | 41.6 | 49.4 | +7.9 |
| financial | 106 | 50.0 | 60.4 | +10.4 |
| toxicology | 145 | 52.4 | 62.1 | +9.7 |
| card_games | 191 | 44.0 | 49.2 | +5.2 |
| codebase_community | 186 | 60.8 | 64.5 | +3.8 |
| superhero | 129 | 79.8 | 82.9 | +3.1 |
| formula_1 | 174 | 38.5 | 50.0 | +11.5 |
| european_football_2 | 129 | 60.5 | 72.1 | +11.6 |
| thrombosis_prediction | 163 | 41.1 | 42.9 | +1.8 |
| student_club | 158 | 63.3 | 69.0 | +5.7 |
| debit_card_specializing | 64 | 40.6 | 56.2 | +15.6 |

By difficulty: simple n=925 base 59.1 -> M3 66.6 (+7.5); moderate n=464 base 41.6 -> M3 48.7 (+7.1); challenging n=145 base 44.1 -> M3 49.7 (+5.5).

**Takeaway**: M3's gain (RA-IR + compiler-enforced minimal projection) is not an artifact of the 3 hand-picked databases in the clean slice - extended to 8 databases never involved in the original research design, it stays positive across the board, from +1.8 to +15.6. The full-set gain (+7.17) is somewhat smaller than on the clean slice (+9.71/+12.94), but the direction and mechanism hold - reasonably solid evidence of generalization.

---

## 2. This round's work log

### 2.1 Environment fixes (infrastructure, not a research finding)
- The project directory was once renamed from a Chinese path to an English one, breaking the hardcoded old path baked into `llm/.venv`'s `activate` script - `python3` kept resolving to the system Python (no `backoff` etc.) even after `source activate`. Fixed by rebuilding the venv.
- Confirmed `run_gpt.sh`/`gpt_request.py` calls the AIML API gateway (`https://api.aimlapi.com/v1/chat/completions`), not the OpenAI endpoint directly - an OpenAI key gets rejected with "Invalid JWT token"; a separate AIML-issued key from aimlapi.com is required.

### 2.2 340-slice reproduction + flip verification
- Independently reproduced the baseline (48.82/26.47) and a single M3 generation run (61.76, net +44 flips). Had bird-analyst re-execute all 68 flipped questions 3x each; 0/68 showed timeout-boundary risk (the historically flaky idx 215 was stable this time), confirming the +12.94 delta is not a timeout-driven false positive.

### 2.3 Mechanism analysis: why does constraining SELECT alone move EX this much?
- Clarified that `m3_ir_prompt.py`'s `schema_block()` already includes live-computed FK hints and enum-value hints - M3 is not zero-preprocessing.
- Confirmed `ra_to_sql.py`'s compiler only fixes the "IR-to-SQL syntax translation rules" (clause skeleton order, keyword escaping, JOIN syntax) - it does not auto-derive join paths from the FK graph. `docs/lit/structural_directions_survey.md` explicitly names "compiler-side derivation/repair of IR join trees from the FK graph" as "the un-taken sliver" (not yet built).
- Confirmed GROUP BY auto-derivation was already probed and ruled out by a prior FD-derivation oracle test on the 143 failures remaining after M3 (0 flips, see the comment at `m3_ir_prompt.py:10-12`) - GROUP BY errors are not a hidden side-effect fix.
- The one hard, attributable constraint: in `ra_to_sql.py`, the SELECT clause content is strictly equal to the IR's `select` field - there is no path for the compiler to add extra columns.

### 2.4 Ablation C (new hypothesis, gated before a paid run)
- Hypothesis: injecting M1's precomputed preprocessing (`structures/<db>.json`'s FK graph, multi-hop join paths, cross-table value index) into the baseline prompt fixes "wrong join" and "wrong value" failures that the current pipeline doesn't specifically target.
- Wrote a new script `src/ablation_c_m1_hints.py` (no existing files touched) and ran a zero-token failure-bucketing gate via bird-analyst: of 174 340-slice kg failures, over_selection 39 (22.4%), **join_mismatch 13 (7.5%)**, **value_mismatch 6 real + 1 gold-label-noise (4.0%)**, pred_execution_error 5 (2.9%), other_logic 110 (63.2%).
- Verdict: join+value combined is ~19/174 (11.5%), about half the size of the over-selection bucket (39, or ~60 in the original taxonomy) - a weak zero-token case. **Recommendation: do not spend the full 340 paid calls yet**; either test the mechanism cheaply on just the ~19-question subset first, or fold it into a future combined-hint experiment. **Current status: script ready, paid generation not yet run.**
- Side finding: california_schools idx 16 has a gold-label bug (question asks about Alameda, gold filters `County='Lake'`) - recorded to bird-analyst's memory to avoid miscounting it in future analyses.

### 2.5 Full 1534-question extension
- Generalized `m0_eval_baseline_340_or_full.py` and `m3_run_340.py` to accept a `[340|full]` argument (default `340`, behavior unchanged; the EX denominator was changed from a hardcoded `340` to a dynamic `len(rows)`, fixing a real bug where feeding it more rows would have computed the wrong percentage).
- While running the full baseline, discovered **8 of 11 databases had 0-byte empty `.sqlite` files** on this machine (only california_schools/financial/toxicology had real data) - `sqlite3.connect()` silently creates an empty file for a nonexistent path instead of erroring, so both generation and evaluation "silently" failed, scoring 0 everywhere with no visible error.
- Found the real `.sqlite` files for those 8 databases (237KB-598MB) already available locally in the already-downloaded `data_minidev.zip` (BIRD MiniDev package), copied them into `llm/data/dev_databases/`, cleared the 1194 invalid predictions for those databases, and regenerated.
- Hit a mid-generation AIML billing interruption that left 15 "run out of funds" error strings cached as if they were finished checkpoint entries (10 superhero + 3 codebase_community + 2 others) - this briefly made superhero look like it regressed under M3 (79.8 -> 75.19); clearing those 15 and regenerating confirmed it was an artifact - superhero actually improves (79.8 -> 82.9).
- Along the way, found and fixed a real bug in `m3_run_340.py`'s evaluation loop: `run_ex()` had no timeout, no parallelism, and no progress printing, so it could hang indefinitely on a slow query against one of the larger (multi-hundred-MB) databases with zero visible output (observed hanging for 83 minutes of CPU time in this run). Added a `func_timeout(30s)` guard and per-100-question progress printing, matching `m0_eval_baseline_340_or_full.py`'s robustness.

---

## 3. Next steps

1. Ablation C (M1 preprocessing injection): if still worth pursuing, validate cheaply on the ~19-question + control subset before committing to a full 340/1534-question paid run.
2. The full-1534 M3 results have not yet been written up in a detailed `REPORT.md`; this document only has the summary tables.
3. `kg_taxonomy.json` (the detailed failure-bucket taxonomy) is missing locally (a gitignored artifact never synced here); `m3_run_340.py` currently skips it gracefully. Re-run a bird-analyst bucketing pass if the exact over-selection-fix count is needed again.
4. `datastructure_study/outputs/`, this document, and `REPORT.md` are all gitignored local artifacts - they will need to be regenerated or manually synced when switching machines or collaborators.
