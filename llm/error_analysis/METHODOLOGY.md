# GPT-5.2 Text-to-SQL Structural Error Attribution

## Overview

### Goal
Use GPT-5.2 to generate predicted SQL on BIRD Mini-Dev (SQLite), measure execution
accuracy (EX, expected ~55%), then **locate which structural component of the SQL the
errors concentrate in** (SELECT/aggregation, JOIN, WHERE, GROUP BY, etc.), to inform
later prompt / fine-tuning improvements.

Data scope: `data/mini_dev_sqlite.json` indices `[0:128] + [346:500]`, **282 questions**
total (7 databases) — the subset I am responsible for.

### Steps
1. **Step 1 — Generate + evaluate**
   - `01_generate.py`: for each question in the subset, build the prompt with
     `llm/src/prompt.py:generate_combined_prompts_one`, call GPT-5.2 to generate SQL,
     and write `outputs/predictions.json` (key = original dataset index).
   - `02_evaluate.py`: reuse `evaluation/evaluation_utils.py:execute_sql`, execute pred
     and gold per question and compare result sets for equality, write
     `outputs/eval_results.jsonl` (with a `passed` flag), and print overall EX broken
     down by difficulty.
2. **Step 2 — Wrong-SQL structure**: `03_analyze_wrong.py` runs structural analysis on
   every **predicted SQL** where `passed==0`.
3. **Step 3 — Corresponding correct-SQL structure**: `04_analyze_gold.py` runs the same
   analysis on the **gold SQL** for the same failing questions.
4. **Step 4 — Automatic comparison**: `05_compare_report.py` diffs wrong pred vs gold
   clause by clause and tallies **which component is wrong most often**, producing
   `outputs/error_report.md` + `outputs/error_breakdown.csv`. **Fully automatic, no manual work.**
   - Shared helper `categorize_failures(w, g)` (defined in `build_report.py`, shared by
     `build_report.py`/`07_synthesize_insights.py`): for each failing question it computes
     `diffs`/`p_only`/`g_only`/`cat` uniformly, so the two scripts don't each repeat the
     diff+classify logic.
5. **Step 4b — Per-question side-by-side**: `06_pairwise.py` prints, for each failing
   question, the pred/gold AST clause diff, relational algebra, and BNF derivation as
   three side-by-side views.
6. **Step 5 — LLM attribution synthesis**: `07_synthesize_insights.py` builds a prompt
   from the `categorize_failures()` statistics (clause-diff frequencies + real examples
   sampled per bucket, requiring each example to have non-empty RA text) and makes a single
   LLM call to produce `outputs/insights.json` (`ra_bullets`/`bnf_bullets`/`root_cause`,
   all citing real idx values, no fabrication allowed).
7. **Report rendering**: `build_report.py` reads
   `eval_results.jsonl`/`wrong_pred_analysis.jsonl`/`gold_analysis.jsonl`/`insights.json`
   and renders a light, information-dense `report.html` (tabs by difficulty; failing cases
   expand to show the AST diff and RA/BNF views). All numbers come from the actual run; nothing is hardcoded.

### Why sqlglot instead of asking the LLM to produce the AST
Asking an LLM to "produce the AST" hallucinates, is format-inconsistent, and is not
reproducible. The AST and clause fingerprints must be **deterministic**, so we parse with
`sqlglot.parse_one(sql, read="sqlite")` to get a real AST and comparable per-clause
fingerprints (`sql_struct.py`). The LLM is kept only where it genuinely adds value and
deterministic tools fall short: **relational-algebra translation** and
**natural-language error categorization** (`llm_analyze.py`).

### How the "BNF" dimension is preserved
Talking about "the BNF" of a single SQL statement is conceptually invalid (BNF describes
a language, not an instance). This pipeline preserves the dimension by splitting it in two:
- **Deterministic part**: `sql_struct.productions()` walks the AST node types and exports
  the "sequence of grammar productions" the statement uses.
- **LLM part**: `llm_analyze.py` has GPT-5.2 emit a BNF-style derivation snippet
  (`bnf_derivation`), written into the `.md` for human review.

### Clause category definitions (Step 4 comparison dimensions)
`SELECT` (projection expressions, aliases stripped) · `DISTINCT` · `AGGREGATION` (set of
aggregate functions) · `FROM` (set of base tables) · `JOIN` (join type + ON condition) ·
`WHERE` (set of atomic predicates after splitting top-level AND) · `GROUP_BY` · `HAVING` ·
`ORDER_BY` (expressions + asc/desc) · `LIMIT` · `SUBQUERY` (number of nested SELECTs) ·
`SET_OP` (UNION/INTERSECT/EXCEPT) · `FUNCTION` (non-aggregate scalar functions) ·
`CAST` (target type).
Pseudo-categories: `PARSE_ERROR` (prediction cannot be parsed) · `EMPTY_PRED` (no SQL
generated) · `SEMANTIC_EQUAL_STRUCT` (structurally identical to gold but wrong result,
usually a literal/semantic-level difference).

### How to read error_report.md
The table is sorted descending by "number of failing questions exhibiting a diff in this
category". A single question can fall into multiple categories, so the percentages sum to
over 100%. The top-ranked category = the **SQL component GPT-5.2 gets wrong most often**
on this subset; prioritize it. Normalization is heuristic: a different alias name is counted
as a diff (e.g. pred uses `T1` while gold uses an alias), so confirm against the examples in
the `.md` when interpreting.

### Run order
Call GPT-5.2 via the AIML API (OpenAI-compatible): `cp error_analysis/.env.example error_analysis/.env` then fill in the AIML key.
```bash
python3 error_analysis/test_compare.py            # First validate Step 4 logic (no API needed)
python3 error_analysis/01_generate.py             # Step 1a generate (--limit N for a smoke test)
python3 error_analysis/02_evaluate.py             # Step 1b evaluate → ~55%
python3 error_analysis/03_analyze_wrong.py        # Step 2
python3 error_analysis/04_analyze_gold.py         # Step 3
python3 error_analysis/05_compare_report.py       # Step 4 report (deterministic, can rerun alone)
python3 error_analysis/06_pairwise.py             # Step 4b per-question BNF/AST/RA side-by-side
python3 error_analysis/07_synthesize_insights.py  # Step 5 LLM attribution synthesis -> outputs/insights.json
python3 error_analysis/build_report.py            # Render report.html (data-driven, no hardcoding)
```

---

## English prompts (for reproducibility / audit)

### Step 1 — SQL generation prompt
Built by `llm/src/prompt.py:generate_combined_prompts_one` = schema dump + question +
external knowledge (evidence) + chain-of-thought + an instruction to return only the
`SELECT ...` SQL with no comments or code fences. Reused unchanged from the existing pipeline.

### Step 2 / Step 3 — per-statement structural analysis prompt (`llm_analyze.py`)
```
You are a database theory expert. Analyze ONE SQL statement.

SQL:
{sql}

Return ONLY a JSON object with exactly these keys:
- "relational_algebra": the query expressed in relational algebra, using operators
  σ (select), π (project), ⋈ (join), × (product), ρ (rename), γ (group/aggregate),
  ∪ ∩ − (set ops), τ (sort). One line of plain text.
- "bnf_derivation": a short BNF-style derivation showing which grammar productions
  this statement uses, e.g. "<query> ::= SELECT <proj> FROM <rel> WHERE <cond>;
  <proj> ::= <agg>(<col>) ...". Keep it under 6 lines.
- "nl_note": one sentence describing what the query computes.

No markdown, no code fences, no extra text. JSON only.
```

### Step 4 — comparison
Fully deterministic Python (`sql_struct.diff_categories`); no LLM prompt involved.
