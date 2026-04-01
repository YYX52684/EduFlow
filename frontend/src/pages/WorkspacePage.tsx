import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { ApiError, apiGet, apiPostJson, apiRequest } from "../utils/api";

type EntryKind = "all" | "output" | "trainset" | "persona" | "input";
type EditorMode = "preview" | "edit";

interface WorkspaceFile {
  name: string;
  path: string;
  mtime?: number;
}

interface FilesResponse {
  files: WorkspaceFile[];
}

interface PersonasResponse {
  presets: string[];
  custom: string[];
}

interface FileReadResponse {
  path?: string;
  content?: string;
}

interface PersonaContentResponse {
  content?: string;
  read_only?: boolean;
}

interface WorkspaceEntry {
  id: string;
  kind: Exclude<EntryKind, "all">;
  title: string;
  path: string;
  mtime?: number;
  editable: boolean;
  deletable: boolean;
  downloadable: boolean;
}

function formatTime(mtime?: number): string {
  if (!mtime) return "";
  const date = new Date(mtime * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}

function kindLabel(kind: Exclude<EntryKind, "all">): string {
  if (kind === "output") return "输出";
  if (kind === "trainset") return "Trainset";
  if (kind === "persona") return "人设";
  return "原材料";
}

export const WorkspacePage = () => {
  const location = useLocation();
  const [inputFiles, setInputFiles] = useState<WorkspaceFile[]>([]);
  const [outputFiles, setOutputFiles] = useState<WorkspaceFile[]>([]);
  const [trainsetFiles, setTrainsetFiles] = useState<WorkspaceFile[]>([]);
  const [personaCustom, setPersonaCustom] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState<EntryKind>("all");
  const [sortMode, setSortMode] = useState<"latest" | "name">("latest");
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const [loadingContent, setLoadingContent] = useState(false);
  const [editorMode, setEditorMode] = useState<EditorMode>("preview");
  const [editorContent, setEditorContent] = useState("");
  const [savedContent, setSavedContent] = useState("");
  const [readOnly, setReadOnly] = useState(true);
  const [saving, setSaving] = useState(false);
  const [contentMessage, setContentMessage] = useState<string | null>(null);

  async function refreshWorkspaceData(silent = false) {
    if (!silent) setRefreshing(true);
    try {
      const [inputResp, outputResp, trainsetResp, personasResp] = await Promise.all([
        apiGet<FilesResponse>("/input/files"),
        apiGet<FilesResponse>("/output/files?with_mtime=1"),
        apiGet<FilesResponse>("/trainset/list"),
        apiGet<PersonasResponse>("/personas"),
      ]);
      setInputFiles(inputResp?.files || []);
      setOutputFiles(outputResp?.files || []);
      setTrainsetFiles(trainsetResp?.files || []);
      setPersonaCustom(personasResp?.custom || []);
      setMessage(null);
    } catch (err) {
      setMessage(
        err instanceof ApiError
          ? err.message
          : "加载工作区文件失败，请稍后重试。",
      );
    } finally {
      if (!silent) setRefreshing(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [inputResp, outputResp, trainsetResp, personasResp] =
          await Promise.all([
            apiGet<FilesResponse>("/input/files"),
            apiGet<FilesResponse>("/output/files?with_mtime=1"),
            apiGet<FilesResponse>("/trainset/list"),
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
          setMessage(
            err instanceof ApiError
              ? err.message
              : "加载工作区文件失败，请稍后重试。",
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

  const entries = useMemo<WorkspaceEntry[]>(() => {
    const regularOutputFiles = outputFiles.filter((file) => {
      const path = (file.path || "").replace(/\\/g, "/");
      return (
        !path.startsWith("output/trainset_lib/") &&
        !path.startsWith("output/persona_lib/")
      );
    });
    const list: WorkspaceEntry[] = [
      ...regularOutputFiles.map((file) => ({
        id: `output:${file.path}`,
        kind: "output" as const,
        title: file.name || file.path,
        path: file.path,
        mtime: file.mtime,
        editable: true,
        deletable: true,
        downloadable: true,
      })),
      ...trainsetFiles.map((file) => ({
        id: `trainset:${file.path}`,
        kind: "trainset" as const,
        title: file.name || file.path,
        path: file.path,
        mtime: file.mtime,
        editable: true,
        deletable: true,
        downloadable: true,
      })),
      ...personaCustom.map((personaId) => ({
        id: `persona:${personaId}`,
        kind: "persona" as const,
        title: personaId.replace(/^custom\//, ""),
        path: personaId,
        editable: true,
        deletable: true,
        downloadable: false,
      })),
      ...inputFiles.map((file) => ({
        id: `input:${file.path}`,
        kind: "input" as const,
        title: file.name || file.path,
        path: file.path,
        editable: false,
        deletable: false,
        downloadable: false,
      })),
    ];

    const keyword = search.trim().toLowerCase();
    const filtered = list.filter((entry) => {
      if (kindFilter !== "all" && entry.kind !== kindFilter) return false;
      if (!keyword) return true;
      return (
        entry.title.toLowerCase().includes(keyword) ||
        entry.path.toLowerCase().includes(keyword)
      );
    });

    filtered.sort((a, b) => {
      if (sortMode === "latest") {
        const timeDiff = (b.mtime || 0) - (a.mtime || 0);
        if (timeDiff !== 0) return timeDiff;
      }
      return a.title.localeCompare(b.title, "zh-Hans-CN");
    });
    return filtered;
  }, [
    inputFiles,
    outputFiles,
    trainsetFiles,
    personaCustom,
    search,
    kindFilter,
    sortMode,
  ]);

  const selectedEntry =
    entries.find((entry) => entry.id === selectedEntryId) || null;
  const dirty = editorContent !== savedContent;

  useEffect(() => {
    if (!entries.length) {
      setSelectedEntryId(null);
      return;
    }
    if (!selectedEntry) {
      setSelectedEntryId(entries[0].id);
    }
  }, [entries, selectedEntry]);

  useEffect(() => {
    if (!entries.length) return;
    const params = new URLSearchParams(location.search);
    const openPath = (params.get("open") || "").trim();
    const openKind = (params.get("kind") || "").trim() as
      | Exclude<EntryKind, "all">
      | "";
    if (!openPath || !openKind) return;
    const targetId = `${openKind}:${openPath}`;
    if (entries.some((entry) => entry.id === targetId)) {
      setSelectedEntryId(targetId);
    }
  }, [entries, location.search]);

  async function loadEntryContent(entry: WorkspaceEntry) {
    setLoadingContent(true);
    setContentMessage(null);
    try {
      if (entry.kind === "persona") {
        const data = await apiGet<PersonaContentResponse>(
          `/personas/content?persona_id=${encodeURIComponent(entry.path)}`,
        );
        const content = data.content || "";
        setEditorContent(content);
        setSavedContent(content);
        setReadOnly(!!data.read_only);
        setEditorMode(data.read_only ? "preview" : "edit");
      } else if (entry.kind === "input") {
        const data = await apiGet<FileReadResponse>(
          `/input/read?path=${encodeURIComponent(entry.path)}`,
        );
        const content = data.content || "";
        setEditorContent(content);
        setSavedContent(content);
        setReadOnly(true);
        setEditorMode("preview");
      } else {
        const data = await apiGet<FileReadResponse>(
          `/output/read?path=${encodeURIComponent(entry.path)}`,
        );
        const content = data.content || "";
        setEditorContent(content);
        setSavedContent(content);
        setReadOnly(false);
        setEditorMode("edit");
      }
    } catch (err) {
      setEditorContent("");
      setSavedContent("");
      setReadOnly(true);
      setContentMessage(
        err instanceof ApiError ? err.message : "加载内容失败，请稍后重试。",
      );
    } finally {
      setLoadingContent(false);
    }
  }

  useEffect(() => {
    if (!selectedEntry) return;
    void loadEntryContent(selectedEntry);
  }, [selectedEntryId]);

  async function handleSelectEntry(entry: WorkspaceEntry) {
    if (entry.id === selectedEntryId) return;
    if (dirty && !window.confirm("当前内容尚未保存，确定切换到其他文件吗？")) {
      return;
    }
    setSelectedEntryId(entry.id);
  }

  async function handleSave() {
    if (!selectedEntry || readOnly) return;
    setSaving(true);
    setContentMessage("保存中…");
    try {
      if (selectedEntry.kind === "persona") {
        await apiPostJson("/personas/content", {
          persona_id: selectedEntry.path,
          content: editorContent,
        });
      } else {
        await apiPostJson("/output/write", {
          path: selectedEntry.path,
          content: editorContent,
        });
      }
      setSavedContent(editorContent);
      setContentMessage("已保存");
      await refreshWorkspaceData(true);
    } catch (err) {
      setContentMessage(
        err instanceof ApiError ? err.message : "保存失败，请稍后重试。",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(entry: WorkspaceEntry) {
    if (!entry.deletable) return;
    const ok = window.confirm(`确定删除「${entry.title}」吗？`);
    if (!ok) return;
    try {
      if (entry.kind === "persona") {
        await apiRequest({
          path: "/personas",
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ persona_id: entry.path }),
        });
      } else if (entry.kind === "trainset") {
        await apiRequest({
          path: "/trainset/delete",
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: entry.path }),
        });
      } else {
        await apiRequest({
          path: "/output/delete",
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: entry.path }),
        });
      }
      setContentMessage(null);
      if (entry.id === selectedEntryId) {
        setSelectedEntryId(null);
        setEditorContent("");
        setSavedContent("");
      }
      await refreshWorkspaceData(true);
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "删除失败");
    }
  }

  function handleDownload(entry: WorkspaceEntry) {
    if (!entry.downloadable) return;
    window.open(
      `/api/output/download?path=${encodeURIComponent(entry.path)}`,
      "_blank",
      "noopener,noreferrer",
    );
  }

  return (
    <section className="page-section">
      <div className="page-section-title">
        <h2>工作区文件</h2>
        <span className="pill">浏览 / 搜索 / 预览 / 编辑</span>
      </div>
      <p className="page-section-desc">
        React 版工作区页已补齐历史文件、Trainset、人设和原材料浏览能力，并支持直接编辑
        output 文件与自定义人设。
      </p>

      <div className="workspace-toolbar">
        <input
          className="field-input"
          placeholder="按文件名或路径搜索"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="field-select"
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value as EntryKind)}
        >
          <option value="all">全部分类</option>
          <option value="output">输出文件</option>
          <option value="trainset">Trainset</option>
          <option value="persona">自定义人设</option>
          <option value="input">输入原材料</option>
        </select>
        <select
          className="field-select"
          value={sortMode}
          onChange={(e) => setSortMode(e.target.value as "latest" | "name")}
        >
          <option value="latest">按最近修改</option>
          <option value="name">按名称</option>
        </select>
        <button
          type="button"
          className="btn btn-ghost"
          disabled={refreshing}
          onClick={() => void refreshWorkspaceData()}
        >
          {refreshing ? "刷新中…" : "刷新列表"}
        </button>
      </div>

      {loading ? (
        <div className="card-muted">正在加载工作区文件…</div>
      ) : (
        <div className="workspace-grid">
          <aside className="workspace-sidebar">
            <div className="workspace-sidebar-meta">
              共 {entries.length} 项
              {search.trim() ? `，已按“${search.trim()}”过滤` : ""}
            </div>
            {!entries.length ? (
              <div className="card-muted">
                当前筛选条件下没有匹配文件。可先回到控制台上传原材料或生成卡片。
              </div>
            ) : (
              <div className="workspace-list">
                {entries.map((entry) => (
                  <button
                    key={entry.id}
                    type="button"
                    className={
                      "workspace-list-item" +
                      (selectedEntry?.id === entry.id ? " active" : "")
                    }
                    onClick={() => void handleSelectEntry(entry)}
                  >
                    <div className="workspace-list-item-top">
                      <span className="workspace-kind-tag">
                        {kindLabel(entry.kind)}
                      </span>
                      {entry.mtime ? (
                        <span className="hint">{formatTime(entry.mtime)}</span>
                      ) : null}
                    </div>
                    <div className="workspace-list-item-title">{entry.title}</div>
                    <div className="workspace-list-item-path">{entry.path}</div>
                  </button>
                ))}
              </div>
            )}
          </aside>

          <div className="workspace-content">
            {selectedEntry ? (
              <>
                <div className="workspace-content-header">
                  <div>
                    <div className="workspace-content-title">
                      {selectedEntry.title}
                    </div>
                    <div className="hint">
                      {selectedEntry.path}
                      {selectedEntry.mtime
                        ? ` · 最近修改：${formatTime(selectedEntry.mtime)}`
                        : ""}
                    </div>
                  </div>
                  <div className="stack-h">
                    <button
                      type="button"
                      className="btn btn-ghost"
                      onClick={() => setEditorMode("preview")}
                    >
                      预览
                    </button>
                    {!readOnly && (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => setEditorMode("edit")}
                      >
                        编辑
                      </button>
                    )}
                    {selectedEntry.downloadable && (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => handleDownload(selectedEntry)}
                      >
                        下载
                      </button>
                    )}
                    {selectedEntry.deletable && (
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => void handleDelete(selectedEntry)}
                      >
                        删除
                      </button>
                    )}
                    {!readOnly && (
                      <button
                        type="button"
                        className="btn btn-primary"
                        disabled={saving || !dirty}
                        onClick={() => void handleSave()}
                      >
                        {saving ? "保存中…" : "保存"}
                      </button>
                    )}
                  </div>
                </div>

                {contentMessage && (
                  <div
                    className={
                      "hint" +
                      (/已保存/.test(contentMessage)
                        ? " text-success"
                        : /保存中/.test(contentMessage)
                          ? ""
                          : " text-danger")
                    }
                  >
                    {contentMessage}
                  </div>
                )}

                {loadingContent ? (
                  <div className="card-muted">正在加载内容…</div>
                ) : editorMode === "edit" && !readOnly ? (
                  <textarea
                    className="workspace-editor"
                    value={editorContent}
                    onChange={(e) => setEditorContent(e.target.value)}
                    spellCheck={false}
                  />
                ) : (
                  <pre className="workspace-preview">
                    {editorContent || "（当前文件没有可显示内容）"}
                  </pre>
                )}
              </>
            ) : (
              <div className="card-muted">
                请选择左侧文件查看详情。若当前工作区还没有文件，可先回控制台上传原材料。
              </div>
            )}
          </div>
        </div>
      )}

      {message && (
        <div className="hint text-danger" style={{ marginTop: 8 }}>
          {message}
        </div>
      )}
    </section>
  );
};

