"""Step 1a: generate GPT-5.2 predictions over the full BIRD dev set (1534 questions).

Reuses llm/src/gpt_request.py:generate_combined_prompts_one to build prompts.
Output: outputs/predictions.json  -> {orig_idx: "SQL\\t----- bird -----\\tdb_id"}
"""
import os
import sys
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from error_analysis import common
from gpt_request import generate_combined_prompts_one, load_checkpoint, save_checkpoint, reconstruct_sql  # from llm/src


def extract_sql(text):
    if not isinstance(text, str):
        return ""
    return reconstruct_sql(text).strip().rstrip(";").strip()


def worker(client, idx, rec):
    prompt = generate_combined_prompts_one(
        db_path=common.db_path(rec["db_id"]),
        question=rec["question"],
        knowledge=rec.get("evidence"),
    )
    try:
        raw = common.chat(client, prompt, max_completion_tokens=2048)
        sql = extract_sql(raw)
    except Exception as e:
        sql = ""
        print(f"  [{idx}] ERROR {type(e).__name__}: {e}")
    return idx, f"{sql}{common.BIRD_SEP}{rec['db_id']}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="smoke-test: only first N subset items")
    ap.add_argument("--threads", type=int, default=4)
    args = ap.parse_args()

    client = common.get_openai_client()
    subset = common.load_questions()
    if args.limit:
        subset = subset[: args.limit]

    out = os.path.join(common.OUT_DIR, "predictions.json")
    results = load_checkpoint(out)
    if results:
        print(f"↻ Resumed from existing results: {len(results)} questions done, skipping")
    subset = [(idx, rec) for idx, rec in subset if idx not in results]

    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        futs = {ex.submit(worker, client, idx, rec): idx for idx, rec in subset}
        done = 0
        for fut in as_completed(futs):
            idx, val = fut.result()
            results[idx] = val
            save_checkpoint(results, out)
            done += 1
            print(f"[{done}/{len(subset)}] idx={idx} done")

    print(f"\nWrote {len(results)} predictions -> {out}")


if __name__ == "__main__":
    main()
