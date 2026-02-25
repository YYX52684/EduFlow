import { useEffect, useState } from "react";
import { apiGet, ApiError } from "../utils/api";

interface WorkspaceFile {
  name: string;
  path: string;
}

interface FilesResponse {
  files: WorkspaceFile[];
}

export const WorkspacePage = () => {
  const [inputFiles, setInputFiles] = useState<WorkspaceFile[]>([]);
  const [outputFiles, setOutputFiles] = useState<WorkspaceFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [inputResp, outputResp] = await Promise.all([
          apiGet<FilesResponse>("/input/files"),
          apiGet<FilesResponse>("/output/files"),
        ]);
        if (!cancelled) {
          setInputFiles(inputResp.files || []);
          setOutputFiles(outputResp.files || []);
        }
      } catch (err) {
        if (!cancelled) {
          setMessage(
            err instanceof ApiError ? err.message : "加载工作区文件失败，请稍后重试。",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  function renderList(title: string, items: WorkspaceFile[]) {
    if (!items.length) {
      return (
        <div className="card-muted">
          当前工作区下暂无 {title === "output" ? "输出" : "输入"} 文件。
        </div>
      );
    }
    return (
      <div className="stack-v">
        {items.map((f) => (
          <div
            key={f.path}
            className="card-muted"
            style={{ display: "flex", justifyContent: "space-between", gap: 8 }}
          >
            <span>{f.name || f.path}</span>
            <span className="hint">{f.path}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <section className="page-section">
      <div className="page-section-title">
        <h2>工作区文件</h2>
        <span className="pill">input/ 与 output/ 目录一览</span>
      </div>
      <p className="page-section-desc">
        这里展示的是当前工作区下的输入与输出文件列表，数据直接来自
        /api/input/files 与 /api/output/files 接口，便于与控制台生成结果对照。
      </p>

      {loading ? (
        <div className="card-muted">正在加载工作区文件…</div>
      ) : (
        <div className="stack-v" style={{ gap: 16 }}>
          <div>
            <h3 style={{ margin: "0 0 8px", fontSize: "0.95rem" }}>输出文件（output/）</h3>
            {renderList("output", outputFiles)}
          </div>
          <div>
            <h3 style={{ margin: "0 0 8px", fontSize: "0.95rem" }}>输入文件（input/）</h3>
            {renderList("input", inputFiles)}
          </div>
        </div>
      )}

      {message && <div className="hint text-danger" style={{ marginTop: 8 }}>{message}</div>}
    </section>
  );
};

