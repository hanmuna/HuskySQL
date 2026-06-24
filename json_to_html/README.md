# JSON to HTML 转换工具

这个工具可以将BIRD预测结果的JSON文件转换为美观的HTML表格，方便在浏览器中查看。

## 文件说明

- `json_to_html.py` - Python转换脚本
- `run_json_to_html.sh` - Shell运行脚本
- `README.md` - 本说明文件

## 使用方法

### 方法1: 使用Shell脚本（推荐）

```bash
cd json_to_html

# 使用默认文件（../llm/exp_result/gpt52_output_kg/predict_dev.json）
./run_json_to_html.sh

# 指定输入文件
./run_json_to_html.sh ../llm/exp_result/gpt52_output/predict_dev.json

# 指定输入和输出文件
./run_json_to_html.sh input.json output.html
```

### 方法2: 直接使用Python脚本

```bash
cd json_to_html

# 基本用法
python3 json_to_html.py --input ../llm/exp_result/gpt52_output_kg/predict_dev.json

# 指定输出文件
python3 json_to_html.py -i input.json -o output.html

# 自定义标题
python3 json_to_html.py -i input.json -o output.html -t "我的SQL预测结果"
```

## 功能特点

- ✅ 美观的HTML表格展示
- ✅ SQL语法高亮（关键字高亮）
- ✅ 统计信息（总记录数、数据库数量）
- ✅ 响应式设计，支持移动端
- ✅ 自动分离SQL和数据库ID
- ✅ 悬停效果，提升用户体验

## 输出示例

生成的HTML文件包含：
- 页面标题和统计信息
- 包含索引、SQL查询、数据库ID的表格
- 美观的样式和布局

## 依赖

- Python 3.6+
- 标准库（json, argparse, html, os, re）

无需安装额外依赖！

