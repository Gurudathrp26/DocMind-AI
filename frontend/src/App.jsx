import React, { useEffect, useRef, useState } from "react";
import {
  auth, chat, clearSession, deleteDoc, getToken, listDocs, listModels, setSession, uploadDoc,
} from "./api.js";

function Login({ onAuthed }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    try {
      const r = await auth(mode, email, password);
      setSession(r.token, r.email);
      onAuthed();
    } catch (ex) {
      setErr(ex.message);
    }
  };

  return (
    <div className="login">
      <form onSubmit={submit} className="card">
        <h1>DocMind AI</h1>
        <p className="muted">Private, offline document Q&amp;A</p>
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input type="password" placeholder="Password (min 6)" value={password}
               onChange={(e) => setPassword(e.target.value)} required minLength={6} />
        {err && <div className="error">{err}</div>}
        <button type="submit">{mode === "login" ? "Log in" : "Create account"}</button>
        <button type="button" className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Need an account? Register" : "Have an account? Log in"}
        </button>
      </form>
    </div>
  );
}

const STATUS_LABEL = {
  queued: "Queued", parsing: "Parsing…", embedding: "Embedding…", ready: "Ready", failed: "Failed",
};

function Sidebar({ docs, refresh }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const input = useRef();

  const onFiles = async (files) => {
    setBusy(true);
    setErr("");
    try {
      for (const f of files) await uploadDoc(f);
      await refresh();
    } catch (ex) {
      setErr(ex.message);
    }
    setBusy(false);
  };

  return (
    <aside>
      <h2>Documents</h2>
      <div
        className="drop"
        onClick={() => input.current.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); onFiles([...e.dataTransfer.files]); }}
      >
        {busy ? "Uploading…" : "Drop files or click (PDF, DOCX, TXT, MD)"}
        <input ref={input} type="file" multiple hidden accept=".pdf,.docx,.txt,.md"
               onChange={(e) => onFiles([...e.target.files])} />
      </div>
      {err && <div className="error">{err}</div>}
      <ul>
        {docs.map((d) => (
          <li key={d.id}>
            <div className="row">
              <span className="name" title={d.filename}>{d.filename}</span>
              <button className="x" onClick={async () => { await deleteDoc(d.id); refresh(); }}>✕</button>
            </div>
            <span className={`badge ${d.status}`}>{STATUS_LABEL[d.status] || d.status}</span>
            {d.status === "ready" && <span className="muted"> {d.chunks} chunks</span>}
            {d.status === "failed" && <div className="error small">{d.error}</div>}
            {d.summary && <details><summary>Summary</summary><div className="summary">{d.summary}</div></details>}
          </li>
        ))}
        {docs.length === 0 && <li className="muted">No documents yet.</li>}
      </ul>
    </aside>
  );
}

function Chat() {
  const [msgs, setMsgs] = useState([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [models, setModels] = useState([]);
  const [model, setModel] = useState("");
  const end = useRef();

  useEffect(() => {
    listModels().then((m) => { setModels(m.models); setModel(m.default); }).catch(() => {});
  }, []);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  const patchLast = (fn) => setMsgs((m) => [...m.slice(0, -1), fn(m[m.length - 1])]);

  const send = async (e) => {
    e.preventDefault();
    const question = q.trim();
    if (!question || busy) return;
    setQ("");
    setBusy(true);
    setMsgs((m) => [...m, { role: "user", text: question }, { role: "ai", text: "", sources: [], stats: null }]);
    try {
      await chat(question, model, (ev) => {
        if (ev.type === "token") patchLast((x) => ({ ...x, text: x.text + ev.text }));
        if (ev.type === "sources") patchLast((x) => ({ ...x, sources: ev.sources }));
        if (ev.type === "done") patchLast((x) => ({ ...x, stats: ev.stats }));
        if (ev.type === "error") patchLast((x) => ({ ...x, text: x.text + `\n⚠ ${ev.message}` }));
      });
    } catch (ex) {
      patchLast((x) => ({ ...x, text: `⚠ ${ex.message}` }));
    }
    setBusy(false);
  };

  return (
    <main>
      <div className="topbar">
        <span className="muted">Model</span>
        <select value={model} onChange={(e) => setModel(e.target.value)}>
          {models.map((m) => <option key={m}>{m}</option>)}
        </select>
      </div>
      <div className="messages">
        {msgs.length === 0 && <p className="muted center">Upload a document, then ask a question about it.</p>}
        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble">{m.text || (busy && i === msgs.length - 1 ? "…" : "")}</div>
            {m.sources?.length > 0 && (
              <details className="sources">
                <summary>{m.sources.length} sources</summary>
                {m.sources.map((s, j) => (
                  <div key={j} className="src">
                    <b>{s.filename} · p{s.page}</b> <span className="muted">(match {s.score})</span>
                    <div>{s.text.slice(0, 220)}…</div>
                  </div>
                ))}
              </details>
            )}
            {m.stats?.model && (
              <div className="stats">
                {m.stats.model} · first token {m.stats.time_to_first_token_s}s · {m.stats.tokens_per_s} tok/s · {m.stats.total_s}s total
              </div>
            )}
          </div>
        ))}
        <div ref={end} />
      </div>
      <form onSubmit={send} className="composer">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about your documents…" disabled={busy} />
        <button disabled={busy || !q.trim()}>{busy ? "…" : "Send"}</button>
      </form>
    </main>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(!!getToken());
  const [docs, setDocs] = useState([]);

  const refresh = () => listDocs().then(setDocs).catch(() => {});

  useEffect(() => {
    if (!authed) return;
    refresh();
    const id = setInterval(refresh, 2000); // live processing status
    return () => clearInterval(id);
  }, [authed]);

  if (!authed) return <Login onAuthed={() => setAuthed(true)} />;

  return (
    <div className="app">
      <header>
        <b>DocMind AI</b>
        <span className="muted">{localStorage.getItem("email")}</span>
        <button className="link" onClick={() => { clearSession(); setAuthed(false); }}>Log out</button>
      </header>
      <div className="body">
        <Sidebar docs={docs} refresh={refresh} />
        <Chat />
      </div>
    </div>
  );
}
