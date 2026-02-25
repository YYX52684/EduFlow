import { FormEvent, useEffect, useState } from "react";
import { apiGet, apiPostJson, ApiError } from "../utils/api";

interface LlmConfigResponse {
  model_type: "deepseek" | "doubao" | "openai" | string;
  base_url: string;
  model: string;
  api_key_masked?: string;
  has_api_key?: boolean;
}

export const SettingsPage = () => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<LlmConfigResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiGet<LlmConfigResponse>("/llm/config");
        if (!cancelled) {
          setConfig(data);
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

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const modelType = String(form.get("model_type") || "deepseek");
    const apiKey = String(form.get("api_key") || "").trim();
    const baseUrl = String(form.get("base_url") || "").trim();
    const model = String(form.get("model") || "").trim();

    setSaving(true);
    setMessage(null);
    try {
      const payload: Record<string, string> = { model_type: modelType };
      if (apiKey) payload.api_key = apiKey;
      if (modelType === "openai") {
        if (baseUrl) payload.base_url = baseUrl;
        if (model) payload.model = model;
      }
      const data = await apiPostJson<{ message?: string }>("/llm/config", payload);
      setMessage(data.message || "已保存。");
      // 重新拉取配置以更新 mask
      const refreshed = await apiGet<LlmConfigResponse>("/llm/config");
      setConfig(refreshed);
    } catch (err) {
      if (err instanceof ApiError) {
        setMessage(err.message);
      } else {
        setMessage("保存失败，请稍后重试。");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="page-section">
      <div className="page-section-title">
        <h2>API 与模型</h2>
        <span className="pill">驱动解析、生成、仿真、优化的统一配置</span>
      </div>
      <p className="page-section-desc">
        此处配置会影响剧本解析、卡片生成、仿真评估与优化器。与旧版设置弹窗共用相同
        API，保存后立即生效。
      </p>

      {loading ? (
        <div className="card-muted">正在加载当前工作区的 LLM 配置…</div>
      ) : (
        <form onSubmit={handleSubmit} className="stack-v" style={{ maxWidth: 520 }}>
          <label className="field-label" htmlFor="model-type">
            模型类型
          </label>
          <select
            id="model-type"
            name="model_type"
            className="field-select"
            defaultValue={config?.model_type ?? "deepseek"}
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
            placeholder={
              config?.has_api_key ? "留空则保持已保存的 Key" : "请输入 Key"
            }
          />
          <div className="hint">
            当前：{config?.has_api_key ? config.api_key_masked || "已设置" : "未设置"}
          </div>

          {config?.model_type === "openai" && (
            <>
              <label className="field-label" htmlFor="base-url">
                Base URL
              </label>
              <input
                id="base-url"
                name="base_url"
                className="field-input"
                defaultValue={config.base_url}
                placeholder="https://api.openai.com/v1"
              />

              <label className="field-label" htmlFor="model-name">
                Model 名称
              </label>
              <input
                id="model-name"
                name="model"
                className="field-input"
                defaultValue={config.model}
                placeholder="gpt-4o"
              />
            </>
          )}

          {message && (
            <div
              className={
                "hint" + (message.includes("已保存") ? " text-success" : " text-danger")
              }
            >
              {message}
            </div>
          )}

          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? "保存中…" : "保存配置"}
          </button>
        </form>
      )}
    </section>
  );
};

