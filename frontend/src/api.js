const BASE = "/api";

export const getToken = () => localStorage.getItem("token");
export const setSession = (token, email) => {
  localStorage.setItem("token", token);
  localStorage.setItem("email", email);
};
export const clearSession = () => {
  localStorage.removeItem("token");
  localStorage.removeItem("email");
};

function headers(json = true) {
  const h = {};
  if (json) h["Content-Type"] = "application/json";
  const t = getToken();
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

async function handle(res) {
  if (res.status === 401 && getToken()) {
    clearSession();
    window.location.reload();
  }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

export const auth = (mode, email, password) =>
  fetch(`${BASE}/${mode}`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ email, password }),
  }).then(handle);

export const listDocs = () => fetch(`${BASE}/documents`, { headers: headers() }).then(handle);

export const uploadDoc = (file) => {
  const fd = new FormData();
  fd.append("file", file);
  return fetch(`${BASE}/documents`, { method: "POST", headers: headers(false), body: fd }).then(handle);
};

export const deleteDoc = (id) =>
  fetch(`${BASE}/documents/${id}`, { method: "DELETE", headers: headers() }).then(handle);

export const listModels = () => fetch(`${BASE}/models`, { headers: headers() }).then(handle);

// Streams the answer. Calls onEvent for each {type: token|sources|done|error}.
export async function chat(question, model, onEvent) {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ question, model }),
  });
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop();
    for (const p of parts) {
      if (p.startsWith("data: ")) onEvent(JSON.parse(p.slice(6)));
    }
  }
}
