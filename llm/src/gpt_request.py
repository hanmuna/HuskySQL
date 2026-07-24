#!/usr/bin/env python3
import argparse
import json
import os
import re
import sqlite3
from typing import Dict

import backoff
import openai
from tqdm import tqdm

"""openai configure"""

openai.debug = True


def new_directory(path):
    if not os.path.exists(path):
        os.makedirs(path)


def get_db_schemas(bench_root: str, db_name: str) -> Dict[str, str]:
    """
    Read an sqlite file, and return the CREATE commands for each of the tables in the database.
    """
    asdf = "database" if bench_root == "spider" else "databases"
    with sqlite3.connect(
        f"file:{bench_root}/{asdf}/{db_name}/{db_name}.sqlite?mode=ro", uri=True
    ) as conn:
        # conn.text_factory = bytes
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        schemas = {}
        for table in tables:
            cursor.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='{}';".format(
                    table[0]
                )
            )
            schemas[table[0]] = cursor.fetchone()[0]

        return schemas


def nice_look_table(column_names: list, values: list):
    rows = []
    # Determine the maximum width of each column
    widths = [
        max(len(str(value[i])) for value in values + [column_names])
        for i in range(len(column_names))
    ]

    # Print the column names
    header = "".join(
        f"{column.rjust(width)} " for column, width in zip(column_names, widths)
    )
    # print(header)
    # Print the values
    for value in values:
        row = "".join(f"{str(v).rjust(width)} " for v, width in zip(value, widths))
        rows.append(row)
    rows = "\n".join(rows)
    final_output = header + "\n" + rows
    return final_output


def generate_schema_prompt(db_path, num_rows=None):
    # extract create ddls
    """
    :param root_place:
    :param db_name:
    :return:
    """
    full_schema_prompt_list = []
    conn = sqlite3.connect(db_path)
    # Create a cursor object
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    schemas = {}
    for table in tables:
        if table == "sqlite_sequence":
            continue
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='{}';".format(
                table[0]
            )
        )
        create_prompt = cursor.fetchone()[0]
        schemas[table[0]] = create_prompt
        if num_rows:
            cur_table = table[0]
            if cur_table in ["order", "by", "group"]:
                cur_table = "`{}`".format(cur_table)

            cursor.execute("SELECT * FROM {} LIMIT {}".format(cur_table, num_rows))
            column_names = [description[0] for description in cursor.description]
            values = cursor.fetchall()
            rows_prompt = nice_look_table(column_names=column_names, values=values)
            verbose_prompt = "/* \n {} example rows: \n SELECT * FROM {} LIMIT {}; \n {} \n */".format(
                num_rows, cur_table, num_rows, rows_prompt
            )
            schemas[table[0]] = "{} \n {}".format(create_prompt, verbose_prompt)

    for k, v in schemas.items():
        full_schema_prompt_list.append(v)

    schema_prompt = "\n\n".join(full_schema_prompt_list)

    return schema_prompt


def generate_comment_prompt(question, knowledge=None):
    pattern_prompt_no_kg = "-- Using valid SQLite, answer the following questions for the tables provided above."
    pattern_prompt_kg = "-- Using valid SQLite and understading External Knowledge, answer the following questions for the tables provided above."
    # question_prompt = "-- {}".format(question) + '\n SELECT '
    question_prompt = "-- {}".format(question)
    knowledge_prompt = "-- External Knowledge: {}".format(knowledge)

    if not knowledge_prompt:
        result_prompt = pattern_prompt_no_kg + "\n" + question_prompt
    else:
        result_prompt = (
            knowledge_prompt + "\n" + pattern_prompt_kg + "\n" + question_prompt
        )

    return result_prompt


def cot_wizard():
    cot = "\nGenerate the SQL after thinking step by step: "

    return cot


def few_shot():
    ini_table = "CREATE TABLE singer\n(\n    singer_id         TEXT not null\n        primary key,\n    nation       TEXT  not null,\n    sname       TEXT null,\n    dname       TEXT null,\n    cname       TEXT null,\n    age    INTEGER         not null,\n    year  INTEGER          not null,\n    birth_year  INTEGER          null,\n    salary  REAL          null,\n    city TEXT          null,\n    phone_number   INTEGER          null,\n--     tax   REAL      null,\n)"
    ini_prompt = "-- External Knowledge: age = year - birth_year;\n-- Using valid SQLite and understading External Knowledge, answer the following questions for the tables provided above.\n-- How many singers in USA who is older than 27?\nThe final SQL is: Let's think step by step."
    ini_cot_result = "1. referring to external knowledge, we need to filter singers 'by year' - 'birth_year' > 27; 2. we should find out the singers of step 1 in which nation = 'US', 3. use COUNT() to count how many singers. Finally the SQL is: SELECT COUNT(*) FROM singer WHERE year - birth_year > 27;</s>"

    one_shot_demo = ini_table + "\n" + ini_prompt + "\n" + ini_cot_result

    return one_shot_demo


def few_shot_no_kg():
    ini_table = "CREATE TABLE singer\n(\n    singer_id         TEXT not null\n        primary key,\n    nation       TEXT  not null,\n    sname       TEXT null,\n    dname       TEXT null,\n    cname       TEXT null,\n    age    INTEGER         not null,\n    year  INTEGER          not null,\n    age  INTEGER          null,\n    salary  REAL          null,\n    city TEXT          null,\n    phone_number   INTEGER          null,\n--     tax   REAL      null,\n)"
    ini_prompt = "-- External Knowledge:\n-- Using valid SQLite and understading External Knowledge, answer the following questions for the tables provided above.\n-- How many singers in USA who is older than 27?\nThe final SQL is: Let's think step by step."
    ini_cot_result = "1. 'older than 27' refers to age > 27 in SQL; 2. we should find out the singers of step 1 in which nation = 'US', 3. use COUNT() to count how many singers. Finally the SQL is: SELECT COUNT(*) FROM singer WHERE age > 27;</s>"

    one_shot_demo = ini_table + "\n" + ini_prompt + "\n" + ini_cot_result

    return one_shot_demo


def generate_combined_prompts_one(db_path, question, knowledge=None):
    schema_prompt = generate_schema_prompt(
        db_path, num_rows=None
    )  # This is the entry to collect values
    comment_prompt = generate_comment_prompt(question, knowledge)

    combined_prompts = (
        schema_prompt + "\n\n" + comment_prompt + cot_wizard() + "\nSELECT "
    )
    # combined_prompts = few_shot() + '\n\n' + schema_prompt + '\n\n' + comment_prompt

    # print(combined_prompts)

    return combined_prompts


def is_quota_error(error_str):
    """Real quota/billing errors, excluding network-layer connection failures
    (e.g. the 'Max retries exceeded' requests raises on DNS resolution failure,
    which is a network issue, not a quota issue)."""
    s = error_str.lower()
    if "max retries exceeded" in s or "nameresolutionerror" in s or "connection" in s:
        return False
    return "quota" in s or "billing" in s or "rate limit" in s


def quota_giveup(e):
    # Handle both old and new SDK error types
    error_str = str(e)
    if not is_quota_error(error_str):
        return False

    if hasattr(openai, "error"):
        return isinstance(e, (openai.error.RateLimitError, openai.error.APIError))
    else:
        # Newer OpenAI SDK
        try:
            from openai import RateLimitError, APIError

            return isinstance(e, (RateLimitError, APIError))
        except ImportError:
            return True


@backoff.on_exception(
    backoff.constant,
    (openai.error.OpenAIError if hasattr(openai, "error") else Exception),
    giveup=quota_giveup,
    raise_on_giveup=True,
    interval=20,
    max_time=300,  # retry network/connection issues for at most 5 min, then give up on this item instead of hanging forever
)
def connect_gpt(engine, prompt, max_tokens, temperature, stop):
    # print(prompt)
    try:
        # Get the API key (works with both old and new SDK)
        api_key = getattr(openai, "api_key", None) or os.getenv("OPENAI_API_KEY")

        # Check whether this model is accessed via the AI/ML API (e.g. gpt-5.1)
        # Per the docs https://docs.aimlapi.com/api-references/text-models-llm/openai/gpt-5-1
        # gpt-5.1 must be accessed via the AI/ML API; its model ID is openai/gpt-5-1
        use_aimlapi = False
        aimlapi_model = None

        if "/" in engine:
            # Full AI/ML API model id (openai/..., Qwen/..., zhipu/glm-4.7, ...): pass through
            use_aimlapi = True
            aimlapi_model = engine
        elif "gpt-5" in engine.lower() or "gpt-6" in engine.lower():
            # gpt-5.x / gpt-6.x etc.: map dots to dashes -> openai/gpt-N-M
            use_aimlapi = True
            aimlapi_model = f"openai/{engine.lower().replace('.', '-')}"

        if use_aimlapi:
            # Use the AI/ML API
            import requests

            try:
                response = requests.post(
                    "https://api.aimlapi.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": aimlapi_model,
                        "messages": [{"role": "user", "content": prompt}],
                        # OpenAI models require max_completion_tokens; other vendors use max_tokens
                        (
                            "max_completion_tokens"
                            if aimlapi_model.startswith("openai/")
                            else "max_tokens"
                        ): max_tokens,
                        "temperature": temperature,
                        "stop": stop if stop else None,
                    },
                    timeout=60,  # 60s timeout
                )
                response.raise_for_status()
                data = response.json()
                result = {
                    "choices": [{"text": data["choices"][0]["message"]["content"]}]
                }
                return result
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, "response") and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get("error", {}).get(
                            "message", error_msg
                        )
                    except:
                        error_msg = e.response.text or error_msg
                raise Exception(f"AI/ML API error: {error_msg}")

        # Decide whether this is a chat model (official OpenAI API)
        if (
            engine == "gpt-3.5-turbo"
            or engine == "gpt-4"
            or "gpt-" in engine
            or "o1" in engine.lower()
        ):
            # Check whether the new OpenAI SDK (v1.0+) is in use
            if hasattr(openai, "OpenAI"):
                # Use the new OpenAI SDK
                client = openai.OpenAI(api_key=api_key)

                # Check whether the model requires max_completion_tokens (e.g. gpt-5.1)
                api_params = {
                    "model": engine,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                }

                # Newer models like gpt-5.1 use max_completion_tokens
                if "gpt-5" in engine.lower() or "gpt-6" in engine.lower():
                    api_params["max_completion_tokens"] = max_tokens
                else:
                    api_params["max_tokens"] = max_tokens

                if stop:
                    api_params["stop"] = stop

                response = client.chat.completions.create(**api_params)
                # Convert the new-format response into the compatible format
                result = {"choices": [{"text": response.choices[0].message.content}]}
            else:
                # Use the legacy ChatCompletion API
                response = openai.ChatCompletion.create(
                    model=engine,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=stop,
                )
                # Convert the chat format into the completion format for compatibility
                result = {
                    "choices": [{"text": response["choices"][0]["message"]["content"]}]
                }
        else:
            # Use the Completion API (for text-davinci-003, code-davinci-002, etc.)
            if hasattr(openai, "OpenAI"):
                # New SDK
                client = openai.OpenAI(api_key=api_key)
                response = client.completions.create(
                    model=engine,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=stop if stop else None,
                )
                result = {
                    "choices": [{"text": choice.text} for choice in response.choices]
                }
            else:
                # Legacy SDK
                result = openai.Completion.create(
                    engine=engine,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=stop,
                )
    except Exception as e:
        error_str = str(e)
        # On a quota error or a missing-model error, execution should stop
        if is_quota_error(error_str):
            print(f"❌ Quota error: {error_str}")
            print("⚠️  Please check:")
            print("   1. Whether the API key has enough quota")
            print(
                "   2. Whether the model name is correct (GPT-5.1 may not exist; use gpt-4, gpt-4-turbo, etc.)"
            )
            print("   3. Whether the API key is allowed to access this model")
            raise  # re-raise so the caller can handle it
        elif "model" in error_str.lower() and (
            "not found" in error_str.lower() or "invalid" in error_str.lower()
        ):
            print(f"❌ Model error: {error_str}")
            print(f"⚠️  Model '{engine}' may not exist or is unavailable")
            print(
                "   Available models include: gpt-3.5-turbo, gpt-4, gpt-4-turbo, gpt-4o, o1-preview, o1-mini, etc."
            )
            raise  # re-raise the exception
        elif (
            "max_tokens" in error_str.lower()
            and "max_completion_tokens" in error_str.lower()
        ):
            # Parameter error: indicate that max_completion_tokens is required
            print(f"⚠️  Parameter error: {error_str}")
            print(f"   Model {engine} requires the max_completion_tokens parameter")
            print(
                "   The code handles this automatically; if it still fails, check the model name"
            )
            raise ValueError(f"Model {engine} parameter error: {error_str}")
        else:
            result = "error:{}".format(e)
            return result


def reconstruct_sql(text):
    """The prompt ends in '...\\nSELECT '. Legacy completion engines
    (code-davinci-002 etc.) only return the continuation after that, so it
    needs 'SELECT' prepended back. Chat engines (gpt-5.x via AIML) instead
    return a full answer that already restates SELECT, often wrapped in a
    ```sql fence - in that case just extract from the first SELECT."""
    cleaned = re.sub(r"```(?:sql)?", "", text, flags=re.IGNORECASE).strip()
    m = re.search(r"\bSELECT\b", cleaned, re.IGNORECASE)
    if m:
        return cleaned[m.start() :]
    return "SELECT" + text


def load_checkpoint(output_path):
    if not output_path or not os.path.exists(output_path):
        return {}
    try:
        return {int(k): v for k, v in json.load(open(output_path)).items()}
    except Exception:
        return {}


def save_checkpoint(responses, output_path):
    """Atomic write: write to a temp file then rename, so an interruption (Ctrl+C / network-retry) never leaves a half-written json."""
    directory_path = os.path.dirname(output_path)
    new_directory(directory_path)
    tmp_path = output_path + ".tmp"
    json.dump(
        {str(k): responses[k] for k in sorted(responses)},
        open(tmp_path, "w"),
        indent=4,
        ensure_ascii=False,
    )
    os.replace(tmp_path, output_path)


def collect_response_from_gpt(
    db_path_list, question_list, api_key, engine, knowledge_list=None, output_path=None
):
    """
    :param db_path: str
    :param question_list: []
    :param output_path: if given, flush to disk incrementally after each question;
        on rerun it first reads this file and skips already-finished questions
        (resume from checkpoint) instead of starting over.
    :return: dict {original_index: sql}
    """
    responses = load_checkpoint(output_path)
    if responses:
        print(
            f"↻ Resumed from existing results: {len(responses)}/{len(question_list)} questions done, skipping"
        )

    pending = [i for i in range(len(question_list)) if i not in responses]
    openai.api_key = api_key
    for i in tqdm(pending):
        question = question_list[i]
        print(
            "--------------------- processing {}th question ---------------------".format(
                i
            )
        )
        print("the question is: {}".format(question))

        if knowledge_list:
            cur_prompt = generate_combined_prompts_one(
                db_path=db_path_list[i], question=question, knowledge=knowledge_list[i]
            )
        else:
            cur_prompt = generate_combined_prompts_one(
                db_path=db_path_list[i], question=question
            )

        try:
            plain_result = connect_gpt(
                engine=engine,
                prompt=cur_prompt,
                max_tokens=256,
                temperature=0,
                stop=["--", "\n\n", ";", "#"],
            )
        except Exception as e:
            # On a quota error or model error, stop execution
            error_str = str(e)
            if is_quota_error(error_str):
                print(f"\n❌ Quota error at question {i + 1}, stopping")
                print(f"   Processed: {i}/{len(question_list)} questions")
                raise
            elif "model" in error_str.lower() and (
                "not found" in error_str.lower() or "invalid" in error_str.lower()
            ):
                print(f"\n❌ Model error at question {i + 1}, stopping")
                raise
            else:
                # Other errors: keep going but record the error
                plain_result = f"error:{error_str}"

        if type(plain_result) == str:
            sql = plain_result
        else:
            sql = reconstruct_sql(plain_result["choices"][0]["text"])

        db_id = db_path_list[i].split("/")[-1].split(".sqlite")[0]
        sql = (
            sql + "\t----- bird -----\t" + db_id
        )  # to avoid unpredicted \t appearing in codex results
        responses[i] = sql

        if output_path:
            save_checkpoint(responses, output_path)

    return responses


def question_package(data_json, knowledge=False):
    question_list = []
    for data in data_json:
        question_list.append(data["question"])

    return question_list


def knowledge_package(data_json, knowledge=False):
    knowledge_list = []
    for data in data_json:
        knowledge_list.append(data["evidence"])

    return knowledge_list


def decouple_question_schema(datasets, db_root_path):
    question_list = []
    db_path_list = []
    knowledge_list = []
    for i, data in enumerate(datasets):
        question_list.append(data["question"])
        cur_db_path = db_root_path + data["db_id"] + "/" + data["db_id"] + ".sqlite"
        db_path_list.append(cur_db_path)
        knowledge_list.append(data["evidence"])

    return question_list, db_path_list, knowledge_list


if __name__ == "__main__":
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument("--eval_path", type=str, default="")
    args_parser.add_argument("--mode", type=str, default="dev")
    args_parser.add_argument("--test_path", type=str, default="")
    args_parser.add_argument("--use_knowledge", type=str, default="False")
    args_parser.add_argument("--db_root_path", type=str, default="")
    # args_parser.add_argument('--db_name', type=str, required=True)
    args_parser.add_argument("--api_key", type=str, required=True)
    args_parser.add_argument(
        "--engine", type=str, required=True, default="code-davinci-002"
    )
    args_parser.add_argument("--data_output_path", type=str)
    args_parser.add_argument("--chain_of_thought", type=str)
    args_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="limit the number of rows to process (for testing)",
    )
    args = args_parser.parse_args()

    eval_data = json.load(open(args.eval_path, "r"))

    # If limit is given, only process the first N rows
    if args.limit and args.limit > 0:
        original_count = len(eval_data)
        eval_data = eval_data[: args.limit]
        print(
            f"⚠️  Test mode: only processing the first {len(eval_data)}/{original_count} rows"
        )

    question_list, db_path_list, knowledge_list = decouple_question_schema(
        datasets=eval_data, db_root_path=args.db_root_path
    )
    assert len(question_list) == len(db_path_list) == len(knowledge_list)

    if args.chain_of_thought == "True":
        output_name = args.data_output_path + "predict_" + args.mode + "_cot.json"
    else:
        output_name = args.data_output_path + "predict_" + args.mode + ".json"

    # Flush incrementally to output_name after each question; if interrupted (Ctrl+C / network
    # issue), rerunning the same command automatically skips questions already written to output_name.
    if args.use_knowledge == "True":
        responses = collect_response_from_gpt(
            db_path_list=db_path_list,
            question_list=question_list,
            api_key=args.api_key,
            engine=args.engine,
            knowledge_list=knowledge_list,
            output_path=output_name,
        )
    else:
        responses = collect_response_from_gpt(
            db_path_list=db_path_list,
            question_list=question_list,
            api_key=args.api_key,
            engine=args.engine,
            knowledge_list=None,
            output_path=output_name,
        )

    print(
        "successfully collect results from {} for {} evaluation; Use knowledge: {}; Use COT: {}".format(
            args.engine, args.mode, args.use_knowledge, args.chain_of_thought
        )
    )
