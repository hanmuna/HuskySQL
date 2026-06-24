#!/bin/bash
# 完整的评估和 HTML 生成流程 - GPT-5.1

# 激活 conda 环境（如果存在）
if [ -f "/opt/homebrew/anaconda3/bin/activate" ]; then
    source /opt/homebrew/anaconda3/bin/activate cv
fi

cd "$(dirname "$0")/.."

db_root_path='./data/dev_databases/'
data_mode='dev'
diff_json_path='./data/dev.json'
predicted_sql_path_kg='./exp_result/gpt51_output_kg/'
predicted_sql_path='./exp_result/gpt51_output/'
ground_truth_path='./data/'
num_cpus=16
meta_time_out=30.0
mode_gt='gt'
mode_predict='gpt51'

echo "=========================================="
echo "🚀 GPT-5.1 完整评估流程"
echo "=========================================="
echo ""

# 步骤1: 清理 SQL 格式
echo "📝 步骤 1/4: 清理 SQL 格式..."
python3 fix_sql_format.py --input ${predicted_sql_path}predict_dev.json --output ${predicted_sql_path}predict_dev.json
python3 fix_sql_format.py --input ${predicted_sql_path_kg}predict_dev.json --output ${predicted_sql_path_kg}predict_dev.json
echo "✅ SQL 格式清理完成"
echo ""

# 步骤2: 运行评估
echo "📊 步骤 2/4: 运行评估（EX 和 VES）..."
echo ""

echo "--- 评估有知识版本 (EX) ---"
# 使用 tee 同时显示进度和保存日志
python3 -u ./src/evaluation.py --db_root_path ${db_root_path} --predicted_sql_path ${predicted_sql_path_kg} --data_mode ${data_mode} \
--ground_truth_path ${ground_truth_path} --num_cpus ${num_cpus} --mode_gt ${mode_gt} --mode_predict ${mode_predict} \
--diff_json_path ${diff_json_path} --meta_time_out ${meta_time_out} 2>&1 | tee ${predicted_sql_path_kg}eval_ex.log

echo ""
echo "--- 评估无知识版本 (EX) ---"
python3 -u ./src/evaluation.py --db_root_path ${db_root_path} --predicted_sql_path ${predicted_sql_path} --data_mode ${data_mode} \
--ground_truth_path ${ground_truth_path} --num_cpus ${num_cpus} --mode_gt ${mode_gt} --mode_predict ${mode_predict} \
--diff_json_path ${diff_json_path} --meta_time_out ${meta_time_out} 2>&1 | tee ${predicted_sql_path}eval_ex.log

echo ""
echo "--- 评估有知识版本 (VES) ---"
echo "⚠️  注意: VES 评估较慢，每条查询需要迭代执行多次..."
python3 -u ./src/evaluation_ves.py --db_root_path ${db_root_path} --predicted_sql_path ${predicted_sql_path_kg} --data_mode ${data_mode} \
--ground_truth_path ${ground_truth_path} --num_cpus ${num_cpus} --mode_gt ${mode_gt} --mode_predict ${mode_predict} \
--diff_json_path ${diff_json_path} --meta_time_out ${meta_time_out} 2>&1 | tee ${predicted_sql_path_kg}eval_ves.log

echo ""
echo "--- 评估无知识版本 (VES) ---"
python3 -u ./src/evaluation_ves.py --db_root_path ${db_root_path} --predicted_sql_path ${predicted_sql_path} --data_mode ${data_mode} \
--ground_truth_path ${ground_truth_path} --num_cpus ${num_cpus} --mode_gt ${mode_gt} --mode_predict ${mode_predict} \
--diff_json_path ${diff_json_path} --meta_time_out ${meta_time_out} 2>&1 | tee ${predicted_sql_path}eval_ves.log

echo "✅ 评估完成"
echo ""

# 步骤3: 提取评估结果并保存为 JSON
echo "📋 步骤 3/4: 提取评估结果..."
python3 << 'PYTHON_SCRIPT'
import json
import re
import os

def extract_eval_results(log_file):
    """从评估日志中提取结果"""
    if not os.path.exists(log_file):
        return None
    
    with open(log_file, 'r') as f:
        content = f.read()
    
    results = {}
    
    # 提取 EX 结果
    if 'ACCURACY' in content:
        ex_match = re.search(r'accuracy\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', content)
        count_match = re.search(r'count\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)', content)
        
        if ex_match and count_match:
            results['ex'] = {
                'simple': {'count': int(count_match.group(1)), 'accuracy': float(ex_match.group(1))},
                'moderate': {'count': int(count_match.group(2)), 'accuracy': float(ex_match.group(2))},
                'challenging': {'count': int(count_match.group(3)), 'accuracy': float(ex_match.group(3))},
                'total': {'count': int(count_match.group(4)), 'accuracy': float(ex_match.group(4))}
            }
    
    # 提取 VES 结果
    if 'VES' in content:
        ves_match = re.search(r'ves\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', content)
        count_match = re.search(r'count\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)', content)
        
        if ves_match and count_match:
            results['ves'] = {
                'simple': {'count': int(count_match.group(1)), 'ves': float(ves_match.group(1))},
                'moderate': {'count': int(count_match.group(2)), 'ves': float(ves_match.group(2))},
                'challenging': {'count': int(count_match.group(3)), 'ves': float(ves_match.group(3))},
                'total': {'count': int(count_match.group(4)), 'ves': float(ves_match.group(4))}
            }
    
    return results if results else None

# 提取结果
results_kg = {}
results_no_kg = {}

# 有知识版本
ex_log_kg = './exp_result/gpt51_output_kg/eval_ex.log'
ves_log_kg = './exp_result/gpt51_output_kg/eval_ves.log'

ex_kg = extract_eval_results(ex_log_kg)
ves_kg = extract_eval_results(ves_log_kg)

if ex_kg:
    results_kg.update(ex_kg)
if ves_kg:
    results_kg.update(ves_kg)

# 无知识版本
ex_log = './exp_result/gpt51_output/eval_ex.log'
ves_log = './exp_result/gpt51_output/eval_ves.log'

ex = extract_eval_results(ex_log)
ves = extract_eval_results(ves_log)

if ex:
    results_no_kg.update(ex)
if ves:
    results_no_kg.update(ves)

# 保存结果
if results_kg:
    with open('./exp_result/gpt51_output_kg/eval_results.json', 'w') as f:
        json.dump(results_kg, f, indent=4)
    print("✅ 有知识版本评估结果已保存: exp_result/gpt51_output_kg/eval_results.json")

if results_no_kg:
    with open('./exp_result/gpt51_output/eval_results.json', 'w') as f:
        json.dump(results_no_kg, f, indent=4)
    print("✅ 无知识版本评估结果已保存: exp_result/gpt51_output/eval_results.json")

PYTHON_SCRIPT

echo ""

# 步骤4: 生成 HTML 文件
echo "🌐 步骤 4/4: 生成 HTML 文件..."
cd ../json_to_html

# 生成有知识版本的 HTML
python3 json_to_html.py \
    --input ../llm/exp_result/gpt51_output_kg/predict_dev.json \
    --output ../llm/exp_result/gpt51_output_kg/predict_dev.html \
    --title "GPT-5.1 Predictions (with Knowledge)" \
    --questions ../llm/data/dev.json \
    --eval-results ../llm/exp_result/gpt51_output_kg/eval_results.json

# 生成无知识版本的 HTML
python3 json_to_html.py \
    --input ../llm/exp_result/gpt51_output/predict_dev.json \
    --output ../llm/exp_result/gpt51_output/predict_dev.html \
    --title "GPT-5.1 Predictions (without Knowledge)" \
    --questions ../llm/data/dev.json \
    --eval-results ../llm/exp_result/gpt51_output/eval_results.json

echo ""
echo "=========================================="
echo "✅ 完成！"
echo "=========================================="
echo ""
echo "📊 评估结果已保存:"
echo "   - exp_result/gpt51_output_kg/eval_results.json"
echo "   - exp_result/gpt51_output/eval_results.json"
echo ""
echo "🌐 HTML 文件已生成:"
echo "   - exp_result/gpt51_output_kg/predict_dev.html"
echo "   - exp_result/gpt51_output/predict_dev.html"
echo ""
echo "💡 在浏览器中打开 HTML 文件查看结果"

