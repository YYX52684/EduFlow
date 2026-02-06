# EduFlow 完整工作流程

在「**设置**」中配置**同一套 API Key + 模型**后，解析、生成卡片、Trainset、优化器、模拟/评估均使用该配置。

---

## 前提

- **输入**：原始 Word 剧本（.docx）或 Markdown（.md）
- **外部测试工具**：能模拟对话并对会话进行评分的工具（如智慧树平台、自建评测脚本等）
- 在 Web 端 **设置 → LLM / API 配置** 中填写 API Key 并选择模型（DeepSeek / 豆包 / OpenAI 兼容），保存

---

## 流程概览

```
原始 Word 文档
      ↓
[1] 解析剧本（上传或按路径）→ 得到 full_content + stages，同时写入 trainset.json
      ↓
[2] 生成教学卡片 → 得到 cards_output_xxx.md
      ↓
[3] 导出卡片到外部测试工具（或使用本系统「学生模拟测试」）
      ↓
[4] 在外部工具中：模拟对话 + 评分，并导出评分结果（如 export_score.json）
      ↓
[5]（可选）运行 DSPy 优化：用 trainset.json + 导出分数迭代优化生成能力
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

### 3. 使用外部测试工具模拟对话并评分

- 将上一步得到的 **cards_output_xxx.md** 导入到外部测试工具（或智慧树平台）。
- 在外部工具中执行：**模拟对话**（学生与 NPC 按卡片设定交互）→ **评分**。
- 将评分结果从外部工具**导出**为本地文件，例如：
  - JSON：`{ "total_score": 85 }` 或自定义字段；
  - 或 Markdown 评测报告。

建议将导出文件放到当前项目下，例如 `output/optimizer/export_score.json`，便于下一步优化器读取。

### 4.（可选）根据评分优化生成能力（DSPy）

- **Web**：在「6. Trainset 与 DSPy 优化」中填写 Trainset 路径（默认 `output/optimizer/trainset.json`），点击「运行优化」。优化器会使用 **trainset** 中的样本生成卡片，并依赖**外部评估导出文件**（如 `output/optimizer/export_score.json`）中的分数作为 metric，迭代改进提示与示例。
- **CLI**：`python run_optimizer.py`（默认读 `output/optimizer/trainset.json`）。需先在外部工具中完成评估并将结果导出到 `output/optimizer/export_score.json`（或通过 `--export` 指定路径）。

多次「生成卡片 → 外部模拟与评分 → 导出分数 → 运行优化」，即可形成**根据评分不断优化生成能力**的闭环，逐步演化出更通用的提示与生成框架。

---

## 小结

| 步骤 | 输入 | 输出 | 说明 |
|------|------|------|------|
| 1 解析 | Word / .md 剧本 | full_content, stages, **trainset.json** | 解析即写 trainset，无需单独构建 |
| 2 生成卡片 | stages + full_content | cards_output_xxx.md | 使用设置中的 API Key + 模型 |
| 3 外部模拟+评分 | cards_output_xxx.md | 对话日志 + 分数 | 在外部工具中完成 |
| 4 导出分数 | 外部工具评分结果 | export_score.json（等） | 供优化器读取 |
| 5 优化（可选） | trainset.json + export 分数 | 优化后的生成程序/提示 | 用评分驱动迭代 |

整个系统使用**同一套 API Key**（在 Web 设置中配置），从解析到生成、优化一致生效。
