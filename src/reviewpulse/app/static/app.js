/* ReviewPulse single-page UI: projects -> setup (uploads) -> rules (review queue) -> results (plan viewer). */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const VERDICTS = ["FAIL", "WARNING", "NOT_EVALUATED", "PASS"];
const VLABEL = { FAIL: "Fail", WARNING: "Warning", NOT_EVALUATED: "Not evaluated", PASS: "Pass" };
const SEVERITIES = ["critical", "major", "minor", "info"];
const SVGNS = "http://www.w3.org/2000/svg";

const state = { health: null, project: null, polls: new Map(), rulesFilter: "all", results: null };

/* ---------------------------------------------------------------- api */
async function api(path, opts = {}) {
  const init = { ...opts, headers: { ...(opts.headers || {}) } };
  if (opts.json !== undefined) {
    init.body = JSON.stringify(opts.json);
    init.headers["Content-Type"] = "application/json";
  }
  const r = await fetch(path, init);
  if (r.status === 204) return null;
  const ct = r.headers.get("content-type") || "";
  const body = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error((body && body.detail) || r.statusText);
  return body;
}

function toast(msg, err = false) {
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "");
  t.textContent = msg;
  $("#toasts").append(t);
  setTimeout(() => t.remove(), err ? 7000 : 3500);
}

function fmtDate(s) {
  if (!s) return "";
  const d = new Date(s);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/* ---------------------------------------------------------------- jobs */
function watchJob(pid, job, onDone) {
  if (!job) return;
  const key = job.id;
  if (state.polls.has(key)) return;
  const tick = async () => {
    let rec;
    try { rec = await api(`/api/projects/${pid}/jobs/${job.id}`); } catch { rec = null; }
    if (rec) renderJob(rec);
    if (!rec || rec.status === "done" || rec.status === "failed") {
      state.polls.delete(key);
      if (rec && rec.status === "failed") toast(`${jobName(rec.kind)} failed: ${rec.error}`, true);
      if (rec && rec.status === "done") toast(`${jobName(rec.kind)} finished`);
      if (onDone) onDone(rec);
      return;
    }
    state.polls.set(key, setTimeout(tick, 900));
  };
  state.polls.set(key, setTimeout(tick, 300));
}

function jobName(kind) {
  return { analyse: "Plan analysis", draft: "Rule drafting", check: "Check", interpret: "Reading requirements" }[kind] || kind;
}

function renderJob(rec) {
  for (const el of $$(`[data-job-kind="${rec.kind}"]`)) {
    const pct = Math.round((rec.progress || 0) * 100);
    const failed = rec.status === "failed";
    el.innerHTML = rec.status === "done" ? "" :
      `<div class="progress"><i style="width:${failed ? 100 : pct}%;${failed ? "background:var(--fail)" : ""}"></i></div>
       <div class="job ${failed ? "err" : ""}">${esc(failed ? rec.error : `${rec.message} · ${pct}%`)}</div>`;
  }
}

/* ---------------------------------------------------------------- router */
async function route() {
  for (const t of state.polls.values()) clearTimeout(t);
  state.polls.clear();
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  try {
    if (parts[0] === "p" && parts[1]) {
      await projectView(parts[1], parts[2] || "setup");
    } else {
      await projectsView();
    }
  } catch (e) {
    $("#view").innerHTML = `<div class="card pad empty">${esc(e.message)}<br><br><a href="#/">Back to projects</a></div>`;
  }
}

function crumbs(items) {
  $("#crumbs").innerHTML = items.map((i) => `<span>/</span><span>${esc(i)}</span>`).join("");
}

/* ---------------------------------------------------------------- projects */
async function projectsView() {
  crumbs([]);
  const [projects, packs] = await Promise.all([api("/api/projects"), api("/api/packs")]);
  const packOpts = packs.map((p) => `<option value="${esc(p.name)}">${esc(p.name)} · ${p.rules} rules</option>`).join("");
  $("#view").innerHTML = `
    <div class="hero">
      <div><h1>Projects</h1><p class="muted">Check architectural plans against the requirement documents that govern them.</p></div>
    </div>
    <form class="card pad newproj" id="newproj">
      <label class="field">Project name<input type="text" name="name" required placeholder="e.g. Résidence Les Pins, lot B"></label>
      <label class="field">Base rule pack<select name="base_pack">${packOpts}<option value="">none (project rules only)</option></select></label>
      <label class="field">Reviewer<input type="text" name="curator" placeholder="your name"></label>
      <button class="btn primary" type="submit">Create project</button>
    </form>
    <div class="card plist">${projects.length ? projects.map(projectRow).join("") :
      `<div class="empty">No projects yet. Create one above, then upload a plan and its requirement document.</div>`}</div>`;
  $("#newproj").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = new FormData(ev.target);
    try {
      const p = await api("/api/projects", { method: "POST", json: { name: f.get("name"), base_pack: f.get("base_pack") || null, curator: f.get("curator") } });
      location.hash = `#/p/${p.id}/setup`;
    } catch (e) { toast(e.message, true); }
  });
}

function projectRow(p) {
  const status = p.active_jobs.length ? `<span class="badge">${esc(jobName(p.active_jobs[0].kind))}…</span>`
    : p.checked ? `<span class="badge state-approved">checked</span>` : p.plan ? `<span class="badge">analysed</span>` : `<span class="badge">new</span>`;
  return `<a class="prow" href="#/p/${p.id}/${p.checked ? "results" : "setup"}">
    <div><b>${esc(p.name)}</b><div class="muted mono">${esc(p.plan || "no plan yet")}</div></div>
    <div class="muted">${esc(p.requirements || "no requirement document")}</div>
    <div class="counts">${status}<span class="badge">${p.rules.total ?? 0} rules</span>${p.base_pack ? `<span class="badge">${esc(p.base_pack)}</span>` : ""}</div>
    <div class="muted">${fmtDate(p.updated)}</div></a>`;
}

/* ---------------------------------------------------------------- project shell */
async function projectView(pid, tab) {
  const p = await api(`/api/projects/${pid}`);
  state.project = p;
  crumbs([p.name]);
  const nd = p.has_drafts ? (await api(`/api/projects/${pid}/drafts`)).filter((d) => d.rule && d.decision.state === "pending").length : 0;
  $("#view").innerHTML = `
    <div class="ptitle">
      <div><h1>${esc(p.name)}</h1><div class="muted">${p.rules.total ?? 0} active rules${p.base_pack ? ` · base pack ${esc(p.base_pack)}` : ""}${p.rules.project ? ` · ${p.rules.project} approved from the requirements` : ""}</div></div>
      <div class="row"><button class="btn primary" id="runcheck" ${p.plan ? "" : "disabled"}>Run check</button></div>
    </div>
    <nav class="tabs">
      <a href="#/p/${pid}/setup" class="${tab === "setup" ? "on" : ""}">Inputs</a>
      <a href="#/p/${pid}/requirements" class="${tab === "requirements" ? "on" : ""}">Requirements</a>
      <a href="#/p/${pid}/rules" class="${tab === "rules" ? "on" : ""}">Rules${nd ? `<span class="n">${nd} to review</span>` : ""}</a>
      <a href="#/p/${pid}/results" class="${tab === "results" ? "on" : ""}">Results</a>
    </nav>
    <section id="tab"></section>`;
  $("#runcheck").addEventListener("click", async () => {
    try {
      const job = await api(`/api/projects/${pid}/check`, { method: "POST" });
      toast("Check started");
      if (tab !== "results") location.hash = `#/p/${pid}/results`;
      watchJob(pid, job, () => tab === "results" ? resultsTab(pid) : null);
      if (tab === "results") $("#tab").insertAdjacentHTML("afterbegin", `<div data-job-kind="${job.kind}"></div>`);
    } catch (e) { toast(e.message, true); }
  });
  if (tab === "requirements") return requirementsTab(pid);
  if (tab === "rules") return rulesTab(pid);
  if (tab === "results") return resultsTab(pid);
  return setupTab(pid);
}

/* ---------------------------------------------------------------- setup tab */
const ICON_UP = `<svg viewBox="0 0 24 24"><path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/></svg>`;

async function setupTab(pid) {
  const p = state.project;
  const [packs, health] = [await api("/api/packs"), state.health];
  const plans = health.plan_types.join(" "), reqs = health.requirement_types.join(" ");
  $("#tab").innerHTML = `
    <div class="grid2">
      <div class="card pad">
        <h2>1 · Plan</h2>
        <p class="muted">A drawing as vector PDF, DXF, SVG, or a scan (PNG, JPG, scanned PDF).</p>
        <label class="drop" data-kind="plan">${ICON_UP}<b>Drop the plan here or click to choose</b><span class="muted mono">${esc(plans)}</span>
          <input type="file" hidden accept="${esc(health.plan_types.join(","))}"></label>
        ${p.plan ? `<div class="file"><span class="badge">plan</span><span class="name">${esc(p.plan)}</span></div>` : ""}
        <div data-job-kind="analyse"></div>
      </div>
      <div class="card pad">
        <h2>2 · Requirement document</h2>
        <p class="muted">The regulation or brief the plan must satisfy. Its clauses become rules you review.</p>
        <label class="drop" data-kind="requirements">${ICON_UP}<b>Drop the document here or click to choose</b><span class="muted mono">${esc(reqs)}</span>
          <input type="file" hidden accept="${esc(health.requirement_types.join(","))}"></label>
        ${p.requirements ? `<div class="file"><span class="badge">document</span><span class="name">${esc(p.requirements)}</span>
          <span class="spacer"></span><button class="btn sm" id="redraft">Draft again</button></div>` : ""}
        <div data-job-kind="draft"></div>
        ${health.llm.available ? "" : `<p class="notice" style="margin-top:12px">The drafting model (${esc(health.llm.model)}) is offline. Clauses are still extracted and you can write rules by hand; start it with <span class="mono">ollama serve</span> to draft automatically.</p>`}
      </div>
    </div>
    <div class="card pad" style="margin-top:16px">
      <h2>3 · Settings</h2>
      <div class="row">
        <label class="field">Base rule pack<select id="basepack">${packs.map((x) => `<option value="${esc(x.name)}" ${x.name === p.base_pack ? "selected" : ""}>${esc(x.name)} · ${x.rules} rules</option>`).join("")}<option value="" ${p.base_pack ? "" : "selected"}>none</option></select></label>
        <label class="field">Reviewer<input type="text" id="curator" value="${esc(p.curator)}" placeholder="your name"></label>
        <button class="btn" id="savesettings" style="align-self:end">Save</button>
      </div>
      <div class="steps" id="steps"></div>
    </div>`;
  renderSteps(p);
  for (const drop of $$(".drop")) {
    const input = $("input", drop);
    drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("over"));
    drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) upload(pid, drop.dataset.kind, e.dataTransfer.files[0]); });
    input.addEventListener("change", () => input.files[0] && upload(pid, drop.dataset.kind, input.files[0]));
  }
  $("#savesettings").addEventListener("click", async () => {
    const v = $("#basepack").value;
    try {
      await api(`/api/projects/${pid}`, { method: "PATCH", json: { base_pack: v || null, clear_base_pack: !v, curator: $("#curator").value } });
      toast("Settings saved");
      route();
    } catch (e) { toast(e.message, true); }
  });
  const rd = $("#redraft");
  if (rd) rd.addEventListener("click", async () => {
    try { watchJob(pid, await api(`/api/projects/${pid}/draft`, { method: "POST" }), () => route()); } catch (e) { toast(e.message, true); }
  });
  for (const j of p.active_jobs) { renderJob(j); watchJob(pid, j, () => route()); }
}

function renderSteps(p) {
  const steps = [
    ["Plan", p.plan ? (p.analysed ? "analysed" : "uploaded") : "missing"],
    ["Requirements", p.requirements ? (p.has_drafts ? "drafted" : "uploaded") : "optional"],
    ["Active rules", String(p.rules.total ?? 0)],
    ["Check", p.checked ? "done" : "not run"],
  ];
  $("#steps").innerHTML = steps.map(([k, v]) => `<div class="step"><div class="k">${k}</div><div class="v">${esc(v)}</div></div>`).join("");
}

async function upload(pid, kind, file) {
  const fd = new FormData();
  fd.append("file", file);
  try {
    const job = await api(`/api/projects/${pid}/${kind === "plan" ? "plan" : "requirements"}`, { method: "POST", body: fd });
    toast(`${file.name} uploaded`);
    await route();
    renderJob(job);
    watchJob(pid, job, () => route());
  } catch (e) { toast(e.message, true); }
}

/* ---------------------------------------------------------------- rules tab */
async function rulesTab(pid) {
  const p = state.project;
  const drafts = p.has_drafts ? await api(`/api/projects/${pid}/drafts`) : [];
  const clauses = await api(`/api/projects/${pid}/clauses`);
  const draftJob = p.active_jobs.find((j) => j.kind === "draft");
  if (!drafts.length) {
    $("#tab").innerHTML = `<div data-job-kind="draft"></div><div class="card">${clauses.length ? clauseOnly(clauses) :
      `<div class="empty">${draftJob ? "Drafting rules from the requirement document…" : p.requirements ? "No drafts yet." : "Upload a requirement document on the Inputs tab to draft rules from it."}</div>`}</div>`;
    if (draftJob) { renderJob(draftJob); watchJob(pid, draftJob, () => route()); }
    return;
  }
  const counts = { all: drafts.length, review: 0, approved: 0, rejected: 0, other: 0 };
  for (const d of drafts) {
    if (d.decision.state === "approved") counts.approved++;
    else if (d.decision.state === "rejected") counts.rejected++;
    else if (d.rule) counts.review++;
    else counts.other++;
  }
  const f = state.rulesFilter;
  const segs = [["all", "All"], ["review", "To review"], ["approved", "Approved"], ["rejected", "Rejected"], ["other", "Not checkable"]];
  $("#tab").innerHTML = `
    <div data-job-kind="draft"></div>
    <div class="toolbar">
      <div class="seg">${segs.map(([k, l]) => `<button data-f="${k}" class="${f === k ? "on" : ""}">${l} · ${counts[k]}</button>`).join("")}</div>
      <span class="spacer"></span>
      <span class="muted">Drafted by ${esc(drafts[0].model || "?")} · every rule is approved by a person before it runs</span>
    </div>
    <div class="card" id="drafts">${drafts.filter((d) => keep(d, f)).map(draftRow).join("") || `<div class="empty">Nothing here.</div>`}</div>`;
  for (const b of $$(".seg button")) b.addEventListener("click", () => { state.rulesFilter = b.dataset.f; rulesTab(pid); });
  for (const row of $$(".draft")) wireDraft(pid, row, drafts[+row.dataset.i]);
  if (draftJob) { renderJob(draftJob); watchJob(pid, draftJob, () => route()); }
}

function keep(d, f) {
  const s = d.decision.state;
  if (f === "all") return true;
  if (f === "approved" || f === "rejected") return s === f;
  if (f === "review") return s === "pending" && d.rule;
  return !d.rule && s === "pending";
}

function clauseOnly(clauses) {
  return `<div class="pad"><p class="notice info">Clauses were extracted, but no rules were drafted (the drafting model was offline). Start the model and use “Draft again” on the Inputs tab.</p></div>` +
    clauses.map((c) => `<div class="draft"><div class="clause"><div class="cid">${esc(c.id)}</div><p>${esc(c.text)}</p></div><div class="muted">${esc(c.heading || "")}</div></div>`).join("");
}

function describe(rule) {
  const c = rule.check || {};
  const at = rule.applies_to || {};
  const what = at.element ? `each ${at.element}` : at.room_type ? `rooms: ${[].concat(at.room_type).join(", ")}` : "the plan";
  const cmp = c.op !== undefined && c.value !== undefined ? `${c.fn} ${c.op} ${c.value}${c.unit ? " " + c.unit : ""}` : c.fn;
  return { what, cmp };
}

function draftRow(d) {
  const st = d.decision.state;
  const label = { from_drawings: "checkable on the plan", needs_other_data: "needs other data", not_checkable: "not checkable on a plan", error: "error" }[d.checkable] || d.checkable;
  let right;
  if (d.rule) {
    const { what, cmp } = describe(d.rule);
    right = `
      <div class="rulehead"><span class="title">${esc(d.rule.title || d.rule.id)}</span><span class="badge mono">${esc(d.rule.id)}</span>
        <span class="badge state-${st}">${st}</span><span class="badge">${esc(d.rule.severity || "")}</span></div>
      <dl class="kv"><dt>Applies to</dt><dd>${esc(what)}</dd><dt>Check</dt><dd>${esc(cmp)}</dd><dt>Class</dt><dd>${esc(d.rule.class)}</dd></dl>
      ${d.flags.map((x) => `<div class="flag">⚑ ${esc(x)}</div>`).join("")}
      ${d.errors.map((x) => `<div class="error">✕ ${esc(x)}</div>`).join("")}
      ${d.decision.message ? `<div class="muted" style="font-size:12.5px">${esc(d.decision.message)}</div>` : ""}
      <div class="editor hide"><textarea spellcheck="false">${esc(d.rule_yaml)}</textarea></div>
      <div class="actions">
        ${st !== "approved" ? `<button class="btn sm primary" data-a="approve">Approve</button>` : ""}
        <button class="btn sm" data-a="edit">Edit rule</button>
        ${st !== "rejected" ? `<button class="btn sm danger" data-a="reject">Reject</button>` : ""}
        ${st !== "pending" ? `<button class="btn sm" data-a="reset">Reset</button>` : ""}
      </div>`;
  } else {
    right = `<div class="rulehead"><span class="badge">${esc(label)}</span><span class="badge state-${st}">${st}</span></div>
      <p class="muted">${esc(d.rationale || "No rule: this clause cannot be checked on a drawing.")}</p>
      ${d.errors.map((x) => `<div class="error">✕ ${esc(x)}</div>`).join("")}`;
  }
  return `<div class="draft" data-i="${d.index}">
    <div class="clause"><div class="cid">${esc(d.clause_id)}</div><p>${esc(d.clause_text)}</p><span class="badge">${esc(label)}</span></div>
    <div>${right}</div></div>`;
}

function wireDraft(pid, row, d) {
  const curator = () => state.project.curator || "reviewer";
  for (const b of $$("[data-a]", row)) {
    b.addEventListener("click", async () => {
      const a = b.dataset.a;
      if (a === "edit") {
        $(".editor", row).classList.toggle("hide");
        b.textContent = $(".editor", row).classList.contains("hide") ? "Edit rule" : "Hide editor";
        return;
      }
      b.disabled = true;
      try {
        if (a === "approve") {
          const ed = $(".editor", row);
          const yaml = ed && !ed.classList.contains("hide") ? $("textarea", row).value : null;
          const r = await api(`/api/projects/${pid}/drafts/${d.index}/approve`, { method: "POST", json: { curator: curator(), rule_yaml: yaml } });
          toast(r.message, !r.ok);
        } else {
          await api(`/api/projects/${pid}/drafts/${d.index}/${a}`, { method: "POST", json: { curator: curator() } });
        }
        await projectView(pid, "rules");
      } catch (e) { toast(e.message, true); b.disabled = false; }
    });
  }
}


/* ---------------------------------------------------------------- requirements tab */
const OUTCOME_TEXT = { SATISFIED: "satisfied on this plan", VIOLATED: "violated on this plan", NOT_APPLICABLE: "does not apply to this plan",
  EXEMPT: "exempt on this plan", UNRESOLVED: "cannot be decided from this plan" };

async function requirementsTab(pid) {
  const p = state.project;
  let doc;
  try { doc = await api(`/api/projects/${pid}/document`); }
  catch (e) { $("#tab").innerHTML = `<div class="card pad"><div class="empty">${esc(e.message)}. Upload a requirement document on the Inputs tab.</div></div>`; return; }
  const got = await api(`/api/projects/${pid}/interpreted`);
  const job = p.active_jobs.find((j) => j.kind === "interpret");
  const done = doc.clauses.filter((c) => got[c.id]);
  const n = (st) => done.filter((c) => got[c.id].status === st).length;
  $("#tab").innerHTML = `
    <div data-job-kind="interpret"></div>
    <div class="toolbar">
      <span><b>${esc(doc.name)}</b> · ${doc.clauses.length} clauses · ${n("DRAFTED")} with a rule · ${n("UNRESOLVED")} not checked yet · ${doc.clauses.length - done.length} not read yet</span>
      <span class="spacer"></span>
      <button class="btn primary" id="readall" ${p.plan ? "" : "disabled"} title="${p.plan ? "" : "Upload a plan first: rules are written against what the plan reader can measure"}">Read all clauses</button>
    </div>
    <p class="muted pad">Each clause becomes a rule only if the rule agrees with the sentence (category, numbers, comparison direction) and uses only facts this plan provides. Otherwise it is marked not checked yet, with the reason. Nothing here is approved: a person approves a rule before it counts.</p>
    <div class="card" id="clauses">${doc.clauses.map((c) => clauseCard(c, got[c.id])).join("")}</div>`;
  $("#readall").addEventListener("click", async () => {
    try { const j = await api(`/api/projects/${pid}/interpret`, { method: "POST" }); toast("Reading started"); watchJob(pid, j, () => route()); } catch (e) { toast(e.message, true); }
  });
  for (const b of $$("[data-read]")) b.addEventListener("click", async () => {
    b.disabled = true; b.textContent = "Reading…";
    try { await api(`/api/projects/${pid}/interpret/${encodeURIComponent(b.dataset.read)}`, { method: "POST" }); } catch (e) { toast(e.message, true); }
    requirementsTab(pid);
  });
  if (job) { renderJob(job); watchJob(pid, job, () => route()); }
}

function clauseCard(c, r) {
  const head = `<div class="clause"><div class="cid">${esc(c.id)}</div><p>${esc(c.text)}</p></div>`;
  if (!r) return `<div class="draft">${head}<div class="muted">Not read yet</div><div class="row"><button class="btn" data-read="${esc(c.id)}">Read this clause</button></div></div>`;
  const body = r.status === "DRAFTED"
    ? `<div class="flag" style="color:var(--pass)">Rule written. It reads: <code>${esc(r.readback)}</code>${r.applies_when && r.applies_when !== "true" ? `<br>Applies when: <code>${esc(r.applies_when)}</code>` : ""}${r.unless && r.unless !== "false" ? `<br>Unless: <code>${esc(r.unless)}</code>` : ""}</div>
       <div class="muted">On this plan (preview, not approved): <b>${esc(OUTCOME_TEXT[r.preview?.outcome] || r.preview?.outcome || "")}</b>${(r.preview?.missing || []).length ? ` · needs: ${esc(r.preview.missing.join(", "))}` : ""}</div>
       ${(r.notes || []).map((x) => `<div class="flag">${esc(x)}</div>`).join("")}`
    : `<div class="flag">Not checked yet: ${esc(r.reason)}</div>`;
  return `<div class="draft">${head}${body}<div class="row"><button class="btn" data-read="${esc(c.id)}">Read again</button></div></div>`;
}

/* ---------------------------------------------------------------- results tab */
async function resultsTab(pid) {
  const p = state.project;
  const active = p.active_jobs.find((j) => j.kind === "analyse" || j.kind === "check");
  if (!p.analysed) {
    $("#tab").innerHTML = `<div class="card pad"><div data-job-kind="${active ? active.kind : "analyse"}"></div><div class="empty">${active ? "Analysing the plan…" : "Upload a plan on the Inputs tab to see results."}</div></div>`;
    if (active) { renderJob(active); watchJob(pid, active, () => route()); }
    return;
  }
  const [view, fd] = await Promise.all([api(`/api/projects/${pid}/view`), api(`/api/projects/${pid}/findings`)]);
  const R = state.results = {
    pid, view, findings: fd.findings, sheet: 0, off: new Set(["PASS"]), sev: "", q: "", sel: null,
    review: false, layers: { rooms: true, elements: true, findings: true },
  };
  $("#tab").innerHTML = `
    <div data-job-kind="check"></div><div data-job-kind="analyse"></div>
    <div class="results">
      <div class="card viewer" id="viewer"></div>
      <aside class="side">
        <div class="summary" id="summary"></div>
        <div class="filters">
          <input type="text" id="q" placeholder="Search findings, rules, rooms">
          <select id="sev"><option value="">All severities</option>${SEVERITIES.map((s) => `<option>${s}</option>`).join("")}</select>
        </div>
        <div class="card flist" id="flist"></div>
        <div class="downloads">
          <a class="btn sm" href="/api/projects/${pid}/files/report.pdf" target="_blank">Annotated PDF</a>
          <a class="btn sm" href="/api/projects/${pid}/files/report.html" target="_blank">HTML report</a>
          <a class="btn sm" href="/api/projects/${pid}/files/findings.csv">CSV</a>
          <a class="btn sm" href="/api/projects/${pid}/files/findings.json">JSON</a>
        </div>
      </aside>
    </div>`;
  $("#q").addEventListener("input", (e) => { R.q = e.target.value.toLowerCase(); renderFindings(); });
  $("#sev").addEventListener("change", (e) => { R.sev = e.target.value; renderFindings(); });
  renderSummary();
  renderViewer();
  renderFindings();
  if (active) { renderJob(active); watchJob(pid, active, () => route()); }
}

function sheetOf(R) { return R.view.sheets[R.sheet] || { findings: [], elements: [], rooms: [] }; }

function renderSummary() {
  const R = state.results;
  const c = {};
  for (const f of R.findings) c[f.verdict] = (c[f.verdict] || 0) + 1;
  $("#summary").innerHTML = VERDICTS.map((v) => `<button class="sbox v-${v} ${R.off.has(v) ? "off" : ""}" data-v="${v}" title="Show or hide">
    <div class="k">${VLABEL[v].toUpperCase()}</div><div class="v">${c[v] || 0}</div></button>`).join("");
  for (const b of $$(".sbox")) b.addEventListener("click", () => {
    R.off.has(b.dataset.v) ? R.off.delete(b.dataset.v) : R.off.add(b.dataset.v);
    renderSummary(); renderFindings();
  });
}

function visible(f) {
  const R = state.results;
  if (R.off.has(f.verdict)) return false;
  if (R.sev && f.severity !== R.sev) return false;
  if (R.q) {
    const hay = `${f.rule_id} ${f.message} ${f.detected || ""} ${f.required || ""} ${(f.source && f.source.clause) || ""}`.toLowerCase();
    if (!hay.includes(R.q)) return false;
  }
  return true;
}

function renderFindings() {
  const R = state.results;
  const order = { FAIL: 0, WARNING: 1, NOT_EVALUATED: 2, PASS: 3 };
  const sevo = { critical: 0, major: 1, minor: 2, info: 3 };
  const items = R.findings.map((f, n) => ({ f, n })).filter(({ f }) => visible(f))
    .sort((a, b) => order[a.f.verdict] - order[b.f.verdict] || sevo[a.f.severity] - sevo[b.f.severity] || a.n - b.n);
  $("#flist").innerHTML = items.length ? items.map(({ f, n }) => {
    const src = f.source || {};
    const dism = f.evidence && f.evidence.dismissed;
    return `<article class="fcard v-${f.verdict} ${R.sel === n ? "sel" : ""} ${dism ? "dismissed" : ""}" data-n="${n}">
      <header><span class="muted mono">#${n + 1}</span><span class="badge verdict">${VLABEL[f.verdict]}</span><span class="badge">${esc(f.tier)}</span><span class="rid">${esc(f.rule_id)}</span><span class="sev">${esc(f.severity)}</span></header>
      <p class="msg">${esc(f.message)}</p>
      ${f.detected || f.required ? `<p class="vals">detected <b>${esc(f.detected || "–")}</b> · required <b>${esc(f.required || "–")}</b></p>` : ""}
      ${src.clause ? `<p class="src">${esc(src.clause)}${src.doc ? ` · ${esc(String(src.doc).split("/").pop())}` : ""}</p>` : ""}
      ${dism ? `<p class="src">dismissed: ${esc(dism)}</p>` : ""}
      <div class="fact">${f.verdict !== "PASS" ? (dism ? `<button class="btn sm" data-act="restore">Restore</button>` : `<button class="btn sm" data-act="dismiss">Dismiss…</button>`) : ""}
        ${f.subject_ids.length ? `<button class="btn sm ok" data-act="confirm">Confirm elements</button>` : ""}</div>
    </article>`;
  }).join("") : `<div class="empty">No findings match the filters.</div>`;
  for (const card of $$(".fcard")) {
    card.addEventListener("click", (e) => {
      if (e.target.closest("[data-act]")) return;
      select(+card.dataset.n, true);
    });
    for (const b of $$("[data-act]", card)) b.addEventListener("click", () => findingAction(+card.dataset.n, b.dataset.act));
  }
  drawFindings();
}

async function findingAction(n, act) {
  const R = state.results;
  const f = R.findings[n];
  const fid = f.evidence.finding_id;
  const body = { recheck: true };
  if (act === "dismiss") {
    const reason = prompt("Why is this finding not an issue? (kept in the audit log)");
    if (!reason) return;
    body.dismiss = [`${fid}:${reason}`];
  } else if (act === "restore") {
    body.restore = [fid];
  } else if (act === "confirm") {
    body.confirm = [...new Set([...(f.evidence.deciding_ids || []), ...f.subject_ids])];
  }
  await triage(body);
}

async function triage(body) {
  const R = state.results;
  try {
    const r = await api(`/api/projects/${R.pid}/triage`, { method: "POST", json: body });
    toast("Saved · re-checking");
    renderJob(r.job);
    watchJob(R.pid, r.job, () => projectView(R.pid, "results"));
  } catch (e) { toast(e.message, true); }
}

/* ---------------------------------------------------------------- plan viewer */
function el(tag, attrs = {}, parent = null) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) e.setAttribute(k, v);
  if (parent) parent.append(e);
  return e;
}
const pts = (a) => a.map((p) => p.join(",")).join(" ");

function renderViewer() {
  const R = state.results;
  const s = sheetOf(R);
  const box = $("#viewer");
  const sheetSel = R.view.sheets.length > 1 ? `<select id="sheetsel">${R.view.sheets.map((x, i) => `<option value="${i}" ${i === R.sheet ? "selected" : ""}>${esc(x.id)}</option>`).join("")}</select>` : "";
  box.innerHTML = `
    <div class="vtools">
      <button class="btn sm" data-z="in" title="Zoom in">+</button><button class="btn sm" data-z="out" title="Zoom out">−</button><button class="btn sm" data-z="fit">Fit</button>
      <button class="btn sm ${R.layers.rooms ? "on" : ""}" data-l="rooms">Rooms</button>
      <button class="btn sm ${R.layers.elements ? "on" : ""}" data-l="elements">Elements</button>
      <button class="btn sm ${R.review ? "on" : ""}" data-l="review" title="Confirm or reject detected elements">Review elements</button>
      ${sheetSel}
    </div>
    <div class="legend card ${R.review ? "" : "hide"}"><div><i style="background:#2e7d32"></i>confirmed</div><div><i style="background:#ef6c00"></i>needs confirmation</div><div><i style="background:#c62828"></i>rejected</div><div class="muted">click an element</div></div>
    <div class="vinfo"><span class="badge">tier ${esc(s.tier)}</span><span class="badge">scale: ${esc(s.scale.method)}${s.scale.confidence != null ? ` (${Math.round(s.scale.confidence * 100)}%)` : ""}</span>
      <span class="badge">${s.rooms.length} rooms · ${s.elements.filter((e) => e.cls === "door").length} doors · ${s.elements.filter((e) => e.cls === "window").length} windows · ${s.elements.filter((e) => e.cls === "wall").length} walls</span></div>`;
  const svg = el("svg", { class: "plan" + (R.review ? " review" : ""), viewBox: `0 0 ${s.width} ${s.height}`, preserveAspectRatio: "xMidYMid meet" }, box);
  el("image", { href: `/api/projects/${R.pid}/sheets/${s.index}/backdrop.png?t=${Date.now()}`, width: s.width, height: s.height }, svg);
  // rooms are tinted; their names are already on the drawing, so label and area go in the tooltip
  const gRooms = el("g", { class: R.layers.rooms ? "" : "hide" }, svg);
  for (const r of s.rooms) {
    if (r.poly.length < 3) continue;
    const poly = el("polygon", { class: "ov-room", points: pts(r.poly), "data-room": r.id }, gRooms);
    el("title", {}, poly).textContent = `${r.label || "unlabelled room"}${r.area_m2 ? ` · ${r.area_m2.toFixed(2)} m²` : ""}`;
  }
  const gEls = el("g", { class: R.layers.elements || R.review ? "" : "hide" }, svg);
  for (const e of s.elements) {
    const cls = `ov-el ${e.cls} ${e.state}`;
    const node = e.line ? el("polyline", { class: cls, points: pts(e.line), "stroke-width": e.stroke, "data-el": e.id }, gEls)
      : el("polygon", { class: cls + " poly", points: pts(e.poly), "data-el": e.id }, gEls);
    node.addEventListener("click", (ev) => { ev.stopPropagation(); elementPopover(e, ev); });
  }
  el("g", { id: "gf" }, svg);
  R.svg = svg;
  R.vb = [0, 0, s.width, s.height];
  panZoom(svg);
  for (const b of $$("[data-z]", box)) b.addEventListener("click", () => zoomBy(b.dataset.z === "in" ? 0.7 : b.dataset.z === "out" ? 1.4 : 0));
  for (const b of $$("[data-l]", box)) b.addEventListener("click", () => {
    const l = b.dataset.l;
    if (l === "review") R.review = !R.review; else R.layers[l] = !R.layers[l];
    renderViewer(); drawFindings();
  });
  const ss = $("#sheetsel");
  if (ss) ss.addEventListener("change", () => { R.sheet = +ss.value; renderViewer(); renderFindings(); });
  svg.addEventListener("click", () => closePop());
}

function centroid(poly) {
  let a = 0, x = 0, y = 0;
  for (let i = 0; i < poly.length; i++) {
    const [x0, y0] = poly[i], [x1, y1] = poly[(i + 1) % poly.length];
    const c = x0 * y1 - x1 * y0;
    a += c; x += (x0 + x1) * c; y += (y0 + y1) * c;
  }
  if (Math.abs(a) < 1e-9) return poly[0];
  return [x / (3 * a), y / (3 * a)];
}

function drawFindings() {
  const R = state.results;
  const g = $("#gf");
  if (!g) return;
  g.innerHTML = "";
  const s = sheetOf(R);
  for (const geo of s.findings) {
    const f = R.findings[geo.n];
    if (!f || !visible(f) || f.verdict === "PASS") continue;
    const grp = el("g", { class: `ov-f v-${f.verdict} ${R.sel === geo.n ? "sel" : ""} ${R.sel !== null && R.sel !== geo.n ? "dim" : ""}`, "data-n": geo.n }, g);
    for (const poly of geo.polygons) el("polygon", { class: "geo", points: pts(poly) }, grp);
    for (const pl of geo.polylines) el("polyline", { class: "line", points: pts(pl) }, grp);
    for (const p of geo.points) el("circle", { class: "pt", cx: p[0], cy: p[1], r: 7 }, grp);
    if (geo.anchor) {
      const pin = el("g", { class: "pin" }, grp);
      el("circle", { cx: geo.anchor[0], cy: geo.anchor[1], r: 11 }, pin);
      el("text", { x: geo.anchor[0], y: geo.anchor[1] }, pin).textContent = String(geo.n + 1);
    }
    grp.addEventListener("click", (e) => { e.stopPropagation(); select(geo.n, false); });
  }
  // subjects of the selected finding
  for (const n of $$(".ov-el.hl", R.svg)) n.classList.remove("hl");
  if (R.sel !== null) {
    const f = R.findings[R.sel];
    const ids = new Set([...(f.subject_ids || []), ...((f.evidence && f.evidence.deciding_ids) || [])]);
    for (const n of $$("[data-el]", R.svg)) if (ids.has(n.dataset.el)) n.classList.add("hl");
  }
}

function select(n, zoom) {
  const R = state.results;
  R.sel = R.sel === n && !zoom ? null : n;
  for (const c of $$(".fcard")) c.classList.toggle("sel", +c.dataset.n === R.sel);
  drawFindings();
  if (R.sel === null) return;
  const card = $(`.fcard[data-n="${n}"]`);
  if (card && !zoom) card.scrollIntoView({ block: "nearest", behavior: "smooth" });
  if (zoom) zoomTo(n);
}

function zoomTo(n) {
  const R = state.results;
  const s = sheetOf(R);
  const geo = s.findings.find((g) => g.n === n);
  const f = R.findings[n];
  const xs = [], ys = [];
  const add = (p) => { xs.push(p[0]); ys.push(p[1]); };
  if (geo) {
    geo.polygons.flat().forEach(add); geo.polylines.flat().forEach(add); geo.points.forEach(add);
    if (geo.anchor) add(geo.anchor);
  }
  const ids = new Set(f.subject_ids || []);
  for (const e of s.elements) if (ids.has(e.id)) (e.line || e.poly).forEach(add);
  for (const r of s.rooms) if (ids.has(r.id)) r.poly.forEach(add);
  if (!xs.length) return;
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const w = Math.max(x1 - x0, s.width * 0.12), h = Math.max(y1 - y0, s.height * 0.12);
  setVB([(x0 + x1) / 2 - w * 0.8, (y0 + y1) / 2 - h * 0.8, w * 1.6, h * 1.6]);
}

function setVB(vb) {
  const R = state.results;
  R.vb = vb;
  R.svg.setAttribute("viewBox", vb.map((v) => v.toFixed(1)).join(" "));
}

function zoomBy(k, cx, cy) {
  const R = state.results;
  const s = sheetOf(R);
  if (!k) return setVB([0, 0, s.width, s.height]);
  const [x, y, w, h] = R.vb;
  cx = cx ?? x + w / 2; cy = cy ?? y + h / 2;
  const nw = Math.min(Math.max(w * k, s.width * 0.01), s.width * 4), nh = nw * h / w;
  setVB([cx - (cx - x) * nw / w, cy - (cy - y) * nh / h, nw, nh]);
}

function panZoom(svg) {
  const R = state.results;
  const toSvg = (ev) => {
    const r = svg.getBoundingClientRect();
    const [x, y, w, h] = R.vb;
    const s = Math.max(w / r.width, h / r.height);
    const ox = x + (w - r.width * s) / 2, oy = y + (h - r.height * s) / 2;
    return [ox + (ev.clientX - r.left) * s, oy + (ev.clientY - r.top) * s, s];
  };
  svg.addEventListener("wheel", (ev) => { ev.preventDefault(); const [x, y] = toSvg(ev); zoomBy(ev.deltaY < 0 ? 0.85 : 1.18, x, y); }, { passive: false });
  let drag = null;
  svg.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0) return;
    drag = { x: ev.clientX, y: ev.clientY, vb: [...R.vb], s: toSvg(ev)[2], moved: false };
  });
  window.addEventListener("pointermove", (ev) => {
    if (!drag) return;
    const dx = ev.clientX - drag.x, dy = ev.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return;
    drag.moved = true;
    svg.classList.add("drag");
    setVB([drag.vb[0] - dx * drag.s, drag.vb[1] - dy * drag.s, drag.vb[2], drag.vb[3]]);
  });
  window.addEventListener("pointerup", () => {
    if (drag && drag.moved) svg.addEventListener("click", (e) => e.stopPropagation(), { capture: true, once: true });
    drag = null; svg.classList.remove("drag");
  });
}

function closePop() { const p = $(".pop"); if (p) p.remove(); }

function elementPopover(e, ev) {
  closePop();
  const R = state.results;
  const box = $("#viewer");
  const r = box.getBoundingClientRect();
  const label = { auto: "accepted automatically (high confidence)", unconfirmed: "needs confirmation", confirmed: "confirmed by you", rejected: "rejected by you" }[e.state];
  const pop = document.createElement("div");
  pop.className = "card pop";
  pop.style.left = Math.min(ev.clientX - r.left + 12, r.width - 290) + "px";
  pop.style.top = Math.min(ev.clientY - r.top + 12, r.height - 180) + "px";
  pop.innerHTML = `<h3><span>${esc(e.cls)}${e.tag ? ` ${esc(e.tag)}` : ""}</span><span class="badge mono">${Math.round((e.confidence || 0) * 100)}%</span></h3>
    <div class="muted">${esc(label)}${e.width_m ? ` · ${e.cls === "wall" ? "thickness" : "width"} ${(+e.width_m).toFixed(2)} m` : ""}</div>
    <div class="mono muted" style="font-size:11px;margin-top:4px">${esc(e.id)}</div>
    <div class="actions">
      ${e.state !== "confirmed" ? `<button class="btn sm ok" data-t="confirm">Confirm</button>` : ""}
      ${e.state !== "rejected" ? `<button class="btn sm danger" data-t="reject">Reject</button>` : ""}
      ${e.state === "confirmed" || e.state === "rejected" ? `<button class="btn sm" data-t="unset">Undo</button>` : ""}
    </div>
    <p class="muted" style="font-size:12px;margin:8px 0 0">Confirmed elements can turn a warning into a firm result; rejected ones are removed before the check.</p>`;
  box.append(pop);
  pop.addEventListener("click", (x) => x.stopPropagation());
  for (const b of $$("[data-t]", pop)) b.addEventListener("click", () => { closePop(); triage({ [b.dataset.t]: [e.id], recheck: true }); });
}

/* ---------------------------------------------------------------- boot */
async function boot() {
  try {
    state.health = await api("/api/health");
    const l = state.health.llm;
    const pill = $("#llm");
    pill.className = "pill " + (l.available ? "on" : "off");
    pill.textContent = l.available ? `drafting model · ${l.model}` : `drafting model offline`;
  } catch (e) { toast("Server not reachable: " + e.message, true); }
  window.addEventListener("hashchange", route);
  route();
}
boot();
