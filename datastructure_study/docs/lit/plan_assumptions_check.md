# Plan-Assumptions Check (3rd survey pass, 2026-07-23)

Adversarial verification of the three load-bearing assumptions behind the
next-step plan, after ablations A/B and the 3-model cross-run. Prior passes:
`m3_novelty_survey.md`, `structural_directions_survey.md`.

---

## Assumption 1 — Literal-validity as output-side hard constraint

**Verdict: TAKEN as a headline mechanism; open only as a measured bucket +
compiler-gate instance of the "prescribe by measurement" principle.**

Prior art, by mechanism family:

- **Deterministic post-generation snap (closest).** A "condition
  post-processing" module — extract value mentions from predicted SQL,
  replace each with the most similar cell (SimCSE) in the referenced
  column — appears in the experimental protocol of the survey
  *A Survey of Text-to-SQL in the Era of LLMs* (arXiv:2408.05109, PDF
  experiments section; applied to all compared methods "for fair
  comparison"). Attribution between the survey's own experiments and
  *Evaluating Cross-Domain Text-to-SQL Models and Benchmarks*
  (arXiv:2310.18538) could not be fully pinned from abstracts, but the
  mechanism is in print either way. ZeroNL2SQL does multi-level
  value/column/table matching and feeds matches back; *Relational Database
  Augmented LLM* (arXiv:2407.15071) keeps a column-wise value memory and
  swaps in value synonyms via embeddings.
- **Detect-then-LLM-refine.** *Tool-SQL* (arXiv:2408.16991) is built
  exactly on "WHERE value does not exist in DB" (condition mismatch): a
  retriever + detector flag non-existent literals, feedback goes to an
  LLM agent; introduces Spider-Mismatch. *PV-SQL* (arXiv:2604.17653,
  Apr 2026): DB probing + rule-based verification checklist, iterative
  refinement, +5% EX on BIRD. *DeepEye-SQL* (arXiv:2510.17586): value
  grounding + verification. All LLM-in-the-loop, not a hard gate, but they
  own the "validate literals against DB contents post-generation" turf.
- **Input-side retrieval** (CHESS, CodeS coarse-to-fine value matching,
  E-SQL candidate predicates via LIKE) — already surveyed; not output-side.

Remaining delta for this project (small, supporting-role only):

1. The **measurement**: what fraction of the residual 85 "wrong value"
   failures are literal-NONEXISTENCE vs wrong CHOICE of an existing value.
   No paper reports this split on BIRD. STATUS.md's own prediction (value
   existence derivable, value choice semantic) implies the oracle number
   may be small — which is itself a publishable boundary datum for the
   principle ("existence is compiler-checkable, choice is not").
2. Integration as a **compile-time hard gate inside the RA compiler**
   (reject/snap at compile, zero extra LLM calls) vs prior art's agentic
   refinement loops. This is an engineering distinction, not a headline.

Recommendation: run the zero-token oracle; report as second (possibly
negative-boundary) instance of the principle; cite Tool-SQL + PV-SQL +
the SimCSE post-processing module prominently. Do NOT frame as a novel
mechanism.

---

## Assumption 2 — Cross-model treatment-effect moderation by failure profile

**Verdict: OPEN in text-to-SQL / LLM-codegen as a predictive framing.
No paper found (2025-2026 arXiv/ACL/ICLR sweep) that publishes "method
delta is a monotone function of the model's own measured failure-bucket
share." But adjacent work supplies reviewer ammunition — see below.**

Closest prior work:

- *Is Self-Repair a Silver Bullet for Code Generation?* (Olausson et al.,
  ICLR 2024, arXiv:2306.09896) — canonical "method effect moderated by
  model property" result: self-repair gains bottlenecked by the model's
  own feedback quality; swapping in stronger-model feedback raises gains.
  Moderator = capability, not failure profile; no monotone per-model plot.
- *ErrorLLM* (arXiv:2603.03742, KDD 2026) — "detection quality directly
  determines refinement effectiveness"; error-type-conditioned refinement,
  but not a per-model moderation analysis.
- *Both Ends Count* (arXiv:2602.21480) — measures column-precision
  (over-selection) per model/agent, i.e. failure-profile heterogeneity
  across models exists in print, but with NO intervention and NO
  delta-vs-profile claim.
- *MapleDoctor* (arXiv:2501.09310) — error taxonomy across 4 methods;
  taxonomy-level, no treatment-effect framing.

Reviewer ammunition against the 3-point moderation figure (collect
defenses now):

1. **n=3.** Any 3 distinct points are monotone with probability 1/3 under
   a random permutation. Standard demand: more models (5-8) or per-bucket
   mechanistic evidence instead of the scatter. Our defense: bucket-level
   fix-rate decomposition (27/60, 23/60...) is the mechanism, the scatter
   is illustration; consider adding 1-2 cheap models on the 340 slice.
2. **Headroom/strength confound.** Delta anti-correlates with baseline EX
   (48.24/+9.71, 54.71/+6.47, 54.12/−3.24) — a reviewer will say "your
   method just helps weaker models." Built-in control we already have:
   **Sonnet 4.5 (54.71) vs Qwen3-Coder (54.12) are a matched-strength
   pair with opposite deltas (+6.47 vs −3.24)** — headroom cannot explain
   the sign flip; failure-profile share (27% vs 22%) plus protocol
   compliance does. Make this pair the centerpiece of the defense.
3. **Regression to the mean / churn.** *Beyond the Mean: Within-Model
   Reliable Change Detection for LLM Evaluation* (arXiv:2604.27405) shows
   low-baseline items regress upward, high-baseline items downward —
   flip counts (49/16 etc.) need significance treatment (McNemar) and
   the up/down decomposition we already log. Cite it preemptively.
4. **Moderator identifiability.** Qwen's negative delta mixes failure
   profile with IR-protocol compliance (8 compile failures = instruction
   following, not projection profile). Demand to expect: recompute Qwen
   delta after zero-token compiler fixes; report "semantic drift only"
   residual so the moderator isn't confounded with format obedience.
   (Sonnet 340/340 compile makes compliance a measurable covariate,
   not a hidden one.)
5. **One prompt, many models.** Cross-model comparisons with a single
   untuned prompt are routinely attacked as biased toward the prompt's
   development model (GPT-5.2 here). Defense: report protocol compliance
   per model; note the IR prompt was frozen before cross-run.
6. **Gold-noise floor.** With BIRD Mini-Dev annotation error rates now
   reported at 52.8% (arXiv:2601.08778 v3) and a CIDR 2026 paper (*Text-
   to-SQL Benchmarks are Broken*, Jin et al.), a reviewer can claim the
   over-selection bucket partially reflects gold ambiguity (their E4
   class), not model error. Defense: 2602.21480 independently measures
   superfluous columns as a real failure; and EX is symmetric — extra
   columns fail execution match regardless of whose fault.

---

## Assumption 3 — Instruction-vs-enforcement ablation

**Verdict: PARTIALLY TAKEN. The generic comparison exists in several
literatures; the specific accuracy-motivated, closed-API, on-BIRD 3-arm
decomposition with a super-additivity finding is not published. Claimable
if framed narrowly and prior art is cited.**

Prior art map:

- **PCC-SQL (arXiv:2607.12341, Jul 2026) — the closest, upgrade from last
  pass.** It DOES run "same column-use constraint as direct prompting vs
  per-token logit mask": prompting leaks 4.84-42.36% (Spider-CU) /
  0.98-39.50% (BIRD-CU), mask leaks 0%; explicitly states "stochastic
  enforcement cannot deterministically rule out violations." Differences:
  compliance metric (leakage/coverage) not EX accuracy; access-control
  motivation; requires logits. Their prompting arm leaking "most but not
  all" violations is the same qualitative shape as our ablation B getting
  ~2/3 of the gain — cite as convergent evidence, and to preempt "this
  comparison is obvious."
- **Grammar Prompting for DSLs** (Wang et al., NeurIPS 2023) — ablates
  grammar-in-prompt with vs without constrained decoding; finds prompting
  the grammar helps even unconstrained. Soft arm = grammar text, not a
  plain NL instruction; DSLs, not SQL.
- **Geng et al.** (EMNLP 2023, GCD without finetuning) — constrained vs
  unconstrained with same prompt; no instruction-equivalent-of-constraint
  arm.
- **Let Me Speak Freely?** (arXiv:2408.02442, EMNLP-Industry 2024) and
  the dottxt rebuttal *Say What You Mean* — soft format instruction vs
  hard constrained decoding on reasoning tasks; contested results; format
  validity, not a semantic constraint.
- **SQLStructEval** (arXiv:2604.06736) — format-only arm, no instruction
  or constraint arm (as established last pass).
- **Template Constrained Decoding for recurring questions**
  (arXiv:2604.28028) — logit-level template enforcement for production
  recurring queries; no soft-instruction control found in abstract;
  adjacent, cite in related work.

What remains claimable for us: the first decomposition on BIRD of a
**semantic, accuracy-improving** constraint (minimal projection) into
format-only (+0.88), instruction-only (+6.47), and compiler-enforced
(+9.71) arms under a closed no-logit API, with the super-additive
interaction ("instruction is best-effort, compilation is a guarantee").
Weakness to fix before claiming a "2x2": the fourth cell (IR format +
soft projection instruction, compiler NOT enforcing) is missing; without
it "super-additive" is an inference across non-orthogonal arms. That cell
costs ~340 calls and would complete a true factorial design.

---

## Assumption 4 — Quick factual checks

**(a) BIRD Mini-Dev status.** Officially alive and promoted
(bird-bench.github.io: optimized + re-uploaded to HuggingFace Jul 2025;
3 dialects; Mini-Interact added Nov 2025). BUT its credibility as gold is
now contested in print:

- *Pervasive Annotation Errors Break Text-to-SQL Benchmarks and
  Leaderboards* (arXiv:2601.08778, v3 2026): expert audit finds **52.8%
  of Mini-Dev examples (263/498) have annotation errors** (vs 32.3% in
  prior work); corrected a 100-example BIRD Dev sample (48% fixed);
  re-evaluating 16 open-source agents on corrected data shifts rankings
  by up to 9 positions (CHESS 7th→1st, 62%→81%); original-vs-corrected
  rank correlation only rs=0.32. Releases SAPAR pipeline.
- CIDR 2026: *Text-to-SQL Benchmarks are Broken: An In-Depth Analysis of
  Annotation Errors* (Jin et al.) — same thesis at a DB venue.
- 2026 papers still report Mini-Dev but increasingly on **corrected**
  versions: ReViSQL (arXiv:2603.20004) reports 93.2% on an
  "expert-verified BIRD Mini-Dev" and claims above-human (92.96% proxy);
  MCI-SQL uses its own BIRD-clear (412 corrected gold).

Implication: full dev 1534 remains the comparable headline number, but
any 2026 submission should acknowledge gold noise and ideally report a
corrected-subset sensitivity check. Never compare our 340-slice numbers
to Mini-Dev numbers — different question sets AND different gold quality.

**(b) Recent (Mar-Jul 2026) papers not to miss:**

- PCC-SQL (arXiv:2607.12341, Jul 2026) — see assumption 3; now must-cite.
- ReViSQL (arXiv:2603.20004, Mar 2026) — human-level EX on verified
  Mini-Dev via clean-data fine-tuning; context for "how solved is BIRD";
  no IR, no projection constraint.
- ErrorLLM (arXiv:2603.03742, KDD 2026) — error-token-conditioned
  refinement LLM; related-work item for measurement-driven repair.
- Pervasive Annotation Errors (arXiv:2601.08778) — must-read for eval
  methodology and rebuttals.
- Beyond the Mean (arXiv:2604.27405) — flip-count significance
  methodology; arms the moderation figure against churn critiques.
- Test-Time Verification via Outcome Reward Models (arXiv:2606.30851) —
  verifier-based selection, no IR; skim only.

---

## Net effect on the plan

1. Literal-validity gate: demote to a boundary experiment inside the
   generalization study; oracle first, expect small or negative headline.
2. Moderation figure: the claim is open; invest in defenses (matched-pair
   Sonnet/Qwen, compliance-adjusted Qwen delta, McNemar, +1-2 models if
   cheap) rather than in more prose.
3. Instruction-vs-enforcement: claimable; add the missing 4th cell
   (IR format + instruction, no enforcement) to make the factorial clean;
   cite PCC-SQL as the compliance-domain analogue.
