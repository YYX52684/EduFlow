# EduFlow - 沉浸式教学卡片自动生成工具

一个面向高校教师的自动化工具，可以将教学剧本（类似"课程版剧本杀"）自动转换为智慧树平台的沉浸式教学卡片。

## 功能特点

- **多格式支持**：支持 Markdown、DOCX、PDF 格式的剧本输入
- **智能分析**：使用 LLM 自动分析剧本结构，划分场景/幕
- **双类卡片生成**：
  - **A类卡片**：NPC角色卡片，与学生进行沉浸式对话
  - **B类卡片**：场景过渡卡片，连接不同场景
- **平台注入**：一键将生成的卡片注入到智慧树教学平台
- **多用户工作区**：部署为正式网站时，每人一个工作区（URL 含 `/w/工作区ID`），上传、生成、平台配置互不影响

## 项目结构

```
EduFlow/
├── main.py              # 命令行入口
├── run_web.py           # Web 服务启动脚本（推荐）
├── config.py            # 配置文件
├── requirements.txt     # 依赖项
├── requirements-dev.txt # 开发/测试依赖（pytest 等）
├── api/                 # Web API（FastAPI）+ 统一异常与 request_id 中间件
├── web/static/          # 前端静态页（index.html）
├── generators/          # 生成器模块
├── parsers/             # 文件解析器
├── api_platform/        # 智慧树平台 API 与卡片注入
├── docs/                # 文档（如 architecture.md 架构与数据流）
├── tests/               # pytest 测试
├── templates/           # 模板文件
├── input/               # 命令行用输入目录
├── output/              # 命令行用输出目录
└── workspaces/          # Web 多用户工作区（每人一个子目录，含 input、output、platform_config.json）
```

## 安装

1. **克隆项目**
```bash
git clone <repository-url>
cd EduFlow
```

2. **创建虚拟环境（推荐）**
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **运行测试（可选）**

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

5. **配置环境变量**

复制 `.env.example` 为 `.env`，并填写配置（`.env` 含 API Key，**不要提交到 Git**；给同事时可私下发一份或让她按说明自建）：

```env
# LLM API配置（必填）
DEEPSEEK_API_KEY=your_deepseek_api_key

# 智慧树平台配置（注入功能需要）
PLATFORM_COOKIE=your_cookie
PLATFORM_AUTHORIZATION=your_jwt_token
PLATFORM_COURSE_ID=your_course_id
PLATFORM_TRAIN_TASK_ID=your_train_task_id
PLATFORM_START_NODE_ID=start_node_id
PLATFORM_END_NODE_ID=end_node_id
```

## 使用方法

**Windows 用户**：若命令行或输出中出现中文乱码，请先在终端执行 `chcp 65001` 切换到 UTF-8 编码，或使用 Windows Terminal / VS Code 内置终端（通常已默认 UTF-8）。程序已自动将输出设为 UTF-8。

### 1. 生成卡片

```bash
# 基本用法：生成卡片并保存为Markdown
python main.py --input "input/你的剧本.md"

# 指定输出文件名
python main.py --input "input/你的剧本.md" --output "output/我的卡片.md"

# 预览模式：只分析剧本结构，不生成卡片
python main.py --input "input/你的剧本.md" --preview
```

### 2. 注入到平台

```bash
# 生成并注入到智慧树平台
python main.py --input "input/你的剧本.md" --inject

# 仅注入已生成的卡片文件
python main.py --inject-only "output/cards_output_xxx.md"
```

### 3. 支持的文件格式

- `.md` - Markdown 文件
- `.docx` - Microsoft Word 文档
- `.pdf` - PDF 文档

## 剧本格式建议

剧本应包含以下要素：

```markdown
# 剧本标题

## 阶段1：场景名称
**角色**：NPC角色名
**学员角色**：学生扮演的角色（可选）
**任务**：本场景的目标

### 情境描述
[描述场景背景和对话情境]

### 关键点
- 要点1
- 要点2

---

## 阶段2：下一个场景
...
```

## 配置说明

### LLM 配置

| 变量 | 说明 | 默认值 |
|-----|------|-------|
| `DEEPSEEK_API_KEY` | DeepSeek API密钥 | - |
| `DEEPSEEK_MODEL` | 使用的模型 | `deepseek-chat` |

### 平台配置

| 变量 | 说明 |
|-----|------|
| `PLATFORM_COOKIE` | 平台登录Cookie |
| `PLATFORM_AUTHORIZATION` | JWT Token |
| `PLATFORM_COURSE_ID` | 课程ID |
| `PLATFORM_TRAIN_TASK_ID` | 训练任务ID |
| `PLATFORM_START_NODE_ID` | 起始节点ID |
| `PLATFORM_END_NODE_ID` | 结束节点ID |

### 卡片默认配置

| 变量 | 说明 | 默认值 |
|-----|------|-------|
| `CARD_MODEL_ID` | AI模型ID | `doubao-seed-1.6` |
| `CARD_TRAINER_NAME` | 虚拟训练官名称 | `ai` |

## 获取平台配置

1. 登录智慧树教学平台
2. 打开浏览器开发者工具（F12）-> Network
3. 进入你要编辑的课程/训练任务
4. 从请求中获取相关ID和认证信息

### 4. Web 交互（可选）

在项目根目录启动 Web 服务后，用浏览器操作：上传剧本分析、生成卡片、模拟测试、评估与注入等。

```bash
# 本机使用（默认 HTTP）
python run_web.py
```

- 打开浏览器会跳转到 **工作区地址**（如 `http://localhost:8000/w/abc123`），每人一个工作区，上传与生成的文件、平台配置均隔离在 `workspaces/<工作区ID>/` 下，互不影响。
- 本机访问：`http://localhost:8000/` 或 `http://127.0.0.1:8000/`，API 文档：`http://localhost:8000/docs`。

**分享给同事（同一局域网）：**

- 启动后终端会打印 **同事访问地址**（如 `http://192.168.x.x:8000`），同事用该地址打开即可（会得到自己的 `/w/xxx` 工作区）。
- 若同事需要用到 **「选择目录」** 上传（浏览器安全策略要求 HTTPS 或 localhost），请用 HTTPS 启动：
  ```bash
  pip install cryptography   # 首次使用 --https 时需安装
  python run_web.py --https
  ```
  同事访问 `https://你的IP:8000`，浏览器提示证书不受信任时点「高级」→「继续访问」即可。
- 若本机有防火墙，需放行 8000 端口或允许 Python 访问网络。

**正式网站部署（大家共用一个站点、工作互不影响）：**

- 将服务部署到一台服务器（公司内网或云主机），所有人访问同一网址（如 `https://eduflow.公司.com`）。
- 每人首次打开会得到唯一的工作区 URL（如 `https://eduflow.公司.com/w/abc123`），收藏该地址即可；上传、生成、平台配置均只在该工作区内，互不干扰。
- **详细步骤**（直接运行、Docker、Nginx + HTTPS）见 **[DEPLOY.md](DEPLOY.md)**。

**同事各自本地跑一份：**

- 你把项目推到 Git，同事 `git clone` 后在本机执行上述安装与配置（含 `.env`），再运行 `python run_web.py`。数据在本机，与服务器或你本机完全独立。

更多说明见 [Operations.md](Operations.md) 第十一节。

### 5. Docker 部署（可选）

```bash
# 构建镜像（项目根目录）
docker build -t eduflow .

# 运行：需提供 .env 或环境变量（至少 DEEPSEEK_API_KEY）
docker run -p 8000:8000 --env-file .env -v "$(pwd)/workspaces:/app/workspaces" eduflow
```

- 访问 `http://localhost:8000/` 或 `http://<服务器IP>:8000/`。挂载 `workspaces` 可将工作区数据持久化到宿主机。

## 卡片编辑与试玩

在 Web 内直接编辑卡片 Markdown，无需导出到平台即可试玩：加载 output 下卡片 → 在编辑器中修改 → 保存或**一键试玩**（用当前内容直接跑仿真）。减少「导出→平台→体验→再改」的往返。

## 闭环优化

闭环优化实现「生成 → 仿真 → 评估」自动迭代，无需外部平台人工评估：

1. **单次闭环**：对已有卡片运行「仿真 + 评估」，并保存为优化器导出文件
   - Web：第 3 步点击「闭环运行」
   - API：`POST /api/closed-loop/run`，body: `{ "cards_path": "...", "save_to_export": true }`

2. **优化器闭环模式**：DSPy 优化时每轮自动仿真+评估
   - CLI：`python run_optimizer.py --auto-eval`
   - Web：第 6 步勾选「闭环模式（仿真+评估替代外部评估）」

## 注意事项

- 生成的卡片以语音形式与学生沟通，内容会自动控制在合适的长度
- 严禁在卡片中使用括号描写（心理、动作等），会影响语音体验
- 建议先使用 `--preview` 预览分析结果，再进行完整生成

## 许可证

MIT License
