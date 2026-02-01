## EduFlow 操作指令总结

### 一、卡片生成命令

| 命令 | 说明 |
|------|------|
| `python main.py -i "剧本.md"` | 从剧本生成卡片（支持 .md / .docx / .pdf） |
| `python main.py -i "剧本.md" -o "输出.md"` | 指定输出文件路径 |
| `python main.py -i "剧本.md" --preview` | 预览模式：只分析结构，不生成卡片 |
| `python main.py -i "剧本.md" -v` | 详细输出模式 |

---

### 二、平台注入命令

| 命令 | 说明 |
|------|------|
| `python main.py --inject-only "卡片.md" --preview-inject` | 预览解析结果（不实际注入） |
| `python main.py --inject-only "卡片.md"` | 将已生成的卡片注入到平台 |
| `python main.py -i "剧本.md" --inject` | 生成卡片后自动注入 |
| `python main.py -i "剧本.md" --preview-inject` | 生成后预览注入内容 |

---

### 三、学生模拟测试命令

| 命令 | 说明 |
|------|------|
| `python main.py --simulate "卡片.md" --persona "excellent"` | 自动模式（LLM扮演优秀学生） |
| `python main.py --simulate "卡片.md" --persona "average"` | 自动模式（LLM扮演普通学生） |
| `python main.py --simulate "卡片.md" --persona "struggling"` | 自动模式（LLM扮演较弱学生） |
| `python main.py --simulate "卡片.md" --manual` | 手动模式（终端输入学生回复） |
| `python main.py --simulate "卡片.md" --persona "average" --hybrid` | 混合模式（可随时切换） |
| `python main.py --simulate "卡片.md" --persona "custom/xxx.yaml"` | 使用自定义人设 |
| `python main.py --simulate "卡片.md" --persona-batch "excellent,average,struggling"` | 批量测试多种人设 |
| `python main.py --simulate "卡片.md" --no-eval` | 模拟测试后不运行评估 |

---

### 四、评估与角色管理命令

| 命令 | 说明 |
|------|------|
| `python main.py --evaluate "logs/session_xxx.json"` | 评估已有的对话日志 |
| `python main.py --list-personas` | 列出所有可用的人设 |
| `python main.py --generate-personas "剧本.docx"` | 根据剧本智能生成推荐角色 |
| `python main.py --generate-personas "剧本.md" --num-personas 5` | 指定生成角色数量 |

---

### 五、项目配置命令

| 命令 | 说明 |
|------|------|
| `python main.py --set-project "URL"` | 从页面URL自动提取课程ID和任务ID |

**示例：**
```bash
python main.py --set-project "https://hike-teaching-center.polymas.com/tch-hike/agent-course-full/5vamqyyzvecvnoY4NKa4/ability-training/create?trainTaskId=WwD67NeKNVsyMrpypxkJ"
```

---

### 六、典型工作流程

#### 流程A：卡片生成与注入
```bash
# 1. 首次/切换项目：设置项目配置
python main.py --set-project "智慧树页面URL"

# 2. 生成卡片
python main.py -i "./input/教学剧本.md"

# 3. 预览注入内容（检查解析是否正确）
python main.py --inject-only "./output/cards_output_xxx.md" --preview-inject

# 4. 正式注入到平台
python main.py --inject-only "./output/cards_output_xxx.md"
```

#### 流程B：学生模拟测试
```bash
# 1. 根据剧本智能生成推荐角色
python main.py --generate-personas "./input/教学剧本.docx"

# 2. 使用预设人设运行模拟测试
python main.py --simulate "./output/cards_output_xxx.md" --persona "excellent"

# 3. 或使用生成的自定义角色
python main.py --simulate "./output/cards_output_xxx.md" --persona "custom/generated_1_xxx.yaml"

# 4. 批量测试多种人设
python main.py --simulate "./output/cards.md" --persona-batch "excellent,average,struggling"

# 5. 单独评估对话日志
python main.py --evaluate "./simulator_output/logs/session_xxx.json"
```

---

### 七、参数速查表

#### 卡片生成参数
| 参数 | 简写 | 说明 |
|------|------|------|
| `--input` | `-i` | 输入剧本文件路径 |
| `--output` | `-o` | 输出文件路径 |
| `--preview` | `-p` | 预览剧本结构 |
| `--verbose` | `-v` | 详细输出 |
| `--use-dspy` | | 使用DSPy结构化生成器 |

#### 平台注入参数
| 参数 | 说明 |
|------|------|
| `--inject` | 生成后注入平台 |
| `--inject-only` | 仅注入已有文件 |
| `--preview-inject` | 预览注入内容 |
| `--set-project` | 从URL设置项目配置 |

#### 模拟测试参数
| 参数 | 说明 |
|------|------|
| `--simulate` | 运行模拟测试，指定卡片文件 |
| `--persona` | 学生人设 (excellent/average/struggling/custom/xxx.yaml) |
| `--manual` | 手动输入模式 |
| `--hybrid` | 混合模式 |
| `--persona-batch` | 批量测试多种人设，逗号分隔 |
| `--sim-output` | 模拟测试输出目录 (默认: simulator_output) |
| `--no-eval` | 模拟测试后不运行评估 |

#### 评估与角色参数
| 参数 | 说明 |
|------|------|
| `--evaluate` | 评估对话日志文件 |
| `--list-personas` | 列出所有可用人设 |
| `--generate-personas` | 根据材料智能生成角色 |
| `--num-personas` | 生成角色数量 (默认: 3) |

---

### 八、.env 配置项

```env
# ========== 认证信息（需要从浏览器获取，会过期）==========
PLATFORM_AUTHORIZATION=eyJ...    # JWT Token
PLATFORM_COOKIE=zhs-jt-cas=...   # Cookie

# ========== 项目信息（可通过 --set-project 自动设置）==========
PLATFORM_COURSE_ID=xxx           # 课程ID
PLATFORM_TRAIN_TASK_ID=xxx       # 训练任务ID
PLATFORM_START_NODE_ID=xxx       # 训练开始节点ID
PLATFORM_END_NODE_ID=xxx         # 训练结束节点ID

# ========== 模拟测试配置 ==========
SIMULATOR_API_KEY=xxx            # LLM服务API密钥
SIMULATOR_API_URL=http://llm-service.polymas.com/api/openai/v1/chat/completions
SIMULATOR_SERVICE_CODE=SI_Ability
SIMULATOR_MODEL=claude-sonnet-4-5-20250514   # 学生模拟器和评估器使用的模型
```

---

### 九、目录结构

```
EduFlow/
├── input/                      # 输入文件目录（剧本等）
├── output/                     # 卡片输出目录
├── simulator/                  # 学生模拟测试模块
│   ├── card_loader.py         # 卡片加载器
│   ├── llm_npc.py             # NPC模拟器
│   ├── llm_student.py         # 学生模拟器
│   ├── student_persona.py     # 人设管理与智能生成
│   ├── session_runner.py      # 会话运行器
│   └── evaluator.py           # 评估报告生成器
├── simulator_config/           # 人设配置目录
│   ├── presets/               # 预设人设 (excellent/average/struggling)
│   └── custom/                # 自定义人设和生成的角色
├── simulator_output/           # 模拟测试输出
│   ├── logs/                  # 对话日志 (JSON + Markdown)
│   └── reports/               # 评估报告
└── main.py                     # 主程序入口
```

---

### 十、预设人设说明

| 人设 | 特点 | 适用场景 |
|------|------|---------|
| `excellent` | 理解力强、回答准确、主动深入 | 测试NPC引导深度学习的能力 |
| `average` | 正常水平、偶有疑惑 | 测试NPC常规教学流程 |
| `struggling` | 理解困难、需要引导 | 测试NPC引导和纠错能力 |
