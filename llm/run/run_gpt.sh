#!/bin/bash
# 激活 conda 环境（如果存在）
if [ -f "/opt/homebrew/anaconda3/bin/activate" ]; then
    source /opt/homebrew/anaconda3/bin/activate cv
fi

eval_path='./data/dev.json'
dev_path='./output/'
db_root_path='./data/dev_databases/'
use_knowledge='True'
not_use_knowledge='False'
mode='dev' # choose dev or dev
cot='True'
no_cot='Fales'

if [ -f "$(dirname "$0")/.env" ]; then
    source "$(dirname "$0")/.env"
fi
if [ -f "$(dirname "$0")/.env.local" ]; then
    source "$(dirname "$0")/.env.local"
fi
if [ -z "$AIMLAPI_API_KEY" ]; then
    echo "❌ 请先 export AIMLAPI_API_KEY=你的key，或写到 llm/run/.env 或 llm/run/.env.local"
    exit 1
fi
YOUR_API_KEY="$AIMLAPI_API_KEY"

engine1='code-davinci-002'
engine2='text-davinci-003'
engine3='gpt-5.2'

# data_output_path='./exp_result/gpt_output/'
# data_kg_output_path='./exp_result/gpt_output_kg/'

# 使用新的输出目录避免覆盖旧结果
data_output_path='./exp_result/gpt52_output/'
data_kg_output_path='./exp_result/gpt52_output_kg/'


# 设置测试数据量（设置为 0 或注释掉则处理全部数据）
TEST_LIMIT=0  # 测试前50条，设置为 0 处理全部数据

if [ "$TEST_LIMIT" -gt 0 ]; then
    echo "⚠️  测试模式: 只处理前 ${TEST_LIMIT} 条数据"
    LIMIT_ARG="--limit ${TEST_LIMIT}"
else
    LIMIT_ARG=""
fi

echo 'generate GPT-5.2 batch with knowledge'
python3 -u ./src/gpt_request.py --db_root_path ${db_root_path} --api_key ${YOUR_API_KEY} --mode ${mode} \
--engine ${engine3} --eval_path ${eval_path} --data_output_path ${data_kg_output_path} --use_knowledge ${use_knowledge} \
--chain_of_thought ${no_cot} ${LIMIT_ARG}

echo 'generate GPT-5.2 batch without knowledge'
python3 -u ./src/gpt_request.py --db_root_path ${db_root_path} --api_key ${YOUR_API_KEY} --mode ${mode} \
--engine ${engine3} --eval_path ${eval_path} --data_output_path ${data_output_path} --use_knowledge ${not_use_knowledge} \
--chain_of_thought ${no_cot} ${LIMIT_ARG}
