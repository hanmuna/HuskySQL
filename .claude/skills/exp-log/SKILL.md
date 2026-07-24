---
description: >
  Log a finished experiment into the research docs: append the result to
  datastructure_study/STATUS.md (and REPORT.md for full runs), in Chinese,
  matching the existing style. Use at the end of any experiment, including
  negative results.
disable-model-invocation: true
allowed-tools: Read, Edit, Bash, Glob
---

Current status file for reference:

!`sed -n '1,80p' datastructure_study/STATUS.md`

Log the experiment the user just finished (details in `$ARGUMENTS` and the
conversation) into the research docs. These docs are intentionally written in
Chinese — write the new entries in Chinese, matching the existing tone:
plain, factual, no hype, no emoji beyond the existing ✅/⏭️ headers.

1. `datastructure_study/STATUS.md`:
   - Append a numbered entry under「已完成 ✅」with: what was done, the exact
     headline numbers (EX before → after, flips, per-bucket effect), where
     the artifacts live (`outputs/...`), and the token/call cost (or 零 token).
   - Update the「更新日期」line to today's date.
   - Prune「下一步」if this experiment completed one of its items.
2. If it was a full-slice or full-dev result worth keeping permanently, add a
   section to `datastructure_study/REPORT.md` with the breakdown tables.
3. Negative or null results MUST be logged with the same rigor (cf. the M2
   entry: "真实 EX 增益 = 0" is recorded prominently). State what the null
   result rules out.
4. Numbers must come from actual eval output in this conversation or from
   artifact files — never from memory of what "should" have happened. If a
   number is missing, recompute it from `outputs/` first.
5. If headline numbers changed (new best EX, new bucket conclusion), also
   update the summary table in the root `CLAUDE.md` (English) so future
   sessions inherit the correct baselines.

Do not commit anything; leave git operations to the user.
