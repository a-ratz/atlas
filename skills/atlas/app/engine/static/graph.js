// Atlas constellation: every insight and map (optionally sketches, specs, captures, projects,
// questions) on one force-directed canvas. Maps glow as hubs, shapes tell the kinds apart,
// colour says map, author or category. Replay walks the vault's history: pick a day or press
// play, and the notes appear in the order they arrived (git add date, else the content date).
// Engine: vendor/force-graph-1.43.5.min.js (MIT), loaded on first use.

const EXTRA = [["sketch", "Sketches"], ["spec", "Specs"], ["capture", "Captures"], ["project", "Projects"], ["question", "Questions"]];
const SHAPES = [["insight", "insight"], ["map", "map"], ["capture", "capture"], ["sketch", "sketch"], ["project", "project"], ["question", "question"]];

let engine = null;
function loadEngine() {
  if (window.ForceGraph) return Promise.resolve();
  engine ??= new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = "/static/vendor/force-graph-1.43.5.min.js";
    s.onload = ok; s.onerror = () => { engine = null; s.remove(); fail(new Error("graph engine failed to load")); };
    document.head.appendChild(s);
  });
  return engine;
}

const label = (n) => n.t || n.id.split("/").pop().replace(/\.md$/, "");
const mapName = (id) => (id || "").split("/").pop().replace(/\.md$/, "").replace(/-map$/, "").replace(/-/g, " ");
const short = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
function withAlpha(color, a) {
  color = color.trim();
  if (color.startsWith("#")) {
    const v = parseInt(color.slice(1, 7), 16);
    return `rgba(${(v >> 16) & 255},${(v >> 8) & 255},${v & 255},${a})`;
  }
  return color.startsWith("hsl(") ? color.replace("hsl(", "hsla(").replace(")", `, ${a})`) : color;
}
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

// time buckets for the replay: days, weeks or months, whatever keeps the bars readable
const DAY = 864e5;
const dayNum = (s) => Math.floor(Date.parse(s + "T12:00:00Z") / DAY);
function buckets(nodes) {
  const days = nodes.map((n) => n.a).filter(Boolean).map(dayNum);
  if (!days.length) return null;
  const lo = Math.min(...days), hi = Math.max(...days, Math.floor(Date.now() / DAY));
  const span = hi - lo + 1;
  const unit = span <= 60 ? 1 : span <= 420 ? 7 : 30;
  const count = Math.ceil(span / unit);
  const fmt = (d) => new Date(d * DAY).toLocaleDateString(undefined, unit === 30 ? { month: "short", year: "2-digit" } : { day: "numeric", month: "short" });
  return { lo, unit, count, of: (n) => (n.a ? Math.floor((dayNum(n.a) - lo) / unit) : 0), label: (i) => fmt(lo + i * unit),
    name: (i) => unit === 1 ? fmt(lo + i) : unit === 7 ? `week of ${fmt(lo + i * 7)}` : fmt(lo + i * 30) };
}

export async function viewGraph(main, ctx) {
  const { api, esc, enc, toast, agentSlot, agentName, svg } = ctx;
  // A highlight the agent made with `atlas.py light`: its notes stay lit until the user clears it. Hidden kinds
  // it needs are shown for this view only; the saved "Also show" choice stays as it was.
  let light = ctx.light && !ctx.light.gone ? ctx.light : null;
  const forced = new Set((light?.kinds || []).filter((k) => EXTRA.some(([x]) => x === k)));
  const saved = (() => { try { return JSON.parse(localStorage.getItem("atlas.graph")) || {}; } catch { return {}; } })();
  const opts = { color: ["map", "agent", "category"].includes(saved.color) ? saved.color : "map", extra: new Set(saved.extra || []) };
  const persist = () => { try { localStorage.setItem("atlas.graph", JSON.stringify({ color: opts.color, extra: [...opts.extra] })); } catch {} };

  main.classList.add("bleed");
  main.innerHTML = `
    <div class="gx">
      <aside class="gx-side" aria-label="Constellation controls">
        <div class="gx-stat"><div class="kicker" id="gx-asof">loading…</div><div class="n" id="gx-n">…</div><div class="s" id="gx-s"></div></div>
        <div class="gx-search"><label class="sr" for="gx-q">Fly to a note</label><input id="gx-q" placeholder="Fly to a note…" autocomplete="off"><div class="gx-sugg" id="gx-sugg" hidden></div></div>
        <section><h3 id="gx-color-h">Colour by</h3><div class="seg" role="group" aria-labelledby="gx-color-h">
          <button type="button" data-color="map">Map</button><button type="button" data-color="agent">Author</button><button type="button" data-color="category">Category</button></div></section>
        <section><div class="gx-legend" id="gx-legend"></div></section>
        <section><h3>Also show</h3><div class="gx-extra">${EXTRA.map(([k, l]) => `<label><input type="checkbox" value="${k}"> ${l}</label>`).join("")}</div></section>
        <section><h3>Shapes</h3><ul class="gx-shapes">${SHAPES.map(([t, l]) => `<li><span class="g" data-t="${t}" aria-hidden="true"></span>${l}</li>`).join("")}</ul></section>
        <div class="gx-glow"><span aria-hidden="true"></span>in the replay, glow = arrived in the period you are looking at</div>
      </aside>
      <div class="gx-main">
        <div class="gx-stage" id="gx-stage">
          <div class="gx-canvas" id="gx-canvas" role="img" aria-label="Graph of the vault's notes and their links"></div>
          <div class="gx-title"><span class="serif">Constellation</span><span class="kicker" id="gx-day">your vault</span><div class="gx-lit" id="gx-lit" hidden></div></div>
          <div class="gx-zoom">
            <button class="icon-btn" id="gx-in" aria-label="Zoom in">${svg("plus")}</button>
            <button class="icon-btn" id="gx-out" aria-label="Zoom out"><svg class="i" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10"/></svg></button>
            <button class="icon-btn" id="gx-fit" aria-label="Fit everything"><svg class="i" viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10"/></svg></button>
          </div>
          <div class="gx-card" id="gx-card" hidden></div>
        </div>
        <section class="replay panel" aria-labelledby="gx-replay-h">
          <div class="sec-h" style="margin:0"><h2 id="gx-replay-h">Replay</h2><span class="sub">pick a day, or press play and watch the vault grow out of your conversations</span></div>
          <div style="display:flex;align-items:flex-end;gap:14px"><button class="play" id="gx-play" type="button" aria-label="Replay the vault growing"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3.2v9.6a.6.6 0 0 0 .9.5l7.4-4.8a.6.6 0 0 0 0-1L5.9 2.7a.6.6 0 0 0-.9.5Z"/></svg></button>
            <div class="bars" id="gx-bars"></div></div>
        </section>
      </div>
    </div>`;
  const $ = (s) => main.querySelector(s);
  const el = $("#gx-canvas");
  let alive = true;
  let theme = {};
  let G = null;  // the force-graph instance, created once the engine has loaded
  const readTheme = () => {
    theme = { stage: css("--stage"), text: css("--text"), soft: css("--soft"), faint: css("--faint"), acc: css("--acc"), edge: css("--edge"), bg: css("--bg"),
      dark: getComputedStyle(document.documentElement).colorScheme.includes("dark"),
      pal: ["--map", "--insight", "--sketch", "--capture", "--ok", "--agent-1", "--warn-fg", "--agent-2"].map(css),
      kind: { sketch: css("--sketch"), spec: css("--sketch"), capture: css("--capture"), project: css("--project"), question: css("--question"), insight: css("--insight"), map: css("--map") } };
  };
  readTheme();
  const repaint = () => { readTheme(); recolor(); G && G.nodeCanvasObject(drawNode); drawLegend(); };
  const themeObs = new MutationObserver(repaint);
  themeObs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  const mq = matchMedia("(prefers-color-scheme: light)");
  mq.addEventListener("change", repaint);
  const cleanupBase = () => { alive = false; themeObs.disconnect(); mq.removeEventListener("change", repaint); window.removeEventListener("atlas:index", onIndex); main.classList.remove("bleed"); stopPlay(); };

  try { await loadEngine(); }
  catch (err) {
    cleanupBase();
    main.innerHTML = `<div class="empty" style="padding:40px">The graph engine could not load (${esc(err.message)}). Reload the page to try again.</div>`;
    return () => {};
  }
  if (!alive) return () => {};

  let data = null, adj = new Map(), byId = new Map(), hover = null, selected = null, focus = null, legendPick = null, legendKey = null, lit = null;
  let mapColor = new Map(), catColor = {}, T = null, sel = 0, timer = null;
  // `light` resolves its notes on a fresh index; the server's may be up to 10 s older. A note it does not have
  // yet joins the highlight when the index catches up (a few tries: a note deleted since stays missing). An index
  // change during a load counts too: that answer may predate it (round 3 on #64).
  let catchUps = 3, indexGen = 0, settled = 0;  // settled: the latest load whose answer is in (or failed)
  // A newer view replaced this one's page before route() could dispose it (it gets the cleanup only after the
  // first load): such a view must neither catch up nor render (round 5 on #64).
  const live = () => alive && el.isConnected;
  function onIndex() { if (!live()) return; indexGen++; if (settled === loadSeq) catchUp(); }  // else that load catches up when it lands
  function catchUp() {
    if (light && data && catchUps > 0 && light.ids.some((id) => !byId.has(id))) { catchUps--; load().catch((err) => toast(`Graph failed: ${err.message}`)); }
  }
  window.addEventListener("atlas:index", onIndex);
  const node = (x) => (typeof x === "object" ? x : byId.get(x));
  const bucketOf = (n) => (T ? T.of(n) : 0);
  const visible = (n) => !T || bucketOf(n) <= sel;
  const replaying = () => T && (timer || sel < T.count - 1);
  const isNew = (n) => replaying() && bucketOf(n) === sel && n.a;  // at "today" a busy week drowned the hubs

  const pick = (i) => (i < theme.pal.length ? theme.pal[i] : `hsl(${(i * 137.508) % 360}, 62%, ${theme.dark ? 66 : 42}%)`);
  function recolor() {
    if (!data) return;
    const maps = [...byId.values()].filter((n) => n.k === "map").sort((a, b) => b.d - a.d);
    mapColor = new Map(maps.map((m, i) => [m.id, pick(i)]));
    const cats = {};
    for (const n of byId.values()) if (n.c) cats[n.c] = (cats[n.c] || 0) + 1;
    catColor = Object.fromEntries(Object.entries(cats).sort((a, b) => b[1] - a[1]).map(([c], i) => [c, pick(i)]));
  }
  const agentColor = (w) => (!w ? theme.faint : w === "user" ? theme.text : css(`--agent-${agentSlot(w)}`));
  const colorOf = (n) => {
    if (opts.color === "agent") return agentColor(n.w);
    if (opts.color === "category") return n.k === "insight" || n.k === "map" ? catColor[n.c] || theme.kind[n.k] : theme.kind[n.k] || theme.faint;
    if (n.k === "map") return mapColor.get(n.id) || theme.kind.map;
    return mapColor.get(n.m) || theme.faint;
  };
  // Importance: in a big graph, size and opacity follow the degree, so hubs read first and the long tail
  // recedes. A young vault keeps every note at full strength: dimming half of ten notes only looks empty.
  let cut = { p75: 12, p90: 18, p99: 34 };  // degree percentiles of the shown insights, set on load
  let big = false;  // more than BIG insights shown
  let mesh = 0.2;  // edge opacity at rest: full for a small vault, a faint mesh once thousands of links pile up
  const BIG = 150;
  const radius = (n) => (n.k === "map" ? 7 + Math.min(10, Math.sqrt(n.d) * 0.5)
    : big ? 1.3 + Math.min(6.7, n.d * 0.17) : 2 + Math.min(5, Math.sqrt(n.d) * 0.55));
  const weight = (n) => (!big || n.k !== "insight" || n.d >= cut.p90 ? 1 : n.d >= cut.p75 ? 0.8 : 0.5);  // opacity at rest
  const neighborhood = (n) => new Set([n.id, ...(adj.get(n.id) || [])]);
  const bigHub = (n) => (adj.get(n.id)?.size || 0) > 60;
  const setFocus = () => { focus = hover ? neighborhood(hover) : selected ? neighborhood(selected) : legendPick || lit; };

  function shape(c, n, r, k) {
    c.beginPath();
    if (n.k === "map") { c.moveTo(n.x, n.y - r * 1.25); c.lineTo(n.x + r * 1.25, n.y); c.lineTo(n.x, n.y + r * 1.25); c.lineTo(n.x - r * 1.25, n.y); c.closePath(); }
    else if (n.k === "sketch" || n.k === "spec") { c.moveTo(n.x, n.y - r * 1.15); c.lineTo(n.x + r, n.y + r * .8); c.lineTo(n.x - r, n.y + r * .8); c.closePath(); }
    else if (n.k === "project") { const s = r * .9; c.rect(n.x - s, n.y - s, 2 * s, 2 * s); }
    else c.arc(n.x, n.y, r, 0, 2 * Math.PI);
  }
  function drawNode(n, c, k) {
    const active = !focus || focus.has(n.id), r = radius(n), col = colorOf(n), fresh = isNew(n), glow = focus && focus === lit;
    c.globalAlpha = !active ? 0.08 : focus ? 1 : weight(n);
    const top = big && n.k === "insight" && n.d >= cut.p99;
    if (active && (fresh || top || glow || n.k === "map" || n === hover || n === selected)) { c.shadowColor = fresh ? theme.acc : col; c.shadowBlur = fresh ? 14 : n.k === "map" ? 18 : glow ? 16 : 10; }
    shape(c, n, r, k);
    if (n.k === "map") {  // hubs: a solid diamond in the map's colour, ringed so it reads against its own spokes
      c.fillStyle = col; c.fill();
      c.lineWidth = 2.5 / Math.max(k, .6); c.strokeStyle = withAlpha(theme.stage, 0.9); c.stroke();
    } else if (n.k === "capture" || n.k === "question") {
      c.fillStyle = theme.stage; c.fill();
      c.lineWidth = 1.4 / Math.max(k, .6);
      c.setLineDash(n.k === "capture" ? [2 / k, 1.6 / k] : []);
      c.strokeStyle = col; c.stroke(); c.setLineDash([]);
    } else { c.fillStyle = col; c.fill(); }
    c.shadowBlur = 0;
    if (fresh && active) { c.beginPath(); c.arc(n.x, n.y, r + 3.5 / k, 0, 2 * Math.PI); c.lineWidth = 1.2 / k; c.strokeStyle = withAlpha(theme.acc, 0.8); c.stroke(); }
    if (glow && active && n.k !== "map") { c.beginPath(); c.arc(n.x, n.y, r + 4 / k, 0, 2 * Math.PI); c.lineWidth = 1.5 / k; c.strokeStyle = withAlpha(col, 0.75); c.stroke(); }  // lit: findable at any zoom
    if (n === selected) { c.beginPath(); c.arc(n.x, n.y, r + 3 / k, 0, 2 * Math.PI); c.lineWidth = 2 / k; c.strokeStyle = col; c.stroke(); }
    const show = active && (n.k === "map" ? (k > 0.7 || (k > 0.25 && n.d >= 120) || focus)
      : n === hover || n === selected || (glow ? lit.size <= 40 || k > 1.2 : focus ? k > (focus.size < 40 ? 1.2 : 2.6) : top ? k > 1.3 : weight(n) >= 0.8 ? k > 2.6 : k > 6));
    if (show) {
      const fs = (n.k === "map" ? 13.5 : 10.5) / k;  // Geist with a firm halo: the italic serif blurred at a distance
      c.font = `${n.k === "map" ? 600 : 500} ${fs}px Geist, ui-sans-serif, system-ui, sans-serif`;
      c.textAlign = "center"; c.textBaseline = "top";
      const text = n.k === "map" ? mapName(n.id) : short(label(n), n === hover || n === selected ? 120 : 48);
      const y = n.y + r * 1.3 + 3 / k, half = c.measureText(text).width / 2;
      const box = [n.x - half, y, n.x + half, y + fs * 1.2];
      // a lit set labels every note at any zoom: draw the ones that fit, zooming in or hovering shows the rest
      const crowded = glow && n !== hover && n !== selected && placed.some((b) => box[0] < b[2] && b[0] < box[2] && box[1] < b[3] && b[1] < box[3]);
      if (!crowded) {
        if (glow) placed.push(box);
        c.lineJoin = "round"; c.lineWidth = (n.k === "map" ? 4.5 : 3.5) / k; c.strokeStyle = withAlpha(theme.stage, 0.95);
        c.strokeText(text, n.x, y);
        c.fillStyle = n.k === "map" ? col : withAlpha(theme.text, 0.92);
        c.fillText(text, n.x, y);
      }
    }
    c.globalAlpha = 1;
  }

  // Hover follows the hand, not the canvas: force-graph re-checks what lies under a resting pointer every
  // frame, so a wheel zoom slid random notes under it and lit up their neighbourhoods. Such a note waits
  // in `slid` and becomes the hover at the next real pointer move (force-graph will not report it again).
  let movedAt = 0, slid, placed = [];  // placed: label boxes of lit notes drawn in this frame
  const applyHover = (n) => { hover = n || null; setFocus(); el.style.cursor = n ? "pointer" : "grab"; };
  el.addEventListener("pointermove", () => {
    movedAt = Date.now();
    if (slid !== undefined) {  // force-graph pauses drawing at rest and does not know about this change
      const n = slid; slid = undefined; applyHover(n); G?.nodeVisibility((x) => visible(x));
    }
  }, { passive: true });
  G = window.ForceGraph()(el)
    .backgroundColor("rgba(0,0,0,0)")
    .nodeId("id").nodeRelSize(1).nodeVal((n) => radius(n) ** 2).nodeLabel(() => "")
    .nodeCanvasObject(drawNode)
    .onRenderFramePre(() => { placed = []; })
    .nodePointerAreaPaint((n, color, c) => { c.fillStyle = color; c.beginPath(); c.arc(n.x, n.y, radius(n) + 2, 0, 2 * Math.PI); c.fill(); })
    .nodeVisibility((n) => visible(n))
    .linkVisibility((l) => visible(node(l.source)) && visible(node(l.target)))
    .linkColor((l) => {
      const center = hover || selected;
      if (center && (l.source.id === center.id || l.target.id === center.id)) {
        const other = l.source.id === center.id ? l.target : l.source;
        return withAlpha(colorOf(other), bigHub(center) ? 0.35 : 0.8);
      }
      if (T && (isNew(l.source) || isNew(l.target)) && !focus) return withAlpha(theme.acc, 0.55);
      if (focus && !center && focus.has(l.source.id) && focus.has(l.target.id)) return withAlpha(colorOf(l.source), 0.3);
      if (focus) return withAlpha(theme.edge, 0.1);
      return withAlpha(theme.edge, l.source.k === "map" || l.target.k === "map" ? Math.min(1, mesh * 1.5) : mesh);
    })
    .linkWidth((l) => { const center = hover || selected; return center && (l.source.id === center.id || l.target.id === center.id) ? (bigHub(center) ? 0.5 : 1.1) : 0.45; })
    .linkDirectionalParticles((l) => { const center = hover || selected; return center && !bigHub(center) && (l.source.id === center.id || l.target.id === center.id) ? 2 : 0; })
    .linkDirectionalParticleWidth(2.2).linkDirectionalParticleSpeed(0.005)
    .onNodeHover((n) => {
      if (n && Date.now() - movedAt > 150) { slid = n; return; }  // slid under a resting pointer (zoom, pan, layout)
      slid = undefined; applyHover(n);
    })
    .onNodeClick((n) => select(n, true))
    .onZoom(() => { if (hover && Date.now() - movedAt > 150) { slid = hover; applyHover(null); } })
    .onBackgroundClick(() => { selected = null; legendPick = null; legendKey = null; setFocus(); $("#gx-card").hidden = true; drawLegend(); })
    .d3AlphaDecay(0.022).d3VelocityDecay(0.32).warmupTicks(60).cooldownTicks(500);
  G.d3Force("charge").strength((n) => (n.k === "map" ? -260 : -24)).distanceMax(520);
  G.d3Force("link").distance((l) => (l.source.k === "map" || l.target.k === "map" ? 80 : 24))
    .strength((l) => (l.source.k === "map" || l.target.k === "map" ? 0.04 : 0.22));
  let fitted = false;
  G.onEngineStop(() => { if (!fitted) { fitted = true; lit ? fitLit() : G.zoomToFit(700, 60); } });
  const ro = new ResizeObserver(() => G.width(el.clientWidth).height(el.clientHeight));
  ro.observe(el);

  // replay
  function drawBars() {
    const box = $("#gx-bars");
    if (!T) { box.innerHTML = `<span class="sub" style="font-size:13px;color:var(--faint)">No dates yet: with git (or dated notes) the replay shows how the vault grew.</span>`; $("#gx-play").hidden = true; return; }
    const per = new Array(T.count).fill(0);
    for (const n of byId.values()) per[bucketOf(n)]++;
    const max = Math.max(1, ...per), every = Math.ceil(T.count / 12);
    box.innerHTML = per.map((v, i) => `<button type="button" class="${i === sel ? "on" : i < sel ? "past" : ""}" data-i="${i}" aria-pressed="${i === sel}" aria-label="Show the vault up to ${esc(T.name(i))}: ${v} arrived">
      <span class="b" style="height:${Math.max(4, Math.round((v / max) * 52))}px"></span><span class="l">${i % every === 0 || i === T.count - 1 ? esc(T.label(i)) : ""}</span></button>`).join("");
    box.querySelectorAll("button").forEach((b) => b.onclick = () => { stopPlay(); setDay(+b.dataset.i); });
    $("#gx-play").hidden = false;
  }
  function stats() {
    const nodes = [...byId.values()];
    const shown = nodes.filter(visible);
    const links = G.graphData().links.filter((l) => visible(node(l.source)) && visible(node(l.target))).length;
    const added = T ? nodes.filter((n) => bucketOf(n) === sel && n.a).length : 0;
    const last = !T || sel === T.count - 1;
    $("#gx-asof").textContent = T ? `as of ${T.name(sel)}` : "all notes";
    $("#gx-n").innerHTML = `${shown.length.toLocaleString()} <small>notes</small>`;
    $("#gx-s").innerHTML = `${links.toLocaleString()} links${T ? ` · <span class="acc-text">+${added} ${T.unit === 1 ? "that day" : "in that period"}</span>` : ""}`;
    $("#gx-day").textContent = T ? (last ? `your vault · today` : `your vault · ${T.name(sel)}`) : "your vault";
  }
  function setDay(i) {
    sel = Math.max(0, Math.min(T ? T.count - 1 : 0, i));
    drawBars(); stats();
    G.nodeVisibility((n) => visible(n));  // a new accessor makes the engine re-evaluate
    G.linkVisibility((l) => visible(node(l.source)) && visible(node(l.target)));
    drawLegend();
  }
  function stopPlay() {
    if (timer) { clearInterval(timer); timer = null; if (G) G.nodeVisibility((n) => visible(n)); }  // redraw: the glow ends with the replay
    const b = main.querySelector("#gx-play");
    if (b) { b.setAttribute("aria-label", "Replay the vault growing"); b.innerHTML = `<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3.2v9.6a.6.6 0 0 0 .9.5l7.4-4.8a.6.6 0 0 0 0-1L5.9 2.7a.6.6 0 0 0-.9.5Z"/></svg>`; }
  }
  $("#gx-play").onclick = () => {
    if (timer) return stopPlay();
    if (!T) return;
    setDay(0);
    const b = $("#gx-play");
    b.setAttribute("aria-label", "Pause the replay");
    b.innerHTML = `<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="3" width="3" height="10" rx=".6"/><rect x="9.5" y="3" width="3" height="10" rx=".6"/></svg>`;
    timer = setInterval(() => { if (!alive || sel >= T.count - 1) return stopPlay(); setDay(sel + 1); }, Math.max(140, Math.min(700, 9000 / T.count)));
  };

  let loadSeq = 0;
  async function load() {
    const seq = ++loadSeq, gen = indexGen;
    let fresh;
    try { fresh = await api(`/api/graph?types=${enc(["insight", "map", ...new Set([...opts.extra, ...forced])].join(","))}`); }
    finally { if (seq === loadSeq) settled = seq; }  // a superseded answer neither holds nor releases events
    if (!live() || seq !== loadSeq) return;
    data = fresh;
    const nodes = data.nodes.map((n) => ({ ...n }));
    const links = data.links.map(([a, b]) => ({ source: nodes[a].id, target: nodes[b].id }));
    byId = new Map(nodes.map((n) => [n.id, n]));
    adj = new Map(nodes.map((n) => [n.id, new Set()]));
    for (const l of links) { adj.get(l.source).add(l.target); adj.get(l.target).add(l.source); }
    const degrees = nodes.filter((n) => n.k === "insight").map((n) => n.d).sort((a, b) => a - b);
    const at = (q) => degrees.length ? degrees[Math.floor(q * (degrees.length - 1))] : 0;
    cut = { p75: at(0.75), p90: at(0.9), p99: Math.max(at(0.99), 1) };
    big = degrees.length > BIG;
    mesh = Math.min(1, Math.max(0.2, 800 / Math.max(1, links.length)));
    T = buckets(nodes);
    sel = T ? T.count - 1 : 0;
    recolor();
    hover = selected = focus = legendPick = legendKey = null; fitted = false;
    lit = light ? new Set(light.ids.filter((id) => byId.has(id))) : null;
    if (lit && !lit.size) lit = null;
    setFocus();
    G.graphData({ nodes, links });
    drawBars(); stats(); drawLegend(); drawLit();
    if (indexGen !== gen) catchUp();  // the index moved while this request ran
    // the user asked to see these: follow the settling layout instead of waiting ~8 s for it to stop
    if (lit) { const iv = setInterval(() => (alive && seq === loadSeq && lit && !fitted ? fitLit() : clearInterval(iv)), 700); }
  }

  const fitLit = () => G.zoomToFit(600, 100, (x) => lit.has(x.id));  // labels hang below and beside their node
  function drawLit() {
    const box = $("#gx-lit");
    box.hidden = !lit;
    if (!lit) return;
    box.innerHTML = `<button type="button" class="gx-lit-t" title="Fit the view to the lit notes">✨ ${esc(light.title)}<span class="n">${lit.size}</span></button>
      <button type="button" class="x" aria-label="Clear the highlight">${svg("x")}</button>`;
    box.querySelector(".gx-lit-t").onclick = fitLit;
    box.querySelector(".x").onclick = () => {
      const reload = forced.size > 0;
      light = lit = null; forced.clear(); syncExtra();
      history.replaceState(null, "", "#/graph");  // no hashchange: the view stays and keeps its layout
      if (reload) load().catch((err) => toast(`Graph failed: ${err.message}`));
      else { setFocus(); drawLit(); G.nodeVisibility((n) => visible(n)); }  // a settled graph draws only when told
    };
  }

  function drawLegend() {
    const box = main.querySelector("#gx-legend");
    if (!box || !data) return;
    const nodes = [...byId.values()].filter(visible);
    let items;
    if (opts.color === "agent") {
      const counts = {};
      for (const n of nodes) counts[n.w || ""] = (counts[n.w || ""] || 0) + 1;
      items = Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([w, c]) => [`agent:${w}`, agentColor(w), w ? (w === "user" ? "You" : agentName(w)) : "unknown", c]);
    } else if (opts.color === "category") {
      const counts = {};
      for (const n of nodes) if (n.c) counts[n.c] = (counts[n.c] || 0) + 1;
      items = Object.entries(catColor).map(([c, col]) => [`cat:${c}`, col, c.replace(/-/g, " "), counts[c] || 0]);
    } else {
      const counts = {};
      for (const n of nodes) { const m = n.k === "map" ? n.id : n.m; if (m) counts[m] = (counts[m] || 0) + 1; }
      items = [...mapColor.entries()].slice(0, 24).map(([id, col]) => [`map:${id}`, col, mapName(id), counts[id] || 0]);
    }
    box.innerHTML = items.map(([key, col, name, n]) => `<button class="gx-leg${legendKey === key ? " on" : ""}" data-key="${esc(key)}"><span class="sw" style="background:${col}"></span>${esc(name)}<span class="n">${n}</span></button>`).join("")
      || `<span style="font-size:13px;color:var(--faint)">Nothing to colour by yet.</span>`;
    box.querySelectorAll(".gx-leg").forEach((b) => b.onclick = () => pickLegend(b.dataset.key));
  }
  function pickLegend(key) {
    if (legendKey === key) { legendKey = null; legendPick = null; }
    else {
      legendKey = key;
      const [kind, val] = [key.slice(0, key.indexOf(":")), key.slice(key.indexOf(":") + 1)];
      const match = kind === "map" ? (n) => n.m === val || n.id === val : kind === "agent" ? (n) => (n.w || "") === val : (n) => n.c === val;
      legendPick = new Set([...byId.values()].filter(match).map((n) => n.id));
    }
    selected = null; $("#gx-card").hidden = true;
    setFocus(); drawLegend();
  }

  async function select(n, fly) {
    selected = n; setFocus();
    if (fly) {
      if (bigHub(n)) { const nb = neighborhood(n); G.zoomToFit(700, 70, (x) => nb.has(x.id)); }
      else { G.centerAt(n.x, n.y, 650); if (G.zoom() < 2.2) G.zoom(2.6, 650); }
    }
    const card = $("#gx-card");
    const nb = [...(adj.get(n.id) || [])].map((id) => byId.get(id)).filter(Boolean).sort((a, b) => b.d - a.d);
    card.hidden = false;
    card.innerHTML = `
      <button class="icon-btn x" aria-label="Close">${svg("x")}</button>
      <div class="gx-kind"><span class="gx-dot" style="background:${colorOf(n)}"></span>${esc(n.k === "insight" ? n.c || "insight" : n.k)}${n.s ? ` · ${esc(n.s)}` : ""}${n.a ? ` · ${esc(n.a)}` : ""}</div>
      <div class="gx-ttl">${esc(n.k === "map" ? mapName(n.id) : label(n))}</div>
      <div class="gx-meta">${n.d} connection${n.d === 1 ? "" : "s"}${n.w ? ` · by ${esc(n.w === "user" ? "you" : agentName(n.w))}` : ""}${n.m && n.k !== "map" ? ` · in <a href="#" data-fly="${esc(n.m)}">${esc(mapName(n.m))}</a>` : ""}</div>
      <div class="gx-desc" id="gx-desc">…</div>
      <div class="gx-actions"><a class="btn primary" href="#/e/${enc(n.id)}">Open</a><button class="btn" id="gx-iso">Only this neighbourhood</button></div>
      ${nb.length ? `<div class="gx-nb-h">Most connected neighbours</div><div class="gx-nb">${nb.slice(0, 14).map((x) => `<a href="#" data-fly="${esc(x.id)}"><span class="gx-dot" style="background:${colorOf(x)}"></span>${esc(short(x.k === "map" ? mapName(x.id) : label(x), 70))}</a>`).join("")}</div>` : ""}`;
    card.querySelector(".x").onclick = () => { selected = null; setFocus(); card.hidden = true; };
    card.querySelectorAll("[data-fly]").forEach((a) => a.onclick = (ev) => { ev.preventDefault(); const t = byId.get(a.dataset.fly); if (t) select(t, true); });
    card.querySelector("#gx-iso").onclick = () => { legendKey = null; legendPick = neighborhood(n); selected = null; setFocus(); drawLegend(); G.zoomToFit(600, 80, (x) => legendPick.has(x.id)); };
    const e = await api(`/api/entity?id=${enc(n.id)}`).catch(() => null);
    if (selected === n && card.querySelector("#gx-desc")) card.querySelector("#gx-desc").textContent = e?.description || "";
  }

  // controls
  main.querySelectorAll("[data-color]").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.color === opts.color));
    b.onclick = () => {
      opts.color = b.dataset.color; persist(); legendKey = null; legendPick = null; setFocus();
      main.querySelectorAll("[data-color]").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); drawLegend();
    };
  });
  const syncExtra = () => main.querySelectorAll(".gx-extra input").forEach((i) => {
    i.checked = opts.extra.has(i.value) || forced.has(i.value);
    i.disabled = forced.has(i.value);
    i.parentElement.title = i.disabled ? "Shown while the highlight is on" : "";
  });
  syncExtra();
  main.querySelectorAll(".gx-extra input").forEach((i) => {
    i.onchange = () => { i.checked ? opts.extra.add(i.value) : opts.extra.delete(i.value); persist(); stopPlay(); load().catch((err) => toast(`Graph failed: ${err.message}`)); };
  });
  $("#gx-fit").onclick = () => G.zoomToFit(600, 60);
  $("#gx-in").onclick = () => G.zoom(G.zoom() * 1.4, 300);
  $("#gx-out").onclick = () => G.zoom(G.zoom() / 1.4, 300);
  const q = $("#gx-q"), sugg = $("#gx-sugg");
  q.oninput = () => {
    const term = q.value.trim().toLowerCase();
    if (term.length < 2) { sugg.hidden = true; return; }
    const hits = [...byId.values()].filter((n) => visible(n) && label(n).toLowerCase().includes(term)).sort((a, b) => b.d - a.d).slice(0, 8);
    sugg.hidden = !hits.length;
    sugg.innerHTML = hits.map((n) => `<button data-id="${esc(n.id)}"><span class="gx-dot" style="background:${colorOf(n)}"></span>${esc(short(label(n), 80))}</button>`).join("");
    sugg.querySelectorAll("button").forEach((b) => b.onclick = () => { const n = byId.get(b.dataset.id); sugg.hidden = true; q.value = ""; if (n) select(n, true); });
  };
  q.onkeydown = (ev) => { if (ev.key === "Enter") sugg.querySelector("button")?.click(); if (ev.key === "Escape") { sugg.hidden = true; q.blur(); } };

  if (ctx.light?.gone) toast("That highlight is no longer in the chat history.");
  try { await load(); } catch (err) { if (alive) toast(`Graph failed: ${err.message}`); }

  return () => { cleanupBase(); ro.disconnect(); G.pauseAnimation(); G._destructor?.(); };
}
