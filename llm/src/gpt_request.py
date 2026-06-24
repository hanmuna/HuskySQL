#!/usr/bin/env python3
import argparse
import fnmatch
import json
import os
import pdb
import pickle
import re
import sqlite3
from typing import Dict, List, Tuple

import backoff
import openai
import pandas as pd
import sqlparse
import requests
from tqdm import tqdm
'''openai configure'''

openai.debug=True


def new_directory(path):  
    if not os.path.exists(path):  
        os.makedirs(path)  


def get_db_schemas(bench_root: str, db_name: str) -> Dict[str, str]:
    """
    Read an sqlite file, and return the CREATE commands for each of the tables in the database.
    """
    asdf = 'database' if bench_root == 'spider' else 'databases'
    with sqlite3.connect(f'file:{bench_root}/{asdf}/{db_name}/{db_name}.sqlite?mode=ro', uri=True) as conn:
        # conn.text_factory = bytes
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        schemas = {}
        for table in tables:
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='{}';".format(table[0]))
            schemas[table[0]] = cursor.fetchone()[0]

        return schemas

def nice_look_table(column_names: list, values: list):
    rows = []
    # Determine the maximum width of each column
    widths = [max(len(str(value[i])) for value in values + [column_names]) for i in range(len(column_names))]

    # Print the column names
    header = ''.join(f'{column.rjust(width)} ' for column, width in zip(column_names, widths))
    # print(header)
    # Print the values
    for value in values:
        row = ''.join(f'{str(v).rjust(width)} ' for v, width in zip(value, widths))
        rows.append(row)
    rows = "\n".join(rows)
    final_output = header + '\n' + rows
    return final_output

def generate_schema_prompt(db_path, num_rows=None):
    # extract create ddls
    '''
    :param root_place:
    :param db_name:
    :return:
    '''
    full_schema_prompt_list = []
    conn = sqlite3.connect(db_path)
    # Create a cursor object
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    schemas = {}
    for table in tables:
        if table == 'sqlite_sequence':
            continue
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='{}';".format(table[0]))
        create_prompt = cursor.fetchone()[0]
        schemas[table[0]] = create_prompt
        if num_rows:
            cur_table = table[0]
            if cur_table in ['order', 'by', 'group']:
                cur_table = "`{}`".format(cur_table)

            cursor.execute("SELECT * FROM {} LIMIT {}".format(cur_table, num_rows))
            column_names = [description[0] for description in cursor.description]
            values = cursor.fetchall()
            rows_prompt = nice_look_table(column_names=column_names, values=values)
            verbose_prompt = "/* \n {} example rows: \n SELECT * FROM {} LIMIT {}; \n {} \n */".format(num_rows, cur_table, num_rows, rows_prompt)
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
        result_prompt = pattern_prompt_no_kg + '\n' + question_prompt
    else:
        result_prompt = knowledge_prompt + '\n' + pattern_prompt_kg + '\n' + question_prompt

    return result_prompt

def cot_wizard():
    cot = "\nGenerate the SQL after thinking step by step: "
    
    return cot

def few_shot():
    ini_table = "CREATE TABLE singer\n(\n    singer_id         TEXT not null\n        primary key,\n    nation       TEXT  not null,\n    sname       TEXT null,\n    dname       TEXT null,\n    cname       TEXT null,\n    age    INTEGER         not null,\n    year  INTEGER          not null,\n    birth_year  INTEGER          null,\n    salary  REAL          null,\n    city TEXT          null,\n    phone_number   INTEGER          null,\n--     tax   REAL      null,\n)"
    ini_prompt = "-- External Knowledge: age = year - birth_year;\n-- Using valid SQLite and understading External Knowledge, answer the following questions for the tables provided above.\n-- How many singers in USA who is older than 27?\nThe final SQL is: Let's think step by step."
    ini_cot_result = "1. referring to external knowledge, we need to filter singers 'by year' - 'birth_year' > 27; 2. we should find out the singers of step 1 in which nation = 'US', 3. use COUNT() to count how many singers. Finally the SQL is: SELECT COUNT(*) FROM singer WHERE year - birth_year > 27;</s>"
    
    one_shot_demo = ini_table + '\n' + ini_prompt + '\n' + ini_cot_result
    
    return one_shot_demo

def few_shot_no_kg():
    ini_table = "CREATE TABLE singer\n(\n    singer_id         TEXT not null\n        primary key,\n    nation       TEXT  not null,\n    sname       TEXT null,\n    dname       TEXT null,\n    cname       TEXT null,\n    age    INTEGER         not null,\n    year  INTEGER          not null,\n    age  INTEGER          null,\n    salary  REAL          null,\n    city TEXT          null,\n    phone_number   INTEGER          null,\n--     tax   REAL      null,\n)"
    ini_prompt = "-- External Knowledge:\n-- Using valid SQLite and understading External Knowledge, answer the following questions for the tables provided above.\n-- How many singers in USA who is older than 27?\nThe final SQL is: Let's think step by step."
    ini_cot_result = "1. 'older than 27' refers to age > 27 in SQL; 2. we should find out the singers of step 1 in which nation = 'US', 3. use COUNT() to count how many singers. Finally the SQL is: SELECT COUNT(*) FROM singer WHERE age > 27;</s>"
    
    one_shot_demo = ini_table + '\n' + ini_prompt + '\n' + ini_cot_result
    
    return one_shot_demo



def generate_combined_prompts_one(db_path, question, knowledge=None):
    schema_prompt = generate_schema_prompt(db_path, num_rows=None) # This is the entry to collect values
    comment_prompt = generate_comment_prompt(question, knowledge)

    combined_prompts = schema_prompt + '\n\n' + comment_prompt + cot_wizard() + '\nSELECT '
    # combined_prompts = few_shot() + '\n\n' + schema_prompt + '\n\n' + comment_prompt

    # print(combined_prompts)

    return combined_prompts

def quota_giveup(e):
    # 兼容新旧版本的错误类型
    error_str = str(e).lower()
    # 检查是否是配额相关错误
    is_quota_error = "quota" in error_str or "exceeded" in error_str or "billing" in error_str
    
    if hasattr(openai, 'error'):
        return isinstance(e, (openai.error.RateLimitError, openai.error.APIError)) and is_quota_error
    else:
        # 新版本 OpenAI SDK
        try:
            from openai import RateLimitError, APIError
            return isinstance(e, (RateLimitError, APIError)) and is_quota_error
        except ImportError:
            return is_quota_error

@backoff.on_exception(
    backoff.constant,
    (openai.error.OpenAIError if hasattr(openai, 'error') else Exception),
    giveup=quota_giveup,
    raise_on_giveup=True,
    interval=20
)
def connect_gpt(engine, prompt, max_tokens, temperature, stop):
    # print(prompt)
    try:
        # 获取 API key（兼容新旧版本）
        api_key = getattr(openai, 'api_key', None) or os.getenv('OPENAI_API_KEY')
        
        # 检查是否是通过 AI/ML API 访问的模型（如 gpt-5.1）
        # 根据文档 https://docs.aimlapi.com/api-references/text-models-llm/openai/gpt-5-1
        # gpt-5.1 需要通过 AI/ML API 访问，模型 ID 是 openai/gpt-5-1
        use_aimlapi = False
        aimlapi_model = None
        
        if 'gpt-5' in engine.lower() or 'gpt-6' in engine.lower():
            # 检查是否是完整的 AI/ML API 模型 ID
            if engine.startswith('openai/'):
                use_aimlapi = True
                aimlapi_model = engine
            else:
                # gpt-5.x / gpt-6.x 等，点号转横杠映射到 openai/gpt-N-M
                use_aimlapi = True
                aimlapi_model = f"openai/{engine.lower().replace('.', '-')}"
        
        if use_aimlapi:
            # 使用 AI/ML API
            import requests
            try:
                response = requests.post(
                    "https://api.aimlapi.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": aimlapi_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_completion_tokens": max_tokens,
                        "temperature": temperature,
                        "stop": stop if stop else None
                    },
                    timeout=60  # 60秒超时
                )
                response.raise_for_status()
                data = response.json()
                result = {'choices': [{'text': data['choices'][0]['message']['content']}]}
                return result
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('error', {}).get('message', error_msg)
                    except:
                        error_msg = e.response.text or error_msg
                raise Exception(f"AI/ML API 错误: {error_msg}")
        
        # 判断是否为chat模型（OpenAI 官方 API）
        if engine == 'gpt-3.5-turbo' or engine == 'gpt-4' or 'gpt-' in engine or 'o1' in engine.lower():
            # 检查是否使用新版本 OpenAI SDK (v1.0+)
            if hasattr(openai, 'OpenAI'):
                # 使用新版本 OpenAI SDK
                client = openai.OpenAI(api_key=api_key)
                
                # 检查模型是否需要使用 max_completion_tokens（如 gpt-5.1）
                api_params = {
                    "model": engine,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                }
                
                # gpt-5.1 等新模型使用 max_completion_tokens
                if 'gpt-5' in engine.lower() or 'gpt-6' in engine.lower():
                    api_params["max_completion_tokens"] = max_tokens
                else:
                    api_params["max_tokens"] = max_tokens
                
                if stop:
                    api_params["stop"] = stop
                
                response = client.chat.completions.create(**api_params)
                # 将新版本格式转换为兼容格式
                result = {'choices': [{'text': response.choices[0].message.content}]}
            else:
                # 使用旧版本 ChatCompletion API
                response = openai.ChatCompletion.create(
                    model=engine,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=stop
                )
                # 将chat格式转换为completion格式以保持兼容性
                result = {'choices': [{'text': response['choices'][0]['message']['content']}]}
        else:
            # 使用Completion API（适用于text-davinci-003, code-davinci-002等）
            if hasattr(openai, 'OpenAI'):
                # 新版本 SDK
                client = openai.OpenAI(api_key=api_key)
                response = client.completions.create(
                    model=engine,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=stop if stop else None
                )
                result = {'choices': [{'text': choice.text} for choice in response.choices]}
            else:
                # 旧版本 SDK
                result = openai.Completion.create(
                    engine=engine, 
                    prompt=prompt, 
                    max_tokens=max_tokens, 
                    temperature=temperature, 
                    stop=stop
                )
    except Exception as e:
        error_str = str(e)
        # 如果是配额错误或模型不存在错误，应该停止执行
        if "quota" in error_str.lower() or "exceeded" in error_str.lower() or "billing" in error_str.lower():
            print(f"❌ 配额错误: {error_str}")
            print("⚠️  请检查:")
            print("   1. API key 是否有足够的配额")
            print("   2. 模型名称是否正确（GPT-5.1 可能不存在，请使用 gpt-4, gpt-4-turbo 等）")
            print("   3. API key 是否有权限访问该模型")
            raise  # 重新抛出异常，让调用者处理
        elif "model" in error_str.lower() and ("not found" in error_str.lower() or "invalid" in error_str.lower()):
            print(f"❌ 模型错误: {error_str}")
            print(f"⚠️  模型 '{engine}' 可能不存在或不可用")
            print("   可用的模型包括: gpt-3.5-turbo, gpt-4, gpt-4-turbo, gpt-4o, o1-preview, o1-mini 等")
            raise  # 重新抛出异常
        elif "max_tokens" in error_str.lower() and "max_completion_tokens" in error_str.lower():
            # 如果是参数错误，提示需要使用 max_completion_tokens
            print(f"⚠️  参数错误: {error_str}")
            print(f"   模型 {engine} 需要使用 max_completion_tokens 参数")
            print("   代码已自动处理，如果仍然失败，请检查模型名称")
            raise ValueError(f"模型 {engine} 参数错误: {error_str}")
        else:
            result = 'error:{}'.format(e)
            return result
def collect_response_from_gpt(db_path_list, question_list, api_key, engine, knowledge_list=None):
    '''
    :param db_path: str
    :param question_list: []
    :return: dict of responses collected from openai
    '''
    responses_dict = {}
    response_list = []
    openai.api_key = api_key
    for i, question in tqdm(enumerate(question_list)):
        print('--------------------- processing {}th question ---------------------'.format(i))
        print('the question is: {}'.format(question))
        
        if knowledge_list:
            cur_prompt = generate_combined_prompts_one(db_path=db_path_list[i], question=question, knowledge=knowledge_list[i])
        else:
            cur_prompt = generate_combined_prompts_one(db_path=db_path_list[i], question=question)
        
        try:
            plain_result = connect_gpt(engine=engine, prompt=cur_prompt, max_tokens=128, temperature=0, stop=['--', '\n\n', ';', '#'])
        except Exception as e:
            # 如果是配额错误或模型错误，停止执行
            error_str = str(e)
            if "quota" in error_str.lower() or "exceeded" in error_str.lower() or "billing" in error_str.lower():
                print(f"\n❌ 在第 {i+1} 个问题时遇到配额错误，停止执行")
                print(f"   已处理: {i}/{len(question_list)} 个问题")
                raise
            elif "model" in error_str.lower() and ("not found" in error_str.lower() or "invalid" in error_str.lower()):
                print(f"\n❌ 在第 {i+1} 个问题时遇到模型错误，停止执行")
                raise
            else:
                # 其他错误，继续执行但记录错误
                plain_result = f'error:{error_str}'
        
        # pdb.set_trace()
        # plain_result = connect_gpt(engine=engine, prompt=cur_prompt, max_tokens=256, temperature=0, stop=['</s>'])
        # determine wheter the sql is wrong
        
        if type(plain_result) == str:
            sql = plain_result
        else:
            sql = 'SELECT' + plain_result['choices'][0]['text']
        
        # responses_dict[i] = sql
        db_id = db_path_list[i].split('/')[-1].split('.sqlite')[0]
        sql = sql + '\t----- bird -----\t' + db_id # to avoid unpredicted \t appearing in codex results
        response_list.append(sql)

    return response_list

def question_package(data_json, knowledge=False):
    question_list = []
    for data in data_json:
        question_list.append(data['question'])

    return question_list

def knowledge_package(data_json, knowledge=False):
    knowledge_list = []
    for data in data_json:
        knowledge_list.append(data['evidence'])

    return knowledge_list

def decouple_question_schema(datasets, db_root_path):
    question_list = []
    db_path_list = []
    knowledge_list = []
    for i, data in enumerate(datasets):
        question_list.append(data['question'])
        cur_db_path = db_root_path + data['db_id'] + '/' + data['db_id'] +'.sqlite'
        db_path_list.append(cur_db_path)
        knowledge_list.append(data['evidence'])
    
    return question_list, db_path_list, knowledge_list

def generate_sql_file(sql_lst, output_path=None):
    result = {}
    for i, sql in enumerate(sql_lst):
        result[i] = sql
    
    if output_path:
        directory_path = os.path.dirname(output_path)  
        new_directory(directory_path)
        json.dump(result, open(output_path, 'w'), indent=4)
    
    return result    

if __name__ == '__main__':
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument('--eval_path', type=str, default='')
    args_parser.add_argument('--mode', type=str, default='dev')
    args_parser.add_argument('--test_path', type=str, default='')
    args_parser.add_argument('--use_knowledge', type=str, default='False')
    args_parser.add_argument('--db_root_path', type=str, default='')
    # args_parser.add_argument('--db_name', type=str, required=True)
    args_parser.add_argument('--api_key', type=str, required=True)
    args_parser.add_argument('--engine', type=str, required=True, default='code-davinci-002')
    args_parser.add_argument('--data_output_path', type=str)
    args_parser.add_argument('--chain_of_thought', type=str)
    args_parser.add_argument('--limit', type=int, default=None, help='限制处理的数据条数（用于测试）')
    args = args_parser.parse_args()
    
    eval_data = json.load(open(args.eval_path, 'r'))
    
    # 如果指定了 limit，只处理前 N 条数据
    if args.limit and args.limit > 0:
        original_count = len(eval_data)
        eval_data = eval_data[:args.limit]
        print(f"⚠️  测试模式: 只处理前 {len(eval_data)}/{original_count} 条数据")
    
    question_list, db_path_list, knowledge_list = decouple_question_schema(datasets=eval_data, db_root_path=args.db_root_path)
    assert len(question_list) == len(db_path_list) == len(knowledge_list)
    
    if args.use_knowledge == 'True':
        responses = collect_response_from_gpt(db_path_list=db_path_list, question_list=question_list, api_key=args.api_key, engine=args.engine, knowledge_list=knowledge_list)
    else:
        responses = collect_response_from_gpt(db_path_list=db_path_list, question_list=question_list, api_key=args.api_key, engine=args.engine, knowledge_list=None)
    
    if args.chain_of_thought == 'True':
        output_name = args.data_output_path + 'predict_' + args.mode + '_cot.json'
    else:
        output_name = args.data_output_path + 'predict_' + args.mode + '.json'
    # pdb.set_trace()
    generate_sql_file(sql_lst=responses, output_path=output_name)

    print('successfully collect results from {} for {} evaluation; Use knowledge: {}; Use COT: {}'.format(args.engine, args.mode, args.use_knowledge, args.chain_of_thought))
