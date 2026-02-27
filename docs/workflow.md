# EduFlow 完整工作流程

在「**设置**」中配置**同一套 API Key + 模型**后，解析、生成卡片、Trainset、优化器、模拟/评估均使用该配置。

---

## 前提

- **输入**：原始 Word 剧本（.docx）或 Markdown（.md）
- 在 Web 端 **设置 → LLM / API 配置** 中填写 API Key 并选择模型（豆包 / DeepSeek / 其它 OpenAI 兼容），保存

---

## 流程概览

```
原始 Word 文档
      ↓
[1] 解析剧本（上传或按路径）→ 得到 full_content + stages，同时写入 trainset.json
      ↓
[2] 生成教学卡片 → 得到 cards_output_xxx.md
      ↓
[3] 使用「学生模拟测试」或闭环仿真运行对话
      ↓
[4] 内部评估器根据 5 大维度自动打分，生成评估报告（evaluation-report-*.md / .json）
      ↓
[5]（可选）运行 DSPy 优化：用 trainset.json + 闭环评估分数迭代优化生成能力
```

---

## 详细步骤

### 1. 解析剧本（第一步即生成 trainset）

- **Web**：在「1. 剧本、分析结构并生成教学卡片」中，将 Word 拖入或点选上传；或左侧选文件后使用「按路径解析」。解析完成后会自动在当前项目下写入 `output/optimizer/trainset.json`（同源文件会覆盖一条）。
- **CLI**：`python main.py --input "path/to/剧本.docx"`，解析后同样会写入 `output/optimizer/trainset.json`。

结果：得到 **full_content**、**stages**，以及当前项目下的 **trainset.json**（供后续优化使用）。

### 2. 生成教学卡片

- **Web**：解析完成后选择生成框架（如 dspy），点击「生成卡片」。卡片会保存到当前项目 output，如 `output/cards_output_YYYYMMDD_HHMMSS.md`。
- **CLI**：`python main.py --input "path/to/剧本.docx"`（不加 `--preview`）会继续生成卡片并保存。

### 3. 闭环仿真与自动评分

- **Web**：在「3. 学生模拟测试 / 闭环验证」中选择卡片文件并运行仿真；系统会：
  - 用指定人设（excellent / average / struggling 等）自动扮演学生，与 NPC 对话；
  - 使用内部评估器 `simulator.evaluator` 按 5 大维度、21 小维度打分；
  - 将评估报告写入 `simulator_output/reports/` 或 `output/optimizer/closed_loop_final_report.md`。

### 4.（可选）根据闭环评分优化生成能力（DSPy）

- **Web**：在「6. 闭环与 DSPy 优化」中填写 Trainset 路径（默认 `output/optimizer/trainset.json`），点击「运行 DSPy 优化」。优化器会使用 **trainset** 中的样本生成卡片，并在每轮内部自动执行「仿真 + 评估」，将多个人设得分求均值作为 metric。
- **CLI**：`python run_optimizer.py`（默认读 `output/optimizer/trainset.json`）。当前仅支持闭环模式：每轮自动仿真+评估，无需也不再支持外部评估导入分数。

**说明**：DSPy 优化器在子进程中运行，避免与主进程的 dspy.settings 线程冲突。部署时请确保使用该版本，否则若出现「dspy.settings can only be changed by the thread that initially configured it」错误，需检查优化器是否在子进程内执行。

---

## 小结

| 步骤 | 输入 | 输出 | 说明 |
|------|------|------|------|
| 1 解析 | Word / .md 剧本 | full_content, stages, **trainset.json** | 解析即写 trainset，无需单独构建 |
| 2 生成卡片 | stages + full_content | cards_output_xxx.md | 使用设置中的 API Key + 模型 |
| 3 闭环仿真+评估 | cards_output_xxx.md | 会话日志 + 评估报告 | 在系统内完成模拟与评分 |
| 4 优化（可选） | trainset.json + 闭环评估分数 | 优化后的生成程序/提示 | 用内部评分驱动迭代 |

整个系统使用**同一套 API Key**（在 Web 设置中配置），从解析到生成、优化一致生效。

**人设命名**：生成学生人设时，按「原文档名_优秀」「原文档名_一般」「原文档名_较差」命名，便于在「人设」下拉中快速识别刚生成的人设。
