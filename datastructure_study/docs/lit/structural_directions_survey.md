# Structural directions survey (2nd pass, 2026-07-23)

Scope: (1) scoop re-check since the first novelty survey
(`m3_novelty_survey.md`, 2026-07-23 same day — this pass adds papers found
under new search angles); (2) which structural/code-level research moves
remain open given our constraints (closed chat API, no logits; research not
engineering). Project context: RA-IR JSON -> deterministic compiler,
minimal-projection enforced, 48.24 -> 57.94 EX on the 340-slice; Ablation A
smoke says free-SELECT IR format alone contributes ~0.

---

## 1. Scoop check — new papers since first pass

### SQLStructEval (arXiv:2604.06736, Apr 2026) — THE ONE THAT MATTERS
Structural Evaluation of LLM Text-to-SQL Generation.
https://arxiv.org/abs/2604.06736

- Publishes the *generation mechanism* we use: closed-API LLM emits a JSON
  IR (fields: select / from / joins / where / group_by / having / order_by /
  limit / distinct) -> internal AST -> deterministic SQL compilation.
  Stage validity on their models: 98.8% JSON valid, 97.1% compilable.
- Motivation is structural *consistency/reliability* (LLMs emit structurally
  diverse SQL for paraphrases even when execution-correct), NOT any failure
  bucket. No constraint on SELECT; "no explicit constraints beyond SQL
  validity".
- Numbers: Spider only. EX 0.742 (direct SQL) -> 0.785 (compile-style),
  i.e. +4.3 points from the *format alone* on Spider. No BIRD.
- Models: GPT-5-mini, GPT-4.1-mini, Claude-4.5, Gemini-3-Pro, DeepSeek-V3.1
  — all via API, confirming compile-style works without logits.
- Consequence for us: "JSON-IR + deterministic compile improves closed-API
  text-to-SQL" is now published prior art. Our claim must be narrowed to the
  *enforced clause-level constraint*, and our Ablation A becomes doubly
  important: on BIRD-340 the free-SELECT format gives ~0 (smoke), which
  *contradicts* their Spider finding and isolates the constraint as the
  active ingredient. That tension (format helps on Spider, not on BIRD;
  constraint is what moves BIRD) is itself a publishable observation.
  MUST cite; MUST run Ablation A on the full 340.

### PCC-SQL (arXiv:2607.12341, Jul 2026)
Policy-Conditioned Constrained Decoding for Column-Level Access Control.

- Formalizes *column-use policy by semantic role* (output / filter /
  aggregation argument) and enforces it via per-token logit masks aligned
  with grammar productions. Deterministically eliminates column-use
  violations in one decoding pass.
- Closest in *spirit* to per-clause column constraints, but (a) needs
  logits (out for us), (b) goal is access-control compliance, not accuracy /
  over-selection. Not a scoop; cite as evidence the field is converging on
  per-clause column-role constraints, and position ours as the no-logits
  variant driven by measured failure buckets.

### Both Ends Count follow-ups
No generation-time fix for "superfluous columns" has appeared since
arXiv:2602.21480 (which only proposed the metric). Verdict: **not scooped**
on minimal-projection *enforcement*.

### MCI-SQL (arXiv:2603.13390) — BIRD dev 74.45 (full 1534, not comparable
to our slice). Metadata-enriched context + mid-generation validation +
candidate selection. Ensemble/context engineering, no IR, no projection
constraint. Also built BIRD-clear (412 corrected samples) — useful citation
for gold-annotation noise, which we observed in the M3 smoke.

---

## 2. Direction-by-direction assessment

### D1. Second clause constraint: GROUP BY via functional dependencies — OPEN
- Prior art: MySQL's ONLY_FULL_GROUP_BY (engine-side FD check, classical);
  MapleDoctor taxonomy has "unaligned aggregation structure" as an error
  class; Post-SQLFix (below) checks context-sensitive semantics *post-hoc*
  on SQL text. Nobody enforces FD-closure-correct GROUP BY inside a
  generation-time IR compiler under a closed API.
- Needs logits? No — same enumerate-in-IR + compiler-enforce pattern as M3.
- Research or engineering? Research IF framed as the second instance of the
  general principle (see D5); engineering if bolted on alone.
- Prerequisite (zero-token): re-bucket M3's remaining 143 failures; count
  GROUP BY/aggregate-structure errors; build a GROUP BY oracle (patch gold
  grouping keys into saved IR, recompile, re-execute) to bound the gain.

### D2. JOIN skeleton from FK graph as hard constraint — CROWDED at input
side, sliver open at compiler side
- Graph-Link (ICML 2026): schema linking as constrained subgraph induction,
  Steiner-tree optimization, guarantees topological connectivity — but the
  graph shapes the *input* to the LLM, not a check on emitted structure.
  Also SteinerSQL (arXiv:2509.19623), SchemaGraphSQL (EACL Findings 2026),
  PPR-SQL (2026, PageRank pruning over FK network).
- The un-taken sliver: compiler-side rejection/repair of IR join trees not
  on the FK graph. But M1 already showed the AST/schema layer ceiling is 0
  on our slice (335/340 syntactically fine), and join-path errors were not
  the dominant bucket. Expected gain small unless re-bucketing says
  otherwise. Verdict: low priority; do not pursue without a bucket count.

### D3. Structural-edits-only execution-feedback repair — NOW CROWDED
- Post-SQLFix ("From Ambiguous Feedback to Verifiable Repair via Formal
  Synthesis", OpenReview 2BMCdwI0m1, Oct 2025, ICLR 2026 cycle):
  canonicalizes SQL to a canonical query structure, symbolic engine produces
  sound diagnoses (syntactic / context-free / context-sensitive), then
  synthesizes a *constrained space of formally verifiable repair plans*.
  +11.6% EX on BIRD/Spider, half the repair iterations vs raw execution
  feedback. This is exactly "repair restricted to verified structural edits".
- SIRIUS-SQL (arXiv:2606.01246): cascade of cheap high-precision structural
  edits before LLM escalation for empty-result repair; structural check as
  low-margin tiebreaker in candidate selection.
- Verdict: the direction is taken. Only a repair-on-*IR* variant remains,
  and that is an increment on Post-SQLFix, not a new mechanism. Skip.

### D4. Value/entity grounding as structural constraint — CROWDED, mostly
engineering
- PV-SQL (arXiv:2604.17653): DB probing discovers storage form of values
  ("California" -> "CA") + rule-based verification that required values
  appear. DeepEye-SQL (arXiv:2510.17586): semantic value retrieval module.
  Alpha-SQL: LSH value retrieval. CHESS earlier. All feed values into the
  prompt or verify post-hoc.
- Compiler-side literal validation against our enum value index is a small
  delta over PV-SQL's verify step; reviewers will read it as engineering.
- Verdict: skip as a headline; keep as a compiler warning feature only if
  re-bucketing shows a large wrong-literal bucket.

### D5. Formal guarantees of the deterministic IR compiler — OPEN as a
FRAMING, thin as a standalone
- LLM-codegen formal methods exist (LLMLift NeurIPS'24 Hoare-logic
  verification, VeriGuard, compile-translation position papers, "New
  Compiler Stack" survey arXiv:2601.02045), but none states a guarantee
  taxonomy for text-to-SQL IR compilation: what the compiler *proves*
  (well-formedness, schema validity, projection cardinality == declared
  intent arity) vs what stays best-effort (semantic clause content).
- SQLStructEval's line "structure as an explicit intermediate artifact
  rather than an implicit decoding constraint" is the closest phrase; they
  do not formalize guarantees.
- Needs logits? No. Zero API cost — it is a theorem-and-proof section over
  `ra_to_sql.py`.
- Verdict: not a standalone paper, but the right *language* for the
  generalizable principle the professor wants. Fold into D6.

### D6. The generalizable principle: oracle-gated clause-level constraints —
OPEN, and it is our natural next move
- Nobody publishes the loop: measure failure buckets -> per-clause oracle
  upper bound -> enforce exactly that clause in the IR compiler -> re-measure.
  SQLStructEval has the compile mechanism without targeting; Both Ends Count
  has the measurement without a fix; PCC-SQL has per-clause enforcement but
  logit-level and for policy, not accuracy.
- A second clause instance (D1's GROUP BY, or whatever re-bucketing
  nominates) turns M3 from a one-off into a testable principle: "a clause is
  fixable by compiler enforcement iff its correct form is computable from
  schema structure + declared intent, independent of question semantics."
  Projection (arity from the ask) and GROUP BY (FD closure from PKs) satisfy
  this; WHERE content does not — which *predicts* where the method stops
  working. A principle that predicts its own failure boundary is a research
  contribution.

### D7. Test-time scaling x IR: voting in canonical IR space — HALF-OPEN
- Existing: self-consistency over SQL strings (C3/DAIL-SQL/CSC-SQL),
  execution-result-pooled voting (SIRIUS-SQL, CHASE-SQL selector).
  SQLStructEval shows high structural diversity under repeated sampling and
  that compile-style raises AST similarity (0.552 -> 0.632) — i.e. the IR
  canonicalizes away spurious diversity.
- Open question: does voting over *canonicalized IR* (compiler-normalized)
  beat voting over SQL strings at equal sample count, i.e. is IR-mediation
  sample-efficient for self-consistency? Not studied. Composes with our
  pipeline. Needs no logits.
- Cost: k samples/question = k x 340 paid calls; no true zero-token oracle
  (we have one sample per question). Cheapest probe: k=3 on the 60-question
  over-selection bucket (~180 calls). Rank below D6/D1 for cost reasons.

---

## 3. Hypotheses in repo format (mechanism, bucket, gain path) + required
zero-token prerequisite

- **H-D1 (GROUP BY):** enforcing FD-closure-consistent grouping keys in the
  IR compiler fixes the "unaligned aggregation structure" bucket, because
  correct grouping keys are computable from PK/uniqueness metadata plus the
  projection, not from question semantics. Prerequisite: re-bucket the 143
  remaining M3 failures + GROUP BY-patch oracle on saved IR (zero token).
- **H-D6 (principle):** a failure bucket is fixable by compiler-level
  constraint iff the correct clause form is derivable from schema structure
  + declared intent; buckets failing this test (WHERE content, ratio logic)
  will show ~0 oracle headroom. Prerequisite: per-clause oracle table over
  all 143 remaining failures (zero token) — this single table is the
  paper's central figure.
- **H-D7 (IR voting):** majority vote in compiler-canonicalized IR space
  needs fewer samples than SQL-string voting for the same EX, because the
  compiler removes execution-irrelevant structural variance (SQLStructEval's
  diversity finding). Prerequisite: none zero-token; first paid probe k=3 on
  the over-selection bucket (~180 calls, needs approval).
- **H-D5 (guarantees):** the compiler's provable properties (well-formed
  output, schema-valid references, projection arity == declared intent)
  partition our EX gain into "guaranteed-by-construction" vs "best-effort"
  components. Prerequisite: none — proofs over `ra_to_sql.py` + re-tally of
  the 49 flipped-up questions by which guarantee was binding (zero token).

## 4. Ranked verdict

1. **D6+D1+D5 bundled** — the generalization study. Research, zero-token
   first step, directly answers "principle not pipeline".
2. **D7 IR-space voting** — genuinely open, composes, but costs API calls
   and is a smaller claim.
3. **D2 join constraint** — only if re-bucketing shows a join bucket; else
   dominated by ICML'26 Graph-Link at the input side.
4. **D3 repair / D4 value grounding** — taken (Post-SQLFix) / engineering
   (PV-SQL et al.). Skip both.
