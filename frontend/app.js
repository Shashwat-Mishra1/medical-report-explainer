/* MedReport Explainer: front end.
   Talks to the FastAPI backend: /upload, /confirm/{id}, /chat, DELETE /report/{id}. */

let reportId = null, tests = [];
const $ = id => document.getElementById(id);
const JSON_HEADERS = {"Content-Type": "application/json"};
const LABELS = {normal: "Normal", low: "Low", high: "High", critical_low: "Very low", critical_high: "Very high"};

function el(tag, cls, text){
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function show(id, on = true){ $(id).classList.toggle("hidden", !on); }

/* ---------- progress, errors, loading ---------- */
function setStep(n){
  document.querySelectorAll(".step").forEach(s => {
    const i = Number(s.dataset.step);
    s.classList.toggle("done", i < n);
    if (i === n) s.setAttribute("aria-current", "step"); else s.removeAttribute("aria-current");
  });
  window.scrollTo({top: 0});
}
function showError(msg){ $("error").textContent = msg; show("error"); window.scrollTo({top: 0, behavior: "smooth"}); }
function hideError(){ show("error", false); }
function busy(msg){ if (msg) $("loadingText").textContent = msg; show("loading", !!msg); }

async function api(url, opts){
  const res = await fetch(url, opts);
  let data = null;
  try { data = await res.json(); } catch (e) {}
  if (!res.ok){
    if (res.status === 404) throw new Error("Your session expired. Please upload the report again.");
    let msg = data && data.detail;
    if (Array.isArray(msg)) msg = "Something was not filled in correctly.";
    throw new Error(msg || "Something went wrong (" + res.status + "). Please try again.");
  }
  return data;
}

/* ---------- numbers and ranges ---------- */
function fmtRange(t){
  if (t.ref_low != null && t.ref_high != null) return t.ref_low + " to " + t.ref_high;
  if (t.ref_high != null) return "below " + t.ref_high;
  if (t.ref_low != null) return "above " + t.ref_low;
  return "none given";
}
function liveStatus(v, t){
  if (t.ref_low != null && v < t.ref_low) return v < t.ref_low * 0.7 ? "critical_low" : "low";
  if (t.ref_high != null && v > t.ref_high) return v > t.ref_high * 1.5 ? "critical_high" : "high";
  return "normal";
}

/* The range bar: the green part is the normal range, the dot is the person's value.
   Values far outside the range are pinned to the edge of the bar. */
function rangeBar(t, animate){
  const lo = t.ref_low, hi = t.ref_high, v = Number(t.value);
  let dmin, dmax;
  if (lo != null && hi != null){
    const span = (hi - lo) || Math.abs(hi) || 1;
    dmin = lo - span * 0.6; dmax = hi + span * 0.6;
    if (lo >= 0) dmin = Math.max(dmin, 0);
  } else if (hi != null){ dmin = 0; dmax = hi * 1.6; }
  else if (lo != null){ dmin = 0; dmax = lo * 2; }
  else { return null; }
  const pct = x => Math.min(100, Math.max(0, (x - dmin) / (dmax - dmin) * 100));
  const pLo = lo != null ? pct(lo) : 0;
  const pHi = hi != null ? pct(hi) : 100;
  const target = Math.min(97, Math.max(3, pct(v)));

  const wrap = el("div", "rb");
  wrap.setAttribute("role", "img");
  wrap.setAttribute("aria-label", "Your value " + t.value + " " + (t.unit || "") + ". Normal range: " + fmtRange(t) + ". Status: " + LABELS[t.status] + ".");
  const track = el("div", "rb-track");
  if (lo != null){ const z = el("div", "rb-low"); z.style.cssText = "left:0;width:" + pLo + "%"; track.appendChild(z); }
  const ok = el("div", "rb-ok"); ok.style.cssText = "left:" + pLo + "%;width:" + (pHi - pLo) + "%"; track.appendChild(ok);
  if (hi != null){ const z = el("div", "rb-high"); z.style.cssText = "left:" + pHi + "%;width:" + (100 - pHi) + "%"; track.appendChild(z); }
  wrap.appendChild(track);
  const dot = el("div", "rb-dot s-" + t.status);
  dot.style.left = animate ? "3%" : target + "%";
  wrap.appendChild(dot);
  if (animate) requestAnimationFrame(() => requestAnimationFrame(() => { dot.style.left = target + "%"; }));
  if (lo != null){ const k = el("span", "rb-tick", String(lo)); k.style.left = pLo + "%"; wrap.appendChild(k); }
  if (hi != null){ const k = el("span", "rb-tick", String(hi)); k.style.left = pHi + "%"; wrap.appendChild(k); }
  return wrap;
}

/* ---------- step 1: upload ---------- */
function initSample(){
  const bar = rangeBar({value: 10.2, unit: "g/dL", ref_low: 12, ref_high: 16, status: "low"}, false);
  $("sampleBar").appendChild(bar);
}

async function handleFile(file){
  if (!file) return;
  hideError();
  busy("Reading your report. Photos can take up to 30 seconds.");
  const fd = new FormData();
  fd.append("file", file);
  try {
    const data = await api("/upload", {method: "POST", body: fd});
    reportId = data.report_id;
    tests = data.tests;
    renderReview();
    show("stepUpload", false); show("stepReview"); setStep(2);
  } catch (e) { showError(e.message); }
  finally { busy(null); $("file").value = ""; }
}

/* ---------- step 2: review ---------- */
function renderReview(){
  const body = $("reviewBody");
  body.innerHTML = "";
  const flagged = tests.filter(t => t.warning).length;
  const notice = $("reviewNotice");
  if (flagged){
    notice.textContent = flagged + (flagged === 1 ? " row needs" : " rows need") + " a quick look (highlighted). Photos can be misread, so please compare these with your report.";
    show("reviewNotice");
  } else { show("reviewNotice", false); }

  if (!tests.length){
    body.appendChild(el("p", "callout", "We could not find any test values in this file. Please try a clearer PDF or a sharper photo."));
    show("confirmBtn", false);
    return;
  }
  show("confirmBtn");

  tests.forEach((t, i) => {
    const row = el("div", "rv-row");
    row.setAttribute("role", "row");
    if (t.warning) row.classList.add("flagged");

    const name = el("div", "rv-name", t.test);
    let warnEl = null;
    if (t.warning){ warnEl = el("span", "rv-warn", t.warning); name.appendChild(warnEl); }

    const valCell = el("div", "rv-val");
    const input = el("input");
    input.type = "number"; input.step = "any"; input.value = t.value;
    input.setAttribute("aria-label", t.test + " value");
    valCell.appendChild(input); valCell.appendChild(el("span", "rv-unit", t.unit));

    const range = el("div", "rv-range", fmtRange(t));
    const chipWrap = el("div");
    const chip = el("span", "chip s-" + t.status, LABELS[t.status]);
    chipWrap.appendChild(chip);

    input.addEventListener("input", () => {
      t.value = input.value;
      const v = Number(input.value);
      if (input.value.trim() !== "" && !Number.isNaN(v)){
        t.status = liveStatus(v, t);
        chip.className = "chip s-" + t.status;
        chip.textContent = LABELS[t.status];
      }
      // The person looked at this row and corrected it, so the warning is done.
      if (warnEl){ warnEl.remove(); warnEl = null; row.classList.remove("flagged"); t.warning = null; }
    });

    const x = el("button", "rv-x", "×");
    x.type = "button";
    x.setAttribute("aria-label", "Remove " + t.test);
    x.addEventListener("click", () => { tests.splice(i, 1); renderReview(); });

    [name, valCell, range, chipWrap, x].forEach(c => row.appendChild(c));
    body.appendChild(row);
  });
}

async function confirmTests(){
  hideError();
  if (tests.some(t => String(t.value).trim() === "" || Number.isNaN(Number(t.value)))){
    return showError("Please enter a number for every value, or remove the row.");
  }
  const payload = tests.map(t => ({test: t.test, value: Number(t.value), unit: t.unit, ref_low: t.ref_low, ref_high: t.ref_high}));
  busy("Preparing your explanation.");
  try {
    const data = await api("/confirm/" + reportId, {method: "POST", headers: JSON_HEADERS, body: JSON.stringify({tests: payload})});
    tests = data.tests;
    renderResults(data.explanation || {});
    show("stepReview", false); show("stepResults"); setStep(3);
    renderChips();
  } catch (e) { showError(e.message); }
  finally { busy(null); }
}

/* ---------- step 3: results ---------- */
function resultCard(t, item){
  const card = el("article", "res");
  const head = el("div", "res-head");
  const left = el("div");
  left.appendChild(el("h4", "res-name", t.test));
  const val = el("p", "res-val");
  val.appendChild(el("strong", null, String(t.value)));
  val.appendChild(document.createTextNode(" " + (t.unit || "")));
  left.appendChild(val);
  head.appendChild(left);
  head.appendChild(el("span", "chip s-" + t.status, LABELS[t.status]));
  card.appendChild(head);
  const bar = rangeBar(t, true);
  if (bar) card.appendChild(bar);
  if (item){
    if (item.meaning) card.appendChild(el("p", "res-text", item.meaning));
    if (item.what_it_may_mean) card.appendChild(el("p", "res-text", "What it may mean: " + item.what_it_may_mean));
    if (item.why) card.appendChild(el("p", "res-text", "Why: " + item.why));
  }
  return card;
}

function renderResults(ex){
  const box = $("results");
  box.innerHTML = "";
  const byName = {};
  tests.forEach(t => byName[t.test] = t);

  // summary + tally (the tally is counted from the checked values, never from the AI)
  const sum = el("div", "summary-box");
  sum.appendChild(el("h2", null, "Your report in plain words"));
  sum.appendChild(el("p", "summary-text", ex.summary || ""));
  const count = s => tests.filter(t => s.includes(t.status)).length;
  const tally = el("div", "tally");
  [["normal", ["normal"], "normal"], ["high", ["high"], "higher than normal"],
   ["low", ["low"], "lower than normal"], ["critical_high", ["critical_high", "critical_low"], "need attention"]]
    .forEach(([cls, keys, label]) => {
      const n = count(keys);
      if (n) tally.appendChild(el("span", "chip s-" + cls, n + " " + label));
    });
  sum.appendChild(tally);
  box.appendChild(sum);

  const groups = [
    ["attention", "Needs special attention", "attention"],
    ["high", "Higher than normal", "watch"],
    ["low", "Lower than normal", "watch"],
    ["normal", "Looking good", "good"]
  ];
  const shown = new Set();
  groups.forEach(([key, title, cls]) => {
    const items = (ex[key] || []).filter(it => byName[it.test]);
    if (!items.length) return;
    const sec = el("section", "group " + cls);
    const h = el("h3", "group-title", title);
    h.appendChild(el("span", "count", String(items.length)));
    sec.appendChild(h);
    items.forEach(it => { shown.add(it.test); sec.appendChild(resultCard(byName[it.test], it)); });
    box.appendChild(sec);
  });
  // Safety net: any checked test the explanation skipped still appears.
  const rest = tests.filter(t => !shown.has(t.test));
  if (rest.length){
    const sec = el("section", "group watch");
    const h = el("h3", "group-title", "Other results");
    h.appendChild(el("span", "count", String(rest.length)));
    sec.appendChild(h);
    rest.forEach(t => sec.appendChild(resultCard(t, null)));
    box.appendChild(sec);
  }
  if (!(ex.attention || []).length){
    box.appendChild(el("p", "none-flagged", "Nothing was marked urgent. Please still share these results with your doctor."));
  }
}

/* ---------- chat ---------- */
function renderChips(){
  const chips = $("chips");
  chips.innerHTML = "";
  ["What does this report mean overall?", "What can I do about my low values?", "Should I be worried?"].forEach(q => {
    const c = el("button", "chip-q", q);
    c.type = "button";
    c.addEventListener("click", () => sendQuestion(q));
    chips.appendChild(c);
  });
}

// Tiny safe renderer for the answer: paragraphs, bullet lists, bold, simple tables.
function inline(parent, text){
  text.split(/(\*\*[^*]+\*\*)/).forEach(part => {
    if (/^\*\*[^*]+\*\*$/.test(part)) parent.appendChild(el("strong", null, part.slice(2, -2)));
    else if (part) parent.appendChild(document.createTextNode(part.replace(/\*/g, "")));
  });
}
function renderAnswer(box, text){
  const lines = text.replace(/\r/g, "").split("\n");
  let list = null, table = null, para = [];
  const flushPara = () => {
    if (!para.length) return;
    const joined = para.join(" ").trim(); para = [];
    if (!joined) return;
    const p = el("p");
    if (/^\*[^*].*[^*]\*$/.test(joined)) p.className = "disc";
    inline(p, joined); box.appendChild(p);
  };
  const flushAll = () => { flushPara(); list = null; table = null; };
  lines.forEach(raw => {
    const line = raw.trim();
    if (!line){ flushAll(); return; }
    if (line.startsWith("|")){
      flushPara(); list = null;
      const cells = line.replace(/^\||\|$/g, "").split("|").map(s => s.trim());
      if (cells.every(c => /^:?-{2,}:?$/.test(c))) return;
      const first = !table;
      if (first){ table = el("table"); box.appendChild(table); }
      const tr = el("tr");
      cells.forEach(c => { const cell = el(first ? "th" : "td"); inline(cell, c); tr.appendChild(cell); });
      table.appendChild(tr);
      return;
    }
    table = null;
    const m = line.match(/^[-*•]\s+(.*)$/);
    if (m){
      flushPara();
      if (!list){ list = el("ul"); box.appendChild(list); }
      const li = el("li"); inline(li, m[1]); list.appendChild(li);
      return;
    }
    list = null;
    para.push(line);
  });
  flushAll();
}

function addMsg(who, text){
  const m = el("div", "msg " + who);
  if (text) m.textContent = text;
  $("messages").appendChild(m);
  $("messages").scrollTop = $("messages").scrollHeight;
  return m;
}

async function sendQuestion(q){
  q = (q || $("question").value).trim();
  if (!q) return;
  $("question").value = "";
  addMsg("user", q);
  const bot = addMsg("bot", "Thinking...");
  try {
    const data = await api("/chat", {method: "POST", headers: JSON_HEADERS, body: JSON.stringify({report_id: reportId, question: q})});
    bot.textContent = "";
    if (/^this may be an emergency/i.test(data.answer)) bot.classList.add("emergency");
    renderAnswer(bot, data.answer);
    const links = (data.sources || []).filter(s => /^https:\/\//.test(s.url));
    if (links.length){
      const src = el("div", "src");
      src.appendChild(document.createTextNode("Sources: "));
      links.forEach((s, i) => {
        if (i) src.appendChild(document.createTextNode(", "));
        const a = el("a", null, s.name);
        a.href = s.url; a.target = "_blank"; a.rel = "noopener noreferrer";
        src.appendChild(a);
      });
      bot.appendChild(src);
    }
  } catch (e) { bot.textContent = e.message; }
  $("messages").scrollTop = $("messages").scrollHeight;
}

/* ---------- reset and delete ---------- */
function resetAll(){
  reportId = null; tests = [];
  $("messages").innerHTML = ""; $("results").innerHTML = "";
  hideError();
  show("stepResults", false); show("stepReview", false); show("stepUpload");
  setStep(1);
}
async function deleteData(){
  if (!confirm("Delete this report and your chat from the server?")) return;
  try { await api("/report/" + reportId, {method: "DELETE"}); } catch (e) {}
  resetAll();
}

/* ---------- wire up ---------- */
const drop = $("drop");
drop.addEventListener("click", () => $("file").click());
drop.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " "){ e.preventDefault(); $("file").click(); } });
drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", e => { e.preventDefault(); drop.classList.remove("over"); handleFile(e.dataTransfer.files[0]); });
$("file").addEventListener("change", e => handleFile(e.target.files[0]));
$("confirmBtn").addEventListener("click", confirmTests);
$("again1").addEventListener("click", resetAll);
$("again2").addEventListener("click", resetAll);
$("deleteBtn").addEventListener("click", deleteData);
$("askForm").addEventListener("submit", e => { e.preventDefault(); sendQuestion(); });
initSample();
