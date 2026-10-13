// Atlas front end (Chart Room). No build step, no dependencies. Hash routes:
//   #/ home · #/chat operator + workbench · #/projects · #/graph constellation · #/t/<type> list
//   #/e/<path> note (a project gets its own page) · #/search?q=… · #/rediscover · #/missing/<name>

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const main = $("#main");
const state = { meta: null, current: null, chatOpen: false, operator: { mode: "standalone" }, chatMessages: [], titles: {}, ctxOn: true };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const enc = encodeURIComponent;
const api = async (path, opts = {}) => {
  opts.headers = { ...(opts.headers || {}), "x-atlas": "1" };  // writes and deep search need it (CSRF guard)
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
};
const post = (path, body, extra = {}) => api(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), ...extra });
const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
};
const toast = (text) => {
  const t = $("#toast");
  t.textContent = text; t.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => (t.hidden = true), 2800);
};

// ------------------------------------------------------------------ undo: an action waits five seconds before it leaves
// Keep, Let go, a note and a snooze are held back for five seconds; Undo (or ⌘Z) drops them before
// they reach the agent. Leaving or hiding the page sends what is still waiting (`leaving`: keepalive).
const MOD = /Mac|iPhone|iPad/.test(navigator.userAgent) ? "⌘" : "Ctrl+";
const held = new Map();
let heldSeq = 0;
function withUndo(label, run, undo = null) {
  const id = ++heldSeq;
  const fire = (leaving = false) => { if (!held.delete(id)) return; renderUndo(); run(leaving); };
  held.set(id, { label, fire, undo, timer: setTimeout(fire, 5000) });
  renderUndo();
}
const sendHeld = () => { for (const h of [...held.values()]) { clearTimeout(h.timer); h.fire(true); } };
function undoLast() {
  const id = [...held.keys()].at(-1);
  if (id === undefined) return false;
  const h = held.get(id);
  clearTimeout(h.timer); held.delete(id); renderUndo(); h.undo?.(); toast(`Undone: ${h.label}`);
  return true;
}
function renderUndo() {
  const box = $("#undo"), last = [...held.values()].at(-1);
  document.body.classList.toggle("undo-on", !!last);
  if (!last) { box.hidden = true; return; }
  box.innerHTML = `<span class="t">${esc(last.label)}${held.size > 1 ? ` <span class="n">+${held.size - 1}</span>` : ""}</span><button type="button" class="undo-btn">Undo <kbd>${MOD}Z</kbd></button>`;
  box.hidden = false;
  box.querySelector(".undo-btn").onclick = undoLast;
}
addEventListener("pagehide", sendHeld);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") sendHeld(); });  // phones may never fire pagehide

// ------------------------------------------------------------------ time
const pad = (n) => String(n).padStart(2, "0");
const localDay = (d = new Date()) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const toDate = (iso) => new Date(iso.length <= 10 ? iso + "T12:00:00" : iso);
const clock = (iso) => { const d = toDate(iso); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const shortDay = (day) => toDate(day).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
function dayLabel(day) {
  const diff = Math.round((toDate(localDay()) - toDate(day)) / 864e5);
  return diff === 0 ? "Today" : diff === 1 ? "Yesterday" : shortDay(day);
}
const rel = (iso) => {
  if (!iso) return "";
  const days = Math.floor((toDate(localDay()) - toDate(iso.slice(0, 10))) / 864e5);
  if (days <= 0) return "today"; if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`; if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
};
const since = (iso) => {
  const s = Math.max(0, (Date.now() - toDate(iso)) / 1000);
  return s < 90 ? "just now" : s < 3600 ? `${Math.round(s / 60)}m` : s < 86400 * 2 ? `${Math.round(s / 3600)}h` : `${Math.round(s / 86400)}d`;
};

// ------------------------------------------------------------------ icons, glyphs, avatars
const P = {
  check: '<path d="M3.5 8.5l3 3 6-7"/>', arrow: '<path d="M3 8h10M9 4l4 4-4 4"/>', plus: '<path d="M8 3v10M3 8h10"/>',
  eye: '<path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8Z"/><circle cx="8" cy="8" r="2"/>',
  clock: '<circle cx="8" cy="8" r="5.6"/><path d="M8 5v3l2 1.5"/>', info: '<circle cx="8" cy="8" r="6"/><path d="M8 7.2V11M8 5v.1"/>',
  warn: '<circle cx="8" cy="8" r="6"/><path d="M8 4.8v3.6M8 11v.1"/>', block: '<circle cx="8" cy="8" r="6"/><path d="M4 12 12 4"/>',
  link: '<path d="M6.5 9.5 9.5 6.5M7 4.5l1-1a2.5 2.5 0 0 1 3.5 3.5l-1 1M9 11.5l-1 1A2.5 2.5 0 0 1 4.5 9l1-1"/>',
  star: '<path d="m8 2 1.8 3.8 4.2.5-3.1 2.9.8 4.1L8 11.3l-3.7 2 .8-4.1L2 6.3l4.2-.5Z"/>', x: '<path d="M4 4l8 8M12 4l-8 8"/>',
  pen: '<path d="M10.5 2.8 13.2 5.5 6 12.7l-3.2.5.5-3.2Z"/>', down: '<path d="m4 6 4 4 4-4"/>', left: '<path d="m10 4-4 4 4 4"/>', right: '<path d="m6 4 4 4-4 4"/>',
  shield: '<path d="M8 1.8 13 3.8v4c0 3-2.2 5.2-5 6.4-2.8-1.2-5-3.4-5-6.4v-4Z"/>', copy: '<rect x="5" y="5" width="8.5" height="8.5" rx="1.5"/><path d="M3 10.5V3.5A1 1 0 0 1 4 2.5h6.5"/>',
  play: '<path d="M5 3.2v9.6a.6.6 0 0 0 .9.5l7.4-4.8a.6.6 0 0 0 0-1L5.9 2.7a.6.6 0 0 0-.9.5Z" fill="currentColor" stroke="none"/>',
  send: '<path d="M8 13V3M3.5 7.5 8 3l4.5 4.5"/>',
};
const svg = (name, cls = "") => `<svg class="i ${cls}" viewBox="0 0 16 16" aria-hidden="true">${P[name]}</svg>`;
const g = (type) => `<span class="g" data-t="${esc(type)}" aria-hidden="true"></span>`;

const AGENT_SLOT = { claude: 1, codex: 2 };
function agentSlot(id) {
  if (!id) return 3;
  if (AGENT_SLOT[id]) return AGENT_SLOT[id];
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return 3 + (h % 4);
}
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);
const agentName = (id) => (id === "user" ? "You" : id ? state.meta?.agents?.find((a) => a.id === id)?.title || cap(id) : "Your agent");
const userInitial = () => (state.meta?.user?.name || "You").trim()[0].toUpperCase();
function avatar(id, size = "", dot = null) {
  if (id === "user") return `<span class="av you ${size}" aria-hidden="true">${esc(userInitial())}</span>`;
  const slot = agentSlot(id), mono = id ? cap(id.slice(0, 2)) : "Ag";
  return `<span class="av ${size}${slot % 2 === 0 ? " sq" : ""}" style="--av:var(--agent-${slot})" aria-hidden="true">${esc(mono)}${dot ? `<span class="dot ${dot}"></span>` : ""}</span>`;
}
function authorAvatar(ev, size = "m") {
  if (ev.agent) return avatar(ev.agent, size);
  return `<span class="av ${size}" style="--av:var(--soft)" aria-hidden="true">${esc((ev.author || "?").trim()[0]?.toUpperCase() || "?")}</span>`;
}
const agentBadge = (id, label) => id === "user" ? `<span class="badge">${esc(label)} you</span>`
  : `<span class="badge agent" style="--av:var(--agent-${agentSlot(id)})">${esc(label)} ${esc(id)}</span>`;

const typeOf = (t) => state.meta?.types.find((x) => x.id === t);
const typeLabel = (t) => typeOf(t)?.label ?? t;
const stripEmoji = (s) => String(s || "").replace(/^[\p{Extended_Pictographic}️‍\s]+/u, "");
const remember = (list) => { for (const e of list || []) if (e?.id) state.titles[e.id] = e.title; return list; };
const titleOf = (id) => state.titles[id] || String(id || "").split("/").pop().replace(/\.md$/, "").replace(/[-_]/g, " ");
const inline = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
  .replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');

// What a reader must know before trusting a page (polish must not make provisional material look accepted).
function epistemic(e) {
  const f = e.facts || {}, m = e.meta || {};
  if (e.type === "capture") return m.kind === "operational" || f.kind === "operational"
    ? ["info", "Operational capture: something noticed in a project, not research. It resolves into a thread, decision or lesson."]
    : ["info", "Pending capture: raw research, not yet knowledge. Its claims become insights once they are distilled and traced to a source."];
  if (m.superseded_by || f.superseded_by) return ["quiet", "Superseded: a newer note replaces this one."];
  if (e.type === "insight") {
    const due = f.revisit_after && String(f.revisit_after) <= localDay();
    if (due) return ["attn", `Revisit due since ${f.revisit_after}: its evidence may have moved.`];
    if (e.status === "speculative") return ["note", "Speculative: a claim we are willing to defend, not settled."];
  }
  if (e.type === "deep") return ["quiet", "Historical archive: read-only, written before the current system."];
  if (e.type === "frame") return ["note", "Research frame: graded evidence; social signals are weak by default."];
  if (e.type === "memory") return ["note", `${e.agent}'s operational memory${e.status ? ` · trust: ${e.status}` : ""}`];
  if (e.type === "note") return ["note", "Your note: it stays yours until you promote it."];
  if (e.type === "question") return ["note", `Open question · ${e.status || "status unknown"}`];
  return null;
}

function byBadges(e) {
  const out = [];
  if (e.by) out.push(agentBadge(e.by, "created by"));
  if (e.edited_by && e.edited_by !== e.by) out.push(agentBadge(e.edited_by, "edited by"));
  return out.join("");
}
const card = (e, extra = "") => {
  remember([e]);
  const f = e.facts || {};
  const due = f.revisit_after && String(f.revisit_after) <= localDay();
  return `
  <a class="card" data-t="${esc(e.type)}" href="#/e/${enc(e.id)}">
    <div class="card-kind">${g(e.type)}<span class="k">${esc(typeLabel(e.type))}</span>${e.status ? `<span>· ${esc(e.status)}</span>` : ""}${e.project ? `<span>· ${esc(e.project)}</span>` : ""}</div>
    <div class="card-title">${esc(e.title)}</div>
    ${e.description ? `<div class="card-desc">${esc(e.description)}</div>` : ""}
    <div class="card-meta">${e.by ? avatar(e.by, "s") : ""}${f.category ? `<span>${esc(f.category)}</span>` : ""}${e.date ? `<span>${esc(e.date)}</span>` : ""}${e.touched ? `<span>· touched ${rel(e.touched)}</span>` : ""}${due ? `<span class="badge acc">revisit due</span>` : ""}</div>
    ${extra}
  </a>`;
};
const chip = (e) => { remember([e]); return `<a class="chip" data-t="${esc(e.type)}" href="#/e/${enc(e.id)}" title="${esc(e.title)}">${g(e.type)}<span class="t">${esc(e.title)}</span></a>`; };

// ------------------------------------------------------------------ agents and presence
const ST_LABEL = { listening: "listening", working: "working", away: "busy", offline: "offline", starting: "starting" };
const named = () => state.operator.agents || [];
function legacyAgent() {  // an operator that runs `wait` without --agent: one unnamed agent
  const op = state.operator, msgs = state.chatMessages;
  const answers = msgs.filter((m) => m.role === "agent" && m.kind !== "progress");
  const lastOut = answers.at(-1)?.ts || "";
  const pending = msgs.filter((m) => m.role === "user" && m.ts > lastOut);
  const task = op.state === "working" ? pending[0] : null;
  const from = task?.ts || lastOut;
  return { id: null, state: op.state, project: null,
    task: task ? { text: task.text, ts: task.ts } : null,
    steps: op.state === "working" ? msgs.filter((m) => m.kind === "progress" && m.ts > from).slice(-6).map((m) => ({ text: m.text, ts: m.ts })) : [],
    last: answers.length ? { text: (answers.at(-1).text || "").replace(/```[\s\S]*?```/g, " ").slice(0, 180), ts: lastOut } : null };
}
function liveAgents() {
  const op = state.operator;
  if (op.mode !== "operator") return [];
  const list = named().filter((a) => a.state !== "offline");
  if (list.length) return list;
  return op.state && op.state !== "offline" && !named().length ? [legacyAgent()] : [];
}
const stateText = (a) => a.state === "working" && a.project ? `in ${a.project}` : ST_LABEL[a.state] || a.state;
function renderPresence() {
  const el = $("#presence");
  if (state.operator.mode !== "operator") {
    el.innerHTML = `<a class="ppill" href="#/chat" title="No agent attached: what you write is kept as a note">${avatar(null, "", "offline")}<span class="nm">Standalone</span></a>`;
  } else {
    const list = liveAgents();
    el.innerHTML = list.length ? list.map((a) => `<a class="ppill" href="#/chat" title="${a.state === "starting" ? "Atlas is ready; the agent has not connected yet. What you write waits for it" : `${esc(agentName(a.id))}: ${esc(stateText(a))}`}">${avatar(a.id, "", a.state)}<span class="nm">${esc(agentName(a.id))}</span><span class="st ${a.state}">${esc(stateText(a))}</span></a>`).join("")
      : `<a class="ppill" href="#/chat" title="The agent session ended; messages wait in the inbox">${avatar(null, "", "offline")}<span class="nm">Agent</span><span class="st">offline</span></a>`;
  }
  const sub = $("#chat-sub");
  if (sub) {
    const list = liveAgents();
    sub.textContent = state.operator.mode !== "operator" ? "No agent attached: messages are kept as notes."
      : list.length === 1 && list[0].state === "starting" ? "Waiting for the agent to connect. Write already: it reads your message when it listens."
      : list.length ? list.map((a) => `${agentName(a.id)} ${stateText(a)}`).join(" · ") : "The agent session ended; messages wait.";
  }
}

// whom a message goes to: one of the named agents (when there are any)
const toChoices = () => named();
function currentTo() {
  const list = toChoices();
  if (!list.length) return null;
  const saved = store.get("atlas.to", null);
  if (list.some((a) => a.id === saved)) return saved;
  return (list.find((a) => a.state === "listening") || list.find((a) => a.state !== "offline") || list[0]).id;
}

// ------------------------------------------------------------------ navigation
function seenCounts() {  // new entries per type = count above what the user last saw in that list
  let seen = store.get("atlas.seenCounts", null);
  if (seen === null) seen = Object.fromEntries(state.meta.types.map((t) => [t.id, t.count]));
  for (const t of state.meta.types) if ((seen[t.id] ?? 0) > t.count) seen[t.id] = t.count;
  store.set("atlas.seenCounts", seen);
  return seen;
}
function markTypeSeen(id) {
  const t = typeOf(id);
  if (!t) return;
  store.set("atlas.seenCounts", { ...seenCounts(), [id]: t.count });
  renderNav();
}
const NAV_ICONS = {
  home: '<path d="M2.5 7.5 8 3l5.5 4.5V13a.5.5 0 0 1-.5.5H3a.5.5 0 0 1-.5-.5Z"/>',
  chat: '<path d="M3 3.5h10a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H7l-3 2.5v-2.5H3a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1Z"/>',
  projects: '<rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="9" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="2.5" y="9" width="4.5" height="4.5" rx="1"/><rect x="9" y="9" width="4.5" height="4.5" rx="1"/>',
  graph: '<circle cx="4" cy="11" r="1.6"/><circle cx="8" cy="4" r="1.6"/><circle cx="12.5" cy="10" r="1.6"/><path d="M4.8 9.6 7.2 5.4M9 5.3l2.6 3.4M5.6 10.8l5.3-.6"/>',
  rediscover: '<circle cx="8" cy="8" r="5.8"/><path d="m10.6 5.4-1.7 3.5-3.5 1.7 1.7-3.5Z"/>',
};
const navIcon = (k) => `<svg class="i" viewBox="0 0 16 16" aria-hidden="true">${NAV_ICONS[k]}</svg>`;
const PROJECT_TYPES = new Set(["project", "thread", "decision", "lesson", "group"]);

function renderNav() {
  const m = state.meta, seen = seenCounts();
  const count = (id) => typeOf(id)?.count || 0;
  const notes = count("insight") + count("map") + count("sketch") + count("spec");
  const typeLink = (t) => {
    const fresh = Math.max(0, t.count - (seen[t.id] ?? 0));
    const only = (s) => s && !s.includes(",") ? `?status=${enc(s)}` : "";  // a link opens what its number counts
    return `<a class="nav-link${t.count ? "" : " zero"}" data-t="${esc(t.id)}" href="#/t/${enc(t.id)}${only(t.count_status)}"><span style="width:12px;display:inline-flex;justify-content:center">${g(t.id)}</span><span class="lbl">${esc(t.plural)}</span>${fresh ? `<span class="new-count" title="${fresh} new since you last looked">+${fresh}</span>` : ""}<span class="count">${t.count}</span></a>${t.aside ? `<a class="nav-aside" href="#/t/${enc(t.id)}${only(t.aside_status)}">+${t.aside} ${esc(t.aside_label || "aside")}</a>` : ""}`;
  };
  let html = `<a class="nav-link primary" href="#/">${navIcon("home")}<span class="lbl">Home</span></a>
    <a class="nav-link primary" href="#/chat">${navIcon("chat")}<span class="lbl">Operator</span></a>
    ${typeOf("project") ? `<a class="nav-link primary" href="#/projects">${navIcon("projects")}<span class="lbl">Projects</span></a>` : ""}
    ${notes >= 3 ? `<a class="nav-link primary" href="#/graph">${navIcon("graph")}<span class="lbl">Constellation</span></a>` : ""}
    ${count("insight") + count("sketch") >= 3 ? `<a class="nav-link primary" href="#/rediscover">${navIcon("rediscover")}<span class="lbl">Rediscover</span></a>` : ""}`;
  const sections = {};
  for (const t of m.types) if (t.nav !== false) (sections[t.section] ??= []).push(t);
  for (const [sec, types] of Object.entries(sections)) {
    if (types.some((t) => t.id === "project")) {  // projects by group, then the memory types in one line
      html += `<div class="nav-section"><span>${esc(sec)}</span><a href="#/projects">all</a></div>`;
      let group = null;
      for (const p of m.projects || []) {
        if (p.group !== group) { group = p.group; html += `<div class="nav-group">${esc(group || "")}</div>`; }
        html += `<a class="nav-link" href="#/e/${enc(p.id)}"><span style="width:12px;display:inline-flex;justify-content:center">${g("project")}</span><span class="lbl">${esc(p.title)}</span>${p.open ? `<span class="count">${p.open} open</span>` : ""}</a>`;
      }
      const rest = types.filter((t) => t.id !== "project");
      if (rest.length) html += `<div class="nav-sub">${rest.map((t) => `<a href="#/t/${enc(t.id)}">${esc(t.plural.toLowerCase())} <span class="mono">${t.count}</span></a>`).join("")}</div>`;
      continue;
    }
    if (types.length === 1 && types[0].id === "agent") {  // agents: who they are, and whether they are here
      html += `<div class="nav-section">${esc(sec)}</div>`;
      const live = Object.fromEntries(named().map((a) => [a.id, a.state]));
      for (const a of m.agents || []) {
        html += `<a class="nav-link" href="#/e/${enc(a.path)}">${avatar(a.id, "s", live[a.id] || null)}<span class="lbl">${esc(a.title)}</span>${live[a.id] ? `<span class="count">${esc(ST_LABEL[live[a.id]])}</span>` : ""}</a>`;
      }
      if (!(m.agents || []).length) html += typeLink(types[0]);
      continue;
    }
    html += `<div class="nav-section">${esc(sec)}</div>` + flow(types, typeLink);
  }
  $("#sidebar").innerHTML = html;
  const arrow = $("#distill-all");
  if (arrow) arrow.onclick = distillAll;
  markNav();
  updateUnread(state.chatMessages);
}
// captures become insights: the two lead their section, joined by an arrow that distills every waiting capture
function flow(types, link) {
  const cap = types.find((t) => t.id === "capture"), ins = types.find((t) => t.id === "insight");
  if (!cap || !ins) return types.map(link).join("");
  const arrow = `<button type="button" class="nav-flow${cap.count ? "" : " idle"}" id="distill-all" title="Distill all waiting captures into insights">` +
    `<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M6 1.5v8.5M2.5 6.8 6 10.3l3.5-3.5"/></svg><span class="lbl">distill all</span></button>`;
  return link(cap) + arrow + link(ins) + types.filter((t) => t !== cap && t !== ins).map(link).join("");
}
async function distillAll() {
  const home = await api("/api/home").catch(() => null);
  const n = home?.needs?.captures_total || 0, ops = home?.needs?.operational_total || 0;
  if (!n) return toast("No captures are waiting to distill");
  const stays = ops ? ` The ${ops} operational capture${ops > 1 ? "s stay" : " stays"} with ${ops > 1 ? "their projects" : "its project"}.` : "";
  const yes = await confirmBox(`Distill all ${n} capture${n > 1 ? "s" : ""}?`,
    `Your agent turns every waiting capture into insights, one after another, oldest first. That can take a while; keep reading meanwhile.${stays}`,
    "Distill all");
  if (!yes || !(await sendText("/distill all"))) return;
  if (state.operator.mode === "operator") { toast(`Sent to ${agentName(currentTo())}`); if (!onChatPage()) openChat(); }
}

// ------------------------------------------------------------------ a question before something big: resolves true or false
function confirmBox(title, text, ok = "OK") {
  return new Promise((resolve) => {
    const d = document.createElement("dialog");
    d.className = "confirm";
    d.innerHTML = `<form method="dialog"><h2>${esc(title)}</h2><p>${esc(text)}</p>
      <div class="confirm-acts"><button class="btn ghost" value="no">Cancel</button><button class="btn primary" value="yes" autofocus>${esc(ok)}</button></div></form>`;
    d.addEventListener("click", (ev) => { if (ev.target === d) d.close("no"); });  // a click on the backdrop cancels
    d.addEventListener("close", () => { resolve(d.returnValue === "yes"); d.remove(); });
    document.body.appendChild(d);
    d.showModal();
  });
}

function markNav() {
  const h = location.hash || "#/";
  const base = h.split("?")[0];
  $$(".nav-link").forEach((a) => a.classList.toggle("active", (a.getAttribute("href") || "").split("?")[0] === base));
  const tab = base.startsWith("#/chat") ? "chat" : base.startsWith("#/projects") || (state.current?.type && PROJECT_TYPES.has(state.current.type)) ? "projects" : base.startsWith("#/graph") ? "graph" : base === "#/" ? "home" : "";
  $$(".tabbar a").forEach((a) => a.classList.toggle("on", a.dataset.tab === tab));
}

// ------------------------------------------------------------------ actions (buttons anywhere: data-send, data-prefill, data-act)
const movesOf = (type) => typeOf(type)?.moves || [];
const fillMove = (send, page) => send.replace(/\{(title|path|project)\}/g, (_, k) => (k === "path" ? page?.id : page?.[k]) ?? "");
function movesButtons(page, { primaryFirst = true } = {}) {
  return movesOf(page.type).map((m, i) => `<button class="btn${primaryFirst && i === 0 ? " primary" : ""}" data-send="${esc(fillMove(m.send, page))}" data-via="move" data-ctx="${esc(page.id)}">${esc(stripEmoji(m.label))}</button>`).join("");
}
function movesBar(page) {
  const moves = movesButtons(page);
  return `<div class="moves-bar panel"><span class="lbl">Your move</span>${moves}${moves ? `<span class="sep" aria-hidden="true"></span>` : ""}
    <button class="btn ghost" data-act="star" data-id="${esc(page.id)}">${svg("star", "sm")}Keep</button>
    <button class="btn ghost" data-act="kill" data-id="${esc(page.id)}">${svg("x", "sm")}Let go</button>
    <button class="btn ghost" data-act="note" data-id="${esc(page.id)}">${svg("pen", "sm")}Leave a note</button></div>`;
}

document.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-send],[data-prefill],[data-act]");
  if (!b || b.disabled || b.closest("iframe")) return;
  ev.preventDefault();
  if (b.dataset.to) store.set("atlas.to", b.dataset.to);
  if (b.dataset.prefill !== undefined) return prefill(b.dataset.prefill);
  if (b.dataset.act) return act(b.dataset.act, b.dataset.id);
  b.disabled = true;
  const ok = await sendText(b.dataset.send, b.dataset.via || null, b.dataset.ctx || null);
  if (ok && b.dataset.once !== undefined) { b.classList.add("chosen"); return; }
  b.disabled = false;
  if (ok && state.operator.mode === "operator") { toast(`Sent to ${agentName(currentTo())}`); if (!onChatPage()) openChat(); }
});

function prefill(text) {
  const mobile = matchMedia("(max-width: 760px)").matches;
  if (mobile || onChatPage()) {
    state.prefill = text;
    if (onChatPage()) applyPrefill(); else location.hash = "#/chat";
    return;
  }
  openChat();
  fillAndSelect($("#dock-input"), text);
}
// the composer grows with its text (a quoted passage must be readable before it is sent)
const fit = (i) => { i.style.height = "auto"; i.style.height = `${Math.min(i.scrollHeight + 2, 200)}px`; };
function applyPrefill() {
  const i = $("#page-input");
  if (!i || state.prefill == null) return;
  fillAndSelect(i, state.prefill); state.prefill = null;
}

const ACT_LABEL = { star: "Kept", kill: "Let go", note: "Note" };
async function act(action, id) {
  let text = "";
  if (action === "note" || action === "kill") {
    text = prompt(action === "note" ? "Your note on this:" : "Why let it go? (optional)");
    if (text === null) return;
  }
  text = text.slice(0, 20000);  // what the server keeps; a keepalive request carries at most 64 KB
  withUndo(`${ACT_LABEL[action] || action}: ${titleOf(id)}`, async (leaving) => {
    const res = await post("/api/action", { id, action, text }, leaving ? { keepalive: true } : {}).catch(() => null);
    if (!res) return toast("Could not save. Is the Atlas server running?");
    toast(state.operator.mode === "operator" ? "Sent to your agent and kept as your note" : `Saved: ${res.note}`);
  });
}

// ------------------------------------------------------------------ views: home
function viewEmpty() {
  const op = state.operator.mode === "operator";
  main.innerHTML = `
    <div class="empty-hero">
      <div class="kicker">${esc(shortDay(localDay()))}</div>
      <h1>${greeting()}${state.meta.user?.name ? `, ${esc(state.meta.user.name)}` : ""}. What are you curious about?</h1>
      <p>${op ? "Ask a question, name a topic, or drop an idea. Your agent researches it, and your knowledge starts to grow right here: captures first, then insights, maps and a constellation."
        : "No agent is attached yet. Open Claude Code or Codex in this folder and say <b>start atlas</b>. Until then, anything you write is kept as a note."}</p>
      ${composer("hero", "e.g. What is the state of research on sleep and memory?  (type / for commands)")}
      <div class="chips">${HERO_CHIPS.map(([label, fill]) => `<button class="facet" data-fill="${esc(fill)}">${esc(label)}</button>`).join("")}</div>
    </div>`;
  wireComposer("hero", () => null, () => { location.hash = "#/chat"; });
  $$("[data-fill]").forEach((b) => b.onclick = () => fillAndSelect($("#hero-input"), b.dataset.fill));
}
// A chip puts a whole question in the box; the ‹part› to make your own arrives selected, so typing replaces it.
const HERO_CHIPS = [["What is the state of research on…", "What is the state of research on ‹sleep and memory›?"],
  ["Explain the landscape of… tools", "Explain the landscape of ‹note-taking› tools"],
  ["I have an idea for…", "I have an idea: ‹a timer that adapts to how focused I am›"]];
function fillAndSelect(i, text) {
  const m = /‹([^›]*)›/.exec(text);
  i.value = text.replace(/[‹›]/g, ""); fit(i); i.focus();
  const [from, to] = m ? [m.index, m.index + m[1].length] : [i.value.length, i.value.length];
  i.setSelectionRange(from, to);
}
const greeting = () => { const h = new Date().getHours(); return h < 5 ? "Late night" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"; };

function sinceSummary(feed, lastSeen) {
  if (!lastSeen) return "Everything below is read live from your vault.";
  const after = feed.filter((ev) => toDate(ev.when) > toDate(lastSeen));
  if (!after.length) return `Nothing changed since you were last here (${rel(lastSeen)}).`;
  const by = new Map();
  for (const ev of after) {
    const who = ev.agent || ev.author || "someone";
    const types = by.get(who) || new Map();
    for (const e of ev.entities) {
      const ids = types.get(e.type) || new Set();
      ids.add(e.id); types.set(e.type, ids);
    }
    by.set(who, types);
  }
  const phrase = (types) => {
    const parts = [...types.entries()].sort((a, b) => b[1].size - a[1].size).slice(0, 3)
      .map(([t, ids]) => `<b>${ids.size} ${esc((ids.size === 1 ? typeLabel(t) : typeOf(t)?.plural || t).toLowerCase().replace(/ \(.*\)$/, ""))}</b>`);
    return parts.length > 1 ? parts.slice(0, -1).join(", ") + " and " + parts.at(-1) : parts[0];
  };
  const people = [...by.entries()].slice(0, 3).map(([who, types]) => `${esc(state.meta.agents?.some((a) => a.id === who) ? agentName(who) : who)} worked on ${phrase(types)}`);
  return `While you were away, ${people.join("; ")}.`;
}

// a registry command as the text the agent receives (/tour → "Write an Atlas tour …")
const commandSend = (name, args = "") => {
  const c = commandList().find((x) => x.name === name);
  return c ? (c.send || `/${c.name} {args}`).replace("{args}", args).trim() : `/${name} ${args}`.trim();
};
function needsItems(n) {
  const items = [];
  const c = n.captures?.[0];
  if (n.captures_total && c) {
    const distill = movesOf("capture").find((m) => /distill/i.test(m.send))?.send || "Distill this capture into insights";
    items.push({ key: "captures", sig: n.sigs?.captures ?? `${n.captures_total}|${c.id}`, ico: g("capture"), t: `${n.captures_total} capture${n.captures_total > 1 ? "s" : ""} waiting to distill`,
      s: `Oldest: ${esc(c.title)}${c.date ? ` · ${rel(c.date)}` : ""}`,
      acts: `<button class="btn primary" data-send="${esc(distill)}" data-via="move" data-ctx="${esc(c.id)}">Distill oldest</button>` });
  }
  for (const d of (n.decisions || []).slice(0, 3)) {
    items.push({ key: `decision:${d.id}`, sig: d.status || "", ico: g("decision"), t: `Decision proposed${d.project ? ` in <a href="#/e/${enc(`projects/${d.group}/${d.project}/project.md`)}">${esc(d.project)}</a>` : ""}`,
      s: `<a href="#/e/${enc(d.id)}">${esc(d.title)}</a>`,
      acts: `<button class="btn" data-send="Accept this decision: set its status to accepted and commit it" data-via="move" data-ctx="${esc(d.id)}">Accept</button><a class="btn outline" href="#/e/${enc(d.id)}">Open</a>` });
  }
  const r = n.revisits?.[0];
  if (n.revisits_total && r) items.push({ key: "revisits", sig: n.sigs?.revisits ?? String(n.revisits_total), ico: svg("clock"), t: n.revisits_total > 1 ? `${n.revisits_total} revisits due` : "Revisit due",
    s: `${esc(r.title)}${r.status ? ` · ${esc(r.status)}` : ""}${r.facts?.revisit_after ? ` · due ${esc(r.facts.revisit_after)}` : ""}`, acts: `<a class="btn" href="#/e/${enc(r.id)}">Open</a>` });
  const f = n.fixes?.[0];
  if (n.fixes_total && f) items.push({ key: "fixes", sig: n.sigs?.fixes ?? String(n.fixes_total), ico: `<span style="color:var(--bad);display:inline-flex">${svg("link")}</span>`, t: `${n.fixes_total} note${n.fixes_total > 1 ? "s need" : " needs"} a fix`,
    s: `${esc(f.title)}: ${esc(String(f.issues?.[0] || "").replace(/[`*]/g, ""))}`, acts: `<button class="btn mono" data-send="/check" data-via="command">/check</button>` });
  const q = n.questions?.[0];
  if (n.questions_total && q) items.push({ key: "questions", sig: n.sigs?.questions ?? String(n.questions_total), ico: g("question"), t: `${n.questions_total} open question${n.questions_total > 1 ? "s" : ""}`, s: esc(q.title), acts: `<a class="btn" href="#/t/question">Open</a>` });
  const o = n.operational?.[0];
  if (n.operational_total && o) items.push({ key: "operational", sig: n.sigs?.operational ?? `${n.operational_total}|${o.id}`, ico: g("capture"), t: `${n.operational_total} operational capture${n.operational_total > 1 ? "s" : ""}`,
    s: `${esc(o.title)}${o.facts?.project ? ` · ${esc(o.facts.project)}` : ""}${o.date ? ` · ${rel(o.date)}` : ""}`,
    acts: `<button class="btn" data-send="Resolve this operational capture into a thread, decision or lesson" data-via="move" data-ctx="${esc(o.id)}">Resolve</button>` });
  const u = n.notes?.[0];
  if (n.notes_total && u) items.push({ key: "notes", sig: n.sigs?.notes ?? `${n.notes_total}|${u.id}`, ico: g("note"), t: `${n.notes_total} of your notes wait for your agent`, s: esc(u.description || u.title), acts: `<a class="btn" href="#/t/note">Open</a>` });
  return items;
}

function agentCard(a) {
  const working = a.state === "working";
  const projectLink = a.project ? (state.meta.projects || []).find((p) => p.project === a.project) : null;
  const steps = a.steps || [];
  return `<article class="agent-card ${esc(a.state)}">
    <div class="ac-head">${avatar(a.id, "l")}<span class="ac-name">${esc(agentName(a.id))}</span>
      ${projectLink ? `<a class="badge" href="#/e/${enc(projectLink.id)}">${g("project")}${esc(a.project)}</a>` : ""}
      <span class="ac-state ${esc(a.state)}"><span class="d${working ? " pulse" : ""}"></span>${esc(ST_LABEL[a.state] || a.state)}${working && a.task ? ` · ${since(a.task.ts)}` : ""}</span></div>
    ${working ? `<div class="ac-task">${a.task ? inline(a.task.text) : "Working…"}</div>
      ${steps.length ? `<ol class="steps">${steps.map((s, i) => `<li class="${i === steps.length - 1 ? "live" : ""}">${i === steps.length - 1 ? `<span class="pulse"></span>` : svg("check", "ok")}<span>${inline(s.text)}</span></li>`).join("")}</ol>` : ""}`
      : `<div class="ac-last">${a.last ? `Last: ${inline(a.last.text)}` : "Nothing yet in this session."}</div>`}
    <div class="ac-foot">
      ${working ? `<a class="btn primary" href="#/chat">${svg("eye", "sm")}Watch</a>` : `<button class="btn" data-prefill="" ${a.id ? `data-to="${esc(a.id)}"` : ""}>Ask ${esc(agentName(a.id))}</button>`}
      <span class="meta">${a.state === "listening" ? "wait armed" : a.state === "away" ? "busy elsewhere" : ""}${!working && a.last ? ` · last answer ${since(a.last.ts)}` : ""}</span>
    </div></article>`;
}
function shiftHtml() {
  const op = state.operator;
  if (op.mode !== "operator") return `<article class="agent-card"><div class="ac-head">${avatar(null, "l")}<span class="ac-name">No agent attached</span><span class="ac-state">standalone</span></div>
    <div class="ac-last">Open Claude Code or Codex in this folder and say <b>start atlas</b>. Until then, what you write is kept as a note in <span class="mono">you/notes/</span>.</div></article>`;
  const agents = liveAgents().sort((a, b) => (b.state === "working") - (a.state === "working"));
  const first = (state.meta.projects || []).find((p) => p.status === "active") || (state.meta.projects || [])[0];
  const dispatch = `<article class="agent-card dispatch">
    <div class="ac-head"><span class="av l" style="--av:var(--soft);background:none;border:1px solid var(--line-strong)">${svg("plus", "sm")}</span><span class="ac-name">Dispatch</span></div>
    <div class="ac-last">Put an agent on something. Results land where you read.</div>
    <div class="chips"><button class="btn mono" data-prefill="/learn ">/learn …</button>${first ? `<button class="btn mono" data-prefill="/project ${esc(first.project)}">/project ${esc(first.project)}</button>` : ""}<button class="btn mono" data-prefill="/map ">/map</button></div></article>`;
  if (!agents.length) return `<article class="agent-card"><div class="ac-head">${avatar(null, "l", "offline")}<span class="ac-name">Your agent</span><span class="ac-state">offline</span></div>
    <div class="ac-last">The agent session ended. Messages wait in the inbox until an agent listens again.</div></article>${dispatch}`;
  return agents.map(agentCard).join("") + dispatch;
}
function refreshShift() { const el = $("#shift"); if (el) el.innerHTML = shiftHtml(); }

const sparkHtml = (days) => {
  const max = Math.max(1, ...days);
  return `<span class="spark" aria-hidden="true">${days.map((v, i) => `<span class="${i === days.length - 1 ? "today" : ""}" style="height:${Math.round((v / max) * 100)}%"></span>`).join("")}</span>`;
};
function metabolismHtml(mb) {
  if (!mb) return "";
  const s = mb.stages, week = (t) => s[t].days.reduce((a, b) => a + b, 0);
  const stage = (t, title, num, what, acc = false) => `<a class="stage" data-t="${t}" href="#/t/${t}">
    <span class="card-kind">${g(t)}<span>${esc(title)}</span></span><span class="num">${num}</span>
    <span class="what${acc ? " acc" : ""}">${what}</span>${sparkHtml(s[t].days)}</a>`;
  const arrow = `<span class="flow-arrow" aria-hidden="true">${svg("arrow")}</span>`;
  return `<div class="metab panel">
    ${stage("capture", "Captures", s.capture.count, s.capture.count ? `${s.capture.count} waiting to distill` : "none waiting", s.capture.count > 0)}${arrow}
    ${stage("insight", "Insights", s.insight.count, `+${week("insight")} this week`)}${arrow}
    ${stage("map", "Maps", s.map.count, mb.unmapped ? `${mb.unmapped} insight${mb.unmapped > 1 ? "s" : ""} without a map` : "every insight mapped")}
    <span class="flow-sep" aria-hidden="true"></span>
    ${stage("sketch", "Sketch → Spec", `${s.sketch.count}<small> / ${s.spec.count}</small>`, `+${week("sketch")} sketch${week("sketch") === 1 ? "" : "es"} · +${week("spec")} spec${week("spec") === 1 ? "" : "s"}`)}
  </div>`;
}
// Three or more commits in a row by the same hand on one day fold into one row: the feed stays a page.
const FOLD_AT = 3;
const hand = (ev) => ev.agent || ev.author || "";
function feedRows(feed) {
  const rows = [];
  for (const ev of feed) {
    const day = localDay(toDate(ev.when)), prev = rows.at(-1);
    if (prev && prev.day === day && hand(prev.events[0]) === hand(ev)) prev.events.push(ev);
    else rows.push({ day, events: [ev] });
  }
  return rows.flatMap((r) => (r.events.length >= FOLD_AT ? [r] : r.events.map((ev) => ({ day: r.day, events: [ev] }))));
}
// The feed shows whole days: the most recent `days` days with activity, at most `cap` rows.
function feedSlice(rows, days, cap) {
  const out = [], seen = new Set();
  for (const row of rows) {
    if (!seen.has(row.day)) { if (seen.size === days) break; seen.add(row.day); }
    out.push(row);
    if (out.length >= cap) break;
  }
  return out;
}
// What a folded run touched, by kind: knowledge first, counted as notes, not commits.
const KIND_ORDER = ["insight", "map", "sketch", "spec", "capture", "project", "decision", "thread", "lesson", "question"];
function touchedPhrase(events) {
  const by = new Map();
  for (const ev of events) for (const e of ev.entities) { const ids = by.get(e.type) || new Set(); ids.add(e.id); by.set(e.type, ids); }
  const rank = (t) => (KIND_ORDER.includes(t) ? KIND_ORDER.indexOf(t) : 99);
  const kinds = [...by.entries()].sort((a, b) => rank(a[0]) - rank(b[0]) || b[1].size - a[1].size);
  const name = (t, n) => esc((n === 1 ? typeLabel(t) : typeOf(t)?.plural || t).toLowerCase().replace(/ \(.*\)$/, ""));
  const shown = kinds.slice(0, 2).map(([t, ids]) => `${ids.size} ${name(t, ids.size)}`);
  const rest = kinds.slice(2).reduce((a, [, ids]) => a + ids.size, 0);
  return shown.join(", ") + (rest ? ` and ${rest} more note${rest === 1 ? "" : "s"}` : "");
}
function feedEventHtml(ev, lastSeen) {
  const unseen = lastSeen && toDate(ev.when) > toDate(lastSeen);
  const m = /^([\w-]{2,14}):\s+(.*)$/.exec(ev.subject);
  const subject = m ? `<span class="verb">${esc(m[1])}</span> ${esc(m[2])}` : esc(ev.subject);
  const who = ev.agent ? agentName(ev.agent) : ev.author;
  return `<li class="${unseen ? "unseen" : ""}"><span class="time">${clock(ev.when)}</span>${authorAvatar(ev)}
    <div class="body"><div><b>${esc(who)}</b> · ${subject}</div>
    <div class="chips">${ev.entities.slice(0, 4).map(chip).join("")}${ev.entities.length + ev.other > 4 ? `<span class="chip">+${ev.entities.length + ev.other - 4}</span>` : ""}</div></div></li>`;
}
function feedGroupHtml(row, lastSeen) {
  const evs = row.events, unseen = lastSeen && evs.some((ev) => toDate(ev.when) > toDate(lastSeen));
  const notes = [...new Map(evs.flatMap((ev) => ev.entities).map((e) => [e.id, e])).values()];
  const who = evs[0].agent ? agentName(evs[0].agent) : evs[0].author;
  const more = notes.length - 4 + evs.reduce((a, ev) => a + ev.other, 0);  // like a single row: other files count too
  return `<li class="grp${unseen ? " unseen" : ""}"><span class="time" title="${esc(clock(evs.at(-1).when))} to ${esc(clock(evs[0].when))}">${clock(evs[0].when)}</span>${authorAvatar(evs[0])}
    <div class="body"><details><summary><b>${esc(who)}</b> · ${evs.length} commits · ${touchedPhrase(evs)}</summary>
      <ul class="feed sub">${evs.map((ev) => feedEventHtml(ev, lastSeen)).join("")}</ul></details>
    <div class="chips">${notes.slice(0, 4).map(chip).join("")}${more > 0 ? `<span class="chip">+${more}</span>` : ""}</div></div></li>`;
}
function feedHtml(rows, lastSeen) {
  let html = "", day = "";
  for (const row of rows) {
    if (row.day !== day) { day = row.day; html += `${html ? "</ul>" : ""}<div class="feed-day">${esc(dayLabel(day))}</div><ul class="feed">`; }
    html += row.events.length > 1 ? feedGroupHtml(row, lastSeen) : feedEventHtml(row.events[0], lastSeen);
  }
  return html ? html + "</ul>" : `<div class="empty">No history yet. With git, every change shows up here.</div>`;
}

// Snooze a row of Needs you: it stays away until the day, or until what it counts changes.
const SNOOZE_FOR = [["Tomorrow", 1], ["Next week", 7], ["In a month", 30]];
const plusDays = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return localDay(d); };
const plainText = (html) => { const d = document.createElement("div"); d.innerHTML = html; return d.textContent.trim(); };
const needRow = (it) => `<li class="need" data-key="${esc(it.key)}"><span class="ico" aria-hidden="true">${it.ico}</span><div class="txt"><div class="t">${it.t}</div><div class="s">${it.s}</div></div>
  <div class="acts">${it.acts}<details class="later"><summary class="btn ghost" title="Snooze this">${svg("clock", "sm")}<span class="sr">Snooze</span></summary>
    <div class="later-menu" role="menu">${SNOOZE_FOR.map(([l, n]) => `<button type="button" role="menuitem" data-snooze="${n}">${l}</button>`).join("")}</div></details></div></li>`;
function wireNeeds(all, data) {
  const box = $("#needs-box");
  if (!box || (data.box && data.box !== box)) return;  // an undo after leaving Home, or after it was drawn anew
  data.box = box;
  const isSnoozed = (it) => data.snoozed?.[it.key]?.sig === it.sig;
  const shown = all.filter((it) => !isSnoozed(it)), parked = all.filter(isSnoozed);
  $("#needs-n").textContent = shown.length;
  $("#needs-count").textContent = !shown.length ? "" : shown.length === 1 ? "One thing needs you." : `${shown.length} things need you.`;
  $("#needs-box").innerHTML = (shown.length ? `<ul class="needs-list${shown.length > 3 ? " clip" : ""}" id="needs-list">${shown.map(needRow).join("")}</ul>
      ${shown.length > 3 ? `<button class="btn ghost needs-all${shown.length > 5 ? " d" : ""}" id="needs-all">Show all ${shown.length}</button>` : ""}`
    : `<div class="empty">Nothing needs you right now.</div>`)
    + (parked.length ? `<details class="snoozed"><summary>${parked.length} snoozed</summary><ul class="mini-list">${parked.map((it) => `<li><span class="t">${esc(plainText(it.t))}</span><span class="when">until ${esc(shortDay(data.snoozed[it.key].until))}</span><button class="btn ghost" data-wake="${esc(it.key)}">Wake</button></li>`).join("")}</ul></details>` : "");
  const more = $("#needs-all");
  if (more) more.onclick = () => { $("#needs-list").classList.remove("clip"); more.remove(); };
  data.snoozed ??= {};
  $$("#needs-box [data-snooze]").forEach((b) => b.onclick = () => {
    const it = all.find((x) => x.key === b.closest(".need").dataset.key), prev = data.snoozed[it.key];
    const until = plusDays(+b.dataset.snooze), label = plainText(it.t);
    data.snoozed[it.key] = { until, sig: it.sig, label };
    wireNeeds(all, data);
    withUndo(`Snoozed until ${shortDay(until)}: ${label}`,
      (leaving) => post("/api/snooze", { key: it.key, until, sig: it.sig, label }, leaving ? { keepalive: true } : {}).catch(() => toast("Could not snooze. Is the Atlas server running?")),
      () => { if (prev) data.snoozed[it.key] = prev; else delete data.snoozed[it.key]; wireNeeds(all, data); });
  });
  $$("#needs-box details.later").forEach((d) => d.addEventListener("toggle", () => {  // keep the menu on screen (phones)
    const menu = d.querySelector(".later-menu");
    menu.style.left = menu.style.right = "";
    if (d.open && menu.getBoundingClientRect().left < 8) { menu.style.right = "auto"; menu.style.left = "0"; }
  }));
  $$("#needs-box [data-wake]").forEach((b) => b.onclick = () => {
    const key = b.dataset.wake;
    delete data.snoozed[key];
    wireNeeds(all, data);
    post("/api/snooze", { key, wake: true }).catch(() => toast("Could not wake it. Is the Atlas server running?"));
  });
}

// The tour: a guided walk through what changed, written by an agent (tours/).
function tourCta(t, lastSeen) {
  if (t && (!lastSeen || Date.parse(t.until) > Date.parse(lastSeen))) {
    return `<a class="tour-cta" href="#/e/${enc(t.id)}"><span class="play" aria-hidden="true">${svg("play")}</span><span class="txt"><b>Take the tour</b>
      <span>${t.stops} stop${t.stops === 1 ? "" : "s"} through what changed since ${esc(shortDay(String(t.since).slice(0, 10)))}${t.by ? ` · written by ${esc(agentName(t.by))}` : ""}</span></span>${svg("arrow")}</a>`;
  }
  const since = lastSeen ? localDay(toDate(lastSeen)) : localDay(new Date(Date.now() - 7 * 864e5));
  return `<div class="tour-cta quiet"><span class="txt"><b>A tour of what changed</b><span>Your agent walks you through it since ${esc(shortDay(since))}, in reading order, and marks what needs your call.${t ? ` Last one: <a href="#/e/${enc(t.id)}">${esc(t.title)}</a>.` : ""}</span></span>
    <button class="btn" data-send="${esc(commandSend("tour", since))}" data-via="command">Write a tour</button></div>`;
}

async function viewHome() {
  if (!(state.meta.content ?? state.meta.total)) return viewEmpty();
  const data = await api("/api/home");
  const lastSeen = store.get("atlas.lastSeen", null);
  const needs = needsItems(data.needs);
  const recent = [...(data.recent.sketch || []).slice(0, 2), ...(data.recent.frame || []).slice(0, 1), ...(data.recent.spec || []).slice(0, 1)].slice(0, 4);
  const rows = feedRows(data.feed);
  let days = 3, cap = 24;
  main.innerHTML = `<div class="home">
    <section class="hero">
      <div class="kicker">${esc(shortDay(localDay()))} · ${clock(new Date().toISOString())}${lastSeen ? ` · last here ${esc(dayLabel(localDay(toDate(lastSeen))))}` : ""}</div>
      <h1 class="home-greet">${greeting()}${state.meta.user?.name ? `, ${esc(state.meta.user.name)}` : ""}.</h1>
      <p class="page-sub">${sinceSummary(data.feed, lastSeen)} <span class="acc-text" id="needs-count"></span>
        <button class="btn ghost" id="mark-seen" style="min-height:30px">Mark all seen</button></p>
    </section>
    <section class="h-shift" aria-labelledby="shift-h">
      <div class="sec-h"><h2 id="shift-h">On shift</h2><span class="sub">agents keep working while you read</span></div>
      <div class="shift" id="shift">${shiftHtml()}</div>
    </section>
    <section class="h-metab" aria-labelledby="meta-h">
      <div class="sec-h"><h2 id="meta-h">Metabolism</h2><span class="sub">how raw research turns into knowledge · last 7 days</span></div>
      ${metabolismHtml(data.metabolism)}
    </section>
    <section class="h-needs" aria-labelledby="needs-h">
        <div class="sec-h"><h2 id="needs-h" class="acc">Needs you</h2><span class="sub mono" id="needs-n"></span></div>
        <div id="needs-box"></div>
    </section>
    <section class="h-feed" aria-labelledby="feed-h">
        <div class="sec-h"><h2 id="feed-h">What changed</h2><span class="sub" style="margin-left:auto">times are repository history, not content dates</span></div>
        ${tourCta(data.tour, lastSeen)}
        <div id="feed-box">${feedHtml(feedSlice(rows, days, cap), lastSeen)}</div>
        ${feedSlice(rows, days, cap).length < rows.length ? `<button class="btn ghost" id="feed-more" style="margin-top:8px">Earlier days</button>` : ""}
    </section>
    ${data.question || recent.length ? `<div class="h-recent">${data.question ? `<section class="h-question">
      <div class="sec-h"><h2>What we don't know yet</h2><span class="sub">one open question a day</span><a class="more" href="#/t/question?status=open">All open questions →</a></div>
      <div class="grid">${card(data.question)}</div></section>` : ""}${recent.length ? `<section${data.question ? ' class="home-sec"' : ""}><div class="sec-h"><h2>Fresh ideas and research</h2><a class="more" href="#/rediscover">Rediscover →</a></div><div class="grid">${recent.map((e) => card(e)).join("")}</div></section>` : ""}</div>` : ""}</div>`;
  wireNeeds(needs, data);
  $("#mark-seen").onclick = () => { store.set("atlas.lastSeen", new Date().toISOString()); toast("Marked as seen"); viewHome(); };
  const more = $("#feed-more");
  if (more) more.onclick = () => {
    days += 3; cap += 40;
    const shown = feedSlice(rows, days, cap);
    $("#feed-box").innerHTML = feedHtml(shown, lastSeen);
    if (shown.length >= rows.length) more.remove();
  };
}

async function viewRediscover() {
  const r = (await api("/api/home")).rediscover;
  main.innerHTML = `
    <section class="hero"><div class="kicker">picked fresh every day</div><h1 class="page">Rediscover</h1><p class="page-sub">Ideas that went quiet, and claims worth a second look.</p></section>
    <div class="sec-h"><h2>Longest-untouched sketches</h2></div><div class="grid">${r.forgotten_sketches.map((e) => card(e)).join("") || `<div class="empty">No sketches yet.</div>`}</div>
    <div class="sec-h home-sec"><h2>Insights of the day</h2></div><div class="grid">${r.insights_of_the_day.map((e) => card(e)).join("") || `<div class="empty">No insights yet.</div>`}</div>
    <div class="sec-h home-sec"><h2>Speculative claims worth a second look</h2></div><div class="grid">${r.speculative_pick.map((e) => card(e)).join("") || `<div class="empty">None right now.</div>`}</div>`;
}

// ------------------------------------------------------------------ views: lists, search
const facetVal = (e, k) => (k === "category" ? e.facts?.category : e[k]) || null;  // by = created_by
async function viewList(type, params) {
  const t = typeOf(type);
  if (!t) { main.innerHTML = `<div class="empty">Unknown type.</div>`; return; }
  const data = await api(`/api/list?type=${enc(type)}`);
  markTypeSeen(type);
  if (data.groups) return renderFrames(t, data.groups);
  const items = remember(data.items);
  const facetKeys = ["status", "group", "project", "by", "category"].filter((k) => params.get(k) || new Set(items.map((e) => facetVal(e, k)).filter(Boolean)).size > 1);  // a filter from the link shows, so it can be cleared
  const active = {};
  for (const k of facetKeys) if (params.get(k)) active[k] = params.get(k);
  const due = params.get("due") === "1";
  let shown = 150, q = "";
  const draw = () => {
    const filtered = items.filter((e) => Object.entries(active).every(([k, v]) => facetVal(e, k) === v)
      && (!due || (e.facts?.revisit_after && String(e.facts.revisit_after) <= localDay()))
      && (!q || (e.title + " " + e.description).toLowerCase().includes(q)));
    $("#facets").innerHTML = facetKeys.map((k) => {
      const counts = {};
      for (const e of items) { const v = facetVal(e, k); if (v) counts[v] = (counts[v] || 0) + 1; }
      if (active[k] && !(active[k] in counts)) counts[active[k]] = 0;  // a filter from a link stays visible, so it can be removed
      return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 14)
        .map(([v, c]) => `<button class="facet${active[k] === v ? " on" : ""}" data-k="${k}" data-v="${esc(v)}" aria-pressed="${active[k] === v}">${esc(v)}<span class="n">${c}</span></button>`).join("");
    }).join("") + (due ? `<button class="facet on" id="due-off">revisit due ✕</button>` : "");
    $("#list").innerHTML = filtered.slice(0, shown).map((e) => card(e)).join("")
      + (filtered.length > shown ? `<button class="btn" id="more">Show more (${filtered.length - shown})</button>` : "")
      + (filtered.length ? "" : `<div class="empty">${items.length ? "Nothing matches." : `No ${esc(t.plural.toLowerCase())} yet.`}</div>`);
    $("#count").textContent = `${filtered.length} of ${items.length}`;
    $$(".facet[data-k]").forEach((b) => b.onclick = () => { const { k, v } = b.dataset; active[k] === v ? delete active[k] : (active[k] = v); shown = 150; draw(); });
    $("#more") && ($("#more").onclick = () => { shown += 300; draw(); });
    $("#due-off") && ($("#due-off").onclick = () => (location.hash = `#/t/${type}`));
  };
  main.innerHTML = `
    <section class="hero"><div class="kicker" style="display:flex;align-items:center;gap:8px">${g(type)}${esc(t.section || "")}</div><h1 class="page">${esc(t.plural)}</h1><p class="page-sub"><span id="count"></span> · newest activity first</p></section>
    <div class="toolbar"><label class="sr" for="filter">Filter</label><input id="filter" placeholder="Filter by title or description…"></div>
    <div class="toolbar" id="facets"></div>
    <div class="list" id="list"></div>`;
  $("#filter").oninput = (ev) => { q = ev.target.value.toLowerCase(); shown = 150; draw(); };
  draw();
}
function renderFrames(t, groups) {
  main.innerHTML = `
    <section class="hero"><h1 class="page">${esc(t.plural)}</h1><p class="page-sub">${groups.length} research runs · each one: brief, manifest and analyses.</p></section>
    <div class="list">${groups.map((gr) => `
      <div class="card" data-t="frame">
        <div class="card-kind">${g("frame")}<span class="k">${esc(gr.group)}</span>${gr.touched ? `<span>· touched ${rel(gr.touched)}</span>` : ""}</div>
        <a href="#/e/${enc(gr.lead)}" class="card-title">${esc(gr.title)}</a>
        ${gr.description ? `<div class="card-desc">${esc(gr.description)}</div>` : ""}
        <div class="chips">${gr.docs.map((d) => `<a class="chip" data-t="frame" href="#/e/${enc(d.id)}">${g("frame")}<span class="t">${esc(d.id.split("/").pop())}</span></a>`).join("")}</div>
      </div>`).join("")}</div>`;
}

async function viewSearch(params) {
  const q = params.get("q") || "", mode = params.get("mode") || "fast";
  $("#search-input").value = q;
  main.innerHTML = `<section class="hero"><div class="kicker">${mode === "deep" ? "semantic search through QMD" : "instant title and text match"}</div><h1 class="page">“${esc(q)}”</h1></section>
    <div class="toolbar"><div class="seg" role="group" aria-label="Search mode"><a class="btn ghost${mode === "fast" ? " on" : ""}" href="#/search?q=${enc(q)}" aria-pressed="${mode === "fast"}">Instant</a><a class="btn ghost${mode === "deep" ? " on" : ""}" href="#/search?q=${enc(q)}&mode=deep" aria-pressed="${mode === "deep"}">Deep (QMD)</a></div></div>
    <div class="list" id="results"><div class="loading">${mode === "deep" ? "Asking QMD; this can take a few seconds…" : "Searching…"}</div></div>`;
  const data = await api(`/api/search?q=${enc(q)}&mode=${mode}`);
  if (data.note) toast(data.note);
  $("#results").innerHTML = data.results.length ? data.results.map((e) => e.id ? card(e, e.snippet ? `<div class="card-desc mono" style="font-size:12.5px">${esc(e.snippet)}</div>` : "")
    : `<div class="card" data-t="external"><div class="card-title">${esc(e.title)}</div><div class="card-desc">${esc(e.description)}</div><div class="path">${esc(e.path)}</div></div>`).join("")
    : `<div class="empty">No results.${mode === "fast" ? ` Try <a href="#/search?q=${enc(q)}&mode=deep">deep search</a>.` : ""}</div>`;
}

function viewMissing(name) {
  main.innerHTML = `<section class="hero"><div class="kicker">a wanted link</div><h1 class="page">Not written yet</h1>
    <p class="page-sub">Some note links to <b>${esc(name)}</b>, but no note with that name exists: a gap someone noticed.</p></section>
    <button class="btn primary" id="want">Ask for this note</button>`;
  $("#want").onclick = async () => { await post("/api/action", { action: "wanted", text: `Wanted note: ${name}` }); toast("Saved as a request"); };
}

// ------------------------------------------------------------------ hover cards: where a link goes, without leaving the page
const cardCache = new Map();
const canHover = matchMedia("(hover: hover) and (pointer: fine)");
let hoverFor = null, hoverTimer = null, hoverAt = { x: 0, y: 0 };
function hoverCardHtml(c) {
  const f = c.facts || {}, due = f.revisit_after && String(f.revisit_after) <= localDay();
  const meta = [c.degree ? `${c.degree} connection${c.degree === 1 ? "" : "s"}` : "no connections",
    c.maps?.length ? `in ${c.maps.map((m) => m.title).join(", ")}` : "", c.date || ""].filter(Boolean);
  return `<div class="hc-kind" data-t="${esc(c.type)}">${g(c.type)}<span class="k">${esc(typeLabel(c.type))}</span>${c.status ? `<span>· ${esc(c.status)}</span>` : ""}${due ? `<span class="badge acc">revisit due</span>` : ""}</div>
    <div class="hc-title">${esc(c.title)}</div>${c.description ? `<div class="hc-desc">${esc(c.description)}</div>` : ""}
    <div class="hc-meta">${meta.map(esc).join(" · ")}</div>`;
}
function hideHover() { clearTimeout(hoverTimer); hoverFor = null; $("#hovercard").hidden = true; }
async function showHover(a) {
  const href = a.getAttribute("href") || "";
  let html;
  if (href.startsWith("#/missing/")) {
    html = `<div class="hc-kind"><span class="k" style="color:var(--bad)">Not written yet</span></div><div class="hc-title">${esc(decodeURIComponent(href.slice(10)))}</div><div class="hc-desc">A note links here, but no note with this name exists.</div>`;
  } else {
    const id = decodeURIComponent(href.slice(4).split("?")[0]);
    let c = cardCache.get(id);
    if (!c) { c = await api(`/api/card?id=${enc(id)}`).catch(() => null); if (c) cardCache.set(id, c); }
    if (!c) return;
    html = hoverCardHtml(c);
  }
  if (hoverFor !== a || !a.isConnected) return;
  const box = $("#hovercard");
  box.innerHTML = html; box.hidden = false;
  const rects = [...a.getClientRects()], w = box.offsetWidth, h = box.offsetHeight;  // a link that wraps: the line under the pointer
  const r = rects.find((x) => hoverAt.y >= x.top && hoverAt.y <= x.bottom) || rects[0] || a.getBoundingClientRect();
  const below = r.bottom + 8 + h < innerHeight || r.top < h + 16;
  box.style.left = `${Math.max(12, Math.min(r.left, innerWidth - w - 12))}px`;
  box.style.top = `${below ? r.bottom + 8 : r.top - h - 8}px`;
}
document.addEventListener("mouseover", (ev) => {
  if (!canHover.matches) return;
  const a = ev.target.closest?.('.reader a[href^="#/e/"], .reader a[href^="#/missing/"]') || null;
  if (a === hoverFor) return;
  hideHover();
  if (!a) return;
  hoverFor = a; hoverAt = { x: ev.clientX, y: ev.clientY };
  hoverTimer = setTimeout(() => showHover(a), 350);
});
addEventListener("scroll", hideHover, { capture: true, passive: true });

// ------------------------------------------------------------------ views: a note (the reader)
function neighborhood(e) {
  const W = 340, H = 230, cx = W / 2, cy = H / 2, r = 74;
  const nodes = e.neighbors || [];
  const pos = nodes.map((_, i) => { const a = (i / nodes.length) * Math.PI * 2 - Math.PI / 2; return [cx + Math.cos(a) * r * 1.05, cy + Math.sin(a) * r * 0.82, a]; });
  const short = (s, n = 14) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  const shape = (t, x, y, s) => {
    if (t === "map") return `<rect x="${x - s}" y="${y - s}" width="${2 * s}" height="${2 * s}" transform="rotate(45 ${x} ${y})" fill="var(--stage)" stroke="var(--hue)" stroke-width="1.6"/>`;
    if (t === "capture") return `<circle cx="${x}" cy="${y}" r="${s}" fill="var(--stage)" stroke="var(--hue)" stroke-width="1.4" stroke-dasharray="2 1.6"/>`;
    if (t === "sketch" || t === "spec") return `<path d="M${x} ${y - s * 1.1}L${x + s} ${y + s * .8}H${x - s}Z" fill="var(--hue)"/>`;
    return `<circle cx="${x}" cy="${y}" r="${s}" fill="var(--hue)"/>`;
  };
  let out = `<svg class="neigh" viewBox="0 0 ${W} ${H}" role="img" aria-label="${nodes.length} linked notes">`;
  nodes.forEach((n, i) => (out += `<line class="${n.rel}" x1="${cx}" y1="${cy}" x2="${pos[i][0]}" y2="${pos[i][1]}"/>`));
  nodes.forEach((n, i) => {
    const [x, y, a] = pos[i], right = Math.cos(a) >= 0;
    out += `<a href="#/e/${enc(n.id)}" data-t="${esc(n.type)}"><title>${esc(n.title)} (${n.rel === "in" ? "links here" : "linked"})</title>${shape(n.type, x, y, 4.5)}
      ${nodes.length <= 12 ? `<text x="${x + (right ? 8 : -8)}" y="${y + 3.5}" text-anchor="${right ? "start" : "end"}">${esc(short(n.title))}</text>` : ""}</a>`;
  });
  out += `<g data-t="${esc(e.type)}"><circle cx="${cx}" cy="${cy}" r="12" fill="var(--hue)" opacity=".2"/>${shape(e.type, cx, cy, 7)}</g></svg>`;
  return `<div class="neigh-box">${out}<div class="neigh-key">solid: this note links there · dashed: links here</div></div>`;
}

function trustPanel(e) {
  const scale = (e.scale || []).filter((v) => !/supersed|archiv|histor|closed/i.test(v));
  const ended = e.status && (e.scale || []).includes(e.status) && !scale.includes(e.status);
  const idx = scale.indexOf(String(e.status));
  const lines = [];
  const f = e.facts || {};
  if (f.revisit_after) {
    const due = String(f.revisit_after) <= localDay();
    lines.push(`<span class="${due ? "acc-text" : ""}">${svg("clock", "sm")}${due ? `Revisit due since ${esc(f.revisit_after)}` : `Revisit after ${esc(f.revisit_after)}`}</span>`);
  }
  if (e.provenance?.length) lines.push(`<span>${svg("check", "sm ok")}Traces back to ${e.provenance.length === 1 ? "a source" : `${e.provenance.length} earlier notes`}</span>`);
  if (e.maps?.length) lines.push(`<span>${svg("check", "sm ok")}Part of ${e.maps.length === 1 ? `the map ${esc(e.maps[0].title)}` : `${e.maps.length} maps`}</span>`);
  if (e.history?.length) { const h = e.history[0]; lines.push(`<span>${svg("pen", "sm")}Last changed ${h.agent ? `by ${esc(agentName(h.agent))}` : `by ${esc(h.author)}`} · ${rel(h.when)}</span>`); }
  if (!scale.length && !lines.length) return "";
  return `<section class="trust panel" aria-label="How far to trust this">
    ${scale.length ? `<div class="meter${ended ? " ended" : ""}" data-t="${esc(e.type)}"><div class="bars" aria-hidden="true">${scale.map((_, i) => `<span class="${i <= idx ? "on" : ""}"></span>`).join("")}</div>
      <div class="labels">${scale.map((v) => `<span class="${v === e.status ? "cur" : ""}">${esc(v)}</span>`).join("")}</div>
      ${ended ? `<div class="labels"><span class="cur">${esc(e.status)}</span></div>` : ""}</div>` : ""}
    ${lines.length ? `<div class="trust-lines">${lines.join("")}</div>` : ""}</section>`;
}

// A person's or organization's card: the notes they wrote (frontmatter `authors:`) and the notes
// that name them, grouped by type. Long groups start closed.
function mentionsTable(e) {
  const m = e.mentions;
  if (!m || (!m.written.length && !m.mentioned.length)) return "";
  const block = (label, list, total) => {
    if (!list.length) return "";
    remember(list);
    const byType = {};
    for (const x of list) (byType[x.type] ||= []).push(x);
    return `<div class="men-group"><h3 class="kicker">${label} · ${total ?? list.length}${total > list.length ? ` (first ${list.length})` : ""}</h3>${Object.entries(byType).map(([t, xs]) =>
      `<details${xs.length <= 8 ? " open" : ""}><summary>${g(t)}<span>${esc(xs.length === 1 ? typeLabel(t) : typeOf(t)?.plural || t)}</span><span class="mono">${xs.length}</span></summary>
        <ul class="mini-list">${xs.map((x) => `<li data-t="${esc(x.type)}"><a href="#/e/${enc(x.id)}">${esc(x.title)}</a>${x.date ? `<span class="when">${esc(x.date)}</span>` : ""}</li>`).join("")}</ul></details>`).join("")}</div>`;
  };
  return `<section aria-labelledby="men-h"><div class="sec-h"><h2 id="men-h">In this vault</h2></div>${block("Written by", m.written, m.total?.written)}${block("Mentioned in", m.mentioned, m.total?.mentioned)}</section>`;
}

function relTable(e) {
  const rows = [
    ...(e.maps || []).map((x) => ["part of", "", x]),
    ...(e.outlinks || []).filter((x) => x.type !== "map").map((x) => ["links to", "", x]),
    ...(e.backlinks || []).map((x) => ["linked from", "in", x]),
    ...(e.siblings || []).map((x) => ["same run", "in", x]),
  ];
  if (!rows.length) return "";
  remember(rows.map((r) => r[2]));
  return `<section aria-labelledby="conn-h"><div class="sec-h"><h2 id="conn-h">Connections</h2><span class="sub mono">${rows.length}</span></div>
    <div class="rel-table">${rows.slice(0, 40).map(([label, cls, x]) => `<div data-t="${esc(x.type)}"><span class="rel ${cls}">${label}</span><a href="#/e/${enc(x.id)}">${g(x.type)}<span>${esc(x.title)}</span></a>${x.status ? `<span class="badge">${esc(x.status)}</span>` : ""}</div>`).join("")}</div></section>`;
}

// What a check flags on this note, as one line that opens: a long list must not push the text away.
function fixBadge(e) {
  const n = e.issues?.length || 0;
  if (!n) return "";
  const links = e.issues.filter((i) => /matches no note/.test(i)).length;
  const label = links === n ? `${n} broken link${n > 1 ? "s" : ""}` : `${n} thing${n > 1 ? "s" : ""} to fix`;
  return `<details class="fixes"><summary>${svg("link", "sm")}<span>${label}</span><button class="btn mono" data-send="/check" data-via="command">/check</button></summary>
    <ul>${e.issues.map((i) => `<li>${inline(i)}</li>`).join("")}</ul></details>`;
}
// Titles here are claims, often whole sentences: the longer the title, the smaller the serif.
const titleClass = (t) => (t.length <= 48 ? "t-l" : t.length <= 90 ? "t-m" : t.length <= 150 ? "t-s" : "t-xs");

const BEHIND_STATUS = ["raised_count"];  // bookkeeping: shown when you point at the status, not in the facts line
// a fact's wiki links ([[…]]) as links to the notes they name; unknown ones as plain words
const factValue = (e, text) => esc(text).replace(/\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]/g, (_, target, alias) => {
  const hit = e.fact_links?.[target.replace(/&amp;/g, "&").replace(/&#39;/g, "'").replace(/&quot;/g, '"')];
  return hit ? `<a href="#/e/${enc(hit.id)}">${alias || esc(hit.title)}</a>` : alias || target;  // alias and target are escaped already
});
function readerHead(e, { crumbs = true } = {}) {
  const t = typeOf(e.type);
  const nav = e.map_nav;
  const facts = Object.entries(e.facts || {}).filter(([k]) => !["category", "description", "status", "revisit_after", "superseded_by", "source", "confidence", "date", "question", ...BEHIND_STATUS].includes(k))
    .map(([k, v]) => `<span title="${esc(k)}">${esc(k)}: ${factValue(e, Array.isArray(v) ? v.join(", ") : typeof v === "object" && v ? JSON.stringify(v) : String(v))}</span>`).join("");
  const behind = BEHIND_STATUS.filter((k) => e.facts?.[k] != null).map((k) => `${k}: ${e.facts[k]}`).join(", ");
  const ep = epistemic(e);
  return `
    ${crumbs ? `<div class="crumbs"><a href="#/t/${enc(e.type)}">${esc(t?.plural || e.type)}</a>${e.group ? `<span aria-hidden="true">/</span><span>${esc(e.group)}</span>` : ""}${e.project ? `<span aria-hidden="true">/</span><a href="#/e/${enc(`projects/${e.group}/${e.project}/project.md`)}">${esc(e.project)}</a>` : ""}
      ${nav ? `<span class="nav"><span>in <a href="#/e/${enc(nav.map)}">${esc(nav.title)}</a></span>
        <a class="icon-btn" href="${nav.prev ? `#/e/${enc(nav.prev)}` : "#"}" aria-label="Previous in this map" ${nav.prev ? "" : 'aria-disabled="true" tabindex="-1"'}>${svg("left")}</a>${nav.pos} / ${nav.total}
        <a class="icon-btn" href="${nav.next ? `#/e/${enc(nav.next)}` : "#"}" aria-label="Next in this map" ${nav.next ? "" : 'aria-disabled="true" tabindex="-1"'}>${svg("right")}</a></span>` : ""}</div>` : ""}
    <div class="meta-row" data-t="${esc(e.type)}"><span class="badge kind">${g(e.type)}${esc(typeLabel(e.type))}</span>${e.facts?.category ? `<span>${esc(e.facts.category)}</span>` : ""}${e.status ? `<span class="badge"${behind ? ` title="${esc(behind)}"` : ""}>${esc(e.status)}</span>` : ""}${byBadges(e)}${e.date ? `<span>${esc(e.date)}</span>` : ""}${facts}${fixBadge(e)}</div>
    <h1 class="e-title ${titleClass(e.title)}">${esc(e.title)}</h1>
    ${e.meta?.description ? `<p class="e-desc">${esc(e.meta.description)}</p>` : ""}
    ${e.facts?.question ? `<div style="display:flex;flex-direction:column;gap:4px;padding-left:14px;border-left:2px solid var(--line)"><span class="kicker">Question</span><span style="font-size:15.5px">${esc(e.facts.question)}</span></div>` : ""}
    ${ep && ep[0] !== "note" ? `<div class="banner${ep[0] === "info" ? "" : ` ${ep[0]}`}">${svg(ep[0] === "info" ? "info" : "warn")}<div>${esc(ep[1])}</div></div>` : ""}
    ${trustPanel(e)}
    ${ep && ep[0] === "note" ? `<div class="banner" style="background:var(--sunk);border-color:var(--line-2);color:var(--soft)">${svg("info")}<div>${esc(ep[1])}</div></div>` : ""}
    ${e.meta?.superseded_by ? `<div class="banner quiet">${svg("warn")}<div>Superseded by ${esc(String(e.meta.superseded_by).replace(/[\[\]"]/g, ""))}</div></div>` : ""}
`;
}

function marginHtml(e) {
  const chain = [...(e.provenance || [])];
  const parts = [];
  if (chain.length || e.maps?.length) {
    parts.push(`<section><h3>Provenance</h3><ol class="chain">
      ${chain.map((x) => `<li data-t="${esc(x.type)}"><span class="node">${g(x.type)}</span><div><span class="k">${esc(typeLabel(x.type))}${x.date ? ` · ${esc(x.date)}` : ""}</span><a href="#/e/${enc(x.id)}">${esc(x.title)}</a></div></li>`).join("")}
      <li class="here" data-t="${esc(e.type)}"><span class="node"></span><div><span class="k">this ${esc(typeLabel(e.type).toLowerCase())}</span><span class="t">${esc(e.title)}</span></div></li>
      ${(e.maps || []).map((x) => `<li data-t="map"><span class="node">${g("map")}</span><div><span class="k">map</span><a href="#/e/${enc(x.id)}">${esc(x.title)}</a></div></li>`).join("")}
    </ol></section>`);
  }
  if (e.neighbors?.length) parts.push(`<section><h3>Neighbourhood${state.meta.types.some((t) => t.id === "insight") ? `<a href="#/graph">Open in constellation →</a>` : ""}</h3>${neighborhood(e)}</section>`);
  if (e.history?.length) parts.push(`<section><h3>Who touched it</h3><ul class="mini-list hist">${e.history.slice(0, 6).map((h) => `<li>${authorAvatar(h, "s")}<span class="t"><b style="color:var(--text);font-weight:500">${esc(h.agent ? agentName(h.agent) : h.author)}</b> · ${esc(h.subject)}</span><span class="when">${esc(rel(h.when))}</span></li>`).join("")}</ul></section>`);
  if (e.members?.length) parts.push(`<section><h3>${e.type === "group" ? "Projects" : "Project memory"} · ${e.members.length}</h3><ul class="mini-list">${e.members.map((x) => `<li data-t="${esc(x.type)}">${g(x.type)}<a href="#/e/${enc(x.id)}">${esc(x.title)}</a>${x.status ? `<span class="when">${esc(x.status)}</span>` : ""}</li>`).join("")}</ul></section>`);
  if (e.group_note) parts.push(`<section><h3>Group</h3><ul class="mini-list"><li data-t="group">${g("group")}<a href="#/e/${enc(e.group_note.id)}">${esc(e.group)}: rules and notes</a></li></ul></section>`);
  parts.push(`<section><h3>File</h3><div class="path">${esc(e.path)}</div><button class="btn ghost" id="copy-path" style="margin-top:8px;min-height:32px">${svg("copy", "sm")}Copy path</button></section>`);
  return parts.join("");
}

async function entityOrMoved(id) {  // a note the agent moved keeps its file name; the engine says where it went
  const res = await fetch(`/api/entity?id=${enc(id)}`, { headers: { "x-atlas": "1" } }).catch(() => null);
  if (!res) return {};
  if (res.ok) return { e: await res.json() };
  return { movedTo: (await res.json().catch(() => ({}))).moved_to };
}

// The vault changed (an agent wrote, moved or finished a note): an open note follows it, keeping the scroll
// position. The composer lives in the dock, outside the page, so a draft stays.
async function refreshOpenView() {
  const [path, qs] = (location.hash || "#/").slice(1).split("?");
  if (!path.startsWith("/e/") || !state.current) return;
  const token = state.routeToken, id = state.current.id;
  const { e } = await entityOrMoved(id);
  if (token !== state.routeToken || (e && e.rev === state.current.rev)) return;  // moved on, or another note changed
  state.keepScroll = { id, y: scrollY };
  disposeView();  // a tour's key handlers
  await viewEntity(decodeURIComponent(path.slice(3)), new URLSearchParams(qs || ""));  // follows a moved note
}
// The scroll position a re-rendered (or moved) note keeps; any other page opens at the top.
function keptScroll(id) {
  const k = state.keepScroll;
  state.keepScroll = null;
  return k?.id === id ? k.y : 0;
}

async function viewEntity(id, params = new URLSearchParams()) {
  const token = state.routeToken;
  const { e, movedTo } = await entityOrMoved(id);
  if (token !== state.routeToken) return;  // the reader moved on while this page loaded
  if (!e && movedTo) {
    if (state.keepScroll?.id === id) state.keepScroll.id = movedTo;
    toast(`Moved to ${movedTo.split("/")[0]}/`);
    location.replace(`#/e/${enc(movedTo)}`);
    return;
  }
  if (!e) { main.innerHTML = `<div class="empty">Not found: ${esc(id)}</div>`; return; }
  remember([e, ...(e.outlinks || []), ...(e.backlinks || []), ...(e.maps || [])]);
  state.current = e;
  rememberVisit(e);
  updateComposers();
  markNav();
  if (e.type === "project" && e.project_view) return renderProject(e);
  if (e.type === "tour" && e.tour_view) return renderTour(e, params);
  main.innerHTML = `<div class="reader-wrap">
    <article class="reader-main"><div class="reader-col">
      ${readerHead(e)}
      <div class="reader" data-src="${esc(e.id)}">${e.html}</div>
      ${mentionsTable(e)}
      ${relTable(e)}
      ${movesBar(e)}
    </div></article>
    <aside class="margin" aria-label="About this note">${marginHtml(e)}</aside></div>`;
  $("#copy-path").onclick = () => navigator.clipboard?.writeText(e.path).then(() => toast("Path copied"));
  window.scrollTo(0, keptScroll(e.id));
}

// ------------------------------------------------------------------ views: projects
const sparkPath = (days) => { const max = Math.max(1, ...days); return days.map((v, i) => `M${i * 10} 24h7v-${v ? Math.max(4, Math.round((v / max) * 24)) : 1.5}h-7z`).join(""); };
const sparkSvg = (days) => `<svg class="sparkline" viewBox="0 0 ${days.length * 10} 24" preserveAspectRatio="none" role="img" aria-label="Sessions per day, last ${days.length} days"><path d="${sparkPath(days)}"/></svg>`;
function checkoutText(co) {
  if (!co) return "";
  if (co.status === "ok") return `<span class="co">${svg("check", "sm ok")}<span>${esc(co.path.replace(/^\/home\/[^/]+/, "~"))} · ${esc(co.branch || "")}</span></span>`;
  if (co.status === "unmapped") return `<span class="co warn">${svg("warn", "sm")}<span>no checkout on this machine</span></span>`;
  return `<span class="co warn">${svg("warn", "sm")}<span>${esc(co.status)}</span></span>`;
}
const statusBadge = (s) => !s ? "" : s === "active" ? `<span class="badge ok"><span class="status-dot"></span>active</span>` : `<span class="badge">${esc(s)}</span>`;
function liveStrip(here) {
  return here.map((a) => `<div class="live-strip"><span class="pulse"></span>${avatar(a.id, "s")}<span class="t"><b>${esc(agentName(a.id))} is here</b>${a.task ? ` · ${esc(a.task.text.slice(0, 90))}` : ` · ${esc(ST_LABEL[a.state])}`}</span>${a.task ? `<span class="mono" style="font-size:11.5px;color:var(--soft)">${since(a.task.ts)}</span>` : ""}</div>`).join("");
}
function projectCard(p) {
  remember([p]);
  const live = p.here?.length > 0;
  const pid = `#/e/${enc(p.id)}`;
  return `<article class="pcard${live ? " live" : ""}${p.status === "paused" ? " paused" : ""}" data-t="project">
    <div class="p-head">${g("project")}<a class="p-title" href="${pid}">${esc(p.title)}</a>${statusBadge(p.status)}${p.aliases?.length ? `<span class="p-alias">aka ${esc(p.aliases.join(", "))}</span>` : ""}</div>
    ${liveStrip(p.here || [])}
    ${p.last ? `<div class="p-last"><span class="kicker">Last time · ${esc(shortDay(p.last.date))} · ${esc(agentName(p.last.agent))}</span><span class="txt">${inline(p.last.text)}</span></div>`
      : p.description ? `<div class="p-last"><span class="txt" style="color:var(--soft)">${esc(p.description)}</span></div>` : ""}
    ${p.next ? `<div class="p-next">${svg("arrow", "sm")}<span><b>Next:</b> ${inline(p.next.text)}</span></div>` : ""}
    <div class="p-stats">
      <a href="${pid}"><span class="n${p.open ? "" : " zero"}">${p.open}</span><span class="l">open threads${p.blocked ? ` · ${p.blocked} blocked` : ""}</span></a>
      <a href="${pid}"><span class="n${p.proposed ? " acc" : " zero"}">${p.proposed}</span><span class="l">to decide</span></a>
      <a href="${pid}"><span class="n${p.provisional ? "" : " zero"}">${p.provisional}</span><span class="l">lesson${p.provisional === 1 ? "" : "s"} to validate</span></a>
    </div>
    <div class="p-foot">${sparkSvg(p.activity || [])}${checkoutText(p.checkout)}
      ${live ? `<a class="btn" href="#/chat">${svg("eye", "sm")}Watch</a>` : `<button class="btn primary" data-send="/project ${esc(p.project)}" data-via="command">Work on it</button>`}</div>
  </article>`;
}

async function viewProjects() {
  const data = await api("/api/projects");
  const projects = data.groups.flatMap((gr) => gr.projects);
  const working = new Set(projects.flatMap((p) => (p.here || []).map((a) => a.id)));
  remember([...data.decisions, ...data.lessons, ...data.blocked]);
  main.innerHTML = `<div class="p-layout" style="margin-top:0">
    <div class="main-col">
      <section class="hero-row">
        <div style="display:flex;flex-direction:column;gap:10px">
          <div class="kicker">${projects.length} project${projects.length === 1 ? "" : "s"} · ${data.groups.length} group${data.groups.length === 1 ? "" : "s"}${working.size ? ` · ${working.size} agent${working.size > 1 ? "s" : ""} at work` : ""}</div>
          <h1 class="page">Projects</h1>
          <p class="page-sub" style="margin:0">One memory per project, shared by every agent. Pick any of them up where the last session left off.</p>
        </div>
        <button class="btn primary" data-prefill="New project: ">${svg("plus", "sm")}New project</button>
      </section>
      ${data.groups.map((gr) => `<section aria-label="${esc(gr.group)}">
        <div class="group-h"><h2>${esc(gr.group)}</h2><span class="mono" style="font-size:12px;color:var(--faint)">${gr.projects.length} project${gr.projects.length === 1 ? "" : "s"}</span>
          <span class="rules">${gr.rules.length ? `${svg("shield", "sm")}<span title="${esc(gr.rules.join("\n"))}">${esc(gr.rules.slice(0, 2).map((r) => r.replace(/[*`]/g, "").split(/(?<=\.)\s/)[0]).join(" · "))}</span>` : "no group rules yet"}</span>
          ${gr.note ? `<a class="more" href="#/e/${enc(gr.note.id)}">Group rules →</a>` : ""}</div>
        <div class="pcards">${gr.projects.map(projectCard).join("") || `<div class="empty">No projects in this group yet.</div>`}</div></section>`).join("")}
      ${projects.length ? "" : `<div class="empty">No projects yet. Say <b>new project</b> in the chat, or <span class="mono">/project &lt;name&gt;</span>.</div>`}
    </div>
    <aside class="side-col across" aria-label="Across projects">
      <div class="serif" style="font-size:28px;line-height:1.1">Across projects</div>
      ${data.decisions.length ? `<section><h3 class="acc">${g("decision")}Decisions to make · ${data.decisions.length}</h3>${data.decisions.map((d) => `<a class="xcard" href="#/e/${enc(d.id)}"><span>${esc(d.title)}</span><span class="s">${esc(d.project || "")}${d.date ? ` · proposed ${esc(rel(d.date))}` : ""}${d.by ? ` by ${esc(agentName(d.by))}` : ""}</span></a>`).join("")}</section>` : ""}
      ${data.blocked.length ? `<section><h3>Waiting on something · ${data.blocked.length}</h3>${data.blocked.map((b) => `<a class="xcard" href="#/e/${enc(b.id)}"><span class="s">${esc(b.project || "")}</span><span>${esc(b.title)}</span><span class="blk">${inline(String(b.blocked))}</span></a>`).join("")}</section>` : ""}
      ${data.lessons.length ? `<section><h3>Lessons to validate · ${data.lessons.length}</h3><ul class="mini-list">${data.lessons.map((l) => `<li data-t="lesson" style="white-space:normal">${g("lesson")}<a href="#/e/${enc(l.id)}" style="white-space:normal">${esc(l.title)}</a><span class="when">${esc(l.project || "")}</span></li>`).join("")}</ul></section>` : ""}
      ${projects.length ? `<section><h3>Checkouts on ${esc(data.machine)}</h3><ul class="mini-list">${projects.map((p) => `<li>${p.checkout?.status === "ok" ? svg("check", "sm ok") : `<span style="color:var(--faint);display:inline-flex">${svg("warn", "sm")}</span>`}<a href="#/e/${enc(p.id)}">${esc(p.title)}</a><span class="when">${esc(p.checkout?.status === "ok" ? "remote matches" : p.checkout?.status || "")}</span></li>`).join("")}</ul></section>` : ""}
      ${data.operational.length ? `<section><h3>Unresolved operational captures</h3>${data.operational.map((o) => `<a class="xcard" href="#/e/${enc(o.id)}"><span>${esc(o.title)}</span><span class="s">${esc(o.facts?.project || "")}${o.date ? ` · ${esc(rel(o.date))}` : ""}</span></a>`).join("")}</section>` : ""}
    </aside></div>`;
}

const BOOT_PARTS = [["identity", "identity", "var(--agent-1)"], ["user", "you", "var(--you-bg)"], ["project", "project", "var(--soft)"], ["rules", "group rules", "var(--faint)"],
  ["decisions", "decisions, never cut", "var(--project)"], ["lessons", "lessons", "var(--ok)"], ["threads", "open threads", "var(--insight)"], ["captures", "captures", "var(--capture)"]];
function bootBox(pv) {
  const b = pv.boot || {};
  if (!b.sections) return "";
  const total = Math.max(b.budget || 1, b.used || 1);
  const parts = BOOT_PARTS.filter(([k]) => b.sections[k]);
  const cnt = b.counts || {};
  const label = (k, l) => k === "decisions" ? `${cnt.decisions || 0} decisions, never cut` : k === "lessons" ? `${cnt.lessons || 0} lessons` : k === "threads" ? `${cnt.threads || 0} open threads` : l;
  return `<section class="panel" style="padding:20px;display:flex;flex-direction:column;gap:12px" aria-labelledby="boot-h">
    <h3 id="boot-h" class="kicker" style="margin:0">What an agent loads here</h3>
    <div class="cmd">atlas.py boot ${esc(pv.project)} --agent ${esc(b.agent)}</div>
    <div class="boot-bar" role="img" aria-label="${b.used} of ${b.budget} tokens">${parts.map(([k, , c]) => `<span style="width:${(b.sections[k] / total) * 100}%;background:${c}" title="${esc(k)}: ${b.sections[k]} tokens"></span>`).join("")}</div>
    <ul class="legend">${parts.map(([k, l, c]) => `<li><span class="sw" style="background:${c}"></span>${esc(label(k, l))}</li>`).join("")}</ul>
    <span style="font-size:12.5px;color:var(--faint)">${b.used} of ${b.budget} tokens${b.omitted?.length ? ` · left out for the budget: ${b.omitted.length}` : " · nothing cut"}${b.other_branch?.length ? ` · ${b.other_branch.length} on other branches` : ""}${cnt.proposed ? ` · ${cnt.proposed} proposed decision${cnt.proposed > 1 ? "s" : ""} listed` : ""}</span>
    ${(b.warnings || []).map((w) => `<div class="banner quiet" style="font-size:12.5px">${svg("warn", "sm")}<div>${inline(w)}</div></div>`).join("")}
  </section>`;
}

function renderProject(e) {
  const pv = e.project_view;
  const threads = pv.threads.filter((t) => t.status === "open");
  const closed = pv.threads.filter((t) => t.status !== "open");
  const proposed = pv.decisions.filter((d) => d.status === "proposed");
  const inForce = pv.decisions.filter((d) => d.status !== "proposed");
  const live = new Set((pv.here || []).map((a) => a.id));
  const lastLine = (t) => t.log?.at(-1);
  const ls = pv.last_session;
  const checkout = pv.checkout?.status === "ok"
    ? `<span>${svg("check", "sm ok")}${esc(pv.checkout.path.replace(/^\/home\/[^/]+/, "~"))} · remote matches</span><span>branch ${esc(pv.checkout.branch || "?")} @ ${esc(pv.checkout.head || "")}</span>`
    : `<span>${svg("warn", "sm")}${esc(pv.checkout?.status || "no checkout")} on ${esc(pv.checkout?.machine || "this machine")}</span>`;
  main.innerHTML = `
    <div class="crumbs"><a href="#/projects">Projects</a><span aria-hidden="true">/</span><span>${esc(e.group || "")}</span><span aria-hidden="true">/</span><span style="color:var(--text)">${esc(e.title)}</span></div>
    <section class="p-hero hero-row" style="margin-top:20px">
      <div style="display:flex;flex-direction:column;gap:12px">
        <div class="row"><h1>${esc(e.title)}</h1>${statusBadge(e.status)}${pv.aliases?.length ? `<span class="badge">aka ${esc(pv.aliases.join(", "))}</span>` : ""}</div>
        ${e.description ? `<p class="page-sub" style="margin:0">${esc(e.description)}</p>` : ""}
        <div class="p-meta">${pv.repo ? `<span>${esc(String(pv.repo).replace(/^https?:\/\//, ""))}</span>` : ""}${checkout}</div>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:8px">
        <button class="btn primary" data-send="/project ${esc(e.project)}" data-via="command" style="min-height:44px;padding:0 18px">${svg("play")}Work on it</button>
        <button class="btn mono" data-send="/close" data-via="command" style="min-height:44px">/close</button>
      </div>
    </section>
    ${(pv.here || []).length ? `<div style="margin-top:20px;display:flex;flex-direction:column;gap:8px">${liveStrip(pv.here)}</div>` : ""}
    <div class="p-layout">
      <div class="main-col">
        ${ls ? `<section class="left-off panel" aria-labelledby="left-h">
          <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px"><span class="kicker">Where we left off</span>
            <span style="display:inline-flex;align-items:center;gap:6px;font-size:12.5px;color:var(--soft)">${[...new Set(ls.lines.map((l) => l.agent))].map((a) => avatar(a, "s")).join("")}${esc(dayLabel(ls.date))} · ${esc([...new Set(ls.lines.map((l) => agentName(l.agent)))].join(" and "))}</span></div>
          <h2 id="left-h" class="h-serif">${inline(ls.lines.at(-1).text)}</h2>
          <div class="lines">${ls.lines.map((l) => `<div class="line">${avatar(l.agent, "s")}<div><a class="th" href="#/e/${enc(l.thread)}">${esc(l.title)}</a>${inline(l.text)}</div></div>`).join("")}</div>
          ${ls.commits?.length ? `<div class="chips" style="align-items:center;font-size:12.5px;color:var(--faint)"><span>commits</span>${ls.commits.map((c) => `<span class="badge" title="${esc(c.subject)}">${esc(c.sha.slice(0, 7))}</span>`).join("")}</div>` : ""}
        </section>` : ""}

        <section aria-labelledby="thr-h">
          <div class="sec-h" style="align-items:center"><h2 id="thr-h" class="h-serif" style="font:400 30px var(--serif);letter-spacing:0;text-transform:none;color:var(--text)">Open threads</h2><span class="sub mono">${threads.length} open · ${closed.length} closed</span>
            <button class="btn more" data-prefill="New thread in ${esc(e.project)}: ">${svg("plus", "sm")}New thread</button></div>
          ${threads.length ? `<div class="thread-list">${threads.map((t) => {
            const ll = lastLine(t), isLive = ll && live.has(ll.agent);
            const continueMove = movesOf("thread")[0];
            return `<article class="thread${isLive ? " live" : ""}" data-t="thread">
              <div class="th-head">${g("thread")}<a class="th-title" href="#/e/${enc(t.id)}">${esc(t.title)}</a>
                ${ll ? `<span style="display:inline-flex;align-items:center;gap:6px;font-size:12px;color:${isLive ? "var(--acc-ink)" : "var(--soft)"}">${isLive ? `<span class="pulse"></span>` : avatar(ll.agent, "s")}${esc(agentName(ll.agent))}, ${esc(isLive ? "now" : rel(ll.date))}</span>` : `<span style="font-size:12px;color:var(--faint)">nobody on it yet</span>`}
                ${t.branch ? `<span class="badge" style="margin-left:auto">${esc(t.branch)}</span>` : ""}</div>
              ${t.next ? `<div class="row"><span class="k">next</span><span>${inline(String(t.next))}</span></div>` : ""}
              ${t.blocked ? `<div class="row"><span class="k warn">blocked</span><span class="blk">${inline(String(t.blocked))}</span></div>` : ""}
              ${t.log?.length ? `<ol class="log">${t.log.slice(-2).map((l) => `<li><span class="w">${esc(shortDay(l.date))} · ${esc(l.agent)}</span> ${inline(l.text)}</li>`).join("")}</ol>` : ""}
              ${continueMove ? `<div><button class="btn" data-send="${esc(fillMove(continueMove.send, t))}" data-via="move" data-ctx="${esc(t.id)}">${esc(stripEmoji(continueMove.label))}</button></div>` : ""}
            </article>`; }).join("")}</div>` : `<div class="empty">No open threads.</div>`}
          ${closed.length ? `<details style="margin-top:10px"><summary style="cursor:pointer;color:var(--soft);font-size:13px">${closed.length} closed thread${closed.length > 1 ? "s" : ""}</summary><ul class="mini-list" style="margin-top:10px">${closed.map((t) => `<li data-t="thread">${g("thread")}<a href="#/e/${enc(t.id)}">${esc(t.title)}</a>${lastLine(t) ? `<span class="when">${esc(rel(lastLine(t).date))}</span>` : ""}</li>`).join("")}</ul></details>` : ""}
        </section>

        <section aria-labelledby="dec-h">
          <div class="sec-h"><h2 id="dec-h" class="h-serif" style="font:400 30px var(--serif);letter-spacing:0;text-transform:none;color:var(--text)">Decisions</h2>
            <span class="sub mono">${proposed.length} proposed · ${inForce.filter((d) => d.status === "accepted").length} accepted${inForce.some((d) => d.status === "superseded") ? ` · ${inForce.filter((d) => d.status === "superseded").length} superseded` : ""}</span></div>
          <div style="display:flex;flex-direction:column;gap:12px">
          ${proposed.map((d) => `<article class="dec-proposed">${g("decision")}<div class="txt"><span class="kicker acc-text">Proposed · needs you</span><a class="t" href="#/e/${enc(d.id)}">${esc(d.title)}</a>
              <span style="font-size:13px;color:var(--soft)">${d.by ? esc(agentName(d.by)) : ""}${d.date ? `, ${esc(rel(d.date))}` : ""}</span></div>
            <div style="display:flex;gap:6px"><button class="btn primary" data-send="Accept this decision: set its status to accepted and commit it" data-via="move" data-ctx="${esc(d.id)}" data-once>Accept</button>
              <button class="btn" data-prefill="About the decision “${esc(d.title)}”: ">Discuss</button></div></article>`).join("")}
          ${inForce.length ? `<div class="dec-list">${inForce.map((d) => `<a href="#/e/${enc(d.id)}" class="${d.status === "superseded" ? "sup" : ""}">${g("decision")}<span class="t">${esc(d.title)}</span>
            <span class="when">${d.status === "superseded" && d.superseded_by ? `superseded by “${esc(typeof d.superseded_by === "object" ? d.superseded_by.title : String(d.superseded_by).replace(/[\[\]"]/g, ""))}”` : `${esc(d.status || "")}${d.date ? ` · ${esc(d.date)}` : ""}`}</span></a>`).join("")}</div>` : ""}
          ${pv.decisions.length ? "" : `<div class="empty">No decisions recorded yet.</div>`}
          </div>
        </section>

        <section aria-labelledby="les-h">
          <div class="sec-h"><h2 id="les-h" class="h-serif" style="font:400 30px var(--serif);letter-spacing:0;text-transform:none;color:var(--text)">Lessons</h2>
            <span class="sub mono">${pv.lessons.filter((l) => l.status === "validated").length} validated · ${pv.lessons.filter((l) => l.status === "provisional").length} provisional</span></div>
          ${pv.lessons.length ? `<div class="lessons">${pv.lessons.map((l) => {
            const promote = movesOf("lesson")[0];
            return `<article class="lesson ${esc(l.status || "")}" data-t="lesson">
              <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">${l.status === "validated" ? `<span class="badge ok">${svg("check", "sm")}validated</span>` : `<span class="badge">${esc(l.status || "lesson")}</span>`}${l.applies_to ? `<span class="mono" style="font-size:11px;color:var(--faint)">applies to ${esc(l.applies_to)}</span>` : ""}</div>
              <a class="t" href="#/e/${enc(l.id)}">${esc(l.title)}</a>
              ${l.evidence ? `<span class="ev">Evidence: ${inline(String(l.evidence))}</span>` : ""}
              ${promote && !l.promoted_to && l.status !== "superseded" ? `<button class="btn" style="align-self:flex-start" data-send="${esc(fillMove(promote.send, l))}" data-via="move" data-ctx="${esc(l.id)}">${g("insight")}${esc(stripEmoji(promote.label))}</button>` : ""}
            </article>`; }).join("")}</div>` : `<div class="empty">No lessons yet.</div>`}
        </section>
      </div>

      <aside class="side-col" aria-label="About this project">
        ${bootBox(pv)}
        ${pv.who?.length ? `<section><h3 class="kicker" style="margin:0 0 12px">Who works here</h3><ul class="mini-list">${pv.who.map((w) => `<li>${avatar(w.agent === "user" ? "user" : w.agent, "m", live.has(w.agent) ? "working" : null)}<span class="t">${esc(agentName(w.agent))}</span><span class="when">${live.has(w.agent) ? "here now" : `${w.lines} log line${w.lines === 1 ? "" : "s"}`}</span></li>`).join("")}</ul></section>` : ""}
        <section><h3 class="kicker" style="margin:0 0 12px">Checkouts</h3><div style="display:flex;flex-direction:column;gap:8px">
          ${pv.checkout?.status === "ok" ? `<div class="xcard"><span style="display:flex;align-items:center;gap:8px">${svg("check", "sm ok")}this machine <span class="mono" style="font-size:11px;color:var(--faint)">${esc(pv.checkout.machine)}</span></span><span class="path">${esc(pv.checkout.path)}</span></div>`
            : `<div class="xcard" style="border-style:dashed"><span>${esc(pv.checkout?.machine || "this machine")} · ${esc(pv.checkout?.status || "")}</span><span class="path">${esc(pv.checkout?.hint || "")}</span></div>`}
          ${Object.entries(pv.paths || {}).filter(([m]) => m !== pv.checkout?.machine).map(([m, p]) => `<div class="xcard"><span class="mono" style="font-size:11px;color:var(--faint)">${esc(m)}</span><span class="path">${esc(p)}</span></div>`).join("")}
        </div></section>
        ${pv.sessions?.length ? `<section><h3 class="kicker" style="margin:0 0 12px">Sessions</h3><ol class="timeline">${pv.sessions.map((s) => {
          const agents = [...new Set(s.lines.map((l) => l.agent))];
          return `<li><span class="dot" style="--av:var(--agent-${agentSlot(agents[0])})"></span><div><span class="w">${esc(shortDay(s.date))} · ${esc(agents.join(", "))}</span><span class="t">${inline(s.lines.at(-1).text)}</span></div></li>`; }).join("")}</ol></section>` : ""}
        ${pv.group_rules?.length ? `<section><h3 class="kicker" style="margin:0 0 12px">Rules of ${esc(e.group)}</h3><ul class="mini-list">${pv.group_rules.map((r) => `<li style="white-space:normal;align-items:flex-start">${svg("shield", "sm")}<span style="white-space:normal;color:var(--soft)">${inline(r)}</span></li>`).join("")}</ul></section>` : ""}
        ${(pv.outlinks?.length || pv.backlinks?.length) ? `<section><h3 class="kicker" style="margin:0 0 12px">Came from, feeds into</h3><ul class="mini-list">${[...pv.outlinks, ...pv.backlinks].map((x) => `<li data-t="${esc(x.type)}">${g(x.type)}<a href="#/e/${enc(x.id)}">${esc(typeLabel(x.type))}: ${esc(x.title)}</a></li>`).join("")}</ul></section>` : ""}
        <section><h3 class="kicker" style="margin:0 0 8px">File</h3><div class="path">${esc(e.path)}</div></section>
      </aside>
    </div>`;
  window.scrollTo(0, keptScroll(e.id));
}

// ------------------------------------------------------------------ views: a tour
// The agent's stops in reading order, then the rest: what it calls mechanical, and every note that
// changed in the period and has no stop (Atlas adds those itself, so a tour cannot hide a change).
const CHANGE = { A: "new", M: "changed" };
const kindPlural = (t, n) => (n === 1 ? typeLabel(t) : typeOf(t)?.plural || t).toLowerCase().replace(/ \(.*\)$/, "");
function renderTour(e, params) {
  const tv = e.tour_view, stops = tv.stops.filter((s) => s.card), missing = tv.stops.filter((s) => s.missing);
  const hasRest = tv.mechanical.length || tv.uncovered.length || tv.distilled;
  const total = stops.length + (hasRest ? 1 : 0);
  const key = `atlas.tour.${e.id}`, visited = new Set(store.get(key, []));
  let i = Math.max(0, Math.min(total - 1, parseInt(params.get("stop") || "0", 10) || 0));
  const day = (iso) => (iso ? shortDay(String(iso).slice(0, 10)) : "now");
  main.innerHTML = `
    <div class="crumbs"><a href="#/t/tour">Tours</a><span aria-hidden="true">/</span><span style="color:var(--text)">${esc(e.title)}</span></div>
    <section class="tour-hero">
      <div class="kicker">Tour · ${esc(day(tv.since))} → ${esc(day(tv.until))} · ${tv.changed_total.toLocaleString()} notes changed${tv.by ? ` · written by ${esc(agentName(tv.by))}` : ""}</div>
      <h1 class="e-title ${titleClass(e.title)}">${esc(e.title)}</h1>
      <div class="reader tour-intro" data-src="${esc(e.id)}">${e.html}</div>
      ${missing.length ? `<div class="banner quiet">${svg("warn")}<div>${missing.length === 1 ? "A stop names a note" : `${missing.length} stops name notes`} that do${missing.length === 1 ? "es" : ""} not exist: ${esc(missing.map((s) => s.missing).join(", "))}</div></div>` : ""}
    </section>
    <div class="tour">
      <ol class="tour-rail" id="tour-rail" aria-label="Stops"></ol>
      <section class="tour-stage panel" id="tour-stage" aria-live="polite"></section>
    </div>`;
  const stopHtml = (s, k) => `
    <div class="stop-k"><span class="kicker">Stop ${k + 1} of ${stops.length}</span>${s.change ? `<span class="badge">${CHANGE[s.change]}</span>` : ""}${s.look_closely ? `<span class="badge acc">Look closely</span>` : ""}</div>
    <a class="stop-title" data-t="${esc(s.card.type)}" href="#/e/${enc(s.card.id)}">${g(s.card.type)}<span>${esc(s.card.title)}</span></a>
    ${s.why ? `<div class="reader stop-why" data-src="${esc(e.id)}">${s.why}</div>` : ""}
    ${s.excerpt ? `<div class="reader stop-quote" data-src="${esc(s.card.id)}"><blockquote><p>${esc(s.excerpt)}</p></blockquote></div>`
      : s.card.description ? `<p class="stop-desc">${esc(s.card.description)}</p>` : ""}
    ${s.unmatched ? `<div class="stop-note">${svg("info", "sm")}Atlas could not find the passage the guide quoted in this note.</div>` : ""}
    ${s.look_closely ? `<div class="banner attn">${svg("warn")}<div class="reader" data-src="${esc(e.id)}"><b>Your call.</b> ${s.look_closely}</div></div>` : ""}
    <div class="stop-acts">
      <a class="btn" href="#/e/${enc(s.card.id)}">Open the note ${svg("arrow", "sm")}</a>
      <button class="btn ghost" data-prefill="Tour stop ${k + 1}, ${esc(s.card.id)}: ">Ask about this stop</button>
      <span class="sp"></span>
      <button class="btn ghost" id="tour-prev" ${k === 0 ? "disabled" : ""}>${svg("left", "sm")}Back</button>
      <button class="btn primary" id="tour-next">${k === total - 1 ? "Finish" : "Next"} ${svg("right", "sm")}</button>
    </div>`;
  const restHtml = () => {
    const groups = new Map();
    for (const x of tv.uncovered) { const k = `${x.type}|${x.change}`; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(x); }
    return `<div class="stop-k"><span class="kicker">The rest</span></div>
      <h2 class="h-serif">What else changed</h2>
      <p class="stop-desc">The stops cover what deserves a read. Every other note that changed in the period is listed here, so the tour hides none of them.</p>
      ${tv.mechanical.length ? `<section class="rest-group"><div class="kicker">Mechanical, says the guide · ${tv.mechanical.length}</div><div class="chips">${tv.mechanical.map(chip).join("")}</div></section>` : ""}
      ${[...groups.entries()].map(([k, xs]) => { const [t, ch] = k.split("|"); return `<details class="rest-group"><summary>${xs.length.toLocaleString()} ${esc(kindPlural(t, xs.length))} ${ch === "A" ? "arrived" : "changed"}</summary>
        <div class="chips">${xs.slice(0, 150).map(chip).join("")}${xs.length > 150 ? `<span class="chip">+${xs.length - 150}</span>` : ""}</div></details>`; }).join("")}
      ${tv.distilled ? `<p class="stop-desc">${tv.distilled} capture${tv.distilled === 1 ? " was" : "s were"} distilled and archived.</p>` : ""}
      <div class="stop-acts"><span class="sp"></span>${stops.length ? `<button class="btn ghost" id="tour-prev">${svg("left", "sm")}Back</button>` : ""}<button class="btn primary" id="tour-next">Finish ${svg("check", "sm")}</button></div>`;
  };
  const rail = () => {
    $("#tour-rail").innerHTML = stops.map((s, k) => `<li class="${k === i ? "on" : ""}" data-t="${esc(s.card.type)}"><button type="button" data-k="${k}">
        <span class="n">${visited.has(k) && k !== i ? svg("check", "sm ok") : k + 1}</span><span class="t">${esc(s.card.title)}</span>${s.look_closely ? `<span class="look" title="Look closely"></span>` : ""}</button></li>`).join("")
      + (hasRest ? `<li class="${i === stops.length ? "on" : ""}"><button type="button" data-k="${stops.length}"><span class="n">…</span><span class="t">The rest · ${(tv.mechanical.length + tv.uncovered.length).toLocaleString()} more notes</span></button></li>` : "");
    $$("#tour-rail button").forEach((b) => b.onclick = () => go(+b.dataset.k));
  };
  const finish = () => {
    const seen = store.get("atlas.lastSeen", null);
    if (tv.until && (!seen || Date.parse(tv.until) > Date.parse(seen))) store.set("atlas.lastSeen", tv.until);
    toast("Tour finished: what it covered counts as seen");
    location.hash = "#/";
  };
  const go = (k) => {
    i = Math.max(0, Math.min(total - 1, k));
    if (i < stops.length) { visited.add(i); store.set(key, [...visited]); }
    history.replaceState(null, "", `#/e/${enc(e.id)}${i ? `?stop=${i}` : ""}`);
    const stage = $("#tour-stage");
    stage.innerHTML = i < stops.length ? stopHtml(stops[i], i) : restHtml();
    $("#tour-prev")?.addEventListener("click", () => go(i - 1));
    $("#tour-next").onclick = () => (i === total - 1 ? finish() : go(i + 1));
    rail();
    if (stage.getBoundingClientRect().top < 60) stage.scrollIntoView({ block: "start" });
  };
  if (!total) { $("#tour-stage").innerHTML = `<div class="empty">This tour has no stops yet, and nothing changed in its period.</div>`; return; }
  const keys = (ev) => {
    if (!$("#tour-stage")) return document.removeEventListener("keydown", keys);
    if (ev.target.closest?.("input, textarea, select, [contenteditable]") || ev.metaKey || ev.ctrlKey || ev.altKey || !$("#palette").hidden) return;
    if (ev.key === "ArrowRight" || ev.key === "j") { ev.preventDefault(); if (i < total - 1) go(i + 1); }
    else if (ev.key === "ArrowLeft" || ev.key === "k") { ev.preventDefault(); go(i - 1); }
  };
  document.addEventListener("keydown", keys);
  state.destroyView = () => document.removeEventListener("keydown", keys);
  go(i);
  window.scrollTo(0, keptScroll(e.id));
}

// ------------------------------------------------------------------ chat: blocks and messages
const onChatPage = () => (location.hash || "").startsWith("#/chat");
// The dock is a column next to the page, except while reading a note: there it lies over the page
// (opened on demand), so the text keeps its width. Only the column remembers whether it was open.
const reading = () => document.body.classList.contains("reading");
// The chat dock is as wide as you drag its left edge; this browser remembers the width.
// Double-click the edge for the default width.
function wireDockResize() {
  const dock = $("#chat");
  const grip = document.createElement("div");
  grip.className = "dock-grip";
  grip.title = "Drag to resize · double-click for the default width";
  dock.prepend(grip);
  const root = document.documentElement;
  const set = (w) => {
    const max = Math.max(320, innerWidth - 520);
    root.style.setProperty("--chat-w", `${Math.round(Math.min(max, Math.max(300, w)))}px`);
  };
  const saved = store.get("atlas.chatWidth", 0);
  if (saved) set(saved);
  grip.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0) return;
    ev.preventDefault();
    grip.setPointerCapture(ev.pointerId);
    document.body.classList.add("dock-resizing");
    const move = (e) => set(innerWidth - e.clientX);
    const done = () => {
      grip.removeEventListener("pointermove", move);
      grip.removeEventListener("pointerup", done);
      grip.removeEventListener("pointercancel", done);
      document.body.classList.remove("dock-resizing");
      store.set("atlas.chatWidth", parseInt(root.style.getPropertyValue("--chat-w"), 10) || 0);
    };
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", done);
    grip.addEventListener("pointercancel", done);
  });
  grip.addEventListener("dblclick", () => { root.style.removeProperty("--chat-w"); store.set("atlas.chatWidth", 0); });
}

function openChat() {
  if (onChatPage() || matchMedia("(max-width: 760px)").matches) { if (!onChatPage()) location.hash = "#/chat"; return; }
  document.body.classList.add("chat-open"); state.chatOpen = true;
  if (!reading()) store.set("atlas.chatOpen", true);
  loadChat();
}
function closeChat() {
  document.body.classList.remove("chat-open"); state.chatOpen = false;
  if (!reading()) store.set("atlas.chatOpen", false);
}

function blockHtml(b, key, bag) {
  switch (b.kind) {
    case "md": return `<div class="bmd reader">${b.html}</div>`;
    case "note": return noteBlock(b.card, true);
    case "notes": return `<div class="bnotes">${b.cards.map((c) => noteBlock(c)).join("")}${b.missing ? `<div class="berror">${b.missing} not found</div>` : ""}</div>`;
    case "choices": return `<div class="bchoices">${b.title ? `<div class="btitle">${esc(b.title)}</div>` : ""}${b.options.map((o) => `<button class="choice" data-choice="${esc(o.send)}">${esc(o.label)}</button>`).join("")}</div>`;
    case "checklist": return `<div class="bcheck">${b.title ? `<div class="btitle">${esc(b.title)}</div>` : ""}${b.options.map((o) => `<label><input type="checkbox" value="${esc(o.send)}"> ${esc(o.label)}</label>`).join("")}<button class="btn primary bcheck-send">Send selection</button></div>`;
    case "chart": return `<div class="bchart">${b.title ? `<div class="btitle">${esc(b.title)}</div>` : ""}${chartSvg(b)}</div>`;
    case "graph": return `<div class="bgraph"><div class="btitle">Around <a href="#/e/${enc(b.card.id)}">${esc(b.card.title)}</a></div>${neighborhood({ type: b.card.type, neighbors: b.neighbors })}</div>`;
    case "html": bag[key] = b.html; return `<iframe class="bhtml" sandbox="allow-scripts allow-forms" data-key="${key}" title="Widget from your agent"></iframe>`;
    default: return `<div class="berror">${esc(b.text || "unknown block")}</div>`;
  }
}
const noteBlock = (c, withMoves = false) => {
  remember([c]);
  const moves = withMoves ? movesOf(c.type) : [];
  return `<div class="bnote" data-t="${esc(c.type)}" data-id="${esc(c.id)}">
    <button class="bnote-head" type="button" aria-expanded="false">
      <span class="bnote-kind">${g(c.type)}<span class="k">${esc(typeLabel(c.type))}</span>${c.status ? `<span>· ${esc(c.status)}</span>` : ""}${c.type === "capture" ? "<span>· pending distill</span>" : ""}<span class="caret">${svg("down", "sm")}</span></span>
      <span class="bnote-title">${esc(c.title)}</span>${c.description ? `<span class="bnote-desc">${esc(c.description)}</span>` : ""}</button>
    ${moves.length ? `<div class="bnote-moves">${moves.map((m) => `<button class="choice" data-send="${esc(fillMove(m.send, c))}" data-via="move" data-ctx="${esc(c.id)}" data-once>${esc(stripEmoji(m.label))}</button>`).join("")}</div>` : ""}
    <div class="bnote-body" hidden></div></div>`;
};
function chartSvg(b) {
  const data = b.data || [];
  if (!data.length) return `<div class="berror">empty chart</div>`;
  const max = Math.max(...data.map((d) => d.value), 0) || 1, unit = b.unit ? ` ${esc(b.unit)}` : "";
  if (b.type === "line") {
    const W = 560, H = 200, P = 28, step = (W - 2 * P) / Math.max(1, data.length - 1);
    const pts = data.map((d, i) => [P + i * step, H - P - (d.value / max) * (H - 2 * P)]);
    return `<svg class="chart" viewBox="0 0 ${W} ${H}"><polyline fill="none" stroke="var(--insight)" stroke-width="2.5" points="${pts.map((p) => p.join(",")).join(" ")}"/>
      ${pts.map((p, i) => `<circle cx="${p[0]}" cy="${p[1]}" r="3.5" fill="var(--insight)"><title>${esc(data[i].label)}: ${data[i].value}${unit}</title></circle>
      <text x="${p[0]}" y="${H - 8}" text-anchor="middle">${esc(data[i].label.slice(0, 10))}</text>`).join("")}</svg>`;
  }
  const W = 560, row = 26, L = 170, H = data.length * row + 8;
  return `<svg class="chart" viewBox="0 0 ${W} ${H}">${data.map((d, i) => {
    const w = Math.max(2, (d.value / max) * (W - L - 70)), y = 4 + i * row;
    return `<text x="${L - 8}" y="${y + 16}" text-anchor="end">${esc(d.label.slice(0, 26))}</text>
      <rect x="${L}" y="${y + 4}" width="${w}" height="16" rx="4" fill="var(--insight)" opacity=".85"/><text x="${L + w + 6}" y="${y + 16}">${d.value}${unit}</text>`;
  }).join("")}</svg>`;
}
function wrapWidget(html) {
  const cs = getComputedStyle(document.documentElement);
  const names = ["--bg", "--surface", "--raised", "--line", "--text", "--soft", "--faint", "--acc", "--on-acc", "--insight", "--map", "--capture", "--ok", "--bad"];
  const vars = names.map((v) => `${v}:${cs.getPropertyValue(v)}`).join(";")
    + `;--bg-elev:${cs.getPropertyValue("--surface")};--bg-sunk:${cs.getPropertyValue("--sunk")};--text-soft:${cs.getPropertyValue("--soft")};--text-faint:${cs.getPropertyValue("--faint")};--accent:${cs.getPropertyValue("--acc")};--accent-soft:${cs.getPropertyValue("--raised")}`;
  const base = `<style>:root{${vars};color-scheme:${cs.colorScheme}}html,body{margin:0}body{font:14px/1.5 ui-sans-serif,system-ui,sans-serif;color:var(--text);background:var(--surface);padding:14px}</style>`;
  const helper = `<script>window.atlas={send:function(t){parent.postMessage({atlas:"send",text:String(t)},"*")},open:function(h){parent.postMessage({atlas:"open",hash:String(h)},"*")}};function __h(){parent.postMessage({atlas:"height",h:document.documentElement.scrollHeight},"*")}addEventListener("load",__h);new ResizeObserver(__h).observe(document.documentElement);document.addEventListener("click",function(e){var a=e.target.closest&&e.target.closest('a[href^="#/"]');if(a){e.preventDefault();atlas.open(a.getAttribute("href"))}});<\/script>`;
  if (!/^\s*<(!doctype|html)/i.test(html)) return `<!doctype html><html><head><meta charset="utf-8">${base}${helper}</head><body>${html}</body></html>`;
  if (/<head[^>]*>/i.test(html)) return html.replace(/<head[^>]*>/i, (m) => m + base + helper);
  return html.replace(/<html[^>]*>/i, (m) => `${m}<head>${base}${helper}</head>`);
}

const msgKey = (m) => `${m.ts}|${m.role}|${m.kind || ""}|${m.agent || ""}`;
function agentMsgHtml(m, i, bag) {
  const blocks = m.blocks || [{ kind: "md", html: `<p>${inline(m.text)}</p>` }];
  if (m.open) remember([{ id: m.open, title: titleOf(m.open) }]);
  return `<div class="amsg" data-agent="${esc(m.agent || "")}">${avatar(m.agent, "m")}<div class="abody">
    <div class="who">${esc(agentName(m.agent))} · ${clock(m.ts)}</div>
    ${blocks.map((b, j) => blockHtml(b, `${i}-${j}`, bag)).join("")}
    ${m.open ? `<div class="opened">opened <a href="#/e/${enc(m.open)}">${esc(titleOf(m.open))}</a>${onChatPage() ? "" : ""}</div>` : ""}</div></div>`;
}
// "> " lines are a quoted passage: one block in the bubble
function bubbleText(s) {
  const out = [];
  let quote = null;
  for (const line of inline(s).split("\n")) {
    if (line.startsWith("&gt; ")) { (quote ??= []).push(line.slice(5)); continue; }
    const from = quote && /^\(from (.+)\)$/.exec(line);  // the quote's source line becomes its caption
    if (quote) { out.push({ q: quote.join("\n"), src: from ? from[1] : null }); quote = null; }
    if (!from) out.push(line);
  }
  if (quote) out.push({ q: quote.join("\n") });
  return out.map((x, k) => (typeof x === "string" ? x + (typeof out[k + 1] === "string" ? "\n" : "")
    : `<span class="q">${x.q}${x.src ? `<span class="qsrc">${esc(x.src.startsWith("an earlier") ? x.src : titleOf(x.src.replace(/&amp;/g, "&").replace(/&#39;/g, "'").replace(/&quot;/g, '"')))}</span>` : ""}</span>`)).join("");
}
function userMsgHtml(m) {
  const label = m.kind === "action" ? `${m.action}${m.text ? ": " + m.text : ""}` : m.text;
  const ctx = [m.context ? `viewing · ${esc(titleOf(m.context))}` : "", m.via ? `via ${esc(m.via)}` : "", m.to ? `to ${esc(agentName(m.to))}` : ""].filter(Boolean).join(" · ");
  const quoted = /(^|\n)> /.test(label || "");
  return `<div class="umsg" data-to="${esc(m.to || "")}">${ctx ? `<span class="ctx">${ctx}</span>` : ""}<div class="bubble${(m.via === "choice" || m.via === "move") && !quoted ? " via" : ""}">${bubbleText(label)}</div></div>`;
}
function runHtml(m) {
  return `<div class="amsg" data-agent="${esc(m.agent || "")}" data-run="${esc(m.agent || "_")}">${avatar(m.agent, "m")}<div class="abody">
    <div class="run live"><div class="run-h"><span>${esc(agentName(m.agent))} · started ${clock(m.ts)}</span><span class="live-tag"><span class="pulse"></span>live</span></div><ol class="steps"></ol></div></div></div>`;
}
function stepHtml(m) { return `<li data-ts="${esc(m.ts)}"><span class="mk"></span><span>${inline(m.text)}</span></li>`; }
function closeRun(el, endTs) {
  if (!el) return;
  const run = el.querySelector(".run"), first = el.querySelector(".steps li")?.dataset.ts;
  run.classList.remove("live");
  run.querySelector(".live-tag")?.remove();
  if (first && endTs) run.querySelector(".run-h span").insertAdjacentHTML("beforeend", ` → ${clock(endTs)}`);
  el.dataset.closed = "1";
}
function paintRuns(container) {  // the newest step of a run whose agent is still working gets the live dot
  const working = new Set(liveAgents().filter((a) => a.state === "working").map((a) => a.id || "_"));
  container.querySelectorAll("[data-run]").forEach((el) => {
    const open = !el.dataset.closed && working.has(el.dataset.run);
    if (!open && !el.dataset.closed && el.querySelector(".run.live")) { el.querySelector(".run").classList.remove("live"); el.querySelector(".live-tag")?.remove(); }
    const items = [...el.querySelectorAll(".steps li")];
    items.forEach((li, i) => {
      const live = open && i === items.length - 1;
      li.classList.toggle("live", live);
      li.querySelector(".mk").outerHTML = live ? `<span class="mk pulse"></span>` : `<span class="mk">${svg("check", "ok")}</span>`;
    });
  });
}

function renderLog(container, messages, empty) {
  if (!container) return;
  container._seen ??= new Set();
  container._bag ??= {};
  container._runs ??= {};
  container.querySelector(".typing")?.remove();
  const fresh = messages.filter((m) => !container._seen.has(msgKey(m)));
  if (!container._seen.size) { container.innerHTML = messages.length ? "" : empty; container._day = null; }
  if (fresh.length) {
    container.querySelector(".chat-welcome, .msg.system")?.remove();
    fresh.forEach((m, k) => {
      const day = localDay(toDate(m.ts));
      if (day !== container._day) { container._day = day; container.insertAdjacentHTML("beforeend", `<div class="day-div">${esc(dayLabel(day))} · ${clock(m.ts)}</div>`); }
      const who = m.agent || "_";
      if (m.role === "agent" && m.kind === "progress") {
        let run = container._runs[who];
        if (!run || !run.isConnected || run.dataset.closed) {
          container.insertAdjacentHTML("beforeend", runHtml(m));
          run = container._runs[who] = container.lastElementChild;
        }
        run.querySelector(".steps").insertAdjacentHTML("beforeend", stepHtml(m));
      } else if (m.role === "agent") {
        closeRun(container._runs[who], m.ts); delete container._runs[who];
        container.insertAdjacentHTML("beforeend", agentMsgHtml(m, container._seen.size + k, container._bag));
      } else container.insertAdjacentHTML("beforeend", userMsgHtml(m));
      container._seen.add(msgKey(m));
    });
    wireBlocks(container, container._bag);
  }
  paintRuns(container);
  const busy = liveAgents().filter((a) => a.state === "working" && !container.querySelector(`[data-run="${CSS.escape(a.id || "_")}"]:not([data-closed])`));
  if (busy.length) container.insertAdjacentHTML("beforeend", `<div class="typing"><span class="pulse"></span>${esc(busy.map((a) => agentName(a.id)).join(" and "))} ${busy.length > 1 ? "are" : "is"} working…</div>`);
  applyFilter(container);
  if (fresh.length || busy.length) {
    container.scrollTop = container.scrollHeight;
    document.fonts?.ready.then(() => requestAnimationFrame(() => (container.scrollTop = container.scrollHeight)));
  }
}
function applyFilter(container) {
  const f = container.id === "page-log" ? state.chatFilter : null;
  container.querySelectorAll(".amsg").forEach((el) => (el.hidden = !!f && el.dataset.agent !== f));
  container.querySelectorAll(".umsg").forEach((el) => (el.hidden = !!f && !!el.dataset.to && el.dataset.to !== f));
}

function wireBlocks(root, bag) {
  root.querySelectorAll("iframe.bhtml:not([data-wired])").forEach((f) => { f.dataset.wired = "1"; f.srcdoc = wrapWidget(bag[f.dataset.key] || ""); });
  root.querySelectorAll(".bnote-head:not([data-wired])").forEach((h) => {
    h.dataset.wired = "1";
    h.onclick = async () => {
      const box = h.parentElement, body = box.querySelector(".bnote-body");
      body.hidden = !body.hidden; box.classList.toggle("open", !body.hidden); h.setAttribute("aria-expanded", String(!body.hidden));
      if (!body.hidden && !body.dataset.loaded) {
        body.innerHTML = `<div class="loading">Loading…</div>`;
        const e = await api(`/api/entity?id=${enc(box.dataset.id)}`).catch(() => null);
        body.dataset.loaded = "1";
        const ep = e && epistemic(e);
        body.innerHTML = e ? `${ep ? `<div class="banner" style="margin-top:12px">${svg("info")}<div>${esc(ep[1])}</div></div>` : ""}<div class="reader" data-src="${esc(e.id)}">${e.html}</div><a class="btn" href="#/e/${enc(e.id)}">Open the full page ${svg("arrow", "sm")}</a>` : `<div class="berror">Could not load.</div>`;
      }
    };
  });
  root.querySelectorAll(".bchoices:not([data-wired])").forEach((box) => {
    box.dataset.wired = "1";
    box.querySelectorAll(".choice").forEach((b) => b.onclick = () => {
      box.querySelectorAll(".choice").forEach((x) => { x.disabled = true; x.classList.toggle("chosen", x === b); });
      sendText(b.dataset.choice, "choice");
    });
  });
  root.querySelectorAll(".bcheck:not([data-wired])").forEach((box) => {
    box.dataset.wired = "1";
    box.querySelector(".bcheck-send").onclick = () => {
      const picked = [...box.querySelectorAll("input:checked")].map((i) => i.value);
      if (!picked.length) return toast("Nothing selected");
      box.querySelectorAll("input,button").forEach((x) => (x.disabled = true));
      sendText(`Selected: ${picked.join("; ")}`, "checklist");
    };
  });
}

let lastOpen = null, lastAgentTs = null;
const chatVisible = () => (state.chatOpen || onChatPage()) && document.visibilityState === "visible";
function updateUnread(messages) {
  const agent = (messages || []).filter((m) => m.role === "agent" && m.kind !== "progress").map((m) => m.ts);
  const newest = agent.at(-1) || "";
  let read = store.get("atlas.chatReadTs", null);
  if (read === null || chatVisible()) { read = newest; store.set("atlas.chatReadTs", read); }
  const readAt = Date.parse(read) || 0;
  const n = agent.filter((ts) => Date.parse(ts) > readAt).length;
  const label = n > 9 ? "9+" : String(n);
  const toggle = $("#chat-toggle");
  toggle.querySelector(".unread-dot")?.remove();
  if (n) toggle.insertAdjacentHTML("beforeend", `<span class="unread-dot">${label}</span>`);
  const nav = document.querySelector('.nav-link[href="#/chat"]');
  if (nav) { nav.querySelector(".unread-count")?.remove(); if (n) nav.insertAdjacentHTML("beforeend", `<span class="unread-count">${label}</span>`); }
  document.title = n ? `(${label}) Atlas` : "Atlas";
}

async function loadChat() {
  const data = await api("/api/chat");
  const agentTs = [...data.messages].reverse().find((m) => m.role === "agent" && m.kind !== "progress")?.ts || "";
  const fresh = lastAgentTs !== null && agentTs > lastAgentTs;
  lastAgentTs = agentTs;
  state.chatMessages = data.messages;
  state.operator = data.operator;
  renderPresence();
  updateUnread(data.messages);
  const empty = `<div class="msg system">${state.operator.mode === "operator" ? "Say hi. Your agent is on the other end." : "Write a thought. It is kept as a note for your agent."}</div>`;
  if (state.chatOpen) renderLog($("#chat-log"), data.messages, empty);
  if (onChatPage()) { renderLog($("#page-log"), data.messages, chatWelcome()); renderFilter(); renderTabs(); renderOpTitle(); }
  refreshShift();
  const opener = [...data.messages].reverse().find((m) => m.role === "agent" && m.open);
  if (opener && lastOpen !== null && opener.ts !== lastOpen) {
    const who = agentName(opener.agent);
    if (store.get("atlas.follow", true)) {
      if (onChatPage()) { store.set("atlas.wb", opener.open); renderTabs(); renderWorkbench(); }
      else { location.hash = `#/e/${enc(opener.open)}`; toast(`${who} opened a page for you`); }
    } else toast(`${who} opened ${titleOf(opener.open)}`);
  }
  if (opener) lastOpen = opener.ts; else if (lastOpen === null) lastOpen = "";
  return fresh;
}
const SUGGESTIONS = [["Research what's new in a topic I care about", "Research what's new in ‹sleep and memory›"],
  ["I have an idea…", "I have an idea: ‹a timer that adapts to how focused I am›"],
  ["What do I already know about…?", "What do I already know about ‹sleep and memory›?"], ["What should we do next?", "What should we do next?"]];
const chatWelcome = () => `<div class="chat-welcome empty-hero" style="margin:auto;text-align:center;align-items:center"><h1 style="font-size:40px">Ask your knowledge graph</h1>
  <p>${state.operator.mode === "operator" ? "Your agents answer here with notes you can unfold, charts, choices and live mockups. What they open lands in the workbench." : "No agent is attached. Open Claude Code or Codex in this folder and say “start atlas”; until then your messages are kept as notes."}</p>
  <div class="chips" style="justify-content:center">${SUGGESTIONS.map(([label, fill]) => `<button class="facet" data-prefill="${esc(fill)}">${esc(label)}</button>`).join("")}</div>
  ${commandList().length ? `<p style="font-size:13px">Type <b>/</b> for commands: ${commandList().slice(0, 6).map((c) => `<code class="mono">/${esc(c.name)}</code>`).join(" ")}…</p>` : ""}</div>`;

// ------------------------------------------------------------------ composer and commands
const commandList = () => state.meta?.commands || [];
function asCommand(text) {
  const m = /^\/([\w-]+)\s*([\s\S]*)$/.exec(text.trim());
  const cmd = m && commandList().find((c) => c.name === m[1]);
  return cmd ? (cmd.send || `/${cmd.name} {args}`).replace("{args}", m[2].trim()).trim() : null;
}
function composer(id, placeholder) {
  return `<form class="composer" id="${id}-form">
    <div class="composer-meta" id="${id}-meta"></div>
    <div class="composer-box"><label class="sr" for="${id}-input">Message your agent</label>
      <textarea id="${id}-input" rows="2" placeholder="${esc(placeholder)}"></textarea>
      <button class="send" type="submit" aria-label="Send">${`<svg viewBox="0 0 16 16" aria-hidden="true">${P.send}</svg>`}</button></div></form>`;
}
const composers = {};
function wireComposer(id, getContext, after = null) {
  const form = $(`#${id}-form`), input = $(`#${id}-input`);
  if (!form) return;
  composers[id] = getContext;
  attachCommands(input, form);
  const send = async (ev) => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    const ctx = state.ctxOn ? getContext()?.id || null : null;
    input.value = ""; fit(input);
    if (await sendText(text, null, ctx)) after?.(); else input.value = text;
  };
  form.onsubmit = send;
  input.addEventListener("input", () => fit(input));
  input.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) send(ev); });
  renderComposerMeta(id);
}
function renderComposerMeta(id) {
  const box = $(`#${id}-meta`);
  if (!box) return;
  const agents = toChoices(), ctx = composers[id]?.(), to = currentTo();
  box.innerHTML = (agents.length > 1 || (agents.length === 1 && agents[0].state === "offline") ? `<span>To</span><select class="to-select" aria-label="Send to">${agents.map((a) => `<option value="${esc(a.id)}"${a.id === to ? " selected" : ""}>${esc(agentName(a.id))}${a.state === "listening" ? "" : ` · ${esc(ST_LABEL[a.state] || a.state)}`}</option>`).join("")}</select>`
    : agents.length === 1 ? `<span>To ${esc(agentName(agents[0].id))}</span>` : "")
    + (ctx ? `<label class="ctx-chip" title="${esc(ctx.id)}"><input type="checkbox"${state.ctxOn ? " checked" : ""}><span>with page · ${esc(ctx.title)}</span></label>` : "");
  box.querySelector("select")?.addEventListener("change", (ev) => { store.set("atlas.to", ev.target.value); updateComposers(); });
  box.querySelector(".ctx-chip input")?.addEventListener("change", (ev) => { state.ctxOn = ev.target.checked; updateComposers(); });
}
function updateComposers() { Object.keys(composers).forEach(renderComposerMeta); }
function attachCommands(input, form) {
  if (!input || input.dataset.cmds) return;
  input.dataset.cmds = "1";
  const pop = document.createElement("div");
  pop.className = "cmd-pop"; pop.hidden = true; pop.setAttribute("role", "listbox"); pop.setAttribute("aria-label", "Commands");
  form.appendChild(pop);
  let items = [], sel = 0;
  const draw = () => {
    pop.innerHTML = items.map((c, i) => `<button type="button" role="option" aria-selected="${i === sel}" class="cmd${i === sel ? " on" : ""}" data-i="${i}"><b>/${esc(c.name)}</b>${c.args ? `<span class="args">${esc(c.args)}</span>` : ""}<span class="help">${esc(c.help || "")}</span></button>`).join("");
    pop.querySelectorAll(".cmd").forEach((b) => b.onmousedown = (ev) => { ev.preventDefault(); sel = +b.dataset.i; complete(); });
  };
  const update = () => {
    const m = /^\/([\w-]*)$/.exec(input.value);
    items = m ? commandList().filter((c) => c.name.startsWith(m[1].toLowerCase())) : [];
    sel = Math.min(sel, Math.max(0, items.length - 1));
    pop.hidden = !items.length; if (items.length) draw();
  };
  const complete = () => { const c = items[sel]; if (!c) return; input.value = `/${c.name}${c.args ? " " : ""}`; pop.hidden = true; input.focus(); };
  input.addEventListener("input", update);
  input.addEventListener("blur", () => setTimeout(() => (pop.hidden = true), 120));
  input.addEventListener("keydown", (ev) => {
    if (pop.hidden) return;
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") { ev.preventDefault(); sel = (sel + (ev.key === "ArrowDown" ? 1 : -1) + items.length) % items.length; draw(); }
    else if (ev.key === "Tab" || (ev.key === "Enter" && !ev.shiftKey && !commandList().some((c) => `/${c.name}` === input.value.trim() && !c.args))) {
      ev.preventDefault(); ev.stopImmediatePropagation(); complete();
    } else if (ev.key === "Escape") pop.hidden = true;
  });
}

async function sendText(text, via = null, context = null) {
  const command = via ? null : asCommand(text);
  if (command) { text = command; via = "command"; }
  try {
    const res = await post("/api/chat", { text, context, via, to: currentTo() });
    if (res.delivered === "note") toast(`Kept as a note: ${res.note}`);
    loadChat();
    return true;
  } catch (err) {
    toast("Could not send. Is the Atlas server running?");
    return false;
  }
}

// ------------------------------------------------------------------ views: operator (conversation + workbench)
// The bar above the conversation names what the agent is doing (`say --title`). While it works on a
// request it has not titled yet, the request stands in; when it is idle, the last title stays.
function renderOpTitle() {
  const el = $("#op-title");
  if (!el) return;
  const msgs = state.chatMessages, lastUser = msgs.filter((m) => m.role === "user").at(-1)?.ts || "";
  const titled = msgs.filter((m) => m.role === "agent" && m.title).at(-1);
  const busy = liveAgents().find((a) => a.state === "working");
  const current = titled && (!busy || titled.ts >= lastUser);  // >=: timestamps have one-second resolution
  let text = current ? titled.title : "";
  if (current && titled.agent && named().length > 1) text = `${agentName(titled.agent)}: ${text}`;
  if (!text && busy) text = busy.task ? `Working on: ${busy.task.text}` : "Working";
  el.innerHTML = text ? `${busy ? '<span class="pulse"></span>' : ""}<span class="t">${esc(text)}</span>` : "";
  el.title = text;
  el.classList.toggle("live", !!busy);
}
function renderFilter() {
  const box = $("#op-filter");
  if (!box) return;
  const ids = [...new Set([...named().map((a) => a.id), ...state.chatMessages.filter((m) => m.role === "agent" && m.agent).map((m) => m.agent)])];
  if (ids.length < 2) { box.hidden = true; state.chatFilter = null; return; }
  box.hidden = false;
  const cur = state.chatFilter || "";
  box.innerHTML = [["", "Everyone"], ...ids.map((id) => [id, agentName(id)])].map(([id, l]) => `<button type="button" data-f="${esc(id)}" aria-pressed="${cur === id}">${esc(l)}</button>`).join("");
  box.querySelectorAll("button").forEach((b) => b.onclick = () => { state.chatFilter = b.dataset.f || null; renderFilter(); applyFilter($("#page-log")); });
}
function opened() {  // pages the agents opened for the user, newest last
  const seen = new Map();
  for (const m of state.chatMessages) if (m.role === "agent" && m.open) { seen.delete(m.open); seen.set(m.open, m); }
  return [...seen.values()].slice(-8);
}
function renderTabs() {
  const box = $("#wb-tabs");
  if (!box) return;
  const tabs = opened(), active = store.get("atlas.wb", null);
  box.innerHTML = tabs.map((m) => `<button type="button" role="tab" aria-selected="${m.open === active}" data-id="${esc(m.open)}">${avatar(m.agent, "s")}<span class="t">${esc(titleOf(m.open))}</span></button>`).join("");
  box.hidden = !tabs.length;
  box.querySelectorAll("button").forEach((b) => b.onclick = () => { store.set("atlas.wb", b.dataset.id); renderTabs(); renderWorkbench(); });
}
async function renderWorkbench() {
  const body = $("#wb-body"), movesBox = $("#wb-moves"), who = $("#wb-who");
  if (!body) return;
  const tabs = opened();
  let id = store.get("atlas.wb", null);
  if (!tabs.some((m) => m.open === id)) id = tabs.at(-1)?.open || null;
  const fromAgent = tabs.find((m) => m.open === id);
  if (!id) {
    body.innerHTML = `<div class="wb-empty"><div class="serif">The workbench</div><p>When an agent opens a page for you (<span class="mono">say --open</span>), it lands here, next to the conversation.</p></div>`;
    movesBox.innerHTML = ""; who.innerHTML = ""; state.wbEntity = null; updateComposers(); return;
  }
  const e = await api(`/api/entity?id=${enc(id)}`).catch(() => null);
  if (!e) { body.innerHTML = `<div class="wb-empty">This page is gone: ${esc(id)}</div>`; return; }
  remember([e]);
  state.wbEntity = e;
  const liveAge = e.modified ? (Date.now() - Date.parse(e.modified)) / 1000 : 1e9;
  who.innerHTML = fromAgent ? `${avatar(fromAgent.agent, "s")}${esc(agentName(fromAgent.agent))} opened this · ${clock(fromAgent.ts)}${liveAge < 180 ? ` <span class="live-badge"><span class="pulse"></span>changed ${since(e.modified)}</span>` : ""}` : "";
  body.innerHTML = `<div class="reader-col" style="margin:0 auto">${readerHead(e, { crumbs: false })}<div class="reader" data-src="${esc(e.id)}">${e.html}</div>
    <a class="btn ghost" href="#/e/${enc(e.id)}" style="align-self:flex-start">Open the full page ${svg("arrow", "sm")}</a></div>`;
  movesBox.innerHTML = movesBar(e).replace("moves-bar panel", "moves-bar");
  updateComposers();
}
async function viewChat() {
  document.body.classList.remove("chat-open"); state.chatOpen = false;
  main.classList.add("bleed");
  main.innerHTML = `<div class="op">
    <section class="op-conv" aria-label="Conversation">
      <div class="op-bar"><span class="op-title" id="op-title" aria-live="polite"></span><div class="seg" role="group" aria-label="Show messages from" id="op-filter" hidden></div></div>
      <div class="chat-log" id="page-log"></div>
      ${composer("page", "Write to your agent…  type / for commands · Enter sends, Shift+Enter for a new line")}
    </section>
    <section class="op-wb" aria-label="Workbench">
      <div class="wb-bar"><span class="kicker">Workbench</span><span class="who" id="wb-who"></span>
        <label class="switch"><input type="checkbox" id="wb-follow"${store.get("atlas.follow", true) ? " checked" : ""}><span class="track"></span>Follow the agent</label></div>
      <div class="wb-tabs" role="tablist" aria-label="Pages the agents opened" id="wb-tabs"></div>
      <div class="wb-body" id="wb-body"></div>
      <div class="wb-moves" id="wb-moves"></div>
    </section></div>`;
  $("#wb-follow").onchange = (ev) => store.set("atlas.follow", ev.target.checked);
  const wbShown = () => !matchMedia("(max-width: 980px)").matches;  // the workbench is hidden on narrow screens
  wireComposer("page", () => state.wbEntity && wbShown() ? { id: state.wbEntity.id, title: state.wbEntity.title } : null);
  await loadChat();
  renderWorkbench();
  applyPrefill();
  if (state.prefill == null) $("#page-input").focus();
}

window.addEventListener("message", (ev) => {
  const frame = [...document.querySelectorAll("iframe.bhtml")].find((f) => f.contentWindow === ev.source);
  if (!frame || !ev.data || typeof ev.data !== "object") return;
  if (ev.data.atlas === "open" && /^#\/(e|t|graph|chat|projects|rediscover|search)\b/.test(String(ev.data.hash))) location.hash = ev.data.hash;  // internal routes only
  if (ev.data.atlas === "height") frame.style.height = Math.min(Math.max((+ev.data.h || 0) + 4, 60), 1400) + "px";
  if (ev.data.atlas === "send") {
    const now = Date.now();
    if (now - (state.lastWidgetSend || 0) < 1500) return;  // a widget cannot flood the agent
    state.lastWidgetSend = now;
    sendText(String(ev.data.text).slice(0, 4000), "widget");
  }
});

// ------------------------------------------------------------------ quote a passage: select text in a note, ask or challenge
// The quote travels in the message text with its source path, so it still says what it quoted
// when the note changes later.
function selectedQuote() {
  const sel = getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) return null;
  const range = sel.getRangeAt(0), node = range.commonAncestorContainer;
  const reader = (node.nodeType === 1 ? node : node.parentElement)?.closest(".reader");
  if (!reader || reader.closest("#palette, .composer")) return null;
  const text = sel.toString().replace(/[ \t]+/g, " ").replace(/\n{2,}/g, "\n").trim();
  if (text.length < 3) return null;
  const src = reader.dataset.src || reader.closest("[data-src]")?.dataset.src || "";
  return { text: text.length > 1500 ? text.slice(0, 1500) + "…" : text, src, rect: range.getBoundingClientRect() };
}
const quoteBlock = (q) => `${q.text.split("\n").map((l) => `> ${l}`).join("\n")}\n${q.src ? `(from ${q.src})` : "(from an earlier answer)"}`;
function showQuoteBar() {
  const bar = $("#quote-bar"), q = selectedQuote();
  if (!q) { bar.hidden = true; return; }
  bar.innerHTML = `<button type="button" data-q="ask">${svg("pen", "sm")}Ask about this</button><button type="button" data-q="challenge">Challenge it</button>`;
  bar.hidden = false;
  const w = bar.offsetWidth, above = q.rect.top > 56;
  bar.style.left = `${Math.max(12, Math.min(q.rect.left + q.rect.width / 2 - w / 2, innerWidth - w - 12))}px`;
  bar.style.top = `${above ? q.rect.top - bar.offsetHeight - 8 : q.rect.bottom + 8}px`;
  bar.querySelectorAll("button").forEach((b) => b.onmousedown = (ev) => {
    ev.preventDefault();  // keep the selection until the click is handled
    bar.hidden = true;
    getSelection()?.removeAllRanges();
    if (b.dataset.q === "ask") prefill(`${quoteBlock(q)}\n\n`);
    else sendText(`Challenge this passage: does it hold up?\n${quoteBlock(q)}`, "move", q.src || null);
  });
}
let quoteTimer = null;
document.addEventListener("selectionchange", () => { clearTimeout(quoteTimer); quoteTimer = setTimeout(showQuoteBar, 220); });

// ------------------------------------------------------------------ palette (⌘K): notes, places, projects; ">" lists commands
const PLACES = [["Home", "#/", "home"], ["Operator", "#/chat", "chat"], ["Projects", "#/projects", "projects"], ["Constellation", "#/graph", "graph"], ["Rediscover", "#/rediscover", "rediscover"]];
const pal = { items: [], sel: 0, seq: 0, notes: [] };
const recentNotes = () => store.get("atlas.recent", []);
const rememberVisit = (e) => store.set("atlas.recent", [{ id: e.id, type: e.type, title: e.title }, ...recentNotes().filter((x) => x.id !== e.id)].slice(0, 8));
function openPalette() {
  hideHover();
  $("#palette").hidden = false;
  const input = $("#pal-input");
  input.value = ""; palQuery(""); input.focus();
}
const closePalette = () => { $("#palette").hidden = true; };
function palRun(i, deep = false) {
  const it = deep ? pal.items.find((x) => x.deep) : pal.items[i];
  if (!it) return;
  closePalette(); it.run();
}
function palDraw() {
  let html = "", section = null;
  pal.items.forEach((it, i) => {
    if (it.section !== section) { section = it.section; html += `<div class="pal-sec">${esc(section)}</div>`; }
    html += `<button type="button" role="option" class="pal-row${i === pal.sel ? " on" : ""}" aria-selected="${i === pal.sel}" data-i="${i}"${it.t ? ` data-t="${esc(it.t)}"` : ""}>
      <span class="ico">${it.ico || ""}</span><span class="lbl">${it.html || esc(it.label)}</span>${it.sub ? `<span class="sub">${esc(it.sub)}</span>` : ""}</button>`;
  });
  const list = $("#pal-list");
  list.innerHTML = (html || `<div class="pal-empty">Nothing matches.</div>`) + `<div class="pal-foot"><span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>↵</kbd> open</span><span><kbd>&gt;</kbd> commands</span></div>`;
  list.querySelectorAll(".pal-row").forEach((b) => {
    b.onmousemove = () => { if (pal.sel !== +b.dataset.i) { pal.sel = +b.dataset.i; pal.moved = true; palDraw(); } };
    b.onclick = () => palRun(+b.dataset.i);
  });
  list.querySelector(".pal-row.on")?.scrollIntoView({ block: "nearest" });
}
async function palQuery(q) {
  const seq = ++pal.seq, query = q.trim(), lower = query.toLowerCase();
  const go = (hash) => () => { location.hash = hash; };
  pal.q = q; pal.sel = 0; pal.moved = false;
  if (query.startsWith(">")) {  // a command goes into the composer: nothing is sent before Enter there
    const w = lower.replace(/^>\s*\/?/, "");
    const score = (c) => (!w ? 0 : c.name.startsWith(w) ? 0 : c.name.includes(w) ? 1 : (c.help || "").toLowerCase().includes(w) ? 2 : 9);
    pal.items = commandList().filter((c) => score(c) < 9).sort((a, b) => score(a) - score(b)).map((c) => ({ section: "Commands",
      html: `<b class="mono">/${esc(c.name)}</b>${c.args ? ` <span class="mono faint">${esc(c.args)}</span>` : ""}`, sub: c.help,
      run: () => prefill(`/${c.name}${c.args ? " " : ""}`) }));
    return palDraw();
  }
  const hit = (s) => !lower || s.toLowerCase().includes(lower);
  const places = PLACES.filter(([l]) => hit(l)).map(([l, h, k]) => ({ section: "Go to", ico: navIcon(k), label: l, run: go(h) }));
  const types = lower ? state.meta.types.filter((t) => t.nav !== false && t.count && hit(t.plural)).map((t) => ({ section: "Go to", ico: g(t.id), t: t.id, label: t.plural, sub: String(t.count), run: go(`#/t/${enc(t.id)}`) })) : [];
  const projects = lower ? (state.meta.projects || []).filter((p) => hit(p.title)).slice(0, 5).map((p) => ({ section: "Projects", ico: g("project"), t: "project", label: p.title, run: go(`#/e/${enc(p.id)}`) })) : [];
  const recent = lower ? [] : recentNotes().map((e) => ({ section: "Recent", ico: g(e.type), t: e.type, label: e.title, sub: typeLabel(e.type), run: go(`#/e/${enc(e.id)}`) }));
  const search = lower ? [{ section: "Search", ico: svg("arrow"), html: `Search the vault for <b>“${esc(query)}”</b>`, run: go(`#/search?q=${enc(query)}`) },
    ...(state.meta.qmd ? [{ section: "Search", ico: svg("arrow"), html: `Deep search (QMD) for <b>“${esc(query)}”</b>`, sub: "Shift+↵", deep: true, run: go(`#/search?q=${enc(query)}&mode=deep`) }] : [])] : [];
  pal.notes = [];
  const build = () => {  // notes arrive late and go on top: a row the reader moved to stays selected
    const cur = pal.items[pal.sel];
    pal.items = [...recent, ...pal.notes, ...projects, ...places, ...types, ...search];
    pal.sel = pal.moved && pal.items.includes(cur) ? pal.items.indexOf(cur) : 0;
    palDraw();
  };
  pal.items = [];
  build();
  if (lower.length < 2) return;
  const data = await api(`/api/search?q=${enc(query)}&n=8`).catch(() => null);
  if (seq !== pal.seq || !data) return;
  pal.notes = remember(data.results).map((e) => ({ section: "Notes", ico: g(e.type), t: e.type, label: e.title, sub: typeLabel(e.type), run: go(`#/e/${enc(e.id)}`) }));
  build();
}
function wirePalette() {
  const input = $("#pal-input");
  let timer = null;
  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => palQuery(input.value), 120); });
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      if (pal.items.length) { pal.sel = (pal.sel + (ev.key === "ArrowDown" ? 1 : -1) + pal.items.length) % pal.items.length; pal.moved = true; palDraw(); }
    } else if (ev.key === "Enter") {
      ev.preventDefault(); clearTimeout(timer);
      if (input.value !== pal.q) palQuery(input.value);  // typed faster than the list: build it for what is typed now
      palRun(pal.sel, ev.shiftKey);
    }
    else if (ev.key === "Escape") { ev.preventDefault(); closePalette(); }
  });
  $("#palette").addEventListener("mousedown", (ev) => { if (ev.target.id === "palette") closePalette(); });
}

// ------------------------------------------------------------------ drop a file or a link on Atlas: it becomes a capture
// A file lands in the registry's drop folder; the composer then holds the registry's line for it.
let dragInside = false;
document.addEventListener("dragstart", () => { dragInside = true; });
document.addEventListener("dragend", () => { dragInside = false; });
const dropKind = (dt) => (dt?.types || []).includes("Files") ? "file" : (dt?.types || []).includes("text/uri-list") ? "url" : null;
function wireDrop() {
  const veil = $("#drop-veil"), d = state.meta.drop || {};
  let depth = 0;
  const off = () => { depth = 0; veil.hidden = true; };
  document.addEventListener("dragenter", (ev) => {
    const kind = dropKind(ev.dataTransfer);
    if (dragInside || !kind) return;
    depth++;
    $("#drop-what").textContent = kind === "file" ? `Files land in ${d.dir}/, then your agent takes them from there.` : "Your agent reads the link and lands what matters as a capture.";
    veil.hidden = false;
  });
  document.addEventListener("dragleave", () => { if (!veil.hidden && --depth <= 0) off(); });
  document.addEventListener("dragover", (ev) => { if (!dragInside && dropKind(ev.dataTransfer)) ev.preventDefault(); });
  document.addEventListener("drop", async (ev) => {
    const kind = dropKind(ev.dataTransfer);
    if (dragInside || !kind) return;
    ev.preventDefault(); off();
    if (kind === "url") {
      const url = (ev.dataTransfer.getData("text/uri-list") || "").split("\n").find((l) => /^https?:\/\//.test(l.trim()))?.trim();
      if (url) prefill(d.url.replace("{url}", () => url));
      return;
    }
    const lines = [];
    for (const file of ev.dataTransfer.files) {
      toast(`Saving ${file.name}…`);
      const res = await fetch("/api/drop", { method: "POST", body: file, headers: { "x-atlas": "1", "x-filename": encodeURIComponent(file.name), "content-type": file.type || "application/octet-stream" } })
        .then((r) => r.json()).catch(() => null);
      if (res?.path) lines.push(d.file.replace("{path}", () => res.path));
      else toast(`Could not save ${file.name}${res?.error ? `: ${res.error}` : ""}`);
    }
    if (lines.length) { prefill(lines.join("\n")); toast(`Saved to ${d.dir}/. Send it when you are ready.`); }
  });
}

// ------------------------------------------------------------------ router, stream, boot
function disposeView() {  // what the open view installed outside main (key handlers, the graph's loop)
  if (state.destroyView) { try { state.destroyView(); } catch {} state.destroyView = null; }
}
async function route() {
  const hash = location.hash || "#/";
  const [path, qs] = hash.slice(1).split("?");
  const params = new URLSearchParams(qs || "");
  document.body.classList.remove("nav-open");
  $("#nav-toggle").setAttribute("aria-expanded", "false");
  hideHover(); $("#quote-bar").hidden = true; closePalette();
  state.routeToken = (state.routeToken || 0) + 1;
  disposeView();
  if (state.keepScroll && decodeURIComponent(path.slice(3)) !== state.keepScroll.id) state.keepScroll = null;  // the reader left a refresh
  main.classList.remove("bleed");
  if (!path.startsWith("/e/")) { state.current = null; updateComposers(); }
  const wasReading = reading();
  document.body.classList.toggle("reading", path.startsWith("/e/"));
  if (!path.startsWith("/chat")) {
    delete composers.page; state.wbEntity = null;
    if (reading() && !wasReading && state.chatOpen) { document.body.classList.remove("chat-open"); state.chatOpen = false; }  // the column does not follow into the reader
    else if (!reading() && store.get("atlas.chatOpen", true) && !state.chatOpen && !matchMedia("(max-width: 1180px)").matches) openChat();
  }
  markNav();
  try {
    if (path === "/" || path === "") await viewHome();
    else if (path === "/chat") await viewChat();
    else if (path === "/projects") await viewProjects();
    else if (path === "/graph") {
      const token = state.routeToken;
      const mod = await import(`/static/graph.js?v=${window.ATLAS_V || ""}`);
      const destroy = await mod.viewGraph(main, { api, esc, enc, toast, agentSlot, agentName, svg });
      if (token === state.routeToken && (location.hash || "").startsWith("#/graph")) state.destroyView = destroy;
      else destroy();
    }
    else if (path === "/rediscover") await viewRediscover();
    else if (path.startsWith("/t/")) await viewList(decodeURIComponent(path.slice(3)), params);
    else if (path.startsWith("/e/")) await viewEntity(decodeURIComponent(path.slice(3)), params);
    else if (path === "/search") await viewSearch(params);
    else if (path.startsWith("/missing/")) viewMissing(decodeURIComponent(path.slice(9)));
    else main.innerHTML = `<div class="empty">Nothing here.</div>`;
  } catch (err) {
    main.innerHTML = `<div class="empty">Could not load this view (${esc(err.message)}). Is the Atlas server still running?</div>`;
  }
}

function connectStream() {
  const es = new EventSource("/api/stream");
  es.addEventListener("chat", async () => {  // also fired on (re)connect, so missed replies show up
    const fresh = await loadChat().catch(() => false);
    if (fresh && !chatVisible()) toast("New message from your agent");
  });
  es.addEventListener("operator", (ev) => {
    state.operator = JSON.parse(ev.data);
    renderPresence(); renderNav(); updateComposers(); refreshShift();
    if (state.chatOpen || onChatPage()) loadChat();
  });
  es.addEventListener("index", async () => {
    cardCache.clear();
    state.meta = await api("/api/meta");
    renderNav();
    if (onChatPage() && state.wbEntity) renderWorkbench();
    else refreshOpenView();
  });
}

async function boot() {
  state.meta = await api("/api/meta");
  state.operator = state.meta.operator;
  remember(state.meta.projects);
  $("#dock-composer").innerHTML = composer("dock", "Write to your agent…  type / for commands");
  wireComposer("dock", () => state.current ? { id: state.current.id, title: state.current.title } : null);
  renderPresence();
  renderNav();
  $("#search-form").onsubmit = (ev) => { ev.preventDefault(); const q = $("#search-input").value.trim(); if (q) location.hash = `#/search?q=${enc(q)}`; };
  const typing = (el) => el?.closest?.("input, textarea, select, [contenteditable]");
  document.addEventListener("keydown", (ev) => {
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "k") { ev.preventDefault(); if ($("#palette").hidden) openPalette(); else closePalette(); }
    if ((ev.metaKey || ev.ctrlKey) && !ev.shiftKey && ev.key.toLowerCase() === "z" && !typing(ev.target) && undoLast()) ev.preventDefault();
    if (ev.key === "Escape" && document.body.classList.contains("nav-open")) document.body.classList.remove("nav-open");
  });
  document.addEventListener("click", (ev) => {  // an open "later" menu closes when you click elsewhere
    for (const d of $$("details.later[open]")) if (!d.contains(ev.target)) d.open = false;
  });
  wirePalette();
  wireDrop();
  wireDockResize();
  $("#chat-toggle").onclick = () => { if (state.chatOpen) closeChat(); else openChat(); };
  $("#chat-close").onclick = closeChat;
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") loadChat().catch(() => {}); });
  $("#theme-toggle").onclick = () => {
    const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next; try { localStorage.setItem("atlas.theme", next); } catch {}
  };
  $("#nav-toggle").onclick = () => { const open = document.body.classList.toggle("nav-open"); $("#nav-toggle").setAttribute("aria-expanded", String(open)); };
  window.addEventListener("hashchange", route);
  await loadChat().catch(() => {});
  if (store.get("atlas.chatOpen", true) && !matchMedia("(max-width: 1180px)").matches && !(location.hash || "").startsWith("#/e/")) openChat();
  await route();
  connectStream();
}
boot();
