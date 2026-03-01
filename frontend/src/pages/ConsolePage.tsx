import { FormEvent, useEffect, useState } from "react";
import {
    ApiError,
    apiGet,
    apiPostJson,
    apiPostSSE,
    apiRequest,
} from "../utils/api";

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

interface WorkspaceFile {
  name: string;
  path: string;
}

interface FilesResponse {
  files: WorkspaceFile[];
}

interface PersonasResponse {
  presets: string[];
  custom: string[];
}

interface TrainsetFile {
  path: string;
  name: string;
  mtime?: number;
}

interface TrainsetListResponse {
  files: TrainsetFile[];
}

function normalizeCardsPath(p: string): string {
  const s = (p || "").trim();
  return s.startsWith("output/") ? s : s ? `output/${s}` : "";
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

  const [outputFiles, setOutputFiles] = useState<WorkspaceFile[]>([]);
  const [personas, setPersonas] = useState<PersonasResponse | null>(null);
  const [trainsetFiles, setTrainsetFiles] = useState<TrainsetFile[]>([]);
  const [selectedTrainsetPath, setSelectedTrainsetPath] = useState<string>("");
  const [cardsPath, setCardsPath] = useState("");

  // 步骤 3：试玩/模拟
  const [simulating, setSimulating] = useState(false);
  const [simulateResult, setSimulateResult] = useState<unknown>(null);
  const [simulateMessage, setSimulateMessage] = useState<string | null>(null);

  // 步骤 4：评估
  const [evaluating, setEvaluating] = useState(false);
  const [evaluateResult, setEvaluateResult] = useState<unknown>(null);
  const [evaluateMessage, setEvaluateMessage] = useState<string | null>(null);

  // 步骤 5：注入
  const [injectPreview, setInjectPreview] = useState<unknown>(null);
  const [injecting, setInjecting] = useState(false);
  const [injectMessage, setInjectMessage] = useState<string | null>(null);
  const [injectTaskName, setInjectTaskName] = useState("");
  const [injectDescription, setInjectDescription] = useState("");

  // 步骤 6：闭环/优化
  const [closedLoopRunning, setClosedLoopRunning] = useState(false);
  const [closedLoopResult, setClosedLoopResult] = useState<unknown>(null);
  const [closedLoopMessage, setClosedLoopMessage] = useState<string | null>(null);
  const [optimizerRunning, setOptimizerRunning] = useState(false);
  const [optimizerProgress, setOptimizerProgress] = useState("");
  const [optimizerResult, setOptimizerResult] = useState<unknown>(null);
  const [optimizerMessage, setOptimizerMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [filesResp, personasResp, trainsetResp] = await Promise.all([
          apiGet<FilesResponse>("/output/files"),
          apiGet<PersonasResponse>("/personas"),
          apiGet<TrainsetListResponse>("/trainset/list"),
        ]);
        if (!cancelled) {
          setOutputFiles((filesResp?.files as WorkspaceFile[]) || []);
          setPersonas(personasResp || null);
          setTrainsetFiles(trainsetResp?.files || []);
        }
      } catch {
        if (!cancelled) {
          setOutputFiles([]);
          setPersonas(null);
          setTrainsetFiles([]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (generateResult?.output_path) {
      setCardsPath(normalizeCardsPath(generateResult.output_path));
    }
  }, [generateResult?.output_path]);

  const cardOptions = outputFiles.filter(
    (f) => (f.path || "").toLowerCase().endsWith(".md"),
  );
  const personaOptions = [
    ...(personas?.presets || ["excellent", "average", "struggling"]),
    ...(personas?.custom || []),
  ];

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

  async function handleSimulate() {
    const path = normalizeCardsPath(cardsPath);
    if (!path) {
      setSimulateMessage("请选择或输入卡片文件路径。");
      return;
    }
    setSimulating(true);
    setSimulateMessage("正在运行模拟…");
    setSimulateResult(null);
    try {
      const res = await apiPostJson("/simulate/run", {
        cards_path: path,
        persona_id: (document.getElementById("simPersona") as HTMLSelectElement)?.value || "excellent",
        mode: "auto",
        output_dir: "simulator_output",
        run_evaluation: true,
      });
      setSimulateResult(res);
      const ev = (res as { evaluation?: { total_score?: number } })?.evaluation;
      const score = ev?.total_score;
      setSimulateMessage(
        score != null
          ? `模拟完成，评估总分：${score}`
          : "模拟完成",
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setSimulateMessage(err.message);
      } else {
        setSimulateMessage("模拟失败，请稍后重试。");
      }
    } finally {
      setSimulating(false);
    }
  }

  async function handleEvaluateUpload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const input = e.currentTarget.elements.namedItem(
      "log_file",
    ) as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) {
      setEvaluateMessage("请选择会话日志文件（.json 或 .txt）。");
      return;
    }
    const ext = (file.name || "").toLowerCase();
    if (!ext.endsWith(".json") && !ext.endsWith(".txt")) {
      setEvaluateMessage("仅支持 .json 或 .txt 格式。");
      return;
    }
    setEvaluating(true);
    setEvaluateMessage("正在评估…");
    setEvaluateResult(null);
    const form = new FormData();
    form.append("file", file);
    form.append("save_to_export", "true");
    try {
      const res = await apiRequest({
        path: "/evaluate/from-file",
        method: "POST",
        body: form,
      });
      setEvaluateResult(res);
      const total = (res as { total_score?: number })?.total_score;
      setEvaluateMessage(
        total != null ? `评估完成，总分：${total}` : "评估完成",
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setEvaluateMessage(err.message);
      } else {
        setEvaluateMessage("评估失败，请稍后重试。");
      }
    } finally {
      setEvaluating(false);
    }
  }

  async function handleInjectPreview() {
    const path = normalizeCardsPath(cardsPath);
    if (!path) {
      setInjectMessage("请选择或输入卡片文件路径。");
      return;
    }
    setInjectMessage("预览中…");
    setInjectPreview(null);
    try {
      const res = await apiPostJson("/inject/preview", { cards_path: path });
      setInjectPreview(res);
      const d = res as { summary?: string; total_a?: number; total_b?: number };
      setInjectMessage(d.summary || `A类 ${d.total_a ?? 0}，B类 ${d.total_b ?? 0}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setInjectMessage(err.message);
      } else {
        setInjectMessage("预览失败，请稍后重试。");
      }
    }
  }

  async function handleInjectRun() {
    const path = normalizeCardsPath(cardsPath);
    if (!path) {
      setInjectMessage("请选择或输入卡片文件路径。");
      return;
    }
    setInjecting(true);
    setInjectMessage("注入中…");
    try {
      const res = await apiPostJson("/inject/run", {
        cards_path: path,
        task_name: injectTaskName.trim() || null,
        description: injectDescription.trim() || null,
      });
      const d = res as { success?: boolean; message?: string };
      setInjectMessage(d.message || (d.success ? "注入成功" : "注入完成"));
    } catch (err) {
      if (err instanceof ApiError) {
        setInjectMessage(err.message);
      } else {
        setInjectMessage("注入失败，请稍后重试。");
      }
    } finally {
      setInjecting(false);
    }
  }

  async function handleClosedLoop() {
    const path = normalizeCardsPath(cardsPath);
    if (!path) {
      setClosedLoopMessage("请选择或输入卡片文件路径。");
      return;
    }
    setClosedLoopRunning(true);
    setClosedLoopMessage("正在运行闭环（仿真+评估）…");
    setClosedLoopResult(null);
    try {
      const res = await apiPostJson("/closed-loop/run", {
        cards_path: path,
        persona_id: "excellent",
        save_to_export: true,
      });
      setClosedLoopResult(res);
      const total = (res as { total_score?: number })?.total_score;
      setClosedLoopMessage(
        total != null
          ? `闭环完成，评估总分：${total}，已保存至 export_score.json`
          : "闭环完成",
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setClosedLoopMessage(err.message);
      } else {
        setClosedLoopMessage("闭环运行失败，请稍后重试。");
      }
    } finally {
      setClosedLoopRunning(false);
    }
  }

  async function handleOptimizerRun() {
    setOptimizerRunning(true);
    setOptimizerProgress("准备中…");
    setOptimizerResult(null);
    setOptimizerMessage(null);
    try {
      await apiPostSSE(
        "/optimizer/run-stream",
        {
          ...(selectedTrainsetPath ? { trainset_path: selectedTrainsetPath } : {}),
          use_auto_eval: true,
          optimizer_type: "bootstrap",
        },
        {
          onProgress: (d) => {
            setOptimizerProgress(d.message || `${d.percent ?? 0}%`);
          },
          onDone: (d) => {
            setOptimizerResult(d);
            setOptimizerProgress("完成");
            const hint = (d as { hint?: string })?.hint;
            setOptimizerMessage(hint || "优化完成");
          },
          onError: (msg) => {
            setOptimizerMessage(msg);
          },
        },
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setOptimizerMessage(err.message);
      } else {
        setOptimizerMessage("优化失败，请稍后重试。");
      }
    } finally {
      setOptimizerRunning(false);
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
          上传教学剧本，解析为阶段结构并写入 trainset 库，为闭环优化做准备。
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
          在解析基础上使用 LLM 生成 A/B 类教学卡片，写入 output/ 目录。
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
            </div>
          )}
        </div>
      </section>

      <section className="page-section">
        <div className="page-section-title">
          <h2>3. 试玩/模拟</h2>
          <span className="pill">调用 /api/simulate/run</span>
        </div>
        <p className="page-section-desc">
          选择卡片文件，使用 LLM 扮演学生与 NPC 对话，自动评估并生成报告。
        </p>

        <div className="stack-v">
          <label className="field-label" htmlFor="cards-path">
            卡片文件路径
          </label>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input
              id="cards-path"
              type="text"
              className="field-input"
              value={cardsPath}
              onChange={(e) => setCardsPath(e.target.value)}
              placeholder="output/cards_output_xxx.md"
              list="cards-path-options"
              style={{ flex: 1, minWidth: 200 }}
            />
            <datalist id="cards-path-options">
              {cardOptions.map((f) => (
                <option key={f.path} value={f.path.startsWith("output/") ? f.path : `output/${f.path}`} />
              ))}
            </datalist>
          </div>

          <label className="field-label" htmlFor="simPersona">
            学生人设
          </label>
          <select
            id="simPersona"
            className="field-input"
            style={{ maxWidth: 200 }}
          >
            {personaOptions.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>

          <button
            type="button"
            className="btn btn-primary"
            disabled={simulating || !cardsPath}
            onClick={handleSimulate}
          >
            {simulating ? "模拟中…" : "运行模拟"}
          </button>

          {simulateMessage && (
            <div className={"hint" + (simulateResult ? " text-success" : " text-danger")}>
              {simulateMessage}
            </div>
          )}
          {simulateResult && (
            <details className="card-muted" style={{ marginTop: 8 }}>
              <summary>对话与评估详情</summary>
              <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
                {JSON.stringify(simulateResult, null, 2)}
              </pre>
            </details>
          )}
        </div>
      </section>

      <section className="page-section">
        <div className="page-section-title">
          <h2>4. 评估会话日志</h2>
          <span className="pill">调用 /api/evaluate/from-file</span>
        </div>
        <p className="page-section-desc">
          上传已有会话日志（.json 或 .txt）进行多维度评估，可保存为 export_score.json 供优化器使用。
        </p>

        <form onSubmit={handleEvaluateUpload} className="stack-v">
          <label className="field-label" htmlFor="log-file">
            选择会话日志
          </label>
          <input
            id="log-file"
            name="log_file"
            type="file"
            className="field-input"
            accept=".json,.txt"
          />
          <button type="submit" className="btn btn-primary" disabled={evaluating}>
            {evaluating ? "评估中…" : "上传并评估"}
          </button>
        </form>

        {evaluateMessage && (
          <div className={"hint" + (evaluateResult ? " text-success" : " text-danger")}>
            {evaluateMessage}
          </div>
        )}
        {evaluateResult && (
          <details className="card-muted" style={{ marginTop: 8 }}>
            <summary>评估报告</summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
              {JSON.stringify(evaluateResult, null, 2)}
            </pre>
          </details>
        )}
      </section>

      <section className="page-section">
        <div className="page-section-title">
          <h2>5. 注入到平台</h2>
          <span className="pill">调用 /api/inject/preview 与 /api/inject/run</span>
        </div>
        <p className="page-section-desc">
          将卡片推送到智慧树平台。需先在「设置」中配置平台参数。
        </p>

        <div className="stack-v">
          <label className="field-label">卡片文件路径</label>
          <input
            type="text"
            className="field-input"
            value={cardsPath}
            onChange={(e) => setCardsPath(e.target.value)}
            placeholder="output/cards_output_xxx.md"
            list="inject-cards-options"
            style={{ maxWidth: 400 }}
          />
          <datalist id="inject-cards-options">
            {cardOptions.map((f) => (
              <option key={f.path} value={f.path.startsWith("output/") ? f.path : `output/${f.path}`} />
            ))}
          </datalist>

          <label className="field-label" style={{ marginTop: 8 }}>
            任务名称（可选）
          </label>
          <input
            type="text"
            className="field-input"
            value={injectTaskName}
            onChange={(e) => setInjectTaskName(e.target.value)}
            placeholder="例如：自动控制原理实训三"
            style={{ maxWidth: 400 }}
          />

          <label className="field-label" style={{ marginTop: 8 }}>
            任务描述（可选）
          </label>
          <input
            type="text"
            className="field-input"
            value={injectDescription}
            onChange={(e) => setInjectDescription(e.target.value)}
            placeholder="为训练任务补充一句话说明，便于平台展示"
            style={{ maxWidth: 400 }}
          />

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn secondary"
              disabled={!cardsPath}
              onClick={handleInjectPreview}
            >
              预览
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={injecting || !cardsPath}
              onClick={handleInjectRun}
            >
              {injecting ? "注入中…" : "执行注入"}
            </button>
          </div>

          {injectMessage && (
            <div className={"hint" + (injectPreview || !injectMessage.includes("失败") ? " text-success" : " text-danger")}>
              {injectMessage}
            </div>
          )}
          {injectPreview && (
            <details className="card-muted" style={{ marginTop: 8 }}>
              <summary>预览详情</summary>
              <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
                {JSON.stringify(injectPreview, null, 2)}
              </pre>
            </details>
          )}
        </div>
      </section>

      <section className="page-section">
        <div className="page-section-title">
          <h2>6. 闭环与 DSPy 优化</h2>
          <span className="pill">闭环运行 / 优化器</span>
        </div>
        <p className="page-section-desc">
          闭环运行：对卡片执行仿真+评估并保存 export_score.json。DSPy 优化：基于 trainset 迭代优化生成能力（闭环模式自动仿真评估）。
        </p>

        <div className="stack-v">
          <label className="field-label">卡片文件路径（闭环用）</label>
          <input
            type="text"
            className="field-input"
            value={cardsPath}
            onChange={(e) => setCardsPath(e.target.value)}
            placeholder="output/cards_output_xxx.md"
            list="closed-loop-cards-options"
            style={{ maxWidth: 400 }}
          />
          <datalist id="closed-loop-cards-options">
            {cardOptions.map((f) => (
              <option key={f.path} value={f.path.startsWith("output/") ? f.path : `output/${f.path}`} />
            ))}
          </datalist>

          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <div className="stack-v" style={{ flex: 1, minWidth: 200 }}>
              <button
                type="button"
                className="btn btn-primary"
                disabled={closedLoopRunning || !cardsPath}
                onClick={handleClosedLoop}
              >
                {closedLoopRunning ? "运行中…" : "闭环运行"}
              </button>
              {closedLoopMessage && (
                <div className={"hint" + (closedLoopResult ? " text-success" : " text-danger")}>
                  {closedLoopMessage}
                </div>
              )}
            </div>

            <div className="stack-v" style={{ flex: 1, minWidth: 200 }}>
              <label className="field-label" style={{ marginBottom: 4 }}>
                Trainset（不选则使用库中最新一份）
              </label>
              <select
                className="field-input"
                value={selectedTrainsetPath}
                onChange={(e) => setSelectedTrainsetPath(e.target.value)}
                style={{ maxWidth: 400 }}
              >
                <option value="">默认（最新）</option>
                {trainsetFiles.map((f) => (
                  <option key={f.path} value={f.path}>
                    {f.name || f.path}
                  </option>
                ))}
              </select>
              <p className="hint" style={{ marginTop: 8, marginBottom: 8 }}>
                基于 trainset 迭代优化，闭环模式自动用三档人设（优秀/一般/较差）并行评估取均值。
              </p>
              <button
                type="button"
                className="btn secondary"
                disabled={optimizerRunning}
                onClick={handleOptimizerRun}
              >
                {optimizerRunning ? "优化中…" : "运行 DSPy 优化"}
              </button>
              {optimizerRunning && (
                <div className="hint">{optimizerProgress}</div>
              )}
              {optimizerMessage && (
                <div className={"hint" + (optimizerResult ? " text-success" : " text-danger")}>
                  {optimizerMessage}
                </div>
              )}
            </div>
          </div>

          {closedLoopResult && (
            <details className="card-muted" style={{ marginTop: 8 }}>
              <summary>闭环结果</summary>
              <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
                {JSON.stringify(closedLoopResult, null, 2)}
              </pre>
            </details>
          )}
          {optimizerResult && (
            <details className="card-muted" style={{ marginTop: 8 }}>
              <summary>优化器结果</summary>
              <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
                {JSON.stringify(optimizerResult, null, 2)}
              </pre>
            </details>
          )}
        </div>
      </section>
    </>
  );
};
