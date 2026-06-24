"""LLM-side structural analysis (GPT-5.2): the parts deterministic tools do poorly.

For one SQL statement, returns JSON:
  relational_algebra : RA expression (text)
  bnf_derivation     : BNF-style derivation sketch (the LLM part of the retained BNF dimension)
  nl_note            : one-line natural-language description of what the query computes
"""
import json
import re

PROMPT_TEMPLATE = """You are a database theory expert. Analyze ONE SQL statement.

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

No markdown, no code fences, no extra text. JSON only."""


def _extract_json(text):
    if text is None:
        return {}
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"_raw": text}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"_raw": text}


def analyze_llm(client, sql, chat_fn):
    prompt = PROMPT_TEMPLATE.format(sql=sql)
    try:
        out = chat_fn(client, prompt, max_completion_tokens=1024)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    return _extract_json(out)
