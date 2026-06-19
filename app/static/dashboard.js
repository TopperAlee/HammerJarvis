const refreshMs = 30000;
const entityCatalogRefreshMs = 60000;
let speechOutputEnabled = true;
let isListening = false;
let dashboardRefreshInFlight = false;
let lastEntityCatalogRefresh = 0;

const elements = {};

function bindElements() {
  const ids = [
    "llmProvider",
    "voiceMiniStatus",
    "currentTime",
    "statusBadge",
    "errorPanel",
    "headline",
    "details",
    "emailCount",
    "eventCount",
    "warningTotal",
    "alertCount",
    "voiceCard",
    "voiceButton",
    "chatMicButton",
    "voiceStatus",
    "ecoflowSummary",
    "ecoflowOverall",
    "soc",
    "pvPower",
    "gridPower",
    "smartMeter",
    "batteryPower",
    "warningCounts",
    "warnings",
    "problemCounts",
    "problems",
    "haEntityCatalogStatus",
    "haEntityCatalogSync",
    "haEntitySearchInput",
    "haEntitySearchButton",
    "syncHaEntities",
    "haEntityResults",
    "emailStatus",
    "emailList",
    "todayEvents",
    "fileSearchInput",
    "fileSearchMode",
    "fileSearchButton",
    "fileContentSearchButton",
    "openLatestFile",
    "fileStatus",
    "fileSearchResults",
    "generatedFiles",
    "webResearchInput",
    "webResearchButton",
    "webResearchStatus",
    "webResearchAnswer",
    "webResearchSources",
    "watcherCounts",
    "performanceSummary",
    "slowestOperation",
    "ollamaBenchmarkStatus",
    "haCachePerformance",
    "refreshPerformance",
    "runOllamaBenchmark",
    "refreshSmartHomeActions",
    "discoverSmartHomeCandidates",
    "allowedSmartHomeActions",
    "smartHomeCandidates",
    "refreshSmartHomeAutoPolicy",
    "smartHomeAutoStatus",
    "smartHomeAutoDomains",
    "smartHomeBlockedDomains",
    "smartHomeTrustedSwitches",
    "refreshHaControlPolicy",
    "haControlStatus",
    "haControlCommandInput",
    "haControlPrepareButton",
    "haControlEntities",
    "refreshMemory",
    "memoryStatus",
    "memorySearchInput",
    "memorySearchButton",
    "memoryAddInput",
    "memoryAddButton",
    "memoryResults",
    "refreshKnowledge",
    "knowledgeStatus",
    "knowledgeSearchInput",
    "knowledgeSearchButton",
    "knowledgeIndexInput",
    "knowledgeIndexButton",
    "knowledgeResults",
    "knowledgeDocuments",
    "refreshActions",
    "pendingActions",
    "runWatchers",
    "refreshWatchers",
    "watcherAlerts",
    "speechToggle",
    "chatLog",
    "recognizedCommand",
    "jarvisAnswer",
    "commandInput",
    "sendCommand",
  ];

  for (const id of ids) {
    elements[id] = document.getElementById(id);
  }

  elements.quickCommands = document.querySelectorAll(".quick-command");
  elements.fileButtons = document.querySelectorAll(".file-button");
  elements.haEntityFilters = document.querySelectorAll(".ha-entity-filter");
}

async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function text(value, fallback = "-") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function formatWatts(value) {
  return value === null || value === undefined ? "-" : `${Math.round(Number(value))} W`;
}

function formatPercent(value) {
  return value === null || value === undefined ? "-" : `${Math.round(Number(value))} %`;
}

function setText(id, value) {
  if (elements[id]) {
    elements[id].textContent = value;
  }
}

function setStatus(overall) {
  const status = overall || "unknown";
  const label = {
    ok: "OK",
    warning: "Warnung",
    critical: "Kritisch",
    unknown: "Unbekannt",
  }[status] || "Unbekannt";
  elements.statusBadge.className = `status-badge status-${status}`;
  elements.statusBadge.textContent = label;
}

function setVoiceStatus(message, mode = "") {
  setText("voiceStatus", message);
  setText("voiceMiniStatus", mode === "active" ? "Hört zu" : "Bereit");
  elements.voiceStatus.className = `voice-status${mode ? ` ${mode}` : ""}`;
}

function clearList(target) {
  if (target) {
    target.innerHTML = "";
  }
}

function renderList(target, items, renderer, emptyText = "Keine Einträge.") {
  clearList(target);
  if (!target) {
    return;
  }
  if (!items || items.length === 0) {
    const item = document.createElement("li");
    item.textContent = emptyText;
    target.appendChild(item);
    return;
  }
  for (const value of items) {
    const item = document.createElement("li");
    const rendered = renderer(value);
    if (rendered instanceof Node) {
      item.appendChild(rendered);
    } else {
      item.textContent = rendered;
    }
    target.appendChild(item);
  }
}

function appendCode(parent, value) {
  if (!value) {
    return;
  }
  const code = document.createElement("code");
  code.textContent = ` ${value}`;
  parent.appendChild(code);
}

function renderWarning(warning) {
  const wrapper = document.createElement("span");
  wrapper.textContent = warning.message || "Unbekannte Warnung";
  appendCode(wrapper, warning.source_entity_id);
  return wrapper;
}

function renderProblem(entity) {
  const wrapper = document.createElement("span");
  appendCode(wrapper, entity.entity_id || "unknown");
  wrapper.append(` ${entity.state || ""}`);
  return wrapper;
}

function renderWatcherAlert(alert) {
  const wrapper = document.createElement("span");
  wrapper.textContent = `${alert.severity || "info"}: ${alert.title || "Hinweis"} - ${alert.message || ""}`;
  if (alert.recommended_action) {
    const action = document.createElement("div");
    action.className = "muted";
    action.textContent = alert.recommended_action;
    wrapper.appendChild(action);
  }
  return wrapper;
}

function renderAllowedSmartHomeAction(entity) {
  const wrapper = document.createElement("span");
  const name = entity.friendly_name || entity.entity_id || "Unbekannt";
  const actions = (entity.allowed_actions || []).join(", ");
  wrapper.textContent = `${name}: ${actions}`;
  appendCode(wrapper, entity.entity_id);
  return wrapper;
}

function renderSmartHomeCandidate(entity) {
  const wrapper = document.createElement("span");
  const name = entity.friendly_name || entity.entity_id || "Unbekannt";
  const actions = (entity.suggested_actions || []).map((action) => smartHomeActionLabel(action)).join(", ");
  wrapper.textContent = `${name}: ${actions || (entity.suggested_actions || []).join(", ")}`;
  appendCode(wrapper, entity.entity_id);
  return wrapper;
}

function renderSmartHomeAutoDomain(entry) {
  const wrapper = document.createElement("span");
  wrapper.textContent = `${entry.label}: ${entry.enabled ? "aktiv" : "inaktiv"} (${(entry.actions || []).join(", ") || "-"})`;
  return wrapper;
}

function renderTrustedSwitch(item) {
  const wrapper = document.createElement("span");
  wrapper.textContent = `${item.friendly_name || item.entity_id || "Switch"} · ${item.category || "trusted"}`;
  appendCode(wrapper, item.entity_id);
  return wrapper;
}

function renderHaEntity(entity) {
  const wrapper = document.createElement("span");
  const name = entity.friendly_name || entity.entity_id || "Unbekannt";
  const domain = entity.domain || "-";
  const state = entity.state || "-";
  const allowlisted = entity.is_allowlisted ? "freigegeben" : "nicht freigegeben";
  wrapper.textContent = `${name} · ${domain} · ${state} · ${allowlisted}`;
  appendCode(wrapper, entity.entity_id);
  if (entity.warning) {
    const warning = document.createElement("div");
    warning.className = "muted";
    warning.textContent = entity.warning;
    wrapper.appendChild(warning);
  }
  return wrapper;
}

function renderHaControlEntity(entity) {
  const wrapper = document.createElement("span");
  const actions = (entity.allowed_actions || []).join(", ");
  wrapper.textContent = `${entity.friendly_name || entity.entity_id || "Entity"} · ${entity.domain || "-"} · ${actions}`;
  appendCode(wrapper, entity.entity_id);
  return wrapper;
}

function renderMemory(memory) {
  const wrapper = document.createElement("span");
  wrapper.textContent = `${memory.key || "-"}: ${memory.value || "-"} (${memory.type || "fact"})`;
  if (memory.tags?.length) {
    const tags = document.createElement("div");
    tags.className = "muted";
    tags.textContent = memory.tags.join(", ");
    wrapper.appendChild(tags);
  }
  const deleteButton = document.createElement("button");
  deleteButton.className = "ghost-button small-action";
  deleteButton.type = "button";
  deleteButton.textContent = "Löschen";
  deleteButton.addEventListener("click", async () => {
    await fetch(`/assistant/memory/${memory.id}`, { method: "DELETE" });
    await refreshMemory();
  });
  wrapper.appendChild(deleteButton);
  return wrapper;
}

function renderKnowledgeResult(result) {
  const wrapper = document.createElement("span");
  wrapper.textContent = `${result.document_name || "-"} [Chunk ${result.chunk_index ?? "-"}]`;
  if (result.snippet) {
    const snippet = document.createElement("div");
    snippet.className = "muted";
    snippet.textContent = result.snippet;
    wrapper.appendChild(snippet);
  }
  return wrapper;
}

function renderKnowledgeDocument(document) {
  const wrapper = document.createElement("span");
  wrapper.textContent = `${document.name || "-"} · ${document.chunk_count ?? 0} Chunks`;
  appendCode(wrapper, document.path);
  return wrapper;
}

function smartHomeActionLabel(action) {
  const labels = {
    turn_on: "einschalten",
    turn_off: "ausschalten",
  };
  return labels[String(action || "")] || String(action || "");
}

function renderEmail(email) {
  const sender = email.sender || email.from || "Unbekannt";
  const subject = email.subject || "(ohne Betreff)";
  return `${sender}: ${subject}`;
}

function renderEvent(event) {
  const time = event.start_time || event.start || event.date || "";
  const title = event.title || event.summary || "Termin";
  return `${time ? `${time} - ` : ""}${title}`;
}

function renderFile(file) {
  const wrapper = document.createElement("span");
  wrapper.textContent = file.filename || file.name || "Datei";
  appendCode(wrapper, file.path);
  if (file.modified_at) {
    const meta = document.createElement("div");
    meta.className = "muted";
    meta.textContent = file.modified_at;
    wrapper.appendChild(meta);
  }
  if (file.snippets?.length) {
    const snippet = document.createElement("div");
    snippet.className = "muted";
    snippet.textContent = file.snippets.slice(0, 2).join(" ... ");
    wrapper.appendChild(snippet);
  }
  return wrapper;
}

function renderWebSource(source) {
  const wrapper = document.createElement("span");
  wrapper.textContent = source.title || source.source || "Quelle";
  appendCode(wrapper, source.url);
  return wrapper;
}

function riskLabel(risk) {
  const labels = {
    GREEN: "GRÜN",
    YELLOW: "GELB",
    RED: "ROT",
  };
  return labels[String(risk || "GREEN").toUpperCase()] || String(risk || "GREEN").toUpperCase();
}

function renderPendingAction(action) {
  const wrapper = document.createElement("div");
  wrapper.className = "action-card";
  const header = document.createElement("div");
  header.className = "action-row";
  const badge = document.createElement("span");
  const risk = String(action.risk || "GREEN").toLowerCase();
  badge.className = `risk-badge risk-${risk}`;
  badge.textContent = riskLabel(action.risk || "GREEN");
  const title = document.createElement("strong");
  title.textContent = action.title || "Aktion";
  header.append(badge, title);

  const description = document.createElement("div");
  description.className = "muted";
  description.textContent = action.description || "";

  const controls = document.createElement("div");
  controls.className = "action-row";
  if (action.risk !== "RED") {
    const executeButton = document.createElement("button");
    executeButton.className = "ghost-button";
    executeButton.type = "button";
    executeButton.textContent = action.risk === "YELLOW" ? "Bestätigen & ausführen" : "Ausführen";
    executeButton.textContent = action.risk === "YELLOW" ? "Bestätigen & ausführen" : "Ausführen";
    executeButton.addEventListener("click", async () => {
      const confirm = action.risk === "YELLOW";
      try {
        const response = await postJson(`/assistant/actions/${action.id}/execute`, { confirm });
        setText("jarvisAnswer", response.message || response.status || "Aktion verarbeitet.");
        await refreshActions();
      } catch (error) {
        setText("jarvisAnswer", "Aktion konnte nicht ausgeführt werden.");
      }
    });
    controls.appendChild(executeButton);
  }
  const rejectButton = document.createElement("button");
  rejectButton.className = "ghost-button";
  rejectButton.type = "button";
  rejectButton.textContent = "Ablehnen";
  rejectButton.addEventListener("click", async () => {
    try {
      await postJson(`/assistant/actions/${action.id}/reject`, {});
      await refreshActions();
    } catch (error) {
      setText("jarvisAnswer", "Aktion konnte nicht abgelehnt werden.");
    }
  });
  controls.appendChild(rejectButton);
  wrapper.append(header, description, controls);
  if (action.risk === "YELLOW") {
    const warning = document.createElement("div");
    warning.className = "muted";
    warning.textContent = "Diese Aktion erfordert ausdrückliche Bestätigung.";
    wrapper.appendChild(warning);
  }
  return wrapper;
}

function addChatMessage(role, message) {
  if (!elements.chatLog) {
    return;
  }
  const item = document.createElement("div");
  item.className = `chat-message ${role}`;
  const label = document.createElement("span");
  label.textContent = role === "user" ? "Du" : "Jarvis";
  const body = document.createElement("p");
  body.textContent = message;
  const time = document.createElement("time");
  time.textContent = new Date().toLocaleTimeString("de-DE", {
    hour: "2-digit",
    minute: "2-digit",
  });
  item.append(label, body, time);
  elements.chatLog.appendChild(item);
  elements.chatLog.scrollTop = elements.chatLog.scrollHeight;
}

function extractChatAnswer(response) {
  return response.answer || response.message || "Jarvis hat geantwortet, aber ohne lesbaren Antworttext.";
}

function isLegacyHomeAssistantCommand(message) {
  const normalized = message.toLowerCase();
  const assistantTerms = ["gmail", "email", "e-mail", "mail", "posteingang", "kalender", "termin", "timetree", "datei", "web", "recherche"];
  if (assistantTerms.some((term) => normalized.includes(term))) {
    return false;
  }
  return ["home assistant", "geräte", "geraete", "probleme", "offline", "unavailable", "unknown", "diagnose"].some((term) => normalized.includes(term));
}

async function sendChatMessage(textValue) {
  const message = text(textValue, "").trim();
  if (!message) {
    return;
  }
  setText("recognizedCommand", message);
  setText("jarvisAnswer", "Jarvis denkt...");
  setVoiceStatus("Befehl wird gesendet.");
  addChatMessage("user", message);

  try {
    let response;
    try {
      response = await postJson("/assistant/chat", { message, confirm: false });
    } catch (assistantError) {
      if (!isLegacyHomeAssistantCommand(message)) {
        const errorText = "Der neue Assistant-Endpunkt hat einen Fehler gemeldet. Bitte prüfe die Backend-Konsole.";
        setText("jarvisAnswer", errorText);
        setVoiceStatus(errorText, "error");
        addChatMessage("assistant", errorText);
        return;
      }
      response = await postJson("/chat", { message });
    }
    const answer = extractChatAnswer(response);
    setText("jarvisAnswer", answer);
    setVoiceStatus("Antwort empfangen.");
    addChatMessage("assistant", answer);
    if (speechOutputEnabled) {
      speakAnswer(answer);
    }
  } catch (error) {
    const errorText = "Verbindung zum Hammer-Jarvis-Backend fehlgeschlagen.";
    setText("jarvisAnswer", errorText);
    setVoiceStatus(errorText, "error");
    addChatMessage("assistant", errorText);
  }
}

function speakAnswer(answer) {
  if (!("speechSynthesis" in window)) {
    setVoiceStatus("Sprachausgabe wird von diesem Browser nicht unterstützt.", "error");
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(answer);
  const voices = window.speechSynthesis.getVoices();
  utterance.lang = "de-DE";
  utterance.rate = 1;
  utterance.voice = voices.find((voice) => voice.lang?.toLowerCase().startsWith("de")) || null;
  window.speechSynthesis.speak(utterance);
}

function startVoiceRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    setVoiceStatus("Sprachsteuerung nicht unterstützt.", "error");
    return;
  }
  if (isListening) {
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.lang = "de-DE";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.onstart = () => {
    isListening = true;
    elements.voiceCard.classList.add("listening");
    elements.voiceButton.classList.add("listening");
    setVoiceStatus("Ich höre zu...", "active");
  };
  recognition.onresult = (event) => {
    const transcript = event.results?.[0]?.[0]?.transcript || "";
    elements.commandInput.value = transcript;
    setText("recognizedCommand", transcript || "-");
    if (transcript) {
      sendChatMessage(transcript);
    }
  };
  recognition.onerror = (event) => {
    setVoiceStatus(`Spracherkennung fehlgeschlagen: ${event.error}`, "error");
  };
  recognition.onend = () => {
    isListening = false;
    elements.voiceCard.classList.remove("listening");
    elements.voiceButton.classList.remove("listening");
    if (!elements.voiceStatus.classList.contains("error")) {
      setVoiceStatus("Sprachsteuerung bereit.");
    }
  };
  recognition.start();
}

function runQuickCommand(command) {
  if (elements.commandInput) {
    elements.commandInput.value = command;
  }
  sendChatMessage(command);
}

async function refreshSystemStatus() {
  updateClock();
  try {
    const status = await fetchJson("/assistant/llm/status");
    const provider = status.provider || "regelbasiert";
    const model = status.model ? ` ${status.model}` : "";
    setText("llmProvider", `${provider}${model}`);
  } catch (error) {
    setText("llmProvider", "unbekannt");
  }
}

async function refreshEcoFlow() {
  const energy = await fetchJson("/ha/ecoflow/energy");
  const humanStatus = energy.human_status || {};
  setStatus(humanStatus.overall);
  setText("headline", humanStatus.headline || energy.summary || "Keine EcoFlow-Daten.");
  renderList(elements.details, humanStatus.details || [], (item) => item);
  setText("ecoflowSummary", energy.summary || humanStatus.headline || "Keine EcoFlow-Daten.");
  setText("ecoflowOverall", humanStatus.overall || "-");
  setText("soc", formatPercent(energy.soc_percent));
  setText("pvPower", formatWatts(energy.pv_power_w));
  setText("gridPower", formatWatts(energy.grid_power_w));
  setText("smartMeter", formatWatts(energy.smart_meter_w));
  setText("batteryPower", formatWatts(energy.battery_power_w));
  const criticalCount = energy.critical_count ?? 0;
  const severityWarnings = energy.warning_count_by_severity ?? 0;
  const infoCount = energy.info_count ?? 0;
  const totalWarnings = energy.warning_count ?? energy.warnings?.length ?? 0;
  setText("warningCounts", `Kritisch: ${criticalCount} | Warnung: ${severityWarnings} | Info: ${infoCount}`);
  setText("warningTotal", totalWarnings);
  renderList(elements.warnings, (energy.warnings || []).slice(0, 5), renderWarning);
}

async function refreshHomeAssistant() {
  const problems = await fetchJson("/ha/problems");
  const critical = problems.critical_count ?? 0;
  const warning = problems.warning_count ?? 0;
  const info = problems.informational_count ?? 0;
  setText("problemCounts", `Kritisch: ${critical} | Warnung: ${warning} | Info: ${info}`);
  const items = [...(problems.critical || []), ...(problems.warning || []), ...(problems.informational || [])].slice(0, 8);
  renderList(elements.problems, items, renderProblem);
}

async function refreshHaEntityCatalog() {
  try {
    const [status, unavailable, candidates] = await Promise.all([
      fetchJson("/assistant/home-assistant/entities/status"),
      fetchJson("/assistant/home-assistant/entities/unavailable"),
      fetchJson("/assistant/home-assistant/entities/actionable-candidates"),
    ]);
    setText(
      "haEntityCatalogStatus",
      `Entities: ${status.entity_count ?? 0} | Unavailable: ${unavailable.count ?? 0} | Kandidaten: ${candidates.count ?? 0}`,
    );
    const lastSync = status.last_sync ? `Letzter Sync: ${status.last_sync}` : "Noch kein Sync.";
    setText("haEntityCatalogSync", `${lastSync} Quelle: ${status.source || "none"}`);
    renderList(elements.haEntityResults, (candidates.entities || []).slice(0, 8), renderHaEntity, "Keine Kandidaten geladen.");
  } catch (error) {
    setText("haEntityCatalogSync", "Entity-Katalog konnte nicht geladen werden.");
  }
}

async function syncHaEntities() {
  setText("haEntityCatalogSync", "Home Assistant Entities werden synchronisiert...");
  try {
    const response = await postJson("/assistant/home-assistant/entities/sync", { force: true });
    setText("haEntityCatalogSync", `Synchronisiert: ${response.entity_count ?? 0} Entities. Quelle: ${response.source || "-"}`);
    await refreshHaEntityCatalog();
  } catch (error) {
    setText("haEntityCatalogSync", "Synchronisierung fehlgeschlagen.");
  }
}

async function searchHaEntities() {
  const query = text(elements.haEntitySearchInput.value, "").trim();
  if (!query) {
    return;
  }
  try {
    const response = await fetchJson(`/assistant/home-assistant/entities/search?q=${encodeURIComponent(query)}`);
    renderList(elements.haEntityResults, response.entities || [], renderHaEntity, "Keine passenden Entities.");
  } catch (error) {
    setText("haEntityCatalogSync", "Entity-Suche fehlgeschlagen.");
  }
}

async function filterHaEntities(filter) {
  const endpoints = {
    unavailable: "/assistant/home-assistant/entities/unavailable",
    candidates: "/assistant/home-assistant/entities/actionable-candidates",
    light: "/assistant/home-assistant/entities?domain=light",
    switch: "/assistant/home-assistant/entities?domain=switch",
    scene: "/assistant/home-assistant/entities?domain=scene",
  };
  try {
    const response = await fetchJson(endpoints[filter] || "/assistant/home-assistant/entities");
    renderList(elements.haEntityResults, response.entities || [], renderHaEntity, "Keine passenden Entities.");
  } catch (error) {
    setText("haEntityCatalogSync", "Filter konnte nicht geladen werden.");
  }
}

async function refreshAlerts() {
  const watcherData = await fetchJson("/assistant/watchers/alerts");
  const alerts = watcherData.alerts || [];
  setText("watcherCounts", `Aktive Hinweise: ${alerts.length}`);
  setText("alertCount", alerts.length);
  renderList(elements.watcherAlerts, alerts.slice(0, 7), renderWatcherAlert);
}

async function refreshPerformance() {
  try {
    const [status, haStatus] = await Promise.all([
      fetchJson("/assistant/performance/status"),
      fetchJson("/assistant/home-assistant/entities/status"),
    ]);
    const summary = status.summary || {};
    setText("performanceSummary", `Operationen: ${summary.count ?? 0} | Fehler: ${summary.errors ?? 0}`);
    const slowest = (status.slowest_operations || [])[0];
    if (slowest) {
      setText("slowestOperation", `Langsamste Operation: ${slowest.name || "-"} | ${slowest.duration_ms ?? 0} ms`);
    } else {
      setText("slowestOperation", "Langsamste Operation: -");
    }
    setText(
      "haCachePerformance",
      `HA Entity Cache: ${haStatus.entity_count ?? 0} Entities | Alter: ${haStatus.cache_age_seconds ?? "-"} s | Sync: ${haStatus.last_sync || "-"}`,
    );
  } catch (error) {
    setText("performanceSummary", "Performance-Daten konnten nicht geladen werden.");
  }
}

async function runOllamaBenchmark() {
  setText("ollamaBenchmarkStatus", "Ollama-Benchmark läuft...");
  try {
    const response = await fetchJson("/assistant/ollama/benchmark/native?models=fast");
    const benchmark = (response.benchmarks || [])[0];
    if (!benchmark) {
      setText("ollamaBenchmarkStatus", response.message || "Kein installiertes Fast-Modell gefunden.");
      return;
    }
    const warning = benchmark.warning ? ` | ${benchmark.warning}` : "";
    const cold = benchmark.cold_start_likely ? " | Cold Start wahrscheinlich" : "";
    setText(
      "ollamaBenchmarkStatus",
      `${benchmark.model || "Ollama"}: HTTP ${benchmark.measured_http_duration_ms ?? "-"} ms | Ollama ${benchmark.ollama_total_duration_ms ?? benchmark.total_duration_ms ?? "-"} ms | Load ${benchmark.load_duration_ms ?? "-"} ms${cold}${warning}`,
    );
    await refreshPerformance();
  } catch (error) {
    setText("ollamaBenchmarkStatus", "Ollama-Benchmark fehlgeschlagen.");
  }
}

async function refreshActions() {
  try {
    const data = await fetchJson("/assistant/actions/pending");
    renderList(elements.pendingActions, data.actions || [], renderPendingAction, "Keine ausstehenden Aktionen.");
  } catch (error) {
    renderList(elements.pendingActions, [], renderPendingAction, "Aktionen konnten nicht geladen werden.");
  }
}

async function refreshSmartHomeActions() {
  try {
    const data = await fetchJson("/assistant/home-assistant/actions/allowed");
    const items = [...(data.allowed_entities || []), ...(data.allowed_scenes || [])];
    renderList(elements.allowedSmartHomeActions, items, renderAllowedSmartHomeAction, "Keine Smart-Home-Aktionen freigegeben.");
  } catch (error) {
    renderList(elements.allowedSmartHomeActions, [], renderAllowedSmartHomeAction, "Freigaben konnten nicht geladen werden.");
  }
}

async function refreshSmartHomeAutoPolicy() {
  try {
    const data = await fetchJson("/assistant/home-assistant/control/auto-policy");
    const active = data.auto_execute_enabled && data.control_mode === "trusted_auto";
    setText("smartHomeAutoStatus", `Auto-Ausführung: ${active ? "aktiv" : "inaktiv"} · Modus: ${data.control_mode || "-"}`);
    const domains = Object.entries(data.auto_execute_domains || {}).map(([key, value]) => ({
      label: key,
      enabled: Boolean(value.enabled),
      actions: value.actions || [],
    }));
    renderList(elements.smartHomeAutoDomains, domains, renderSmartHomeAutoDomain, "Keine Auto-Domains konfiguriert.");
    renderList(elements.smartHomeBlockedDomains, data.blocked_domains || [], (value) => String(value), "Keine blockierten Domains konfiguriert.");
    renderList(elements.smartHomeTrustedSwitches, data.trusted_switches || [], renderTrustedSwitch, "Keine vertrauenswürdigen Switches konfiguriert.");
  } catch (error) {
    setText("smartHomeAutoStatus", "Auto-Policy konnte nicht geladen werden.");
  }
}

async function discoverSmartHomeCandidates() {
  try {
    const data = await fetchJson("/assistant/home-assistant/actions/candidates");
    renderList(elements.smartHomeCandidates, data.candidates || [], renderSmartHomeCandidate, "Keine sicheren Kandidaten gefunden.");
  } catch (error) {
    renderList(elements.smartHomeCandidates, [], renderSmartHomeCandidate, "Kandidaten konnten nicht geladen werden.");
  }
}

async function refreshHaControlPolicy() {
  try {
    const data = await fetchJson("/assistant/home-assistant/control/entities");
    setText("haControlStatus", `${data.count ?? 0} kontrollierbare Entities laut Policy.`);
    renderList(elements.haControlEntities, (data.entities || []).slice(0, 8), renderHaControlEntity, "Keine kontrollierbaren Entities.");
  } catch (error) {
    setText("haControlStatus", "Control Policy konnte nicht geladen werden.");
  }
}

async function refreshMemory() {
  try {
    const data = await fetchJson("/assistant/memory");
    setText("memoryStatus", `${data.count ?? 0} lokale Erinnerung(en).`);
    renderList(elements.memoryResults, (data.memories || []).slice(-8).reverse(), renderMemory, "Keine Erinnerungen gespeichert.");
  } catch (error) {
    setText("memoryStatus", "Gedächtnis konnte nicht geladen werden.");
  }
}

async function searchMemory() {
  const query = text(elements.memorySearchInput.value, "").trim();
  if (!query) {
    return refreshMemory();
  }
  try {
    const data = await fetchJson(`/assistant/memory/search?q=${encodeURIComponent(query)}`);
    setText("memoryStatus", `${data.count ?? 0} Treffer.`);
    renderList(elements.memoryResults, data.memories || [], renderMemory, "Keine passenden Erinnerungen.");
  } catch (error) {
    setText("memoryStatus", "Gedächtnissuche fehlgeschlagen.");
  }
}

async function addMemory() {
  const value = text(elements.memoryAddInput.value, "").trim();
  if (!value) {
    return;
  }
  await sendChatMessage(`Merke dir, dass ${value}`);
  elements.memoryAddInput.value = "";
  await refreshMemory();
}

async function refreshKnowledge() {
  try {
    const status = await fetchJson("/assistant/knowledge/status");
    const documents = await fetchJson("/assistant/knowledge/documents");
    setText("knowledgeStatus", `${status.document_count ?? 0} Dokument(e), ${status.chunk_count ?? 0} Chunk(s).`);
    renderList(elements.knowledgeDocuments, documents.documents || [], renderKnowledgeDocument, "Keine Dokumente indexiert.");
  } catch (error) {
    setText("knowledgeStatus", "Wissensspeicher konnte nicht geladen werden.");
  }
}

async function searchKnowledge() {
  const query = text(elements.knowledgeSearchInput.value, "").trim();
  if (!query) {
    return refreshKnowledge();
  }
  try {
    const data = await fetchJson(`/assistant/knowledge/search?q=${encodeURIComponent(query)}`);
    setText("knowledgeStatus", `${data.count ?? 0} Wissenstreffer.`);
    renderList(elements.knowledgeResults, data.results || [], renderKnowledgeResult, "Keine passenden Wissens-Chunks.");
  } catch (error) {
    setText("knowledgeStatus", "Wissenssuche fehlgeschlagen.");
  }
}

async function indexKnowledgePath() {
  const path = text(elements.knowledgeIndexInput.value, "").trim();
  if (!path) {
    return;
  }
  try {
    const data = await postJson("/assistant/knowledge/index", { path, recursive: true });
    setText("knowledgeStatus", data.message || `${data.count ?? 0} Datei(en) indexiert.`);
    elements.knowledgeIndexInput.value = "";
    await refreshKnowledge();
  } catch (error) {
    setText("knowledgeStatus", "Indexierung fehlgeschlagen.");
  }
}

async function prepareHaControlCommand() {
  const command = text(elements.haControlCommandInput.value, "").trim();
  if (!command) {
    return;
  }
  await sendChatMessage(command);
  await refreshActions();
}

async function refreshRecentFiles() {
  let filesData;
  try {
    filesData = await fetchJson("/assistant/files/recent");
  } catch (error) {
    filesData = await fetchJson("/assistant/files/exports");
  }
  renderList(elements.generatedFiles, (filesData.files || []).slice(0, 5), renderFile, "Keine aktuellen Dateien.");
}

async function refreshEmail() {
  try {
    const data = await fetchJson("/assistant/email/search?q=is%3Aunread%20newer_than%3A30d");
    const count = data.total_email_count ?? data.count ?? 0;
    setText("emailCount", count);
    setText("emailStatus", data.message || `${count} Nachrichten gefunden.`);
    const emails = collectEmails(data).slice(0, 5);
    renderList(elements.emailList, emails, renderEmail, "Keine ungelesenen Nachrichten.");
  } catch (error) {
    setText("emailCount", "-");
    setText("emailStatus", "Gmail konnte nicht geprüft werden.");
    renderList(elements.emailList, [], renderEmail);
  }
}

function collectEmails(data) {
  if (Array.isArray(data.emails)) {
    return data.emails;
  }
  const emails = [];
  for (const provider of data.providers || data.results || []) {
    if (Array.isArray(provider.emails)) {
      emails.push(...provider.emails);
    }
  }
  return emails;
}

async function refreshTimeTree() {
  try {
    const data = await fetchJson("/assistant/timetree/today");
    const events = data.events || data.appointments || [];
    setText("eventCount", events.length);
    renderList(elements.todayEvents, events.slice(0, 5), renderEvent, "Keine Termine.");
  } catch (error) {
    setText("eventCount", "-");
    renderList(elements.todayEvents, [], renderEvent, "TimeTree nicht erreichbar.");
  }
}

async function searchFiles() {
  const query = text(elements.fileSearchInput.value, "").trim();
  if (!query) {
    return;
  }
  const contentMode = elements.fileSearchMode.value === "content";
  const endpoint = contentMode ? "/assistant/files/content-search" : "/assistant/files/search";
  setText("fileStatus", contentMode ? "Dateiinhalte werden durchsucht..." : "Dateien werden gesucht...");
  try {
    const response = await fetchJson(`${endpoint}?q=${encodeURIComponent(query)}`);
    setText("fileStatus", response.message || "Suche abgeschlossen.");
    renderList(elements.fileSearchResults, response.files || [], renderFile, "Keine passenden Dateien.");
  } catch (error) {
    setText("fileStatus", "Dateisuche fehlgeschlagen.");
  }
}

async function runWebResearch() {
  const query = text(elements.webResearchInput.value, "").trim();
  if (!query) {
    return;
  }
  setText("webResearchStatus", "Recherche läuft...");
  setText("webResearchAnswer", "-");
  renderList(elements.webResearchSources, [], renderWebSource);
  try {
    const response = await postJson("/assistant/web/research", { query });
    setText("webResearchStatus", response.message || "Recherche abgeschlossen.");
    setText("webResearchAnswer", response.answer || response.summary || response.message || "Keine Zusammenfassung verfügbar.");
    renderList(elements.webResearchSources, response.sources || [], renderWebSource, "Keine Quellen.");
  } catch (error) {
    setText("webResearchStatus", "Internetrecherche fehlgeschlagen.");
  }
}

async function refreshDashboard() {
  if (dashboardRefreshInFlight) {
    return;
  }
  dashboardRefreshInFlight = true;
  try {
    elements.errorPanel.hidden = true;
    const tasks = [
      refreshSystemStatus(),
      refreshEcoFlow(),
      refreshHomeAssistant(),
      refreshAlerts(),
      refreshRecentFiles(),
      refreshEmail(),
      refreshTimeTree(),
      refreshSmartHomeActions(),
      refreshSmartHomeAutoPolicy(),
      refreshHaControlPolicy(),
      refreshMemory(),
      refreshKnowledge(),
      refreshActions(),
      refreshPerformance(),
    ];
    const now = Date.now();
    if (now - lastEntityCatalogRefresh >= entityCatalogRefreshMs) {
      lastEntityCatalogRefresh = now;
      tasks.push(refreshHaEntityCatalog());
    }
    await Promise.all(tasks);
  } catch (error) {
    elements.errorPanel.hidden = false;
    setStatus("critical");
  } finally {
    dashboardRefreshInFlight = false;
  }
}

function updateClock() {
  setText("currentTime", new Date().toLocaleTimeString("de-DE"));
}

function wireEvents() {
  elements.sendCommand.addEventListener("click", () => sendChatMessage(elements.commandInput.value));
  elements.commandInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      sendChatMessage(elements.commandInput.value);
    }
  });
  elements.voiceButton.addEventListener("click", startVoiceRecognition);
  elements.chatMicButton.addEventListener("click", startVoiceRecognition);
  elements.speechToggle.addEventListener("click", () => {
    speechOutputEnabled = !speechOutputEnabled;
    if (!speechOutputEnabled && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    elements.speechToggle.textContent = speechOutputEnabled ? "Sprachausgabe: Ein" : "Sprachausgabe: Aus";
    setVoiceStatus(speechOutputEnabled ? "Sprachausgabe ist eingeschaltet." : "Sprachausgabe ist ausgeschaltet.");
  });
  for (const button of elements.quickCommands) {
    button.addEventListener("click", () => runQuickCommand(button.dataset.command || button.textContent));
  }
  for (const button of elements.fileButtons) {
    button.addEventListener("click", () => runQuickCommand(button.dataset.command || "erstelle eine Excel fuer Ausgaben"));
  }
  elements.fileSearchButton.addEventListener("click", searchFiles);
  elements.fileContentSearchButton.addEventListener("click", () => {
    elements.fileSearchMode.value = "content";
    searchFiles();
  });
  elements.fileSearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      searchFiles();
    }
  });
  elements.openLatestFile.addEventListener("click", async () => {
    try {
      const response = await postJson("/assistant/files/open-latest", {});
      setText("fileStatus", response.message || "Letzte Datei wurde geöffnet.");
    } catch (error) {
      setText("fileStatus", "Letzte Datei konnte nicht geöffnet werden.");
    }
  });
  elements.webResearchButton.addEventListener("click", runWebResearch);
  elements.webResearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      runWebResearch();
    }
  });
  elements.refreshWatchers.addEventListener("click", refreshAlerts);
  elements.refreshPerformance.addEventListener("click", refreshPerformance);
  elements.runOllamaBenchmark.addEventListener("click", runOllamaBenchmark);
  elements.syncHaEntities.addEventListener("click", syncHaEntities);
  elements.haEntitySearchButton.addEventListener("click", searchHaEntities);
  elements.haEntitySearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      searchHaEntities();
    }
  });
  for (const button of elements.haEntityFilters) {
    button.addEventListener("click", () => filterHaEntities(button.dataset.filter));
  }
  elements.refreshSmartHomeActions.addEventListener("click", refreshSmartHomeActions);
  elements.discoverSmartHomeCandidates.addEventListener("click", discoverSmartHomeCandidates);
  elements.refreshSmartHomeAutoPolicy.addEventListener("click", refreshSmartHomeAutoPolicy);
  elements.refreshHaControlPolicy.addEventListener("click", refreshHaControlPolicy);
  elements.haControlPrepareButton.addEventListener("click", prepareHaControlCommand);
  elements.haControlCommandInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      prepareHaControlCommand();
    }
  });
  elements.refreshMemory.addEventListener("click", refreshMemory);
  elements.memorySearchButton.addEventListener("click", searchMemory);
  elements.memoryAddButton.addEventListener("click", addMemory);
  elements.memorySearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      searchMemory();
    }
  });
  elements.memoryAddInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      addMemory();
    }
  });
  elements.refreshKnowledge.addEventListener("click", refreshKnowledge);
  elements.knowledgeSearchButton.addEventListener("click", searchKnowledge);
  elements.knowledgeIndexButton.addEventListener("click", indexKnowledgePath);
  elements.knowledgeSearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      searchKnowledge();
    }
  });
  elements.knowledgeIndexInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      indexKnowledgePath();
    }
  });
  elements.refreshActions.addEventListener("click", refreshActions);
  elements.runWatchers.addEventListener("click", async () => {
    try {
      await postJson("/assistant/watchers/run", {});
      await refreshAlerts();
    } catch (error) {
      elements.errorPanel.hidden = false;
    }
  });
}

function initializeVoiceAvailability() {
  if (!("speechSynthesis" in window)) {
    setVoiceStatus("Sprachausgabe wird von diesem Browser nicht unterstützt.", "error");
  }
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    setVoiceStatus("Sprachsteuerung nicht unterstützt.", "error");
  }
}

function initDashboard() {
  bindElements();
  wireEvents();
  initializeVoiceAvailability();
  updateClock();
  refreshDashboard();
  window.setInterval(updateClock, 1000);
  window.setInterval(refreshDashboard, refreshMs);
}

document.addEventListener("DOMContentLoaded", initDashboard);
