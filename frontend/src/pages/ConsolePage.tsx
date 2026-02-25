import { FormEvent, useState } from "react";
import { apiRequest, apiPostJson, ApiError } from "../utils/api";

interface UploadResponse {
  filename: string;
  full_content_length: number;
  stages_count: number;
  stages: unknown[];
  full_content: string;
  trainset_path?: string;
  trainset_count?: number;
  truncated_note?: string;
}

interface GenerateResponse {
  output_path: string;
  output_filename: string;
  full_path: string;
  workspace_id: string;
  stages_count: number;
  cards_count: number;
  content_preview?: string;
}

export const ConsolePage = () => {
  const [analyzing, setAnalyzing] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [analyzeMessage, setAnalyzeMessage] = useState<string | null>(null);

  const [generating, setGenerating] = useState(false);
  const [generateResult, setGenerateResult] = useState<GenerateResponse | null>(
    null,
  );
  const [generateMessage, setGenerateMessage] = useState<string | null>(null);

  async function handleUpload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const input = e.currentTarget.elements.namedItem(
      "script_file",
    ) as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) {
      setAnalyzeMessage("请先选择一个剧本文件。");
      return;
    }
    const form = new FormData();
    form.append("file", file);

    setAnalyzing(true);
    setAnalyzeMessage(null);
    setUploadResult(null);
    setGenerateResult(null);
    setGenerateMessage(null);
    try {
      const data = await apiRequest<UploadResponse>({
        path: "/script/upload",
        method: "POST",
        body: form,
      });
      setUploadResult(data);
      const note = data.truncated_note ? `（${data.truncated_note}）` : "";
      const trainsetInfo =
        data.trainset_count != null
          ? `；Trainset 已更新（共 ${data.trainset_count} 条），闭环优化时将使用。`
          : "";
      setAnalyzeMessage(
        `已解析「${data.filename}」：共 ${data.stages_count} 个阶段，原文长度 ${data.full_content_length} 字${note}${trainsetInfo}`,
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setAnalyzeMessage(err.message);
      } else {
        setAnalyzeMessage("解析失败，请稍后重试。");
      }
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleGenerate() {
    if (!uploadResult) {
      setGenerateMessage("请先上传并解析剧本。");
      return;
    }
    setGenerating(true);
    setGenerateMessage("正在生成卡片…");
    setGenerateResult(null);
    try {
      const res = await apiPostJson<GenerateResponse>("/cards/generate", {
        full_content: uploadResult.full_content,
        stages: uploadResult.stages,
        framework_id: "dspy",
        source_filename: uploadResult.filename,
      });
      setGenerateResult(res);
      setGenerateMessage(
        `已生成卡片：${res.output_path}（阶段数 ${res.stages_count}，估算卡片数 ${res.cards_count}）`,
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setGenerateMessage(err.message);
      } else {
        setGenerateMessage("生成失败，请稍后重试。");
      }
    } finally {
      setGenerating(false);
    }
  }

  return (
    <>
      <section className="page-section">
        <div className="page-section-title">
          <h2>1. 剧本上传与解析</h2>
          <span className="pill">支持 .md / .docx / .doc / .pdf</span>
        </div>
        <p className="page-section-desc">
          与旧版左上主流程等价：上传教学剧本→调用 /api/script/upload 解析→可选写入
          trainset.json，为闭环优化做准备。
        </p>

        <form onSubmit={handleUpload} className="stack-v">
          <label className="field-label" htmlFor="script-file">
            选择剧本文件
          </label>
          <input
            id="script-file"
            name="script_file"
            type="file"
            className="field-input"
            accept=".md,.docx,.doc,.pdf"
          />
          <button type="submit" className="btn btn-primary" disabled={analyzing}>
            {analyzing ? "解析中…" : "上传并解析"}
          </button>
        </form>

        {analyzeMessage && (
          <div
            className={
              "hint" + (uploadResult ? " text-success" : " text-danger")
            }
            style={{ marginTop: 8 }}
          >
            {analyzeMessage}
          </div>
        )}
      </section>

      <section className="page-section">
        <div className="page-section-title">
          <h2>2. 生成教学卡片</h2>
          <span className="pill">调用 /api/cards/generate</span>
        </div>
        <p className="page-section-desc">
          在上一阶段解析出的结构基础上，使用当前工作区的 LLM 配置生成 A/B 类教学卡片，
          并写入当前工作区的 output/ 目录。
        </p>

        <div className="stack-v">
          <button
            type="button"
            className="btn btn-primary"
            disabled={generating || !uploadResult}
            onClick={handleGenerate}
          >
            {generating ? "生成中…" : "生成卡片 Markdown"}
          </button>

          {generateMessage && (
            <div
              className={
                "hint" +
                (generateResult && generateResult.output_path
                  ? " text-success"
                  : " text-danger")
              }
            >
              {generateMessage}
            </div>
          )}

          {generateResult && (
            <div className="card-muted">
              <div>
                生成文件路径：
                <code>{generateResult.output_path}</code>
              </div>
              {generateResult.content_preview && (
                <details style={{ marginTop: 6 }}>
                  <summary className="hint">预览前 2k 字</summary>
                  <pre style={{ whiteSpace: "pre-wrap" }}>
                    {generateResult.content_preview}
                  </pre>
                </details>
              )}
              <p className="hint" style={{ marginTop: 6 }}>
                你可以在「工作区」页面查看 output/ 下的所有文件，或继续使用旧版界面对卡片做
                预览与编辑。
              </p>
            </div>
          )}
        </div>
      </section>
    </>
  );
};

