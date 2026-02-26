# EduFlow 智慧树卡片注入 - Chrome 插件

任意页面均可打开扩展；拖入 .md 剧本 → 生成卡片 → 在智慧树配置页点击「注入平台」即可完成注入。无需配置 Cookie/课程/任务/节点 ID。

## 使用前提

- **默认**：扩展自动使用 [eduflows.cn](https://eduflows.cn) 后端（DSPy 生成），无需配置。
- **备选**：若后端不可用，可展开「LLM 直连配置」填写 API Key 作为备用。
- 注入前需打开**智慧树能力训练配置页**（某门课的卡片编辑页），扩展会自动检测当前标签页是否为该页面。

## 安装

1. Chrome 地址栏输入 `chrome://extensions/`，打开「扩展程序」。
2. 开启右上角「开发者模式」。
3. 点击「加载已解压的扩展程序」，选择本项目的 `extension` 目录。

## 使用步骤

1. **打开扩展**：点击浏览器工具栏的扩展图标，打开侧边栏（任意页面均可打开）。
2. **确认当前页**：侧边栏顶部会显示「当前页面：智慧树能力训练配置页」或「当前页面不是智慧树配置页」。若尚未打开配置页，请先打开智慧树能力训练配置页。
3. **（可选）**：默认使用 eduflows.cn 生成，无需配置。若需本地部署或后端不可用，可展开「EduFlow 后端」修改地址，或填写「LLM 直连」作为备用。
4. **拖入文件**：将 **.md / .docx / .pdf** 剧本拖入侧边栏的拖放区，或点击选择文件。支持 .docx 和 .pdf 需在 `extension/lib/` 下放入对应库（见下方「可选：.docx / .pdf 支持」）。
5. **生成卡片**：点击「生成卡片」，等待分幕与卡片生成完成。
6. **注入平台**：确保当前标签页为智慧树能力训练配置页，点击「注入平台」。完成后刷新画布即可看到新卡片。

## 默认 LLM 配置（与 .env 一致）

- **API 地址**：`http://llm-service.polymas.com/api/openai/v1`
- **模型**：`Doubao-1.5-pro-32k`
- **Service Code**：`SI_Ability`
- **API Key**：需在扩展侧边栏中填写（与 `.env` 中 `LLM_API_KEY` 一致）。

## 可选：.docx / .pdf 支持

- 仅 **.md** 时无需额外文件。
- **.docx**：将 [mammoth.browser.min.js](https://cdnjs.cloudflare.com/ajax/libs/mammoth/1.6.0/mammoth.browser.min.js) 下载并保存为 `extension/lib/mammoth.min.js`，重新加载扩展即可。
- **.pdf**：将 PDF.js 的浏览器构建（如 `pdf.min.js`）放入 `extension/lib/pdf.min.js` 并重新加载扩展。具体用法见 `extension/lib/README.md`。

## 文件说明

- `manifest.json` - 插件配置与权限（含 sidePanel）。
- `background.js` - 认证、智慧树 API、LLM 调用、当前标签页检测。
- `sidepanel.html` / `sidepanel.js` / `sidepanel.css` - 侧边栏 UI（拖入文件、生成卡片、注入平台）。
- `content.js` - 仅在智慧树配置页运行，响应「注入平台」并执行注入。
