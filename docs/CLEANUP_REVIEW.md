# 不必要的注释、.md 文件与 UI 内容审查

## 一、.md 文件

### 建议归并到 docs/（减少根目录杂乱）

| 文件 | 说明 | 建议 |
|------|------|------|
| **错误文档汇总.md** | 故障排查记录，有参考价值 | 移至 `docs/troubleshooting.md`，便于与架构/工作流文档统一 |
| **WORKFLOW.md** | 完整工作流程说明 | 移至 `docs/workflow.md` |
| **Operations.md** | CLI 操作指令总结 | 移至 `docs/operations.md` |

### 建议保留位置

- **README.md**、**DEPLOY.md**：项目入口与部署说明，保留在根目录。
- **docs/architecture.md**、**docs/REDUNDANCY_REVIEW.md**：已在 docs，保留。
- **workspaces/README.md**、**workspaces/demo/README.md**：工作区说明，保留。
- **templates/*.md**：模板资源，保留。

### 无需纳入版本控制的目录

- **.VSCodeCounter/**：VSCode 统计插件生成，建议加入 `.gitignore`，不提交。

### 用户/生成数据（非文档）

- `workspaces/*/output/*.md`、`output/*.md`、`input/*.md` 等为运行产物或用户数据，按需在 `.gitignore` 中忽略，不视为「冗余文档」。

---

## 二、代码注释

### 可删除或简化的注释

| 位置 | 内容 | 建议 |
|------|------|------|
| **simulator/card_loader.py** 约 269–272 行 | `# TODO: 需要抓取教师端API来实现` 及下方 3 行「需要的API」列表 | 与 `raise NotImplementedError` 的文案重复，可删去注释块，仅保留异常说明 |

### 建议保留的注释

- **api_platform/api_client.py**：`# 注意：isDefault=1…`、`# 最后一张B类卡片…` 等为业务逻辑说明，保留。
- **config.py**、**main.py** 等处的配置项/参数说明：保留。
- **generators/** 内与 JSON 解析、钩子相关的注释：保留。

---

## 三、UI 无关或易误导内容

### 占位符（placeholder）

| 位置 | 当前 placeholder | 说明 | 建议 |
|------|------------------|------|------|
| 注入「卡片文件路径」 | `output/cards_output_20260202_170046.md` | 带具体日期，易被误认为固定路径 | 改为 `output/cards_output_xxx.md` |
| 仿真侧边栏「卡片文件路径」 | `output/cards_output_20260202_170046.md` | 同上 | 改为 `output/cards_output_xxx.md` |
| 按步骤仿真「路径」 | `output/cards_output_xxx.md` | 已为通用示例 | 无需修改 |

其余 placeholder（如「请输入用户名」「留空则保持已保存的值」等）为正常提示，保留。

### HTML 注释

- `<!-- 收藏夹与标签页图标 -->`、`<!-- 链接预览（Edge/社交分享等） -->` 有助于维护，保留。

---

## 四、已执行的清理项（与本审查同步）

- 将 **错误文档汇总.md** → **docs/troubleshooting.md**，**WORKFLOW.md** → **docs/workflow.md**，**Operations.md** → **docs/operations.md**；根目录原文件已删除。
- 在 **.gitignore** 中增加 **.VSCodeCounter/**。
- **web/static/index.html** 中两处 `placeholder="output/cards_output_20260202_170046.md"` 改为 `output/cards_output_xxx.md`。
- **simulator/card_loader.py** 中删除与 `NotImplementedError` 文案重复的 TODO 注释块（保留异常说明）。
