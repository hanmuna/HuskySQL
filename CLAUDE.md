# BIRD text-to-SQL research repo

Fork of the BIRD benchmark (AlibabaResearch/DAMO-ConvAI). The active work is a
research effort in `datastructure_study/`: code-level structured generation
(AST / RA-IR, NOT prompt engineering) to fix failure classes the vanilla
GPT-5.2 baseline cannot. Everything else (`llm/`, `materials/`) is the
benchmark harness it builds on.

## Ground rules

- **Language**: all code, comments, config, commit messages in English. The
  `.md` research docs inside `datastructure_study/` are intentionally Chinese
  (and gitignored for that reason) — keep writing those in Chinese. Never any
  Korean/Japanese anywhere.
- **Zero-token principle**: before proposing any run that calls the LLM API,
  first check whether the question can be answered from saved artifacts
  (`datastructure_study/outputs/*.json`, `llm/exp_result/`). Recompiling saved
  IR, re-bucketing failures, and oracle upper bounds are all zero-token.
- **Paid runs need explicit user approval**: anything that calls
  `connect_gpt` / the AIML API (~340+ calls per dev-slice run). State the
  estimated call count first.
- Do not re-run `datastructure_study/src/m0_eval_baseline_340.py` — VES is slow and
  `outputs/results_340.json` already exists. EX-only re-evaluation is cheap
  (see `/eval340` skill).
- `llm/src/*.py` has pre-existing Chinese comments — leave them unless asked.
- API keys live in `llm/run/.env(.local)` (gitignored, read-denied). Never
  read or commit them.
- `*.sqlite` databases are gitignored (too large); they exist locally under
  `llm/data/dev_databases/<db_id>/<db_id>.sqlite`.

## Established results (do not re-derive)

Dev slice = first 340 dev questions = california_schools(89) + financial(106)
+ toxicology(145), clean DB boundary.

| Stage | EX on 340 (with knowledge) | Note |
|---|---|---|
| Baseline GPT-5.2 | **48.24** (no-kg 25.59) | VES tracks EX; efficiency not the bottleneck |
| M2 AST repair | +0.00 | 335/340 already parse → AST/schema-layer ceiling is 0 |
| M3 RA-IR → SQL | **57.94** (+9.71) | net flips +33 (49 up / 16 down); over-selection bucket 27/60 fixed |
| Ablation A (IR format, no minimality) | 49.12 (+0.88) | format alone ≈ nothing; constraint carries ~91% of the gain |
| Ablation B (baseline + instruction) | 54.71 (+6.47) | soft instruction fixes 23/60; enforcement still +3.24 ahead, super-additive |
| Projection oracle | 61.76 upper bound | 46/176 failures fixable by minimal projection |

Biggest failure bucket: SELECT over-selection (extra columns), 60/176 (34%) —
a soft prompt instruction recovers ~2/3 of the gain (ablation B); compiled
minimal projection recovers more AND guarantees no extra columns. Cross-model
(five models, full-340, each vs its own baseline): GPT-4.1-mini +12.35,
GPT-5.2 +9.71, Sonnet 4.5 +6.47 (best absolute: 61.18), DeepSeek-chat −3.53,
Qwen3-Coder −2.94. NOT a single-factor monotone law (DeepSeek falsifies it):
net effect = in-bucket benefit − model-specific format tax (semantic drift
38-39 down-flips for the negative models vs 12-28 positive). Two
matched-strength sign-flip pairs (Sonnet/Qwen, GPT-5.2/DeepSeek) kill the
headroom confound. Decomposition: outputs/xmodel_benefit_tax.json.
Professor brief: datastructure_study/docs/prof_brief.html.
GLM-4.7 abandoned (provider overload). Hard constraint: AIML closed chat API exposes no logits, so true
grammar-constrained decoding (PICARD/xgrammar) requires switching to local
open weights.

Progress source of truth: `datastructure_study/STATUS.md`. Full numbers:
`datastructure_study/REPORT.md`.

## Key paths

- `datastructure_study/outputs/results_340.json` — per-question idx, db_id,
  difficulty, gold, pred_kg/nokg, ex_kg/nokg, ves_* (evaluation master file)
- `datastructure_study/outputs/m3_predict_340.json` — per-question saved RA IR
  + compiled SQL (recompile with `src/ra_to_sql.py` at zero token)
- `datastructure_study/outputs/kg_taxonomy.json` — failure bucket → idx list
- `datastructure_study/structures/<db>.json` — FK graph / column profile /
  enum value index (rebuild: `src/m1_build_structures.py`)
- Python for all study scripts: `llm/.venv/bin/python` (study scripts live
  in `datastructure_study/src/`; run them from inside `datastructure_study/`)

## Research workflow

How to orchestrate any new research thread in this repo:

1. **Hypothesis first.** Write one sentence: what mechanism, what failure
   bucket it should fix, expected EX delta. If it can't name a bucket from
   `kg_taxonomy.json`, it isn't ready.
2. **Zero-token upper bound.** Build an oracle over saved predictions/gold
   (like `src/oracle_projection.py`) to bound the possible gain BEFORE spending
   API calls. If the bound is small, stop here.
3. **Literature check** → delegate to the `paper-scout` agent (runs on Fable,
   keeps its own cross-session memory of surveyed papers).
4. **Failure/data analysis** → delegate to the `bird-analyst` agent so eval
   logs and per-question dumps stay out of the main context.
5. **Paid generation run** (user-approved) → delegate to the `exp-runner`
   agent; every run script must checkpoint like `src/m3_run_340.py` (resumable,
   flush every ~20 items).
6. **Evaluate** with the `/eval340` skill (EX-only, compares against 48.24
   baseline and 57.94 M3). Flip-verification rule: any single-question flip
   near the 30 s timeout (e.g. idx 215 historically) must be re-executed
   individually before you count it — one flaky query once produced a fake
   +0.29 "gain".
7. **Log** with `/exp-log`: update `STATUS.md` (and `REPORT.md` for full
   results) in Chinese, matching the existing doc style. Negative results get
   logged too — "M2 gain = 0" is one of the most useful facts in this repo.
