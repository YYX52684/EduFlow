# EduFlow 项目冗余与重复设计审查报告

本文档汇总项目中**高度重复/冗余**的功能与设计，并给出可落地的重构建议（优先级与改动范围）。

---

## 一、API 路由层

### 1.1 工作区路径解析重复（高）

**现象**：  
- `api/routes/optimizer.py` 中有 `_resolve_output_path(workspace_id, relative_path)`。  
- `api/routes/trainset.py` 中有 `_resolve_input_path` 与 `_resolve_output_path`。  
- 逻辑一致：规范化相对路径（补 `output/` 或 `input/` 前缀）后调用 `resolve_workspace_path(..., kind="output"|"input")`。

**建议**：  
- 在 `api/workspace.py` 中新增统一方法，例如：  
  - `resolve_output_path(workspace_id, relative_path, must_exist=False)`  
  - `resolve_input_path(workspace_id, relative_path, must_exist=False)`  
- 各路由只保留「业务参数校验 + 调用 workspace 方法」，删除本地的 `_resolve_*_path`。

**涉及文件**：`api/workspace.py`、`api/routes/optimizer.py`、`api/routes/trainset.py`。

---

### 1.2 工作区“配置文件路径”重复（中）

**现象**：  
- `api/routes/llm_config.py`：`_config_path(workspace_id)` → `get_workspace_dirs` + `os.path.join(root, "llm_config.json")`。  
- `api/routes/platform_config.py`：`_workspace_config_path(workspace_id)` → `get_workspace_dirs` + `os.path.join(workspace_root, "platform_config.json")`。  
- 模式相同：先取工作区根目录，再拼文件名。

**建议**：  
- 在 `api/workspace.py` 中增加：  
  `get_workspace_file_path(workspace_id: str, filename: str) -> str`  
- `llm_config` 与 `platform_config` 中不再各自实现 `_config_path` / `_workspace_config_path`，改为调用该函数并传入对应文件名。

**涉及文件**：`api/workspace.py`、`api/routes/llm_config.py`、`api/routes/platform_config.py`。

---

### 1.3 平台配置“读取与合并”重复（中）

**现象**：  
- `api/routes/inject.py` 中 `_get_workspace_platform_config(workspace_id)`：读 `workspaces/<id>/platform_config.json`，与 `PLATFORM_CONFIG` 合并，工作区非空值覆盖。  
- `api/routes/platform_config.py` 中 GET 与 reset 逻辑也涉及「工作区 JSON + .env/PLATFORM_CONFIG」的合并与回退。  
- 合并规则和 key 列表（如 base_url, cookie, authorization, course_id, ...）在两处重复。

**建议**：  
- 在 `platform_config` 模块中抽出一个**唯一真相**：  
  - 例如 `get_merged_platform_config(workspace_id: str) -> dict`（仅读、合并，不写）。  
- `inject` 不再实现 `_get_workspace_platform_config`，改为调用 `get_merged_platform_config(workspace_id)`。  
- 若需区分「供前端展示」与「供注入使用」，可在同一模块内再包一层（如脱敏、过滤 key），避免两处各自实现合并逻辑。

**涉及文件**：`api/routes/platform_config.py`、`api/routes/inject.py`。

---

### 1.4 流式 vs 非流式端点核心逻辑双份（高）

**现象**：  
- **卡片生成**：`/generate` 与 `/generate-stream` 中「校验 stages、选框架、实例化 Generator、调 generate_all_cards、写文件、拼 header、返回结果」几乎完全一致；流式版多了一个线程 + Queue + SSE 包装。  
- **闭环**：`/run` 与 `/run-stream` 同理，核心都是 `run_simulate_and_evaluate(...)` + 可选的 `_write_export_files`。  
- **优化器**：`/run` 与 `/run-stream` 同理，核心都是参数校验 + 路径解析 + `run_optimize_dspy(...)`。

**建议**：  
- 每个功能只保留**一份核心逻辑**（同步函数），接受可选的 `progress_callback`（或类似）。  
- 非流式路由：直接调用该核心函数并返回 JSON。  
- 流式路由：在同一核心函数上包一层「线程 + Queue + async event_stream」，只负责把 progress/done/error 转为 SSE，不再复制业务代码。  
- 示例（卡片）：  
  - 抽 `_run_generate_cards(req, workspace_id, progress_callback=None, card_callback=None)`，内部完成框架选择、generator 创建、写文件、返回 `(output_path, output_filename, ...)`。  
  - `generate_cards` 调用 `_run_generate_cards(req, workspace_id)`。  
  - `generate_cards_stream` 在子线程中调用 `_run_generate_cards(..., progress_cb=..., card_cb=...)`，主协程只消费 Queue 并写 SSE。

**涉及文件**：`api/routes/cards.py`、`api/routes/closed_loop.py`、`api/routes/optimizer.py`。

---

### 1.5 仅用 get_workspace_dirs / get_project_dirs 的“一个返回值”（低）

**现象**：  
- 多处出现 `_, output_dir, _ = get_workspace_dirs(workspace_id)` 或 `get_project_dirs(...)`，仅用 `output_dir` 或 `project_output`。

**建议**：  
- 若此类用法很多，可在 `workspace.py` 增加便捷方法，例如：  
  - `get_workspace_output_dir(workspace_id)`  
  - `get_project_output_dir(workspace_id)`  
- 减少重复解构与注释，可读性更好；优先级可低于 1.1/1.2。

**涉及文件**：`api/workspace.py`、各 route 文件。

---

## 二、模拟器层（simulator）

### 2.1 LLM 调用模式重复（高）

**现象**：  
- `simulator/llm_npc.py`、`simulator/llm_student.py`、`simulator/evaluator.py`（以及 `student_persona.py` 中若存在 LLM 调用）中，均存在：  
  - 从 config 取 `api_url`、`api_key`、`model`、`service_code`；  
  - 构建 `headers`（Content-Type、Authorization、serviceCode）；  
  - 构建 `payload`（model, messages, max_tokens, temperature, stream=False）；  
  - `requests.post(api_url, headers=..., json=payload, timeout=...)`；  
  - 解析 `result["choices"][0]["message"]["content"]` 或兼容 `content`/`response`。  
- 仅参数（max_tokens、temperature、timeout）和解析细节略有不同，结构高度一致。

**建议**：  
- 在 `simulator` 下新增公共模块，例如 `simulator/llm_client.py`，提供：  
  - `call_chat_completion(api_url, api_key, model, messages, max_tokens=400, temperature=0.7, service_code="", timeout=60) -> str`  
  - 内部统一处理 headers、payload、requests.post、错误与响应解析。  
- `LLMNPC`、`LLMStudent`、评估器（及 persona 中 LLM 调用）均改为调用该函数，仅传各自参数。

**涉及文件**：新建 `simulator/llm_client.py`；修改 `simulator/llm_npc.py`、`simulator/llm_student.py`、`simulator/evaluator.py`（及 `student_persona.py` 若存在 LLM 调用）。

---

### 2.2 默认配置重复（中）

**现象**：  
- `llm_npc._default_npc_config()`、`llm_student._default_student_config()` 均从 `config` 取 `DEEPSEEK_CHAT_URL`、`DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`，返回相同结构的 dict。  
- 评估器内部也有类似的 defaults。

**建议**：  
- 在 `simulator/llm_client.py`（或 `config`）中提供**一份**「模拟器用默认配置」：  
  - 例如 `get_simulator_default_config() -> dict`（api_url, api_key, model）。  
- NPC/Student/Evaluator 的 `config or {}` 与 `defaults` 合并时，统一使用该默认配置，再按角色覆盖 `max_tokens`、`temperature` 等。  
- 可与 2.1 一起做：先统一默认配置，再统一调用 `call_chat_completion`。

**涉及文件**：`simulator/llm_client.py`（或 `config.py`）、`simulator/llm_npc.py`、`simulator/llm_student.py`、`simulator/evaluator.py`。

---

## 三、解析器层（parsers）

### 3.1 文件校验与错误风格重复（低）

**现象**：  
- `pdf_parser`、`md_parser`、`docx_parser` 等均存在：  
  - 文件存在性检查 `os.path.exists`；  
  - 扩展名校验（`.pdf`、`.md`、`.docx`）；  
  - `ImportError` 与 `ValueError` 的提示信息风格类似。  

**建议**：  
- 在 `parsers` 包内增加一个公共辅助，例如：  
  - `_validate_path(file_path: str, expected_ext: str, parser_name: str) -> None`  
  - 内部完成存在性、扩展名、可选的安全路径检查，统一抛出 `FileNotFoundError` / `ValueError`。  
- 各 parser 在入口处调用 `_validate_path`，减少重复 if/raise 和重复错误文案。

**涉及文件**：`parsers/` 下新建 `_utils.py` 或放在 `__init__.py` 中；各 `*_parser.py`。

---

## 四、前端（web/static/index.html）

### 4.1 POST 请求写法重复（低）

**现象**：  
- 大量 `apiFetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(...) })` 的重复模式。  
- `apiFetch` 已统一处理 `Authorization` 与 `X-Workspace-Id`，仅 body 与 path 不同。

**建议**：  
- 封装 `apiPost(path, body)`，内部固定 `method: 'POST'`、`Content-Type: application/json`、`body: JSON.stringify(body)`，调用 `apiFetch`。  
- 将现有所有「仅 POST + JSON」的调用替换为 `apiPost(path, body)`，减少样板代码。

**涉及文件**：`web/static/index.html`。

---

### 4.2 SSE 流式请求模式（若存在多处）（低）

**现象**：  
- 若存在多处「fetch 流式接口 + 解析 event: progress/done/error」的类似代码，则存在重复。

**建议**：  
- 抽成统一封装，例如：  
  - `streamApi(path, body, { onProgress, onDone, onError })`  
  - 内部使用 `fetch` + 读流 + 按行解析 SSE，按 event 类型回调。  
- 卡片流式生成、闭环流式、优化器流式等可共用该封装。  
- 需确认当前 HTML 中 SSE 使用点数量后再决定是否值得抽象。

**涉及文件**：`web/static/index.html`。

---

## 五、总结与优先级建议

| 优先级 | 项 | 主要收益 |
|--------|----|----------|
| 高 | 1.1 工作区路径解析统一到 workspace | 单一真相、少 bug、易维护 |
| 高 | 1.4 流式/非流式共用核心逻辑 | 少重复、行为一致、易改 |
| 高 | 2.1 模拟器 LLM 调用统一 | 改 API 格式/错误处理一处即可 |
| 中 | 1.2 工作区配置文件路径统一 | 与 1.1 一起可进一步收敛 workspace API |
| 中 | 1.3 平台配置合并逻辑统一 | 注入与配置页行为一致、少漂移 |
| 中 | 2.2 模拟器默认配置统一 | 与 2.1 一起做更简洁 |
| 低 | 1.5 便捷方法 get_*_output_dir | 可读性 |
| 低 | 3.1 解析器校验辅助 | 错误信息一致、少重复 |
| 低 | 4.1 / 4.2 前端 apiPost / streamApi | 前端可读性与维护成本 |

建议实施顺序：**1.1 → 1.4 → 2.1（含 2.2）→ 1.2 → 1.3**，其余按需在重构时顺带完成。
