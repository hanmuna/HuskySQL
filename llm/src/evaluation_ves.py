import os
import pdb
import sys
import json
import numpy as np
import argparse
import sqlite3
import multiprocessing as mp
from func_timeout import func_timeout, FunctionTimedOut
import time
import math
from tqdm import tqdm

def result_callback(result):
    exec_result.append(result)
    if hasattr(result_callback, 'pbar'):
        result_callback.pbar.update(1)

def clean_abnormal(input):
    input = np.asarray(input)
    processed_list = []
    mean = np.mean(input,axis=0)
    std = np.std(input,axis=0)
    for x in input:
        if x < mean + 3 * std and x > mean - 3 * std:
            processed_list.append(x)
    return processed_list

def execute_sql(sql, db_path):
    # Connect to the database
    conn = sqlite3.connect(db_path)
    # Create a cursor object
    cursor = conn.cursor()
    start_time = time.time()
    cursor.execute(sql)
    exec_time = time.time() - start_time
    return exec_time

def iterated_execute_sql(predicted_sql,ground_truth,db_path,iterate_num):
    conn = sqlite3.connect(db_path)
    diff_list = []
    cursor = conn.cursor()
    cursor.execute(predicted_sql)
    predicted_res = cursor.fetchall()
    cursor.execute(ground_truth)
    ground_truth_res = cursor.fetchall()
    time_ratio = 0
    if set(predicted_res) == set(ground_truth_res):
        for i in range(iterate_num):
            predicted_time = execute_sql(predicted_sql, db_path)
            ground_truth_time = execute_sql(ground_truth, db_path)
            diff_list.append(ground_truth_time / predicted_time)
        processed_diff_list = clean_abnormal(diff_list)
        time_ratio = sum(processed_diff_list) / len(processed_diff_list)
    return time_ratio



def execute_model(predicted_sql,ground_truth, db_place, idx, iterate_num, meta_time_out, skip_timeout=300.0):
    """
    执行SQL评估模型（VES）
    :param skip_timeout: 如果超过这个时间（秒），则跳过该条目，不参与评估统计（默认300秒=5分钟）
    """
    try:
        # 使用 skip_timeout 作为超时时间，如果超过则跳过
        time_ratio = func_timeout(skip_timeout, iterated_execute_sql,
                                  args=(predicted_sql, ground_truth, db_place, iterate_num))
        # 正常执行完成
        result = {'sql_idx': idx, 'time_ratio': time_ratio, 'skipped': False}
        return result
    except KeyboardInterrupt:
        sys.exit(0)
    except FunctionTimedOut:
        # 如果超时时间达到 skip_timeout（300秒），标记为跳过
        result = {'sql_idx': idx, 'time_ratio': None, 'skipped': True, 'reason': 'timeout_exceeded'}
        return result
    except Exception as e:
        # 其他错误（SQL语法错误等），标记为错误但不跳过
        result = {'sql_idx': idx, 'time_ratio': 0, 'skipped': False}
        return result


def package_sqls(sql_path, db_root_path, mode='gpt', data_mode='dev'):
    clean_sqls = []
    db_path_list = []
    # 支持 gpt, gpt51 等模式
    if mode == 'gpt' or 'gpt' in mode.lower():
        sql_data = json.load(open(sql_path + 'predict_' + data_mode + '.json', 'r'))
        # 确保按数字顺序处理键
        sorted_keys = sorted(sql_data.keys(), key=lambda x: int(x) if x.isdigit() else float('inf'))
        for idx in sorted_keys:
            sql_str = sql_data[idx]
            if type(sql_str) == str:
                sql, db_name = sql_str.split('\t----- bird -----\t')
            else:
                sql, db_name = " ", "financial"
            clean_sqls.append(sql)
            db_path_list.append(db_root_path + db_name + '/' + db_name + '.sqlite')

    elif mode == 'gt':
        sqls = open(sql_path + data_mode + '_gold.sql')
        sql_txt = sqls.readlines()
        for idx, sql_str in enumerate(sql_txt):
            sql, db_name = sql_str.strip().split('\t')
            clean_sqls.append(sql)
            db_path_list.append(db_root_path + db_name + '/' + db_name + '.sqlite')

    return clean_sqls, db_path_list

def run_sqls_parallel(sqls, db_places, num_cpus=1, iterate_num=100, meta_time_out=30.0, skip_timeout=300.0):
    # Initialize progress bar with better visibility
    import sys
    result_callback.pbar = tqdm(
        total=len(sqls), 
        desc="Evaluating SQL (VES)", 
        unit="query", 
        ncols=120,
        file=sys.stderr,  # 输出到 stderr，避免被重定向
        mininterval=0.5,  # 至少每0.5秒更新一次
        maxinterval=2.0   # 最多每2秒更新一次
    )
    
    print(f"🚀 开始 VES 评估 {len(sqls)} 条 SQL 查询（每条迭代 {iterate_num} 次）...", file=sys.stderr)
    print(f"⏱️  超时跳过阈值: {skip_timeout} 秒（超过此时间的查询将被跳过）", file=sys.stderr)
    pool = mp.Pool(processes=num_cpus)
    for i,sql_pair in enumerate(sqls):
        predicted_sql, ground_truth = sql_pair
        pool.apply_async(execute_model, args=(predicted_sql, ground_truth, db_places[i], i, iterate_num, meta_time_out, skip_timeout), callback=result_callback)
    pool.close()
    pool.join()
    
    # Close progress bar
    result_callback.pbar.close()
    print(f"✅ VES 评估完成！共处理 {len(sqls)} 条查询", file=sys.stderr)

def sort_results(list_of_dicts):
  return sorted(list_of_dicts, key=lambda x: x['sql_idx'])

def compute_ves(exec_results):
    num_queries = len(exec_results)
    total_ratio = 0
    count = 0

    for i, result in enumerate(exec_results):
        # 跳过被标记为跳过的条目
        if result.get('skipped', False):
            continue
        if result['time_ratio'] != 0 and result['time_ratio'] is not None:
            count += 1
        if result['time_ratio'] is not None:
            total_ratio += math.sqrt(result['time_ratio']) * 100
    ves = (total_ratio/num_queries) if num_queries > 0 else 0
    return ves

def load_json(dir):
    with open(dir, 'r') as j:
        contents = json.loads(j.read())
    return contents

def compute_ves_by_diff(exec_results,diff_json_path, limit=None):
    # 过滤掉被跳过的条目（超时超过5分钟的）
    skipped_count = 0
    skipped_indices = []
    valid_results = []
    
    for res in exec_results:
        if res.get('skipped', False):
            skipped_count += 1
            skipped_indices.append(res['sql_idx'])
            if skipped_count <= 10:  # 只打印前10个跳过的索引
                print(f"⏭️  跳过索引 {res['sql_idx']}: {res.get('reason', 'timeout_exceeded')}", file=sys.stderr)
        else:
            valid_results.append(res)
    
    if skipped_count > 0:
        print(f"⚠️  共跳过 {skipped_count} 条超时超过5分钟的查询", file=sys.stderr)
        if skipped_count > 10:
            print(f"   （前10个跳过的索引已显示，共跳过 {skipped_count} 条）", file=sys.stderr)
    
    num_queries = len(valid_results)
    contents = load_json(diff_json_path)
    
    # 如果指定了 limit，只评估前 limit 条数据
    if limit is not None:
        contents = contents[:limit]
    
    # 需要根据实际的结果索引来匹配，因为有些条目被跳过了
    result_dict = {res['sql_idx']: res for res in valid_results}
    
    simple_results, moderate_results, challenging_results = [], [], []
    
    for i,content in enumerate(contents):
        # 如果这个索引被跳过了，跳过它
        if i in skipped_indices:
            continue
            
        # 检查是否有对应的结果
        if i not in result_dict:
            continue
            
        result = result_dict[i]
            
        if content['difficulty'] == 'simple':
            simple_results.append(result)
        if content['difficulty'] == 'moderate':
            moderate_results.append(result)
        if content['difficulty'] == 'challenging':
            challenging_results.append(result)
    
    simple_ves = compute_ves(simple_results) if simple_results else 0
    moderate_ves = compute_ves(moderate_results) if moderate_results else 0
    challenging_ves = compute_ves(challenging_results) if challenging_results else 0
    all_ves = compute_ves(exec_results) if exec_results else 0
    count_lists = [len(simple_results), len(moderate_results), len(challenging_results), num_queries]
    return simple_ves, moderate_ves, challenging_ves, all_ves, count_lists

def print_data(score_lists,count_lists):
    levels = ['simple', 'moderate', 'challenging', 'total']
    print("{:20} {:20} {:20} {:20} {:20}".format("", *levels))
    print("{:20} {:<20} {:<20} {:<20} {:<20}".format('count', *count_lists))

    print('=========================================    VES   ========================================')
    print("{:20} {:<20.2f} {:<20.2f} {:<20.2f} {:<20.2f}".format('ves', *score_lists))

if __name__ == '__main__':
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument('--predicted_sql_path', type=str, required=True, default='')
    args_parser.add_argument('--ground_truth_path', type=str, required=True, default='')
    args_parser.add_argument('--data_mode', type=str, required=True, default='dev')
    args_parser.add_argument('--db_root_path', type=str, required=True, default='')
    args_parser.add_argument('--num_cpus', type=int, default=1)
    args_parser.add_argument('--meta_time_out', type=float, default=30.0)
    args_parser.add_argument('--mode_gt', type=str, default='gt')
    args_parser.add_argument('--mode_predict', type=str, default='gpt')
    args_parser.add_argument('--diff_json_path',type=str,default='')
    args_parser.add_argument('--skip_timeout', type=float, default=300.0, help='如果评估超过此时间（秒），则跳过该条目，不参与评估统计（默认300秒=5分钟）')
    args = args_parser.parse_args()
    exec_result = []
    
    pred_queries, db_paths = package_sqls(args.predicted_sql_path, args.db_root_path, mode=args.mode_predict,
                                          data_mode=args.data_mode)
    # generate gt sqls:
    gt_queries, db_paths_gt = package_sqls(args.ground_truth_path, args.db_root_path, mode='gt',
                                           data_mode=args.data_mode)

    # 只评估实际有预测结果的数据
    min_len = min(len(pred_queries), len(gt_queries))
    pred_queries = pred_queries[:min_len]
    gt_queries = gt_queries[:min_len]
    db_paths = db_paths[:min_len]
    
    query_pairs = list(zip(pred_queries, gt_queries))
    import sys
    print(f'📊 预测查询数量: {len(pred_queries)}, 真实查询数量: {len(gt_queries)}', file=sys.stderr)
    print(f'📊 将评估前 {min_len} 条数据', file=sys.stderr)
    print(f'📊 预测查询数量: {len(pred_queries)}, 真实查询数量: {len(gt_queries)}')
    print(f'📊 将评估前 {min_len} 条数据')
    
    run_sqls_parallel(query_pairs, db_places=db_paths, num_cpus=args.num_cpus, meta_time_out=args.meta_time_out, skip_timeout=args.skip_timeout)
    exec_result = sort_results(exec_result)
    
    print(f'�� 执行结果数量: {len(exec_result)}, 预期数量: {len(pred_queries)}')
    if len(exec_result) != len(pred_queries):
        print(f'⚠️  警告: 执行结果数量 ({len(exec_result)}) 与预测查询数量 ({len(pred_queries)}) 不匹配！')
    
    print('start calculate')
    # 只评估前 min_len 条数据
    simple_ves, moderate_ves, challenging_ves, ves, count_lists = \
        compute_ves_by_diff(exec_result, args.diff_json_path, limit=min_len)
    score_lists = [simple_ves, moderate_ves, challenging_ves, ves]
    print_data(score_lists, count_lists)
    print('===========================================================================================')
    print("Finished evaluation")


