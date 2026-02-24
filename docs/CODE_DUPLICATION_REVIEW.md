# 代码重复审查报告（可复用但重复实现的部分）

本报告列出项目中「本可复用一段代码、却重复实现」的板块，并给出合并建议。

---

## 1. 工作区文件列表与上传（input_files / output_files）

**位置**：`api/routes/input_files.py`、`api/routes/output_files.py`

**重复点**：

- **列出目录文件**：两处都实现「递归 `os.walk` → 收集相对路径 → 排序 → 返回 `{"files": [...]}`」，仅目录来源、前缀（`input/` vs `output/`）和扩展名过滤不同。
- **上传文件**：两处都实现「取 filename、校验扩展名 → 规范化 subpath → `makedirs` → 读流写盘 → 返回相对 path」，仅允许扩展名、默认 subpath、是否支持 `save_as` 不同。

**建议**：

- 在 `api/workspace.py` 或新建 `api/file_ops.py` 中抽出：
  - `list_dir_files(root_dir, prefix="input/", allowed_ext=None)`：`allowed_ext is None` 表示不过滤扩展名。
  - `save_upload_to_dir(root_dir, file, subpath="", allowed_ext, save_as=None)`：返回 `(rel_path, error_msg)`，error_msg 非空时由路由返回 400。
- `input_files` / `output_files` 只负责取目录（`get_workspace_dirs` / `get_project_dirs`）、传参并返回统一格式。

---

## 2. 平台配置 JSON 的读写（platform_config.py）

**位置**：`api/routes/platform_config.py`

**重复点**：

- **读配置**：`get_merged_platform_config`、`get_platform_config`、`save_platform_config`、`load_platform_config`、`set_project_from_url` 中共 **5 处**「若文件存在则 `open + json.load`，异常则忽略/空 dict」。
- **写配置**：`save_platform_config`、`load_platform_config`、`set_project_from_url` 中共 **3 处**「`json.dump(current, f, ensure_ascii=False, indent=2)`」。

**建议**：

- 在 `platform_config.py` 内增加：
  - `_read_workspace_config(path: str) -> dict`：存在则读并返回，否则返回 `{}`。
  - `_write_workspace_config(path: str, data: dict)`：写入 JSON。
- 所有「读当前工作区 platform_config.json」改为调用 `_read_workspace_config(_workspace_config_path(workspace_id))`，所有写操作改为先读再改再 `_write_workspace_config`，避免重复 try/except 与 open 逻辑。

---

## 3. 从 URL 提取 course_id / train_task_id

**位置**：`api/routes/platform_config.py`（`_extract_ids_from_url`）、`cli/platform_cfg.py`（内联 `re.search`）

**重复点**：

- 同一逻辑两处实现：`agent-course-full/([^/]+)`、`trainTaskId=([^&]+)`。

**建议**：

- 在 `api/workspace.py` 或 `config.py` 旁新增小模块（如 `api/platform_utils.py`），或直接放在 `api/routes/platform_config.py` 并导出：
  - `extract_course_and_task_from_url(url: str) -> tuple[str|None, str|None]`。
- `platform_config.py` 的 `_extract_ids_from_url` 改为调用该函数；`cli/platform_cfg.py` 从该处导入并调用，避免重复正则与错误提示文案（可保留 CLI 的 print 文案，仅提取逻辑复用）。

---

## 4. 按扩展名选择解析器（get_parser）

**位置**：`cli/common.py`（`get_parser_for_file`）、`api/routes/script.py`（`_get_parser_for_ext`）、`generators/trainset_builder.py`（`_get_parser_for_path`）

**重复点**：

- 三处都是「按 `.md/.docx/.doc/.pdf` 选解析函数」，映射表与错误信息几乎相同；API 里对 `.doc` 返回 `None` 并在上层用 `parse_doc_with_structure` 单独处理，本质仍是「按扩展名分支」。

**建议**：

- 在 `parsers/__init__.py` 或 `parsers/utils.py` 中提供统一入口，例如：
  - `get_parser_for_extension(ext: str, with_structure: bool = False)`  
    返回 `(parse_xxx, needs_structure)` 或直接返回可调用的解析函数（对 .doc/.docx 返回 `parse_*_with_structure` 的包装，使调用方统一用「一个函数(path) -> content 或 (content, structure)」）。
- CLI、API、trainset_builder 都改为从该处获取解析器，删除三份 `_get_parser_*` 实现。

---

## 5. 剧本解析 + 结构分析 + stages 标准化（script 路由）

**位置**：`api/routes/script.py` 的 `upload_and_analyze` 与 `analyze_by_path`

**重复点**：

- **解析**：两处都是「按 suffix 分支 docx → parse_docx_with_structure，doc → parse_doc_with_structure，else → _get_parser_for_ext」。
- **分析**：两处都「`ContentSplitter(api_key/base_url/model).analyze(full_content)`」。
- **stages 转 trainset 格式**：完全相同的列表推导（`id/title/description/role/task/key_points/content_excerpt`）。
- **写入 trainset**：两处都是「`get_project_dirs` → `output/optimizer/trainset.json` → `append_trainset_example`」，仅 `source_file` 参数不同。

**建议**：

- 抽出共用函数，例如在同一文件或 `api/script_helpers.py` 中：
  - `parse_file_to_content(path: str, suffix: str) -> str`
  - `analyze_content_to_stages(content, workspace_id) -> (stages, stages_for_trainset, result_dict)`（内部创建 Splitter、跑 analyze、拼 stages_for_trainset）。
  - `maybe_append_trainset(workspace_id, full_content, stages_for_trainset, source_file) -> count | None`
- 两个路由改为：解析 → 分析 → 可选 append_trainset → 拼装响应，避免两段 40+ 行几乎相同的逻辑。

---

## 6. 平台配置完整性检查（缺失项列表）

**位置**：`api/routes/inject.py`（`_check_platform_config(cfg)`）、`cli/common.py`（`check_platform_config()`）

**重复点**：

- 检查的 key 一致：`cookie`、`authorization`、`course_id`、`train_task_id`、`start_node_id`、`end_node_id`。
- 一处返回 `(bool, list[str])` 缺失项，一处用全局 `PLATFORM_CONFIG` 并 print 缺失项；「哪些 key 必填」与「缺失项列表」的生成逻辑重复。

**建议**：

- 在 `api/routes/platform_config.py` 或 `api/workspace.py` 中定义：
  - `PLATFORM_REQUIRED_KEYS = ["cookie", "authorization", "course_id", "train_task_id", "start_node_id", "end_node_id"]`
  - `check_platform_config_keys(cfg: dict) -> tuple[bool, list[str]]`：返回 (是否完整, 缺失的 key 名或显示名)。
- `inject._check_platform_config` 改为调用该函数；`cli/common.check_platform_config` 从同一处导入，用返回的缺失列表做 print，避免两处手写同样的 key 列表与 append 逻辑。

---

## 7. output 路径规范化（output_files.py）

**位置**：`api/routes/output_files.py` 的 `read_output_file`、`write_output_file`

**重复点**：

- 两处都有「把 path 转成带 `output/` 前缀的 rel」：  
  `rel = path.strip().replace("\\", "/").lstrip("/"); if not rel.startswith("output/"): rel = "output/" + rel`。

**建议**：

- 在 `api/workspace.py` 中增加 `normalize_output_rel(path: str) -> str`，两处改为 `rel = normalize_output_rel(path)`，避免复制粘贴。

---

## 8. DSPy 优化器 export_config 的构建（CLI vs API）

**位置**：`cli/optimizer.py`（`run_optimize_dspy` 前）、`api/routes/optimizer.py`（`_run_optimizer`）

**重复点**：

- 两处都根据 `export_path` 的扩展名和 `DSPY_OPTIMIZER_CONFIG` 构造 `export_config`：  
  `_ext = os.path.splitext(export_path)[1].lower()`，`_parser = "md" if _ext in (".md", ".markdown") else cfg.get("parser", "json")`，以及 `json_score_key`、`csv_score_column`。

**建议**：

- 在 `generators/dspy_optimizer.py` 或 `config.py` 旁增加 `build_export_config(export_path: str, cfg: dict) -> dict`，CLI 与 API 都调用该函数，避免重复扩展名判断与 key 读取。

---

## 9. 闭环中仿真/评估的 LLM 配置（closed_loop）

**位置**：`generators/closed_loop.py` 的 `_build_llm_config`

**重复点**：

- `sim_config` 与 `eval_config` 在 doubao 分支中完全一致，在 deepseek 分支中也完全一致，仅 model_type 不同导致取值不同。

**建议**：

- 先按 `model_type` 取一套 `(api_url, api_key, model, **extra)`，再 `sim_config = eval_config = {...}` 一次赋值，避免两段重复的 dict 字面量。

---

## 小结（按优先级）

| 优先级 | 板块 | 重复程度 | 建议动作 |
|--------|------|----------|----------|
| 高 | 平台配置 JSON 读写 | 5 读 + 3 写 | 抽 `_read_workspace_config` / `_write_workspace_config` |
| 高 | script 路由解析+分析+stages | 两段 40+ 行几乎相同 | 抽 `parse_file_to_content`、`analyze_content_to_stages`、`maybe_append_trainset` |
| 高 | 按扩展名选解析器 | 3 处映射表 | 统一到 `parsers` 的 `get_parser_for_extension` |
| 中 | input/output 列表与上传 | 2 处列表 + 2 处上传 | 抽 `list_dir_files`、`save_upload_to_dir` |
| 中 | URL 提取 course/task | API + CLI 两处 | 抽 `extract_course_and_task_from_url` 并复用 |
| 中 | 平台配置完整性检查 | 两处 key 列表 + 缺失逻辑 | 抽 `PLATFORM_REQUIRED_KEYS` + `check_platform_config_keys` |
| 低 | output 路径规范化 | 2 处相同片段 | 抽 `normalize_output_rel` |
| 低 | DSPy export_config | CLI + API | 抽 `build_export_config` |
| 低 | closed_loop LLM 配置 | 同文件内 sim/eval 重复 | 先取一套再赋值 |

按上述顺序逐步抽公共函数，可以在不改变行为的前提下明显减少重复、便于后续修改（例如扩展名或配置 key 变更只改一处）。
