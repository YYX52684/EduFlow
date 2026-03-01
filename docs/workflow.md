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
[1] 解析剧本（上传或按路径）→ 得到 full_content + stages，同时写入 trainset 库 output/trainset_lib/{原文档名}_trainset.json
      ↓
[2] 生成教学卡片 → 得到 cards_output_xxx.md
      ↓
[3] 使用「学生模拟测试」或闭环仿真运行对话（人设来自工作区 output/persona_lib 或预设）
      ↓
[4] 内部评估器根据 5 大维度自动打分，生成评估报告（evaluation-report-*.md / .json）
      ↓
[5]（可选）运行 DSPy 优化：选择 trainset（默认库中最新）+ 人设 + 优化器；已跑过的 trainset 可命中缓存，不重跑
```

---

## 详细步骤

### 1. 解析剧本（第一步即生成 trainset）

- **Web**：在「1. 剧本上传与解析」中上传或按路径解析。解析完成后会写入当前工作区 **trainset 库**：`output/trainset_lib/{原文档名}_trainset.json`（每份原文档对应一个文件，可多份并存）。
- **CLI**：`python main.py --input "path/to/剧本.docx"` 等，解析后可按需构建 trainset。

结果：得到 **full_content**、**stages**，以及 **trainset 库** 中的一份文件（在「历史生成文件」中可管理，闭环优化时可选或使用默认最新）。

### 2. 生成教学卡片

- **Web**：解析完成后选择生成框架（如 dspy），点击「生成卡片」。卡片会保存到当前项目 output，如 `output/cards_output_YYYYMMDD_HHMMSS.md`。
- **CLI**：`python main.py --input "path/to/剧本.docx"`（不加 `--preview`）会继续生成卡片并保存。

### 3. 闭环仿真与自动评分

- **Web**：在「3. 学生模拟测试 / 闭环验证」中选择卡片文件并运行仿真；系统会：
  - 用指定人设（excellent / average / struggling 等）自动扮演学生，与 NPC 对话；
  - 使用内部评估器 `simulator.evaluator` 按 5 大维度、21 小维度打分；
  - 将评估报告写入 `simulator_output/reports/` 或 `output/optimizer/closed_loop_final_report.md`。

### 4.（可选）根据闭环评分优化生成能力（DSPy）

- **Web**：在「6. 闭环与 DSPy 优化」中选择 **Trainset**（不选则使用 trainset 库中最新一份），点击「运行 DSPy 优化」。优化器使用所选 trainset 生成卡片并在每轮内部执行「仿真 + 评估」。同一 trainset 再次选中时可**命中缓存**，直接返回上次结果不重跑。
- **CLI**：`python run_optimizer.py`（可指定 `--trainset` 或按 course_id 选 trainset 文件）。闭环模式：每轮自动仿真+评估。

**说明**：DSPy 优化器在子进程中运行；Web 端缓存按 trainset 文件内容 hash 存储于 `output/optimizer/dspy_cache/`。

---

## 小结

| 步骤 | 输入 | 输出 | 说明 |
|------|------|------|------|
| 1 解析 | Word / .md 剧本 | full_content, stages, **trainset 库**（每文档一份） | 解析即写 trainset_lib，无需单独构建 |
| 2 生成卡片 | stages + full_content | cards_output_xxx.md | 使用设置中的 API Key + 模型 |
| 3 闭环仿真+评估 | cards_output_xxx.md + 人设 | 会话日志 + 评估报告 | 人设来自工作区 persona_lib 或预设 |
| 4 优化（可选） | 所选 trainset（默认最新）+ 闭环评估 | 优化后的程序/卡片；可缓存 | 同一 trainset 再跑可命中缓存 |

整个系统使用**同一套 API Key**（在 Web 设置中配置），从解析到生成、优化一致生效。

**历史生成文件**：在「工作区文件」页可查看与管理 **输出文件**、**Trainset 库**、**人设库**（output/persona_lib，生成时写入 `{源文件名}_人设/` 下 优秀.yaml、一般.yaml、较差.yaml）。
