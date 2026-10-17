// Teams: chats and channels, read and written through the addon's routes (addon.py).
// Everything that comes from Teams is set as text, never as markup.

const OPEN_EVERY = 4000;   // the open conversation
const LISTS_EVERY = 30000; // the chat list and the teams

const SKELETON = `
<section class="tm">
  <header class="tm-head">
    <h1>Teams</h1>
    <div class="tm-tabs" role="tablist" hidden>
      <button type="button" role="tab" data-tab="chats">Chats</button>
      <button type="button" role="tab" data-tab="channels">Channels</button>
    </div>
    <span class="tm-user"></span>
    <button type="button" class="btn tm-signout" hidden>Sign out</button>
  </header>
  <div class="tm-body">
    <nav class="tm-list" aria-label="Conversations"></nav>
    <div class="tm-conv">
      <div class="tm-conv-head"><h2></h2><span class="tm-sub"></span></div>
      <ol class="tm-msgs" aria-live="polite"></ol>
      <div class="tm-note" hidden></div>
      <form class="tm-compose" hidden>
        <label class="tm-sr" for="tm-text">Message</label>
        <textarea id="tm-text" rows="2" placeholder="Write a message. Enter sends, Shift+Enter starts a new line."></textarea>
        <button type="submit" class="btn primary">Send</button>
      </form>
    </div>
  </div>
</section>`;

export async function view(main, ctx) {
  const css = document.createElement("link");
  css.rel = "stylesheet";
  css.href = new URL("./view.css", import.meta.url).href;
  document.head.append(css);
  main.innerHTML = SKELETON;
  const $ = (sel) => main.querySelector(sel);
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  let alive = true, tab = "chats", open = null, timers = [], backoff = 0, sending = false;
  // still on screen: not cleaned up, and the reader has not navigated away while this view was starting
  const live = () => alive && (!ctx.current || ctx.current());
  const call = async (path, opts = {}) => {
    const res = await fetch(ctx.base + path, { ...opts, headers: { ...(opts.headers || {}), "x-atlas": "1" } });
    let data = {};
    try { data = await res.json(); } catch {}
    if (res.status === 429) backoff = Math.max(backoff, (data.retry_after || 10) * 1000);
    return { status: res.status, data };
  };

  const when = (iso) => {
    if (!iso) return "";
    const d = new Date(iso);
    const today = new Date().toDateString() === d.toDateString();
    return today ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                 : d.toLocaleDateString([], { day: "numeric", month: "short" });
  };

  // ---------------------------------------------------------------- states before a conversation
  const state = (await call("/state")).data;
  if (!live()) { destroy(); return destroy; }
  if (!state.configured) {
    setup();
    return destroy;
  }
  if (!state.signed_in) {
    const box = el("div", "tm-empty");
    box.append(el("p", "", "Sign in with your Microsoft account to see your chats and channels here."));
    const go = el("a", "btn primary", "Sign in with Microsoft");
    go.href = ctx.base + "/login";
    box.append(go);
    if (ctx.params.get("error")) box.append(el("p", "tm-err", `Microsoft refused the sign-in: ${ctx.params.get("error")}`));
    $(".tm-body").replaceChildren(box);
    return destroy;
  }

  $(".tm-user").textContent = state.demo ? "Demo: made-up people" : state.user;
  $(".tm-tabs").hidden = false;
  if (!state.demo) $(".tm-signout").hidden = false;
  $(".tm-signout").onclick = async () => {
    await call("/logout", { method: "POST" });
    ctx.toast("Signed out of Microsoft");
    location.reload();
  };
  const openFor = {};  // each tab keeps the conversation it had open (smoke run on #60)
  const drafts = new Map();  // each conversation keeps its own draft: a draft never changes its destination
  const keyOf = (conv) => `${conv.kind}:${conv.team || ""}:${conv.id}`;
  const keepDraft = () => {
    if (!open) return;
    const text = $("#tm-text").value;
    if (text) drafts.set(keyOf(open), text); else drafts.delete(keyOf(open));
  };
  for (const b of main.querySelectorAll(".tm-tabs button")) b.onclick = () => {
    if (b.dataset.tab === tab) return;
    keepDraft();
    openFor[tab] = open;
    tab = b.dataset.tab;
    open = null;
    $("#tm-text").value = "";
    showTab();
    if (openFor[tab]) openConv(openFor[tab]);
  };
  $(".tm-compose").onsubmit = (e) => { e.preventDefault(); send(); };
  $("#tm-text").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } };

  // ---------------------------------------------------------------- lists
  async function showTab() {
    for (const b of main.querySelectorAll(".tm-tabs button")) b.setAttribute("aria-selected", String(b.dataset.tab === tab));
    if (!open) clearConv();
    await (tab === "chats" ? loadChats() : loadTeams());
  }

  async function loadChats() {
    const { status, data } = await call("/chats");
    if (!live() || tab !== "chats") return;
    if (status !== 200) return listError(status, data);
    const list = $(".tm-list");
    list.replaceChildren();
    for (const c of data.chats) {
      const row = el("button", "tm-row");
      row.type = "button";
      row.setAttribute("aria-current", String(open?.kind === "chat" && open.id === c.id));
      const top = el("span", "tm-row-top");
      top.append(el("span", "tm-row-title", c.title), el("span", "tm-time", when(c.at)));
      row.append(top, el("span", "tm-row-last", c.last_from && c.last ? `${c.last_from}: ${c.last}` : c.last));
      row.onclick = () => openConv({ kind: "chat", id: c.id, title: c.title, sub: c.members.join(", ") });
      list.append(row);
    }
    if (!data.chats.length) list.append(el("p", "tm-quiet", "No chats yet."));
  }

  async function loadTeams() {
    const { status, data } = await call("/teams");
    if (!live() || tab !== "channels") return;
    if (status !== 200) return listError(status, data);
    const list = $(".tm-list");
    list.replaceChildren();
    for (const t of data.teams) {
      list.append(el("div", "tm-team", t.name));
      for (const ch of t.channels) {
        const row = el("button", "tm-row tm-channel");
        row.type = "button";
        row.setAttribute("aria-current", String(open?.kind === "channel" && open.id === ch.id));
        row.append(el("span", "tm-hash", "#"), el("span", "tm-row-title", ch.name));
        row.onclick = () => openConv({ kind: "channel", id: ch.id, team: t.id, title: ch.name, sub: t.name });
        list.append(row);
      }
    }
    if (!data.teams.length) list.append(el("p", "tm-quiet", "You are in no teams."));
  }

  function listError(status, data) {
    const list = $(".tm-list");
    list.replaceChildren(el("p", "tm-err", status === 401 ? "Signed out: reload to sign in again."
      : status === 429 ? "Microsoft asks to slow down; trying again shortly."
      : `Teams answered ${status}${data.message ? `: ${data.message}` : ""}`));
  }

  // ---------------------------------------------------------------- a conversation
  const pathOf = (conv) => conv.kind === "chat" ? `/chats/${encodeURIComponent(conv.id)}/messages`
    : `/channels/${encodeURIComponent(conv.team)}/${encodeURIComponent(conv.id)}/messages`;

  function clearConv() {
    $(".tm-conv-head h2").textContent = tab === "chats" ? "Pick a chat" : "Pick a channel";
    $(".tm-sub").textContent = "";
    $(".tm-msgs").replaceChildren();
    $(".tm-compose").hidden = true;
    $(".tm-note").hidden = true;
  }

  async function openConv(conv) {
    keepDraft();
    open = conv;
    $("#tm-text").value = drafts.get(keyOf(conv)) || "";
    $(".tm-conv-head h2").textContent = conv.kind === "channel" ? `# ${conv.title}` : conv.title;
    $(".tm-sub").textContent = conv.sub || "";
    $(".tm-compose").hidden = false;
    $(".tm-msgs").replaceChildren();
    for (const row of main.querySelectorAll(".tm-row")) row.setAttribute("aria-current", "false");
    await loadMessages(true);
    (tab === "chats" ? loadChats : loadTeams)();
    $("#tm-text").focus();
  }

  async function loadMessages(scroll) {
    if (!open) return;
    const asked = open;
    const { status, data } = await call(pathOf(asked));
    if (!live() || asked !== open) return;
    const note = $(".tm-note");
    if (status === 403 && data.error === "consent") {
      note.hidden = false;
      note.textContent = "Reading channel posts needs an admin's consent to ChannelMessage.Read.All. "
        + "Once it is given, set channel_messages: true for the addon in atlas.yaml and sign in again. Posting works without it.";
      $(".tm-msgs").replaceChildren();
      return;
    }
    if (status !== 200) { note.hidden = false; note.textContent = status === 429 ? "Microsoft asks to slow down; trying again shortly." : `Teams answered ${status}.`; return; }
    note.hidden = true;
    renderMessages(data.messages, scroll);
  }

  function renderMessages(messages, scroll) {
    const box = $(".tm-msgs");
    const atEnd = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    box.replaceChildren();
    for (const m of messages) {
      const li = el("li", m.system ? "tm-msg system" : "tm-msg");
      const meta = el("div", "tm-meta");
      meta.append(el("span", "tm-from", m.from), el("span", "tm-time", when(m.at)));
      li.append(meta, el("p", "tm-text", m.text || (m.attachments ? "(an attachment)" : "")));
      const extras = el("div", "tm-extras");
      if (m.replies) extras.append(el("span", "tm-replies", m.replies === 1 ? "1 reply" : `${m.replies} replies`));
      if (m.attachments && /^https:\/\//.test(m.link)) {
        const a = el("a", "", m.attachments === 1 ? "Open the attachment in Teams" : `Open ${m.attachments} attachments in Teams`);
        a.href = m.link; a.target = "_blank"; a.rel = "noopener noreferrer";
        extras.append(a);
      }
      if (extras.childElementCount) li.append(extras);
      box.append(li);
    }
    if (scroll || atEnd) box.scrollTop = box.scrollHeight;
  }

  async function send() {
    const area = $("#tm-text"), button = $(".tm-compose button");
    const text = area.value.trim();
    if (sending || !text || !open) return;  // one message in flight at a time: a double click sends once
    const target = open;
    sending = true;
    area.disabled = button.disabled = true;
    let status = 0, data = {};
    try {
      ({ status, data } = await call(pathOf(target), { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text }) }));
    } catch {
      // no answer (Atlas restarting, the network gone): Teams may have taken the message all the same
    } finally {
      sending = false;
      area.disabled = button.disabled = false;
    }
    if (!live()) return;
    if (status === 200 && data.sent) {
      drafts.delete(keyOf(target));
      if (target === open && area.value.trim() === text) area.value = "";
      if (target !== open) ctx.toast(`Sent to ${target.title}.`);  // the reader moved on: the answer is not this conversation's
      else if (data.messages) renderMessages(data.messages, true);
      else loadMessages(true);
    } else if (!status) {
      // unconfirmed, not failed: show the conversation as it is, and keep the draft in case it did not arrive
      ctx.toast("No answer, so the message may have gone out. Check the conversation before sending it again.");
      if (target === open) loadMessages(true);
    } else if (status === 403 && data.error === "post_refused") ctx.toast("Not sent: this channel does not take your posts.");
    else ctx.toast(status === 429 ? "Microsoft asks to slow down; try again in a moment." : `Not sent: Teams answered ${status}.`);
    if (target === open) area.focus();
  }

  // ---------------------------------------------------------------- staying current
  function every(ms, fn) {
    const tick = async () => {
      if (!alive) return;
      const wait = backoff;
      backoff = 0;
      if (!wait && !document.hidden) { try { await fn(); } catch {} }
      if (alive) timers.push(setTimeout(tick, Math.max(ms, wait)));
    };
    timers.push(setTimeout(tick, ms));
  }
  every(OPEN_EVERY, () => loadMessages(false));
  every(LISTS_EVERY, () => (tab === "chats" ? loadChats() : loadTeams()));
  try {
    await showTab();
  } catch (err) {
    destroy();  // the router never gets the cleanup of a view that failed to start: stop the polling here
    throw err;
  }
  if (!live()) destroy();
  return destroy;

  // ---------------------------------------------------------------- setup, and leaving
  function setup() {
    const box = el("div", "tm-empty tm-setup");
    box.append(el("h2", "", "Connect Teams"),
      el("p", "", "Register an app in Microsoft Entra ID (your admin may have to): App registrations, New registration, "
        + "single tenant; platform “Mobile and desktop applications” with the redirect URI "
        + "http://localhost/api/addons/teams/callback; "
        + "delegated permissions as the addon's README lists them. Then put its IDs into the vault's atlas.yaml and restart Atlas:"),
      el("pre", "", "addons:\n  teams:\n    client_id: <Application (client) ID>\n    tenant: <Directory (tenant) ID>"),
      el("p", "tm-quiet", "Or try it with made-up people first: demo: true instead of the two IDs."));
    $(".tm-body").replaceChildren(box);
  }

  function destroy() {
    alive = false;
    for (const t of timers) clearTimeout(t);
    timers = [];
    css.remove();
  }
}
