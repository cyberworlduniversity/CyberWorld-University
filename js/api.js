const CWU_API = window.CWU_API || "http://127.0.0.1:5000/api";

async function cwuApi(path, options = {}) {
  const response = await fetch(CWU_API + path, {
    credentials: "include",
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
    ...options
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

async function cwuCurrentUser() {
  return cwuApi("/auth/me");
}
