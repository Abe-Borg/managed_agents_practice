const form = document.querySelector("#run-form");
const picker = document.querySelector("#files");
const dropZone = document.querySelector("#drop-zone");
const selected = document.querySelector("#selected-files");
const notice = document.querySelector("#notice");
const panels = document.querySelector("#panels");
const workspace = document.querySelector("#workspace");
const isolation = document.querySelector("#isolation");
let stream = null;
let runId = null;
let labels = [];
let finished = new Set();
let refreshTimer = null;
let latestEventId = 0;

function setNotice(message, isError = false) {
  notice.textContent = message;
  notice.classList.toggle("error", isError);
}

function showSelection() {
  selected.replaceChildren();
  for (const file of picker.files) {
    const chip = document.createElement("span");
    chip.className = "file-chip";
    chip.textContent = `${file.name} · ${(file.size / 1024).toFixed(1)} KB`;
    selected.append(chip);
  }
}

picker.addEventListener("change", showSelection);
for (const type of ["dragenter", "dragover"]) {
  dropZone.addEventListener(type, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
}
for (const type of ["dragleave", "drop"]) {
  dropZone.addEventListener(type, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  });
}
dropZone.addEventListener("drop", (event) => {
  picker.files = event.dataTransfer.files;
  showSelection();
});

function panelFor(label) {
  return [...panels.children].find((panel) => panel.dataset.label === label);
}

function createPanel(label) {
  const panel = document.createElement("article");
  panel.className = "panel";
  panel.dataset.label = label;
  panel.innerHTML = `
    <div class="panel-head"><div><span class="eyebrow">SESSION</span><h3></h3></div><span class="badge">queued</span></div>
    <div class="metrics"><span class="cost">Cost: —</span><span class="reason"></span></div>
    <ol class="log" aria-label="Live activity"></ol>
    <div class="result" hidden><div class="report"></div><div class="charts"></div></div>
    <form class="followup" hidden><label>Ask a follow-up</label><div><input name="question" maxlength="4000" required placeholder="What changed by region?"><button type="submit">Ask →</button></div></form>
    <form class="raise" hidden><label>Raise budget (cents)</label><div><input name="to_cents" type="number" min="1" max="500" required><button type="submit">Resume →</button></div></form>`;
  panel.querySelector("h3").textContent = label;
  panel.querySelector(".followup").addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = panel.querySelector('[name="question"]').value.trim();
    if (!question) return;
    await action(panel, "ask", { question });
  });
  panel.querySelector(".raise").addEventListener("submit", async (event) => {
    event.preventDefault();
    const to_cents = Number(panel.querySelector('[name="to_cents"]').value);
    await action(panel, "raise-budget", { to_cents });
  });
  panels.append(panel);
}

async function action(panel, name, payload) {
  const sessionId = panel.dataset.sessionId;
  if (!sessionId) return;
  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/${name}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    });
    if (!response.ok) throw new Error((await response.json()).detail || "Request failed");
    panel.querySelector(`.${name === "ask" ? "followup" : "raise"}`).hidden = true;
    panel.querySelector(".badge").textContent = "running";
    finished.delete(panel.dataset.label);
    connect();
  } catch (error) {
    setNotice(error.message, true);
  }
}

function appendEvent(event) {
  const panel = panelFor(event.label);
  if (!panel) return;
  if (event.session_id) panel.dataset.sessionId = event.session_id;
  const line = document.createElement("li");
  line.className = `log-${event.kind}`;
  line.textContent = `${event.tool_name ? `[${event.tool_name}] ` : ""}${event.text}`;
  panel.querySelector(".log").append(line);
  panel.querySelector(".log").scrollTop = panel.querySelector(".log").scrollHeight;
  if (event.list_cost_cents !== null) panel.querySelector(".cost").textContent = `Cost: ${event.list_cost_cents}¢`;
  if (event.kind === "done") {
    finished.add(event.label);
    panel.querySelector(".reason").textContent = event.stop_reason || "";
    panel.querySelector(".badge").textContent = event.stop_reason === "budget_reached" ? "paused" : "finished";
    if (finished.size === labels.length) refreshSummary();
  } else if (event.kind === "error") {
    panel.querySelector(".badge").textContent = "error";
  } else {
    panel.querySelector(".badge").textContent = "running";
  }
}

function connect() {
  if (!runId || stream) return;
  stream = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events?after=${latestEventId}`);
  stream.onmessage = (message) => {
    if (message.lastEventId) latestEventId = Number(message.lastEventId);
    try { appendEvent(JSON.parse(message.data)); } catch { setNotice("Could not read a progress event", true); }
  };
  stream.onerror = () => {
    if (finished.size === labels.length) {
      stream.close();
      stream = null;
    }
  };
}

async function refreshSummary() {
  if (!runId) return;
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
    if (response.status === 202) {
      clearTimeout(refreshTimer);
      refreshTimer = setTimeout(refreshSummary, 600);
      return;
    }
    if (!response.ok) throw new Error((await response.json()).detail || "Summary unavailable");
    const summary = await response.json();
    isolation.textContent = `Isolation ${summary.isolation_passed ? "✅ passed" : "❌ failed or incomplete"} · total ${summary.total_list_cost_cents}¢`;
    for (const item of summary.sessions) {
      const panel = panelFor(item.label);
      panel.dataset.sessionId = item.session_id || "";
      panel.querySelector(".badge").textContent = item.status;
      panel.querySelector(".reason").textContent = item.stop_reason;
      panel.querySelector(".cost").textContent = `Cost: ${item.list_cost_cents ?? "—"}¢`;
      panel.querySelector(".followup").hidden = item.status !== "completed";
      panel.querySelector(".raise").hidden = item.status !== "paused_budget";
      if (item.status === "completed" && item.artifacts_path) {
        const result = panel.querySelector(".result");
        result.hidden = false;
        const report = await fetch(`/api/runs/${encodeURIComponent(runId)}/${encodeURIComponent(item.label)}/report`);
        if (report.ok) {
          result.querySelector(".report").innerHTML = await report.text();
          const charts = result.querySelector(".charts");
          charts.replaceChildren(...result.querySelectorAll(".report img"));
        }
      }
    }
  } catch (error) { setNotice(error.message, true); }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const files = [...picker.files];
  if (!files.length || files.length > 5 || files.some((file) => file.size > 1024 * 1024 || !file.name.endsWith(".csv"))) {
    setNotice("Choose 1–5 .csv files, up to 1 MB each.", true);
    return;
  }
  if (stream) { stream.close(); stream = null; }
  const body = new FormData();
  files.forEach((file) => body.append("files", file));
  body.append("budget_cents", document.querySelector("#budget").value);
  document.querySelector("#start").disabled = true;
  setNotice("Starting sessions…");
  try {
    const response = await fetch("/api/runs", { method: "POST", body });
    if (!response.ok) throw new Error((await response.json()).detail || "Upload failed");
    const run = await response.json();
    runId = run.run_id;
    latestEventId = 0;
    labels = run.labels;
    finished = new Set();
    panels.replaceChildren();
    labels.forEach(createPanel);
    document.querySelector("#run-id").textContent = runId;
    workspace.hidden = false;
    isolation.textContent = "Isolation check pending";
    setNotice("Sessions started. Progress appears below.");
    connect();
  } catch (error) { setNotice(error.message, true); }
  finally { document.querySelector("#start").disabled = false; }
});
