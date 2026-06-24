#!/bin/bash
# 安装依赖脚本

echo "🔧 安装 Python 依赖包..."

# 检查是否在 conda 环境中
if [ -n "$CONDA_DEFAULT_ENV" ]; then
    echo "✅ 检测到 conda 环境: $CONDA_DEFAULT_ENV"
    pip install backoff openai pandas sqlparse tqdm requests
    echo "✅ 安装完成！"
else
    echo "⚠️  未检测到 conda 环境"
    echo ""
    echo "📋 请按以下步骤操作:"
    echo ""
    echo "1. 激活 conda 环境:"
    echo "   source /opt/homebrew/anaconda3/bin/activate cv"
    echo ""
    echo "2. 安装依赖:"
    echo "   pip install backoff openai pandas sqlparse tqdm requests"
    echo ""
    echo "或者直接运行以下命令:"
    echo "   source /opt/homebrew/anaconda3/bin/activate cv && pip install backoff openai pandas sqlparse tqdm requests"
fi

