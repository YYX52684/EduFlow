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

### 三、项目配置命令

| 命令 | 说明 |
|------|------|
| `python main.py --set-project "URL"` | 从页面URL自动提取课程ID和任务ID |

**示例：**
```bash
python main.py --set-project "https://hike-teaching-center.polymas.com/tch-hike/agent-course-full/5vamqyyzvecvnoY4NKa4/ability-training/create?trainTaskId=WwD67NeKNVsyMrpypxkJ"
```

---

### 四、典型工作流程

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

---

### 五、参数速查表

| 参数 | 简写 | 说明 |
|------|------|------|
| `--input` | `-i` | 输入剧本文件路径 |
| `--output` | `-o` | 输出文件路径 |
| `--preview` | `-p` | 预览剧本结构 |
| `--verbose` | `-v` | 详细输出 |
| `--inject` | | 生成后注入平台 |
| `--inject-only` | | 仅注入已有文件 |
| `--preview-inject` | | 预览注入内容 |
| `--set-project` | | 从URL设置项目配置 |

---

### 六、.env 配置项

```env
# 认证信息（需要从浏览器获取，会过期）
PLATFORM_AUTHORIZATION=eyJ...    # JWT Token
PLATFORM_COOKIE=zhs-jt-cas=...   # Cookie

# 项目信息（可通过 --set-project 自动设置）
PLATFORM_COURSE_ID=xxx           # 课程ID
PLATFORM_TRAIN_TASK_ID=xxx       # 训练任务ID
```