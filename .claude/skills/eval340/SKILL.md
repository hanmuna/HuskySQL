---
description: >
  Evaluate a prediction set on the 340-question BIRD dev slice (EX only, no
  VES) and compare against the 48.24 baseline and 57.94 M3 result. Use after
  any generation run or recompile that produced new SQL for the slice.
argument-hint: "[path to predictions json]"
allowed-tools: Bash, Read, Write, Glob
---

Evaluate predictions on the first-340 BIRD dev slice. Argument (optional):
path to the predictions file — `$ARGUMENTS`. If omitted, ask nothing; look
for the most recently modified candidate under `datastructure_study/outputs/`
and confirm the choice in your report.

Accepted prediction formats:
- `{idx: {"sql": ...}}` (m3_predict_340.json style)
- `{idx: "SQL\t----- bird -----\tdb_id"}` (BIRD predict_dev.json style)
- `{idx: "SQL"}` plain

Procedure:

1. Write a throwaway eval script to $TMPDIR (do not commit it). Reuse the
   exact EX semantics of `datastructure_study/src/m0_eval_baseline_340_or_full.py`: execute
   predicted and gold SQL on `llm/data/dev_databases/<db_id>/<db_id>.sqlite`,
   compare with `set()` equality, 30 s timeout via func_timeout, errors/
   timeouts count as 0. Gold and metadata come from
   `datastructure_study/outputs/results_340.json` (fields: idx, db_id,
   difficulty, gold, ex_kg).
2. Run it with `llm/.venv/bin/python`. EX only — never VES (slow, and VES
   tracks EX anyway).
3. Report:
   - Overall EX vs baseline EX_kg 48.24 and M3 57.94 (and oracle bound 61.76).
   - Flips vs baseline: wrong→right and right→wrong counts, net, with idx
     lists (truncate to ~15 each).
   - Breakdown by db_id and difficulty.
4. **Flakiness gate**: for every flip whose query ran close to the timeout,
   or involving historically flaky idx 215, re-execute that single question
   2-3 times. Exclude unstable ones from the claimed delta and list them
   separately. A fake +0.29 once came from exactly this.
5. Save the per-question results to
   `datastructure_study/outputs/<name>_eval.json` (name derived from the
   predictions file) so the run is diffable later. Do not overwrite
   `results_340.json`.
