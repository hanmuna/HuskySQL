"""Step 5: one LLM call that writes the RA/BNF narrative bullets grounded in real
representative failures from THIS run, instead of hand-written prose copied from
an older subset run. Reads outputs/{eval_results,wrong_pred_analysis,gold_analysis}.jsonl,
writes outputs/insights.json for build_report.py to render.
"""
import os
import sys
import json
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from error_analysis import common
from error_analysis.build_report import categorize_failures, CATS

CAT_LABEL = {c[0]: c[1] for c in CATS}


def pick_examples(per_bucket, n=2):
    """idx -> coarse category, then up to n examples per bucket with usable RA text."""
    examples = {}
    for cat, idxs in per_bucket.items():
        chosen = [i for i in idxs if i["pred"].get("relational_algebra") and i["gold"].get("relational_algebra")][:n]
        if chosen:
            examples[cat] = chosen
    return examples


def main():
    ev = {x["idx"]: x for x in common.read_jsonl(os.path.join(common.OUT_DIR, "eval_results.jsonl"))}
    w = {x["idx"]: x for x in common.read_jsonl(os.path.join(common.OUT_DIR, "wrong_pred_analysis.jsonl"))}
    g = {x["idx"]: x for x in common.read_jsonl(os.path.join(common.OUT_DIR, "gold_analysis.jsonl"))}

    clause_counter = Counter()
    per_bucket = {}
    cats = categorize_failures(w, g)
    for idx, pr in w.items():
        gd = g[idx]
        c = cats[idx]
        clause_counter.update(c["diffs"])
        per_bucket.setdefault(c["cat"], []).append({"idx": idx, "pred": pr, "gold": gd, "diffs": c["diffs"]})

    n_failed = len(w)
    clause_pct = {k: round(100 * v / n_failed, 1) for k, v in clause_counter.most_common()}
    examples = pick_examples(per_bucket)

    sample_block = []
    for cat, items in examples.items():
        for it in items:
            idx = it["idx"]
            sample_block.append(
                f"### idx {idx} — bucket: {CAT_LABEL.get(cat, cat)}\n"
                f"question: {ev[idx]['question']}\n"
                f"pred SQL: {it['pred']['sql']}\n"
                f"gold SQL: {it['gold']['sql']}\n"
                f"RA pred: {it['pred'].get('relational_algebra')}\n"
                f"RA gold: {it['gold'].get('relational_algebra')}\n"
                f"BNF pred: {it['pred'].get('bnf_derivation')}\n"
                f"BNF gold: {it['gold'].get('bnf_derivation')}\n"
                f"AST clause diff: {', '.join(it['diffs']) or 'value-only'}\n"
            )

    prompt = f"""You are a database-theory expert writing the findings section of a text-to-SQL error
analysis report. The model is GPT-5.2, evaluated on {len(ev)} BIRD dev questions ({n_failed} wrong,
clause-level diff frequency over the {n_failed} failures: {json.dumps(clause_pct)}).

Below are real representative failing cases, each with the predicted and gold SQL plus their
relational-algebra (RA) and BNF-grammar-derivation views, grouped by which structural bucket they fall in:

{chr(10).join(sample_block)}

Write a JSON object with exactly these keys:
- "ra_bullets": list of 3 strings. Each is one finding about what diverges *semantically* between
  pred and gold RA expressions, grounded in one of the idx examples above. Cite the idx like "idx 42".
  Plain text, no markdown bold.
- "bnf_bullets": list of 3 strings. Each is one finding about which *grammar productions* the model
  over/under-expands relative to gold's BNF derivation, grounded in an idx example. Cite the idx.
- "root_cause": one paragraph (3-5 sentences) synthesizing the dominant failure mode across RA/BNF/AST
  and a concrete suggestion for what to fix in the pipeline (prompt, schema description, or post-processing).

Only use facts visible in the examples above — do not invent SQL or idx numbers not listed.
JSON only, no markdown fences, no extra text.
"""

    client = common.get_openai_client()
    raw = common.chat(client, prompt, max_completion_tokens=1400)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
    insights = json.loads(raw)
    insights["clause_pct"] = clause_pct
    insights["n_total"] = len(ev)
    insights["n_failed"] = n_failed

    out = os.path.join(common.OUT_DIR, "insights.json")
    json.dump(insights, open(out, "w"), indent=2, ensure_ascii=False)
    print(f"Wrote {out}")
    print(json.dumps(insights, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
