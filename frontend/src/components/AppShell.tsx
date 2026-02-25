import { Link, NavLink } from "react-router-dom";
import type { ReactNode } from "react";

type AppShellProps = {
  children: ReactNode;
};

export const AppShell = ({ children }: AppShellProps) => {
  return (
    <div className="app-root">
      <header className="app-header">
        <div>
          <h1 className="app-title">
            <Link to="/" style={{ textDecoration: "none", color: "inherit" }}>
              EduFlow 控制台（预览版）
            </Link>
          </h1>
          <p className="app-subtitle">基于 React 的新前端正在逐步替换旧版页面。</p>
        </div>
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
            登录 / 账户
          </NavLink>
        </nav>
      </header>
      <main className="app-main">{children}</main>
    </div>
  );
};

