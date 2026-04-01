import { Link, NavLink } from "react-router-dom";
import { useEffect, useState, type ReactNode } from "react";
import { ApiError, apiGet } from "../utils/api";

type AppShellProps = {
  children: ReactNode;
};

interface MeResponse {
  user?: {
    id?: string;
    username?: string;
    email?: string | null;
    is_optimizer_admin?: boolean;
  };
  workspace_id?: string;
}

export const AppShell = ({ children }: AppShellProps) => {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiGet<MeResponse>("/auth/me");
        if (!cancelled) {
          setMe(data);
          setMessage(null);
        }
      } catch (err) {
        if (!cancelled) {
          setMe(null);
          if (err instanceof ApiError && err.status !== 401) {
            setMessage(err.message);
          }
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function handleLogout() {
    try {
      localStorage.removeItem("eduflow_token");
    } catch {
      // ignore
    }
    window.location.reload();
  }

  const username = me?.user?.username || "未登录";
  const workspaceId = me?.workspace_id || "demo";

  return (
    <div className="app-root">
      <header className="app-header">
        <div>
          <h1 className="app-title">
            <Link to="/" style={{ textDecoration: "none", color: "inherit" }}>
              EduFlow React 控制台
            </Link>
          </h1>
          <p className="app-subtitle">
            React 并行版入口，当前旧版 Web 仍保留为默认首页。
          </p>
          <div className="hint" style={{ marginTop: 6 }}>
            当前工作区：<code>{workspaceId}</code>
            {me?.user?.email ? `，账号：${me.user.email}` : ""}
          </div>
        </div>
        <div className="stack-v" style={{ alignItems: "flex-end", gap: 8 }}>
          <div className="hint">{username}</div>
          <nav className="app-nav" aria-label="主导航">
            <NavLink
              to="/"
              className={({ isActive }) =>
                "btn btn-ghost" + (isActive ? " pill" : "")
              }
            >
              控制台
            </NavLink>
            <NavLink
              to="/workspace"
              className={({ isActive }) =>
                "btn btn-ghost" + (isActive ? " pill" : "")
              }
            >
              工作区
            </NavLink>
            <NavLink
              to="/settings"
              className={({ isActive }) =>
                "btn btn-ghost" + (isActive ? " pill" : "")
              }
            >
              设置
            </NavLink>
            <NavLink
              to="/auth"
              className={({ isActive }) =>
                "btn btn-ghost" + (isActive ? " pill" : "")
              }
            >
              {me?.user ? "账户" : "登录 / 账户"}
            </NavLink>
            <a className="btn btn-ghost" href="/">
              旧版首页
            </a>
            {me?.user && (
              <button type="button" className="btn btn-primary" onClick={handleLogout}>
                退出
              </button>
            )}
          </nav>
        </div>
      </header>
      {message && <div className="hint text-danger" style={{ marginTop: 10 }}>{message}</div>}
      <main className="app-main">{children}</main>
    </div>
  );
};
