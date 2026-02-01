# EduFlow - 沉浸式教学卡片自动生成工具

一个面向高校教师的自动化工具，可以将教学剧本（类似"课程版剧本杀"）自动转换为智慧树平台的沉浸式教学卡片。

## 功能特点

- **多格式支持**：支持 Markdown、DOCX、PDF 格式的剧本输入
- **智能分析**：使用 LLM 自动分析剧本结构，划分场景/幕
- **双类卡片生成**：
  - **A类卡片**：NPC角色卡片，与学生进行沉浸式对话
  - **B类卡片**：场景过渡卡片，连接不同场景
- **平台注入**：一键将生成的卡片注入到智慧树教学平台

## 项目结构

```
EduFlow/
├── main.py              # 主入口脚本
├── config.py            # 配置文件
├── requirements.txt     # 依赖项
├── generators/          # 生成器模块
│   ├── content_splitter.py  # 剧本分析器
│   └── card_generator.py    # 卡片生成器
├── parsers/             # 文件解析器
│   ├── md_parser.py     # Markdown解析
│   ├── docx_parser.py   # Word文档解析
│   └── pdf_parser.py    # PDF解析
├── platform/            # 平台对接模块
│   ├── api_client.py    # 智慧树API客户端
│   └── card_injector.py # 卡片注入器
├── templates/           # 模板文件
│   └── system_context.md    # LLM系统上下文
├── input/               # 输入目录（放置剧本）
└── output/              # 输出目录（生成的卡片）
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

4. **配置环境变量**

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

## 注意事项

- 生成的卡片以语音形式与学生沟通，内容会自动控制在合适的长度
- 严禁在卡片中使用括号描写（心理、动作等），会影响语音体验
- 建议先使用 `--preview` 预览分析结果，再进行完整生成

## 许可证

MIT License
