# workspaces 工作区目录

每个子目录对应一个**项目**（工作区），用**项目名**作为文件夹名，便于识别。

## 推荐结构（可读项目名）

```
workspaces/
  编译原理/          ← 项目名，在 Web 中打开 /w/编译原理
    input/           ← 原始文档（.docx / .md / .pdf）
    output/          ← 生成的卡片、trainset、优化结果
  自动控制/          ← 另一个项目
    input/
    output/
```

- 在浏览器访问：`/w/编译原理` 或在前端输入「编译原理」点「打开项目」
- 文件路径即：`workspaces/编译原理/input/编译原理.docx`
- **命令行统一**：`python main.py --workspace 编译原理 --input 编译原理.docx`、`python run_optimizer.py --workspace 编译原理` 会使用同一套目录，与 Web 一致。

## 旧目录（随机 id）

若看到 `51e28027972a`、`be4c1a3eedee` 等随机 id 目录，是旧版生成的。可以：

- 继续用：在浏览器打开 `/w/51e28027972a` 仍可访问
- 迁移到可读名：把该目录下 `input/`、`output/` 内容复制到 `workspaces/编译原理/` 下，之后用「编译原理」即可

## 示例

`编译原理/` 下已放好空的 input、output 和本说明，可直接在 Web 中打开「编译原理」项目使用。
