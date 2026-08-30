"""The browser UI.

Visual design follows the TEN Capital dark lockup: navy ground, tri-colour accent
(coral / amber / teal) echoing the three figures in the mark. The score bands reuse that
same triad — teal is strong, amber is mixed, coral is weak — so the palette carries meaning
rather than decoration.

Everything except the Google Fonts stylesheet is inline; every face has a real fallback
stack, so a blocked font request costs polish and nothing else.

Upload limits and accepted formats are injected from the server at render time. They are
never hardcoded here, so the page cannot promise something the backend refuses.
"""

from __future__ import annotations

import json

_TOKEN = "__ONEPAGER_CONFIG__"

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TEN Capital Network — Deck to One-Pager</title>
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<meta name="theme-color" content="#0B1526">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root{
    --navy-950:#0B1526; --navy-900:#101E33; --navy-800:#16283F; --navy-700:#1E354F;
    --coral:#EE5A4E; --coral-soft:#F0776C; --amber:#F3A22A; --teal:#35BEBB;
    --ink-100:#F3F6FA; --ink-300:#C4D0E0; --ink-500:#7E90A8; --ink-600:#5C6E86;
    --sans:'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    --display:'Sora', var(--sans);
    --mono:'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }

  *{ box-sizing:border-box; }

  html, body{
    margin:0; padding:0;
    background:var(--navy-950); color:var(--ink-100);
    font-family:var(--sans); min-height:100vh;
  }

  body{
    display:flex; align-items:flex-start; justify-content:center;
    padding:48px 20px 64px; position:relative; overflow-x:hidden;
  }

  /* ambient tri-colour glow, echoing the logo's three figures */
  body::before{
    content:""; position:fixed; inset:0; pointer-events:none; z-index:0;
    background:
      radial-gradient(480px 380px at 14% 8%, rgba(238,90,78,0.16), transparent 60%),
      radial-gradient(480px 380px at 86% 6%, rgba(243,162,42,0.13), transparent 60%),
      radial-gradient(560px 420px at 50% 100%, rgba(53,190,187,0.14), transparent 60%);
  }

  .stage{ position:relative; z-index:1; width:100%; max-width:620px; }

  /* --- brand lockup --- */
  .brand{ display:flex; align-items:center; gap:12px; margin-bottom:28px; padding-left:4px; }
  .brand-mark{ width:34px; height:34px; flex-shrink:0; }
  .brand-word{
    font-family:var(--display); font-weight:800; font-size:15px;
    letter-spacing:0.04em; line-height:1.15; color:var(--ink-100); text-transform:uppercase;
  }
  .brand-word span{
    display:block; font-weight:600; font-size:10px; letter-spacing:0.22em;
    color:var(--ink-500); margin-top:2px;
  }

  /* --- card --- */
  .card{
    background:linear-gradient(180deg, var(--navy-900) 0%, var(--navy-800) 100%);
    border:1px solid var(--navy-700); border-radius:20px;
    padding:44px 44px 36px; position:relative; overflow:hidden;
    box-shadow:0 30px 60px -20px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.03);
  }
  .card + .card{ margin-top:18px; }
  .card::after{
    content:""; position:absolute; top:0; left:44px; right:44px; height:2px;
    background:linear-gradient(90deg, var(--coral), var(--amber), var(--teal));
    border-radius:2px;
  }

  .eyebrow{
    display:flex; align-items:center; gap:8px;
    font-family:var(--mono); font-size:11px; letter-spacing:0.14em;
    text-transform:uppercase; color:var(--teal); margin-bottom:14px;
  }
  .eyebrow::before{
    content:""; width:6px; height:6px; border-radius:50%;
    background:var(--teal); box-shadow:0 0 0 3px rgba(53,190,187,0.18);
  }
  .eyebrow.is-amber{ color:var(--amber); }
  .eyebrow.is-amber::before{ background:var(--amber); box-shadow:0 0 0 3px rgba(243,162,42,0.18); }
  .eyebrow.is-coral{ color:var(--coral); }
  .eyebrow.is-coral::before{ background:var(--coral); box-shadow:0 0 0 3px rgba(238,90,78,0.18); }

  h1{
    font-family:var(--display); font-size:28px; font-weight:700; line-height:1.25;
    margin:0 0 12px; letter-spacing:-0.01em;
  }
  h1 .arrow{ color:var(--ink-500); font-weight:400; margin:0 4px; }
  h1 .to{
    background:linear-gradient(90deg, var(--coral-soft), var(--amber));
    -webkit-background-clip:text; background-clip:text; color:transparent;
  }

  .lede{ color:var(--ink-300); font-size:15px; line-height:1.6; margin:0 0 28px; max-width:46ch; }

  /* --- dropzone --- */
  .dropzone{
    display:block; border:1.5px dashed var(--navy-700); border-radius:14px;
    padding:38px 24px; text-align:center; cursor:pointer;
    background:rgba(255,255,255,0.015);
    transition:border-color .18s ease, background .18s ease, transform .18s ease;
  }
  .dropzone:hover, .dropzone.is-over{ border-color:var(--teal); background:rgba(53,190,187,0.05); }
  .dropzone:focus-visible{ outline:2px solid var(--teal); outline-offset:3px; }
  .dropzone:active{ transform:scale(0.997); }
  .dropzone.has-file{ border-style:solid; border-color:var(--teal); background:rgba(53,190,187,0.05); }

  .dropzone-icon{
    width:38px; height:38px; margin:0 auto 14px; border-radius:10px;
    background:linear-gradient(135deg, rgba(238,90,78,0.16), rgba(243,162,42,0.16));
    border:1px solid var(--navy-700); display:flex; align-items:center; justify-content:center;
  }
  .dropzone-icon svg{ width:18px; height:18px; }
  .dropzone-title{ font-size:15px; font-weight:600; color:var(--ink-100); margin-bottom:6px;
                   word-break:break-word; }
  .dropzone-sub{ font-family:var(--mono); font-size:11.5px; color:var(--ink-500); }
  .dropzone-sub b{ color:var(--ink-300); font-weight:500; }
  .file-input{ position:absolute; width:1px; height:1px; opacity:0; pointer-events:none; }

  /* --- optional field --- */
  .field{ margin-top:18px; }
  .field label{
    display:block; font-family:var(--mono); font-size:10.5px; letter-spacing:0.12em;
    text-transform:uppercase; color:var(--ink-500); margin-bottom:7px;
  }
  .field input{
    width:100%; padding:11px 13px; border-radius:10px;
    border:1px solid var(--navy-700); background:var(--navy-950);
    color:var(--ink-100); font-family:var(--sans); font-size:14px;
  }
  .field input::placeholder{ color:var(--ink-600); }
  .field input:focus{ outline:none; border-color:var(--teal); }

  /* --- buttons --- */
  .cta{
    width:100%; margin-top:22px; padding:16px 20px; border:none; border-radius:12px;
    background:linear-gradient(90deg, var(--coral) 0%, var(--coral-soft) 45%, var(--amber) 100%);
    color:#17130E; font-family:var(--display); font-weight:700; font-size:15px;
    letter-spacing:0.01em; cursor:pointer;
    transition:filter .15s ease, transform .15s ease;
    box-shadow:0 10px 24px -10px rgba(238,90,78,0.45);
  }
  .cta:hover:not(:disabled){ filter:brightness(1.06); transform:translateY(-1px); }
  .cta:active:not(:disabled){ transform:translateY(0); }
  .cta:disabled{
    background:var(--navy-950); color:var(--ink-600);
    border:1px solid var(--navy-700); box-shadow:none; cursor:not-allowed;
  }
  .cta:focus-visible{ outline:2px solid var(--ink-100); outline-offset:3px; }

  .ghost{
    display:inline-block; padding:11px 18px; border-radius:10px;
    border:1px solid var(--navy-700); background:transparent; color:var(--ink-300);
    font-family:var(--sans); font-weight:600; font-size:13.5px;
    cursor:pointer; text-decoration:none; transition:border-color .15s, color .15s;
  }
  .ghost:hover{ border-color:var(--teal); color:var(--ink-100); }
  .ghost:focus-visible{ outline:2px solid var(--teal); outline-offset:2px; }
  .btn-row{ display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }

  /* --- progress --- */
  .track{
    height:6px; border-radius:3px; background:var(--navy-950);
    border:1px solid var(--navy-700); overflow:hidden; margin:18px 0 12px;
  }
  .track > i{
    display:block; height:100%; width:12%;
    background:linear-gradient(90deg, var(--coral), var(--amber), var(--teal));
    transition:width .6s cubic-bezier(.4,0,.2,1);
  }
  .track.is-working > i{ animation:pulse 1.9s ease-in-out infinite; }
  @keyframes pulse{ 0%,100%{ opacity:1 } 50%{ opacity:.55 } }

  .stage-line{ font-family:var(--display); font-weight:600; font-size:15px; color:var(--ink-100); }
  .meta{ font-family:var(--mono); font-size:11.5px; color:var(--ink-500); margin-top:8px;
         line-height:1.6; }

  /* --- result --- */
  .result-title{
    font-family:var(--display); font-size:21px; font-weight:700; margin:0 0 4px;
    letter-spacing:-0.01em; word-break:break-word;
  }
  .tiles{ display:flex; gap:12px; flex-wrap:wrap; margin:22px 0 4px; }
  .tile{
    flex:1 1 150px; border:1px solid var(--navy-700); border-radius:12px;
    padding:16px 14px; background:var(--navy-950); text-align:center;
  }
  .tile b{ display:block; font-family:var(--display); font-size:30px; line-height:1.05; }
  .tile span{
    display:block; font-family:var(--mono); font-size:9.5px; letter-spacing:0.1em;
    text-transform:uppercase; color:var(--ink-500); margin-top:7px;
  }
  .tile .rail{ height:3px; border-radius:2px; background:var(--navy-700); margin-top:11px; overflow:hidden; }
  .tile .rail > i{ display:block; height:100%; border-radius:2px; }
  .band-strong{ border-color:rgba(53,190,187,0.45); }
  .band-strong b, .band-strong .rail > i{ color:var(--teal); background:var(--teal); }
  .band-strong b{ background:none; }
  .band-mixed{ border-color:rgba(243,162,42,0.45); }
  .band-mixed b{ color:var(--amber); }
  .band-mixed .rail > i{ background:var(--amber); }
  .band-weak{ border-color:rgba(238,90,78,0.45); }
  .band-weak b{ color:var(--coral); }
  .band-weak .rail > i{ background:var(--coral); }

  .notice{
    border-radius:11px; padding:13px 15px; font-size:13px; line-height:1.6; margin-top:18px;
    border:1px solid;
  }
  .notice-warn{ background:rgba(238,90,78,0.09); border-color:rgba(238,90,78,0.4); color:#FFC9C3; }
  .notice-warn b{ color:var(--coral-soft); }
  .notice-note{ background:rgba(243,162,42,0.08); border-color:rgba(243,162,42,0.34); color:#F6DDB4; }
  .notice-sent{ background:rgba(53,190,187,0.09); border-color:rgba(53,190,187,0.38); color:#BFEFEE; }
  .notice-sent b{ color:var(--teal); }
  .notice-note b{ color:var(--amber); }
  .notice ul{ margin:7px 0 0; padding-left:19px; }
  .notice li{ margin-top:3px; }

  /* --- disclosure & footer --- */
  .disclosure{
    margin-top:22px; padding-top:18px; border-top:1px solid var(--navy-700);
    font-size:12px; line-height:1.65; color:var(--ink-500);
  }
  .disclosure code{
    font-family:var(--mono); background:var(--navy-950); border:1px solid var(--navy-700);
    color:var(--ink-300); padding:2px 6px; border-radius:5px; font-size:11.5px;
  }
  footer{
    text-align:center; margin-top:22px; font-family:var(--mono); font-size:11px;
    letter-spacing:0.08em; color:var(--ink-600); text-transform:uppercase;
  }

  .hidden{ display:none !important; }
  .sr-only{
    position:absolute; width:1px; height:1px; padding:0; margin:-1px;
    overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0;
  }

  @media (max-width:480px){
    .card{ padding:32px 24px 28px; }
    .card::after{ left:24px; right:24px; }
    h1{ font-size:23px; }
  }
  @media (prefers-reduced-motion: reduce){
    *{ animation:none !important; transition:none !important; }
  }
</style>
</head>
<body>

<div class="stage">

  <div class="brand">
    <svg class="brand-mark" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg"
         role="img" aria-label="TEN Capital Network">
      <path d="M50 6 C64 6 74 16 74 16" stroke="var(--amber)" stroke-width="11" stroke-linecap="round" fill="none"/>
      <path d="M76 66 C76 82 63 92 63 92" stroke="var(--teal)" stroke-width="11" stroke-linecap="round" fill="none"/>
      <path d="M24 66 C24 82 37 92 37 92" stroke="var(--coral)" stroke-width="11" stroke-linecap="round" fill="none" transform="rotate(180 50 79)"/>
      <circle cx="50" cy="20" r="11" fill="var(--amber)"/>
      <circle cx="78" cy="68" r="11" fill="var(--teal)"/>
      <circle cx="22" cy="68" r="11" fill="var(--coral)"/>
    </svg>
    <div class="brand-word">Ten Capital<span>Network</span></div>
  </div>

  <form class="card" id="form">
    <div class="eyebrow">Deck Analyzer</div>
    <h1>Pitch Deck<span class="arrow">&rarr;</span><span class="to">Founder&nbsp;&amp;&nbsp;Team One&#8209;Pager</span></h1>
    <p class="lede">
      Upload a pitch deck and get a single-page investor PDF answering one question:
      is this the right team to build this business, and where are the gaps?
      Every claim is cited to a slide.
    </p>

    <label class="dropzone" id="drop" for="deck-upload" tabindex="0">
      <div class="dropzone-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="var(--ink-100)" stroke-width="1.6"
             stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 3v4a1 1 0 0 0 1 1h4"/>
          <path d="M17 21H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7l5 5v11a2 2 0 0 1-2 2Z"/>
        </svg>
      </div>
      <div class="dropzone-title" id="drop-title">Drop a deck here, or click to choose</div>
      <div class="dropzone-sub" id="drop-sub"></div>
      <input class="file-input" type="file" id="deck-upload">
    </label>

    <div class="field">
      <label for="company">Company name override — optional</label>
      <input id="company" type="text" autocomplete="off"
             placeholder="Leave blank to read it from the deck">
    </div>

    <button class="cta" id="go" type="submit" disabled>Generate one-pager PDF</button>

    <div class="btn-row">
      <a class="ghost" id="tpl" href="/api/template.pdf">Download blank template</a>
    </div>

    <div class="disclosure" id="disclosure"></div>
  </form>

  <section class="card hidden" id="progress" aria-live="polite">
    <div class="eyebrow is-amber" id="prog-eyebrow">Working</div>
    <div class="stage-line" id="stage-line">Queued</div>
    <div class="track is-working"><i id="fill"></i></div>
    <div class="meta" id="prog-meta"></div>
  </section>

  <section class="card hidden" id="result"></section>
  <section class="card hidden" id="error" role="alert"></section>

  <footer>Powered by TEN Capital Network</footer>
</div>

<script id="cfg" type="application/json">__ONEPAGER_CONFIG__</script>
<script>
(function () {
  "use strict";
  const CFG = JSON.parse(document.getElementById("cfg").textContent);
  const $ = (id) => document.getElementById(id);
  const PROGRESS = { queued:12, extracting:34, analyzing:72, rendering:93, done:100, error:100 };

  let file = null, timer = null;

  // --- setup driven by server config, so the page cannot overpromise ----------------
  $("deck-upload").setAttribute("accept", CFG.accept.join(","));
  $("drop-sub").innerHTML =
    CFG.accept.map((e) => "<b>" + e + "</b>").join(" &middot; ") +
    " &nbsp;&middot;&nbsp; up to " + CFG.max_upload_mb + "&nbsp;MB";
  $("disclosure").innerHTML = CFG.disclosure_html;

  // --- file selection ---------------------------------------------------------------
  const drop = $("drop");
  drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("deck-upload").click(); }
  });
  ["dragenter", "dragover"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("is-over"); }));
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, () => drop.classList.remove("is-over")));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer.files.length) choose(e.dataTransfer.files[0]);
  });
  $("deck-upload").addEventListener("change", (e) => {
    if (e.target.files.length) choose(e.target.files[0]);
  });

  function choose(f) {
    const ext = "." + (f.name.split(".").pop() || "").toLowerCase();
    if (CFG.accept.indexOf(ext) === -1) {
      return fail("That is a " + ext + " file. Upload one of: " + CFG.accept.join(", ") + ".");
    }
    const mb = f.size / 1048576;
    if (mb > CFG.max_upload_mb) {
      return fail("That deck is " + mb.toFixed(1) + " MB, over the " +
                  CFG.max_upload_mb + " MB limit.");
    }
    file = f;
    drop.classList.add("has-file");
    $("drop-title").textContent = f.name;
    $("drop-sub").innerHTML = "<b>" + mb.toFixed(1) + " MB</b> &nbsp;&middot;&nbsp; click to change";
    $("go").disabled = false;
    hide("error");
  }

  // --- submit -------------------------------------------------------------------------
  $("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!file) return;

    const body = new FormData();
    body.append("deck", file);
    const company = $("company").value.trim();
    if (company) body.append("company", company);

    hide("result"); hide("error");
    $("go").disabled = true;
    show("progress");
    paint({ status: "queued", stage_text: "Uploading the deck", elapsed_seconds: 0 });

    let res;
    try {
      res = await fetch("/api/jobs", { method: "POST", body: body });
    } catch (err) {
      return fail("Could not reach the server. Check your connection and try again.");
    }
    if (!res.ok) {
      let detail = "Upload failed.";
      try { detail = (await res.json()).detail || detail; } catch (err) { /* non-JSON body */ }
      return fail(detail);
    }
    poll((await res.json()).id);
  });

  // --- polling --------------------------------------------------------------------------
  function poll(id) {
    timer = setInterval(async () => {
      let job;
      try { job = await (await fetch("/api/jobs/" + id)).json(); }
      catch (err) { return; }                       // transient blip: keep polling
      paint(job);
      if (job.status === "done")  { stop(); succeed(job, id); }
      if (job.status === "error") { stop(); fail(job.detail, job.exit_code); }
    }, 2000);
  }

  function stop() { if (timer) { clearInterval(timer); timer = null; } }

  function paint(job) {
    $("stage-line").textContent = job.stage_text;
    $("fill").style.width = (PROGRESS[job.status] || 12) + "%";
    const bits = [Math.round(job.elapsed_seconds || 0) + "s elapsed"];
    if (job.slides) bits.push(job.slides + " slides read");
    if (job.used_vision) bits.push("image-based deck — reading page images");
    $("prog-meta").textContent = bits.join("  ·  ");
  }

  // --- outcomes ---------------------------------------------------------------------------
  function band(v) { return v >= 70 ? "band-strong" : v >= 40 ? "band-mixed" : "band-weak"; }

  function tile(value, label) {
    return '<div class="tile ' + band(value) + '"><b>' + value + "</b>" +
           "<span>" + label + "</span>" +
           '<div class="rail"><i style="width:' + value + '%"></i></div></div>';
  }

  function succeed(job, id) {
    hide("progress");
    const warn = job.low_confidence
      ? '<div class="notice notice-warn"><b>Low confidence</b> — evidence quality ' +
        job.evidence_quality + "/100. This deck does not contain enough team information " +
        "to score reliably; treat the score as provisional.</div>"
      : "";
    const mailed = job.emailed
      ? '<div class="notice notice-sent"><b>Emailed</b> — a copy has been sent to ' +
        esc(CFG.email_to.join(", ")) + ".</div>"
      : (CFG.email_to.length
          ? '<div class="notice notice-note"><b>Not emailed</b> — delivery did not ' +
            "succeed; see the notes below. Your download is unaffected.</div>"
          : "");
    const notes = (job.notes && job.notes.length)
      ? '<div class="notice notice-note"><b>Notes</b><ul>' +
        job.notes.map((n) => "<li>" + esc(n) + "</li>").join("") + "</ul></div>"
      : "";

    $("result").innerHTML =
      '<div class="eyebrow">One-pager ready</div>' +
      '<h2 class="result-title">' + esc(job.company_name || job.filename) + "</h2>" +
      '<div class="meta">' + esc(job.filename) + "  ·  " +
        Math.round(job.elapsed_seconds) + "s  ·  " + job.tokens.input + " in / " +
        job.tokens.output + " out  ·  ~$" + job.cost_usd.toFixed(3) + "</div>" +
      '<div class="tiles">' +
        tile(job.team_score, "Team score / 100") +
        tile(job.evidence_quality, "Evidence quality") +
      "</div>" + warn + mailed + notes +
      '<a class="cta" style="display:block;text-align:center;text-decoration:none" ' +
        'href="/api/jobs/' + id + '/pdf">Download one-pager PDF</a>' +
      '<div class="btn-row">' +
        '<a class="ghost" href="/api/jobs/' + id + '/json">Analysis JSON</a>' +
        '<button class="ghost" type="button" id="again">Analyze another deck</button>' +
      "</div>";
    show("result");
    $("go").disabled = false;
    $("again").addEventListener("click", reset);
    $("result").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function fail(message, code) {
    stop();
    hide("progress");
    $("error").innerHTML =
      '<div class="eyebrow is-coral">Could not generate</div>' +
      '<div class="notice notice-warn">' + esc(message) +
      (code ? ' <span style="opacity:.65">(exit code ' + code + ")</span>" : "") + "</div>";
    show("error");
    $("go").disabled = !file;
  }

  function reset() {
    hide("result"); hide("error");
    file = null;
    drop.classList.remove("has-file");
    $("drop-title").textContent = "Drop a deck here, or click to choose";
    $("drop-sub").innerHTML =
      CFG.accept.map((e) => "<b>" + e + "</b>").join(" &middot; ") +
      " &nbsp;&middot;&nbsp; up to " + CFG.max_upload_mb + "&nbsp;MB";
    $("deck-upload").value = "";
    $("go").disabled = true;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function show(id) { $(id).classList.remove("hidden"); }
  function hide(id) { $(id).classList.add("hidden"); }
  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }
})();
</script>
</body>
</html>
"""

#: What the page tells a founder about their deck. Both variants must stay true of the
#: running app, which is why the recipient list comes from the server rather than the copy.
DISCLOSURE_BASE = (
    "The deck is processed on the server and passed to Anthropic's Claude API for analysis. "
    "It is written to a temporary file that is deleted as soon as the job finishes, and the "
    "generated PDF is held in memory for <code>{ttl} minutes</code> before it is discarded. "
)
DISCLOSURE_NO_EMAIL = "Nothing is emailed, stored, or retained after that."
DISCLOSURE_EMAIL = (
    "A copy of the one-pager and its analysis JSON is emailed to <code>{to}</code>. "
    "The deck itself is never emailed and is not retained."
)


def disclosure_html(job_ttl_minutes: int, email_to: list[str] | None) -> str:
    """Say exactly what this deployment does with an uploaded deck."""
    base = DISCLOSURE_BASE.format(ttl=job_ttl_minutes)
    if email_to:
        return base + DISCLOSURE_EMAIL.format(to=", ".join(email_to))
    return base + DISCLOSURE_NO_EMAIL


def render_page(
    accept: tuple[str, ...],
    max_upload_mb: int,
    job_ttl_minutes: int,
    email_to: list[str] | None = None,
) -> str:
    """Render the page with server-side limits injected, so the UI cannot overpromise."""
    config = {
        "accept": list(accept),
        "max_upload_mb": max_upload_mb,
        "disclosure_html": disclosure_html(job_ttl_minutes, email_to),
        "email_to": email_to or [],
    }
    return _PAGE.replace(_TOKEN, json.dumps(config))
