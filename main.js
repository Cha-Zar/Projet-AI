let pyodide = null;
let pyEngine = null;

const MIN_ANSWERS = 5;
const MAX_DIAGNOSES = 5;

const appState = {
  screen: "loading", // loading | start | diagnose | results
  rulesCount: 0,
  symptomsCount: 0,
  categories: [],
  currentQ: null,
  answeredCount: 0,
  answers: {},
  livePreview: [],
  diagnoses: [],
  inconsistencies: [],
  showFacts: false,
  showRuleMgr: false,
};

// ── Initialisation Pyodide et chargement des modules ──────────────────────────
async function initPyodide() {
  const bar = document.querySelector(".loading-bar-fill");
  const log = document.querySelector(".loading-log");

  const setProgress = (pct, msg) => {
    bar.style.width = pct + "%";
    log.textContent = "> " + msg;
  };

  try {
    setProgress(10, "Chargement de Pyodide (WebAssembly)...");
    pyodide = await loadPyodide({
      indexURL: "https://cdn.jsdelivr.net/pyodide/v0.25.0/full/",
    });

    setProgress(30, "Chargement du moteur Python (engine.py)...");
    const pyResp = await fetch("./py/engine.py");
    const pyCode = await pyResp.text();
    await pyodide.runPythonAsync(pyCode);

    setProgress(50, "Chargement des règles...");
    const rulesResp = await fetch("./data/rules.json");
    const rulesJson = await rulesResp.text();
    const rulesResult = JSON.parse(
      pyodide.runPython(
        `load_rules('''${rulesJson
          .replace(/\\/g, "\\\\") // 🔥 IMPORTANT
          .replace(/'/g, "\\'")}''')`,
      ),
    );
    appState.rulesCount = rulesResult.rules_count;

    setProgress(75, "Chargement des questions et de l'arbre...");
    const qResp = await fetch("./data/questions.json");
    const qJson = await qResp.text();
    const qResult = JSON.parse(
      pyodide.runPython(`load_questions('''${qJson.replace(/'/g, "\\'")}''')`),
    );
    appState.symptomsCount = qResult.symptoms_count;
    appState.categories = qResult.categories;

    setProgress(95, "Finalisation...");
    await new Promise((r) => setTimeout(r, 300));
    setProgress(100, "Système prêt.");
    await new Promise((r) => setTimeout(r, 300));

    appState.screen = "start";
    render();
  } catch (e) {
    document.getElementById("app-root").innerHTML = `
      <div style="text-align:center;padding:60px;background:var(--surface);border:1px solid var(--border);border-radius:12px;">
        <div style="font-size:48px;margin-bottom:16px;">❌</div>
        <div style="font-family:var(--display);font-size:32px;letter-spacing:2px;color:var(--red);margin-bottom:12px;">ERREUR</div>
        <div style="font-family:var(--mono);font-size:11px;color:var(--text-muted);line-height:1.8;">
          ${e.message}<br><br>
          Vérifiez que les fichiers <strong>py/engine.py</strong>, <strong>data/rules.json</strong> et <strong>data/questions.json</strong> existent<br>
          et que vous utilisez un serveur local (pas file://).<br><br>
          <span style="color:var(--amber);">Astuce : python3 -m http.server 8000</span>
        </div>
      </div>`;
  }
}

// ── Rendu principal ───────────────────────────────────────────────────────────
function render() {
  const root = document.getElementById("app-root");
  updateBadges();
  if (appState.screen === "loading") {
    root.innerHTML = renderLoading();
    return;
  }
  if (appState.screen === "start") {
    root.innerHTML = renderStart();
    return;
  }
  if (appState.screen === "diagnose") {
    root.innerHTML = renderDiagnose();
    return;
  }
  if (appState.screen === "results") {
    root.innerHTML = renderResults();
    return;
  }
}

function updateBadges() {
  const h = document.getElementById("header-badge");
  const f = document.getElementById("footer-badge");
  if (h) h.textContent = `${appState.rulesCount} Règles`;
  if (f) f.textContent = `${appState.rulesCount} règles`;
}

function renderLoading() {
  return `
    <div id="pyodide-status">
      <div class="loading-logo">⚡ SYSDIAG</div>
      <div style="font-family:var(--mono);font-size:11px;color:var(--text-muted);margin-bottom:20px;letter-spacing:1px;">
        Chargement du moteur d'inférence via <strong style="color:#ffd43b;">Pyodide</strong>
      </div>
      <div class="loading-bar-track"><div class="loading-bar-fill"></div></div>
      <div class="loading-text">Initialisation...</div>
      <div class="loading-log"></div>
    </div>`;
}

function renderStart() {
  return `
    <div class="start-section">
      <div class="stats-strip">
        <div class="stat-cell"><div class="stat-num">${appState.rulesCount}</div><div class="stat-label">Règles expert</div></div>
        <div class="stat-cell"><div class="stat-num">${appState.symptomsCount}</div><div class="stat-label">Symptômes</div></div>
        <div class="stat-cell"><div class="stat-num">${appState.categories.length}</div><div class="stat-label">Catégories</div></div>
        <div class="stat-cell"><div class="stat-num">${MAX_DIAGNOSES}</div><div class="stat-label">Max résultats</div></div>
      </div>

      <div class="intro-card">
        <div class="intro-label">// À propos du système</div>
        <div class="intro-text">
          Ce système expert utilise le <strong>chaînage avant</strong> pour diagnostiquer les pannes informatiques.<br>
          Il pose des questions dans un <strong>ordre sémantiquement cohérent</strong> grâce à un arbre de dépendances.<br>
          Répondez à <strong>au moins ${MIN_ANSWERS} questions</strong> pour débloquer le diagnostic.
        </div>
        <div class="python-badge">
          <span class="python-snake">🐍</span>
          <span>Moteur Python natif exécuté via Pyodide (WASM).</span>
        </div>
      </div>

      <button class="btn-start" onclick="startDiagnosis()">▶ &nbsp; LANCER LE DIAGNOSTIC</button>

      <div class="section-toggle" onclick="toggleRuleMgr()">
        ⚙ &nbsp; Gestionnaire de règles dynamique &nbsp;
        <span style="color:var(--purple)">${appState.showRuleMgr ? "▲ masquer" : "▼ afficher"}</span>
      </div>
      ${appState.showRuleMgr ? renderRuleMgr() : ""}
    </div>`;
}

function renderRuleMgr() {
  let rulesList = "";
  try {
    const r = pyodide.runPython("json.dumps(_engine.rules[:20])");
    const rules = JSON.parse(r);
    rulesList = rules
      .map(
        (r) => `
      <div class="rule-row">
        <span class="rule-id">${r.id}</span>
        <span class="rule-cat">${r.category}</span>
        <span class="rule-conc">${r.conclusion}</span>
        <span class="rule-conf">${Math.round((r.confidence || 0) * 100)}%</span>
      </div>`,
      )
      .join("");
  } catch (e) {
    console.warn(e);
  }
  return `
    <div class="rule-mgr">
      <div class="rule-mgr-title">⚙ Gestion dynamique des règles</div>
      <div class="input-row">
        <input class="txt-input" id="del-id" placeholder="ID à supprimer (ex: R01)">
        <button class="btn-sm danger" onclick="deleteRule()">Supprimer</button>
      </div>
      <textarea class="txt-input" id="new-rule" rows="4" style="width:100%;margin-top:6px;" placeholder='{"id":"R99","category":"Custom","severity":"medium","conditions":{"symptom_id":true},"conclusion":"...","solution":"...","confidence":0.85}'></textarea>
      <button class="btn-sm" onclick="addRule()" style="margin-top:8px;">+ Ajouter règle</button>
      <div class="rules-list" style="margin-top:16px;">
        <div style="font-family:var(--mono);font-size:9px;color:var(--text-muted);letter-spacing:2px;text-transform:uppercase;margin-bottom:8px;">Règles actives (20 premières)</div>
        ${rulesList}
      </div>
    </div>`;
}

function renderDiagnose() {
  const q = appState.currentQ;
  if (!q) return "";

  const answered = appState.answeredCount;
  const progress = Math.min((answered / (answered + 10)) * 100, 95);
  const minReached = answered >= MIN_ANSWERS;

  const catColors = {
    Alimentation: "#f59e0b",
    Ecran: "#00e8ff",
    RAM: "#8b5cf6",
    Disque: "#10b981",
    Réseau: "#3b82f6",
    OS: "#8b5cf6",
    Démarrage: "#ef4444",
    Ventilation: "#06b6d4",
    Périphériques: "#ec4899",
    Son: "#f97316",
    Batterie: "#84cc16",
    Performance: "#eab308",
    Sécurité: "#dc2626",
  };
  const catColor = catColors[q.category] || "#00e8ff";

  // Live inference
  let liveHtml = "";
  if (appState.livePreview.length > 0 && answered >= 2) {
    const items = appState.livePreview
      .map((c) => {
        const pct = Math.round(c.confidence * 100);
        const color = pct >= 80 ? "#10b981" : pct >= 65 ? "#f59e0b" : "#ef4444";
        return `<div class="live-item">
        <span class="live-rule">${c.rule_id}</span>
        <span class="live-conclusion">${c.conclusion}</span>
        <span class="live-conf" style="color:${color};width:32px;text-align:right">${pct}%</span>
        <div class="conf-bar-mini"><div class="conf-fill-mini" style="width:${pct}%;background:${color}"></div></div>
      </div>`;
      })
      .join("");
    liveHtml = `
      <div class="live-inference">
        <div class="live-title"><div class="dot-blink"></div> Hypothèses en cours (chaînage avant)</div>
        ${items}
      </div>`;
  }

  // Facts panel
  let factsHtml = "";
  if (appState.showFacts && Object.keys(appState.answers).length > 0) {
    factsHtml = `<div class="facts-panel">
      <div class="facts-panel-title">// Base de faits — Session courante</div>
      ${Object.entries(appState.answers)
        .map(([sid, info]) => {
          const cls =
            info.val === "yes" ? "yes" : info.val === "no" ? "no" : "unknown";
          const icon =
            info.val === "yes" ? "OUI" : info.val === "no" ? "NON" : "?";
          return `<div class="fact-row">
          <div class="fact-dot ${cls}"></div>
          <span class="fact-text">${info.question}</span>
          <span class="fact-val">[${icon}]</span>
        </div>`;
        })
        .join("")}
    </div>`;
  }

  return `
    <div class="question-section">
      <div class="progress-header">
        <span class="progress-label">// Progression diagnostic</span>
        <div class="progress-stats">
          <span class="progress-num">${answered} réponse${answered > 1 ? "s" : ""}</span>
          ${answered > 0 ? `<span class="progress-impact">↑ ${appState.livePreview.length} règle${appState.livePreview.length !== 1 ? "s" : ""} activée${appState.livePreview.length !== 1 ? "s" : ""}</span>` : ""}
        </div>
      </div>
      <div class="progress-track"><div class="progress-fill" style="width:${progress}%"></div></div>

      ${liveHtml}

      <div class="category-trail">
        <div class="trail-dot" style="background:${catColor}"></div>
        <span>Catégorie</span>
        <span class="trail-sep">/</span>
        <span style="color:${catColor}">${q.category}</span>
      </div>

      <div class="question-card">
        <div class="q-num">// SYMPTÔME_${String(answered + 1).padStart(3, "0")}</div>
        <div class="q-text">${q.question}</div>
        <div class="answer-grid">
          <button class="answer-btn yes" onclick="answerQ('yes')">
            <span class="btn-icon">✓</span>
            <span class="btn-label">OUI</span>
          </button>
          <button class="answer-btn no" onclick="answerQ('no')">
            <span class="btn-icon">✗</span>
            <span class="btn-label">NON</span>
          </button>
          <button class="answer-btn unknown" onclick="answerQ('unknown')">
            <span class="btn-icon">?</span>
            <span class="btn-label">INCONNU</span>
          </button>
        </div>
      </div>

      ${!minReached ? `<div class="min-warning">ℹ Répondez encore <strong>${MIN_ANSWERS - answered}</strong> question(s) pour activer le diagnostic.</div>` : ""}

      <div class="nav-row">
        <button class="btn-nav" onclick="startOver()">↺ Recommencer</button>
        <button class="btn-diagnose ${!minReached ? "locked" : ""}" onclick="${minReached ? "runDiagnosis()" : "showNotif('Répondez à au moins " + MIN_ANSWERS + " questions d\\'abord','error')"}">
          Diagnostiquer →
        </button>
      </div>

      ${
        answered > 0
          ? `
        <div class="facts-toggle" onclick="toggleFacts()">
          📋 Faits collectés (${answered}) <span style="color:var(--purple)">${appState.showFacts ? "▲" : "▼"}</span>
        </div>
        ${factsHtml}`
          : ""
      }
    </div>`;
}

function renderResults() {
  const d = appState.diagnoses;
  const inc = appState.inconsistencies;
  const count = appState.answeredCount;

  const incPanel =
    inc.length > 0
      ? `
    <div class="inconsistency-panel">
      <div class="panel-title" style="color:var(--amber);">⚠️ Incohérences détectées</div>
      <ul class="panel-list">
        ${inc.map((i) => `<li>${i}</li>`).join("")}
      </ul>
    </div>`
      : "";

  if (d.length === 0) {
    return `<div class="results-section">
      <div class="results-header">
        <div class="results-eyebrow">// résultats diagnostic</div>
        <div class="results-title" style="color:var(--red);">AUCUN RÉSULTAT</div>
        <div class="results-meta">Basé sur ${count} réponses · ${appState.rulesCount} règles évaluées</div>
      </div>
      ${incPanel}
      <div class="no-results">
        <div class="no-results-icon">🔍</div>
        <div class="no-results-title">Pas de Correspondance</div>
        <div class="no-results-text">Les symptômes fournis ne correspondent à aucune règle dans la base de connaissances. Essayez de répondre à plus de questions ou de corriger des réponses contradictoires.</div>
        <div style="display:flex;gap:12px;justify-content:center;">
          <button class="btn-nav" onclick="goBack()">← Revenir</button>
          <button class="btn-nav" onclick="startOver()">↺ Recommencer</button>
        </div>
      </div>
    </div>`;
  }

  return `<div class="results-section">
    <div class="results-header">
      <div class="results-eyebrow">// résultats du moteur</div>
      <div class="results-title">${d.length} Diagnostic${d.length > 1 ? "s" : ""}</div>
      <div class="results-meta">Basé sur ${count} réponses · ${appState.rulesCount} règles évaluées${d.length === MAX_DIAGNOSES ? " · Top " + MAX_DIAGNOSES + " affichés" : ""}</div>
    </div>
    ${incPanel}
    ${d.map((diag, i) => renderDiagCard(diag, i)).join("")}
    <div style="margin-top:24px;">
      <button class="btn-nav" onclick="startOver()">↺ Nouveau diagnostic</button>
    </div>
    ${
      count > 0
        ? `
      <div class="facts-toggle" onclick="toggleFacts()">
        📋 Tous les faits collectés (${count}) <span style="color:var(--purple)">${appState.showFacts ? "▲" : "▼"}</span>
      </div>
      ${appState.showFacts ? renderFactsPanelFull() : ""}`
        : ""
    }
  </div>`;
}

function renderFactsPanelFull() {
  return `<div class="facts-panel">
    <div class="facts-panel-title">// Base de faits complète</div>
    ${Object.entries(appState.answers)
      .map(([sid, info]) => {
        const cls =
          info.val === "yes" ? "yes" : info.val === "no" ? "no" : "unknown";
        const icon =
          info.val === "yes" ? "OUI" : info.val === "no" ? "NON" : "?";
        return `<div class="fact-row">
        <div class="fact-dot ${cls}"></div>
        <span class="fact-text">${info.question}</span>
        <span class="fact-val">[${icon}]</span>
      </div>`;
      })
      .join("")}
  </div>`;
}

function renderDiagCard(diag, i) {
  const pct = Math.round(diag.confidence * 100);
  const cls = pct >= 85 ? "high" : pct >= 70 ? "med" : "low";
  const sevClass = `sev-${diag.severity || "medium"}`;
  const sevLabel =
    {
      critical: "🚨 CRITIQUE",
      high: "🔴 ÉLEVÉ",
      medium: "🟡 MOYEN",
      low: "🟢 FAIBLE",
    }[diag.severity] || "MOYEN";

  const condItems = Object.entries(diag.conditions)
    .map(([sid, expected]) => {
      const info = appState.answers[sid];
      const actual = info
        ? info.val === "yes"
          ? true
          : info.val === "no"
            ? false
            : null
        : undefined;
      const icon =
        actual === undefined ? "❓" : actual === expected ? "✅" : "❌";
      const qText = (info && info.question) || sid;
      return `<div class="cond-item">
      <span class="cond-status">${icon}</span>
      <span class="cond-text">${qText}</span>
      <span class="cond-expected">→ ${expected ? "OUI" : "NON"}</span>
    </div>`;
    })
    .join("");

  const sourcesHtml =
    diag.sources && diag.sources.length > 0
      ? `
    <div class="sources-block">
      <div class="sources-label">Sources de connaissances</div>
      ${diag.sources.map((s) => `<div class="source-item">${s}</div>`).join("")}
    </div>`
      : "";

  return `
    <div class="diag-card ${i === 0 ? "is-top" : ""}">
      <div class="diag-header" onclick="toggleCard('body-${i}','chev-${i}')">
        <div>
          <div class="diag-rank">
            ${i === 0 ? "🏆 DIAGNOSTIC PRINCIPAL" : `#${i + 1} DIAGNOSTIC`} &nbsp;·&nbsp; ${diag.rule_id}
            <span class="severity-chip ${sevClass}">${sevLabel}</span>
          </div>
          <div class="diag-conclusion">${diag.conclusion}</div>
          <div class="diag-category">Catégorie : ${diag.category}</div>
        </div>
        <div class="conf-display">
          <div class="conf-pct ${cls}">${pct}%</div>
          <div class="conf-word">Confiance</div>
          <div class="conf-bar"><div class="conf-fill fill-${cls}" style="width:${pct}%"></div></div>
          <span class="chevron ${i === 0 ? "open" : ""}" id="chev-${i}">▼</span>
        </div>
      </div>
      <div class="diag-body ${i === 0 ? "open" : ""}" id="body-${i}">
        <div class="solution-block">
          <div class="sol-label">💡 Solution recommandée</div>
          <div class="sol-text">${diag.solution}</div>
        </div>
        <div class="conditions-grid">
          <div class="cond-label">Conditions vérifiées</div>
          ${condItems}
        </div>
        ${sourcesHtml}
      </div>
    </div>`;
}

// ── Actions ─────────────────────────────────────────────────────────────────
async function startDiagnosis() {
  pyodide.runPython("reset_session()");
  appState.answers = {};
  appState.answeredCount = 0;
  appState.livePreview = [];
  appState.showFacts = false;
  appState.screen = "diagnose";

  const qStr = pyodide.runPython("get_next_question()");
  appState.currentQ = JSON.parse(qStr);
  render();
}

async function answerQ(val) {
  const q = appState.currentQ;
  if (!q) return;

  appState.answers[q.id] = { val, question: q.question };
  pyodide.runPython(`answer_question('${q.id}', '${val}')`);
  appState.answeredCount = parseInt(pyodide.runPython("get_answers_count()"));

  const previewStr = pyodide.runPython("get_live_preview()");
  appState.livePreview = JSON.parse(previewStr);

  const nextStr = pyodide.runPython("get_next_question()");
  const nextQ = JSON.parse(nextStr);

  if (!nextQ) {
    await runDiagnosis();
    return;
  }
  appState.currentQ = nextQ;
  render();
}

async function runDiagnosis() {
  const answered = appState.answeredCount;
  if (answered < MIN_ANSWERS) {
    showNotif(
      `Répondez à au moins ${MIN_ANSWERS} questions (${answered}/${MIN_ANSWERS})`,
      "error",
    );
    return;
  }

  const resultStr = pyodide.runPython("run_diagnosis()");
  const result = JSON.parse(resultStr);

  if (result.error) {
    showNotif(result.error, "error");
    return;
  }

  appState.diagnoses = result.diagnoses;
  appState.inconsistencies = result.inconsistencies;
  appState.answeredCount = result.answers_count;
  appState.screen = "results";
  render();
}

function startOver() {
  appState.screen = "start";
  appState.answers = {};
  appState.answeredCount = 0;
  appState.diagnoses = [];
  appState.livePreview = [];
  appState.showFacts = false;
  render();
}

function goBack() {
  appState.screen = "diagnose";
  render();
}

function toggleCard(bodyId, chevId) {
  const b = document.getElementById(bodyId);
  const c = document.getElementById(chevId);
  if (b) b.classList.toggle("open");
  if (c) c.classList.toggle("open");
}

function toggleFacts() {
  appState.showFacts = !appState.showFacts;
  render();
}

function toggleRuleMgr() {
  appState.showRuleMgr = !appState.showRuleMgr;
  render();
}

// ── Gestion dynamique des règles ─────────────────────────────────────────────
function addRule() {
  const input = document.getElementById("new-rule");
  if (!input) return;
  const raw = input.value.trim();
  try {
    JSON.parse(raw);
    const escaped = raw.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
    const res = JSON.parse(pyodide.runPython(`add_rule_py('${escaped}')`));
    if (res.error) {
      showNotif("Erreur: " + res.error, "error");
      return;
    }
    appState.rulesCount = res.count;
    input.value = "";
    showNotif("Règle ajoutée avec succès", "success");
    render();
  } catch (e) {
    showNotif("JSON invalide: " + e.message, "error");
  }
}

function deleteRule() {
  const input = document.getElementById("del-id");
  if (!input) return;
  const id = input.value.trim().toUpperCase();
  if (!id) return;
  const res = JSON.parse(pyodide.runPython(`delete_rule_py('${id}')`));
  if (res.error) {
    showNotif(res.error, "error");
    return;
  }
  appState.rulesCount = res.count;
  input.value = "";
  showNotif(`Règle ${id} supprimée`, "success");
  render();
}

function showNotif(msg, type) {
  const n = document.getElementById("notif");
  n.textContent = msg;
  n.className = `notif ${type} show`;
  setTimeout(() => n.classList.remove("show"), 3200);
}

// ── Démarrage ───────────────────────────────────────────────────────────────
render();
initPyodide();
