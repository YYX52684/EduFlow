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

复制 `.env.example` 为 `.env`，并填写配置：

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

MIT License
