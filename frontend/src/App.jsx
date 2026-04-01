import { useState, useRef, useEffect, useCallback } from "react";
import "./App.css";

const API = "http://localhost:8001";

// ── API helpers ──────────────────────────────────────────────
const apiFetch = async (path, opts = {}, token = null) => {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const r = await fetch(`${API}${path}`, { ...opts, headers });
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return r.json();
};

// ── Sub-components ───────────────────────────────────────────
function AuthScreen({ onAuth }) {
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setError(""); setLoading(true);
    try {
      const data = await apiFetch(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      onAuth(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-logo">
          <span className="logo-mark">◈</span>
          <span className="logo-text">Sapien</span>
        </div>
        <p className="auth-sub">RAG · Mistral AI · pgvector</p>

        <div className="auth-tabs">
          {["login", "register"].map(m => (
            <button key={m} className={`auth-tab ${mode === m ? "auth-tab--active" : ""}`}
              onClick={() => setMode(m)}>
              {m.toUpperCase()}
            </button>
          ))}
        </div>

        <div className="auth-fields">
          <input className="auth-input" placeholder="Username"
            value={username} onChange={e => setUsername(e.target.value)}
            onKeyDown={e => e.key === "Enter" && submit()} />
          <input className="auth-input" type="password" placeholder="Password"
            value={password} onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === "Enter" && submit()} />
        </div>

        {error && <div className="auth-error">{error}</div>}

        <button className="auth-submit" onClick={submit} disabled={loading || !username || !password}>
          {loading ? "⟳" : mode === "login" ? "Sign in →" : "Create account →"}
        </button>
      </div>
    </div>
  );
}

function SessionItem({ session, active, onSelect, onDelete }) {
  return (
    <div className={`session-item ${active ? "session-item--active" : ""}`}
      onClick={() => onSelect(session)}>
      <span className="session-title">{session.title}</span>
      <button className="session-delete" onClick={e => { e.stopPropagation(); onDelete(session.id); }}>✕</button>
    </div>
  );
}

function FileTag({ name, onRemove }) {
  return (
    <div className="file-tag">
      <span className="file-tag-icon">◈</span>
      <span className="file-tag-name">{name}</span>
      <button className="file-tag-remove" onClick={() => onRemove(name)}>✕</button>
    </div>
  );
}

function SourceBadge({ name }) {
  return <span className="source-badge">↗ {name}</span>;
}

import ReactMarkdown from 'react-markdown';

function Message({ msg }) {
  const isUser = msg.role === "user";
  return (
    <div className={`message ${isUser ? "message--user" : "message--ai"}`}>
      <div className="message-role">{isUser ? "YOU" : "Sapien"}</div>
      <div className="message-content">
        {isUser ? (
          <span style={{ whiteSpace: "pre-wrap" }}>{msg.content}</span>
        ) : (
          <ReactMarkdown>{msg.content}</ReactMarkdown>
        )}
        {msg.sources && msg.sources.length > 0 && (
          <div className="message-sources">
            {msg.sources.map(s => <SourceBadge key={s} name={s} />)}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main App ─────────────────────────────────────────────────
export default function App() {
  const [auth, setAuth] = useState(() => {
    const raw = localStorage.getItem("sapien_auth");
    return raw ? JSON.parse(raw) : null;
  });

  const [sessions, setSessions] = useState([]);
  const [activeSession, setActiveSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [docs, setDocs] = useState([]);
  const [input, setInput] = useState("");
  const [uploading, setUploading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const fileRef = useRef();
  const bottomRef = useRef();
  const token = auth?.token;

  // persist auth
  useEffect(() => {
    if (auth) localStorage.setItem("sapien_auth", JSON.stringify(auth));
    else localStorage.removeItem("sapien_auth");
  }, [auth]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const load = useCallback(async () => {
    if (!token) return;
    const [sessData, docData] = await Promise.all([
      apiFetch("/sessions", {}, token),
      apiFetch("/documents", {}, token),
    ]);
    setSessions(sessData.sessions);
    setDocs(docData.documents);
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const selectSession = async (session) => {
    setActiveSession(session);
    const data = await apiFetch(`/sessions/${session.id}/messages`, {}, token);
    setMessages(data.messages);
  };

  const newSession = async () => {
    const s = await apiFetch("/sessions", { method: "POST" }, token);
    setSessions(prev => [s, ...prev]);
    setActiveSession(s);
    setMessages([]);
  };

  const removeSession = async (id) => {
    await apiFetch(`/sessions/${id}`, { method: "DELETE" }, token);
    setSessions(prev => prev.filter(s => s.id !== id));
    if (activeSession?.id === id) { setActiveSession(null); setMessages([]); }
  };

  const uploadFile = async (file) => {
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    try {
      await fetch(`${API}/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const data = await apiFetch("/documents", {}, token);
      setDocs(data.documents);
    } catch (e) {
      alert("Upload failed: " + e.message);
    } finally {
      setUploading(false);
    }
  };

  const removeDoc = async (name) => {
    await apiFetch(`/documents/${encodeURIComponent(name)}`, { method: "DELETE" }, token);
    setDocs(docs.filter(d => d !== name));
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || streaming) return;

    let session = activeSession;
    if (!session) {
      session = await apiFetch("/sessions", { method: "POST" }, token);
      setSessions(prev => [session, ...prev]);
      setActiveSession(session);
    }

    const userMsg = { role: "user", content: text };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput("");
    setStreaming(true);

    // placeholder for streaming reply
    const aiIdx = newMessages.length;
    setMessages([...newMessages, { role: "assistant", content: "", sources: [] }]);

    const history = newMessages.slice(-10).map(m => ({ role: m.role, content: m.content }));

    const resp = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ message: text, session_id: session.id, history }),
    });

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let fullText = "";
    let sources = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        try {
          const d = JSON.parse(line.slice(5).trim());
          if (d.type === "sources") sources = d.sources;
          if (d.type === "delta") {
            fullText += d.text;
            setMessages(prev => {
              const updated = [...prev];
              updated[aiIdx] = { role: "assistant", content: fullText, sources };
              return updated;
            });
          }
          if (d.type === "done") {
            // refresh session list (title may have auto-updated)
            load();
          }
        } catch { }
      }
    }

    setStreaming(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  const logout = () => { setAuth(null); setSessions([]); setActiveSession(null); setMessages([]); setDocs([]); };

  if (!auth) return <AuthScreen onAuth={d => setAuth(d)} />;

  return (
    <div className="app">
      {/* History sidebar */}
      <nav className="history-sidebar">
        <div className="history-header">
          <div className="logo">
            <span className="logo-mark">◈</span>
            <span className="logo-text">Sapien</span>
          </div>
          <button className="new-chat-btn" onClick={newSession}>+ New chat</button>
        </div>

        <div className="session-list">
          {sessions.length === 0 && <div className="empty-sessions">No conversations yet</div>}
          {sessions.map(s => (
            <SessionItem key={s.id} session={s}
              active={activeSession?.id === s.id}
              onSelect={selectSession}
              onDelete={removeSession} />
          ))}
        </div>

        <div className="history-footer">
          <span className="username-chip">@{auth.username}</span>
          <button className="logout-btn" onClick={logout}>Sign out</button>
        </div>
      </nav>

      {/* Docs sidebar */}
      <aside className="sidebar">
        <div className="section-label">KNOWLEDGE BASE</div>

        <div
          className={`drop-zone ${dragOver ? "drop-zone--active" : ""} ${uploading ? "drop-zone--uploading" : ""}`}
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={e => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) uploadFile(f); }}
          onClick={() => fileRef.current?.click()}
        >
          <input ref={fileRef} type="file" accept=".pdf,.txt,.doc,.docx" hidden onChange={e => { const f = e.target.files[0]; if (f) uploadFile(f); }} />
          <div className="drop-zone-icon">{uploading ? "⟳" : "⊕"}</div>
          <div className="drop-zone-text">{uploading ? "Ingesting…" : "Drop or click"}</div>
          <div className="drop-zone-hint">PDF · TXT · DOCX</div>
        </div>

        <div className="file-list">
          {docs.length === 0 && <div className="empty-docs">No documents</div>}
          {docs.map(d => <FileTag key={d} name={d} onRemove={removeDoc} />)}
        </div>

        <div className="model-info">
          <span className="model-chip">mistral-large-latest</span>
          <span className="model-chip">mistral-embed</span>
          <span className="model-chip">pgvector</span>
        </div>
      </aside>

      {/* Main chat */}
      <main className="chat">
        <div className="chat-messages">
          {messages.length === 0 && (
            <div className="empty-state">
              <div className="empty-state-glyph">◈</div>
              <div className="empty-state-title">
                {activeSession ? activeSession.title : "Start a new chat"}
              </div>
              <div className="empty-state-sub">
                Upload documents then ask anything about them.
              </div>
            </div>
          )}
          {messages.map((m, i) => <Message key={i} msg={m} />)}
          {streaming && messages[messages.length - 1]?.content === "" && (
            <div className="message message--ai">
              <div className="message-role">Sapien</div>
              <div className="message-content">
                <span className="thinking"><span>▪</span><span>▪</span><span>▪</span></span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="chat-input-area">
          <div className="input-wrapper">
            <textarea className="chat-input"
              placeholder="Ask a question about your documents…"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1} />
            <button className={`send-btn ${streaming ? "send-btn--loading" : ""}`}
              onClick={sendMessage} disabled={streaming || !input.trim()}>
              {streaming ? "⟳" : "↑"}
            </button>
          </div>
          <div className="input-hint">Enter to send · Shift+Enter for newline</div>
        </div>
      </main>
    </div>
  );
}
