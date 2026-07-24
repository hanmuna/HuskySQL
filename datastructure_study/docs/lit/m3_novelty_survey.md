# M3 Novelty Survey: RA-IR + Deterministic Compiler vs Prior Art

Scope: assess whether M3 ("LLM emits RA-IR JSON with enforced minimal `select`,
compiled to SQL by a deterministic ~120-line compiler, motivated by a measured
34% over-selection failure bucket + a zero-cost oracle upper bound, under a
closed chat API with no logits") is a defensible research contribution or
"just engineering," against published work. All numbers below are reported
as either (a) the paper's own full-dataset numbers (Spider/BIRD full dev,
1534q), clearly labeled, or (b) our own 340-question BIRD dev slice numbers
(california_schools + financial + toxicology) — never conflated.

---

## Thread 1 — Classic IR-based text-to-SQL (fine-tuned era)

### IRNet / SemQL — Guo et al., ACL 2019, "Towards Complex Text-to-SQL in
Cross-Domain Database with Intermediate Representation"
arXiv: https://arxiv.org/abs/1905.08205 · ACL: https://aclanthology.org/P19-1444/

- Introduces SemQL, a grammar-based IR sitting between NL and SQL; pipeline
  is schema linking → grammar-based neural decoder emits SemQL → SemQL is
  **deterministically compiled to SQL** (this half of the pattern — IR +
  deterministic compiler — is not new; IRNet did it in 2019).
- SemQL simplifies by removing set operators / some SQL syntax noise, but
  its SELECT/projection is still whatever the grammar decoder emits — there
  is **no explicit "select is an enumerated minimal list" constraint**; the
  grammar constrains *validity* (is this a legal SemQL tree), not *minimality*
  of one particular clause.
- Trained end-to-end on a grammar-based neural decoder (Seq2Tree over SemQL
  productions) — requires access to the model's generation process
  (fine-tuned model, grammar decoding at the token/production level).
  **Not applicable to a closed chat API with no logits.**
- Evaluated on Spider only (predates BIRD, predates knowledge/evidence
  setting).

### NatSQL — Gan et al., 2021, "Natural SQL: Making SQL Easier to Infer from
Natural Language Specifications"
arXiv: https://arxiv.org/abs/2109.05153

- A second-generation IR explicitly designed to be *closer to NL surface
  form* than SemQL: drops explicit JOIN/GROUP BY/HAVING keywords, lets a
  seq2seq model infer them implicitly, then a deterministic post-processor
  reconstructs full SQL (again: IR + deterministic compiler, same pattern
  as IRNet, still not new).
- Also used with fine-tuned encoder-decoder models (T5, RAT-SQL variants);
  the QPL paper's own comparison table (Table 1, Spider dev, fine-tuned
  models) shows NatSQL+RAT-SQL at 73.7% overall EX vs DIN-SQL/GPT-4 at
  74.2% and GPT-3.5-turbo zero-shot at 74.3% — i.e. by 2023 a bare zero-shot
  LLM prompt without any IR already matched a fine-tuned IR pipeline on
  Spider. This is useful context: IRs bought their gains in the pre-LLM
  era; the open question this survey is checking is whether IR-style
  structure still buys anything **on top of** a strong closed LLM — which
  is exactly M3's setting.
- No explicit minimal-projection enforcement; no BIRD evaluation; no
  closed-API/no-logits treatment.

### QPL (Query Plan Language) — Eyal et al., EMNLP Findings 2023, "Semantic
Decomposition of Question and SQL for Text-to-SQL Parsing"
arXiv: https://arxiv.org/abs/2310.13575 · repo: https://github.com/bgunlp/qpl
(companion framing paper: arXiv 2312.14798, "Targeting Query Plans vs. SQL")

Read in full (not just abstract) — this is the closest structural relative
to M3's IR, so worth detail:

- QPL is a **tree of 9 operators** (Scan, Aggregate, Filter, Sort, TopSort,
  Join, Except, Intersect, Union), each node context-free (only depends on
  its own inputs, unlike physical nested-loop plans). Every node carries an
  explicit `Output [...]` column list — so in some sense *every* QPL node
  has an enumerated projection, not just the root. This is structurally
  close to what M3 does with its single `select` field, but generalized to
  every intermediate node (modularity/interpretability was the goal, not
  anti-over-selection).
- QPL is derived **deterministically from gold SQL** via Microsoft SQL
  Server's query optimizer execution plans (SQL → optimizer plan → QPL).
  The *learned* direction is NL → QPL (fine-tuned Flan-T5-XL, 3B, 15 epochs).
  Decoding is constrained with **PICARD** (an incremental parser operating
  on model logits at each decoding step, enforcing QPL grammar validity).
  This is genuinely grammar/logit-level constrained decoding — **not
  reproducible on a closed chat API** (this is exactly the gap M3's
  authors flagged as a hard constraint in `docs/IMPLEMENTATION_GUIDE.md`).
- QPL was evaluated on **Spider only** (not BIRD); its stated goals are
  compositional generalization to complex queries and non-expert
  interpretability (they ran a user study showing non-experts verify QPL
  outputs better than raw SQL). **Nowhere does the QPL paper name, measure,
  or specifically target a "SELECT over-selection" failure class** — that
  framing (and the 34% number) is a BIRD-specific empirical finding this
  project made, not something QPL set out to fix.
- Bottom line: QPL is the closest prior IR to M3's mechanism (tree IR with
  per-node explicit projection, deterministic IR→SQL compiler) but differs
  on every axis that matters for the novelty claim: (a) fine-tuned model +
  logit-level grammar decoding vs. M3's closed-API JSON-schema-only
  constraint, (b) modularity/interpretability motivation vs. M3's
  failure-bucket-driven minimal-projection motivation, (c) Spider vs. BIRD,
  (d) no over-selection framing at all.

### RESDSQL — Li et al., AAAI 2023, "Decoupling Schema Linking and Skeleton
Parsing for Text-to-SQL"
arXiv: https://arxiv.org/abs/2302.05965

- Not really an IR; decouples schema-item ranking (cross-encoder filters
  relevant tables/columns) from "skeleton" decoding (SQL keyword structure
  without concrete schema items) in a fine-tuned seq2seq model. Mentioned
  for completeness — orthogonal to M3 (schema linking, not projection
  enforcement), fine-tuned only, Spider/robustness variants only.

**Thread 1 verdict:** the "IR + deterministic compiler" pattern is
30-year-old-DB-textbook / at-least-2019-NLP-old. What none of IRNet /
NatSQL / QPL do is (a) run under a closed, logit-free chat API, or (b)
single out minimal SELECT-list enforcement as the one thing structurally
guaranteed while leaving WHERE/expressions as a raw-SQL escape hatch. That
second point — deliberately constraining *only* the one clause identified
by failure analysis as unfixable-by-prompting, and deliberately *not*
constraining the semantic clauses — is a design choice none of these
papers make (they constrain the whole grammar, because they have logit
access and can afford to).

---

## Thread 2 — Constrained/grammar decoding

### PICARD — Scholak, Schucher, Bahdanau, EMNLP 2021
arXiv: https://arxiv.org/abs/2109.05093 · repo:
https://github.com/servicenow/picard

- Incremental parser wrapping a fine-tuned autoregressive model (T5);
  at every decoding step it uses the model's logits/beam and rejects
  tokens that would make the partial output an invalid/unresolvable SQL
  query (including schema-invalid column references). Requires full
  logit/beam access to the decoder. **Structurally impossible to
  replicate against GPT-5.2 via a closed chat API** — this is exactly why
  the project's `IMPLEMENTATION_GUIDE.md` route C ("real grammar-constrained
  decoding") was marked as requiring a model swap to open weights.

### JSON-schema / grammar-constrained structured output (xgrammar,
Outlines, vLLM guided decoding, OpenAI Structured Outputs)
- General survey: "Generating Structured Outputs from Language Models:
  Benchmark and Studies," arXiv 2501.10868 (https://arxiv.org/html/2501.10868v1).
- Mechanism: JSON Schema → compiled to a finite-state machine / CFG; at
  each token the engine masks invalid next-tokens to probability 0. This
  is **still logit-level** — it needs the serving stack (vLLM/SGLang/local
  HF) to expose token probabilities, or a provider's own hosted constrained
  decoding (OpenAI's `response_format: json_schema` / function calling,
  which under the hood is provider-side constrained decoding you don't
  control or observe).
- **This is the key distinction for M3's framing**: OpenAI-style "JSON
  mode" only guarantees *syntactic* JSON validity (and, with strict
  schemas, field types/required-keys) — it does **not** and **cannot**
  guarantee a semantic invariant like "this array contains no more items
  than the question asked for." Minimal-projection is a *content*
  constraint, not a schema-shape constraint, so provider-side JSON-schema
  enforcement alone would not have solved the over-selection bucket even
  if used — M3's actual lever is the **downstream deterministic compiler
  refusing to look anywhere outside the `select` field**, combined with
  a prompt that asks for a minimal list. Nobody in this thread does
  "constrain a semantic-minimality property via output-schema-shape +
  a post-hoc deterministic compiler, under a closed API" as a named
  substitute for real grammar decoding — that combination (not the IR
  idea itself, which is old) is the part worth stating explicitly as the
  mechanism-level delta.

**Thread 2 verdict:** every constrained-decoding paper in this space
assumes logit/beam access. M3's actual mechanism is not "constrained
decoding" in the PICARD/xgrammar sense at all — it is "ask for a
structured artifact whose *shape* is easy for a closed API to get right
(JSON keys), then have a deterministic downstream stage physically unable
to violate the one property that matters (extra columns), regardless of
whether the *shape* constraint was itself enforced by logits or just by
prompting + JSON mode." That's a real distinction to make explicit in the
writeup: it should be named "format-mediated post-hoc structural
enforcement" and explicitly contrasted with "true" grammar-constrained
decoding, not conflated with it.

---

## Thread 3 — Recent BIRD leaderboard / 2024-2026 LLM text-to-SQL systems

Checked leaderboard (bird-bench.github.io) live plus arXiv for each:

| System | Year | What it changes | IR/plan? | Over-selection? |
|---|---|---|---|---|
| DIN-SQL | 2023 | Decomposition into sub-prompts (schema linking → classification → generation → self-correction) | No — outputs SQL directly at each stage | Not addressed |
| DAIL-SQL | 2023 | Prompt/example-selection engineering (representation + example organization) | No | Not addressed |
| MAC-SQL | 2024 | Multi-agent (Selector/Decomposer/Refiner) collaboration | No — agents emit SQL/sub-SQL | Not addressed |
| CHESS | 2024 | Retrieval (schema pruning, value retrieval via LSH) + agentic pipeline | No | Not addressed |
| RESDSQL | 2023 | Schema-linking/skeleton decoupling (fine-tuned) | Skeleton, not IR | Not addressed |
| CHASE-SQL | 2024, ICLR'25 (arXiv 2410.01943) | Multi-path generation: divide-conquer decomposition, **"chain-of-thought reasoning based on query execution plans"**, preference-optimized selection | **No** — "query execution plan" here is a *natural-language reasoning style* (CoT prompted to imitate what a DB engine would do step by step), the actual output is still free-form SQL text, not a parsed/compiled IR. Easy to mistake for an IR from the name; it isn't one. | Not addressed |
| XiYan-SQL | 2024 (arXiv 2411.08599) | Multi-generator ensemble + selection | No | Not addressed |
| Alpha-SQL | 2025 (arXiv 2502.17248) | Zero-shot MCTS search over SQL construction actions | Action sequence during search, not an emitted/compiled IR artifact | Not addressed |
| ReFoRCE | 2025 | Self-refinement + consensus voting + column exploration | No | "Column exploration" = schema/value retrieval, not projection minimality |
| OpenSearch-SQL | 2025 | Agentic, coarse-to-fine SQL generation with alignment/consistency checks | No | Not addressed |
| Agentar-Scale-SQL | 2025 (arXiv 2509.24403), current #2 overall leaderboard | Orchestrated test-time scaling (many candidates + verification) | No | Not addressed |
| AskData+GPT-4o | 2025 (arXiv 2505.19988), current #1 overall leaderboard | Agentic data-access system | No | Not addressed |

None of the current top BIRD leaderboard entries generate an intermediate
structured plan that a deterministic compiler turns into SQL — they are
uniformly variants of (a) better retrieval/schema-linking, (b) multi-agent
decomposition still emitting free-form SQL at the leaf, (c) sampling +
selection/self-consistency over many free-form SQL candidates. **This is
itself a notable gap**: the entire leaderboard is chasing gains through
more candidates / better selection / better retrieval, not through
constraining what a single candidate is allowed to say. M3's approach is
orthogonal to essentially the whole current leaderboard and could in
principle be layered under any of them (their agents could emit RA-IR
instead of SQL at the final step).

**Thread 3 verdict:** no leaderboard system does IR-generation +
deterministic-compile, and none specifically attacks column
over-selection as a named mechanism (only diagnose it, see Thread 4).

---

## Thread 4 — Does anyone name "SELECT over-selection" as a distinct
failure class and fix it?

### "Both Ends Count! Just How Good are LLM Agents at Text-to-Big SQL?"
Eizaguirre, Tissen, Sánchez-Artigas, arXiv 2602.21480 (v4, April 2026)
https://arxiv.org/html/2602.21480

- **This is the closest published naming of the exact phenomenon.** They
  define a "Category C: Superfluous columns" failure — valid rows,
  extra/irrelevant columns in the SELECT — and a column-precision metric
  `P(S, Ŝ) = |S ∩ Ŝ| / |Ŝ|` they call **"minimal projection overhead"**
  to penalize it in place of binary EX.
- Evaluated on BIRD (10 queries × 50 iterations × 11 models = 5,500
  executions; 930 incorrect translations). They give a concrete example
  (query 886: models return `year, MAX(round)` instead of just `year`) —
  structurally identical to this project's idx6/idx10/idx14 examples.
- **Critically: they propose no generation-time fix.** Their contribution
  is a **better evaluation metric (VES\*)**, not a method — they explicitly
  frame query rewriting / semantic matching as "future work," not
  something they built or tested. So the diagnosis is prior art (and very
  recent, essentially concurrent with this project's own failure
  analysis), but **the fix is not** — nobody has closed the loop from
  "we can now measure superfluous columns" to "here is a mechanism that
  structurally prevents them."
- This paper should be cited prominently: it independently validates
  that over-selection is a real, named, measured phenomenon on BIRD (not
  just an artifact of this project's own 340-slice), which strengthens
  the motivation section, while also meaning the "we discovered this
  failure class" framing must be softened to "we independently measured
  and confirmed this failure class, and — unlike prior work — fixed it
  structurally."

### "Understanding, Detecting, and Repairing Real-World In-Context-Learning-
Based Text-to-SQL Errors" — Shen et al., ACM Proc. Softw. Eng. (FSE) 2026
arXiv 2501.09310 (v3, June 2026) https://arxiv.org/abs/2501.09310

- Large empirical taxonomy: 27 error types across 7 categories (Syntax,
  Schema, Logic, Convention, Semantic, Not-an-Error, Others/Unclassifiable),
  built from DIN-SQL/MAC-SQL/CHESS/DAIL-SQL-style outputs with GPT-3.5/GPT-4o
  on **both BIRD and Spider** (6,136 generated SQL queries total on BIRD).
- Has a category **"E2: Projection Error"** under Semantic Error: "The
  SELECT statement contains incorrect columns or formats." Their own
  worked example ("Whose post has the highest popularity?" → model
  incorrectly selects `MAX(ViewCount)` instead of `DisplayName`) is a
  **wrong-column** case, not an **extra-column** case — i.e. their
  taxonomy conflates "picked the wrong column" (semantically incorrect
  logic) with "picked the right column plus extra ones" (semantically
  correct logic, extra projection) under one bucket. **They do not
  separately isolate "logically correct query, just too many SELECT
  columns" as its own class the way this project's `extra_columns_*`
  buckets do** — which is a real, usable distinction point: this
  project's failure taxonomy is finer-grained on exactly the axis that
  matters for motivating a projection-only fix.
- Their proposed fix, **MapleDoctor**, is a **post-hoc detection-and-
  repair** framework operating on already-generated free-form SQL text
  (pattern/rule-based repairers per error type, some LLM-assisted
  validation) — reported as repairing "13.8% more queries" than existing
  repair baselines with fewer mis-repairs. This is a fundamentally
  different mechanism family from M3: repair-after-the-fact on SQL text,
  vs. M3's constrain-the-output-format-so-the-error-cannot-be-expressed-
  in-the-first-place. Also note: this is a **repair layer bolted onto
  whatever SQL the ICL model already produced** — it does not change what
  the base LLM is asked to emit, whereas M3 changes the emission target
  itself (IR, not SQL).

**Thread 4 verdict:** the failure class is independently confirmed by two
2026 papers (one names it almost identically — "superfluous
columns"/minimal projection overhead; one buries a related-but-conflated
version inside a broader taxonomy). **Neither proposes a generation-time
structural fix.** One proposes a metric, the other proposes post-hoc
repair of free-form SQL. This is the strongest part of M3's novelty case:
the gap between "we can now measure/name this" (2026 prior art, both
papers) and "we prevent it by construction" (M3) is real and currently
unfilled in the literature I could find.

---

## Verdict

### Is this novel enough to be a research contribution?

**Partially, and only with the right framing.** The individual pieces are
each unoriginal on their own:

- "LLM emits an IR, deterministic compiler turns it into SQL" —
  established since IRNet (2019), refined by NatSQL (2021) and QPL (2023).
- "Constrain LLM output via JSON/structured format" — standard practice
  (OpenAI Structured Outputs, function calling, `outlines`/`xgrammar`),
  not a contribution in itself.
- "Over-selection is a real BIRD failure mode" — independently discovered
  and named by "Both Ends Count!" (arXiv 2602.21480) and (in blurrier form)
  by the FSE'26 taxonomy paper (arXiv 2501.09310), both essentially
  concurrent with this project.

**What is not published, as far as this survey found:** the specific
*combination* — (1) under a closed, logit-free chat API (ruling out every
Thread-1/Thread-2 mechanism that assumes decoder access), (2) targeting
one named, measured, previously-diagnosed-but-unfixed failure class
(minimal projection / superfluous columns), (3) via a deliberately
asymmetric IR that constrains *only* the structural clause responsible for
that failure class while leaving semantic clauses (WHERE, ratio
expressions) as an intentional raw-SQL escape hatch, (4) gated by a
zero-token oracle upper-bound computed *before* committing to the
(costly, closed-API) generation run, to make the go/no-go decision
principled rather than "let's just try it."

That combination is the actual candidate contribution. It is a **narrow
but real delta over QPL/NatSQL/IRNet** (closed-API substitute for
grammar-constrained decoding + deliberately partial constraint scope) and
a **real delta over the two 2026 diagnosis papers** (structural fix vs.
metric-only / post-hoc-repair-only). It is not a new IR design, not a new
decoding algorithm, and not the discovery of the failure class — so it
must not be framed as any of those.

### Closest prior work and the exact delta

| Axis | QPL (closest IR) | "Both Ends Count!" (closest diagnosis) | M3 |
|---|---|---|---|
| Emits a plan/IR | Yes, tree of 9 ops | No (measures existing SQL) | Yes, flat `select/joins/where/...` |
| Enforces minimal projection specifically | No (enforces whole-grammar validity) | No (measures it, doesn't enforce) | Yes, only this field |
| Needs logits/fine-tuning | Yes (Flan-T5-XL + PICARD) | N/A | No (closed GPT-5.2 chat API) |
| Deterministic compiler to SQL | Yes (QPL→CTE) | N/A | Yes (~120-line compiler) |
| Motivated by a measured failure bucket | No (motivated by compositional generalization / interpretability) | Yes (defines the bucket) | Yes (34% bucket, gated by oracle bound) |
| Dataset | Spider | BIRD | BIRD (340-slice) |
| Produces a generation-time fix | Yes, but not for this failure class | No | Yes |

### How to frame it as research, not engineering

The professor's objection to the earlier work was "run model, bucket
failures, write report" — no generalizable idea. M3 needs an explicit
hypothesis/mechanism statement, e.g.:

> **Hypothesis:** under a closed, logit-free chat API, cardinality/
> enumeration constraints (e.g. "select exactly these N columns, no more")
> are more reliably enforced by moving them into a typed output field that
> a deterministic downstream compiler is structurally incapable of
> exceeding, than by natural-language negative instructions
> ("don't select extra columns") given to the same model in the same
> prompt. Free-form generation + instruction cannot make the absence of
> extra tokens the model's problem; structured-field + compiler makes it
> the compiler's — the model can still choose the wrong minimal set, but
> it cannot choose a non-minimal one.

Framed this way, minimal-SELECT-projection-on-BIRD is one *instance* of a
more general, testable principle about which classes of LLM output errors
are fixable by prompting vs. must be fixed by moving the constraint out of
natural language entirely. That is the generalizable idea a reviewer can
evaluate — not "we built an IR."

### The 3 most important framing/ablation recommendations

1. **JSON-IR-with-free-SELECT ablation (isolate format from constraint).**
   Re-run the same IR/JSON protocol but with `select` as an unconstrained
   free-form array (model can list as many columns as it wants) instead of
   the current implicit "minimal" instruction+field. If EX gain persists at
   anywhere near +9.71 without the minimality push, the driver is "asking
   the model to think structurally via JSON" (a format/attention effect),
   not "the compiler physically cannot over-project" — which would gut the
   headline mechanism claim. This is the single most important experiment
   in the paper and should be run before anything else.

2. **Prompt-only "select minimal columns" instruction ablation (no
   IR/compiler at all).** Add one sentence to the existing free-form-SQL
   baseline prompt ("Only SELECT the exact column(s) the question asks
   for, nothing else") and re-measure the 340-slice EX. The original
   REPORT.md itself asserts this bucket is "purely a prompt-instruction
   problem" (§4.2) — that claim is currently *unvalidated by a direct
   comparison*. A reviewer's first question will be "did you just try
   telling it in the prompt?" If the plain instruction recovers most of
   the +9.71, M3's compiler is not doing the load-bearing work claimed. If
   the plain instruction recovers little (plausible — negative/exhaustive
   constraints are known to be weakly followed by LLMs, unlike positive
   constraints), that gap *is* the empirical evidence for the hypothesis
   above, and turns "we assert prompting can't fix this" into "we
   measured that prompting doesn't fix this, by this much."

3. **Validate beyond the 340-question slice before claiming a general
   principle.** Everything reported so far (48.24→57.94, oracle +13.5,
   flip 49/16) is on the fixed 340-question / 3-database dev slice used
   for cheap iteration — legitimate for development, but a reviewer will
   treat any claim of generality as unsupported until shown on the full
   1534-question dev set (different databases, different SELECT
   patterns, different over-selection base rates) or on a second,
   independent failure class subjected to the same "enumerate-then-compile"
   treatment. Either the full-dev-set run or a second-instance
   generalization test is necessary to move from "we fixed 340 questions"
   to "we validated a mechanism," and the two numbers must never be
   reported side by side without explicitly labeling which slice each
   came from (per project convention already in place).

---

## Sources
- IRNet/SemQL: https://arxiv.org/abs/1905.08205 · https://aclanthology.org/P19-1444/
- NatSQL: https://arxiv.org/abs/2109.05153
- QPL: https://arxiv.org/abs/2310.13575 · https://github.com/bgunlp/qpl · companion: https://arxiv.org/abs/2312.14798
- RESDSQL: https://arxiv.org/abs/2302.05965
- PICARD: https://arxiv.org/abs/2109.05093 · https://github.com/servicenow/picard
- Structured-output benchmark survey: https://arxiv.org/html/2501.10868v1
- CHASE-SQL: https://arxiv.org/abs/2410.01943
- XiYan-SQL: https://arxiv.org/pdf/2411.08599
- Alpha-SQL: https://arxiv.org/html/2502.17248v1
- Agentar-Scale-SQL: https://arxiv.org/html/2509.24403v1
- AskData: https://arxiv.org/abs/2505.19988
- "Both Ends Count! Just How Good are LLM Agents at Text-to-Big SQL?": https://arxiv.org/html/2602.21480
- "Understanding, Detecting, and Repairing Real-World ICL-Based Text-to-SQL Errors" (MapleDoctor): https://arxiv.org/abs/2501.09310
- BIRD leaderboard: https://bird-bench.github.io/
