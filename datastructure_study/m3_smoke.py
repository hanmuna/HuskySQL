#!/usr/bin/env python3
"""M3 smoke test: 5 questions. Build IR prompt -> call model -> parse IR JSON ->
ra_to_sql -> execute -> compare to gold. Reports IR-parse / compile / EX per query.
Spends 5 model calls. Run once."""
import os, sys, json, re, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "llm", "src"))
import openai
from gpt_request import connect_gpt           # reuse the AIML caller
from ra_to_sql import ra_to_sql
from m3_prompt import build_ir_prompt

DBR = os.path.join(HERE, "..", "llm", "data", "dev_databases")
ENGINE = "gpt-5.2"
IDXS = [6, 16, 1, 271, 180]


def load_key():
    env = os.path.join(HERE, "..", "llm", "run", ".env")
    for line in open(env):
        if line.startswith("AIMLAPI_API_KEY"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.getenv("AIMLAPI_API_KEY")


def extract_json(text):
    t = re.sub(r"```(?:json)?", "", text, flags=re.I).strip()
    s = t.find("{")
    if s < 0:
        return None
    depth = 0
    for i in range(s, len(t)):
        if t[i] == "{":
            depth += 1
        elif t[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[s:i + 1])
                except Exception:
                    return None
    return None


def run(db, sql):
    try:
        c = sqlite3.connect(os.path.join(DBR, db, db + ".sqlite")).cursor()
        c.execute(sql)
        return set(c.fetchall()), None
    except Exception as e:
        return None, str(e)[:70]


def main():
    openai.api_key = load_key()
    rows = {r["idx"]: r for r in json.load(open(os.path.join(HERE, "outputs", "results_340.json")))}
    results = []
    for idx in IDXS:
        r = rows[idx]
        dbp = os.path.join(DBR, r["db_id"], r["db_id"] + ".sqlite")
        prompt = build_ir_prompt(dbp, r["question"], r["evidence"])
        raw = connect_gpt(engine=ENGINE, prompt=prompt, max_tokens=800, temperature=0, stop=None)
        text = raw if isinstance(raw, str) else raw["choices"][0]["text"]
        ir = extract_json(text)
        rec = {"idx": idx, "db": r["db_id"], "baseline_ex": r["ex_kg"],
               "ir_ok": ir is not None, "compile_ok": False, "ex": 0, "sql": "", "err": ""}
        if ir is not None:
            try:
                sql = ra_to_sql(ir)
                rec["sql"] = sql
                rec["compile_ok"] = True
                gold_set, _ = run(r["db_id"], r["gold"])
                pred_set, err = run(r["db_id"], sql)
                rec["err"] = err or ""
                rec["ex"] = 1 if (pred_set is not None and pred_set == gold_set) else 0
            except Exception as e:
                rec["err"] = "compile:" + str(e)[:60]
        else:
            rec["err"] = "IR-parse-failed: " + text[:80].replace("\n", " ")
        rec["ir"] = ir
        results.append(rec)
        print(f"idx{idx:<4}[{r['db_id']:<18}] base_ex={r['ex_kg']} ir_ok={rec['ir_ok']} "
              f"compile={rec['compile_ok']} EX={rec['ex']}  {rec['err']}")

    open(os.path.join(HERE, "outputs", "m3_smoke.json"), "w").write(
        json.dumps(results, ensure_ascii=False, indent=1))
    nok = sum(x["ex"] for x in results)
    nbase = sum(x["baseline_ex"] for x in results)
    print(f"\nsmoke: IR-parse {sum(x['ir_ok'] for x in results)}/5, "
          f"compile {sum(x['compile_ok'] for x in results)}/5, "
          f"EX {nok}/5 (baseline on same 5: {nbase}/5)")


if __name__ == "__main__":
    main()
