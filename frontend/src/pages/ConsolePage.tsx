import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
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

interface UploadBatchItem extends UploadResponse {
  index: number;
  success: boolean;
  error?: string;
}

interface UploadBatchResponse {
  results: UploadBatchItem[];
  total_count: number;
  success_count: number;
  failure_count: number;
  max_concurrency: number;
}

interface GenerateBatchItem extends Partial<GenerateResponse> {
  index: number;
  success: boolean;
  source_filename?: string;
  error?: string;
}

interface GenerateBatchResponse {
  results: GenerateBatchItem[];
  total_count: number;
  success_count: number;
  failure_count: number;
  max_concurrency: number;
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

interface AuthMeResponse {
  user?: {
    is_optimizer_admin?: boolean;
  };
}

function normalizeCardsPath(p: string): string {
  const s = (p || "").trim();
  return s.startsWith("output/") ? s : s ? `output/${s}` : "";
}

export const ConsolePage = () => {
  const [analyzing, setAnalyzing] = useState(false);
  const [selectedScriptFiles, setSelectedScriptFiles] = useState<File[]>([]);
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [uploadResults, setUploadResults] = useState<UploadBatchItem[]>([]);
  const [analyzeMessage, setAnalyzeMessage] = useState<string | null>(null);
  const [personaGenerating, setPersonaGenerating] = useState(false);
  const [personaGenerateMessage, setPersonaGenerateMessage] = useState<string | null>(null);

  const [generating, setGenerating] = useState(false);
  const [generateResult, setGenerateResult] = useState<GenerateResponse | null>(
    null,
  );
  const [generateResults, setGenerateResults] = useState<GenerateBatchItem[]>([]);
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

  // 步骤 6：闭环/优化
  const [closedLoopRunning, setClosedLoopRunning] = useState(false);
  const [closedLoopResult, setClosedLoopResult] = useState<unknown>(null);
  const [closedLoopMessage, setClosedLoopMessage] = useState<string | null>(null);
  const [optimizerRunning, setOptimizerRunning] = useState(false);
  const [optimizerProgress, setOptimizerProgress] = useState("");
  const [optimizerResult, setOptimizerResult] = useState<unknown>(null);
  const [optimizerMessage, setOptimizerMessage] = useState<string | null>(null);
  const [isOptimizerAdmin, setIsOptimizerAdmin] = useState(false);
  const [optimizerType, setOptimizerType] = useState<"bootstrap" | "mipro">("bootstrap");
  const [optimizerPersonaId, setOptimizerPersonaId] = useState("excellent");
  const [optimizerRoundsMode, setOptimizerRoundsMode] = useState<"default" | "custom">("default");
  const [optimizerMaxRoundsInput, setOptimizerMaxRoundsInput] = useState("1");
  const [optimizerNoCache, setOptimizerNoCache] = useState(false);

  async function refreshConsoleData() {
    const [filesResp, personasResp, trainsetResp] = await Promise.all([
      apiGet<FilesResponse>("/output/files"),
      apiGet<PersonasResponse>("/personas"),
      apiGet<TrainsetListResponse>("/trainset/list"),
    ]);
    setOutputFiles((filesResp?.files as WorkspaceFile[]) || []);
    setPersonas(personasResp || null);
    setTrainsetFiles(trainsetResp?.files || []);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [filesResp, personasResp, trainsetResp, meResp] = await Promise.all([
          apiGet<FilesResponse>("/output/files"),
          apiGet<PersonasResponse>("/personas"),
          apiGet<TrainsetListResponse>("/trainset/list"),
          apiGet<AuthMeResponse>("/auth/me"),
        ]);
        if (!cancelled) {
          setOutputFiles((filesResp?.files as WorkspaceFile[]) || []);
          setPersonas(personasResp || null);
          setTrainsetFiles(trainsetResp?.files || []);
          setIsOptimizerAdmin(!!meResp?.user?.is_optimizer_admin);
        }
      } catch {
        if (!cancelled) {
          setOutputFiles([]);
          setPersonas(null);
          setTrainsetFiles([]);
          setIsOptimizerAdmin(false);
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

  useEffect(() => {
    if (!personaOptions.includes(optimizerPersonaId)) {
      setOptimizerPersonaId(personaOptions[0] || "excellent");
    }
  }, [optimizerPersonaId, personaOptions]);

  async function handleUpload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const input = e.currentTarget.elements.namedItem(
      "script_file",
    ) as HTMLInputElement | null;
    const files = Array.from(input?.files || []);
    if (!files.length) {
      setAnalyzeMessage("请先选择至少一个剧本文件。");
      return;
    }
    setSelectedScriptFiles(files);
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    if (files.length > 1) {
      form.append("max_concurrency", String(Math.min(files.length, 3)));
    }

    setAnalyzing(true);
    setAnalyzeMessage(null);
    setUploadResult(null);
    setUploadResults([]);
    setGenerateResult(null);
    setGenerateResults([]);
    setGenerateMessage(null);
    setPersonaGenerateMessage(null);
    try {
      const data = await apiRequest<UploadBatchResponse>({
        path: "/script/upload-batch",
        method: "POST",
        body: form,
      });
      const results = data.results || [];
      const successItems = results.filter(
        (item) => item.success && item.full_content && item.stages_count > 0,
      );
      setUploadResults(results);
      setUploadResult(successItems[0] || null);
      const successCount = data.success_count ?? successItems.length;
      const failureCount = data.failure_count ?? Math.max(0, results.length - successCount);
      setAnalyzeMessage(
        `批量解析完成：成功 ${successCount} 个，失败 ${failureCount} 个。`,
      );
      if (successCount > 0) {
        await refreshConsoleData();
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setAnalyzeMessage(err.message);
      } else {
        setAnalyzeMessage("批量解析失败，请稍后重试。");
      }
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleGeneratePersonas() {
    if (selectedScriptFiles.length !== 1) {
      setPersonaGenerateMessage("请先只选择一个剧本文件，再生成人设。");
      return;
    }
    setPersonaGenerating(true);
    setPersonaGenerateMessage("正在根据剧本生成学生人设…");
    try {
      const form = new FormData();
      form.append("file", selectedScriptFiles[0]);
      form.append("num_personas", "3");
      const data = await apiRequest<{ count?: number }>({
        path: "/personas/generate",
        method: "POST",
        body: form,
      });
      setPersonaGenerateMessage(`已生成 ${data.count ?? 0} 个人设，并已写入人设库。`);
      await refreshConsoleData();
    } catch (err) {
      if (err instanceof ApiError) {
        setPersonaGenerateMessage(err.message);
      } else {
        setPersonaGenerateMessage("生成人设失败，请稍后重试。");
      }
    } finally {
      setPersonaGenerating(false);
    }
  }

  async function handleGenerate() {
    const validItems = uploadResults.filter(
      (item) => item.success && item.full_content && item.stages && item.stages.length,
    );
    if (!validItems.length) {
      setGenerateMessage("请先上传并解析至少一个可用剧本。");
      return;
    }
    setGenerating(true);
    setGenerateMessage(`正在并发生成 ${validItems.length} 份卡片…`);
    setGenerateResult(null);
    setGenerateResults([]);
    try {
      const res = await apiPostJson<GenerateBatchResponse>("/cards/generate-batch", {
        items: validItems.map((item) => ({
          full_content: item.full_content,
          stages: item.stages,
          framework_id: "dspy",
          source_filename: item.filename,
        })),
        max_concurrency: validItems.length,
      });
      const results = res.results || [];
      const successItems = results.filter(
        (item) => item.success && item.output_path,
      );
      setGenerateResults(results);
      setGenerateResult((successItems[0] as GenerateResponse | undefined) || null);
      const firstOutputPath = successItems[0]?.output_path;
      if (firstOutputPath) {
        setCardsPath(normalizeCardsPath(firstOutputPath));
      }
      setGenerateMessage(
        `批量生成完成：成功 ${res.success_count ?? successItems.length} 个，失败 ${res.failure_count ?? Math.max(0, results.length - successItems.length)} 个。`,
      );
      if (results.length > 0) {
        await refreshConsoleData();
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setGenerateMessage(err.message);
      } else {
        setGenerateMessage("批量生成失败，请稍后重试。");
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
          optimizer_type: optimizerType,
          persona_id: optimizerPersonaId || "excellent",
          max_rounds:
            optimizerRoundsMode === "custom"
              ? Math.max(1, parseInt(optimizerMaxRoundsInput || "1", 10) || 1)
              : null,
          no_cache: optimizerNoCache,
          use_auto_eval: true,
        },
        {
          onProgress: (d) => {
            setOptimizerProgress(d.message || `${d.percent ?? 0}%`);
          },
          onDone: (d) => {
            setOptimizerResult(d);
            setOptimizerProgress("完成");
            const hint = (d as { hint?: string })?.hint;
            const cacheHit = !!(d as { cache_hit?: boolean })?.cache_hit;
            setOptimizerMessage(hint || (cacheHit ? "命中缓存，未重跑优化" : "优化完成"));
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
          <span className="pill">支持 .md / .docx / .doc / .pdf；支持批量</span>
        </div>
        <p className="page-section-desc">
          一次可选择多个教学剧本，批量解析为阶段结构并写入 trainset 库，为后续并发生成卡片做准备。
        </p>

        <form onSubmit={handleUpload} className="stack-v">
          <label className="field-label" htmlFor="script-file">
            选择一个或多个剧本文件
          </label>
          <input
            id="script-file"
            name="script_file"
            type="file"
            className="field-input"
            accept=".md,.docx,.doc,.pdf"
            multiple
            onChange={(e) =>
              setSelectedScriptFiles(Array.from(e.target.files || []))
            }
          />
          {selectedScriptFiles.length > 0 && (
            <div className="hint">
              已选择 {selectedScriptFiles.length} 个文件
              {selectedScriptFiles.length === 1
                ? `：${selectedScriptFiles[0].name}`
                : "，解析后可并发生成卡片。"}
            </div>
          )}
          <div className="stack-h">
            <button type="submit" className="btn btn-primary" disabled={analyzing}>
              {analyzing ? "解析中…" : "上传并解析"}
            </button>
            <button
              type="button"
              className="btn secondary"
              disabled={personaGenerating || selectedScriptFiles.length !== 1}
              onClick={handleGeneratePersonas}
            >
              {personaGenerating ? "生成人设中…" : "根据单份剧本生成人设"}
            </button>
          </div>
        </form>

        {analyzeMessage && (
          <div
            className={
              "hint" +
              (uploadResults.some((item) => item.success)
                ? " text-success"
                : " text-danger")
            }
            style={{ marginTop: 8 }}
          >
            {analyzeMessage}
          </div>
        )}

        {personaGenerateMessage && (
          <div
            className={
              "hint" +
              (personaGenerateMessage.includes("已生成")
                ? " text-success"
                : " text-danger")
            }
          >
            {personaGenerateMessage}
          </div>
        )}

        {uploadResults.length > 0 && (
          <div className="stack-v" style={{ marginTop: 8 }}>
            {uploadResults.map((item) => (
              <div key={`${item.index}-${item.filename}`} className="card-muted">
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <span style={{ wordBreak: "break-word" }}>{item.filename}</span>
                  <strong
                    style={{
                      color: item.success ? "var(--accent-strong)" : "#b2523c",
                    }}
                  >
                    {item.success ? "解析成功" : "解析失败"}
                  </strong>
                </div>
                {item.success ? (
                  <div className="hint" style={{ marginTop: 6 }}>
                    阶段数：{item.stages_count}；原文长度：{item.full_content_length} 字
                  </div>
                ) : (
                  <div className="hint text-danger" style={{ marginTop: 6 }}>
                    {item.error || "解析失败"}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="page-section">
        <div className="page-section-title">
          <h2>2. 批量生成教学卡片</h2>
          <span className="pill">调用 /api/cards/generate-batch</span>
        </div>
        <p className="page-section-desc">
          在解析基础上并发生成多份 A/B 类教学卡片，输出文件默认命名为 `cards_文件名.md`。
        </p>

        <div className="stack-v">
          <button
            type="button"
            className="btn btn-primary"
            disabled={
              generating ||
              !uploadResults.some(
                (item) => item.success && item.stages && item.stages.length,
              )
            }
            onClick={handleGenerate}
          >
            {generating ? "批量生成中…" : "并发生成卡片 Markdown"}
          </button>

          {generateMessage && (
            <div
              className={
                "hint" +
                (generateResults.some((item) => item.success)
                  ? " text-success"
                  : " text-danger")
              }
            >
              {generateMessage}
            </div>
          )}

          {generateResults.length > 0 && (
            <div className="stack-v">
              {generateResults.map((item, idx) => (
                <div
                  key={`${item.index}-${item.source_filename || idx}`}
                  className="card-muted"
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <span style={{ wordBreak: "break-word" }}>
                      {item.source_filename || `文件 ${idx + 1}`}
                    </span>
                    <strong
                      style={{
                        color: item.success ? "var(--accent-strong)" : "#b2523c",
                      }}
                    >
                      {item.success ? "生成成功" : "生成失败"}
                    </strong>
                  </div>
                  {item.success && item.output_path ? (
                    <div className="hint" style={{ marginTop: 6 }}>
                      输出路径：<code>{item.output_path}</code>
                      {" · "}
                      <Link
                        to={`/workspace?kind=output&open=${encodeURIComponent(item.output_path)}`}
                      >
                        打开并编辑
                      </Link>
                    </div>
                  ) : (
                    <div className="hint text-danger" style={{ marginTop: 6 }}>
                      {item.error || "生成失败"}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {generateResult && (
            <div className="card-muted">
              <div>
                默认选中的卡片路径：
                <code>{generateResult.output_path}</code>
                {" · "}
                <Link
                  to={`/workspace?kind=output&open=${encodeURIComponent(generateResult.output_path)}`}
                >
                  去工作区查看
                </Link>
              </div>
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
              <label className="field-label">优化人设</label>
              <select
                className="field-input"
                value={optimizerPersonaId}
                onChange={(e) => setOptimizerPersonaId(e.target.value)}
                style={{ maxWidth: 240 }}
              >
                {personaOptions.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
              <label className="field-label">Rounds</label>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <label className="hint">
                  <input
                    type="radio"
                    name="reactOptimizerRounds"
                    checked={optimizerRoundsMode === "default"}
                    onChange={() => setOptimizerRoundsMode("default")}
                  />{" "}
                  默认
                </label>
                <label className="hint">
                  <input
                    type="radio"
                    name="reactOptimizerRounds"
                    checked={optimizerRoundsMode === "custom"}
                    onChange={() => setOptimizerRoundsMode("custom")}
                  />{" "}
                  自定义
                </label>
                <input
                  type="number"
                  className="field-input"
                  min={1}
                  max={99}
                  disabled={optimizerRoundsMode !== "custom"}
                  value={optimizerMaxRoundsInput}
                  onChange={(e) => setOptimizerMaxRoundsInput(e.target.value)}
                  style={{ width: 100 }}
                />
              </div>
              {isOptimizerAdmin && (
                <>
                  <label className="field-label">优化器</label>
                  <select
                    className="field-input"
                    value={optimizerType}
                    onChange={(e) => setOptimizerType(e.target.value as "bootstrap" | "mipro")}
                    style={{ maxWidth: 240 }}
                  >
                    <option value="bootstrap">bootstrap</option>
                    <option value="mipro">mipro</option>
                  </select>
                </>
              )}
              <label className="hint">
                <input
                  type="checkbox"
                  checked={optimizerNoCache}
                  onChange={(e) => setOptimizerNoCache(e.target.checked)}
                />{" "}
                强制重跑（跳过缓存）
              </label>
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
