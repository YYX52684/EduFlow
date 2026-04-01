import { FormEvent, useEffect, useState } from "react";
import { ApiError, apiGet, apiPostJson } from "../utils/api";

interface LlmConfigResponse {
  model_type: "deepseek" | "doubao" | "openai" | string;
  base_url: string;
  model: string;
  api_key_masked?: string;
  has_api_key?: boolean;
}

interface PlatformConfigResponse {
  base_url: string;
  cookie: string;
  authorization: string;
  course_id: string;
  train_task_id: string;
  start_node_id: string;
  end_node_id: string;
}

type ThemeMode = "light" | "dark" | "leaf";

const defaultLlmConfig: LlmConfigResponse = {
  model_type: "doubao",
  base_url: "",
  model: "",
  api_key_masked: "",
  has_api_key: false,
};

const defaultPlatformConfig: PlatformConfigResponse = {
  base_url: "https://cloudapi.polymas.com",
  cookie: "",
  authorization: "",
  course_id: "",
  train_task_id: "",
  start_node_id: "",
  end_node_id: "",
};

function applyAppearance(theme: ThemeMode, wallpaper: string) {
  const root = document.documentElement;
  const body = document.body;
  const themes: Record<ThemeMode, Record<string, string>> = {
    light: {
      "--bg": "#fdf9f3",
      "--paper": "#ffffff",
      "--ink": "#4a4a4a",
      "--ink-light": "#6b5f52",
      "--accent": "#8fa989",
      "--accent-strong": "#7a9a74",
      "--border": "#e4ddd0",
    },
    dark: {
      "--bg": "#16181b",
      "--paper": "#21252b",
      "--ink": "#f5f3ef",
      "--ink-light": "#d0c8bc",
      "--accent": "#7aa36d",
      "--accent-strong": "#93b982",
      "--border": "#3a4048",
    },
    leaf: {
      "--bg": "#f3f8f1",
      "--paper": "#ffffff",
      "--ink": "#3c5140",
      "--ink-light": "#5f7262",
      "--accent": "#79a96b",
      "--accent-strong": "#628f56",
      "--border": "#d6e5cf",
    },
  };
  Object.entries(themes[theme]).forEach(([key, value]) => {
    root.style.setProperty(key, value);
  });
  if (wallpaper.trim()) {
    body.style.backgroundImage = `linear-gradient(rgba(255,255,255,0.75), rgba(255,255,255,0.75)), url(${wallpaper.trim()})`;
    body.style.backgroundSize = "cover";
    body.style.backgroundPosition = "center";
    body.style.backgroundAttachment = "fixed";
  } else {
    body.style.backgroundImage = "";
    body.style.backgroundSize = "";
    body.style.backgroundPosition = "";
    body.style.backgroundAttachment = "";
  }
}

export const SettingsPage = () => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<LlmConfigResponse>(defaultLlmConfig);
  const [platformConfig, setPlatformConfig] =
    useState<PlatformConfigResponse>(defaultPlatformConfig);
  const [platformUrl, setPlatformUrl] = useState("");
  const [theme, setTheme] = useState<ThemeMode>("light");
  const [wallpaper, setWallpaper] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const storedTheme = (localStorage.getItem("eduflow_theme") as ThemeMode) || "light";
    const storedWallpaper = localStorage.getItem("eduflow_wallpaper") || "";
    setTheme(storedTheme);
    setWallpaper(storedWallpaper);
    applyAppearance(storedTheme, storedWallpaper);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [llmData, platformData] = await Promise.all([
          apiGet<LlmConfigResponse>("/llm/config"),
          apiGet<PlatformConfigResponse>("/platform/config"),
        ]);
        if (!cancelled) {
          setConfig({ ...defaultLlmConfig, ...llmData });
          setPlatformConfig({ ...defaultPlatformConfig, ...platformData });
        }
      } catch (err) {
        if (!cancelled) {
          setMessage(
            err instanceof ApiError ? err.message : "加载配置失败，请稍后重试。",
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

  async function handleSubmitLlm(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const payload: Record<string, string> = {
        model_type: config.model_type,
        base_url: config.base_url || "",
        model: config.model || "",
      };
      const keyInput = (e.currentTarget.elements.namedItem("api_key") as HTMLInputElement | null)?.value?.trim() || "";
      if (keyInput || !config.has_api_key) payload.api_key = keyInput;
      const data = await apiPostJson<{ message?: string }>("/llm/config", payload);
      const refreshed = await apiGet<LlmConfigResponse>("/llm/config");
      setConfig({ ...defaultLlmConfig, ...refreshed });
      setMessage(data.message || "已保存。");
      if (e.currentTarget) e.currentTarget.reset();
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "保存失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function handleClearApiKey() {
    setSaving(true);
    setMessage(null);
    try {
      const data = await apiPostJson<{ message?: string }>("/llm/config", {
        api_key: "",
      });
      const refreshed = await apiGet<LlmConfigResponse>("/llm/config");
      setConfig({ ...defaultLlmConfig, ...refreshed });
      setMessage(data.message || "已清空当前工作区保存的 API Key。");
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "清空失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function handleSavePlatform(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const data = await apiPostJson<{ message?: string }>("/platform/config", platformConfig);
      setMessage(data.message || "平台配置已保存。");
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "平台配置保存失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function handleLoadPlatformFromUrl() {
    setSaving(true);
    setMessage(null);
    try {
      const data = await apiPostJson<PlatformConfigResponse & { message?: string }>(
        "/platform/load-config",
        {
          url: platformUrl,
          ...platformConfig,
        },
      );
      setPlatformConfig({ ...defaultPlatformConfig, ...data });
      setMessage(data.message || "已从 URL 加载并保存平台配置。");
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "加载平台配置失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  function handleSaveAppearance() {
    localStorage.setItem("eduflow_theme", theme);
    localStorage.setItem("eduflow_wallpaper", wallpaper);
    applyAppearance(theme, wallpaper);
    setMessage("外观设置已应用到当前浏览器。");
  }

  return (
    <>
      <section className="page-section">
        <div className="page-section-title">
          <h2>API 与模型</h2>
          <span className="pill">统一驱动解析、生成、仿真、优化</span>
        </div>
        <p className="page-section-desc">
          与旧版设置面板共用同一套后端配置。保存后立即作用于当前工作区。
        </p>

        {loading ? (
          <div className="card-muted">正在加载当前工作区配置…</div>
        ) : (
          <form onSubmit={handleSubmitLlm} className="stack-v" style={{ maxWidth: 560 }}>
            <label className="field-label" htmlFor="model-type">
              模型类型
            </label>
            <select
              id="model-type"
              className="field-select"
              value={config.model_type}
              onChange={(e) =>
                setConfig((prev) => ({ ...prev, model_type: e.target.value }))
              }
            >
              <option value="deepseek">DeepSeek</option>
              <option value="doubao">豆包</option>
              <option value="openai">OpenAI 兼容（自定义）</option>
            </select>

            <label className="field-label" htmlFor="api-key">
              API Key
            </label>
            <input
              id="api-key"
              name="api_key"
              type="password"
              className="field-input"
              placeholder={config.has_api_key ? "留空则保持当前已保存 Key" : "请输入 Key"}
            />
            <div className="hint">
              当前：{config.has_api_key ? config.api_key_masked || "已设置" : "未设置"}
            </div>

            <label className="field-label" htmlFor="base-url">
              Base URL
            </label>
            <input
              id="base-url"
              className="field-input"
              value={config.base_url}
              onChange={(e) =>
                setConfig((prev) => ({ ...prev, base_url: e.target.value }))
              }
              placeholder="https://api.openai.com/v1"
            />

            <label className="field-label" htmlFor="model-name">
              Model 名称
            </label>
            <input
              id="model-name"
              className="field-input"
              value={config.model}
              onChange={(e) =>
                setConfig((prev) => ({ ...prev, model: e.target.value }))
              }
              placeholder="gpt-4o"
            />

            <div className="stack-h">
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? "保存中…" : "保存 LLM 配置"}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={saving}
                onClick={handleClearApiKey}
              >
                清空已保存 Key
              </button>
            </div>
          </form>
        )}
      </section>

      <section className="page-section">
        <div className="page-section-title">
          <h2>平台配置</h2>
          <span className="pill">用于卡片注入与项目定位</span>
        </div>
        <p className="page-section-desc">
          可直接从智慧树 URL 提取课程与任务 ID，也支持手工保存整套平台参数。
        </p>

        <form onSubmit={handleSavePlatform} className="stack-v" style={{ maxWidth: 720 }}>
          <label className="field-label" htmlFor="platform-url">
            智慧树页面 URL
          </label>
          <input
            id="platform-url"
            className="field-input"
            value={platformUrl}
            onChange={(e) => setPlatformUrl(e.target.value)}
            placeholder="用于自动提取课程 ID / 训练任务 ID"
          />
          <button type="button" className="btn btn-ghost" disabled={saving} onClick={handleLoadPlatformFromUrl}>
            从 URL 加载并保存配置
          </button>

          {[
            ["base_url", "平台 Base URL"],
            ["authorization", "Authorization"],
            ["cookie", "Cookie"],
            ["course_id", "课程 ID"],
            ["train_task_id", "训练任务 ID"],
            ["start_node_id", "开始节点 ID"],
            ["end_node_id", "结束节点 ID"],
          ].map(([key, label]) => (
            <label key={key} className="field-label">
              {label}
              <input
                className="field-input"
                value={platformConfig[key as keyof PlatformConfigResponse]}
                onChange={(e) =>
                  setPlatformConfig((prev) => ({
                    ...prev,
                    [key]: e.target.value,
                  }))
                }
              />
            </label>
          ))}

          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? "保存中…" : "保存平台配置"}
          </button>
        </form>
      </section>

      <section className="page-section">
        <div className="page-section-title">
          <h2>外观</h2>
          <span className="pill">主题与壁纸仅保存在当前浏览器</span>
        </div>
        <p className="page-section-desc">
          用于补齐旧版的基础外观能力，不影响工作区数据与后端配置。
        </p>

        <div className="stack-v" style={{ maxWidth: 560 }}>
          <label className="field-label" htmlFor="theme-mode">
            主题
          </label>
          <select
            id="theme-mode"
            className="field-select"
            value={theme}
            onChange={(e) => setTheme(e.target.value as ThemeMode)}
          >
            <option value="light">浅色</option>
            <option value="dark">深色</option>
            <option value="leaf">青叶</option>
          </select>

          <label className="field-label" htmlFor="wallpaper-url">
            壁纸 URL
          </label>
          <input
            id="wallpaper-url"
            className="field-input"
            value={wallpaper}
            onChange={(e) => setWallpaper(e.target.value)}
            placeholder="可留空，仅使用主题配色"
          />

          <div className="stack-h">
            <button type="button" className="btn btn-primary" onClick={handleSaveAppearance}>
              应用外观
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setWallpaper("");
                localStorage.removeItem("eduflow_wallpaper");
                applyAppearance(theme, "");
                setMessage("已清除壁纸。");
              }}
            >
              清除壁纸
            </button>
          </div>
        </div>
      </section>

      {message && (
        <div
          className={
            "page-section hint" +
            (/(已保存|已应用|已清除|已从 URL 加载|默认)/.test(message)
              ? " text-success"
              : " text-danger")
          }
        >
          {message}
        </div>
      )}
    </>
  );
};
