const $ = (s, el = document) => el.querySelector(s);
const MANAGERS = ["ceo", "admin", "super_admin", "hr", "hr_manager", "manager", "stakeholder"];
const state = {
  route: location.pathname,
  token: localStorage.getItem("jwt") || "",
  user: JSON.parse(localStorage.getItem("user") || "null"),
  authTab: "login",
  messages: [],
  history: [],
  docs: [],
  vaults: [],
  vault: "general",
  users: [],
  logs: [],
  stats: null,
  tab: "documents",
  streaming: false,
  sideOpen: false,
  theme: localStorage.getItem("theme") || "dark",
};
document.documentElement.setAttribute("data-theme", state.theme);

function headers() {
  const tok = state.token || localStorage.getItem("jwt") || "";
  state.token = tok;
  const h = { "Content-Type": "application/json" };
  if (tok) {
    h.Authorization = "Bearer " + tok;
    h["X-Access-Token"] = tok;
  }
  return h;
}
async function api(path, opts = {}) {
  const res = await fetch(path, { credentials: "include", ...opts, headers: { ...headers(), ...(opts.headers || {}) } });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = j.detail || JSON.stringify(j);
    } catch (e) {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return res.json();
}
function nav(path) {
  history.pushState({}, "", path);
  state.route = path;
  state.sideOpen = false;
  render();
}
window.addEventListener("popstate", () => {
  state.route = location.pathname;
  render();
});
function esc(s) {
  return (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function toggleTheme() {
  state.theme = state.theme === "dark" ? "light" : "dark";
  localStorage.setItem("theme", state.theme);
  document.documentElement.setAttribute("data-theme", state.theme);
  render();
}
function themeBtn() {
  return `<button class="theme" type="button" onclick="toggleTheme()">${state.theme === "dark" ? "Light" : "Dark"}</button>`;
}

function loginView() {
  const tab = state.authTab || "login";
  return `<div class="login">
    <div class="login-top">${themeBtn()}</div>
    <div class="login-card">
      <p class="kicker">Enterprise AI</p>
      <h1>Sign in to your workspace</h1>
      <p class="sub">Use your work email. Company names stay private until you are inside.</p>
      <div class="tabs">
        <button type="button" class="btn ghost ${tab === "login" ? "on" : ""}" onclick="state.authTab='login';render()">Sign in</button>
        <button type="button" class="btn ghost ${tab === "register" ? "on" : ""}" onclick="state.authTab='register';render()">Create account</button>
      </div>
      ${
        tab === "login"
          ? `<form onsubmit="doLogin(event)">
        <input class="field" name="email" type="email" required placeholder="you@company.com" autocomplete="username" />
        <input class="field" name="password" type="password" required placeholder="Password" autocomplete="current-password" />
        <button class="btn" type="submit">Sign in</button>
      </form>`
          : `<form onsubmit="doRegister(event)">
        <input class="field" name="company_name" required placeholder="Organization name" />
        <input class="field" name="name" required placeholder="Your full name" />
        <input class="field" name="email" type="email" required placeholder="you@company.com" />
        <select class="field" name="role">
          <option value="ceo">I am the CEO / owner</option>
          <option value="stakeholder">I am a stakeholder</option>
          <option value="hr">I am HR</option>
          <option value="manager">I am a manager / faculty</option>
          <option value="employee">I am an employee / student</option>
        </select>
        <input class="field" name="password" type="password" required minlength="8" placeholder="Password (min 8)" />
        <p class="hint">First person on a new work domain becomes CEO.</p>
        <button class="btn" type="submit">Continue</button>
      </form>`
      }
      <p class="err" id="loginErr"></p>
      <p class="ok" id="loginOk"></p>
    </div>
  </div>`;
}

async function doLogin(ev) {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: fd.get("email"), password: fd.get("password") }),
    });
    state.token = data.access_token;
    state.user = data.user;
    localStorage.setItem("jwt", state.token);
    localStorage.setItem("user", JSON.stringify(state.user));
    nav("/chat");
  } catch (e) {
    $("#loginErr").textContent = e.message;
  }
}
async function doRegister(ev) {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  try {
    const data = await api("/auth/register-org", {
      method: "POST",
      body: JSON.stringify({
        company_name: fd.get("company_name"),
        name: fd.get("name"),
        email: fd.get("email"),
        password: fd.get("password"),
        role: fd.get("role"),
      }),
    });
    if (data.pending) {
      $("#loginOk").textContent = data.message;
      return;
    }
    state.token = data.access_token;
    state.user = data.user;
    localStorage.setItem("jwt", state.token);
    localStorage.setItem("user", JSON.stringify(state.user));
    nav("/chat");
  } catch (e) {
    $("#loginErr").textContent = e.message;
  }
}

function chatView() {
  const u = state.user || {};
  const initial = (u.company_name || "E").slice(0, 1).toUpperCase();
  return `<div class="scrim ${state.sideOpen ? "on" : ""}" onclick="state.sideOpen=false;render()"></div>
  <div class="shell">
    <aside class="side ${state.sideOpen ? "open" : ""}">
      <div class="side-pad" style="display:flex;align-items:center;gap:10px">
        <div class="av">${initial}</div>
        <div style="min-width:0">
          <div style="font-weight:600;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(u.company_name || "")}</div>
          <div style="font-size:11px;color:var(--faint)">Private workspace</div>
        </div>
      </div>
      <div class="side-pad" style="padding-top:0">
        <button class="nav" onclick="nav('/library')">Document workspace</button>
        <button class="nav" onclick="newChat()">New chat</button>
        <label class="nav fill">Upload company document
          <input type="file" accept=".pdf,.docx,.xlsx,.txt,.md" onchange="chatUpload(event)" style="display:none" />
        </label>
        <p class="hint" id="chatUpMsg"></p>
      </div>
      <div class="sec">Knowledge</div>
      <div class="scroll" style="max-height:28vh">
        ${(state.docs || []).length
          ? state.docs.slice(0, 20).map((d) => `<div class="row">${esc(d.filename)} · ${d.chunk_count || 0}</div>`).join("")
          : `<div class="row">No files yet. Upload above.</div>`}
      </div>
      <div class="sec">Chats</div>
      <div class="scroll" style="flex:1">
        ${(state.history || []).map((h) => `<div style="display:flex;align-items:center;gap:4px;padding-right:6px">
          <button class="hist" style="flex:1" onclick="loadHist(${h.id})">${esc((h.query || "Chat").slice(0, 56))}</button>
          <button type="button" title="Delete this chat" onclick="event.stopPropagation();deleteChat(${h.id})" style="border:0;background:transparent;color:var(--faint);cursor:pointer;font-size:14px;padding:4px 6px">✕</button>
        </div>`).join("") || `<div class="row">No chats yet.</div>`}
      </div>
      <div class="foot">
        <div style="font-size:13px;font-weight:500">${esc(u.name || "")}</div>
        <div style="font-size:11px;color:var(--faint);text-transform:capitalize">${esc(u.role || "")} · ${esc(u.department || "General")}</div>
        <div style="margin-top:8px;display:flex;gap:12px;font-size:12px">
          <a href="/library" onclick="event.preventDefault();nav('/library')" style="color:var(--muted)">Documents</a>
          ${MANAGERS.includes(u.role) ? `<a href="/admin-ui" onclick="event.preventDefault();nav('/admin-ui')" style="color:var(--muted)">Admin</a>` : ""}
          <button type="button" onclick="logout()" style="background:0;border:0;color:var(--danger);cursor:pointer;padding:0">Log out</button>
        </div>
      </div>
    </aside>
    <section class="main">
      <header class="top">
        <div style="display:flex;align-items:center;gap:10px;min-width:0">
          <button class="menu" type="button" onclick="state.sideOpen=!state.sideOpen;render()">☰</button>
          <div style="min-width:0">
            <div style="font-weight:600;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(u.company_name)} AI</div>
            <div style="font-size:11px;color:var(--faint)">Company knowledge only</div>
          </div>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          ${state.messages.length ? `<button class="theme" type="button" onclick="clearCurrentChat()">Delete chat</button>` : ""}
          ${themeBtn()}
        </div>
      </header>
      <div id="thread" class="thread scroll">
        <div class="inner">
          ${state.messages.length === 0 ? emptyState(u) : state.messages.map(messageHtml).join("")}
          ${state.streaming ? `<p class="hint">Thinking…</p>` : ""}
        </div>
      </div>
      <div class="composer">
        <form class="composer-in" onsubmit="sendChat(event)">
          <div class="box">
            <button class="icon" type="button" title="New chat" onclick="newChat()">＋</button>
            <textarea name="q" rows="1" placeholder="Message ${esc(u.company_name || "your")} AI" oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,140)+'px'"></textarea>
            <button class="send" type="submit">↑</button>
          </div>
          <p class="hint" style="text-align:center">＋ starts a new chat. Upload files in Document workspace.</p>
        </form>
      </div>
    </section>
  </div>`;
}

function emptyState(u) {
  return `<div style="text-align:center;padding:48px 8px">
    <div style="font-size:clamp(22px,5vw,28px);font-weight:600;letter-spacing:-.03em;margin-bottom:10px">How can I help?</div>
    <p class="sub" style="max-width:440px;margin:0 auto">Private assistant for ${esc(u.company_name || "your company")}. Upload a handbook, then ask.</p>
  </div>`;
}
function messageHtml(m) {
  const src = (m.sources || []).map((s) => `<span class="src">${esc(s.file || "doc")} · p.${s.page || "?"}</span>`).join("");
  return `<div class="msg ${m.role}">
    <div class="av">${m.role === "user" ? "You" : "AI"}</div>
    <div class="bub">${esc(m.content)}${src ? `<div>${src}</div>` : ""}</div>
  </div>`;
}
function newChat() {
  state.messages = [];
  render();
}
function clearCurrentChat() {
  state.messages = [];
  render();
}
async function deleteChat(id) {
  if (!confirm("Delete this chat?")) return;
  try {
    await api("/chat/history/" + id, { method: "DELETE" });
  } catch (e) {}
  state.history = (state.history || []).filter((h) => h.id !== id);
  if (state.messages.length && state.history.every((h) => h.query !== state.messages[0].content)) {
    state.messages = [];
  }
  render();
}

async function sendChat(ev) {
  ev.preventDefault();
  const q = ev.target.q.value.trim();
  if (!q) return;
  ev.target.q.value = "";
  state.messages.push({ role: "user", content: q });
  state.messages.push({ role: "assistant", content: "", sources: [] });
  state.streaming = true;
  render();
  try {
    const tok = state.token || localStorage.getItem("jwt") || "";
    if (!tok) throw new Error("Please sign in again.");
    const res = await fetch("/chat", {
      method: "POST",
      credentials: "include",
      headers: headers(),
      body: JSON.stringify({
        message: q,
        access_token: tok,
        history: state.messages.slice(0, -2).map((m) => ({ role: m.role, content: m.content })),
      }),
    });
    if (!res.ok) {
      let msg = "Chat failed";
      try {
        const j = await res.json();
        msg = j.detail || msg;
      } catch (e) {}
      throw new Error(msg);
    }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop();
      for (const p of parts) {
        if (!p.startsWith("data:")) continue;
        let j;
        try {
          j = JSON.parse(p.slice(5).trim());
        } catch (e) {
          continue;
        }
        const last = state.messages[state.messages.length - 1];
        if (j.token) last.content += j.token;
        if (j.done) last.sources = j.sources || [];
      }
      const inner = $(".inner");
      if (inner) inner.innerHTML = state.messages.map(messageHtml).join("");
      const th = $("#thread");
      if (th) th.scrollTop = th.scrollHeight;
    }
  } catch (e) {
    state.messages[state.messages.length - 1].content = "Could not get a reply: " + e.message;
  }
  state.streaming = false;
  await loadHistory();
  render();
}

async function chatUpload(ev) {
  const file = ev.target.files && ev.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  fd.append("department", (state.user && state.user.department) || "general");
  fd.append("access_level", "general");
  fd.append("access_token", state.token || localStorage.getItem("jwt") || "");
  const el = $("#chatUpMsg");
  if (el) el.textContent = "Uploading " + file.name + "…";
  try {
    const res = await fetch("/documents/upload", {
      method: "POST",
      credentials: "include",
      headers: { Authorization: "Bearer " + (state.token || ""), "X-Access-Token": state.token || "" },
      body: fd,
    });
    const j = await res.json();
    if (!res.ok) throw new Error(j.detail || "upload failed");
    await pollChatJob(j.job_id);
  } catch (e) {
    if (el) el.textContent = e.message;
  }
  ev.target.value = "";
}
async function pollChatJob(id) {
  const j = await api("/ingest/status/" + id);
  const el = $("#chatUpMsg");
  if (el) el.textContent = (j.status === "done" ? "Ready · " : "") + (j.message || j.status);
  if (j.status === "queued" || j.status === "processing") setTimeout(() => pollChatJob(id), 800);
  else {
    await loadDocs();
    render();
  }
}
async function loadDocs(vault) {
  try {
    const q = vault ? "?vault=" + encodeURIComponent(vault) : "";
    state.docs = await api("/documents" + q);
  } catch (e) {
    state.docs = state.docs || [];
  }
}
async function loadHistory() {
  try {
    state.history = await api("/chat/history");
  } catch (e) {
    state.history = [];
  }
}
function loadHist(id) {
  const h = state.history.find((x) => x.id === id);
  if (!h) return;
  state.messages = [
    { role: "user", content: h.query },
    { role: "assistant", content: h.response, sources: h.sources },
  ];
  render();
}
async function logout() {
  try {
    await api("/auth/logout", { method: "POST" });
  } catch (e) {}
  state.token = "";
  state.user = null;
  localStorage.removeItem("jwt");
  localStorage.removeItem("user");
  nav("/login");
}

function adminView() {
  const tabs = ["documents", "users", "logs", "stats"];
  return `<div class="shell" style="display:block">
    <header class="top">
      <div style="font-weight:600">${esc(state.user?.company_name || "")} · Admin</div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        ${themeBtn()}
        <button class="btn ghost" onclick="nav('/chat')">Chat</button>
        <button class="btn ghost" onclick="logout()">Log out</button>
      </div>
    </header>
    <div class="inner">
      <div class="tabs">${tabs.map((t) => `<button class="btn ghost ${state.tab === t ? "on" : ""}" onclick="state.tab='${t}';render()">${t}</button>`).join("")}</div>
      ${adminTab()}
    </div>
  </div>`;
}
function adminTab() {
  if (state.tab === "documents")
    return `<form class="login-card" style="margin:12px 0" onsubmit="uploadDoc(event)">
      <div style="font-weight:600;margin-bottom:8px">Upload knowledge</div>
      <input type="file" name="file" required />
      <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
        <input class="field" style="margin:0;flex:1" name="department" placeholder="department" />
        <select class="field" style="margin:0;flex:1" name="access_level">${["general", "hr", "finance", "it"].map((a) => `<option>${a}</option>`).join("")}</select>
      </div>
      <button class="btn" style="margin-top:10px">Ingest</button>
      <p class="hint" id="upMsg"></p>
    </form>
    <div class="scroll">${(state.docs || []).map((d) => `<div class="row">${esc(d.filename)} · ${d.access_level} · ${d.chunk_count}</div>`).join("")}</div>`;
  if (state.tab === "users")
    return `<form class="login-card" style="margin:12px 0" onsubmit="addUser(event)">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
        <input class="field" style="margin:0" name="name" placeholder="name" />
        <input class="field" style="margin:0" name="email" placeholder="email" />
        <select class="field" style="margin:0" name="role"><option>employee</option><option>manager</option><option>hr</option></select>
        <input class="field" style="margin:0" name="department" placeholder="department" />
      </div>
      <button class="btn" style="margin-top:10px">Add user</button>
    </form>
    ${(state.users || []).map((u) => `<div class="row">${esc(u.name)} · ${esc(u.email)} · ${esc(u.role)} · ${esc(u.status || "")}</div>`).join("")}`;
  if (state.tab === "logs")
    return (state.logs || []).map((l) => `<div class="row">${esc(l.created_at || "")} · ${esc(l.query)}</div>`).join("");
  const s = state.stats || {};
  return `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-top:12px">${[
    ["Queries", s.queries_30d],
    ["Users", s.active_users],
    ["Latency", s.avg_latency_ms],
    ["Docs", s.documents],
  ]
    .map(([k, v]) => `<div class="login-card" style="padding:16px"><div class="hint" style="margin:0">${k}</div><div style="font-size:24px;font-weight:600">${v ?? "—"}</div></div>`)
    .join("")}</div>`;
}
async function uploadDoc(ev) {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  fd.append("access_token", state.token || "");
  const res = await fetch("/documents/upload", {
    method: "POST",
    credentials: "include",
    headers: { Authorization: "Bearer " + state.token, "X-Access-Token": state.token || "" },
    body: fd,
  });
  const j = await res.json();
  $("#upMsg").textContent = "Queued " + j.job_id;
  pollJob(j.job_id);
}
async function pollJob(id) {
  const j = await api("/ingest/status/" + id);
  if ($("#upMsg")) $("#upMsg").textContent = j.status + " " + (j.message || "");
  if (j.status === "queued" || j.status === "processing") setTimeout(() => pollJob(id), 800);
  else {
    await loadAdmin();
    render();
  }
}
async function addUser(ev) {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  await api("/admin/users", {
    method: "POST",
    body: JSON.stringify({
      name: fd.get("name"),
      email: fd.get("email"),
      role: fd.get("role"),
      department: fd.get("department"),
      password: "Password@123",
    }),
  });
  await loadAdmin();
  render();
}
async function loadAdmin() {
  try {
    state.docs = await api("/documents");
  } catch (e) {
    state.docs = [];
  }
  try {
    state.users = await api("/admin/users");
  } catch (e) {
    state.users = [];
  }
  try {
    state.logs = await api("/admin/logs");
  } catch (e) {
    state.logs = [];
  }
  try {
    state.stats = await api("/admin/stats");
  } catch (e) {
    state.stats = null;
  }
}

function libraryView() {
  const u = state.user || {};
  const vaults = state.vaults || [];
  const current = state.vault || (vaults[0] && vaults[0].id) || "general";
  const active = vaults.find((v) => v.id === current) || vaults[0];
  const files = (state.docs || []).filter((d) => !current || d.access_level === current);
  return `<div class="shell">
    <aside class="side ${state.sideOpen ? "open" : ""}">
      <div class="side-pad">
        <div style="font-weight:600;font-size:14px">${esc(u.company_name || "")}</div>
        <div class="hint">Document workspace</div>
        <button class="nav" onclick="nav('/chat')">Back to chat</button>
      </div>
      <div class="sec">Vaults you can open</div>
      <div class="scroll" style="flex:1">
        ${vaults
          .map(
            (v) => `<button class="hist" onclick="openVault('${v.id}')" style="${v.id === current ? "background:var(--soft);color:var(--text)" : ""}">${esc(v.title)}</button>`
          )
          .join("")}
      </div>
      <div class="foot">
        <div style="font-size:12px;color:var(--faint)">Vaults you cannot access are hidden.</div>
      </div>
    </aside>
    <section class="main">
      <header class="top">
        <div style="display:flex;align-items:center;gap:10px">
          <button class="menu" type="button" onclick="state.sideOpen=!state.sideOpen;render()">☰</button>
          <div>
            <div style="font-weight:600">${esc((active && active.title) || "Documents")}</div>
            <div class="hint" style="margin:0">${esc((active && active.blurb) || "")}</div>
          </div>
        </div>
        ${themeBtn()}
      </header>
      <div class="thread scroll">
        <div class="inner">
          ${
            active && active.can_upload
              ? `<form class="login-card" style="margin-bottom:18px;width:100%" onsubmit="uploadVaultDoc(event)">
            <div style="font-weight:600;margin-bottom:6px">Add a file to ${esc(active.title)}</div>
            <p class="hint">Stored only for ${esc(u.company_name || "this company")}. Chat will only retrieve it for people allowed in this vault.</p>
            <input type="file" name="file" required />
            <input type="hidden" name="access_level" value="${esc(active.id)}" />
            <button class="btn" style="margin-top:12px;max-width:220px">Upload into this vault</button>
            <p class="hint" id="libUp"></p>
          </form>`
              : `<p class="hint">You can read this vault when you ask in chat. You cannot add files here.</p>`
          }
          <div class="sec" style="padding-left:0">Files in this vault</div>
          ${
            files.length
              ? files
                  .map(
                    (d) => `<div class="login-card" style="margin:8px 0;padding:14px 16px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap">
              <div>
                <div style="font-weight:600">${esc(d.filename)}</div>
                <div class="hint" style="margin:4px 0 0">${esc(d.file_type)} · ${d.chunk_count || 0} chunks · ${esc(d.access_level)}</div>
              </div>
            </div>`
                  )
                  .join("")
              : `<p class="sub">No documents in this vault yet.</p>`
          }
        </div>
      </div>
    </section>
  </div>`;
}
async function openVault(id) {
  state.vault = id;
  await loadDocs(id);
  render();
}
async function loadVaults() {
  try {
    state.vaults = await api("/documents/vaults");
  } catch (e) {
    state.vaults = [{ id: "general", title: "Company-wide", blurb: "Everyone", can_upload: true }];
  }
}
async function uploadVaultDoc(ev) {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  fd.append("access_token", state.token || "");
  fd.append("department", (state.user && state.user.department) || "general");
  const res = await fetch("/documents/upload", {
    method: "POST",
    credentials: "include",
    headers: { Authorization: "Bearer " + (state.token || ""), "X-Access-Token": state.token || "" },
    body: fd,
  });
  const j = await res.json();
  if (!res.ok) {
    $("#libUp").textContent = j.detail || "Upload failed";
    return;
  }
  $("#libUp").textContent = "Indexing…";
  await pollLib(j.job_id);
}
async function pollLib(id) {
  const j = await api("/ingest/status/" + id);
  if ($("#libUp")) $("#libUp").textContent = j.status + " " + (j.message || "");
  if (j.status === "queued" || j.status === "processing") setTimeout(() => pollLib(id), 800);
  else {
    await loadDocs(state.vault);
    render();
  }
}

function render() {
  const root = $("#app");
  const path = state.route.split("?")[0];
  if (!state.user && path !== "/" && path !== "/login") {
    nav("/login");
    return;
  }
  if (path === "/chat") root.innerHTML = chatView();
  else if (path === "/library") root.innerHTML = libraryView();
  else if (path === "/admin-ui") root.innerHTML = adminView();
  else root.innerHTML = loginView();
}

(async function init() {
  if (state.user && (location.pathname === "/" || location.pathname === "/login")) state.route = "/chat";
  if (state.user) {
    await loadHistory();
    await loadDocs();
  }
  if (location.pathname === "/admin-ui") await loadAdmin();
  render();
})();
