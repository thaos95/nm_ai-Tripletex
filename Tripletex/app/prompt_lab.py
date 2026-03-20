from fastapi.responses import HTMLResponse


PROMPT_LAB_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tripletex Prompt Lab</title>
  <style>
    :root {
      --bg: #f2efe8;
      --panel: rgba(255, 252, 247, 0.9);
      --ink: #1b1f1e;
      --muted: #5d6763;
      --line: rgba(27, 31, 30, 0.12);
      --accent: #0f766e;
      --accent-2: #b45309;
      --danger: #b91c1c;
      --ok: #166534;
      --shadow: 0 18px 50px rgba(33, 33, 24, 0.12);
      --radius: 22px;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.18), transparent 30%),
        radial-gradient(circle at right 20%, rgba(180, 83, 9, 0.14), transparent 26%),
        linear-gradient(180deg, #f7f3eb 0%, #ece5d8 100%);
      min-height: 100vh;
    }

    .shell {
      max-width: 1320px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }

    .hero {
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 20px;
      margin-bottom: 22px;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }

    .hero-copy {
      padding: 28px;
    }

    .hero-copy h1 {
      font-size: clamp(2.3rem, 4vw, 4.4rem);
      line-height: 0.95;
      margin: 0 0 12px;
      letter-spacing: -0.04em;
    }

    .hero-copy p {
      margin: 0;
      color: var(--muted);
      font-size: 1.05rem;
      line-height: 1.45;
      max-width: 54ch;
    }

    .hero-stats {
      padding: 24px;
      display: grid;
      gap: 14px;
      align-content: start;
    }

    .stat {
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px 16px;
      background: rgba(255,255,255,0.52);
    }

    .stat strong {
      display: block;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--muted);
      margin-bottom: 6px;
    }

    .stat span {
      font-size: 1.2rem;
    }

    .workspace {
      display: grid;
      grid-template-columns: minmax(340px, 460px) minmax(0, 1fr);
      gap: 20px;
    }

    .controls {
      padding: 22px;
      position: sticky;
      top: 20px;
      align-self: start;
    }

    label {
      display: block;
      font-size: 0.84rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin: 14px 0 8px;
    }

    textarea,
    input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px 15px;
      font: inherit;
      color: var(--ink);
      background: rgba(255,255,255,0.78);
    }

    textarea {
      min-height: 240px;
      resize: vertical;
      line-height: 1.4;
    }

    .button-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 18px;
    }

    button {
      border: 0;
      border-radius: 999px;
      padding: 12px 18px;
      font: inherit;
      cursor: pointer;
      transition: transform 120ms ease, opacity 120ms ease, background 120ms ease;
    }

    button:hover { transform: translateY(-1px); }
    button:disabled { opacity: 0.6; cursor: wait; transform: none; }

    .primary { background: var(--accent); color: white; }
    .secondary { background: #e8dfcf; color: var(--ink); }
    .ghost { background: transparent; border: 1px solid var(--line); color: var(--ink); }

    .preset-list {
      display: grid;
      gap: 8px;
      margin-top: 16px;
    }

    .preset-list button {
      text-align: left;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.55);
      padding: 12px 14px;
      color: var(--ink);
    }

    .results {
      display: grid;
      gap: 20px;
    }

    .result-card {
      padding: 20px;
    }

    .result-card h2 {
      margin: 0 0 12px;
      font-size: 1.15rem;
      letter-spacing: -0.02em;
    }

    .kv {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }

    .kv .chip {
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 10px 12px;
      background: rgba(255,255,255,0.5);
    }

    .chip strong {
      display: block;
      color: var(--muted);
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 4px;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.95rem;
    }

    th, td {
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 10px 8px;
      vertical-align: top;
    }

    th {
      color: var(--muted);
      font-size: 0.74rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    pre {
      margin: 0;
      padding: 14px;
      border-radius: 16px;
      background: #111827;
      color: #ecfdf5;
      overflow: auto;
      font-size: 0.84rem;
      line-height: 1.4;
    }

    .status {
      border-radius: 999px;
      display: inline-block;
      padding: 8px 12px;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.7);
    }

    .safe { color: var(--ok); }
    .risky { color: var(--accent-2); }
    .error { color: var(--danger); }

    .muted { color: var(--muted); }

    @media (max-width: 980px) {
      .hero, .workspace { grid-template-columns: 1fr; }
      .controls { position: static; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="panel hero-copy">
        <h1>Prompt Lab</h1>
        <p>Test naturlig språk mot Tripletex-agenten lokalt. Kjør en trygg inspect for å se parsed task og plan, eller kjør solve med sandbox-credentials for å treffe API-endepunktene.</p>
      </div>
      <div class="panel hero-stats">
        <div class="stat"><strong>Flow</strong><span>Prompt -> normalize -> classify -> validate -> plan -> execute</span></div>
        <div class="stat"><strong>Inspect</strong><span>Ingen Tripletex-credentials nødvendig</span></div>
        <div class="stat"><strong>Solve</strong><span>Bruk sandbox `base_url` og `session_token`</span></div>
      </div>
    </section>

    <section class="workspace">
      <div class="panel controls">
        <label for="prompt">Prompt</label>
        <textarea id="prompt" spellcheck="false">Opprett og send en faktura til kunden Brattli AS (org.nr 845762686) på 26450 kr eksklusiv MVA. Fakturaen gjelder Skylagring.</textarea>

        <label for="baseUrl">Tripletex Base URL</label>
        <input id="baseUrl" placeholder="https://tx-proxy.ainm.no/v2">

        <label for="sessionToken">Session Token</label>
        <input id="sessionToken" type="password" placeholder="Bare nødvendig for solve">

        <div class="button-row">
          <button class="primary" id="inspectBtn">Inspect Prompt</button>
          <button class="secondary" id="solveBtn">Solve Prompt</button>
          <button class="ghost" id="clearBtn">Clear Output</button>
        </div>

        <div class="preset-list">
          <button data-prompt='Opprett kunde Acme AS, acme@example.org. Opprett produktet "Consulting" for 1500 kr. Opprett og send en faktura.'>Multi-step invoice</button>
          <button data-prompt='Kan du vennligst opprette kunden Brattli AS med org.nr 845762686 og e-post post@brattli.no i Tripletex, takk.'>Noisy customer prompt</button>
          <button data-prompt='The customer Windmill Ltd (org no. 830362894) has an outstanding invoice for 32200 NOK excluding VAT for "System Development". Register full payment on this invoice.'>Payment prompt</button>
          <button data-prompt='Crie o projeto "Implementacao Rio" vinculado ao cliente Rio Azul Lda (org. no 827937223). O gerente de projeto e Goncalo Oliveira (goncalo.oliveira@example.org).'>Portuguese project</button>
        </div>
      </div>

      <div class="results">
        <div class="panel result-card">
          <h2>Run Summary</h2>
          <div class="kv" id="summaryGrid">
            <div class="chip"><strong>Status</strong><span class="muted">No run yet</span></div>
          </div>
        </div>

        <div class="panel result-card">
          <h2>Plan</h2>
          <table id="planTable">
            <thead><tr><th>Step</th><th>Resource</th><th>Action</th></tr></thead>
            <tbody><tr><td colspan="3" class="muted">No plan yet</td></tr></tbody>
          </table>
        </div>

        <div class="panel result-card">
          <h2>Parsed Task</h2>
          <pre id="parsedTaskBox">{}</pre>
        </div>

        <div class="panel result-card">
          <h2>Warnings And Errors</h2>
          <pre id="warningsBox">[]</pre>
        </div>

        <div class="panel result-card">
          <h2>Diagnosis</h2>
          <div class="kv" id="diagnosisGrid">
            <div class="chip"><strong>Category</strong><span class="muted">No run yet</span></div>
          </div>
          <pre id="diagnosisBox">{}</pre>
        </div>

        <div class="panel result-card">
          <h2>Raw Response</h2>
          <pre id="rawBox">{}</pre>
        </div>
      </div>
    </section>
  </div>

  <script>
    const promptEl = document.getElementById("prompt");
    const baseUrlEl = document.getElementById("baseUrl");
    const sessionTokenEl = document.getElementById("sessionToken");
    const inspectBtn = document.getElementById("inspectBtn");
    const solveBtn = document.getElementById("solveBtn");
    const clearBtn = document.getElementById("clearBtn");
    const parsedTaskBox = document.getElementById("parsedTaskBox");
    const warningsBox = document.getElementById("warningsBox");
    const rawBox = document.getElementById("rawBox");
    const summaryGrid = document.getElementById("summaryGrid");
    const diagnosisGrid = document.getElementById("diagnosisGrid");
    const diagnosisBox = document.getElementById("diagnosisBox");
    const planTableBody = document.querySelector("#planTable tbody");

    function setBusy(isBusy) {
      inspectBtn.disabled = isBusy;
      solveBtn.disabled = isBusy;
    }

    function setSummary(items) {
      summaryGrid.innerHTML = "";
      items.forEach(item => {
        const div = document.createElement("div");
        div.className = "chip";
        div.innerHTML = `<strong>${item.label}</strong><span class="${item.kind || ""}">${item.value}</span>`;
        summaryGrid.appendChild(div);
      });
    }

    function setPlan(plan) {
      if (!plan || !plan.length) {
        planTableBody.innerHTML = '<tr><td colspan="3" class="muted">No plan</td></tr>';
        return;
      }
      planTableBody.innerHTML = plan.map(step => `
        <tr>
          <td>${step.name}</td>
          <td>${step.resource}</td>
          <td>${step.action}</td>
        </tr>
      `).join("");
    }

    function classifyDetail(detail) {
      const text = String(detail || "").toLowerCase();
      if (!text) {
        return {
          category: "none",
          severity: "safe",
          summary: "No external error detail.",
          implication: "No diagnosis needed."
        };
      }
      if (text.includes("bankkontonummer") || text.includes("bank account")) {
        return {
          category: "validation_environment",
          severity: "risky",
          summary: "Tripletex company configuration blocks invoice creation.",
          implication: "Prompt parsing and workflow may still be correct. This is usually an external environment blocker, not a parser failure."
        };
      }
      if (text.includes("wrong endpoint path") || (text.includes("404") && text.includes("not found"))) {
        return {
          category: "wrong_endpoint",
          severity: "error",
          summary: "A Tripletex endpoint path is wrong.",
          implication: "This is a real code bug and should be fixed before submission."
        };
      }
      if (text.includes("401") || text.includes("unauthorized")) {
        return {
          category: "unauthorized",
          severity: "error",
          summary: "Tripletex authentication failed.",
          implication: "Check Basic Auth formatting and the provided session token."
        };
      }
      if (text.includes("missing") || text.includes("required")) {
        return {
          category: "validation_missing_fields",
          severity: "risky",
          summary: "Tripletex rejected the payload because required fields are missing.",
          implication: "Usually recoverable by adjusting payload shaping or prerequisites."
        };
      }
      if (text.includes("values\": []") || text.includes("\"values\":[]") || text.includes("no results")) {
        return {
          category: "no_results",
          severity: "risky",
          summary: "Resolver query returned no results.",
          implication: "The agent may need broader search or prerequisite creation."
        };
      }
      if (text.includes("422")) {
        return {
          category: "validation_generic",
          severity: "risky",
          summary: "Tripletex returned a generic validation error.",
          implication: "Read the raw detail carefully to decide if this is payload or environment."
        };
      }
      return {
        category: "unknown",
        severity: "error",
        summary: "Unclassified failure.",
        implication: "Inspect raw response and proxy logs."
      };
    }

    function setDiagnosis(detail, mode, status) {
      const diagnosis = classifyDetail(detail);
      diagnosisGrid.innerHTML = "";
      [
        { label: "Category", value: diagnosis.category, kind: diagnosis.severity },
        { label: "HTTP", value: String(status), kind: status >= 400 ? "error" : "safe" },
        { label: "Mode", value: mode },
      ].forEach(item => {
        const div = document.createElement("div");
        div.className = "chip";
        div.innerHTML = `<strong>${item.label}</strong><span class="${item.kind || ""}">${item.value}</span>`;
        diagnosisGrid.appendChild(div);
      });
      diagnosisBox.textContent = JSON.stringify(diagnosis, null, 2);
    }

    function setOutputs(data, mode, status) {
      const parsedTask = data.parsed_task || {};
      const warnings = {
        warnings: data.warnings || [],
        blocking_error: data.blocking_error || null,
        detail: data.detail || null
      };
      parsedTaskBox.textContent = JSON.stringify(parsedTask, null, 2);
      warningsBox.textContent = JSON.stringify(warnings, null, 2);
      rawBox.textContent = JSON.stringify(data, null, 2);
      setDiagnosis(data.detail, mode, status);
      setPlan(data.plan || []);
      setSummary([
        { label: "Mode", value: mode },
        { label: "HTTP", value: String(status), kind: status >= 400 ? "error" : "safe" },
        { label: "Task", value: parsedTask.task_type || data.status || "unknown" },
        { label: "Language", value: parsedTask.language_hint || "unknown" },
        { label: "Safety", value: data.safety || (status >= 400 ? "error" : "n/a"), kind: data.safety === "risky" ? "risky" : data.safety === "safe" ? "safe" : "" },
        { label: "Warnings", value: String((data.warnings || []).length) },
      ]);
    }

    async function run(mode) {
      const prompt = promptEl.value.trim();
      if (!prompt) {
        setSummary([{ label: "Status", value: "Prompt required", kind: "error" }]);
        return;
      }

      const endpoint = mode === "inspect" ? "/inspect" : "/solve";
      const payload = mode === "inspect"
        ? { prompt, files: [] }
        : {
            prompt,
            files: [],
            tripletex_credentials: {
              base_url: baseUrlEl.value.trim(),
              session_token: sessionTokenEl.value
            }
          };

      if (mode === "solve" && (!payload.tripletex_credentials.base_url || !payload.tripletex_credentials.session_token)) {
        setSummary([{ label: "Status", value: "Solve requires base URL and session token", kind: "error" }]);
        return;
      }

      setBusy(true);
      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await response.json().catch(() => ({}));
        setOutputs(data, mode, response.status);
      } catch (error) {
        setOutputs({ detail: String(error) }, mode, 0);
      } finally {
        setBusy(false);
      }
    }

    inspectBtn.addEventListener("click", () => run("inspect"));
    solveBtn.addEventListener("click", () => run("solve"));
    clearBtn.addEventListener("click", () => {
      parsedTaskBox.textContent = "{}";
      warningsBox.textContent = "[]";
      rawBox.textContent = "{}";
      diagnosisBox.textContent = "{}";
      diagnosisGrid.innerHTML = '<div class="chip"><strong>Category</strong><span class="muted">Cleared</span></div>';
      setPlan([]);
      setSummary([{ label: "Status", value: "Cleared" }]);
    });

    document.querySelectorAll("[data-prompt]").forEach(button => {
      button.addEventListener("click", () => {
        promptEl.value = button.dataset.prompt || "";
      });
    });
  </script>
</body>
</html>
"""


def prompt_lab_page() -> HTMLResponse:
    return HTMLResponse(PROMPT_LAB_HTML)
