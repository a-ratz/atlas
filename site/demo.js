// Atlas recorded demo (GitHub Pages). No server and no agent: this answers the front end's API calls
// from demo-data.json, which site/build.py recorded from the real engine on the demo vault, and replays
// the one recorded scene (a distill) when the visitor asks for it. Loaded before app.js.
(() => {
  const realFetch = window.fetch.bind(window);
  const DAY = 864e5;
  let D = null;
  let vault = "before";             // which recorded vault the answers come from
  let chatIdx = 0, operator = null;  // the recorded chat (and agent presence) now on screen
  let trigger = null, playing = false, played = false;
  const playAt = [];                // when each scene step played here, ms
  const extras = [];                // what the visitor typed, and the canned replies
  const snoozed = {};
  const sources = [];

  const ready = realFetch("demo-data.json").then((r) => r.json()).then((data) => {
    D = data;
    chatIdx = D.chat;
    operator = retime(D.bodies[D.chat].operator);
    try {  // "while you were away" needs a last visit: two days ago, the first time
      if (!localStorage.getItem("atlas.lastSeen")) localStorage.setItem("atlas.lastSeen", JSON.stringify(new Date(Date.now() - 2 * DAY).toISOString()));
    } catch {}
  });

  // ---------------------------------------------------------------- time: the recording happens now
  // Timestamps near the recording move by how long ago it was recorded; the scene's own move to when it
  // played here. Dates far from the recording (a source from 2010) stay as they are.
  const pad = (n) => String(n).padStart(2, "0");
  const localIso = (ms) => {
    const d = new Date(ms), off = -d.getTimezoneOffset();
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}` +
      `${off >= 0 ? "+" : "-"}${pad(Math.floor(Math.abs(off) / 60))}:${pad(Math.abs(off) % 60)}`;
  };
  const near = (ms) => ms > D.recorded_at - 120 * DAY && ms < D.recorded_at + 2 * DAY;
  const ISO_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/;
  const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
  function shiftTime(s) {
    const t = Date.parse(s);
    if (isNaN(t) || !near(t)) return s;
    const steps = D.scene.steps;
    if (t >= steps[0].at) {
      let i = 0;
      while (i + 1 < steps.length && steps[i + 1].at <= t) i++;
      if (playAt[i] != null) return localIso(playAt[i] + (t - steps[i].at));
    }
    return localIso(t + (loaded - D.recorded_at));
  }
  function shiftDay(s) {
    const t = Date.parse(`${s}T12:00:00Z`);
    if (isNaN(t) || !near(t)) return s;
    const today = new Date(), days = Math.round((Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()) - Date.parse(`${D.record_day}T00:00:00Z`)) / DAY);
    return new Date(t + days * DAY).toISOString().slice(0, 10);
  }
  const loaded = Date.now();
  function retime(v) {
    if (typeof v === "string") return ISO_TIME.test(v) ? shiftTime(v) : ISO_DAY.test(v) ? shiftDay(v) : v;
    if (Array.isArray(v)) return v.map(retime);
    if (v && typeof v === "object") { const o = {}; for (const k in v) o[k] = retime(v[k]); return o; }
    return v;
  }

  // ---------------------------------------------------------------- answers
  const reply = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  const recorded = (key) => { const i = D.states[vault][key]; return i == null ? null : retime(D.bodies[i]); };
  const orMissing = (body) => (body ? reply(body) : reply({ error: "not found" }, 404));

  function search(q) {
    const words = (q.get("q") || "").toLowerCase().split(/\s+/).filter(Boolean);
    const type = q.get("type"), limit = Math.max(1, Math.min(60, parseInt(q.get("n"), 10) || 60));
    const out = { mode: "fast", results: [] };
    if (q.get("mode") === "deep") out.note = "Deep search runs on your own Atlas with QMD; the demo shows instant results.";
    if (!words.length) return out;
    const has = (r, w) => r.t.includes(w) || r.d.includes(w) || r.b.includes(w);
    out.results = recorded("search")
      .filter((r) => (!type || r.type === type) && words.every((w) => has(r, w)))
      .map((r) => ({ r, score: words.reduce((s, w) => s + 5 * r.t.includes(w) + 3 * r.d.includes(w) + 1, 0) }))
      .sort((a, b) => b.score - a.score || (b.r.touched > a.r.touched ? 1 : b.r.touched < a.r.touched ? -1 : 0))
      .slice(0, limit).map((x) => x.r.card);
    return out;
  }

  function chatPayload() {
    const payload = retime(D.bodies[chatIdx]);
    for (const m of payload.messages) {  // the scene's first message is whatever the visitor sent
      if (trigger && m.role === "user" && m.text === D.scene.trigger) {
        m.text = trigger.text; m.via = trigger.via; m.context = trigger.context || null;
      }
    }
    payload.messages = payload.messages.concat(extras).sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts));
    payload.operator = operator;
    return payload;
  }

  function emit(type, data) { for (const s of sources) s.fire(type, data); }

  function play(body) {
    playing = true;
    trigger = { text: body.text, via: body.via, context: body.context };
    let delay = 0;
    D.scene.steps.forEach((step, i) => {
      delay += step.pause;
      setTimeout(() => {
        playAt[i] = Date.now();
        chatIdx = step.chat;
        if (step.vault) vault = step.vault;
        operator = retime(D.bodies[step.chat].operator);
        for (const a of operator.agents || []) if (a.task && a.task.text === D.scene.trigger) a.task.text = trigger.text;
        if (i === D.scene.steps.length - 1) {
          playing = false; played = true;
          if (/\ball\b/i.test(trigger.text)) setTimeout(() => { extras.push({ ...D.canned.all, ts: localIso(Date.now()) }); emit("chat"); }, 1500);
        }
        emit("operator", operator);
        emit("chat");
        if (step.vault) emit("index", { version: Date.now() });
      }, delay);
    });
  }

  function chatPost(body) {
    const text = String(body.text || "").trim();
    if (!text) return reply({ ok: false }, 400);
    if (!played && !playing && /\bdistill/i.test(text)) {
      play(body);
      return reply({ ok: true, delivered: "agent" });
    }
    extras.push({ ts: localIso(Date.now()), role: "user", kind: "message", text, context: body.context || null,
                  ...(body.via ? { via: body.via } : {}), ...(body.to ? { to: body.to } : {}) });
    setTimeout(() => emit("chat"), 0);
    if (!playing) setTimeout(() => { extras.push({ ...D.canned[played ? "after" : "before"], ts: localIso(Date.now()) }); emit("chat"); }, 900);
    return reply({ ok: true, delivered: "agent" });
  }

  async function answer(url, opts) {
    await ready;
    const path = url.pathname.slice(url.pathname.indexOf("/api/")), q = url.searchParams;
    if ((opts.method || "GET").toUpperCase() === "POST") {
      let body = {};
      try { body = JSON.parse(opts.body || "{}"); } catch {}
      if (path === "/api/chat") return chatPost(body);
      if (path === "/api/action") return reply({ ok: true, note: "you/notes/demo.md" });
      if (path === "/api/snooze") {
        if (body.wake) delete snoozed[body.key];
        else snoozed[body.key] = { until: body.until, sig: body.sig || "", label: body.label || "" };
        return reply({ ok: true, snoozed: { ...snoozed } });
      }
      if (path === "/api/drop") return reply({ error: "dropping files needs your own Atlas" }, 400);
      return reply({ error: "not found" }, 404);
    }
    switch (path) {
      case "/api/meta": return reply({ ...recorded("meta"), operator });
      case "/api/home": return reply({ ...recorded("home"), snoozed: { ...snoozed } });
      case "/api/projects": return reply(recorded("projects"));
      case "/api/list": return orMissing(recorded(`list:${q.get("type")}`));
      case "/api/entity": {  // a note that moved between two recorded states says where it went
        const e = recorded(`entity:${q.get("id")}`);
        return e ? reply(e) : reply(recorded(`moved:${q.get("id")}`) || { error: "not found" }, 404);
      }
      case "/api/card": return orMissing(recorded(`card:${q.get("id")}`));
      case "/api/graph": return orMissing(recorded(`graph:${(q.get("types") || "insight,map").split(",").filter(Boolean).sort().join(",")}`));
      case "/api/search": return reply(search(q));
      case "/api/chat": return reply(chatPayload());
    }
    return reply({ error: "not found" }, 404);
  }

  window.fetch = (input, opts = {}) => {
    const url = new URL(typeof input === "string" ? input : input.url, location.href);
    if (url.origin === location.origin && url.pathname.includes("/api/")) return answer(url, opts);
    return realFetch(input, opts);
  };

  // the live stream: the scene pushes the same events the engine would
  window.EventSource = class {
    constructor(url) {
      this.url = url; this.handlers = {};
      sources.push(this);
      ready.then(() => { this.fire("chat"); this.fire("operator", operator); });
    }
    addEventListener(type, fn) { (this.handlers[type] ||= []).push(fn); }
    removeEventListener(type, fn) { this.handlers[type] = (this.handlers[type] || []).filter((f) => f !== fn); }
    close() { const i = sources.indexOf(this); if (i >= 0) sources.splice(i, 1); }
    fire(type, data) { for (const fn of this.handlers[type] || []) fn({ type, data: JSON.stringify(data ?? {}) }); }
  };

  // ---------------------------------------------------------------- the notice: no agent here
  const css = document.createElement("style");
  css.textContent = `
    .demo-pill { display: inline-flex; align-items: center; gap: 7px; height: 30px; padding: 0 12px; border-radius: 99px;
      border: 1px solid color-mix(in srgb, var(--acc) 55%, transparent); background: color-mix(in srgb, var(--acc) 12%, transparent);
      color: var(--text-hi); font: 500 12px var(--sans); white-space: nowrap; text-decoration: none; flex-shrink: 0; }
    .demo-pill:hover { background: color-mix(in srgb, var(--acc) 20%, transparent); }
    .demo-pill .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--acc); }
    .demo-pill .long { color: var(--text-2); font-weight: 400; }
    @media (max-width: 1180px) { .demo-pill .long { display: none; } }`;
  document.head.appendChild(css);

  const PLACEHOLDER = "Demo: no AI agent is connected; replies are recorded";
  document.addEventListener("DOMContentLoaded", () => {
    const pill = document.createElement("a");
    pill.className = "demo-pill";
    pill.href = "https://github.com/a-ratz/atlas";
    pill.target = "_blank"; pill.rel = "noopener";
    pill.title = "A recording of a real Atlas session. No AI agent is connected: the chat plays back recorded answers. Click to install Atlas.";
    pill.innerHTML = '<span class="dot"></span>Recorded demo<span class="long"> · no AI agent connected</span>';
    const actions = document.querySelector(".top-actions");
    actions.parentNode.insertBefore(pill, actions);
    new MutationObserver(() => {
      for (const t of document.querySelectorAll("textarea[id$='-input']")) if (t.placeholder !== PLACEHOLDER) t.placeholder = PLACEHOLDER;
    }).observe(document.body, { childList: true, subtree: true });
    let first = true;
    try { first = !localStorage.getItem("atlas.demo.seen"); localStorage.setItem("atlas.demo.seen", "1"); } catch {}
    if (first && innerWidth >= 1100) ready.then(() => setTimeout(() => {  // the welcome and its button, right away
      if (!document.body.classList.contains("chat-open")) document.querySelector("#chat-toggle")?.click();
    }, 600));
  });
})();
