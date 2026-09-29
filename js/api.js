const CWU_API = "https://cyberworld-university.onrender.com/api";

async function cwuApi(path, options = {}) {
  const response = await fetch(CWU_API + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || data.message || ("Request failed (" + response.status + ")"));
  }
  return data;
}

async function cwuCurrentUser() {
  return cwuApi("/auth/me");
}
