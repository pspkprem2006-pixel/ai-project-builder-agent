"""Frontend generators: React (Vite) and Next.js (App Router)."""

from __future__ import annotations

import json
from typing import Any

from app.services.codegen.base import (
    blueprint_context,
    is_pk,
    pascal_case,
    render_template,
    singularize,
    snake_case,
    table_columns,
    table_plural,
)


def _field_meta(column: dict[str, Any]) -> dict[str, Any]:
    """Map a blueprint column to frontend field metadata."""
    name = column.get("name") or ""
    type_raw = (column.get("type") or "TEXT").upper()
    label = " ".join(word.capitalize() for word in name.split("_"))

    if "BOOLEAN" in type_raw:
        ftype = "checkbox"
    elif "DATE" in type_raw or "TIMESTAMP" in type_raw:
        ftype = "date"
    elif any(k in type_raw for k in ("INT", "NUMERIC", "DECIMAL", "FLOAT", "DOUBLE", "REAL", "SERIAL")):
        ftype = "number"
    elif "JSON" in type_raw:
        ftype = "textarea"
    else:
        ftype = "text"

    return {
        "key": name,
        "label": label,
        "type": ftype,
        "required": not column.get("constraints") or "NOT NULL" in type_raw,
    }


def _table_fields(table: dict[str, Any]) -> list[dict[str, Any]]:
    skipped = {"id", "created_at", "updated_at"}
    fields = [_field_meta(c) for c in table_columns(table) if c.get("name") not in skipped]
    return fields[:8]


def _form_fields(table: dict[str, Any]) -> list[dict[str, Any]]:
    fields = [
        _field_meta(c) for c in table_columns(table)
        if not is_pk(c) and c.get("name") not in ("created_at", "updated_at")
    ]
    return fields


def _js_field_lines(table: dict[str, Any], skip: set[str]) -> str:
    fields = [_field_meta(c) for c in table_columns(table) if c.get("name") not in skip]
    lines = [json.dumps(f, separators=(",", ":")) for f in fields]
    return ",\n".join(lines)


def _input_jsx(field: dict[str, Any]) -> str:
    key, label, ftype, required = field["key"], field["label"], field["type"], field["required"]
    if ftype == "checkbox":
        return (
            f'        <label className="field-label checkbox">\n'
            f'          <input type="checkbox" checked={{{key} === true}} '
            f'onChange={{e => setForm((f) => ({{ ...f, {key}: e.target.checked }}))}} />\n'
            f"          {label}\n"
            f"        </label>\n"
        )
    if ftype == "textarea":
        return (
            f'      <div className="field">\n'
            f'        <label className="field-label" htmlFor="{key}">{label}{" *" if required else ""}</label>\n'
            f'        <textarea id="{key}" value={{form.{key} || ""}} '
            f'onChange={{e => setForm((f) => ({{ ...f, {key}: e.target.value }}))}} rows={{4}} />\n'
            f"      </div>\n"
        )
    return (
        f'      <div className="field">\n'
        f'        <label className="field-label" htmlFor="{key}">{label}{" *" if required else ""}</label>\n'
        f'        <input id="{key}" type="{ftype}" value={{form.{key} || ""}} '
        f'onChange={{e => setForm((f) => ({{ ...f, {key}: e.target.value }}))}} />\n'
        f"      </div>\n"
    )


def _form_jsx(table: dict[str, Any]) -> str:
    return "".join(_input_jsx(f) for f in _form_fields(table))


def _frontend_tokens(context: dict[str, Any]) -> dict[str, str]:
    primary = context["primary_table"]
    table_name = primary.get("name") or "items"
    model = pascal_case(singularize(table_name))
    plural = table_plural(table_name)
    return {
        "PROJECT_NAME": context["project_name"],
        "APP_SLUG": context["app_slug"],
        "MODEL": model,
        "MODEL_LOWER": snake_case(singularize(table_name)),
        "PLURAL": plural,
        "PLURAL_LOWER": plural.lower(),
        "PLURAL_TITLE": plural.replace("_", " ").title(),
        "MODEL_TITLE": singularize(table_name).replace("_", " ").title(),
    }


REACT_README = """# __PROJECT_NAME__ - React Client

React (Vite) frontend generated from the project blueprint. Designed to consume
the matching generated API (same auth + resource endpoints under `/api/v1`).

## Features

- JWT authentication (login / register) with a React context provider
- Protected routes with a route guard
- CRUD screen for `__MODEL__`
- Axios client with auth token injection and centralized error handling

## Quick start

```bash
npm install
cp .env.example .env.local
npm run dev            # http://localhost:5173
```

Set `VITE_API_URL` to your API base URL (without `/api/v1`).

## Test

```bash
npm test
```

## Structure

```text
src/
  api/           axios client
  auth/          auth context + hook
  components/    layout, route guard, shared UI
  pages/         login, register, dashboard, __MODEL__ CRUD
  utils/         formatters
  main.jsx       entry point
  App.jsx        routing
```
"""

REACT_PACKAGE_JSON = """{
  "name": "__APP_SLUG__-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "axios": "^1.7.7",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.3",
    "vite": "^5.4.10",
    "vitest": "^2.1.5"
  }
}
"""

REACT_VITE_CONFIG = """import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  test: {
    environment: "jsdom",
  },
});
"""

REACT_INDEX_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>__PROJECT_NAME__</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
"""

REACT_MAIN = """import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
"""

REACT_APP = """import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import Dashboard from "./pages/Dashboard";
import __MODEL__Form from "./pages/__MODEL__Form";
import __MODEL__List from "./pages/__MODEL__List";
import Login from "./pages/Login";
import Register from "./pages/Register";

function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="center-page">Loading...</div>;
  }

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/register" element={user ? <Navigate to="/" replace /> : <Register />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/__PLURAL_LOWER__" element={<__MODEL__List />} />
          <Route path="/__PLURAL_LOWER__/new" element={<__MODEL__Form />} />
          <Route path="/__PLURAL_LOWER__/:id" element={<__MODEL__Form />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
"""

REACT_CLIENT = """import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const client = axios.create({ baseURL: `${API_URL}/api/v1` });

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("user");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export function apiErrorMessage(error) {
  return error?.response?.data?.detail || error?.response?.data?.message || error.message;
}
"""

REACT_AUTH_CONTEXT = """import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { client } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const response = await client.get("/auth/me");
      setUser(response.data);
    } catch {
      localStorage.removeItem("access_token");
      localStorage.removeItem("user");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  const login = useCallback(async (email, password) => {
    const response = await client.post("/auth/login", { email, password });
    localStorage.setItem("access_token", response.data.access_token);
    await loadUser();
  }, [loadUser]);

  const register = useCallback(async (payload) => {
    const response = await client.post("/auth/register", payload);
    localStorage.setItem("access_token", response.data.access_token);
    await loadUser();
  }, [loadUser]);

  const logout = useCallback(() => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user");
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return context;
}
"""

REACT_PROTECTED = """import { Navigate, Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

function ProtectedRoute() {
  const { user } = useAuth();
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}

export default ProtectedRoute;
"""

REACT_LAYOUT = """import { Link, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

function Layout() {
  const { user, logout } = useAuth();
  const location = useLocation();

  const links = [
    { to: "/", label: "Dashboard" },
    { to: "/__PLURAL_LOWER__", label: "__PLURAL_TITLE__" },
  ];

  return (
    <div className="app-shell">
      <nav className="sidebar">
        <div className="brand">__PROJECT_NAME__</div>
        {links.map((link) => (
          <Link
            key={link.to}
            to={link.to}
            className={`nav-link${location.pathname === link.to ? " active" : ""}`}
          >
            {link.label}
          </Link>
        ))}
      </nav>
      <main className="content">
        <header className="topbar">
          <span>Signed in as <strong>{user?.email}</strong></span>
          <button className="button button-ghost" onClick={logout}>Logout</button>
        </header>
        <Outlet />
      </main>
    </div>
  );
}

export default Layout;
"""

REACT_LOGIN = """import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { apiErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";

function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="center-page">
      <form className="auth-card" onSubmit={handleSubmit}>
        <h1>Sign in to __PROJECT_NAME__</h1>
        {error && <div className="alert">{error}</div>}
        <div className="field">
          <label className="field-label" htmlFor="email">Email</label>
          <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="password">Password</label>
          <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        <button className="button" type="submit" disabled={submitting}>
          {submitting ? "Signing in..." : "Sign in"}
        </button>
        <p className="auth-hint">
          No account? <Link to="/register">Register</Link>
        </p>
      </form>
    </div>
  );
}

export default Login;
"""

REACT_REGISTER = """import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { apiErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";

function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await register(form);
      navigate("/");
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="center-page">
      <form className="auth-card" onSubmit={handleSubmit}>
        <h1>Create your account</h1>
        {error && <div className="alert">{error}</div>}
        <div className="field">
          <label className="field-label" htmlFor="full_name">Full name</label>
          <input id="full_name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="email">Email</label>
          <input id="email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="password">Password</label>
          <input id="password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        </div>
        <button className="button" type="submit" disabled={submitting}>
          {submitting ? "Creating..." : "Register"}
        </button>
        <p className="auth-hint">
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}

export default Register;
"""

REACT_DASHBOARD = """import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

function Dashboard() {
  const { user } = useAuth();

  return (
    <section>
      <h1>Welcome, {user?.full_name || user?.email}!</h1>
      <p>Your generated application is ready. Explore the modules:</p>
      <div className="card-grid">
        <Link to="/__PLURAL_LOWER__" className="card">
          <h3>__PLURAL_TITLE__</h3>
          <p>Manage __MODEL_TITLE__ records with full CRUD.</p>
        </Link>
        <Link to="/register" className="card">
          <h3>Users</h3>
          <p>Register new accounts (auth is JWT-based).</p>
        </Link>
      </div>
    </section>
  );
}

export default Dashboard;
"""

REACT_LIST_TEMPLATE = """import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiErrorMessage, client } from "../api/client";

const COLUMNS = [
__COLUMNS__
];

function __MODEL__List() {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    client
      .get("/__PLURAL_LOWER__")
      .then((response) => setItems(response.data))
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  async function remove(id) {
    if (!window.confirm("Delete this record?")) return;
    try {
      await client.delete(`/__PLURAL_LOWER__/${id}`);
      setItems((current) => current.filter((item) => item.id !== id));
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  return (
    <section>
      <div className="page-header">
        <h1>__PLURAL_TITLE__</h1>
        <Link className="button" to="/__PLURAL_LOWER__/new">New __MODEL_TITLE__</Link>
      </div>
      {error && <div className="alert">{error}</div>}
      {loading && <p>Loading...</p>}
      {!loading && items.length === 0 && <p>No records yet.</p>}
      {!loading && items.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              {COLUMNS.map((column) => (
                <th key={column.key}>{column.label}</th>
              ))}
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                {COLUMNS.map((column) => (
                  <td key={column.key}>{String(item[column.key] ?? "-")}</td>
                ))}
                <td className="row-actions">
                  <Link className="button button-small" to={`/__PLURAL_LOWER__/${item.id}`}>Edit</Link>
                  <button className="button button-small button-danger" onClick={() => remove(item.id)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export default __MODEL__List;
"""

REACT_FORM_TEMPLATE = """import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { apiErrorMessage, client } from "../api/client";

function __MODEL__Form() {
  const { id } = useParams();
  const navigate = useNavigate();
  const isEditing = Boolean(id);
  const [form, setForm] = useState({});
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (isEditing) {
      client
        .get(`/__PLURAL_LOWER__/${id}`)
        .then((response) => setForm(response.data))
        .catch((err) => setError(apiErrorMessage(err)));
    }
  }, [id, isEditing]);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      if (isEditing) {
        await client.patch(`/__PLURAL_LOWER__/${id}`, form);
      } else {
        await client.post("/__PLURAL_LOWER__", form);
      }
      navigate("/__PLURAL_LOWER__");
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="form-page">
      <h1>{isEditing ? "Edit" : "New"} __MODEL_TITLE__</h1>
      {error && <div className="alert">{error}</div>}
      <form onSubmit={handleSubmit}>
__FIELDS__
        <div className="form-actions">
          <button className="button" type="submit" disabled={submitting}>
            {submitting ? "Saving..." : isEditing ? "Save changes" : "Create"}
          </button>
          <Link className="button button-ghost" to="/__PLURAL_LOWER__">Cancel</Link>
        </div>
      </form>
    </section>
  );
}

export default __MODEL__Form;
"""

REACT_STYLES = """:root {
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  color-scheme: light;
}

* { box-sizing: border-box; }

body { margin: 0; background: #f6f7f9; color: #1c2430; }

.app-shell { display: flex; min-height: 100vh; }

.sidebar {
  width: 230px; background: #101828; color: #e6e9ef; padding: 24px 16px;
  display: flex; flex-direction: column; gap: 8px;
}

.brand { font-size: 1.05rem; font-weight: 700; margin-bottom: 18px; color: #fff; }

.nav-link { color: #c9cfd9; text-decoration: none; padding: 9px 12px; border-radius: 8px; }
.nav-link:hover { background: #1d2939; color: #fff; }
.nav-link.active { background: #4f46e5; color: #fff; }

.content { flex: 1; padding: 28px 36px; }

.topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }

.center-page { display: grid; place-items: center; min-height: 100vh; background: #f6f7f9; }

.auth-card { background: #fff; border-radius: 12px; padding: 32px; width: 380px; box-shadow: 0 8px 24px rgba(16,24,40,.08); }
.auth-card h1 { font-size: 1.3rem; margin-top: 0; }
.auth-hint { font-size: .9rem; color: #667085; }

.field { margin-bottom: 14px; }
.field-label { display: block; font-size: .85rem; font-weight: 600; margin-bottom: 6px; }
.field-label.checkbox { display: flex; align-items: center; gap: 8px; font-weight: 500; }
input, textarea {
  width: 100%; padding: 9px 11px; border: 1px solid #d0d5dd; border-radius: 8px;
  font-size: .95rem; font-family: inherit;
}
input[type="checkbox"] { width: auto; }

.button {
  display: inline-flex; align-items: center; gap: 6px; background: #4f46e5; color: #fff;
  border: none; border-radius: 8px; padding: 9px 16px; font-size: .9rem; cursor: pointer; text-decoration: none;
}
.button:hover { background: #4338ca; }
.button:disabled { opacity: .6; cursor: not-allowed; }
.button-ghost { background: transparent; color: #4f46e5; }
.button-ghost:hover { background: #eef2ff; }
.button-small { padding: 5px 10px; font-size: .8rem; }
.button-danger { background: #dc2626; }
.button-danger:hover { background: #b91c1c; }

.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
.form-page { max-width: 560px; }
.form-actions { display: flex; gap: 10px; margin-top: 18px; }

.alert { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; }

.table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 16px rgba(16,24,40,.06); }
.table th, .table td { text-align: left; padding: 11px 14px; border-bottom: 1px solid #eaecf0; font-size: .9rem; }
.table th { background: #f9fafb; font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; color: #475467; }
.row-actions { display: flex; gap: 8px; }

.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.card { background: #fff; border-radius: 12px; padding: 20px; text-decoration: none; color: inherit; box-shadow: 0 4px 16px rgba(16,24,40,.06); }
.card:hover { box-shadow: 0 8px 24px rgba(16,24,40,.12); }
.card h3 { margin: 0 0 6px; }
.card p { margin: 0; color: #667085; font-size: .9rem; }
"""

REACT_TEST = """import { describe, expect, it } from "vitest";

import { apiErrorMessage } from "../api/client";

describe("apiErrorMessage", () => {
  it("falls back to the generic message", () => {
    expect(apiErrorMessage(new Error("network down"))).toBe("network down");
  });

  it("prefers the server detail", () => {
    const error = { response: { data: { detail: "Invalid email or password" } } };
    expect(apiErrorMessage(error)).toBe("Invalid email or password");
  });
});
"""

REACT_ENV_EXAMPLE = """# Base URL of the generated API (without /api/v1)
VITE_API_URL=http://localhost:8000
"""

REACT_GITIGNORE = """node_modules/
dist/
.env.local
coverage/
"""

REACT_DOCKERFILE = """FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
"""


def generate_react(blueprint: dict[str, Any]) -> dict[str, str]:
    context = blueprint_context(blueprint)
    tokens = _frontend_tokens(context)
    primary = context["primary_table"]

    files = {
        "README.md": render_template(REACT_README, **tokens),
        ".gitignore": REACT_GITIGNORE,
        ".env.example": REACT_ENV_EXAMPLE,
        "package.json": render_template(REACT_PACKAGE_JSON, **tokens),
        "vite.config.js": REACT_VITE_CONFIG,
        "index.html": render_template(REACT_INDEX_HTML, **tokens),
        "Dockerfile": REACT_DOCKERFILE,
        "src/main.jsx": REACT_MAIN,
        "src/App.jsx": render_template(REACT_APP, **tokens),
        "src/styles.css": REACT_STYLES,
        "src/api/client.js": REACT_CLIENT,
        "src/auth/AuthContext.jsx": REACT_AUTH_CONTEXT,
        "src/components/ProtectedRoute.jsx": REACT_PROTECTED,
        "src/components/Layout.jsx": render_template(REACT_LAYOUT, **tokens),
        "src/pages/Login.jsx": REACT_LOGIN,
        "src/pages/Register.jsx": REACT_REGISTER,
        "src/pages/Dashboard.jsx": render_template(REACT_DASHBOARD, **tokens),
        f"src/pages/{tokens['MODEL']}List.jsx": render_template(
            REACT_LIST_TEMPLATE,
            **tokens,
            COLUMNS=_js_field_lines(primary, {"id", "created_at", "updated_at"}),
        ),
        f"src/pages/{tokens['MODEL']}Form.jsx": render_template(
            REACT_FORM_TEMPLATE,
            **tokens,
            FIELDS=_form_jsx(primary),
        ),
        "src/__tests__/client.test.js": REACT_TEST,
    }
    return files


NEXT_README = """# __PROJECT_NAME__ - Next.js Web App

Next.js (App Router) frontend generated from the project blueprint. Designed to
consume the matching generated API (same auth + resource endpoints under `/api/v1`).

## Features

- JWT authentication (login / register) with a React context provider
- Middleware route protection (cookie + header token)
- CRUD screens for `__MODEL__`
- Server Components + Client Components with `src/lib/api.js`

## Quick start

```bash
npm install
cp .env.local.example .env.local
npm run dev            # http://localhost:3001
```

Set `NEXT_PUBLIC_API_URL` to your API base URL (without `/api/v1`).

## Structure

```text
src/
  app/
    (auth)/login, register
    (app)/dashboard, __PLURAL_LOWER__ (list + create)
    layout.js, page.js, globals.css
  lib/           api client, auth context
middleware.js    route protection
```
"""

NEXT_PACKAGE_JSON = """{
  "name": "__APP_SLUG__-web",
  "private": true,
  "version": "0.1.0",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "^15.1.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "eslint": "^9.17.0",
    "eslint-config-next": "^15.1.0"
  }
}
"""

NEXT_CONFIG = """/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
};

export default nextConfig;
"""

NEXT_JS_CONFIG = """{
  "compilerOptions": {
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
"""

NEXT_LAYOUT = """import "./globals.css";

export const metadata = {
  title: "__PROJECT_NAME__",
  description: "Web app generated from an AI blueprint",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
"""

NEXT_HOME = """import { redirect } from "next/navigation";

export default function Home() {
  redirect("/dashboard");
}
"""

NEXT_GLOBALS = """:root { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; background: #f6f7f9; color: #1c2430; }

.center-page { display: grid; place-items: center; min-height: 100vh; }
.auth-card { background: #fff; border-radius: 12px; padding: 32px; width: 380px; box-shadow: 0 8px 24px rgba(16,24,40,.08); }
.auth-card h1 { font-size: 1.3rem; margin-top: 0; }
.auth-hint { font-size: .9rem; color: #667085; }
.field { margin-bottom: 14px; }
.field-label { display: block; font-size: .85rem; font-weight: 600; margin-bottom: 6px; }
input, textarea { width: 100%; padding: 9px 11px; border: 1px solid #d0d5dd; border-radius: 8px; font-size: .95rem; font-family: inherit; }

.button { display: inline-flex; align-items: center; gap: 6px; background: #4f46e5; color: #fff; border: none; border-radius: 8px; padding: 9px 16px; font-size: .9rem; cursor: pointer; text-decoration: none; }
.button:hover { background: #4338ca; }
.button-ghost { background: transparent; color: #4f46e5; }
.button-danger { background: #dc2626; }
.button-small { padding: 5px 10px; font-size: .8rem; }

.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
.alert { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; }

.table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 12px; overflow: hidden; }
.table th, .table td { text-align: left; padding: 11px 14px; border-bottom: 1px solid #eaecf0; font-size: .9rem; }
.table th { background: #f9fafb; font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; color: #475467; }

.app-shell { display: flex; min-height: 100vh; }
.sidebar { width: 230px; background: #101828; color: #e6e9ef; padding: 24px 16px; display: flex; flex-direction: column; gap: 8px; }
.brand { font-size: 1.05rem; font-weight: 700; margin-bottom: 18px; color: #fff; }
.nav-link { color: #c9cfd9; text-decoration: none; padding: 9px 12px; border-radius: 8px; }
.nav-link:hover { background: #1d2939; color: #fff; }
.nav-link.active { background: #4f46e5; color: #fff; }
.content { flex: 1; padding: 28px 36px; }
.topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }

.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.card { background: #fff; border-radius: 12px; padding: 20px; text-decoration: none; color: inherit; box-shadow: 0 4px 16px rgba(16,24,40,.06); }
.card h3 { margin: 0 0 6px; }
.card p { margin: 0; color: #667085; font-size: .9rem; }
.form-page { max-width: 560px; }
.form-actions { display: flex; gap: 10px; margin-top: 18px; }
"""

NEXT_API = """const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_BASE = `${API_URL}/api/v1`;

export const TOKEN_COOKIE = "__APP_SLUG___token";

function headers(extra = {}) {
  return {
    "Content-Type": "application/json",
    ...extra,
  };
}

export async function apiFetch(path, { method = "GET", body, token } = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: headers(token ? { Authorization: `Bearer ${token}` } : {}),
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || detail.message || `Request failed (${response.status})`);
  }
  if (response.status === 204) return null;
  return response.json();
}

export async function register(payload) {
  return apiFetch("/auth/register", { method: "POST", body: payload });
}

export async function login(email, password) {
  return apiFetch("/auth/login", { method: "POST", body: { email, password } });
}

export async function me(token) {
  return apiFetch("/auth/me", { token });
}

export async function listItems(token) {
  return apiFetch("/__PLURAL_LOWER__", { token });
}

export async function createItem(token, payload) {
  return apiFetch("/__PLURAL_LOWER__", { method: "POST", body: payload, token });
}

export async function deleteItem(token, id) {
  return apiFetch(`/__PLURAL_LOWER__/${id}`, { method: "DELETE", token });
}
"""

NEXT_AUTH_CONTEXT = """"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { login, me, register } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const token = localStorage.getItem("access_token");
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        const data = await me(token);
        setUser(data);
      } catch {
        localStorage.removeItem("access_token");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const signIn = useCallback(async (email, password) => {
    const data = await login(email, password);
    localStorage.setItem("access_token", data.access_token);
    setUser(await me(data.access_token));
  }, []);

  const signUp = useCallback(async (payload) => {
    const data = await register(payload);
    localStorage.setItem("access_token", data.access_token);
    setUser(await me(data.access_token));
  }, []);

  const signOut = useCallback(() => {
    localStorage.removeItem("access_token");
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
"""

NEXT_AUTH_LAYOUT = """"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AuthProvider, useAuth } from "@/lib/auth-context";

function AuthGuard({ children }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);

  if (loading) return <div className="center-page">Loading...</div>;
  return children;
}

export default function AuthLayout({ children }) {
  return (
    <AuthProvider>
      <AuthGuard>{children}</AuthGuard>
    </AuthProvider>
  );
}
"""

NEXT_APP_LAYOUT = """"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { AuthProvider, useAuth } from "@/lib/auth-context";

function Shell({ children }) {
  const { user, signOut } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  function handleSignOut() {
    signOut();
    router.replace("/login");
  }

  const links = [
    { to: "/dashboard", label: "Dashboard" },
    { to: "/__PLURAL_LOWER__", label: "__PLURAL_TITLE__" },
  ];

  return (
    <div className="app-shell">
      <nav className="sidebar">
        <div className="brand">__PROJECT_NAME__</div>
        {links.map((link) => (
          <Link key={link.to} href={link.to} className={`nav-link${pathname === link.to ? " active" : ""}`}>
            {link.label}
          </Link>
        ))}
      </nav>
      <main className="content">
        <header className="topbar">
          <span>
            Signed in as <strong>{user?.email}</strong>
          </span>
          <button className="button button-ghost" onClick={handleSignOut}>
            Logout
          </button>
        </header>
        {children}
      </main>
    </div>
  );
}

export default function AppLayout({ children }) {
  return (
    <AuthProvider>
      <Shell>{children}</Shell>
    </AuthProvider>
  );
}
"""

NEXT_LOGIN = """"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const { signIn } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    try {
      await signIn(email, password);
      router.push("/dashboard");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="center-page">
      <form className="auth-card" onSubmit={handleSubmit}>
        <h1>Sign in to __PROJECT_NAME__</h1>
        {error && <div className="alert">{error}</div>}
        <div className="field">
          <label className="field-label" htmlFor="email">Email</label>
          <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="password">Password</label>
          <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        <button className="button" type="submit">Sign in</button>
        <p className="auth-hint">
          No account? <Link href="/register">Register</Link>
        </p>
      </form>
    </div>
  );
}
"""

NEXT_REGISTER = """"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/lib/auth-context";

export default function RegisterPage() {
  const { signUp } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [error, setError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    try {
      await signUp(form);
      router.push("/dashboard");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="center-page">
      <form className="auth-card" onSubmit={handleSubmit}>
        <h1>Create your account</h1>
        {error && <div className="alert">{error}</div>}
        <div className="field">
          <label className="field-label" htmlFor="full_name">Full name</label>
          <input id="full_name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="email">Email</label>
          <input id="email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="password">Password</label>
          <input id="password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        </div>
        <button className="button" type="submit">Register</button>
        <p className="auth-hint">
          Already registered? <Link href="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
"""

NEXT_DASHBOARD = """import Link from "next/link";

export default function DashboardPage() {
  return (
    <section>
      <h1>Dashboard</h1>
      <p>Your generated application is ready. Explore the modules:</p>
      <div className="card-grid">
        <Link href="/__PLURAL_LOWER__" className="card">
          <h3>__PLURAL_TITLE__</h3>
          <p>Manage __MODEL_TITLE__ records with full CRUD.</p>
        </Link>
      </div>
    </section>
  );
}
"""

NEXT_LIST_TEMPLATE = """"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { deleteItem, listItems } from "@/lib/api";

const COLUMNS = [
__COLUMNS__
];

export default function __MODEL__ListPage() {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const token = localStorage.getItem("access_token");
      setItems(await listItems(token));
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function remove(id) {
    if (!window.confirm("Delete this record?")) return;
    try {
      const token = localStorage.getItem("access_token");
      await deleteItem(token, id);
      await refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section>
      <div className="page-header">
        <h1>__PLURAL_TITLE__</h1>
        <Link className="button" href="/__PLURAL_LOWER__/new">New __MODEL_TITLE__</Link>
      </div>
      {error && <div className="alert">{error}</div>}
      {items.length === 0 && <p>No records yet.</p>}
      {items.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              {COLUMNS.map((column) => (
                <th key={column.key}>{column.label}</th>
              ))}
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                {COLUMNS.map((column) => (
                  <td key={column.key}>{String(item[column.key] ?? "-")}</td>
                ))}
                <td>
                  <button className="button button-small button-danger" onClick={() => remove(item.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
"""

NEXT_NEW_TEMPLATE = """"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { createItem } from "@/lib/api";

export default function New__MODEL__Page() {
  const router = useRouter();
  const [form, setForm] = useState({});
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const token = localStorage.getItem("access_token");
      await createItem(token, form);
      router.push("/__PLURAL_LOWER__");
      router.refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="form-page">
      <h1>New __MODEL_TITLE__</h1>
      {error && <div className="alert">{error}</div>}
      <form onSubmit={handleSubmit}>
__FIELDS__
        <div className="form-actions">
          <button className="button" type="submit" disabled={submitting}>
            {submitting ? "Saving..." : "Create"}
          </button>
          <Link className="button button-ghost" href="/__PLURAL_LOWER__">Cancel</Link>
        </div>
      </form>
    </section>
  );
}
"""

NEXT_MIDDLEWARE = """import { NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login", "/register"];

export function middleware(request) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get("access_token")?.value || "";
  const isPublic = PUBLIC_PATHS.some((path) => pathname.startsWith(path));

  if (isPublic && token) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }
  if (!isPublic && !token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
"""

NEXT_ENV_EXAMPLE = """# Base URL of the generated API (without /api/v1)
NEXT_PUBLIC_API_URL=http://localhost:8000
"""

NEXT_GITIGNORE = """node_modules/
.next/
.env.local
"""

NEXT_DOCKERFILE = """FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next ./.next
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json
EXPOSE 3000
CMD ["npm", "start"]
"""


def _next_input_jsx(field: dict[str, Any]) -> str:
    key, label, ftype, required = field["key"], field["label"], field["type"], field["required"]
    if ftype == "checkbox":
        return (
            f'        <label className="field-label checkbox">\n'
            f'          <input type="checkbox" checked={{form.{key} === true}} '
            f'onChange={{e => setForm((f) => ({{ ...f, {key}: e.target.checked }}))}} />\n'
            f"          {label}\n"
            f"        </label>\n"
        )
    if ftype == "textarea":
        return (
            f'      <div className="field">\n'
            f'        <label className="field-label" htmlFor="{key}">{label}{" *" if required else ""}</label>\n'
            f'        <textarea id="{key}" value={{form.{key} || ""}} '
            f'onChange={{e => setForm((f) => ({{ ...f, {key}: e.target.value }}))}} rows={{4}} />\n'
            f"      </div>\n"
        )
    return (
        f'      <div className="field">\n'
        f'        <label className="field-label" htmlFor="{key}">{label}{" *" if required else ""}</label>\n'
        f'        <input id="{key}" type="{ftype}" value={{form.{key} || ""}} '
        f'onChange={{e => setForm((f) => ({{ ...f, {key}: e.target.value }}))}} />\n'
        f"      </div>\n"
    )


def generate_nextjs(blueprint: dict[str, Any]) -> dict[str, str]:
    context = blueprint_context(blueprint)
    tokens = _frontend_tokens(context)
    primary = context["primary_table"]
    form_fields = _form_fields(primary)

    return {
        "README.md": render_template(NEXT_README, **tokens),
        ".gitignore": NEXT_GITIGNORE,
        ".env.local.example": NEXT_ENV_EXAMPLE,
        "package.json": render_template(NEXT_PACKAGE_JSON, **tokens),
        "next.config.mjs": NEXT_CONFIG,
        "jsconfig.json": NEXT_JS_CONFIG,
        "Dockerfile": NEXT_DOCKERFILE,
        "middleware.js": NEXT_MIDDLEWARE,
        "src/app/layout.js": render_template(NEXT_LAYOUT, **tokens),
        "src/app/page.js": NEXT_HOME,
        "src/app/globals.css": NEXT_GLOBALS,
        "src/app/(auth)/layout.js": NEXT_AUTH_LAYOUT,
        "src/app/(auth)/login/page.js": render_template(NEXT_LOGIN, **tokens),
        "src/app/(auth)/register/page.js": render_template(NEXT_REGISTER, **tokens),
        "src/app/(app)/layout.js": render_template(NEXT_APP_LAYOUT, **tokens),
        "src/app/(app)/dashboard/page.js": render_template(NEXT_DASHBOARD, **tokens),
        f"src/app/(app)/{tokens['PLURAL_LOWER']}/page.js": render_template(
            NEXT_LIST_TEMPLATE,
            **tokens,
            COLUMNS=_js_field_lines(primary, {"id", "created_at", "updated_at"}),
        ),
        f"src/app/(app)/{tokens['PLURAL_LOWER']}/new/page.js": render_template(
            NEXT_NEW_TEMPLATE,
            **tokens,
            FIELDS="".join(_next_input_jsx(f) for f in form_fields),
        ),
        "src/lib/api.js": render_template(NEXT_API, **tokens),
        "src/lib/auth-context.js": NEXT_AUTH_CONTEXT,
    }

