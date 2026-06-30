import sys
import json
import argparse
import sqlite3
import multiprocessing as mp
from func_timeout import func_timeout, FunctionTimedOut
from tqdm import tqdm

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



def execute_model(predicted_sql,ground_truth, db_place, idx, meta_time_out):
    try:
        res = func_timeout(meta_time_out, execute_sql,
                                  args=(predicted_sql, ground_truth, db_place))
    except KeyboardInterrupt:
        sys.exit(0)
    except FunctionTimedOut:
        res = 0
    except Exception as e:
        res = 0
    return {'sql_idx': idx, 'res': res}


def package_sqls(sql_path, db_root_path, mode='gpt', data_mode='dev'):
    clean_sqls = []
    db_path_list = []
    # Support gpt, gpt51 and similar modes
    if mode == 'gpt' or 'gpt' in mode.lower():
        sql_data = json.load(open(sql_path + 'predict_' + data_mode + '.json', 'r'))
        # Process keys in numeric order
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

def run_sqls_parallel(sqls, db_places, num_cpus=1, meta_time_out=30.0):
    # Initialize progress bar with better visibility
    import sys
    result_callback.pbar = tqdm(
        total=len(sqls),
        desc="Evaluating SQL",
        unit="query",
        ncols=120,
        file=sys.stderr,  # write to stderr to avoid being redirected
        mininterval=0.5,  # update at least every 0.5s
        maxinterval=2.0   # update at most every 2s
    )

    print(f"🚀 Starting evaluation of {len(sqls)} SQL queries...", file=sys.stderr)
    pool = mp.Pool(processes=num_cpus)
    for i,sql_pair in enumerate(sqls):
        predicted_sql, ground_truth = sql_pair
        pool.apply_async(execute_model, args=(predicted_sql, ground_truth, db_places[i], i, meta_time_out), callback=result_callback)
    pool.close()
    pool.join()
    
    # Close progress bar
    result_callback.pbar.close()
    print(f"✅ Evaluation done! Processed {len(sqls)} queries", file=sys.stderr)

def sort_results(list_of_dicts):
  return sorted(list_of_dicts, key=lambda x: x['sql_idx'])

def compute_acc_by_diff(exec_results,diff_json_path, limit=None):
    num_queries = len(exec_results)
    results = [res['res'] for res in exec_results]
    contents = load_json(diff_json_path)

    # If limit is given, only evaluate the first `limit` rows
    if limit is not None:
        contents = contents[:limit]

    simple_results, moderate_results, challenging_results = [], [], []

    for i,content in enumerate(contents):
        if content['difficulty'] == 'simple':
            simple_results.append(exec_results[i])

        if content['difficulty'] == 'moderate':
            moderate_results.append(exec_results[i])

        if content['difficulty'] == 'challenging':
            challenging_results.append(exec_results[i])

    # Guard against empty lists
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

    # Only evaluate rows that actually have predictions
    min_len = min(len(pred_queries), len(gt_queries))
    pred_queries = pred_queries[:min_len]
    gt_queries = gt_queries[:min_len]
    db_paths = db_paths[:min_len]
    
    query_pairs = list(zip(pred_queries,gt_queries))
    import sys
    print(f'📊 Predicted queries: {len(pred_queries)}, ground-truth queries: {len(gt_queries)}', file=sys.stderr)
    print(f'📊 Will evaluate the first {min_len} rows', file=sys.stderr)
    print(f'📊 Predicted queries: {len(pred_queries)}, ground-truth queries: {len(gt_queries)}')
    print(f'📊 Will evaluate the first {min_len} rows')
    
    run_sqls_parallel(query_pairs, db_places=db_paths, num_cpus=args.num_cpus, meta_time_out=args.meta_time_out)
    exec_result = sort_results(exec_result)
    
    print(f'📊 Execution results: {len(exec_result)}, expected: {len(pred_queries)}')
    if len(exec_result) != len(pred_queries):
        print(f'⚠️  Warning: execution result count ({len(exec_result)}) does not match predicted query count ({len(pred_queries)})!')

    print('start calculate')
    # Only evaluate the first min_len rows
    simple_acc, moderate_acc, challenging_acc, acc, count_lists = \
        compute_acc_by_diff(exec_result, args.diff_json_path, limit=min_len)
    score_lists = [simple_acc, moderate_acc, challenging_acc, acc]
    print_data(score_lists,count_lists)
    print('===========================================================================================')
    print("Finished evaluation")
    