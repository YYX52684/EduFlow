import { FormEvent, useState } from "react";
import { ApiError, apiPostJson } from "../utils/api";

type Tab = "login" | "register";

interface LoginResponse {
  token: string;
  workspace_id: string;
  message?: string;
}

export const AuthPage = () => {
  const [tab, setTab] = useState<Tab>("login");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleLogin(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const identifier = String(form.get("identifier") || "").trim();
    const password = String(form.get("password") || "");
    setPending(true);
    setMessage(null);
    try {
      const data = await apiPostJson<LoginResponse>("/auth/login", {
        identifier,
        password,
      });
      localStorage.setItem("eduflow_token", data.token);
      setMessage("登录成功，正在刷新页面…");
      setTimeout(() => window.location.reload(), 600);
    } catch (err) {
      if (err instanceof ApiError) {
        setMessage(err.message);
      } else {
        setMessage("登录失败，请稍后重试");
      }
    } finally {
      setPending(false);
    }
  }

  async function handleRegister(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const email = String(form.get("email") || "").trim();
    const password = String(form.get("password") || "");
    const passwordAgain = String(form.get("password_again") || "");
    if (!email) {
      setMessage("请填写邮箱。");
      return;
    }
    if (password !== passwordAgain) {
      setMessage("两次输入的密码不一致。");
      return;
    }
    setPending(true);
    setMessage(null);
    try {
      const data = await apiPostJson<LoginResponse>("/auth/register", {
        email,
        password,
      });
      localStorage.setItem("eduflow_token", data.token);
      setMessage("注册成功，正在刷新页面…");
      setTimeout(() => window.location.reload(), 600);
    } catch (err) {
      if (err instanceof ApiError) {
        setMessage(err.message);
      } else {
        setMessage("注册失败，请稍后重试");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="page-section">
      <div className="page-section-title">
        <h2>登录与账户</h2>
        <span className="pill">工作区隔离 + 历史记录</span>
      </div>
      <p className="page-section-desc">
        登录后，可使用属于自己的工作区与历史文件。此页面是旧版登录弹窗的 React
        版本，行为与原有接口保持一致。
      </p>

      <div className="stack-h" style={{ marginBottom: 8 }}>
        <button
          type="button"
          className={
            "btn btn-ghost" + (tab === "login" ? " pill" : "")
          }
          onClick={() => {
            setTab("login");
            setMessage(null);
          }}
        >
          登录
        </button>
        <button
          type="button"
          className={
            "btn btn-ghost" + (tab === "register" ? " pill" : "")
          }
          onClick={() => {
            setTab("register");
            setMessage(null);
          }}
        >
          注册
        </button>
      </div>

      {tab === "login" ? (
        <form onSubmit={handleLogin} className="stack-v" style={{ maxWidth: 420 }}>
          <label className="field-label" htmlFor="login-identifier">
            邮箱
          </label>
          <input
            id="login-identifier"
            name="identifier"
            className="field-input"
            placeholder="用于登录的邮箱"
            autoComplete="username"
            required
          />

          <label className="field-label" htmlFor="login-password">
            密码
          </label>
          <input
            id="login-password"
            name="password"
            type="password"
            className="field-input"
            placeholder="请输入密码"
            autoComplete="current-password"
            required
          />

          {message && (
            <div
              className={
                "hint" + (message.includes("成功") ? " text-success" : " text-danger")
              }
            >
              {message}
            </div>
          )}

          <button type="submit" className="btn btn-primary" disabled={pending}>
            {pending ? "登录中…" : "登录"}
          </button>
        </form>
      ) : (
        <form
          onSubmit={handleRegister}
          className="stack-v"
          style={{ maxWidth: 420 }}
        >
          <p className="hint">
            使用邮箱注册，注册成功后会自动登录。
          </p>
          <label className="field-label" htmlFor="reg-email">
            邮箱
          </label>
          <input
            id="reg-email"
            name="email"
            type="email"
            className="field-input"
            placeholder="用于登录与找回密码"
            autoComplete="email"
            required
          />

          <label className="field-label" htmlFor="reg-password">
            密码
          </label>
          <input
            id="reg-password"
            name="password"
            type="password"
            className="field-input"
            placeholder="至少 6 位"
            autoComplete="new-password"
            required
          />

          <label className="field-label" htmlFor="reg-password-again">
            再次输入密码
          </label>
          <input
            id="reg-password-again"
            name="password_again"
            type="password"
            className="field-input"
            placeholder="请再输入一次密码"
            autoComplete="new-password"
            required
          />

          {message && (
            <div
              className={
                "hint" + (message.includes("成功") ? " text-success" : " text-danger")
              }
            >
              {message}
            </div>
          )}

          <button type="submit" className="btn btn-primary" disabled={pending}>
            {pending ? "注册中…" : "注册并登录"}
          </button>
        </form>
      )}
    </section>
  );
};

