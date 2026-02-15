# EduFlow 示例工作区 (demo)

本工作区用于**演示 EduFlow 各项功能**，包含完整预置文件，可快速体验从剧本解析到卡片生成、闭环验证、闭环优化、评估、注入平台的全流程。

## 目录结构

```
demo/
├── input/                           # 输入
│   └── 示例剧本-课堂演示.md          # 2 阶段简化剧本
├── output/
│   ├── cards_output_demo.md         # 预置教学卡片（2 阶段 A/B 类）
│   ├── optimizer/
│   │   └── trainset.json            # DSPy 训练集
│   └── simulator_output/
│       ├── logs/
│       │   └── session_demo.json    # 仿真会话日志
│       └── reports/
│           ├── evaluation-report-demo.json
│           └── evaluation-report-demo.md   # 评估报告
├── platform_config.json             # 智慧树平台配置模板（需自行填写）
└── README.md                        # 本说明
```

## 功能演示步骤

### 1. 剧本解析

- **Web**：选择工作区 `demo`，在「1. 导入剧本」上传 `input/示例剧本-课堂演示.md`（或选择已解析的剧本重新解析）。
- **CLI**：`python main.py --input "workspaces/demo/input/示例剧本-课堂演示.md" --output "workspaces/demo/output/cards.md"`

解析后会自动更新 `output/optimizer/trainset.json`。

### 2. 生成卡片

- **Web**：解析完成后选择生成框架（如 dspy），点击「生成卡片」。卡片会保存到 `output/cards_output_YYYYMMDD_HHMMSS.md`。
- 本示例已预置 `output/cards_output_demo.md`，可直接用于后续步骤。

### 3. 闭环验证与优化（3a / 3b）

- **3a 闭环运行（单次验证）**  
  - 卡片路径填写：`output/cards_output_demo.md`  
  - 点击「闭环运行」，等待仿真 + 评估完成，可在 `output/simulator_output/` 查看会话日志与评估报告。

- **3b 闭环优化（DSPy 迭代）**  
  - trainset 路径：`output/optimizer/trainset.json`  
  - 点击「闭环优化」，等待进度条完成。优化后的卡片会写入 `output/optimizer/cards_for_eval.md`。

### 4. 评估（高级）

- 若使用外部评估工具，可将评估结果导出为 `output/optimizer/export_score.json` 或 `.md`，供优化器使用。
- 本示例已预置 `output/simulator_output/reports/evaluation-report-demo.json` 作为参考。

### 5. 注入平台

- 将 `platform_config.json` 中的 `course_id`、`train_task_id`、`cookie`、`authorization` 等替换为实际值。
- **Web**：在注入页选择工作区、填写卡片路径（如 `output/cards_output_demo.md`），点击注入。
- **CLI**：`python main.py --inject-only "output/cards_output_demo.md" --workspace demo`

### 6. 仿真侧边栏

- 打开右侧「仿真」侧边栏，可查看项目进度、卡片编辑与试玩、按步骤试玩。
- 卡片路径填写：`output/cards_output_demo.md`，即可在侧边栏中试玩或编辑卡片。

## 注意事项

- 示例剧本仅包含 2 个阶段，便于快速跑通全流程。
- `platform_config.json` 需替换为真实的智慧树平台凭证才能完成注入。
- 闭环优化（DSPy）耗时会随 trainset 大小和轮数增加（约 15–60 分钟）。
