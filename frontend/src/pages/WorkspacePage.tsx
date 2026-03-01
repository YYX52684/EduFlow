import { useEffect, useState } from "react";
import { ApiError, apiGet, apiRequest } from "../utils/api";

interface WorkspaceFile {
  name: string;
  path: string;
}

interface FilesResponse {
  files: WorkspaceFile[];
}

interface TrainsetFile {
  path: string;
  name: string;
  mtime?: number;
}

interface TrainsetListResponse {
  files: TrainsetFile[];
}

interface PersonasResponse {
  presets: string[];
  custom: string[];
}

export const WorkspacePage = () => {
  const [inputFiles, setInputFiles] = useState<WorkspaceFile[]>([]);
  const [outputFiles, setOutputFiles] = useState<WorkspaceFile[]>([]);
  const [trainsetFiles, setTrainsetFiles] = useState<TrainsetFile[]>([]);
  const [personaCustom, setPersonaCustom] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [inputResp, outputResp, trainsetResp, personasResp] = await Promise.all([
          apiGet<FilesResponse>("/input/files"),
          apiGet<FilesResponse>("/output/files"),
          apiGet<TrainsetListResponse>("/trainset/list"),
          apiGet<PersonasResponse>("/personas"),
        ]);
        if (!cancelled) {
          setInputFiles(inputResp?.files || []);
          setOutputFiles(outputResp?.files || []);
          setTrainsetFiles(trainsetResp?.files || []);
          setPersonaCustom(personasResp?.custom || []);
          setMessage(null);
        }
      } catch (err) {
        if (!cancelled) {
          setMessage(err instanceof ApiError ? err.message : "加载工作区文件失败，请稍后重试。");
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

  async function handleDeleteTrainset(path: string) {
    if (!path) return;
    try {
      await apiRequest({
        path: "/trainset/delete",
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      setTrainsetFiles((prev) => prev.filter((f) => f.path !== path));
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "删除失败");
    }
  }

  async function handleDeletePersona(personaId: string) {
    if (!personaId) return;
    try {
      await apiRequest({
        path: "/personas",
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ persona_id: personaId }),
      });
      setPersonaCustom((prev) => prev.filter((id) => id !== personaId));
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "删除失败");
    }
  }

  return (
    <section className="page-section">
      <div className="page-section-title">
        <h2>历史生成文件</h2>
        <span className="pill">工作区 output / Trainset 库 / 人设库</span>
      </div>
      <p className="page-section-desc">
        当前工作区的输出文件、Trainset 库与人设库一览；可在控制台生成卡片与闭环优化时选用。
      </p>

      {loading ? (
        <div className="card-muted">正在加载…</div>
      ) : (
        <div className="stack-v" style={{ gap: 20 }}>
          <div>
            <h3 style={{ margin: "0 0 8px", fontSize: "0.95rem" }}>输出文件（output/）</h3>
            {renderList("output", outputFiles)}
          </div>
          <div>
            <h3 style={{ margin: "0 0 8px", fontSize: "0.95rem" }}>Trainset 库</h3>
            {!trainsetFiles.length ? (
              <div className="card-muted">暂无 trainset，上传并解析剧本后会自动写入。</div>
            ) : (
              <div className="stack-v">
                {trainsetFiles.map((f) => (
                  <div
                    key={f.path}
                    className="card-muted"
                    style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}
                  >
                    <span>{f.name || f.path}</span>
                    <span className="hint" style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>{f.path}</span>
                    <button
                      type="button"
                      className="btn secondary"
                      onClick={() => handleDeleteTrainset(f.path)}
                      style={{ flexShrink: 0 }}
                    >
                      删除
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div>
            <h3 style={{ margin: "0 0 8px", fontSize: "0.95rem" }}>人设库</h3>
            {!personaCustom.length ? (
              <div className="card-muted">暂无自定义人设；在控制台可生成人设并保存到此处。</div>
            ) : (
              <div className="stack-v">
                {personaCustom.map((id) => (
                  <div
                    key={id}
                    className="card-muted"
                    style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}
                  >
                    <span>{id.replace(/^custom\//, "")}</span>
                    <button
                      type="button"
                      className="btn secondary"
                      onClick={() => handleDeletePersona(id)}
                      style={{ flexShrink: 0 }}
                    >
                      删除
                    </button>
                  </div>
                ))}
              </div>
            )}
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

