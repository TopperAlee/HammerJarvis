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
  problemCounts: document.getElementById("problemCounts"),
  problems: document.getElementById("problems"),
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

function setVoiceStatus(message, mode) {
  elements.voiceStatus.textContent = message;
  elements.voiceStatus.className = `voice-status${mode ? ` ${mode}` : ""}`;
}

function extractChatAnswer(response) {
  if (response.answer) {
    return response.answer;
  }
  if (response.message) {
    return response.message;
  }
  if (response.human_status) {
    return formatHumanStatus(response.human_status);
  }
  if (response.overview?.human_status) {
    return formatHumanStatus(response.overview.human_status);
  }
  if (response.problems) {
    return formatProblemAnswer(response.problems);
  }
  if (Array.isArray(response.entities)) {
    return `Ich habe ${response.entities.length} passende Entities gefunden.`;
  }
  return "Ich habe eine Antwort erhalten, kann sie aber noch nicht kompakt anzeigen.";
}

function formatHumanStatus(humanStatus) {
  const details = humanStatus.details || [];
  if (details.length === 0) {
    return humanStatus.headline || "Keine Zusammenfassung verfuegbar.";
  }
  return `${humanStatus.headline} ${details.join("; ")}`;
}

function formatProblemAnswer(problems) {
  const critical = problems.critical_count ?? 0;
  const warning = problems.warning_count ?? 0;
  const info = problems.informational_count ?? 0;
  return `Home Assistant Diagnose: ${critical} kritisch, ${warning} Warnungen, ${info} Hinweise.`;
}

async function sendChatMessage(message) {
  const trimmed = message.trim();
  if (!trimmed) {
    setVoiceStatus("Bitte zuerst einen Befehl eingeben.", "error");
    return;
  }
  elements.recognizedCommand.textContent = trimmed;
  elements.jarvisAnswer.textContent = "Jarvis denkt...";
  setVoiceStatus("Befehl wird gesendet.", "");
  try {
    const response = await postJson("/chat", { message: trimmed });
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

function speakText(text) {
  if (!("speechSynthesis" in window)) {
    setVoiceStatus("Sprachausgabe wird von diesem Browser nicht unterstützt.", "error");
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  const voices = window.speechSynthesis.getVoices();
  utterance.lang = "de-DE";
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
    elements.voiceButton.classList.add("listening");
    setVoiceStatus("Hoere zu...", "active");
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
    elements.voiceButton.classList.remove("listening");
    if (!elements.voiceStatus.classList.contains("error")) {
      setVoiceStatus("Sprachsteuerung bereit.", "");
    }
  };
  recognition.start();
}

function updateDashboard(energy, problems) {
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
    const [energy, problems] = await Promise.all([
      fetchJson("/ha/ecoflow/energy"),
      fetchJson("/ha/problems"),
    ]);
    updateDashboard(energy, problems);
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
      ? "Sprachausgabe ein/aus"
      : "Sprachausgabe aus";
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
}

initializeVoiceControls();
refresh();
window.setInterval(refresh, refreshMs);
