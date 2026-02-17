## 错误文档汇总（EduFlow）

本文记录本项目近期排查并修复过的典型错误，便于后续定位与复用解决方案。

---

## 1. 卡片生成报错：`dspy.settings can only be changed by the thread that initially configured it`

- **现象**
  - 生成教学卡片时，部分卡片内容被替换为：
    - `"[生成失败: dspy.settings can only be changed by the thread that initially configured it.]"`。
  - 常见于使用 DSPy 框架生成卡片（`framework_id = "dspy"`）的场景。

- **原因**
  - DSPy 的 `dspy.settings` 是**线程局部**的，并且**只能由最初配置它的那个线程修改**。
  - FastAPI / Uvicorn 在处理请求时使用多线程，不同请求可能落在不同线程。
  - 当非“初始线程”再次调用 `dspy.configure(lm=...)` 时，就会触发上述错误。

- **修复方案**
  - 在 `generators/dspy_card_generator.py` 中：
    - 引入单线程执行器：
      - `ThreadPoolExecutor(max_workers=1, thread_name_prefix="dspy-card-gen")`
    - 将 `generate_all_cards` 的实际逻辑挪到 `_generate_all_cards_impl`，并：
      - **主线程调用时**（如 CLI/优化器）：直接调用实现函数。
      - **非主线程调用时**（Web 请求）：通过单线程执行器提交任务，确保所有 DSPy 调用都在同一工作线程内执行。
  - 同时保留 `_dspy_lm_lock`，序列化 `dspy.configure` 调用。

- **使用建议**
  - Web 场景下只需正常调用 `/api/cards/generate` 即可，内部已处理线程问题。
  - CLI / 优化器脚本继续按原方式调用，不需要额外改动。

---

## 2. .doc 支持与 doc2docx / pywin32 依赖冲突

- **现象**
  - 为支持 `.doc` 文件解析时，引入 `doc2docx`，安装时出现类似错误：
    - `ERROR: Cannot install doc2docx ... because these package versions have conflicting dependencies.`
    - `Additionally, some packages ... have no matching distributions: pywin32`

- **原因**
  - `doc2docx` 在 Windows 上依赖 `pywin32>=305,<306`，且需要本机安装 Microsoft Word。
  - 某些环境（如不完整的 Windows Python 发行版、WSL 等）无法安装匹配的 `pywin32`，导致依赖解析失败。

- **修复方案**
  - 将 `doc2docx` 从 **强依赖** 改为 **可选依赖**：
    - 从 `requirements.txt` 中移除 `doc2docx`，并加注释说明：
      - 仅在需要 `.doc` 解析时手动安装：`pip install doc2docx`
      - 且要求 Windows + 安装了 Microsoft Word。
  - 新增 `parsers/doc_parser.py`：
    - 如检测到安装了 `doc2docx`：
      - 先将 `.doc` 转为临时 `.docx`，再复用 `parse_docx_with_structure`。
    - 未安装时：
      - 明确抛出 `ImportError`，提示安装 `doc2docx` 或将 `.doc` 另存为 `.docx`。
  - 后端与前端均已支持 `.doc` 扩展名，但在运行时如缺少依赖，会给出**清晰错误提示**。

- **使用建议**
  - **推荐**：优先在 Word/WPS 中将 `.doc` 另存为 `.docx` 后再使用本系统。
  - 如确需直接解析 `.doc`：
    - 确保环境为 Windows，且可成功安装 `pywin32` 与 `doc2docx`。

---

## 3. 前端 JSON 解析错误：`Unexpected token 'I', "Internal S"... is not valid JSON`

- **现象**
  - Web 前端操作时弹出：
    - `Unexpected token 'I', "Internal S"... is not valid JSON`
  - 实际是某个 API 返回了 `Internal Server Error` 等**非 JSON**内容。

- **原因**
  - 前端多处直接对 `fetch` 响应调用 `r.json()`：
    - 若后端返回 HTML/纯文本（如 500 错误页），`JSON.parse` 会在 `"Internal S..."` 处报语法错误。
  - 报错信息掩盖了真正后端错误，排查困难。

- **修复方案（`web/static/index.html`）**
  - 增加统一的安全解析函数：
    ```js
    function safeResponseJson(r) {
      return r.text().then(function(text) {
        try { return JSON.parse(text); }
        catch (e) { return { detail: text || r.statusText || 'Invalid response' }; }
      });
    }
    ```
  - 将所有 `r.json()` 调用替换为 `safeResponseJson(r)`，保证：
    - 响应为合法 JSON 时：行为不变。
    - 响应为非 JSON（如 `"Internal Server Error"`）时：
      - 不再抛出 `Unexpected token`，而是返回形如 `{ detail: "Internal Server Error" }`。
  - 后端尽量使用 `HTTPException(status_code=..., detail=...)` 返回 JSON 错误体。

- **使用建议**
  - 前端统一使用 `safeResponseJson` 解析接口响应，再根据 `r.ok` 与 `data.detail` 决定提示内容。
  - 若页面上出现后端错误提示，可直接复制 `detail` 内容进行排查。

---

## 4. 大体量文档（超长 DOCX）分析失败或超时

- **现象**
  - 对体量很大的 `.docx`（如“附件1/附件2 核心认知类/拓展认知型”等）进行结构分析时：
    - 分析过程非常慢，甚至直接失败或返回 500。
    - 之前还可能触发前端的 JSON 解析错误（见问题 3）。

- **原因**
  - `ContentSplitter.analyze` 之前会将**整篇剧本**直接拼到提示词里发送给 LLM：
    - 非常长的文档可能：
      - 超出模型上下文长度；
      - 导致请求体过大、超时或接口报错。

- **修复方案（`generators/content_splitter.py`）**
  - 新增最大内容长度限制：
    - `ANALYZE_CONTENT_MAX_CHARS = 50000`（约 5 万字符，可根据需要调整）。
  - 在 `analyze` 中：
    - 若 `len(content) > ANALYZE_CONTENT_MAX_CHARS`：
      - 截断到前 5 万字符；
      - 在末尾追加说明：
        > `[以下内容因篇幅过长已省略，仅对以上部分进行分幕分析。建议将文档拆成多个较小文件或只分析前半部分。]`
      - 在返回结果中添加字段：`_truncated_note`。
  - 在 `api/routes/script.py` 的返回中透出该说明：
    - 若 `result.get("_truncated_note")` 存在，则在响应中加入：
      - `truncated_note: result["_truncated_note"]`

- **使用建议**
  - 如遇到**特别长的 Word 剧本**：
    - 建议先在 Word 中**按章节拆分为多个较小文件**；
    - 或仅保留本次分析所需的部分内容。
  - 前端可根据 `truncated_note` 给出明显提示，告知本次分析只覆盖了文档前半部分。

---

## 5. 其他注意事项

- **中文工作区名与路径**
  - 工作区 ID（如 `微观科学`、`动物解剖`）允许中文，内部通过 `get_workspace_dirs` 与 `resolve_workspace_path` 映射为 `workspaces/<工作区>/input|output`。
  - 只要通过 Web 界面创建/选择工作区并使用 API，路径解析是安全的；不要手工构造包含 `..` 的相对路径。

- **图片与嵌入对象**
  - 当前 DOCX 解析器只提取**段落文字**与**表格文字**，不会解析图片/图表/嵌入对象。
  - 文档中存在图片 **不会导致解析报错**，只是这些内容不会进入剧本文本。

---

如后续遇到新的典型错误或改动，可在本文件中继续追加条目，保持一处集中记录，方便同事快速了解历史问题与现有约束。
