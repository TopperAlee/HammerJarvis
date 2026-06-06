const refreshMs = 10000;
let speechOutputEnabled = true;
let isListening = false;

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

async function refreshAlerts() {
  const watcherData = await fetchJson("/assistant/watchers/alerts");
  const alerts = watcherData.alerts || [];
  setText("watcherCounts", `Aktive Hinweise: ${alerts.length}`);
  setText("alertCount", alerts.length);
  renderList(elements.watcherAlerts, alerts.slice(0, 7), renderWatcherAlert);
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
  try {
    elements.errorPanel.hidden = true;
    await Promise.all([
      refreshSystemStatus(),
      refreshEcoFlow(),
      refreshHomeAssistant(),
      refreshAlerts(),
      refreshRecentFiles(),
      refreshEmail(),
      refreshTimeTree(),
    ]);
  } catch (error) {
    elements.errorPanel.hidden = false;
    setStatus("critical");
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
