# EduFlow 架构与数据流

本文档描述 EduFlow 的核心架构、模块职责与关键数据流，便于新人上手与后续扩展。

## 1. 系统概览

EduFlow 将「教学剧本」转为「智慧树平台沉浸式卡片」，并支持本地仿真、多维度评估与闭环优化。

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│  剧本文件    │ ──► │ 解析 + 分幕   │ ──► │ 卡片生成     │ ──► │ 平台注入 /   │
│ md/docx/pdf │     │ parsers +    │     │ generators   │     │ 本地仿真评估 │
└─────────────┘     │ splitter     │     │ (A/B 卡)     │     └──────────────┘
                    └──────────────┘     └─────────────┘
```

- **入口**：CLI（`main.py`）、Web（`run_web.py` → FastAPI）、API 路由。
- **工作区**：按 `X-Workspace-Id`（或 URL `/w/<id>`）隔离，每工作区独立 `workspaces/<id>/input`、`output`、配置。

## 2. 模块职责

| 模块 | 职责 |
|------|------|
| **parsers/** | 多格式解析（md/docx/doc/pdf）、任务元数据提取（任务名、描述、评价项）。 |
| **generators/content_splitter** | 调用 LLM 将剧本分析为多「阶段」(stages)，含缓存（内存+可选磁盘）。 |
| **generators/frameworks/** | 卡片生成框架：default（模板+LLM）、dspy（DSPy 结构化）。实现 `BaseCardGenerator.generate_all_cards(stages, content)`。 |
| **generators/evaluation_section** | 根据阶段/文档评价项生成「评价项」Markdown 章节。 |
| **simulator/** | 卡片加载（LocalCardLoader）、LLM NPC、学生人设、SessionRunner 跑对话、Evaluator 多维度评估。 |
| **api_platform/** | 智慧树 API 客户端、卡片注入器（解析 Markdown → A 类节点、B 类连线、评价项）。 |
| **api/** | FastAPI 应用、路由、工作区解析、统一异常与 request_id 中间件。 |

## 3. 关键数据流

### 3.1 剧本 → 卡片（生成流水线）

1. **输入**：用户上传或指定剧本文件（md/docx/doc/pdf）。
2. **解析**：`parse_*` / `parse_*_with_structure` → 全文 `content`，docx/doc 额外得到 `doc_structure`（标题层级与内容块）。
3. **分幕**：`ContentSplitter.analyze(content)` → `stages`（每项含 id、title、role、task、key_points、interaction_rounds 等）。
4. **生成**：`BaseCardGenerator.generate_all_cards(stages, content)` → 合并的 Markdown（A1-B1-A2-B2… + 可选评价项章节）。
5. **元数据**：从文档或结构体中提取 `task_name`、`description`、`evaluation_items`，与评价项章节一并写入输出。

### 3.2 卡片 → 平台（注入）

1. **输入**：生成的 `cards_output_*.md` 文件路径。
2. **解析**：`CardInjector.parse_markdown(path)` → `List[ParsedCard]`（A/B 分类、role/context/阶段元数据等）。
3. **转换**：A 类 → `to_a_card_format()`（step_name、llm_prompt、description、interaction_rounds 等）；B 类 → 连线 transitionPrompt。
4. **请求**：`PlatformAPIClient` 依次 `create_step` / `create_flow`，可选 `editConfiguration`、评价项接口。

### 3.3 仿真 → 评估（闭环）

1. **加载**：`LocalCardLoader.load(path)` → 卡片列表（含 prompt、card_id）。
2. **会话**：`SessionRunner` 用 `LLMNPC` + `LLMStudent`（或 ManualStudent）按卡片顺序对话，产出 `SessionLog`（dialogue 列表）。
3. **评估**：`Evaluator.evaluate(dialogue)` → `EvaluationReport`（多维度分数、总分、建议）。
4. **导出**：报告可写入 `output/optimizer/export_score.json`，供 DSPy 优化器作为自动 metric（闭环模式）。

## 4. 配置分层

- **全局**：`config.py` + `.env`（API Key、平台 base_url、默认模型等）。
- **工作区**：`workspaces/<id>/platform_config.json`、`workspaces/<id>/llm_config.json`，覆盖或补充全局配置，便于多课程/多环境。

## 5. 扩展点

- **新解析格式**：在 `parsers/` 增加解析函数并在 `parsers/__init__.py` 与 `get_parser_for_file` 中注册。
- **新生成框架**：在 `generators/frameworks/` 下新建子目录，实现 `BaseCardGenerator`，框架库会自动发现（`list_frameworks()`）。
- **新评估维度**：修改 `simulator/evaluator.py` 中评估 prompt 与维度定义即可。

---

*文档版本：与代码同步维护。*
