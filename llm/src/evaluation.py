import sys
import json
import argparse
import sqlite3
import multiprocessing as mp
from func_timeout import func_timeout, FunctionTimedOut
from tqdm import tqdm
import time

def load_json(dir):
    with open(dir, 'r') as j:
        contents = json.loads(j.read())
    return contents

def result_callback(result):
    exec_result.append(result)
    if hasattr(result_callback, 'pbar'):
        result_callback.pbar.update(1)


def execute_sql(predicted_sql,ground_truth, db_path):
    conn = sqlite3.connect(db_path)
    # Connect to the database
    cursor = conn.cursor()
    cursor.execute(predicted_sql)
    predicted_res = cursor.fetchall()
    cursor.execute(ground_truth)
    ground_truth_res = cursor.fetchall()
    res = 0
    if set(predicted_res) == set(ground_truth_res):
        res = 1
    return res



def execute_model(predicted_sql,ground_truth, db_place, idx, meta_time_out, skip_timeout=120.0):
    """
    执行SQL评估模型
    :param skip_timeout: 如果超过这个时间（秒），则跳过该条目，不参与评估统计
    """
    try:
        # 使用 skip_timeout 作为超时时间，如果超过则跳过
        res = func_timeout(skip_timeout, execute_sql,
                                  args=(predicted_sql, ground_truth, db_place))
        # 正常执行完成（在skip_timeout时间内完成）
        result = {'sql_idx': idx, 'res': res, 'skipped': False}
        return result
    except KeyboardInterrupt:
        sys.exit(0)
    except FunctionTimedOut:
        # 如果超时时间达到 skip_timeout（120秒），标记为跳过
        result = {'sql_idx': idx, 'res': None, 'skipped': True, 'reason': 'timeout_exceeded'}
        return result
    except Exception as e:
        # 其他错误（SQL语法错误等），标记为错误但不跳过
        result = {'sql_idx': idx, 'res': 0, 'skipped': False}
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
        # sql_txt = [sql.split('\t')[0] for sql in sql_txt]
        for idx, sql_str in enumerate(sql_txt):
            sql, db_name = sql_str.strip().split('\t')
            clean_sqls.append(sql)
            db_path_list.append(db_root_path + db_name + '/' + db_name + '.sqlite')

    return clean_sqls, db_path_list

def run_sqls_parallel(sqls, db_places, num_cpus=1, meta_time_out=30.0, skip_timeout=120.0):
    # Initialize progress bar with better visibility
    import sys
    result_callback.pbar = tqdm(
        total=len(sqls), 
        desc="Evaluating SQL", 
        unit="query", 
        ncols=120,
        file=sys.stderr,  # 输出到 stderr，避免被重定向
        mininterval=0.5,  # 至少每0.5秒更新一次
        maxinterval=2.0   # 最多每2秒更新一次
    )
    
    print(f"🚀 开始评估 {len(sqls)} 条 SQL 查询...", file=sys.stderr)
    print(f"⏱️  超时跳过阈值: {skip_timeout} 秒（超过此时间的查询将被跳过）", file=sys.stderr)
    pool = mp.Pool(processes=num_cpus)
    for i,sql_pair in enumerate(sqls):
        predicted_sql, ground_truth = sql_pair
        pool.apply_async(execute_model, args=(predicted_sql, ground_truth, db_places[i], i, meta_time_out, skip_timeout), callback=result_callback)
    pool.close()
    pool.join()
    
    # Close progress bar
    result_callback.pbar.close()
    print(f"✅ 评估完成！共处理 {len(sqls)} 条查询", file=sys.stderr)

def sort_results(list_of_dicts):
  return sorted(list_of_dicts, key=lambda x: x['sql_idx'])

def compute_acc_by_diff(exec_results,diff_json_path, limit=None):
    # 过滤掉被跳过的条目（超时超过2分钟的）
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
        print(f"⚠️  共跳过 {skipped_count} 条超时超过2分钟的查询", file=sys.stderr)
        if skipped_count > 10:
            print(f"   （前10个跳过的索引已显示，共跳过 {skipped_count} 条）", file=sys.stderr)
    
    num_queries = len(valid_results)
    results = [res['res'] for res in valid_results]
    contents = load_json(diff_json_path)
    
    # 如果指定了 limit，只评估前 limit 条数据
    if limit is not None:
        contents = contents[:limit]
    
    # 需要根据实际的结果索引来匹配，因为有些条目被跳过了
    # 创建一个映射：原始索引 -> 结果
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

    # 添加空列表检查
    simple_acc = sum([res['res'] for res in simple_results])/len(simple_results) if simple_results else 0
    moderate_acc = sum([res['res'] for res in moderate_results])/len(moderate_results) if moderate_results else 0
    challenging_acc = sum([res['res'] for res in challenging_results])/len(challenging_results) if challenging_results else 0
    all_acc = sum(results)/num_queries if num_queries > 0 else 0
    count_lists = [len(simple_results), len(moderate_results), len(challenging_results), num_queries]
    return simple_acc * 100, moderate_acc * 100, challenging_acc * 100, all_acc * 100, count_lists



def print_data(score_lists,count_lists):
    levels = ['simple', 'moderate', 'challenging', 'total']
    print("{:20} {:20} {:20} {:20} {:20}".format("", *levels))
    print("{:20} {:<20} {:<20} {:<20} {:<20}".format('count', *count_lists))

    print('======================================    ACCURACY    =====================================')
    print("{:20} {:<20.2f} {:<20.2f} {:<20.2f} {:<20.2f}".format('accuracy', *score_lists))


if __name__ == '__main__':
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument('--predicted_sql_path', type=str, required=True, default='')
    args_parser.add_argument('--ground_truth_path', type=str, required=True, default='')
    args_parser.add_argument('--data_mode', type=str, required=True, default='dev')
    args_parser.add_argument('--db_root_path', type=str, required=True, default='')
    args_parser.add_argument('--num_cpus', type=int, default=1)
    args_parser.add_argument('--meta_time_out', type=float, default=30.0)
    args_parser.add_argument('--skip_timeout', type=float, default=120.0, help='如果评估超过此时间（秒），则跳过该条目，不参与评估统计（默认120秒=2分钟）')
    args_parser.add_argument('--mode_gt', type=str, default='gt')
    args_parser.add_argument('--mode_predict', type=str, default='gpt')
    args_parser.add_argument('--difficulty',type=str,default='simple')
    args_parser.add_argument('--diff_json_path',type=str,default='')
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
    
    query_pairs = list(zip(pred_queries,gt_queries))
    import sys
    print(f'📊 预测查询数量: {len(pred_queries)}, 真实查询数量: {len(gt_queries)}', file=sys.stderr)
    print(f'📊 将评估前 {min_len} 条数据', file=sys.stderr)
    print(f'📊 预测查询数量: {len(pred_queries)}, 真实查询数量: {len(gt_queries)}')
    print(f'📊 将评估前 {min_len} 条数据')
    
    run_sqls_parallel(query_pairs, db_places=db_paths, num_cpus=args.num_cpus, meta_time_out=args.meta_time_out, skip_timeout=args.skip_timeout)
    exec_result = sort_results(exec_result)
    
    print(f'📊 执行结果数量: {len(exec_result)}, 预期数量: {len(pred_queries)}')
    if len(exec_result) != len(pred_queries):
        print(f'⚠️  警告: 执行结果数量 ({len(exec_result)}) 与预测查询数量 ({len(pred_queries)}) 不匹配！')
    
    print('start calculate')
    # 只评估前 min_len 条数据
    simple_acc, moderate_acc, challenging_acc, acc, count_lists = \
        compute_acc_by_diff(exec_result, args.diff_json_path, limit=min_len)
    score_lists = [simple_acc, moderate_acc, challenging_acc, acc]
    print_data(score_lists,count_lists)
    print('===========================================================================================')
    print("Finished evaluation")
    