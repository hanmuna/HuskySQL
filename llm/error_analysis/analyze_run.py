"""Shared structural analysis used by 03_analyze_wrong.py and 04_analyze_gold.py.

For each FAILED question (passed==0), run sqlglot (deterministic) + GPT-5.2 (RA/BNF)
on either the predicted SQL (target='pred') or the gold SQL (target='gold').
Writes <target>_analysis.jsonl + a human-readable .md.
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from error_analysis import common, sql_struct
from error_analysis.llm_analyze import analyze_llm

OUT_NAME = {"pred": "wrong_pred_analysis", "gold": "gold_analysis"}
SQL_KEY = {"pred": "pred_sql", "gold": "gold_sql"}


def _one(client, row, target):
    sql = row[SQL_KEY[target]]
    struct = sql_struct.analyze(sql)
    llm = analyze_llm(client, sql, common.chat)
    return {
        "idx": row["idx"],
        "question_id": row["question_id"],
        "db_id": row["db_id"],
        "difficulty": row["difficulty"],
        "target": target,
        "sql": sql,
        "parse_error": struct["parse_error"],
        "fingerprint": struct["fingerprint"],
        "productions": struct["productions"],
        "ast_repr": struct["ast_repr"],
        "relational_algebra": llm.get("relational_algebra"),
        "bnf_derivation": llm.get("bnf_derivation"),
        "nl_note": llm.get("nl_note"),
        "llm_error": llm.get("error"),
    }


def run(target, threads=4):
    assert target in ("pred", "gold")
    rows = common.read_jsonl(os.path.join(common.OUT_DIR, "eval_results.jsonl"))
    failed = [r for r in rows if not r["passed"]]
    client = common.get_openai_client()

    out = []
    with ThreadPoolExecutor(max_workers=threads) as ex:
        futs = [ex.submit(_one, client, r, target) for r in failed]
        for i, fut in enumerate(as_completed(futs), 1):
            out.append(fut.result())
            print(f"[{i}/{len(failed)}] {target} idx={out[-1]['idx']}")

    out.sort(key=lambda r: r["idx"])
    base = os.path.join(common.OUT_DIR, OUT_NAME[target])
    common.write_jsonl(base + ".jsonl", out)
    _write_md(base + ".md", target, out)
    print(f"\nWrote {len(out)} {target} analyses -> {base}.jsonl/.md")


def _write_md(path, target, rows):
    title = "Wrong-prediction" if target == "pred" else "Gold"
    with open(path, "w") as f:
        f.write(f"# {title} SQL structural analysis ({len(rows)} failed questions)\n\n")
        for r in rows:
            f.write(f"## idx {r['idx']} (qid {r['question_id']}, {r['db_id']}, {r['difficulty']})\n\n")
            f.write(f"```sql\n{r['sql']}\n```\n\n")
            if r["parse_error"]:
                f.write(f"- **parse_error**: `{r['parse_error']}`\n")
            f.write(f"- **relational algebra**: {r.get('relational_algebra')}\n")
            f.write(f"- **nl**: {r.get('nl_note')}\n\n")
            f.write(f"<details><summary>BNF derivation</summary>\n\n```\n{r.get('bnf_derivation')}\n```\n</details>\n\n")
            f.write("---\n\n")
