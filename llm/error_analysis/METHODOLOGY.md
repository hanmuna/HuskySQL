# GPT-5.2 Text-to-SQL 错误结构归因分析

## 中文说明

### 目标
用 GPT-5.2 在 BIRD Mini-Dev (SQLite) 上生成预测 SQL,评估出执行准确率(EX,预期约 55%),
再**定位错误集中在 SQL 的哪个结构成分**(SELECT/聚合、JOIN、WHERE、GROUP BY 等),为后续 prompt / 微调改进提供依据。

数据范围:`data/mini_dev_sqlite.json` 索引 `[0:128] + [346:500]`,共 **282 题**(7 个库),即本人负责的子集。

### 四个步骤
1. **Step 1 — 生成 + 评估**
   - `01_generate.py`:对子集每题用 `llm/src/prompt.py:generate_combined_prompts_one` 构建 prompt,调 GPT-5.2 生成 SQL,
     写 `outputs/predictions.json`(键 = 原始数据集索引)。
   - `02_evaluate.py`:复用 `evaluation/evaluation_utils.py:execute_sql`,逐题执行 pred 与 gold 并做结果集相等比较,
     写 `outputs/eval_results.jsonl`(含 `passed` 标记),打印总体 EX 与按难度分档。
2. **Step 2 — 错误 SQL 结构**:`03_analyze_wrong.py` 对所有 `passed==0` 的**预测 SQL** 做结构分析。
3. **Step 3 — 对应正确 SQL 结构**:`04_analyze_gold.py` 对同一批失败题的**gold SQL** 做同样分析。
4. **Step 4 — 自动对比**:`05_compare_report.py` 逐子句 diff 错误预测 vs gold,统计**哪个成分最常出错**,
   输出 `outputs/error_report.md` + `outputs/error_breakdown.csv`。**全自动,无人工。**

### 为什么用 sqlglot 而不是让 LLM 生成 AST
让 LLM「生成 AST」会幻觉、格式不一致、不可复现。AST 与子句指纹必须**确定性**,
因此用 `sqlglot.parse_one(sql, read="sqlite")` 解析,得到真·AST 和可比较的逐子句指纹(`sql_struct.py`)。
LLM 只保留在它真正有价值、确定性工具做不好的地方:**关系代数翻译**与**自然语言错误归类**(`llm_analyze.py`)。

### 「BNF」维度如何保留
单条 SQL 谈「它的 BNF」概念上不成立(BNF 描述语言而非实例)。本管线把该维度拆成两部分保留:
- **确定性部分**:`sql_struct.productions()` 遍历 AST 节点类型,导出该语句用到的「语法产生式序列」。
- **LLM 部分**:`llm_analyze.py` 让 GPT-5.2 输出一段 BNF 风格的推导片段(`bnf_derivation`),写进 `.md` 供人审阅。

### 子句类别定义(Step 4 对比维度)
`SELECT`(投影表达式,去别名) · `DISTINCT` · `AGGREGATION`(聚合函数集合) · `FROM`(基表集合) ·
`JOIN`(连接类型+ON 条件) · `WHERE`(顶层 AND 拆分后的原子谓词集合) · `GROUP_BY` · `HAVING` ·
`ORDER_BY`(表达式+升降序) · `LIMIT` · `SUBQUERY`(嵌套 SELECT 数) · `SET_OP`(UNION/INTERSECT/EXCEPT) ·
`FUNCTION`(非聚合标量函数) · `CAST`(目标类型)。
另有伪类别:`PARSE_ERROR`(预测无法解析) · `EMPTY_PRED`(没生成 SQL) ·
`SEMANTIC_EQUAL_STRUCT`(结构与 gold 一致但结果错,通常是字面值/语义层面差异)。

### 如何解读 error_report.md
表格按「出现该类别差异的失败题数」降序排列。一道题可同时落入多个类别,故百分比之和会超过 100%。
排名第一的类别 = GPT-5.2 在本子集上**最常做错的 SQL 成分**,优先据此改进。
归一化为启发式:别名命名不同会被记为差异(如 pred 用 `T1` 而 gold 用别名),解读时结合 `.md` 里的样例确认。

### 运行顺序
通过 AIML API(OpenAI 兼容)调 GPT-5.2:`cp error_analysis/.env.example error_analysis/.env` 后填入 AIML key。
```bash
python3 error_analysis/test_compare.py            # 先验证 Step4 逻辑(无需 API)
python3 error_analysis/01_generate.py             # Step1a 生成(--limit N 可冒烟)
python3 error_analysis/02_evaluate.py             # Step1b 评估 → ~55%
python3 error_analysis/03_analyze_wrong.py        # Step2
python3 error_analysis/04_analyze_gold.py         # Step3
python3 error_analysis/05_compare_report.py       # Step4 报告(确定性,可单独重跑)
python3 error_analysis/06_pairwise.py             # Step4b 逐题 BNF/AST/RA 两头并排对照
```

---

## English prompts (for reproducibility / audit)

### Step 1 — SQL generation prompt
Built by `llm/src/prompt.py:generate_combined_prompts_one` = schema dump + question +
external knowledge (evidence) + chain-of-thought + an instruction to return only the
`SELECT ...` SQL with no comments or code fences. Reused unchanged from the existing pipeline.

### Step 2 / Step 3 — per-statement structural analysis prompt (`llm_analyze.py`)
```
You are a database theory expert. Analyze ONE SQL statement.

SQL:
{sql}

Return ONLY a JSON object with exactly these keys:
- "relational_algebra": the query expressed in relational algebra, using operators
  σ (select), π (project), ⋈ (join), × (product), ρ (rename), γ (group/aggregate),
  ∪ ∩ − (set ops), τ (sort). One line of plain text.
- "bnf_derivation": a short BNF-style derivation showing which grammar productions
  this statement uses, e.g. "<query> ::= SELECT <proj> FROM <rel> WHERE <cond>;
  <proj> ::= <agg>(<col>) ...". Keep it under 6 lines.
- "nl_note": one sentence describing what the query computes.

No markdown, no code fences, no extra text. JSON only.
```

### Step 4 — comparison
Fully deterministic Python (`sql_struct.diff_categories`); no LLM prompt involved.
