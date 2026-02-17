# EduFlow 代码库健康度审查（防「屎山」）

本报告从**架构、API、前端、配置与安全、可维护性**等维度审查项目，给出**必须改 / 应该改 / 可择机改**的结论与具体建议。

---

## 一、架构与模块边界

### 1.1 入口与 sys.path（应改）

**现状**：至少 5 处修改 `sys.path`（`api/app.py`、`main.py`、`run_web.py`、`run_optimizer.py`、`tests/conftest.py`），依赖「当前工作目录 + 脚本所在目录」才能正确 import。

**风险**：从非项目根目录执行、或以 `python -c` / 其他入口启动时易出现 `ModuleNotFoundError`，排查成本高。

**建议**：
- 统一入口：Web 用 `python -m uvicorn api.app:app --reload`（项目根为 cwd），或保持 `run_web.py` 但内部只设一次 `sys.path` 并 `os.chdir(_ROOT)`（run_web 已 chdir，可保留）。
- CLI：在 `main.py` 开头集中一次 `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))`，其余脚本尽量通过 `python main.py subcommand` 或显式 `PYTHONPATH=根目录 python script.py` 运行。
- 长期：做成可安装包（`pip install -e .`），根目录提供 `pyproject.toml`，不再依赖 path 注入。

### 1.2 main.py 单文件过大（应改）

**现状**：`main.py` 约 **1351 行**，包含解析、生成、注入、模拟、评估、优化、人设、项目配置等大量子命令，且大量使用「在分支内 import」以减轻启动依赖。

**风险**：单文件承担过多职责，新人难以定位逻辑；修改某一子命令易误伤其它；合并冲突频繁。

**建议**：
- 按子命令拆成 **CLI 子模块**（如 `cli/script.py`、`cli/simulate.py`、`cli/inject.py`、`cli/optimizer.py`、`cli/personas.py`），每个文件只处理一类命令。
- `main.py` 只做：解析顶层参数、dispatch 到对应子模块的 `run(args)`，并保留顶层共用的 `get_parser_for_file`、`check_platform_config` 等工具函数（可放入 `cli/common.py`）。
- 子模块内再按需 lazy import（如 `simulator`、`generators`），避免启动时全量加载。

### 1.3 根目录 input/output 与工作区目录并存（建议澄清）

**现状**：`config.py` 定义根目录 `INPUT_DIR`、`OUTPUT_DIR` 并在 import 时 `makedirs`；Web 与多数 API 使用 `workspaces/<id>/input|output`。`main.py` 和 `run_optimizer.py` 中部分路径在「未指定 workspace」时回退到根目录 `OUTPUT_DIR` / `OPTIMIZER_OUTPUT_DIR`。

**风险**：两套「输入/输出」概念并存，新人易混淆；根目录的 `input/`、`output/` 与工作区隔离语义不一致。

**建议**：
- 在 `config.py` 顶部用注释明确：**根目录 `INPUT_DIR`/`OUTPUT_DIR` 仅用于 CLI 未指定 `--workspace` 时的默认路径；Web 与 API 一律使用 `workspaces/<id>/input|output`。**
- 长期可考虑：CLI 也默认要求 `--workspace`，无 workspace 时使用 `default` 工作区，减少两套路径并存。

### 1.4 模块依赖关系

**结论**：`api` 依赖 `generators`、`parsers`、`simulator`、`api_platform`、`config`；无循环依赖。各层边界清晰，可保持。

---

## 二、API 与路由

### 2.1 认证与鉴权（已较好）

- 工作区相关路由统一使用 `require_workspace_owned`，与 `get_workspace_id` + 数据库校验一致。
- `/api/health`、`/api/auth/*` 为公开；`/api/frameworks` 仅列举框架，无敏感数据；`/api/personas` 为人设列表与生成，当前未绑定工作区，可接受。

### 2.2 路由前缀风格（小问题）

- 多数为 `prefix="/api/xxx"`（如 `/api/script`、`/api/cards`），而 `evaluate` 为 `prefix="/api"`，路由为 `/api/evaluate`、`/api/evaluate/from-file`。
- **建议**：若希望风格统一，可将 evaluate 改为 `prefix="/api/evaluate"`，路由即 `/api/evaluate`、`/api/evaluate/from-file`（与其它模块一致）。非必须，属一致性优化。

### 2.3 异常与错误体（已较好）

- 业务异常继承 `EduFlowError`，统一 `to_dict()`，中间件注入 `request_id`，未捕获异常不泄露堆栈。无需大改。

---

## 三、前端（index.html）

### 3.1 单文件过大（必须重视）

**现状**：**约 3515 行** 单 HTML 文件，内联 CSS（约 1050 行）+ 内联 JS（约 2400+ 行），227+ 处 `getElementById`/`querySelector`，大量事件绑定与流程逻辑混在一起。

**风险**：任何功能改动都要在巨型文件中搜索；合并冲突多；难以做按需加载与单元测试；新人上手成本高。

**建议（分阶段）**：
1. **短期**：按功能拆成 **多份 JS 文件**（如 `auth.js`、`settings.js`、`script.js`、`cards.js`、`simulate.js`、`inject.js`、`optimizer.js`、`output.js`、`common.js`），`index.html` 只保留结构 + 少量内联或一个 `main.js` 做初始化。不引入构建工具也可完成，只需 `<script src="static/xxx.js">` 顺序加载。  
   **已做**：已新增 `web/static/js/common.js`、`auth.js`、`settings.js`，`index.html` 已按顺序加载三者；内联脚本仍保留完整逻辑以兼容，后续可将「从 var handleStack 到注入按钮」整段迁入 `app.js` 并删内联重复。
2. **中期**：引入轻量构建（如 Vite + vanilla 或 Vue 3 单页），将 HTML 拆成若干「区块组件」或「页面片段」，CSS 按模块拆成文件或 CSS-in-JS，便于复用与测试。
3. **长期**：若产品继续膨胀，可考虑状态管理（如 Pinia/Vuex 或 Zustand）与路由（如 Vue Router），避免全局变量和「到处都是 getElementById」。

### 3.2 全局状态与命名（建议）

- 当前大量依赖全局变量和直接 DOM 操作，没有集中状态对象。拆成多文件时，建议至少有一个 **全局命名空间**（如 `window.EduFlow = { state: {...}, api: {...} }`），避免命名冲突和「谁改了什么」难以追踪。

---

## 四、配置与安全

### 4.1 JWT 密钥（必须改）

**现状**：`api/routes/auth.py` 中 `JWT_SECRET = os.getenv("JWT_SECRET", "eduflow-dev-secret-change-in-production")`。若生产未设 `JWT_SECRET`，任何人可伪造 token。

**建议**：
- 生产环境（或非本地环境）**禁止使用默认值**：若 `os.getenv("JWT_SECRET")` 为空且判定为生产，则启动时报错或拒绝启动。
- 已在 `.env.example` 中说明 JWT_SECRET；建议在 `auth.py` 启动时若为默认 secret 打 **logging.warning**，并在部署文档中明确「生产必须设置 JWT_SECRET」。

### 4.2 CORS（建议）

**现状**：`allow_origins=["*"]`，适合开发；生产若仅限前端域名，应改为具体 `origins` 列表（从环境变量读取）。

### 4.3 敏感信息与路径（已较好）

- API Key、平台 Cookie/Authorization 等均从环境变量或工作区配置读取，无硬编码密钥。
- 工作区路径解析使用 `resolve_workspace_path`，防止 `..` 逃逸，可保持。

---

## 五、死代码与重复

### 5.1 已做过的去重（见 REDUNDANCY_REVIEW / CLEANUP_REVIEW）

- 路径解析、平台配置合并、流式/非流式核心逻辑、模拟器 LLM 调用等已做了一轮收敛，当前重复度可接受。

### 5.2 可选清理

- **config.py**：根目录 `INPUT_DIR`/`OUTPUT_DIR` 若仅被 CLI 使用，可在注释中写明「仅 CLI 默认路径」，避免误用于 Web。
- **main.py**：拆分为子模块后，可顺带删除未再使用的 import 与重复的「检查平台配置」等工具函数重复定义（若有）。

---

## 六、测试与文档

### 6.1 测试

- 现有 16 个用例，覆盖异常处理、配置流、解析、评估等；**建议**：为关键 API 路由增加集成测试（如带 token 的请求、工作区隔离），并为核心生成器/解析器增加单元测试，避免重构时回归。

### 6.2 文档

- README、DEPLOY、docs/（architecture、workflow、operations、troubleshooting）已较完整；代码内注释已清理过一轮。保持「复杂逻辑必有注释」即可。

---

## 七、优先级汇总

| 优先级 | 项 | 说明 |
|--------|----|------|
| **P0** | JWT_SECRET 生产禁用默认值 | ✅ 已实现：`EDUFLOW_ENV=production` 时未配置或使用默认值则启动时 `RuntimeError` 拒绝启动 |
| **P1** | main.py 拆成 CLI 子模块 | 单文件 1300+ 行，维护成本高，拆分后易扩展 |
| **P1** | 前端 index.html 拆成多 JS 文件 | 3500+ 行单文件是最大可维护性瓶颈，先按功能拆 JS 即可见效 |
| **P2** | 统一入口与 sys.path | 减少 path 注入，推荐可安装包或统一 PYTHONPATH |
| **P2** | config 根目录 input/output 注释 | 明确「仅 CLI 默认」，避免与工作区概念混淆 |
| **P2** | evaluate 路由前缀统一为 /api/evaluate | 与其它 API 风格一致 |
| **P3** | CORS 生产环境收紧 | 从环境变量读取 allow_origins |
| **P3** | 增加 API/集成测试 | 保证重构与上线安全 |

---

## 八、已做的即时改进（与本审查同步）

- **auth.py**：在应用启动时若 `JWT_SECRET` 仍为默认值，打 **warning** 日志，提醒生产必须设置。
- **.env.example**：确保 JWT_SECRET 项存在且注释中写明「生产必填」。

按上述 P0→P1→P2 顺序推进，可显著降低「屎山」化风险，并保持后续迭代可维护。
