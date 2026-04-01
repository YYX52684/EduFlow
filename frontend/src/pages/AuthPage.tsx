import { FormEvent, useEffect, useMemo, useState } from "react";
import { ApiError, apiPostJson } from "../utils/api";

type Tab = "login" | "register" | "forgot" | "reset";

interface LoginResponse {
  token: string;
  workspace_id: string;
  message?: string;
}

interface ForgotPasswordResponse {
  message?: string;
  reset_url?: string;
  reset_token?: string;
}

export const AuthPage = () => {
  const initialToken = useMemo(() => {
    const params = new URLSearchParams(window.location.search || "");
    return params.get("reset_token") || params.get("token") || "";
  }, []);
  const [tab, setTab] = useState<Tab>(initialToken ? "reset" : "login");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [forgotResult, setForgotResult] = useState<ForgotPasswordResponse | null>(null);
  const [resetToken, setResetToken] = useState(initialToken);

  useEffect(() => {
    if (initialToken) {
      setTab("reset");
    }
  }, [initialToken]);

  function redirectToConsole() {
    const pathname = window.location.pathname || "/";
    window.location.href = pathname.startsWith("/app") ? "/app/" : "/";
  }

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
      setMessage("登录成功，正在进入控制台…");
      setTimeout(redirectToConsole, 500);
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
      setMessage("注册成功，正在进入控制台…");
      setTimeout(redirectToConsole, 500);
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

  async function handleForgotPassword(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const identifier = String(form.get("identifier") || "").trim();
    if (!identifier) {
      setMessage("请输入邮箱。");
      return;
    }
    setPending(true);
    setMessage(null);
    setForgotResult(null);
    try {
      const data = await apiPostJson<ForgotPasswordResponse>("/auth/forgot-password", {
        identifier,
      });
      setForgotResult(data);
      setMessage(data.message || "若该账号存在，您将收到重置链接。请查收邮件或联系管理员。");
    } catch (err) {
      if (err instanceof ApiError) {
        setMessage(err.message);
      } else {
        setMessage("找回密码失败，请稍后重试");
      }
    } finally {
      setPending(false);
    }
  }

  async function handleResetPassword(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const token = String(form.get("token") || resetToken || "").trim();
    const newPassword = String(form.get("new_password") || "");
    const passwordAgain = String(form.get("new_password_again") || "");
    if (!token) {
      setMessage("缺少重置令牌，请重新申请找回密码。");
      return;
    }
    if (newPassword !== passwordAgain) {
      setMessage("两次输入的新密码不一致。");
      return;
    }
    setPending(true);
    setMessage(null);
    try {
      const data = await apiPostJson<{ message?: string }>("/auth/reset-password", {
        token,
        new_password: newPassword,
      });
      setMessage(data.message || "密码已重置，请使用新密码登录。");
      setTab("login");
      setResetToken("");
      window.history.replaceState(null, "", window.location.pathname);
    } catch (err) {
      if (err instanceof ApiError) {
        setMessage(err.message);
      } else {
        setMessage("重置密码失败，请稍后重试");
      }
    } finally {
      setPending(false);
    }
  }

  const isSuccess = !!message && /(成功|已发送|已重置|请查收|若该账号存在)/.test(message);

  return (
    <section className="page-section">
      <div className="page-section-title">
        <h2>登录与账户</h2>
        <span className="pill">登录 / 注册 / 找回密码 / 重置密码</span>
      </div>
      <p className="page-section-desc">
        React 版本已补齐旧版账户主流程。旧版首页仍是默认入口，React 入口可独立完成登录与找回密码。
      </p>

      <div className="stack-h" style={{ marginBottom: 8 }}>
        {[
          ["login", "登录"],
          ["register", "注册"],
          ["forgot", "找回密码"],
          ["reset", "重置密码"],
        ].map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={"btn btn-ghost" + (tab === id ? " pill" : "")}
            onClick={() => {
              setTab(id as Tab);
              setMessage(null);
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "login" && (
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

          <button type="submit" className="btn btn-primary" disabled={pending}>
            {pending ? "登录中…" : "登录"}
          </button>
        </form>
      )}

      {tab === "register" && (
        <form onSubmit={handleRegister} className="stack-v" style={{ maxWidth: 420 }}>
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

          <button type="submit" className="btn btn-primary" disabled={pending}>
            {pending ? "注册中…" : "注册并登录"}
          </button>
        </form>
      )}

      {tab === "forgot" && (
        <form onSubmit={handleForgotPassword} className="stack-v" style={{ maxWidth: 420 }}>
          <label className="field-label" htmlFor="forgot-identifier">
            邮箱
          </label>
          <input
            id="forgot-identifier"
            name="identifier"
            className="field-input"
            placeholder="请输入注册时使用的邮箱"
            autoComplete="username"
            required
          />

          <button type="submit" className="btn btn-primary" disabled={pending}>
            {pending ? "发送中…" : "发送重置链接"}
          </button>

          {forgotResult?.reset_url && (
            <div className="card-muted">
              <div>开发环境重置链接：</div>
              <a href={forgotResult.reset_url}>{forgotResult.reset_url}</a>
            </div>
          )}
          {forgotResult?.reset_token && (
            <div className="card-muted">
              <div>开发环境重置令牌：</div>
              <code>{forgotResult.reset_token}</code>
            </div>
          )}
        </form>
      )}

      {tab === "reset" && (
        <form onSubmit={handleResetPassword} className="stack-v" style={{ maxWidth: 420 }}>
          <label className="field-label" htmlFor="reset-token">
            重置令牌
          </label>
          <input
            id="reset-token"
            name="token"
            className="field-input"
            value={resetToken}
            onChange={(e) => setResetToken(e.target.value)}
            placeholder="来自邮件链接或管理员提供的 token"
            required
          />

          <label className="field-label" htmlFor="reset-password">
            新密码
          </label>
          <input
            id="reset-password"
            name="new_password"
            type="password"
            className="field-input"
            placeholder="至少 6 位"
            autoComplete="new-password"
            required
          />

          <label className="field-label" htmlFor="reset-password-again">
            再次输入新密码
          </label>
          <input
            id="reset-password-again"
            name="new_password_again"
            type="password"
            className="field-input"
            placeholder="请再输入一次"
            autoComplete="new-password"
            required
          />

          <button type="submit" className="btn btn-primary" disabled={pending}>
            {pending ? "重置中…" : "确认并重置密码"}
          </button>
        </form>
      )}

      {message && (
        <div
          className={"hint" + (isSuccess ? " text-success" : " text-danger")}
          style={{ marginTop: 10 }}
        >
          {message}
        </div>
      )}
    </section>
  );
};
