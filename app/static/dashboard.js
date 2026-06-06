const refreshMs = 10000;
let speechOutputEnabled = true;
let isListening = false;

const elements = {
  updatedAt: document.getElementById("updatedAt"),
  statusBadge: document.getElementById("statusBadge"),
  errorPanel: document.getElementById("errorPanel"),
  headline: document.getElementById("headline"),
  details: document.getElementById("details"),
  ecoflowOverall: document.getElementById("ecoflowOverall"),
  ecoflowSummary: document.getElementById("ecoflowSummary"),
  soc: document.getElementById("soc"),
  pvPower: document.getElementById("pvPower"),
  gridPower: document.getElementById("gridPower"),
  smartMeter: document.getElementById("smartMeter"),
  batteryPower: document.getElementById("batteryPower"),
  warningCounts: document.getElementById("warningCounts"),
  warnings: document.getElementById("warnings"),
  watcherCounts: document.getElementById("watcherCounts"),
  watcherAlerts: document.getElementById("watcherAlerts"),
  runWatchers: document.getElementById("runWatchers"),
  refreshWatchers: document.getElementById("refreshWatchers"),
  fileStatus: document.getElementById("fileStatus"),
  fileSearchInput: document.getElementById("fileSearchInput"),
  fileSearchMode: document.getElementById("fileSearchMode"),
  fileSearchButton: document.getElementById("fileSearchButton"),
  fileContentSearchButton: document.getElementById("fileContentSearchButton"),
  openLatestFile: document.getElementById("openLatestFile"),
  fileSearchResults: document.getElementById("fileSearchResults"),
  generatedFiles: document.getElementById("generatedFiles"),
  fileButtons: document.querySelectorAll(".file-button"),
  webResearchInput: document.getElementById("webResearchInput"),
  webResearchButton: document.getElementById("webResearchButton"),
  webResearchStatus: document.getElementById("webResearchStatus"),
  webResearchAnswer: document.getElementById("webResearchAnswer"),
  webResearchSources: document.getElementById("webResearchSources"),
  problemCounts: document.getElementById("problemCounts"),
  problems: document.getElementById("problems"),
  voiceCard: document.getElementById("voiceCard"),
  commandInput: document.getElementById("commandInput"),
  sendCommand: document.getElementById("sendCommand"),
  voiceButton: document.getElementById("voiceButton"),
  speechToggle: document.getElementById("speechToggle"),
  voiceStatus: document.getElementById("voiceStatus"),
  recognizedCommand: document.getElementById("recognizedCommand"),
  jarvisAnswer: document.getElementById("jarvisAnswer"),
  quickButtons: document.querySelectorAll(".quick-button"),
};

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

function formatWatts(value) {
  return value === null || value === undefined ? "-" : `${Math.round(value)} W`;
}

function formatPercent(value) {
  return value === null || value === undefined ? "-" : `${Math.round(value)} %`;
}

function setStatus(overall) {
  const status = overall || "unknown";
  elements.statusBadge.className = `status-badge status-${status}`;
  elements.statusBadge.textContent = {
    ok: "OK",
    warning: "Warnung",
    critical: "Kritisch",
    unknown: "Unbekannt",
  }[status] || "Unbekannt";
}

function setVoiceStatus(message, mode) {
  elements.voiceStatus.textContent = message;
  elements.voiceStatus.className = `voice-status${mode ? ` ${mode}` : ""}`;
}

function renderList(target, items, renderer) {
  target.innerHTML = "";
  if (!items || items.length === 0) {
    const item = document.createElement("li");
    item.textContent = "Keine Eintraege.";
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

function renderWarning(warning) {
  const wrapper = document.createElement("span");
  wrapper.textContent = warning.message || "Unbekannte Warnung";
  if (warning.source_entity_id) {
    const code = document.createElement("code");
    code.textContent = ` ${warning.source_entity_id}`;
    wrapper.appendChild(code);
  }
  return wrapper;
}

function renderProblem(entity) {
  const wrapper = document.createElement("span");
  const code = document.createElement("code");
  code.textContent = entity.entity_id || "unknown";
  wrapper.appendChild(code);
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

function renderGeneratedFile(file) {
  const wrapper = document.createElement("span");
  wrapper.textContent = file.filename || "Datei";
  if (file.path) {
    const code = document.createElement("code");
    code.textContent = ` ${file.path}`;
    wrapper.appendChild(code);
  }
  return wrapper;
}

function renderSearchResult(file) {
  const wrapper = document.createElement("span");
  wrapper.textContent = file.name || "Datei";
  if (file.path) {
    const code = document.createElement("code");
    code.textContent = ` ${file.path}`;
    wrapper.appendChild(code);
    const openButton = document.createElement("button");
    openButton.className = "dashboard-button inline-button";
    openButton.type = "button";
    openButton.textContent = "Oeffnen";
    openButton.addEventListener("click", async () => {
      try {
        const response = await postJson("/assistant/files/open", { path: file.path });
        elements.fileStatus.textContent = response.message || "Datei wurde geoeffnet.";
      } catch (error) {
        elements.fileStatus.textContent = "Datei konnte nicht geoeffnet werden.";
      }
    });
    wrapper.appendChild(openButton);
    const summarizeButton = document.createElement("button");
    summarizeButton.className = "dashboard-button inline-button";
    summarizeButton.type = "button";
    summarizeButton.textContent = "Zusammenfassen";
    summarizeButton.addEventListener("click", async () => {
      try {
        const response = await postJson("/assistant/files/summarize", { path: file.path });
        elements.fileStatus.textContent = response.summary || response.message || "Keine Zusammenfassung verfuegbar.";
      } catch (error) {
        elements.fileStatus.textContent = "Zusammenfassung fehlgeschlagen.";
      }
    });
    wrapper.appendChild(summarizeButton);
    const extractButton = document.createElement("button");
    extractButton.className = "dashboard-button inline-button";
    extractButton.type = "button";
    extractButton.textContent = "Eckdaten extrahieren";
    extractButton.addEventListener("click", async () => {
      try {
        const response = await postJson("/assistant/files/extract-key-fields", {
          path: file.path,
          document_type: "kaufvertrag",
        });
        const entries = Object.entries(response.key_snippets || {});
        elements.fileStatus.textContent = entries.length
          ? entries.map(([key, values]) => `${key}: ${values[0]}`).join(" | ")
          : response.message || "Keine Eckdaten gefunden.";
      } catch (error) {
        elements.fileStatus.textContent = "Eckdaten konnten nicht extrahiert werden.";
      }
    });
    wrapper.appendChild(extractButton);
  }
  if (file.snippets && file.snippets.length > 0) {
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
  if (source.url) {
    const code = document.createElement("code");
    code.textContent = ` ${source.url}`;
    wrapper.appendChild(code);
  }
  return wrapper;
}

function extractChatAnswer(response) {
  if (response.answer) {
    return response.answer;
  }
  return "Jarvis hat geantwortet, aber ohne lesbaren Antworttext.";
}

async function sendChatMessage(message) {
  const trimmed = message.trim();
  if (!trimmed) {
    return;
  }
  elements.recognizedCommand.textContent = trimmed;
  elements.jarvisAnswer.textContent = "Jarvis denkt...";
  setVoiceStatus("Befehl wird gesendet.", "");

  try {
    let response;
    try {
      response = await postJson("/assistant/chat", { message: trimmed, confirm: false });
    } catch (assistantError) {
      if (!isLegacyHomeAssistantCommand(trimmed)) {
        const messageText = "Der neue Assistant-Endpunkt hat einen Fehler gemeldet. Bitte prüfe die Backend-Konsole.";
        elements.jarvisAnswer.textContent = messageText;
        setVoiceStatus(messageText, "error");
        return;
      }
      response = await postJson("/chat", { message: trimmed });
    }
    const answer = extractChatAnswer(response);
    elements.jarvisAnswer.textContent = answer;
    setVoiceStatus("Antwort empfangen.", "");
    if (speechOutputEnabled) {
      speakText(answer);
    }
  } catch (error) {
    const messageText = "Verbindung zum Hammer-Jarvis-Backend fehlgeschlagen.";
    elements.jarvisAnswer.textContent = messageText;
    setVoiceStatus(messageText, "error");
  }
}

function isLegacyHomeAssistantCommand(message) {
  const normalized = message.toLowerCase();
  const assistantTerms = [
    "gmail",
    "email",
    "e-mail",
    "mail",
    "posteingang",
    "nachricht",
    "kalender",
    "termin",
    "meeting",
    "timetree",
  ];
  if (assistantTerms.some((term) => normalized.includes(term))) {
    return false;
  }
  return [
    "home assistant",
    "schalte",
    "geräte",
    "geraete",
    "probleme",
    "offline",
    "entities",
    "entity",
    "nicht verfügbar",
    "nicht verfuegbar",
  ].some((term) => normalized.includes(term));
}

function speakText(text) {
  if (!("speechSynthesis" in window)) {
    setVoiceStatus("Sprachausgabe wird von diesem Browser nicht unterstützt.", "error");
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  const voices = window.speechSynthesis.getVoices();
  utterance.lang = "de-DE";
  utterance.rate = 1;
  utterance.voice =
    voices.find((voice) => voice.lang?.toLowerCase().startsWith("de")) || null;
  window.speechSynthesis.speak(utterance);
}

function startVoiceRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    setVoiceStatus(
      "Spracherkennung wird von diesem Browser nicht unterstützt. Bitte Chrome oder Edge verwenden.",
      "error",
    );
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
    elements.recognizedCommand.textContent = transcript || "-";
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
      setVoiceStatus("Sprachsteuerung bereit.", "");
    }
  };
  recognition.start();
}

function updateDashboard(energy, problems, watcherData, filesData) {
  const humanStatus = energy.human_status || {};
  elements.errorPanel.hidden = true;
  setStatus(humanStatus.overall);
  elements.updatedAt.textContent = `Aktualisiert: ${new Date().toLocaleTimeString("de-DE")}`;
  elements.headline.textContent = humanStatus.headline || energy.summary || "Keine EcoFlow-Daten.";
  elements.ecoflowOverall.textContent = humanStatus.overall || "-";
  elements.ecoflowSummary.textContent = energy.summary || "";

  renderList(elements.details, humanStatus.details || [], (item) => item);

  elements.soc.textContent = formatPercent(energy.soc_percent);
  elements.pvPower.textContent = formatWatts(energy.pv_power_w);
  elements.gridPower.textContent = formatWatts(energy.grid_power_w);
  elements.smartMeter.textContent = formatWatts(energy.smart_meter_w);
  elements.batteryPower.textContent = formatWatts(energy.battery_power_w);

  const criticalCount = energy.critical_count ?? 0;
  const warningSeverityCount = energy.warning_count_by_severity ?? 0;
  const infoCount = energy.info_count ?? 0;
  elements.warningCounts.textContent =
    `Kritisch: ${criticalCount} | Warnung: ${warningSeverityCount} | Info: ${infoCount}`;
  renderList(elements.warnings, energy.warnings || [], renderWarning);

  const alerts = watcherData.alerts || [];
  elements.watcherCounts.textContent = `Aktive Hinweise: ${alerts.length}`;
  renderList(elements.watcherAlerts, alerts, renderWatcherAlert);

  renderList(elements.generatedFiles, filesData.files || [], renderGeneratedFile);

  const problemCritical = problems.critical_count ?? 0;
  const problemWarning = problems.warning_count ?? 0;
  const problemInfo = problems.informational_count ?? 0;
  elements.problemCounts.textContent =
    `Kritisch: ${problemCritical} | Warnung: ${problemWarning} | Info: ${problemInfo}`;
  const problemItems = [
    ...(problems.critical || []),
    ...(problems.warning || []),
    ...(problems.informational || []),
  ];
  renderList(elements.problems, problemItems, renderProblem);
}

async function refresh() {
  try {
    const [energy, problems, watcherData, filesData] = await Promise.all([
      fetchJson("/ha/ecoflow/energy"),
      fetchJson("/ha/problems"),
      fetchJson("/assistant/watchers/alerts"),
      fetchJson("/assistant/files/exports"),
    ]);
    updateDashboard(energy, problems, watcherData, filesData);
  } catch (error) {
    elements.errorPanel.hidden = false;
    setStatus("critical");
    elements.updatedAt.textContent = "Verbindung fehlgeschlagen";
  }
}

function initializeVoiceControls() {
  if (!("speechSynthesis" in window)) {
    setVoiceStatus("Sprachausgabe wird von diesem Browser nicht unterstützt.", "error");
  }
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    setVoiceStatus(
      "Spracherkennung wird von diesem Browser nicht unterstützt. Bitte Chrome oder Edge verwenden.",
      "error",
    );
  }

  elements.sendCommand.addEventListener("click", () => {
    sendChatMessage(elements.commandInput.value);
  });
  elements.commandInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      sendChatMessage(elements.commandInput.value);
    }
  });
  elements.voiceButton.addEventListener("click", startVoiceRecognition);
  elements.speechToggle.addEventListener("click", () => {
    speechOutputEnabled = !speechOutputEnabled;
    if (!speechOutputEnabled && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    elements.speechToggle.textContent = speechOutputEnabled
      ? "Sprachausgabe: Ein"
      : "Sprachausgabe: Aus";
    setVoiceStatus(
      speechOutputEnabled ? "Sprachausgabe ist eingeschaltet." : "Sprachausgabe ist ausgeschaltet.",
      "",
    );
  });
  for (const button of elements.quickButtons) {
    button.addEventListener("click", () => {
      const command = button.dataset.command || "";
      elements.commandInput.value = command;
      sendChatMessage(command);
    });
  }
  elements.refreshWatchers.addEventListener("click", refresh);
  elements.runWatchers.addEventListener("click", async () => {
    try {
      await postJson("/assistant/watchers/run", {});
      await refresh();
    } catch (error) {
      elements.errorPanel.hidden = false;
    }
  });
  for (const button of elements.fileButtons) {
    button.addEventListener("click", async () => {
      const command = button.dataset.command || "";
      elements.fileStatus.textContent = "Datei wird erstellt...";
      const response = await postJson("/assistant/chat", { message: command, confirm: false });
      elements.fileStatus.textContent = response.answer || "Datei wurde erstellt.";
      await refresh();
    });
  }
  elements.fileSearchButton.addEventListener("click", async () => {
    await runFileSearch();
  });
  elements.fileContentSearchButton.addEventListener("click", async () => {
    elements.fileSearchMode.value = "content";
    await runFileSearch();
  });
  elements.fileSearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      elements.fileSearchButton.click();
    }
  });
  elements.openLatestFile.addEventListener("click", async () => {
    try {
      const response = await postJson("/assistant/files/open-latest", {});
      elements.fileStatus.textContent = response.message || "Letzte Datei wurde geoeffnet.";
    } catch (error) {
      elements.fileStatus.textContent = "Letzte Datei konnte nicht geoeffnet werden.";
    }
  });
  elements.webResearchButton.addEventListener("click", async () => {
    const query = elements.webResearchInput.value.trim();
    if (!query) {
      return;
    }
    elements.webResearchStatus.textContent = "Recherche laeuft...";
    elements.webResearchAnswer.textContent = "-";
    renderList(elements.webResearchSources, [], renderWebSource);
    try {
      const response = await postJson("/assistant/web/research", { query });
      elements.webResearchStatus.textContent = response.message || "Recherche abgeschlossen.";
      elements.webResearchAnswer.textContent = response.summary || response.message || "Keine Zusammenfassung verfuegbar.";
      renderList(elements.webResearchSources, response.sources || [], renderWebSource);
    } catch (error) {
      elements.webResearchStatus.textContent = "Internetrecherche fehlgeschlagen.";
    }
  });
  elements.webResearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      elements.webResearchButton.click();
    }
  });
}

async function runFileSearch() {
    const query = elements.fileSearchInput.value.trim();
    if (!query) {
      return;
    }
    try {
      const endpoint = elements.fileSearchMode.value === "content"
        ? "/assistant/files/content-search"
        : "/assistant/files/search";
      const response = await fetchJson(`${endpoint}?q=${encodeURIComponent(query)}`);
      elements.fileStatus.textContent = response.message || "Suche abgeschlossen.";
      renderList(elements.fileSearchResults, response.files || [], renderSearchResult);
    } catch (error) {
      elements.fileStatus.textContent = "Dateisuche fehlgeschlagen.";
    }
}

initializeVoiceControls();
refresh();
window.setInterval(refresh, refreshMs);
