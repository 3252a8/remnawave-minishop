// Self-contained HTML gallery for a capture run. With a baseline run it also
// becomes a before/after viewer (toggle, swipe curtain, changed-only filter).

const escapeJson = (value) => JSON.stringify(value).replace(/</g, "\\u003c");

/**
 * @param {{ title: string, shots: object[], baseline?: { href: string, shots: object[] } | null }} data
 */
export function renderGallery(data) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${data.title.replace(/[<&]/g, "")}</title>
<style>
:root { color-scheme: dark; --bg:#0f1115; --panel:#171a21; --line:#2a2f3a; --text:#e7e9ee; --muted:#9aa3b2; --accent:#4fd1a5; --warn:#f2b84b; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 14px/1.4 system-ui, sans-serif; }
header { position: sticky; top: 0; z-index: 2; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 12px 16px; background: var(--panel); border-bottom: 1px solid var(--line); }
header h1 { font-size: 15px; margin: 0 12px 0 0; }
input, select, button { font: inherit; color: var(--text); background: var(--bg); border: 1px solid var(--line); border-radius: 8px; height: 32px; padding: 0 10px; }
button { cursor: pointer; }
button[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); }
.count { color: var(--muted); margin-left: auto; }
main { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; padding: 16px; }
.card { display: flex; flex-direction: column; gap: 6px; padding: 8px; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; cursor: pointer; text-align: left; height: auto; }
.card img { width: 100%; aspect-ratio: 4 / 3; object-fit: cover; object-position: top; border-radius: 6px; background: #000; }
.card .meta { display: flex; justify-content: space-between; gap: 6px; color: var(--muted); font-size: 12px; }
.card strong { font-size: 13px; word-break: break-all; }
.badge { padding: 1px 6px; border-radius: 999px; font-size: 11px; border: 1px solid var(--line); }
.badge.changed { color: var(--warn); border-color: var(--warn); }
.badge.error { color: #ff7a7a; border-color: #ff7a7a; }
dialog { width: 100vw; height: 100vh; max-width: none; max-height: none; margin: 0; padding: 0; border: 0; background: var(--bg); color: var(--text); }
.viewer-bar { position: sticky; top: 0; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 10px 16px; background: var(--panel); border-bottom: 1px solid var(--line); z-index: 1; }
.viewer-bar .title { font-weight: 600; margin-right: auto; word-break: break-all; }
.stage { padding: 16px; display: flex; justify-content: center; }
.stage > img, .side img { display: block; max-width: 100%; height: auto; min-width: 0; align-self: start; }
.frame { position: relative; display: inline-block; max-width: 100%; }
.frame img { display: block; max-width: 100%; height: auto; }
.frame .over { position: absolute; inset: 0; overflow: hidden; }
.frame .over img { width: 100%; }
.frame .handle { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--accent); pointer-events: none; }
.side { display: grid; width: 100%; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 16px; align-items: start; }
.side figure { margin: 0; }
.side figcaption { color: var(--muted); margin-bottom: 6px; }
.findings { margin: 0 16px 16px; color: var(--muted); font-size: 12px; white-space: pre-wrap; }
</style>
</head>
<body>
<header>
  <h1>${data.title.replace(/[<&]/g, "")}</h1>
  <input id="q" type="search" placeholder="Filter by id…" aria-label="Filter by id">
  <select id="viewport" aria-label="Viewport"><option value="">All viewports</option></select>
  <select id="theme" aria-label="Theme"><option value="">All themes</option></select>
  <button id="changed" type="button" aria-pressed="false" hidden>Changed only</button>
  <span class="count" id="count"></span>
</header>
<main id="grid"></main>
<dialog id="viewer">
  <div class="viewer-bar">
    <button type="button" id="prev" aria-label="Previous">←</button>
    <button type="button" id="next" aria-label="Next">→</button>
    <span class="title" id="vtitle"></span>
    <span id="modes"></span>
    <button type="button" id="close">Close (Esc)</button>
  </div>
  <div class="stage" id="stage"></div>
  <pre class="findings" id="findings"></pre>
</dialog>
<script>
const DATA = ${escapeJson(data)};
const key = (s) => s.viewport + "-" + s.theme + "/" + s.id;
const base = new Map((DATA.baseline?.shots || []).filter((s) => s.file).map((s) => [key(s), s]));
const shots = DATA.shots.filter((s) => s.file).map((s) => {
  const before = base.get(key(s));
  const reviewed = Boolean(before?.hash && s.hash && s.comparison?.afterHash === s.hash &&
    s.comparison.beforeHash === before.hash && typeof s.comparison.changed === "boolean");
  return { ...s, before, reviewed, changed: reviewed && s.comparison.changed,
    different: Boolean(before && before.hash !== s.hash) };
});
const hasReviewed = shots.some((shot) => shot.reviewed);
const $ = (id) => document.getElementById(id);
for (const [field, el] of [["viewport", $("viewport")], ["theme", $("theme")]]) {
  for (const value of [...new Set(shots.map((s) => s[field]))]) el.append(new Option(value, value));
}
if (base.size) {
  $("changed").hidden = false;
  $("changed").textContent = hasReviewed ? "Confirmed changes" : "Different captures";
  $("changed").setAttribute("aria-pressed", String(new URLSearchParams(location.search).get("changed") === "1"));
}
let visible = [];
let current = -1;
let mode = "after";
function render() {
  const q = $("q").value.trim().toLowerCase();
  const onlyChanged = $("changed").getAttribute("aria-pressed") === "true";
  visible = shots.filter((s) =>
    (!q || s.id.toLowerCase().includes(q)) &&
    (!$("viewport").value || s.viewport === $("viewport").value) &&
    (!$("theme").value || s.theme === $("theme").value) &&
    (!onlyChanged || (hasReviewed ? s.changed : s.different)));
  $("count").textContent = visible.length + " / " + shots.length + " shots";
  const grid = $("grid");
  grid.replaceChildren(...visible.map((s, index) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "card";
    const img = document.createElement("img");
    img.loading = "lazy";
    img.alt = "";
    img.src = s.file;
    const name = document.createElement("strong");
    name.textContent = s.id;
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = s.viewport + " · " + s.theme;
    const badges = document.createElement("span");
    if (s.changed) badges.innerHTML += '<span class="badge changed">changed</span> ';
    else if (!s.reviewed && s.different) badges.innerHTML += '<span class="badge">pixel difference</span> ';
    if (s.errors?.length) badges.innerHTML += '<span class="badge error">' + s.errors.length + " err</span>";
    meta.append(badges);
    card.append(img, name, meta);
    card.onclick = () => open(index);
    return card;
  }));
}
function picture(src) {
  const img = document.createElement("img");
  img.src = src;
  img.alt = "";
  return img;
}
function show() {
  const s = visible[current];
  if (!s) return;
  $("vtitle").textContent = s.id + " — " + s.viewport + " · " + s.theme + (s.changed ? " · changed" : "");
  const modes = s.before ? ["after", "before", "swipe", "side"] : ["after"];
  if (!modes.includes(mode)) mode = "after";
  $("modes").replaceChildren(...modes.map((m) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = m;
    b.setAttribute("aria-pressed", String(m === mode));
    b.onclick = () => { mode = m; show(); };
    return b;
  }));
  const stage = $("stage");
  const beforeSrc = s.before ? DATA.baseline.href + "/" + s.before.file : "";
  if (mode === "before") stage.replaceChildren(picture(beforeSrc));
  else if (mode === "side") {
    const wrap = document.createElement("div");
    wrap.className = "side";
    for (const [label, src] of [["before", beforeSrc], ["after", s.file]]) {
      const fig = document.createElement("figure");
      const cap = document.createElement("figcaption");
      cap.textContent = label;
      fig.append(cap, picture(src));
      wrap.append(fig);
    }
    stage.replaceChildren(wrap);
  } else if (mode === "swipe") {
    const frame = document.createElement("div");
    frame.className = "frame";
    const over = document.createElement("div");
    over.className = "over";
    const handle = document.createElement("div");
    handle.className = "handle";
    over.append(picture(beforeSrc));
    frame.append(picture(s.file), over, handle);
    const set = (x) => {
      const box = frame.getBoundingClientRect();
      const p = Math.min(1, Math.max(0, (x - box.left) / box.width));
      over.style.clipPath = "inset(0 " + (100 - p * 100) + "% 0 0)";
      handle.style.left = p * 100 + "%";
    };
    frame.onpointermove = (event) => set(event.clientX);
    requestAnimationFrame(() => { const box = frame.getBoundingClientRect(); set(box.left + box.width / 2); });
    stage.replaceChildren(frame);
  } else stage.replaceChildren(picture(s.file));
  const lines = [...(s.errors || []).map((e) => "error: " + e), ...(s.findings || []).map((f) => f.kind + ": " + f.target + " " + f.detail + (f.text ? " — " + f.text : ""))];
  $("findings").textContent = lines.join("\\n");
}
function open(index) { current = index; show(); if (!$("viewer").open) $("viewer").showModal(); }
$("prev").onclick = () => open((current - 1 + visible.length) % visible.length);
$("next").onclick = () => open((current + 1) % visible.length);
$("close").onclick = () => $("viewer").close();
document.addEventListener("keydown", (event) => {
  if (!$("viewer").open) return;
  if (event.key === "ArrowLeft") $("prev").click();
  if (event.key === "ArrowRight") $("next").click();
  if (event.key === " " && visible[current]?.before) { event.preventDefault(); mode = mode === "before" ? "after" : "before"; show(); }
});
for (const id of ["q", "viewport", "theme"]) $(id).addEventListener("input", render);
$("changed").onclick = () => { const b = $("changed"); b.setAttribute("aria-pressed", String(b.getAttribute("aria-pressed") !== "true")); render(); };
render();
</script>
</body>
</html>
`;
}
