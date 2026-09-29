// Cyber World University — shared UI helpers.
// Business data is handled by Firebase Authentication and the Flask API.

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[character]));
}

function toast(message) {
  const element = document.getElementById("toast");
  if (!element) return;
  element.textContent = message;
  element.classList.add("show");
  window.setTimeout(() => element.classList.remove("show"), 2200);
}

function showToast(message) {
  toast(message);
}

function toggleMenu() {
  document.getElementById("mainNav")?.classList.toggle("open");
}

async function logout() {
  try {
    if (window.CWU?.logout) await window.CWU.logout();
  } finally {
    localStorage.removeItem("cwu_user");
    location.href = location.pathname.includes("/admin/") ? "../login.html" : "login.html";
  }
}

window.CWU_UI = { esc, toast, showToast, toggleMenu, logout };
