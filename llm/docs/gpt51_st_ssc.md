## GPT-5.1 ST-SSC 方法说明

### 方法定位与命名
- 方法名: Single-turn Structured Self-Correction (ST-SSC)
- 定位: 单轮结构化自纠错, 无训练, 无循环
- 不是:
  - Chain-of-Thought (CoT): 不要求显式思维链
  - Self-Consistency: 不采样多解、不投票
  - Training/Fine-tuning: 无额外训练

### 与 SHARE 的关系(可直接写入)
Inspired by SHARE, we explore whether a single structured self-reflection step—without any additional training—can improve execution accuracy of GPT-5 for text-to-SQL.

差异要点:
- SHARE: 动作轨迹分解 + 两阶段纠错 + 训练
- ST-SSC: 单轮错误类型自诊断 + 单轮修正 + 零训练

### Pipeline(清晰版)
Input: NL Question + Schema
1) GPT-5 生成初始 SQL
2) GPT-5 只判一个错误类型(schema/logic/math/none)
3) GPT-5 只修这一个错误类型(单次修正)
4) 执行 SQL, 评估 EX / VES

约束:
- 不循环
- 只允许一种错误类型
- 只允许一次修正

### Prompt 模板

Step 1: 初始 SQL
```
You are an expert text-to-SQL system.
Given the question and database schema, generate a single SQLite query.

Question:
{question}

Schema:
{schema}

Output ONLY the SQL query.
```

Step 2: 错误类型自诊断(单选)
```
You are reviewing the following SQL query generated for a text-to-SQL task.

Question:
{question}

Schema:
{schema}

SQL:
{sql}

Classify the MOST LIKELY error type of this SQL, if any.
Choose EXACTLY ONE from the following options:

1. schema_error: wrong table, column, or join
2. logic_error: incorrect filtering, join logic, or missing condition
3. math_error: incorrect aggregation, ratio, or arithmetic expression
4. no_error: the SQL is likely correct

Respond ONLY with one label.
```

Step 3: 仅修一种错误
```
You previously classified the SQL error type as: {error_type}

Now revise the SQL query to fix ONLY this type of error.

Rules:
- Do NOT change unrelated parts of the query.
- Do NOT introduce new tables or columns unless required by the error type.
- If the error type is "no_error", output the original SQL unchanged.

Original SQL:
{sql}

Output ONLY the revised SQL.
```

### 为什么不会太简单(可直接写)
该方法的贡献在于强约束的自纠错流程: 强制单一错误类型 + 单次修正, 在保证计算成本几乎不增加的前提下, 提供可复现的性能增益与可解释性改进, 作为轻量且稳定的强基线。

### 最小实验与消融建议
对照组:
- Baseline: 原始 SQL 直接执行
- Free-form 修正: 允许模型自由改写
- ST-SSC: 结构化单轮修正

消融:
- 去掉错误类型分类(直接改)
- 允许多错误类型(观察是否退化)

分析建议:
- 按错误类型统计修正成功/失败比例
- 统计 no_error 的保留率与误改率

### 关键参考
- SHARE: An SLM-based Hierarchical Action CorREction Assistant for Text-to-SQL (ACL 2025), arXiv:2506.00391
  - https://arxiv.org/abs/2506.00391
- SelECT-SQL: Self-correcting ensemble Chain-of-Thought for Text-to-SQL, arXiv:2409.10007
  - https://arxiv.org/abs/2409.10007
- Self-Consistency Improves Chain of Thought Reasoning in Language Models, arXiv:2203.11171
  - https://arxiv.org/abs/2203.11171
