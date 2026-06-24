#!/usr/bin/env python3
"""
健康检查脚本 - 测试 OpenAI API 和模型可用性
"""

import os
import sys
import json

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️  警告: 未安装 openai 库")
    print("   将跳过实际 API 测试，只进行配置检查")
    print("   要安装: pip install openai 或 pip install --user openai")


def test_api_key(api_key):
    """测试 API key 是否有效"""
    print("=" * 60)
    print("🔍 测试 API Key...")
    print("=" * 60)
    
    try:
        if hasattr(openai, 'OpenAI'):
            # 新版本 SDK
            client = openai.OpenAI(api_key=api_key)
            # 尝试列出模型来验证 API key
            models = client.models.list()
            print("✅ API Key 有效")
            print(f"   可以访问 {len(list(models))} 个模型")
            return True, client
        else:
            # 旧版本 SDK
            openai.api_key = api_key
            models = openai.Model.list()
            print("✅ API Key 有效")
            print(f"   可以访问 {len(models.data)} 个模型")
            return True, None
    except Exception as e:
        error_str = str(e)
        print(f"❌ API Key 无效或出错: {error_str}")
        if "invalid" in error_str.lower() or "authentication" in error_str.lower():
            print("   请检查 API key 是否正确")
        return False, None


def test_model(client, model_name):
    """测试特定模型是否可用"""
    print("\n" + "=" * 60)
    print(f"🔍 测试模型: {model_name}")
    print("=" * 60)
    
    try:
        if client:
            # 新版本 SDK
            # 检查模型是否需要使用 max_completion_tokens（如 gpt-5.1）
            api_params = {
                "model": model_name,
                "messages": [{"role": "user", "content": "Say 'Hello'"}],
                "temperature": 0
            }
            
            # gpt-5.1 等新模型使用 max_completion_tokens
            if 'gpt-5' in model_name.lower() or 'gpt-6' in model_name.lower():
                api_params["max_completion_tokens"] = 10
            else:
                api_params["max_tokens"] = 10
            
            response = client.chat.completions.create(**api_params)
            result = response.choices[0].message.content
        else:
            # 旧版本 SDK
            api_params = {
                "model": model_name,
                "messages": [{"role": "user", "content": "Say 'Hello'"}],
                "temperature": 0
            }
            
            # gpt-5.1 等新模型使用 max_completion_tokens（旧版本 SDK 也支持）
            if 'gpt-5' in model_name.lower() or 'gpt-6' in model_name.lower():
                api_params["max_completion_tokens"] = 10
            else:
                api_params["max_tokens"] = 10
            
            response = openai.ChatCompletion.create(**api_params)
            result = response['choices'][0]['message']['content']
        
        print(f"✅ 模型 {model_name} 可用")
        print(f"   响应: {result}")
        return True
    except Exception as e:
        error_str = str(e)
        print(f"❌ 模型 {model_name} 不可用")
        
        if "not found" in error_str.lower() or "invalid" in error_str.lower():
            print("   原因: 模型不存在或名称错误")
            print("   可用的模型包括:")
            print("     - gpt-3.5-turbo")
            print("     - gpt-4")
            print("     - gpt-4-turbo")
            print("     - gpt-4o")
            print("     - o1-preview")
            print("     - o1-mini")
        elif "quota" in error_str.lower() or "exceeded" in error_str.lower() or "billing" in error_str.lower():
            print("   原因: API 配额已用完或余额不足")
            print("   请检查:")
            print("     1. OpenAI 账户余额")
            print("     2. API 使用配额限制")
            print("     3. 是否需要升级计划")
        elif "rate limit" in error_str.lower():
            print("   原因: 达到速率限制")
            print("   请稍后再试")
        else:
            print(f"   错误详情: {error_str}")
        
        return False


def list_available_models(client):
    """列出可用的模型"""
    print("\n" + "=" * 60)
    print("📋 可用的模型列表")
    print("=" * 60)
    
    try:
        if client:
            models = client.models.list()
            model_names = [m.id for m in models if 'gpt' in m.id.lower() or 'o1' in m.id.lower()]
        else:
            models = openai.Model.list()
            model_names = [m.id for m in models.data if 'gpt' in m.id.lower() or 'o1' in m.id.lower()]
        
        # 过滤并排序
        chat_models = sorted([m for m in model_names if 'gpt' in m.lower() or 'o1' in m.lower()])
        
        print("Chat 模型:")
        for model in chat_models[:10]:  # 只显示前10个
            print(f"   - {model}")
        
        if len(chat_models) > 10:
            print(f"   ... 还有 {len(chat_models) - 10} 个模型")
            
    except Exception as e:
        print(f"⚠️  无法列出模型: {e}")


def check_config():
    """检查配置文件"""
    print("=" * 60)
    print("📋 配置检查")
    print("=" * 60)
    
    script_path = os.path.join(os.path.dirname(__file__), 'run', 'run_gpt.sh')
    if not os.path.exists(script_path):
        print("❌ 未找到 run_gpt.sh 文件")
        return None, None

    with open(script_path, 'r') as f:
        content = f.read()

    import re
    # 获取 API key：环境变量 > run/.env > run/.env.local（.env.local 优先级更高）
    api_key = os.getenv('AIMLAPI_API_KEY')
    for env_file in ('.env', '.env.local'):
        env_path = os.path.join(os.path.dirname(__file__), 'run', env_file)
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                match = re.search(r"AIMLAPI_API_KEY=['\"]?([^'\"\n]+)", f.read())
                if match:
                    api_key = match.group(1)

    if api_key:
        print(f"✅ 找到 API key: {api_key[:20]}...{api_key[-10:]}")
    else:
        print("❌ 未找到 API key，请先 export AIMLAPI_API_KEY=... 或写到 run/.env.local")
    
    # 获取模型
    match = re.search(r"engine3='([^']+)'", content)
    model = match.group(1) if match else None
    
    if model:
        print(f"📌 配置的模型: {model}")
        known_models = ['gpt-3.5-turbo', 'gpt-4', 'gpt-4-turbo', 'gpt-4o', 'o1-preview', 'o1-mini']
        if model in known_models:
            print(f"✅ 模型 {model} 是已知的有效模型")
        else:
            print(f"⚠️  模型 {model} 不在已知模型列表中")
            print(f"   已知模型: {', '.join(known_models)}")
            print(f"   如果 {model} 不存在，API 调用会失败")
    
    # 检查预测文件
    pred_file = os.path.join(os.path.dirname(__file__), 'exp_result', 'gpt52_output', 'predict_dev.json')
    if os.path.exists(pred_file):
        with open(pred_file, 'r') as f:
            data = json.load(f)
            errors = [v for k, v in data.items() if 'error' in str(v)]
            print(f"\n📊 预测文件状态:")
            print(f"   总条目: {len(data)}")
            print(f"   错误条目: {len(errors)}")
            if errors:
                error_msg = errors[0]
                if 'quota' in error_msg.lower():
                    print(f"   ⚠️  主要错误: API 配额问题")
                elif 'model' in error_msg.lower():
                    print(f"   ⚠️  主要错误: 模型问题")
    
    return api_key, model


def main():
    print("🚀 OpenAI API 健康检查")
    print("=" * 60)
    
    # 先检查配置
    api_key, configured_model = check_config()
    
    if not OPENAI_AVAILABLE:
        print("\n" + "=" * 60)
        print("❌ 无法进行 API 测试（需要安装 openai 库）")
        print("=" * 60)
        print("\n💡 安装方法:")
        print("   pip install openai")
        print("   或")
        print("   pip install --user openai")
        return
    
    # 如果配置检查没有找到 API key，尝试其他来源
    if not api_key:
        # 1. 从环境变量获取
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            print("\n📌 从环境变量获取 API key")
        
        # 2. 从脚本参数获取
        if not api_key and len(sys.argv) > 1:
            api_key = sys.argv[1]
            print("\n📌 从命令行参数获取 API key")
        
        # 3. 提示用户输入
        if not api_key:
            print("\n⚠️  未找到 API key")
            api_key = input("请输入你的 OpenAI API key (或按 Enter 跳过): ").strip()
            if not api_key:
                print("❌ 未提供 API key，退出")
                return
    
    # 测试 API key
    is_valid, client = test_api_key(api_key)
    if not is_valid:
        print("\n❌ API key 无效，无法继续测试")
        return
    
    # 列出可用模型
    list_available_models(client)
    
    # 测试常用模型
    test_models = [
        'gpt-3.5-turbo',
        'gpt-4',
        'gpt-4-turbo',
        'gpt-4o',
        'gpt-5.2',  # 用户想测试的模型
    ]
    
    print("\n" + "=" * 60)
    print("🧪 测试模型可用性")
    print("=" * 60)
    
    results = {}
    for model in test_models:
        results[model] = test_model(client, model)
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    
    available_models = [m for m, r in results.items() if r]
    unavailable_models = [m for m, r in results.items() if not r]
    
    if available_models:
        print(f"✅ 可用模型 ({len(available_models)}):")
        for m in available_models:
            print(f"   - {m}")
    
    if unavailable_models:
        print(f"\n❌ 不可用模型 ({len(unavailable_models)}):")
        for m in unavailable_models:
            print(f"   - {m}")
    
    print("\n" + "=" * 60)
    if available_models:
        print("✅ 健康检查完成！至少有一个模型可用")
        print(f"\n💡 建议: 在 run_gpt.sh 中使用以下模型之一:")
        print(f"   engine3='{available_models[0]}'")
    else:
        print("❌ 健康检查失败！没有可用的模型")
        print("   请检查 API key 和账户状态")
    print("=" * 60)


if __name__ == '__main__':
    main()

