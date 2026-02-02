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

### 五（续）、DSPy 优化与外部评估

使用**外部平台的导出文件**作为评分指标，对 DSPy 卡片生成器进行优化（如 BootstrapFewShot）。

| 命令 | 说明 |
|------|------|
| `python main.py --build-trainset "trainset.json" -i "剧本.md"` | 从单个剧本文件构建 trainset 并保存为 JSON |
| `python main.py --build-trainset "trainset.json" -i "input/剧本目录/"` | 从目录下所有 .md/.docx/.pdf 构建 trainset |
| `python main.py --validate-trainset "trainset.json"` | 校验 trainset 结构与评估标准对齐（见下方「Trainset 与评估标准」） |
| `python main.py --optimize-dspy --trainset "trainset.json"` | 运行 DSPy 优化（需先有 trainset 和外部评估导出文件） |
| `python main.py --optimize-dspy --trainset "trainset.json" --export-file "score.json"` | 指定外部评估导出文件路径 |
| `python main.py --optimize-dspy --trainset "trainset.json" --cards-output "cards.md"` | 指定优化时生成卡片的输出路径 |

**外部评估导出文件格式约定**

- **JSON**：至少包含一个数字类型的总分字段。默认读取键 `total_score`，可与项目内评估器 `EvaluationReport.to_dict()` 兼容。例如：`{"total_score": 85.5}`。键名可通过配置 `DSPY_JSON_SCORE_KEY` 或 `--export-file` 同目录下的解析配置修改。
- **CSV**：若为表格，需约定「总分」列名或列索引，在配置中指定 `DSPY_CSV_SCORE_COLUMN` 或列索引。
- 若平台导出格式不同，可在 `generators/external_metric.py` 中配置 `parser="custom"` 并传入自定义解析函数。

**Trainset 与评估标准**

trainset 用于 DSPy 优化和卡片生成，要**符合外部评估标准**，需同时满足：

1. **结构**：每条样本含 `full_script`（完整剧本文本）、`stages`（阶段列表）；每个 stage 含 `id, title, description, role, task, key_points, content_excerpt`（与 ContentSplitter 输出一致）。缺字段会导致生成或评估失败。
2. **内容对齐**：外部评估会看「目标达成度」「知识点覆盖率」「环节准出」等维度，这些维度依赖剧本中的**任务目标**和**评分标准**。建议 `full_script` 中保留剧本原有的「任务目标」「评分标准」等段落，这样生成的卡片和对话才有明确的评估依据；各 stage 的 `task`、`key_points` 应覆盖该阶段要考察的知识点或能力，便于环节准出检查有据可依。

运行 `python main.py --validate-trainset "output/optimizer/trainset_xxx.json"` 会做结构校验，并对缺少「任务目标」「评分标准」等给出建议（不强制，仅提示）。

**推荐流程：不断优化 DSPy 生成器**

1. 构建 trainset：`python main.py --build-trainset "output/optimizer/trainset.json" -i "input/剧本目录/" -v`
2. 运行优化：`python main.py --optimize-dspy --trainset "output/optimizer/trainset.json"`
3. 每轮优化时，脚本会把当前生成的卡片写入 `output/optimizer/cards_for_eval.md`，并提示：「请使用外部平台对上述卡片进行评估，并将结果导出到」`output/optimizer/export_score.json`。
4. 在外部平台完成评估后，将结果导出到约定路径（同上），再继续优化（或下一轮由优化器自动读分）。

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

#### 流程C：DSPy 不断优化（使用外部评估）
```bash
# 1. 从剧本构建 trainset
python main.py --build-trainset "./output/optimizer/trainset.json" -i "./input/剧本目录/" -v

# 2. 运行 DSPy 优化（需已安装 dspy-ai）
python main.py --optimize-dspy --trainset "./output/optimizer/trainset.json"

# 3. 按提示：用外部平台对 output/optimizer/cards_for_eval.md 评估，并导出到 output/optimizer/export_score.json
# 4. 优化器会读取导出文件中的分数并继续；可多轮迭代
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

#### DSPy 优化参数
| 参数 | 说明 |
|------|------|
| `--optimize-dspy` | 运行 DSPy 生成器优化（使用外部评估导出文件作为指标） |
| `--trainset` | trainset JSON 路径（用于 --optimize-dspy） |
| `--devset` | 可选 devset JSON 路径 |
| `--build-trainset` | 从剧本文件或目录构建 trainset 并保存为 JSON（需配合 -i 指定数据来源） |
| `--cards-output` | 优化时生成卡片的输出路径 |
| `--export-file` | 外部评估导出文件路径（优化时读取分数） |
| `--optimizer` | 优化器类型：bootstrap / mipro（默认: bootstrap） |
| `--max-rounds` | Bootstrap 最大轮数 |

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

# ========== DSPy 优化与外部评估 ==========
DSPY_EXPORT_FILE=output/optimizer/export_score.json   # 外部评估导出文件路径
DSPY_EXPORT_PARSER=json                               # 解析器: json / csv / custom
DSPY_JSON_SCORE_KEY=total_score                       # JSON 分数字段名
DSPY_CARDS_OUTPUT=output/optimizer/cards_for_eval.md # 优化时生成卡片输出路径
DSPY_OPTIMIZER=bootstrap                              # 优化器: bootstrap / mipro
DSPY_MAX_ROUNDS=1                                     # Bootstrap 轮数
DSPY_MAX_BOOTSTRAPPED_DEMOS=4                         # 最大 bootstrap 示例数
```

---

### 九、目录结构

```
EduFlow/
├── input/                      # 输入文件目录（剧本等）
├── output/                     # 卡片输出目录
│   └── optimizer/              # DSPy 优化：生成卡片与外部评估导出文件约定路径
├── generators/                  # 卡片生成与优化
│   ├── external_metric.py     # 外部评估指标适配（从导出文件解析分数）
│   ├── trainset_builder.py     # Trainset 构建与加载
│   ├── dspy_optimizer.py       # DSPy 优化封装（BootstrapFewShot 等）
│   └── dspy_card_generator.py  # DSPy 卡片生成器
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
