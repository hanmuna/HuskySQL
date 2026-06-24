#!/usr/bin/env python3
"""
快速测试 gpt-5.2 模型
"""

import sys
import os
import re

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    import openai
    from gpt_request import connect_gpt
    
    print("=" * 60)
    print("🧪 测试 gpt-5.2 模型")
    print("=" * 60)
    
    # API key 从环境变量或 run/.env、run/.env.local 读取（.env.local 优先级更高）
    api_key = os.getenv('AIMLAPI_API_KEY')
    for env_file in ('.env', '.env.local'):
        env_path = os.path.join('run', env_file)
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                match = re.search(r"AIMLAPI_API_KEY=['\"]?([^'\"\n]+)", f.read())
                if match:
                    api_key = match.group(1)

    if api_key:
        print(f"✅ 找到 API key: {api_key[:20]}...{api_key[-10:]}")
    else:
        print("❌ 未找到 API key，请先 export AIMLAPI_API_KEY=... 或写到 run/.env 或 run/.env.local")
        sys.exit(1)
    
    # 设置 API key
    openai.api_key = api_key
    
    # 测试 gpt-5.2
    print("\n测试 gpt-5.2 模型...")
    try:
        result = connect_gpt('gpt-5.2', 'Say hello in one word', 10, 0, None)
        if isinstance(result, dict) and 'choices' in result:
            print(f"✅ 成功！响应: {result['choices'][0]['text']}")
        else:
            print(f"⚠️  返回结果: {result}")
    except Exception as e:
        error_str = str(e)
        print(f"❌ 错误: {error_str}")
        
        if "max_tokens" in error_str.lower() and "max_completion_tokens" in error_str.lower():
            print("\n💡 提示: 代码应该已经修复，但可能还需要:")
            print("   1. 确认 gpt_request.py 中的修复已保存")
            print("   2. 重新运行健康检查脚本")
            print("   3. 检查模型名称是否正确")
        
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✅ 测试完成！gpt-5.2 模型可以正常使用")
    print("=" * 60)
    
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("\n💡 请确保:")
    print("   1. 已安装 openai 库: pip install openai")
    print("   2. 在正确的 Python 环境中运行")
    sys.exit(1)

