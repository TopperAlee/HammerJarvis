const DASHBOARD_BUILD = "engineering-diagnostics-20260714";
const refreshMs = 30000;
const entityCatalogRefreshMs = 60000;
const fetchTimeoutMs = 15000;
const activityRefreshMs = 500;
const completedActivityMaxAgeMs = 12000;
const failedActivityMaxAgeMs = 30000;
const speechVoiceStorageKey = "hammerJarvisSpeechVoice";
const speechDefaults = {
  lang: "de-DE",
  rate: 0.94,
  pitch: 0.96,
  volume: 1.0,
  targetChunkLength: 220,
  maxChunkLength: 260,
};
const VOICE_LOAD_STATES = {
  IDLE: "idle",
  LOADING: "loading",
  SUCCESS: "success",
  EMPTY: "empty",
  UNSUPPORTED: "unsupported",
  ERROR: "error",
  CANCELLED: "cancelled",
};
const VOICE_RETRY_DELAYS_MS = [0, 100, 300, 750, 1500, 3000];
const VOICE_LOAD_WATCHDOG_MS = 5500;
const VOICE_LOAD_ELAPSED_UPDATE_MS = 250;
const HANDS_FREE_STATES = {
  DISABLED: "disabled",
  STARTING: "starting",
  ARMED: "armed",
  WAKE_DETECTED: "wake_detected",
  COMMAND_LISTENING: "command_listening",
  PROCESSING: "processing",
  SPEAKING: "speaking",
  COOLDOWN: "cooldown",
  ERROR: "error",
};
const HANDS_FREE_RECONNECT_DELAYS_MS = [1000, 2000, 5000];
const HANDS_FREE_STORAGE_KEY = "hammerJarvisHandsFreeWanted";
const DESKTOP_EVENT_RECONNECT_DELAYS_MS = [1000, 2000, 5000];
const PROTOOL_PANEL_DIMENSIONS = {
  OP7: { rows: 4, columns: 20 },
  TD17_4x20: { rows: 4, columns: 20 },
  OP17_4x20: { rows: 4, columns: 20 },
  TD17_8x40: { rows: 8, columns: 40 },
  OP17_8x40: { rows: 8, columns: 40 },
  OP27_8x40: { rows: 8, columns: 40 },
};
let speechOutputEnabled = true;
let isListening = false;
let isAssistantSpeaking = false;
let commandRecognitionRunId = 0;
let currentCommandRecognition = null;
let dashboardRefreshInFlight = false;
let lastEntityCatalogRefresh = 0;
let speechVoices = [];
let speechVoicesListenerRegistered = false;
let speechRunId = 0;
let chatActivityId = "";
let speechActivityId = "";
let recognitionActivityId = "";
let activityTimer = null;
let voiceLoadState = VOICE_LOAD_STATES.IDLE;
let voiceLoadGeneration = 0;
let voiceLoadAttempt = 0;
let voiceLoadStartTime = 0;
let voiceLoadTimers = [];
let voiceLoadElapsedTimer = null;
let voiceLoadInProgress = false;
let voiceLoadDiagnosticsLogged = false;
let dashboardInitialized = false;
let handsFreeState = HANDS_FREE_STATES.DISABLED;
let handsFreeWanted = false;
let handsFreeAudioContext = null;
let handsFreeMediaStream = null;
let handsFreeSource = null;
let handsFreeWorklet = null;
let handsFreeSocket = null;
let handsFreeStreamingPaused = true;
let handsFreeReconnectAttempt = 0;
let handsFreeReconnectTimer = null;
let handsFreeResumeTimer = null;
let handsFreeCommandTimer = null;
let handsFreeConfig = {
  enabled: false,
  installed: false,
  model_available: false,
  sample_rate: 16000,
  frame_ms: 80,
  command_timeout_ms: 8000,
};
let desktopEventSocket = null;
let desktopEventReconnectAttempt = 0;
let desktopEventReconnectTimer = null;
let desktopEventHeartbeatTimer = null;
let desktopAgentState = "Nicht verbunden";
let selectedProToolFile = null;
const knowledgeBusyDocumentIds = new Set();

const elements = {};
const activities = new Map();
const recentActivities = [];
const requiredVoiceElementIds = [
  "voiceLoadingPanel",
  "voiceSelect",
  "reloadVoices",
  "voiceStatusText",
  "voiceProgressText",
  "voiceDiagnosticText",
  "voiceLoadingIndicator",
];

console.info(`[Hammer Jarvis] dashboard.js geladen: ${DASHBOARD_BUILD}`);
if (document?.documentElement) {
  document.documentElement.dataset.dashboardBuild = DASHBOARD_BUILD;
}

registerGlobalDashboardErrorHandlers();

function registerGlobalDashboardErrorHandlers() {
  window.addEventListener("error", (event) => {
    console.error("[Hammer Jarvis] Dashboard-Laufzeitfehler", event.error || event.message);
    if (voiceLoadState === VOICE_LOAD_STATES.LOADING || voiceLoadState === VOICE_LOAD_STATES.IDLE) {
      renderVoiceInitializationError(event.error || new Error(String(event.message || "Unbekannter Fehler")));
    }
  });
  window.addEventListener("unhandledrejection", (event) => {
    console.error("[Hammer Jarvis] Unbehandelte Dashboard-Promise", event.reason);
    if (voiceLoadState === VOICE_LOAD_STATES.LOADING || voiceLoadState === VOICE_LOAD_STATES.IDLE) {
      renderVoiceInitializationError(event.reason || new Error("Unbehandelte Promise-Ablehnung"));
    }
  });
}

function bindElements() {
  const ids = [
    "llmProvider",
    "voiceMiniStatus",
    "currentTime",
    "statusBadge",
    "errorPanel",
    "activityPanel",
    "activeActivities",
    "recentActivities",
    "clearActivities",
    "headline",
    "details",
    "emailCount",
    "eventCount",
    "warningTotal",
    "alertCount",
    "voiceCard",
    "voiceButton",
    "chatMicButton",
    "handsFreeToggle",
    "handsFreeChatToggle",
    "handsFreeStatus",
    "handsFreeDetails",
    "desktopAgentStatus",
    "desktopWakeWord",
    "desktopWakeEngine",
    "desktopReconnectButton",
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
    "knowledgeDropZone",
    "knowledgeFileInput",
    "knowledgeSelectFilesButton",
    "knowledgeUploadQueue",
    "knowledgeUploadSummary",
    "knowledgeSupportedFormats",
    "commandCenter",
    "openCommandPalette",
    "closeCommandPalette",
    "commandPalette",
    "commandPaletteInput",
    "commandPaletteStatus",
    "commandPaletteResult",
    "commandPaletteCommands",
    "activeContextList",
    "recommendationsList",
    "researchContextQuery",
    "researchSourceCount",
    "researchContextSize",
    "researchAnswerButton",
    "researchAnswerText",
    "researchAnswerSources",
    "researchEngineeringObjects",
    "researchRecommendations",
    "protoolFilePath",
    "protoolBrowseButton",
    "protoolFilePicker",
    "protoolSelectedFileName",
    "protoolPanel",
    "protoolTextColumn",
    "protoolEncoding",
    "protoolIncludePreview",
    "protoolBatchFilePaths",
    "protoolAnalyzeButton",
    "protoolImportButton",
    "protoolBatchAnalyzeButton",
    "protoolStatus",
    "protoolProjectSummary",
    "protoolSummary",
    "protoolNoIssues",
    "protoolIssuesBody",
    "protoolFileReports",
    "engineeringModules",
    "engineeringProjectPath",
    "engineeringOpenProject",
    "engineeringProjectStatus",
    "engineeringProjectExplorer",
    "runEngineeringDiagnostics",
    "diagnosticsSeverityFilter",
    "diagnosticsCategoryFilter",
    "diagnosticsSummary",
    "diagnosticsIssueDetails",
    "diagnosticsIssueTableBody",
    "refreshActions",
    "pendingActions",
    "runWatchers",
    "refreshWatchers",
    "watcherAlerts",
    "speechToggle",
    "voiceLoadingPanel",
    "voiceSelect",
    "voiceSelectStatus",
    "voiceLoadingIndicator",
    "voiceStatusText",
    "voiceProgressText",
    "voiceDiagnosticText",
    "reloadVoices",
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
  elements.topNavButtons = document.querySelectorAll(".top-tab");
}

async function fetchJson(url, options = {}) {
  return requestJson(url, { ...options, method: "GET" });
}

async function postJson(url, body, options = {}) {
  return requestJson(url, { ...options, method: "POST", body });
}

async function requestJson(url, options = {}) {
  const timeoutMs = options.timeoutMs ?? fetchTimeoutMs;
  const activityId = options.activityId || "";
  let timeoutHandle = null;
  const controller = new AbortController();
  if (activityId && !activities.has(activityId)) {
    startActivity(activityId, options.activityTitle || "Anfrage wird ausgeführt", {
      category: options.activityCategory || "api",
      detail: options.activityDetail || "Anfrage wird gesendet",
      timeoutMs,
    });
  }
  if (activityId) {
    updateActivity(activityId, { detail: options.activityDetail || "Anfrage wird gesendet" });
  }
  try {
    timeoutHandle = window.setTimeout(() => controller.abort("timeout"), timeoutMs);
    const fetchOptions = {
      method: options.method || "GET",
      cache: "no-store",
      signal: controller.signal,
      headers: options.body ? { "Content-Type": "application/json" } : undefined,
      body: options.body ? JSON.stringify(options.body) : undefined,
    };
    const response = await fetch(url, fetchOptions);
    if (!response.ok) {
      const error = new Error(`HTTP ${response.status}`);
      error.kind = "http";
      throw error;
    }
    return response.json();
  } catch (error) {
    if (error.name === "AbortError" || controller.signal.aborted) {
      const timeoutError = new Error(`Zeitüberschreitung nach ${formatDuration(timeoutMs)}.`);
      timeoutError.kind = "timeout";
      if (activityId) {
        timeoutActivity(activityId, timeoutError.message);
      }
      throw timeoutError;
    }
    if (activityId) {
      failActivity(activityId, error.kind === "http" ? error.message : "Netzwerkfehler oder Backend nicht erreichbar.");
    }
    throw error;
  } finally {
    if (timeoutHandle) {
      window.clearTimeout(timeoutHandle);
    }
  }
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
  setText("voiceMiniStatus", mode === "active" ? "Hört zu" : mode === "speaking" ? "Spricht" : "Bereit");
  elements.voiceStatus.className = `voice-status${mode ? ` ${mode}` : ""}`;
}

function startActivity(id, title, options = {}) {
  const activity = {
    id,
    title,
    status: options.status || "running",
    startTime: Date.now(),
    endTime: null,
    detail: options.detail || "",
    progress: options.progress ?? null,
    retry: options.retry ?? null,
    retryTotal: options.retryTotal ?? null,
    timeoutMs: options.timeoutMs ?? null,
    category: options.category || "system",
  };
  activities.set(id, activity);
  startActivityTicker();
  renderActivities();
  return id;
}

function updateActivity(id, patch = {}) {
  const activity = activities.get(id);
  if (!activity) {
    return;
  }
  Object.assign(activity, patch);
  if (activity.status === "pending") {
    activity.status = "running";
  }
  renderActivities();
}

function finishActivity(id, detail = "Abgeschlossen") {
  endActivity(id, "success", detail);
}

function failActivity(id, detail = "Fehler") {
  endActivity(id, "error", detail);
}

function timeoutActivity(id, detail = "Zeitüberschreitung") {
  endActivity(id, "timeout", detail);
}

function cancelActivity(id, detail = "Abgebrochen") {
  endActivity(id, "cancelled", detail);
}

function endActivity(id, status, detail) {
  const activity = activities.get(id);
  if (!activity) {
    return;
  }
  activity.status = status;
  activity.detail = detail || activity.detail;
  activity.endTime = Date.now();
  activities.delete(id);
  recentActivities.unshift(activity);
  trimRecentActivities();
  renderActivities();
}

function trimRecentActivities() {
  const now = Date.now();
  for (let index = recentActivities.length - 1; index >= 0; index -= 1) {
    const activity = recentActivities[index];
    const maxAge = activity.status === "success" ? completedActivityMaxAgeMs : failedActivityMaxAgeMs;
    if (recentActivities.length > 10 || now - activity.endTime > maxAge) {
      recentActivities.splice(index, 1);
    }
  }
}

function startActivityTicker() {
  if (activityTimer) {
    return;
  }
  activityTimer = window.setInterval(() => {
    trimRecentActivities();
    renderActivities();
    if (activities.size === 0 && recentActivities.length === 0) {
      window.clearInterval(activityTimer);
      activityTimer = null;
    }
  }, activityRefreshMs);
}

function renderActivities() {
  try {
    renderActivityList(elements.activeActivities, Array.from(activities.values()).slice(0, 5), "Keine aktiven Vorgänge.");
    renderActivityList(elements.recentActivities, recentActivities.slice(0, 5), "Keine abgeschlossenen Vorgänge.");
  } catch (error) {
    console.warn("[Hammer Jarvis Activity] Aktivitätsanzeige fehlgeschlagen.", error);
  }
}

function renderActivityList(target, items, emptyText) {
  if (!target) {
    return;
  }
  target.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("li");
    empty.className = "activity-item activity-cancelled";
    empty.textContent = emptyText;
    target.appendChild(empty);
    return;
  }
  for (const activity of items) {
    target.appendChild(renderActivityItem(activity));
  }
}

function renderActivityItem(activity) {
  const item = document.createElement("li");
  item.className = `activity-item activity-${activity.status}`;
  const indicator = document.createElement("span");
  indicator.className = activity.status === "running" || activity.status === "retrying" || activity.status === "pending"
    ? "activity-spinner"
    : "activity-pulse";
  const body = document.createElement("span");
  const title = document.createElement("strong");
  title.textContent = activity.title;
  const detail = document.createElement("span");
  detail.className = "activity-detail";
  detail.textContent = activityDetailText(activity);
  const elapsed = document.createElement("span");
  elapsed.className = "activity-elapsed";
  elapsed.textContent = activityElapsedText(activity);
  body.append(title, detail, elapsed);
  item.append(indicator, body);
  return item;
}

function activityDetailText(activity) {
  const parts = [];
  if (activity.retry !== null && activity.retryTotal !== null) {
    parts.push(`Versuch ${activity.retry} von ${activity.retryTotal}`);
  }
  if (activity.progress) {
    parts.push(activity.progress);
  }
  if (activity.detail) {
    parts.push(activity.detail);
  }
  return parts.join(" · ") || activity.status;
}

function activityElapsedText(activity) {
  const end = activity.endTime || Date.now();
  const duration = Math.max(0, end - activity.startTime);
  if (activity.endTime) {
    return `${activityStatusLabel(activity.status)} · ${formatDuration(duration)}`;
  }
  return `läuft seit ${formatDuration(duration)}`;
}

function activityStatusLabel(status) {
  return {
    pending: "Wartet",
    running: "Aktiv",
    retrying: "Wiederholung",
    success: "Abgeschlossen",
    error: "Fehler",
    timeout: "Zeitüberschreitung",
    cancelled: "Abgebrochen",
  }[status] || status;
}

function formatDuration(milliseconds) {
  const totalSeconds = Math.max(0, Math.round(milliseconds / 100) / 10);
  if (totalSeconds < 60) {
    return `${totalSeconds.toLocaleString("de-DE", { maximumFractionDigits: 1 })} Sekunden`;
  }
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.round(totalSeconds % 60);
  return `${minutes} Minute${minutes === 1 ? "" : "n"} ${seconds} Sekunden`;
}

function withButtonLoading(button, loadingText, action) {
  if (!button || button.disabled) {
    return Promise.resolve();
  }
  const originalText = button.dataset.originalText || button.textContent;
  button.dataset.originalText = originalText;
  button.disabled = true;
  button.classList.add("button-loading");
  button.textContent = loadingText;
  return Promise.resolve()
    .then(action)
    .then((result) => {
      button.textContent = "Abgeschlossen";
      window.setTimeout(() => restoreButton(button), 900);
      return result;
    })
    .catch((error) => {
      button.textContent = "Fehler";
      window.setTimeout(() => restoreButton(button), 1400);
      console.warn("[Hammer Jarvis Dashboard] Button-Aktion fehlgeschlagen.", error);
      return undefined;
    });
}

function restoreButton(button) {
  if (!button) {
    return;
  }
  button.disabled = false;
  button.classList.remove("button-loading");
  button.textContent = button.dataset.originalText || button.textContent;
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

function openCommandPalette() {
  if (!elements.commandPalette) {
    return;
  }
  elements.commandPalette.hidden = false;
  elements.commandPaletteInput?.focus();
  refreshCommandPaletteCommands();
}

function closeCommandPalette() {
  if (elements.commandPalette) {
    elements.commandPalette.hidden = true;
  }
}

function navigateDashboardSection(targetId, sourceButton = null) {
  const target = document.getElementById(targetId);
  if (!target) {
    return;
  }
  setActiveTopTab(sourceButton || findTopTabForTarget(targetId));
  if (!target.hasAttribute("tabindex")) {
    target.setAttribute("tabindex", "-1");
  }
  target.scrollIntoView({ behavior: "smooth", block: "start" });
  target.focus({ preventScroll: true });
}

function findTopTabForTarget(targetId) {
  return Array.from(elements.topNavButtons || []).find((button) => button.dataset.target === targetId) || null;
}

function setActiveTopTab(activeButton) {
  for (const button of elements.topNavButtons || []) {
    const isActive = button === activeButton;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-current", isActive ? "page" : "false");
  }
}

async function parseCommandPaletteIntent() {
  const value = text(elements.commandPaletteInput?.value, "").trim();
  if (!value) {
    setText("commandPaletteResult", "Bitte einen Befehl eingeben.");
    return;
  }
  try {
    const result = await postJson("/assistant/intent/parse", {
      text: value,
      source: "command_palette",
      context: {},
    });
    const message = `${result.intent || "unknown"} · Risiko: ${result.risk || "-"} · ${result.message || ""}`;
    setText("commandPaletteResult", message);
    setText("commandPaletteStatus", message);
    await refreshCommandCenter();
  } catch (error) {
    setText("commandPaletteResult", "Intent konnte nicht erkannt werden.");
    setText("commandPaletteStatus", "Command Palette Fehler.");
  }
}

async function refreshCommandPaletteCommands() {
  if (!elements.commandPaletteCommands || elements.commandPaletteCommands.childElementCount > 0) {
    return;
  }
  try {
    const commands = await fetchJson("/assistant/commands");
    renderList(elements.commandPaletteCommands, commands, (command) => {
      const wrapper = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = command.label || command.intent || "Befehl";
      const detail = document.createElement("div");
      detail.className = "muted";
      detail.textContent = Array.isArray(command.examples) ? command.examples.join(" · ") : "";
      wrapper.append(title, detail);
      return wrapper;
    });
  } catch (error) {
    renderList(elements.commandPaletteCommands, [], () => "", "Befehle konnten nicht geladen werden.");
  }
}

async function refreshCommandCenter() {
  await Promise.all([
    refreshActiveContext(),
    refreshRecommendations(),
    refreshResearchContext(),
  ]);
}

async function refreshActiveContext() {
  if (!elements.activeContextList) {
    return;
  }
  try {
    const context = await fetchJson("/assistant/context");
    const rows = [
      ["Workspace", context.active_workspace],
      ["Projekt", context.active_project_name || context.active_project_id],
      ["Datei", context.active_file],
      ["Dateityp", context.active_file_type],
      ["Panel", context.active_panel],
      ["Sprache", context.active_language],
      ["Aufgabe", context.current_task],
    ].filter(([, value]) => Boolean(value));
    renderList(
      elements.activeContextList,
      rows,
      ([label, value]) => `${label}: ${value}`,
      "Kein aktiver Kontext.",
    );
  } catch (error) {
    renderList(elements.activeContextList, [], () => "", "Kontext konnte nicht geladen werden.");
  }
}

async function refreshRecommendations() {
  if (!elements.recommendationsList) {
    return;
  }
  try {
    const recommendations = await fetchJson("/assistant/recommendations");
    renderList(
      elements.recommendationsList,
      recommendations,
      renderRecommendation,
      "Keine Empfehlungen.",
    );
  } catch (error) {
    renderList(elements.recommendationsList, [], () => "", "Empfehlungen konnten nicht geladen werden.");
  }
}

function renderRecommendation(recommendation) {
  const wrapper = document.createElement("span");
  wrapper.textContent = `${recommendation.title || "Empfehlung"}: ${recommendation.message || ""}`;
  const badge = document.createElement("small");
  badge.className = `recommendation-badge severity-${recommendation.severity || "info"}`;
  badge.textContent = recommendation.severity || "info";
  wrapper.append(" ", badge);
  return wrapper;
}

async function refreshResearchContext() {
  if (!elements.researchContextQuery || !elements.researchSourceCount || !elements.researchContextSize) {
    return;
  }
  const query = text(elements.commandPaletteInput?.value, "").trim()
    || text(elements.knowledgeSearchInput?.value, "").trim()
    || "Systemstatus";
  try {
    const context = await postJson("/assistant/research/context", {
      query,
      include_web: false,
    });
    setText("researchContextQuery", context.request?.query || query);
    setText("researchSourceCount", String(context.statistics?.source_count ?? (context.sources || []).length ?? 0));
    setText("researchContextSize", `${context.statistics?.prompt_char_count ?? text(context.prompt, "").length} Zeichen`);
  } catch (error) {
    setText("researchContextQuery", query);
    setText("researchSourceCount", "-");
    setText("researchContextSize", "Research-Kontext nicht verfügbar");
  }
}

async function buildResearchAnswer() {
  const query = text(elements.commandPaletteInput?.value, "").trim()
    || text(elements.knowledgeSearchInput?.value, "").trim()
    || "Systemstatus";
  try {
    const answer = await postJson("/assistant/research/answer", { query });
    setText("researchAnswerText", answer.answer || "Keine Antwort erzeugt.");
    renderList(elements.researchAnswerSources, answer.sources || [], renderResearchSource, "Keine Quellen.");
    renderList(elements.researchEngineeringObjects, answer.engineering_objects || [], renderEngineeringObject, "Keine Engineering Objects.");
    renderList(elements.researchRecommendations, answer.recommendations || [], (recommendation) => recommendation, "Keine Empfehlungen.");
    setText("researchSourceCount", String((answer.sources || []).length));
  } catch (error) {
    setText("researchAnswerText", "Research-Antwort konnte nicht erzeugt werden.");
  }
}

function renderResearchSource(source) {
  return `${source.type || "SOURCE"}: ${source.title || source.id || "Quelle"}`;
}

function renderEngineeringObject(object) {
  const source = object.source ? ` (${object.source})` : "";
  return `${object.type || "Object"}: ${object.name || object.id || "Engineering Object"}${source}`;
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

function renderKnowledgeDocument(knowledgeDocument) {
  const wrapper = document.createElement("div");
  wrapper.className = "knowledge-document";
  const title = document.createElement("strong");
  title.textContent = knowledgeDocument.original_name || knowledgeDocument.name || "Unbenanntes Dokument";
  const meta = document.createElement("div");
  meta.className = "muted";
  meta.textContent = [
    (knowledgeDocument.extension || "-").replace(/^\./, "").toUpperCase(),
    formatFileSize(knowledgeDocument.size_bytes),
    `${knowledgeDocument.chunk_count ?? 0} Chunks`,
    formatKnowledgeDate(knowledgeDocument.indexed_at),
    knowledgeDocumentStatus(knowledgeDocument.extraction_status),
    knowledgeDocument.source_type === "upload" ? "Upload" : "Lokaler Pfad",
  ].filter(Boolean).join(" · ");
  wrapper.append(title, meta);
  if (knowledgeDocument.extraction_message) {
    const message = document.createElement("div");
    message.className = "muted";
    message.textContent = knowledgeDocument.extraction_message;
    wrapper.appendChild(message);
  }
  const controls = document.createElement("div");
  controls.className = "knowledge-document-controls";
  controls.append(
    createKnowledgeDocumentButton("Details", () => showKnowledgeDetails(knowledgeDocument)),
    createKnowledgeDocumentButton("Neu indexieren", (button) => reindexKnowledgeDocument(knowledgeDocument, button)),
    createKnowledgeDocumentButton("Entfernen", (button) => deleteKnowledgeDocument(knowledgeDocument, button)),
  );
  wrapper.appendChild(controls);
  return wrapper;
}

function createKnowledgeDocumentButton(label, action) {
  const button = document.createElement("button");
  button.className = "ghost-button small-action";
  button.type = "button";
  button.textContent = label;
  button.addEventListener("click", () => action(button));
  return button;
}

function formatFileSize(value) {
  const size = Number(value);
  if (!Number.isFinite(size) || size < 0) return "-";
  if (size < 1024) return `${size} Byte`;
  if (size < 1024 * 1024) return `${(size / 1024).toLocaleString("de-DE", { maximumFractionDigits: 1 })} KB`;
  return `${(size / (1024 * 1024)).toLocaleString("de-DE", { maximumFractionDigits: 1 })} MB`;
}

function formatKnowledgeDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
}

function knowledgeDocumentStatus(status) {
  return {
    indexed: "Bereit",
    pending: "Verarbeitung ausstehend",
    error: "Fehler",
    ocr_required: "OCR erforderlich",
    missing: "Quelldatei fehlt",
    source_file_missing: "Quelldatei fehlt",
  }[String(status || "")] || "Unbekannt";
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

function addChatMessage(role, message, knowledgeSources = []) {
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
  if (role === "assistant" && Array.isArray(knowledgeSources) && knowledgeSources.length) {
    const uniqueNames = [...new Set(knowledgeSources.map((source) => text(source?.name, "").trim()).filter(Boolean))];
    if (uniqueNames.length) {
      const sources = document.createElement("div");
      sources.className = "knowledge-chat-sources";
      const heading = document.createElement("strong");
      heading.textContent = "Quellen:";
      const list = document.createElement("ul");
      for (const name of uniqueNames) {
        const source = document.createElement("li");
        source.textContent = name;
        list.appendChild(source);
      }
      sources.append(heading, list);
      item.appendChild(sources);
    }
  }
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
  if (chatActivityId && activities.has(chatActivityId)) {
    cancelActivity(chatActivityId, "Neue Anfrage gestartet.");
  }
  chatActivityId = `chat-${Date.now()}`;
  startActivity(chatActivityId, "Jarvis verarbeitet die Anfrage", {
    detail: "Anfrage wird gesendet",
    category: "chat",
    timeoutMs: 30000,
  });
  setText("recognizedCommand", message);
  setText("jarvisAnswer", "Jarvis denkt...");
  setVoiceStatus("Befehl wird gesendet.");
  setDesktopAgentState("Jarvis denkt", "Jarvis verarbeitet den Befehl.");
  addChatMessage("user", message);

  try {
    let response;
    try {
      response = await postJson("/assistant/chat", { message, confirm: false }, {
        activityId: chatActivityId,
        activityTitle: "Jarvis verarbeitet die Anfrage",
        activityDetail: "Assistant-Endpunkt wird aufgerufen",
        timeoutMs: 30000,
      });
    } catch (assistantError) {
      if (!isLegacyHomeAssistantCommand(message)) {
        const errorText = "Der neue Assistant-Endpunkt hat einen Fehler gemeldet. Bitte prüfe die Backend-Konsole.";
        failActivity(chatActivityId, "Assistant-Endpunkt hat einen Fehler gemeldet.");
        setText("jarvisAnswer", errorText);
        setVoiceStatus(errorText, "error");
        addChatMessage("assistant", errorText);
        setDesktopAgentState("Fehler", errorText);
        scheduleHandsFreeResume();
        return;
      }
      updateActivity(chatActivityId, { detail: "Legacy-Home-Assistant-Endpunkt wird genutzt." });
      response = await postJson("/chat", { message }, {
        activityId: chatActivityId,
        activityTitle: "Jarvis verarbeitet die Anfrage",
        activityDetail: "Legacy-Endpunkt wird aufgerufen",
        timeoutMs: 30000,
      });
    }
    const answer = extractChatAnswer(response);
    updateActivity(chatActivityId, { detail: "Antwort wird angezeigt." });
    setText("jarvisAnswer", answer);
    setVoiceStatus("Antwort empfangen.");
    addChatMessage("assistant", answer, response.knowledge_sources || []);
    if (speechOutputEnabled) {
      speakAnswer(answer);
    } else {
      setDesktopAgentState("Bereit", "Desktop-Agent bereit.");
      scheduleHandsFreeResume();
    }
    finishActivity(chatActivityId, "Antwort empfangen.");
  } catch (error) {
    const errorText = "Verbindung zum Hammer-Jarvis-Backend fehlgeschlagen.";
    if (error.kind === "timeout") {
      timeoutActivity(chatActivityId, error.message);
    } else {
      failActivity(chatActivityId, "Backend-Verbindung fehlgeschlagen.");
    }
    setText("jarvisAnswer", errorText);
    setVoiceStatus(errorText, "error");
    addChatMessage("assistant", errorText);
    setDesktopAgentState("Fehler", errorText);
    scheduleHandsFreeResume();
  }
}

function speakAnswer(answer) {
  if (!("speechSynthesis" in window)) {
    setVoiceStatus("Sprachausgabe wird von diesem Browser nicht unterstützt.", "error");
    scheduleHandsFreeResume();
    return;
  }
  cancelSpeechOutput(false);
  if (!speechOutputEnabled) {
    scheduleHandsFreeResume();
    return;
  }
  const preparedText = prepareSpeechText(answer);
  if (!preparedText) {
    setVoiceStatus("Keine verwertbare Textausgabe für die Sprachausgabe.", "error");
    scheduleHandsFreeResume();
    return;
  }
  const chunks = splitSpeechText(preparedText);
  if (chunks.length === 0) {
    setVoiceStatus("Keine verwertbare Textausgabe für die Sprachausgabe.", "error");
    scheduleHandsFreeResume();
    return;
  }
  pauseWakeStreaming();
  isAssistantSpeaking = true;
  setDesktopAgentState("Jarvis spricht", "Jarvis spricht.");
  setHandsFreeState(HANDS_FREE_STATES.SPEAKING, "Jarvis spricht. Weckwort-Erkennung pausiert.");
  const runId = ++speechRunId;
  if (speechActivityId && activities.has(speechActivityId)) {
    cancelActivity(speechActivityId, "Neue Sprachausgabe gestartet.");
  }
  speechActivityId = `speech-${Date.now()}`;
  startActivity(speechActivityId, "Jarvis spricht", {
    detail: "Sprachausgabe wird vorbereitet",
    progress: `0 von ${chunks.length} Abschnitten`,
    category: "voice",
  });
  speakSpeechChunkQueue(chunks, runId, chunks.length);
}

function cancelSpeechOutput(showReadyStatus = true) {
  speechRunId += 1;
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
  if (speechActivityId && activities.has(speechActivityId)) {
    cancelActivity(speechActivityId, "Sprachausgabe abgebrochen.");
  }
  if (showReadyStatus) {
    setVoiceStatus("Sprachsteuerung bereit.");
  }
}

function speakSpeechChunkQueue(chunks, runId, totalChunks = chunks.length) {
  if (runId !== speechRunId || !speechOutputEnabled || chunks.length === 0) {
    return;
  }
  const chunk = chunks.shift();
  const currentChunk = totalChunks - chunks.length;
  if (speechActivityId && activities.has(speechActivityId)) {
    updateActivity(speechActivityId, {
      detail: "Audioausgabe läuft",
      progress: `${currentChunk} von ${totalChunks} Abschnitten`,
    });
  }
  const utterance = new SpeechSynthesisUtterance(chunk);
  const voice = getSelectedSpeechVoice();
  utterance.lang = speechDefaults.lang;
  utterance.rate = speechDefaults.rate;
  utterance.pitch = speechDefaults.pitch;
  utterance.volume = speechDefaults.volume;
  if (voice) {
    utterance.voice = voice;
  } else if (speechVoices.length === 0) {
    setText("voiceSelectStatus", "Keine Browser-Stimmen geladen. Browserstandard wird verwendet.");
  }
  utterance.onstart = () => {
    if (runId === speechRunId) {
      setVoiceStatus("Jarvis spricht.", "speaking");
    }
  };
  utterance.onend = () => {
    if (runId !== speechRunId) {
      return;
    }
    if (chunks.length > 0 && speechOutputEnabled) {
      window.setTimeout(() => speakSpeechChunkQueue(chunks, runId, totalChunks), 80);
      return;
    }
    setVoiceStatus("Sprachsteuerung bereit.");
    isAssistantSpeaking = false;
    setDesktopAgentState("Cooldown", "Jarvis hat geantwortet. Kurzer Cooldown.");
    scheduleHandsFreeResume();
    if (speechActivityId && activities.has(speechActivityId)) {
      finishActivity(speechActivityId, "Sprachausgabe abgeschlossen.");
    }
  };
  utterance.onerror = (event) => {
    if (runId !== speechRunId) {
      return;
    }
    const reason = event?.error ? ` (${event.error})` : "";
    isAssistantSpeaking = false;
    setDesktopAgentState("Fehler", `Sprachausgabe fehlgeschlagen${reason}.`);
    setVoiceStatus(`Sprachausgabe fehlgeschlagen${reason}.`, "error");
    scheduleHandsFreeResume();
    if (speechActivityId && activities.has(speechActivityId)) {
      failActivity(speechActivityId, `Sprachausgabe fehlgeschlagen${reason}.`);
    }
  };
  try {
    window.speechSynthesis.speak(utterance);
  } catch (error) {
    if (runId === speechRunId) {
      isAssistantSpeaking = false;
      setDesktopAgentState("Fehler", "Sprachausgabe konnte nicht gestartet werden.");
      setVoiceStatus("Sprachausgabe konnte nicht gestartet werden.", "error");
      scheduleHandsFreeResume();
      if (speechActivityId && activities.has(speechActivityId)) {
        failActivity(speechActivityId, "Sprachausgabe konnte nicht gestartet werden.");
      }
    }
  }
}

function prepareSpeechText(value) {
  let prepared = text(value, "").trim();
  if (!prepared) {
    return "";
  }
  prepared = prepared.replace(/```[\s\S]*?```/g, " Ein technischer Codeabschnitt wurde ausgelassen. ");
  prepared = prepared.replace(/https?:\/\/[^\s)]+/gi, " Link ausgelassen. ");
  prepared = prepared.replace(/`([^`]+)`/g, "$1");
  prepared = prepared.replace(/^\s{0,3}#{1,6}\s*/gm, "");
  prepared = prepared.replace(/^\s{0,3}>\s?/gm, "");
  prepared = prepared.replace(/^\s*[-*+]\s+/gm, ". ");
  prepared = prepared.replace(/^\s*\d+[\.)]\s+/gm, ". ");
  prepared = prepared.replace(/[*_~|]/g, " ");
  prepared = prepared.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  prepared = prepared.replace(/\s+/g, " ");
  prepared = prepared.replace(/\s+([.,;:!?])/g, "$1");
  return prepared.trim();
}

function splitSpeechText(value) {
  const prepared = text(value, "").trim();
  if (!prepared) {
    return [];
  }
  const sentences = prepared.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [prepared];
  const chunks = [];
  let current = "";
  for (const sentence of sentences.map((item) => item.trim()).filter(Boolean)) {
    const next = current ? `${current} ${sentence}` : sentence;
    if (next.length <= speechDefaults.maxChunkLength) {
      current = next;
      continue;
    }
    if (current) {
      chunks.push(current);
    }
    if (sentence.length > speechDefaults.maxChunkLength) {
      chunks.push(...splitLongSpeechSegment(sentence));
      current = "";
    } else {
      current = sentence;
    }
  }
  if (current) {
    chunks.push(current);
  }
  return chunks;
}

function splitLongSpeechSegment(segment) {
  const words = segment.split(/\s+/).filter(Boolean);
  const chunks = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > speechDefaults.targetChunkLength && current) {
      chunks.push(current);
      current = word;
    } else {
      current = next;
    }
  }
  if (current) {
    chunks.push(current);
  }
  return chunks;
}

function validateVoiceDomElements() {
  const missing = requiredVoiceElementIds.filter((id) => !elements[id]);
  if (missing.length > 0) {
    console.error("[Hammer Jarvis Voice] Fehlende Voice-DOM-Elemente", missing);
    renderVoiceInitializationError(new Error(`Fehlende Voice-DOM-Elemente: ${missing.join(", ")}`));
    return false;
  }
  return true;
}

function renderVoiceInitializationError(error) {
  clearVoiceLoadTimers();
  voiceLoadInProgress = false;
  setVoiceLoadState(VOICE_LOAD_STATES.ERROR);
  setVoiceSelectUnavailable(
    "Keine Browser-Stimmen verfügbar",
    "Stimmeninitialisierung fehlgeschlagen. Dashboard läuft weiter.",
  );
  setText("voiceProgressText", "Voice-Bootstrap wurde mit Fehler beendet.");
  updateVoiceDiagnostic(speechVoices.length);
  failActivity("voice-load", "Stimmeninitialisierung fehlgeschlagen.");
  console.error("[Hammer Jarvis Voice] Initialisierung fehlgeschlagen", error);
}

function initializeVoiceSubsystemSafely() {
  try {
    if (!validateVoiceDomElements()) {
      return;
    }
    startVoiceLoadingCycle();
    if (voiceLoadState === VOICE_LOAD_STATES.IDLE) {
      console.error("[Hammer Jarvis Voice] Bootstrap beendet, aber Zustand blieb idle.");
      renderVoiceInitializationError(new Error("Voice-Zustand blieb nach Bootstrap idle."));
    }
  } catch (error) {
    renderVoiceInitializationError(error);
  }
}

function startVoiceLoadingCycle() {
  const generation = voiceLoadGeneration + 1;
  try {
    if (!validateVoiceDomElements()) {
      return;
    }
    cancelVoiceLoadingCycle(VOICE_LOAD_STATES.CANCELLED, false);
    voiceLoadGeneration = generation;
    voiceLoadAttempt = 0;
    voiceLoadStartTime = Date.now();
    voiceLoadInProgress = true;
    voiceLoadDiagnosticsLogged = false;
    setVoiceLoadState(VOICE_LOAD_STATES.LOADING);
    startActivity("voice-load", "Browser-Stimmen werden geladen", {
      detail: `Versuch 0 von ${VOICE_RETRY_DELAYS_MS.length}`,
      retry: 0,
      retryTotal: VOICE_RETRY_DELAYS_MS.length,
      category: "voice",
      timeoutMs: VOICE_LOAD_WATCHDOG_MS,
    });
    registerSpeechVoicesChangedListener();
    if (!("speechSynthesis" in window)) {
      finishVoiceLoadingCycle(
        VOICE_LOAD_STATES.UNSUPPORTED,
        "Sprachausgabe wird von diesem Browser nicht unterstützt.",
      );
      return;
    }
    setVoiceSelectLoading();
    voiceLoadElapsedTimer = window.setInterval(() => updateVoiceLoadingProgress(generation), VOICE_LOAD_ELAPSED_UPDATE_MS);
    for (const [index, delay] of VOICE_RETRY_DELAYS_MS.entries()) {
      const timer = window.setTimeout(() => runVoiceLoadAttempt(generation, index + 1), delay);
      voiceLoadTimers.push(timer);
    }
    const watchdog = window.setTimeout(() => {
      if (generation !== voiceLoadGeneration || isFinalVoiceLoadState()) {
        return;
      }
      finishVoiceLoadingCycle(VOICE_LOAD_STATES.EMPTY, "0 Stimmen geladen · Suche nach 5 Sekunden beendet");
    }, VOICE_LOAD_WATCHDOG_MS);
    voiceLoadTimers.push(watchdog);
    updateVoiceLoadingProgress(generation);
  } catch (error) {
    handleVoiceLoadingError(error, generation);
  }
}

function cancelVoiceLoadingCycle(nextState = VOICE_LOAD_STATES.CANCELLED, updateUi = true) {
  clearVoiceLoadTimers();
  voiceLoadInProgress = false;
  if (updateUi) {
    setVoiceLoadState(nextState);
  }
}

function clearVoiceLoadTimers() {
  for (const timer of voiceLoadTimers) {
    window.clearTimeout(timer);
  }
  voiceLoadTimers = [];
  if (voiceLoadElapsedTimer) {
    window.clearInterval(voiceLoadElapsedTimer);
    voiceLoadElapsedTimer = null;
  }
}

function runVoiceLoadAttempt(generation, attempt) {
  if (generation !== voiceLoadGeneration || isFinalVoiceLoadState()) {
    return;
  }
  try {
    voiceLoadAttempt = attempt;
    updateVoiceLoadingProgress(generation);
    const voices = readBrowserVoices();
    if (voices.length > 0) {
      applyAvailableVoices(voices);
      return;
    }
    if (attempt >= VOICE_RETRY_DELAYS_MS.length) {
      finishVoiceLoadingCycle(VOICE_LOAD_STATES.EMPTY, "0 Stimmen geladen · Suche nach 5 Sekunden beendet");
    }
  } catch (error) {
    handleVoiceLoadingError(error, generation);
  }
}

function readBrowserVoices() {
  if (!("speechSynthesis" in window)) {
    return [];
  }
  return getValidSpeechVoices(window.speechSynthesis.getVoices());
}

function applyAvailableVoices(voices) {
  if (!voices || voiceLoadState === VOICE_LOAD_STATES.ERROR || voiceLoadState === VOICE_LOAD_STATES.UNSUPPORTED) {
    return;
  }
  const validVoices = getValidSpeechVoices(voices);
  if (validVoices.length === 0) {
    updateVoiceDiagnostic(0);
    return;
  }
  speechVoices = validVoices;
  clearVoiceLoadTimers();
  voiceLoadInProgress = false;
  setVoiceLoadState(VOICE_LOAD_STATES.SUCCESS);
  populateVoiceSelectFromState(validVoices);
  const germanCount = germanSpeechVoices(validVoices).length;
  const selectedVoice = getSelectedSpeechVoice();
  const statusText = germanCount > 0
    ? `${validVoices.length} Stimmen geladen · ${germanCount} deutsch · Auswahl: ${selectedVoice?.name || "Browserstandard"}`
    : `${validVoices.length} Stimmen geladen · keine deutsche Stimme gefunden`;
  setVoiceStatusText(statusText);
  setText("voiceSelectStatus", statusText);
  setText("voiceProgressText", `Versuch ${voiceLoadAttempt || 1} von ${VOICE_RETRY_DELAYS_MS.length} · ${formatDuration(Date.now() - voiceLoadStartTime)}`);
  updateVoiceDiagnostic(validVoices.length);
  logSpeechVoiceDiagnostics();
  finishActivity("voice-load", statusText);
}

function finishVoiceLoadingCycle(state, statusText) {
  if (isFinalVoiceLoadState()) {
    return;
  }
  clearVoiceLoadTimers();
  voiceLoadInProgress = false;
  setVoiceLoadState(state);
  if (state === VOICE_LOAD_STATES.EMPTY) {
    speechVoices = [];
    setVoiceSelectUnavailable(
      "Keine Browser-Stimmen verfügbar",
      "Keine Stimmen nach 5 Sekunden. Windows-Sprachpakete oder Browser prüfen.",
    );
    setText("voiceProgressText", `Versuch ${VOICE_RETRY_DELAYS_MS.length} von ${VOICE_RETRY_DELAYS_MS.length} · ${formatDuration(Date.now() - voiceLoadStartTime)}`);
    updateVoiceDiagnostic(0);
    logSpeechVoiceDiagnostics();
    timeoutActivity("voice-load", statusText);
    return;
  }
  if (state === VOICE_LOAD_STATES.UNSUPPORTED) {
    setVoiceSelectUnavailable("Sprachausgabe nicht unterstützt", statusText);
    setText("voiceProgressText", "Keine Web Speech API verfügbar.");
    updateVoiceDiagnostic(0);
    failActivity("voice-load", statusText);
    return;
  }
  setVoiceStatusText(statusText);
  updateVoiceDiagnostic(speechVoices.length);
}

function handleVoiceLoadingError(error, generation = voiceLoadGeneration) {
  if (generation !== voiceLoadGeneration) {
    return;
  }
  clearVoiceLoadTimers();
  voiceLoadInProgress = false;
  setVoiceLoadState(VOICE_LOAD_STATES.ERROR);
  setVoiceSelectUnavailable(
    "Keine Browser-Stimmen verfügbar",
    "Stimmeninitialisierung fehlgeschlagen. Dashboard läuft weiter.",
  );
  updateVoiceDiagnostic(speechVoices.length);
  failActivity("voice-load", "Stimmeninitialisierung fehlgeschlagen.");
  console.error("[Hammer Jarvis Voice] Stimmenladezyklus fehlgeschlagen.", error);
}

function registerSpeechVoicesChangedListener() {
  if (speechVoicesListenerRegistered || !("speechSynthesis" in window)) {
    return;
  }
  const onVoicesChanged = () => {
    const generation = voiceLoadGeneration;
    try {
      const voices = readBrowserVoices();
      if (generation !== voiceLoadGeneration) {
        return;
      }
      if (voices.length > 0) {
        applyAvailableVoices(voices);
      } else {
        updateVoiceDiagnostic(0);
      }
    } catch (error) {
      handleVoiceLoadingError(error);
    }
  };
  if (typeof window.speechSynthesis.addEventListener === "function") {
    window.speechSynthesis.addEventListener("voiceschanged", onVoicesChanged);
  } else {
    window.speechSynthesis.onvoiceschanged = onVoicesChanged;
  }
  speechVoicesListenerRegistered = true;
}

function getValidSpeechVoices(voices) {
  try {
    return Array.from(voices || []).filter((voice) => String(voice?.name || voice?.voiceURI || "").trim());
  } catch (error) {
    return [];
  }
}

function isGermanVoice(voice) {
  return String(voice?.lang || "").toLowerCase().startsWith("de");
}

function germanSpeechVoices(voices) {
  return getValidSpeechVoices(voices).filter(isGermanVoice);
}

function choosePreferredGermanVoice(voices) {
  const germanVoices = germanSpeechVoices(voices);
  const byName = (needle) => germanVoices.find((voice) => String(voice?.name || "").toLowerCase().includes(needle));
  return (
    byName("natural")
    || byName("online")
    || byName("katja")
    || byName("conrad")
    || germanVoices.find((voice) => String(voice?.lang || "").toLowerCase() === "de-de")
    || germanVoices[0]
    || null
  );
}

function chooseFallbackSpeechVoice(voices) {
  const validVoices = getValidSpeechVoices(voices);
  return choosePreferredGermanVoice(validVoices)
    || validVoices.find((voice) => Boolean(voice?.default))
    || validVoices[0]
    || null;
}

function populateVoiceSelectFromState(voices) {
  const select = elements.voiceSelect;
  if (!select) {
    console.warn("[Hammer Jarvis Voice] voiceSelect nicht gefunden.");
    return;
  }
  const validVoices = getValidSpeechVoices(voices);
  const germanVoices = germanSpeechVoices(validVoices);
  if (validVoices.length === 0) {
    setVoiceSelectUnavailable(
      "Keine Browser-Stimmen verfügbar",
      "Keine Stimmen nach 5 Sekunden. Windows-Sprachpakete oder Browser prüfen.",
    );
    return;
  }

  const visibleVoices = germanVoices.length > 0 ? germanVoices : validVoices;
  const storedVoiceId = readStoredVoiceId();
  const previousValue = select.value || storedVoiceId;
  const automaticVoice = germanVoices.length > 0 ? choosePreferredGermanVoice(validVoices) : chooseFallbackSpeechVoice(validVoices);
  select.innerHTML = "";
  select.disabled = false;
  for (const voice of visibleVoices) {
    const option = document.createElement("option");
    option.value = voiceId(voice);
    option.textContent = voiceLabel(voice);
    select.appendChild(option);
  }
  const automaticVoiceId = automaticVoice ? voiceId(automaticVoice) : "";
  const storedStillAvailable = visibleVoices.some((voice) => voiceId(voice) === storedVoiceId);
  const previousStillAvailable = visibleVoices.some((voice) => voiceId(voice) === previousValue);
  select.value = storedStillAvailable ? storedVoiceId : previousStillAvailable ? previousValue : automaticVoiceId;
  if (select.value) {
    storeVoiceId(select.value);
  }
}

function setVoiceSelectLoading() {
  const select = elements.voiceSelect;
  if (!select) {
    return;
  }
  select.innerHTML = "";
  const option = document.createElement("option");
  option.value = "";
  option.textContent = "Stimmen werden geladen...";
  select.appendChild(option);
  select.disabled = true;
  setVoiceStatusText("Browser-Stimmen werden geladen");
  setText("voiceSelectStatus", "Browser-Stimmen werden geladen.");
}

function setVoiceSelectUnavailable(optionText, statusText) {
  const select = elements.voiceSelect;
  if (!select) {
    return;
  }
  select.innerHTML = "";
  const option = document.createElement("option");
  option.value = "";
  option.textContent = optionText;
  select.appendChild(option);
  select.disabled = true;
  setVoiceStatusText(statusText);
  setText("voiceSelectStatus", statusText);
}

function setVoiceLoadState(state) {
  voiceLoadState = state;
  const panel = elements.voiceLoadingPanel;
  if (panel) {
    panel.classList.remove(
      "voice-loading",
      "voice-success",
      "voice-empty",
      "voice-unsupported",
      "voice-error",
      "voice-cancelled",
    );
    panel.classList.add(`voice-${state}`);
    panel.setAttribute("aria-busy", state === VOICE_LOAD_STATES.LOADING ? "true" : "false");
  }
  if (elements.reloadVoices) {
    if (!elements.reloadVoices.dataset.originalText) {
      elements.reloadVoices.dataset.originalText = elements.reloadVoices.textContent;
    }
    elements.reloadVoices.disabled = state === VOICE_LOAD_STATES.LOADING;
    elements.reloadVoices.classList.toggle("button-loading", state === VOICE_LOAD_STATES.LOADING);
    elements.reloadVoices.textContent = state === VOICE_LOAD_STATES.LOADING
      ? "Stimmen werden gesucht..."
      : elements.reloadVoices.dataset.originalText;
  }
}

function setVoiceStatusText(value) {
  setText("voiceStatusText", value);
}

function updateVoiceLoadingProgress(generation) {
  if (generation !== voiceLoadGeneration || voiceLoadState !== VOICE_LOAD_STATES.LOADING) {
    return;
  }
  const elapsed = voiceLoadStartTime ? formatDuration(Date.now() - voiceLoadStartTime) : "0 Sekunden";
  const attempt = Math.max(voiceLoadAttempt, 1);
  setVoiceStatusText("Browser-Stimmen werden geladen");
  setText("voiceProgressText", `Versuch ${attempt} von ${VOICE_RETRY_DELAYS_MS.length} · läuft seit ${elapsed}`);
  setText("voiceSelectStatus", `Browser-Stimmen werden geladen. Versuch ${attempt} von ${VOICE_RETRY_DELAYS_MS.length}.`);
  updateVoiceDiagnostic(speechVoices.length);
  updateActivity("voice-load", {
    status: "retrying",
    retry: attempt,
    retryTotal: VOICE_RETRY_DELAYS_MS.length,
    detail: `läuft seit ${elapsed}`,
  });
}

function updateVoiceDiagnostic(totalVoices) {
  const apiStatus = "speechSynthesis" in window ? "verfügbar" : "nicht verfügbar";
  setText("voiceDiagnosticText", `Build: ${DASHBOARD_BUILD} · TTS API: ${apiStatus} · getVoices(): ${totalVoices} · Zustand: ${voiceLoadState}`);
}

function isFinalVoiceLoadState() {
  return [
    VOICE_LOAD_STATES.SUCCESS,
    VOICE_LOAD_STATES.EMPTY,
    VOICE_LOAD_STATES.UNSUPPORTED,
    VOICE_LOAD_STATES.ERROR,
    VOICE_LOAD_STATES.CANCELLED,
  ].includes(voiceLoadState) && !voiceLoadInProgress;
}

function getSelectedSpeechVoice() {
  const selectedId = elements.voiceSelect?.value || readStoredVoiceId();
  const selectedVoice = speechVoices.find((voice) => voiceId(voice) === selectedId);
  return selectedVoice || chooseFallbackSpeechVoice(speechVoices);
}

function voiceId(voice) {
  return [voice?.voiceURI || "", voice?.name || "", voice?.lang || ""].join("||");
}

function voiceLabel(voice) {
  const name = String(voice?.name || "Unbenannte Stimme").trim();
  const lang = String(voice?.lang || "Sprache unbekannt").trim();
  return `${name} — ${lang}`;
}

function logSpeechVoiceDiagnostics() {
  if (voiceLoadDiagnosticsLogged) {
    return;
  }
  const allCount = speechVoices.length;
  const germanCount = germanSpeechVoices(speechVoices).length;
  const selectedVoice = getSelectedSpeechVoice();
  console.info("[Hammer Jarvis Voice]", {
    state: voiceLoadState,
    totalVoices: allCount,
    germanVoices: germanCount,
    selectedVoice: selectedVoice?.name || "Browserstandard",
    attempts: voiceLoadAttempt,
    durationMs: voiceLoadStartTime ? Date.now() - voiceLoadStartTime : 0,
  });
  voiceLoadDiagnosticsLogged = true;
}

function readStoredVoiceId() {
  try {
    return localStorage.getItem(speechVoiceStorageKey) || "";
  } catch (error) {
    return "";
  }
}

function storeVoiceId(value) {
  try {
    localStorage.setItem(speechVoiceStorageKey, value);
  } catch (error) {
    setText("voiceSelectStatus", "Stimme ausgewählt, aber lokale Speicherung ist nicht verfügbar.");
  }
}

function removeStoredVoiceId() {
  try {
    localStorage.removeItem(speechVoiceStorageKey);
  } catch (error) {
    // localStorage can be unavailable in strict browser privacy modes.
  }
}

function reloadSpeechVoices() {
  try {
    startVoiceLoadingCycle();
  } catch (error) {
    renderVoiceInitializationError(error);
  }
}

function setHandsFreeState(state, message = "") {
  handsFreeState = state;
  const active = ![HANDS_FREE_STATES.DISABLED, HANDS_FREE_STATES.ERROR].includes(state);
  const wakeDetected = state === HANDS_FREE_STATES.WAKE_DETECTED || state === HANDS_FREE_STATES.COMMAND_LISTENING;
  elements.voiceCard?.classList.toggle("hands-free-armed", state === HANDS_FREE_STATES.ARMED);
  elements.voiceCard?.classList.toggle("wake-detected", wakeDetected);
  elements.handsFreeToggle?.classList.toggle("active", active);
  elements.handsFreeToggle?.classList.toggle("wake-detected", wakeDetected);
  elements.handsFreeChatToggle?.classList.toggle("active", active);
  elements.handsFreeChatToggle?.classList.toggle("wake-detected", wakeDetected);
  elements.handsFreeToggle && (elements.handsFreeToggle.textContent = active ? "Browser-Fallback: Ein" : "Browser-Fallback: Aus");
  elements.handsFreeChatToggle && (elements.handsFreeChatToggle.textContent = active ? "Browser-Fallback: Ein" : "Browser-Fallback: Aus");
  const panel = elements.handsFreeDetails?.closest(".hands-free-panel");
  panel?.classList.toggle("active", active);
  panel?.classList.toggle("error", state === HANDS_FREE_STATES.ERROR);
  if (message) {
    setText("handsFreeStatus", message);
    setText("handsFreeDetails", message);
  }
}

async function refreshWakeWordStatus() {
  const status = await fetchJson("/assistant/voice/wake/status", { timeoutMs: 6000 });
  handsFreeConfig = { ...handsFreeConfig, ...status };
  return status;
}

async function toggleHandsFreeMode() {
  if (handsFreeWanted) {
    stopHandsFreeMode("Freihändiger Modus ausgeschaltet.");
    return;
  }
  await startHandsFreeMode();
}

async function startHandsFreeMode() {
  if (handsFreeWanted || handsFreeState === HANDS_FREE_STATES.STARTING) {
    return;
  }
  handsFreeWanted = true;
  storeHandsFreeWanted(true);
  setHandsFreeState(HANDS_FREE_STATES.STARTING, "Lokale Weckwort-Erkennung wird gestartet.");
  startActivity("hands-free", "Freihändige Sprachsteuerung wird gestartet", {
    detail: "Status und Mikrofon werden geprüft",
    category: "voice",
    timeoutMs: 20000,
  });
  try {
    const status = await refreshWakeWordStatus();
    if (!status.enabled) {
      throw new Error("Wake Word ist nicht aktiviert. Setze WAKE_WORD_ENABLED=true in .env.");
    }
    if (!status.installed || !status.model_available) {
      throw new Error("openWakeWord ist nicht installiert oder das Modell ist nicht verfügbar. Führe .\\scripts\\setup-wake-word.ps1 aus.");
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("Mikrofonzugriff wird von diesem Browser nicht unterstützt.");
    }
    await startWakeAudioPipeline();
    await openWakeWordSocket();
    setHandsFreeState(HANDS_FREE_STATES.ARMED, "Browser-Fallback aktiv. Das konfigurierte openWakeWord-Modell lauscht lokal.");
    finishActivity("hands-free", "Freihändiger Modus aktiv.");
  } catch (error) {
    stopHandsFreeMode(error.message || "Freihändiger Modus konnte nicht gestartet werden.", true);
    failActivity("hands-free", error.message || "Freihändiger Modus konnte nicht gestartet werden.");
  }
}

function stopHandsFreeMode(message = "Freihändiger Modus ausgeschaltet.", isError = false) {
  handsFreeWanted = false;
  storeHandsFreeWanted(false);
  clearHandsFreeTimers();
  closeWakeWordSocket();
  stopWakeAudioPipeline();
  setHandsFreeState(isError ? HANDS_FREE_STATES.ERROR : HANDS_FREE_STATES.DISABLED, message);
  if (!isError && activities.has("hands-free")) {
    cancelActivity("hands-free", message);
  }
}

async function startWakeAudioPipeline() {
  handsFreeMediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
    },
  });
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextCtor) {
    throw new Error("Web Audio API wird von diesem Browser nicht unterstützt.");
  }
  handsFreeAudioContext = new AudioContextCtor();
  if (handsFreeAudioContext.state === "suspended") {
    await handsFreeAudioContext.resume();
  }
  const frameSize = Math.round((handsFreeConfig.sample_rate || 16000) * (handsFreeConfig.frame_ms || 80) / 1000);
  await handsFreeAudioContext.audioWorklet.addModule(`/static/audio/wake-word-processor.js?v=${DASHBOARD_BUILD}`);
  handsFreeWorklet = new AudioWorkletNode(handsFreeAudioContext, "wake-word-processor", {
    processorOptions: {
      targetSampleRate: handsFreeConfig.sample_rate || 16000,
      frameSize,
    },
  });
  handsFreeWorklet.port.onmessage = (event) => {
    if (!handsFreeWanted || handsFreeStreamingPaused || handsFreeState !== HANDS_FREE_STATES.ARMED) {
      return;
    }
    if (handsFreeSocket?.readyState === WebSocket.OPEN && event.data?.type === "pcm_frame") {
      handsFreeSocket.send(event.data.frame);
    }
  };
  handsFreeSource = handsFreeAudioContext.createMediaStreamSource(handsFreeMediaStream);
  handsFreeSource.connect(handsFreeWorklet);
  handsFreeStreamingPaused = false;
}

function stopWakeAudioPipeline() {
  handsFreeStreamingPaused = true;
  try {
    handsFreeSource?.disconnect();
    handsFreeWorklet?.disconnect();
  } catch (error) {
    // Disconnect can throw if nodes were never connected.
  }
  handsFreeSource = null;
  handsFreeWorklet = null;
  if (handsFreeMediaStream) {
    for (const track of handsFreeMediaStream.getTracks()) {
      track.stop();
    }
  }
  handsFreeMediaStream = null;
  if (handsFreeAudioContext) {
    handsFreeAudioContext.close().catch(() => {});
  }
  handsFreeAudioContext = null;
}

function openWakeWordSocket() {
  return new Promise((resolve, reject) => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/assistant/voice/wake/stream`;
    handsFreeSocket = new WebSocket(url);
    handsFreeSocket.binaryType = "arraybuffer";
    let resolved = false;
    const startupTimer = window.setTimeout(() => {
      if (!resolved) {
        reject(new Error("Verbindung zur lokalen Weckwort-Erkennung wurde nicht rechtzeitig geöffnet."));
      }
    }, 6000);
    handsFreeSocket.onopen = () => {
      handsFreeReconnectAttempt = 0;
      updateActivity("hands-free", { detail: "WebSocket verbunden" });
    };
    handsFreeSocket.onmessage = (event) => {
      const payload = parseWakeWordMessage(event.data);
      if (!payload) {
        return;
      }
      if (payload.type === "ready" && !resolved) {
        window.clearTimeout(startupTimer);
        resolved = true;
        resolve();
        return;
      }
      handleWakeWordEvent(payload);
    };
    handsFreeSocket.onerror = () => {
      if (!resolved) {
        window.clearTimeout(startupTimer);
        reject(new Error("Verbindung zur lokalen Weckwort-Erkennung fehlgeschlagen."));
      }
    };
    handsFreeSocket.onclose = () => {
      window.clearTimeout(startupTimer);
      if (handsFreeWanted) {
        scheduleWakeWordReconnect();
      }
    };
  });
}

function closeWakeWordSocket() {
  if (handsFreeSocket) {
    handsFreeSocket.onclose = null;
    handsFreeSocket.close();
  }
  handsFreeSocket = null;
}

function parseWakeWordMessage(value) {
  try {
    return JSON.parse(value);
  } catch (error) {
    return null;
  }
}

function handleWakeWordEvent(payload) {
  if (payload.type === "wake_detected") {
    pauseWakeStreaming();
    setHandsFreeState(HANDS_FREE_STATES.WAKE_DETECTED, "Browser-Fallback hat ein Wake-Ereignis erkannt. Ich höre den nächsten Befehl.");
    playWakeBeep();
    startHandsFreeCommandRecognition();
    return;
  }
  if (payload.type === "error") {
    const message = payload.message || "Wake-Word-Erkennung meldet einen Fehler.";
    setHandsFreeState(HANDS_FREE_STATES.ERROR, message);
    return;
  }
  if (payload.type === "status" && handsFreeState === HANDS_FREE_STATES.ARMED) {
    setText("handsFreeStatus", "Browser-Fallback aktiv.");
  }
}

function pauseWakeStreaming() {
  handsFreeStreamingPaused = true;
}

function resumeWakeStreaming() {
  if (!handsFreeWanted || isListening) {
    return;
  }
  handsFreeStreamingPaused = false;
  setHandsFreeState(HANDS_FREE_STATES.ARMED, "Browser-Fallback aktiv.");
}

function scheduleHandsFreeResume(delayMs = handsFreeConfig.cooldown_ms || 1800) {
  if (!handsFreeWanted) {
    return;
  }
  clearTimeout(handsFreeResumeTimer);
  setHandsFreeState(HANDS_FREE_STATES.COOLDOWN, "Kurze Pause, dann wird der Browser-Fallback wieder aktiv.");
  handsFreeResumeTimer = window.setTimeout(() => resumeWakeStreaming(), delayMs);
}

function clearHandsFreeTimers() {
  clearTimeout(handsFreeReconnectTimer);
  clearTimeout(handsFreeResumeTimer);
  clearTimeout(handsFreeCommandTimer);
  handsFreeReconnectTimer = null;
  handsFreeResumeTimer = null;
  handsFreeCommandTimer = null;
}

function scheduleWakeWordReconnect() {
  const delay = HANDS_FREE_RECONNECT_DELAYS_MS[Math.min(handsFreeReconnectAttempt, HANDS_FREE_RECONNECT_DELAYS_MS.length - 1)];
  handsFreeReconnectAttempt += 1;
  setHandsFreeState(HANDS_FREE_STATES.STARTING, `Verbindung zur lokalen Weckwort-Erkennung wird neu aufgebaut (${delay / 1000}s).`);
  handsFreeReconnectTimer = window.setTimeout(async () => {
    if (!handsFreeWanted) {
      return;
    }
    try {
      await openWakeWordSocket();
      resumeWakeStreaming();
    } catch (error) {
      if (handsFreeReconnectAttempt >= HANDS_FREE_RECONNECT_DELAYS_MS.length) {
        stopHandsFreeMode("Verbindung zur lokalen Weckwort-Erkennung konnte nicht wiederhergestellt werden.", true);
      }
    }
  }, delay);
}

function startHandsFreeCommandRecognition() {
  setHandsFreeState(HANDS_FREE_STATES.COMMAND_LISTENING, "Ich höre den Befehl.");
  startCommandRecognition({
    source: "desktop_agent",
    autoSend: true,
    timeoutMs: handsFreeConfig.command_timeout_ms || 9000,
    initialPrompt: "Jarvis wurde aktiviert. Ich höre zu...",
  });
}

function cleanHandsFreeCommand(value) {
  return text(value, "").replace(/^\s*(hey\s+)?jarvis[:,\-\s]*/i, "").trim() || value;
}

function playWakeBeep() {
  try {
    const context = handsFreeAudioContext || new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = 880;
    gain.gain.setValueAtTime(0.0001, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.08, context.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.16);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.18);
  } catch (error) {
    // Audio feedback is optional.
  }
}

function storeHandsFreeWanted(value) {
  try {
    localStorage.setItem(HANDS_FREE_STORAGE_KEY, value ? "true" : "false");
  } catch (error) {
    // Hands-free mode still works without persistent preference.
  }
}

function initializeHandsFreeStatus() {
  refreshWakeWordStatus()
    .then((status) => {
      const configured = status.enabled && status.installed && status.model_available;
      setText("handsFreeStatus", configured ? "Browser-Fallback verfügbar." : "Desktop-Agent: Nicht verbunden. Browser-Fallback optional.");
    })
    .catch(() => {
      setText("handsFreeStatus", "Wake-Word-Status konnte nicht geladen werden.");
    });
}

function setDesktopAgentState(state, detail = "") {
  desktopAgentState = state || desktopAgentState;
  setText("desktopAgentStatus", desktopAgentState);
  if (detail) {
    setText("handsFreeStatus", detail);
  }
}

function connectDesktopEventBridge() {
  clearTimeout(desktopEventReconnectTimer);
  if (desktopEventSocket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(desktopEventSocket.readyState)) {
    return;
  }
  setDesktopAgentState("Verbindung wird hergestellt", "Desktop-Agent-Verbindung wird hergestellt.");
  desktopEventSocket = new WebSocket(buildDesktopEventSocketUrl());
  desktopEventSocket.onopen = () => {
    desktopEventReconnectAttempt = 0;
    setDesktopAgentState("Bereit", "Desktop-Agent-Eventbrücke verbunden.");
    startDesktopHeartbeat();
  };
  desktopEventSocket.onmessage = (event) => {
    const payload = parseWakeWordMessage(event.data);
    if (!payload) {
      return;
    }
    handleDesktopEvent(payload);
  };
  desktopEventSocket.onerror = () => {
    setDesktopAgentState("Fehler", "Desktop-Agent-Verbindung meldet einen Fehler.");
  };
  desktopEventSocket.onclose = () => {
    stopDesktopHeartbeat();
    if (desktopEventReconnectAttempt >= DESKTOP_EVENT_RECONNECT_DELAYS_MS.length) {
      setDesktopAgentState("Fehler", "Desktop-Agent nicht verbunden. Manuelle Sprachtaste bleibt verfügbar.");
      return;
    }
    const delay = DESKTOP_EVENT_RECONNECT_DELAYS_MS[desktopEventReconnectAttempt];
    desktopEventReconnectAttempt += 1;
    setDesktopAgentState("Verbindung wird hergestellt", `Desktop-Agent-Reconnect in ${delay / 1000}s.`);
    desktopEventReconnectTimer = window.setTimeout(connectDesktopEventBridge, delay);
  };
}

function buildDesktopEventSocketUrl(locationSource = window.location) {
  const protocol = locationSource.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${locationSource.host}/assistant/desktop/events`;
}

function startDesktopHeartbeat() {
  stopDesktopHeartbeat();
  desktopEventHeartbeatTimer = window.setInterval(() => {
    if (desktopEventSocket?.readyState === WebSocket.OPEN) {
      desktopEventSocket.send(JSON.stringify({ type: "heartbeat" }));
    }
  }, 15000);
}

function stopDesktopHeartbeat() {
  clearInterval(desktopEventHeartbeatTimer);
  desktopEventHeartbeatTimer = null;
}

function handleDesktopEvent(payload) {
  if (payload.type === "desktop_status") {
    setText("desktopWakeWord", payload.wake_word || "Jarvis");
    setText("desktopWakeEngine", formatDesktopWakeEngine(payload.wake_engine, payload.agent_state));
    setDesktopAgentState(payload.agent_connected ? "Bereit" : "Nicht verbunden");
    return;
  }
  if (payload.type !== "wake_detected") {
    return;
  }
  if (payload.wake_word !== "Jarvis") {
    setDesktopAgentState("Fehler", "Wake-Ereignis mit unerwartetem Wake Word ignoriert.");
    return;
  }
  if (isListening || isAssistantSpeaking || [
    HANDS_FREE_STATES.COMMAND_LISTENING,
    HANDS_FREE_STATES.PROCESSING,
    HANDS_FREE_STATES.SPEAKING,
  ].includes(handsFreeState)) {
    setDesktopAgentState("Cooldown", "Wake-Ereignis ignoriert, weil Jarvis bereits beschäftigt ist.");
    return;
  }
  setDesktopAgentState("Jarvis erkannt", "Jarvis wurde aktiviert.");
  playWakeBeep();
  startCommandRecognition({
    source: "desktop_agent",
    autoSend: true,
    timeoutMs: handsFreeConfig.command_timeout_ms || 9000,
    initialPrompt: "Jarvis wurde aktiviert. Ich höre zu...",
  });
}

function formatDesktopWakeEngine(engine, state) {
  if (engine === "windows_speech") {
    return "Windows Speech";
  }
  if (engine === "openwakeword_custom") {
    return "openWakeWord Custom";
  }
  return state || "Unbekannt";
}

function scheduleDesktopCooldown(state = "Cooldown") {
  setDesktopAgentState(state, "Kurzer Cooldown nach der Spracherkennung.");
  window.setTimeout(() => {
    if (desktopEventSocket?.readyState === WebSocket.OPEN) {
      setDesktopAgentState("Bereit", "Desktop-Agent bereit.");
    }
  }, 1200);
}

function cleanupHandsFreeOnUnload() {
  stopDesktopHeartbeat();
  clearTimeout(desktopEventReconnectTimer);
  if (desktopEventSocket) {
    desktopEventSocket.close();
    desktopEventSocket = null;
  }
  stopHandsFreeMode("Dashboard wird geschlossen.");
}

function startCommandRecognition(options = {}) {
  const config = {
    source: options.source || "button",
    autoSend: options.autoSend !== false,
    timeoutMs: options.timeoutMs || 9000,
    initialPrompt: options.initialPrompt || "Ich höre zu...",
  };
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    setVoiceStatus("Spracherkennung wird von diesem Browser nicht unterstützt. Bitte Chrome oder Edge verwenden.", "error");
    setDesktopAgentState("Fehler", "Browser-Spracherkennung nicht verfügbar.");
    enableSpeechButtons();
    return;
  }
  if (isListening || currentCommandRecognition) {
    setVoiceStatus("Spracherkennung läuft bereits.");
    return;
  }
  if (isAssistantSpeaking) {
    setVoiceStatus("Jarvis spricht gerade. Bitte warte kurz.", "speaking");
    return;
  }

  let recognitionHadResult = false;
  let completed = false;
  const runId = ++commandRecognitionRunId;
  recognitionActivityId = `speech-recognition-${runId}`;
  startActivity(recognitionActivityId, "Spracherkennung läuft", {
    detail: config.source === "desktop_agent" ? "Desktop-Agent hat Jarvis erkannt." : "Mikrofon wird gestartet",
    category: "voice",
    timeoutMs: config.timeoutMs + 3000,
  });
  const recognition = new SpeechRecognition();
  currentCommandRecognition = recognition;
  recognition.lang = "de-DE";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  const timeoutHandle = window.setTimeout(() => {
    if (runId !== commandRecognitionRunId || completed) {
      return;
    }
    try {
      recognition.abort();
    } catch (error) {
      // The browser may already have ended the recognizer.
    }
    setVoiceStatus("Keine Sprache erkannt. Bitte erneut versuchen.", "error");
    timeoutActivity(recognitionActivityId, "Keine Sprache erkannt.");
  }, config.timeoutMs);
  recognition.onstart = () => {
    if (runId !== commandRecognitionRunId) {
      try {
        recognition.abort();
      } catch (error) {
        // Ignore stale recognizer abort errors.
      }
      return;
    }
    isListening = true;
    disableSpeechButtons();
    elements.voiceCard.classList.add("listening");
    elements.voiceButton.classList.add("listening");
    setVoiceStatus(config.initialPrompt, "active");
    setDesktopAgentState(config.source === "desktop_agent" ? "Browser-Spracherkennung aktiv" : desktopAgentState);
    updateActivity(recognitionActivityId, { detail: "Mikrofon aktiv. Bitte sprechen." });
  };
  recognition.onresult = (event) => {
    if (runId !== commandRecognitionRunId) {
      return;
    }
    recognitionHadResult = true;
    completed = true;
    const transcript = event.results?.[0]?.[0]?.transcript || "";
    elements.commandInput.value = transcript;
    setText("recognizedCommand", transcript || "-");
    finishActivity(recognitionActivityId, transcript ? `Erkannt: ${transcript}` : "Kein Text erkannt.");
    if (transcript && config.autoSend) {
      sendChatMessage(transcript);
    }
  };
  recognition.onerror = (event) => {
    if (runId !== commandRecognitionRunId) {
      return;
    }
    const message = speechRecognitionErrorMessage(event.error);
    setVoiceStatus(message, event.error === "aborted" ? "" : "error");
    if (event.error === "no-speech") {
      timeoutActivity(recognitionActivityId, message);
    } else if (event.error === "aborted") {
      cancelActivity(recognitionActivityId, message);
    } else {
      failActivity(recognitionActivityId, message);
    }
  };
  recognition.onend = () => {
    if (runId !== commandRecognitionRunId) {
      return;
    }
    window.clearTimeout(timeoutHandle);
    isListening = false;
    currentCommandRecognition = null;
    enableSpeechButtons();
    elements.voiceCard.classList.remove("listening");
    elements.voiceButton.classList.remove("listening");
    if (!recognitionHadResult && recognitionActivityId && activities.has(recognitionActivityId)) {
      cancelActivity(recognitionActivityId, "Spracherkennung beendet.");
    }
    if (!elements.voiceStatus.classList.contains("error")) {
      setVoiceStatus("Sprachsteuerung bereit.");
    }
    if (config.source === "desktop_agent" && !recognitionHadResult) {
      scheduleDesktopCooldown("Cooldown");
    }
  };
  try {
    recognition.start();
  } catch (error) {
    window.clearTimeout(timeoutHandle);
    currentCommandRecognition = null;
    enableSpeechButtons();
    failActivity(recognitionActivityId, "Spracherkennung konnte nicht gestartet werden.");
    setVoiceStatus("Spracherkennung konnte nicht gestartet werden.", "error");
  }
}

function startVoiceRecognition() {
  return startCommandRecognition({ source: "button", autoSend: true });
}

function speechRecognitionErrorMessage(errorCode) {
  if (errorCode === "no-speech") {
    return "Keine Sprache erkannt. Bitte erneut versuchen.";
  }
  if (errorCode === "not-allowed" || errorCode === "service-not-allowed") {
    return "Mikrofonzugriff wurde verweigert. Bitte erlaube den Mikrofonzugriff im Browser.";
  }
  if (errorCode === "network") {
    return "Browser-Spracherkennung ist aktuell nicht verfügbar.";
  }
  if (errorCode === "aborted") {
    return "Spracherkennung wurde abgebrochen.";
  }
  if (errorCode === "audio-capture") {
    return "Kein Mikrofon verfügbar oder Mikrofon wird bereits verwendet.";
  }
  return `Spracherkennung fehlgeschlagen: ${errorCode || "unbekannter Fehler"}`;
}

function disableSpeechButtons() {
  for (const button of [elements.voiceButton, elements.chatMicButton]) {
    if (button) {
      button.disabled = true;
      button.classList.add("button-loading");
    }
  }
}

function enableSpeechButtons() {
  for (const button of [elements.voiceButton, elements.chatMicButton]) {
    if (button) {
      button.disabled = false;
      button.classList.remove("button-loading");
    }
  }
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
    setText("knowledgeSupportedFormats", `Unterstützt: ${(status.supported_extensions || []).join(", ") || "-"}. Maximales Uploadlimit: ${status.max_upload_mb ?? "-"} MB.`);
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

async function openEngineeringProject() {
  const path = text(elements.engineeringProjectPath?.value, "").trim();
  if (!path) {
    setText("engineeringProjectStatus", "Bitte einen Projektpfad eingeben.");
    return;
  }
  try {
    setText("engineeringProjectStatus", "Engineering-Projekt wird geladen...");
    const opened = await postJson("/assistant/engineering/projects/open", { path });
    setText("engineeringProjectStatus", `${opened.project_name || "Projekt"} geladen: ${opened.file_count ?? 0} Datei(en).`);
    await refreshEngineeringProjectTree(opened.project_id);
  } catch (error) {
    setText("engineeringProjectStatus", "Engineering-Projekt konnte nicht geladen werden.");
  }
}

async function refreshEngineeringProjectTree(projectId) {
  if (!projectId) {
    return;
  }
  try {
    const tree = await fetchJson(`/assistant/engineering/projects/${encodeURIComponent(projectId)}/tree`);
    renderEngineeringTree(tree);
  } catch (error) {
    setText("engineeringProjectStatus", "Projektbaum konnte nicht geladen werden.");
  }
}

function renderEngineeringTree(tree) {
  if (!elements.engineeringProjectExplorer) {
    return;
  }
  elements.engineeringProjectExplorer.textContent = "";
  elements.engineeringProjectExplorer.appendChild(renderEngineeringTreeNode(tree));
}

function renderEngineeringTreeNode(node) {
  const item = document.createElement("li");
  const label = document.createElement("button");
  label.type = "button";
  label.className = "engineering-tree-item";
  label.textContent = node?.name || "Unbenannt";
  if (node?.type === "ProjectFile") {
    label.addEventListener("click", () => setText("engineeringProjectStatus", "Analyse verfügbar"));
  }
  item.appendChild(label);
  if (Array.isArray(node?.children) && node.children.length) {
    const children = document.createElement("ul");
    for (const child of node.children) {
      children.appendChild(renderEngineeringTreeNode(child));
    }
    item.appendChild(children);
  }
  return item;
}

async function runEngineeringDiagnostics() {
  const severity = elements.diagnosticsSeverityFilter?.value || "info";
  const categories = text(elements.diagnosticsCategoryFilter?.value, "text,graph,project")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  try {
    const report = await postJson("/assistant/engineering/diagnostics/run", {
      include_categories: categories,
      severity_min: severity,
    });
    renderEngineeringDiagnostics(report);
    await refreshCommandCenter();
  } catch (error) {
    setText("diagnosticsSummary", "Diagnose konnte nicht ausgeführt werden.");
    clearEngineeringDiagnosticsDetails();
  }
}

function clearEngineeringDiagnosticsDetails() {
  if (elements.diagnosticsIssueTableBody) {
    elements.diagnosticsIssueTableBody.textContent = "";
  }
  setText("diagnosticsIssueDetails", "Keine Details ausgewählt.");
}

function renderEngineeringDiagnostics(report) {
  setText(
    "diagnosticsSummary",
    `Gesamt: ${report.issue_count ?? 0} | Kritisch: ${report.critical_count ?? 0} | Warnungen: ${report.warning_count ?? 0} | Hinweise: ${report.info_count ?? 0}`,
  );
  setText("diagnosticsIssueDetails", "Keine Details ausgewählt.");
  if (!elements.diagnosticsIssueTableBody) {
    return;
  }
  elements.diagnosticsIssueTableBody.textContent = "";
  for (const issue of report.issues || []) {
    elements.diagnosticsIssueTableBody.appendChild(renderEngineeringDiagnosticIssue(issue));
  }
}

function renderEngineeringDiagnosticIssue(issue) {
  const row = document.createElement("tr");
  const values = [
    issue.severity,
    issue.rule_id,
    issue.title,
    issue.source_file,
    issue.source_line,
    issue.recommendation,
  ];
  for (const value of values) {
    const cell = document.createElement("td");
    cell.textContent = text(value, "");
    row.appendChild(cell);
  }
  row.addEventListener("click", () => {
    setText(
      "diagnosticsIssueDetails",
      `${issue.rule_id}: ${JSON.stringify(issue.evidence || {})}`,
    );
  });
  return row;
}

async function analyzeProToolCsv() {
  const filePath = text(elements.protoolFilePath?.value, "").trim();
  const textColumn = Number.parseInt(elements.protoolTextColumn?.value || "2", 10);
  if (!selectedProToolFile && !filePath) {
    setProToolError("Bitte einen lokalen CSV-Dateipfad eingeben oder eine CSV-Datei auswaehlen.");
    return;
  }
  if (!Number.isInteger(textColumn) || textColumn < 1) {
    setProToolError("Die Textspalte muss eine Zahl groesser oder gleich 1 sein.");
    return;
  }
  if (selectedProToolFile) {
    return analyzeSelectedProToolFile(textColumn);
  }
  return analyzeProToolPath(filePath, textColumn);
}

async function analyzeProToolPath(filePath, textColumn) {
  setText("protoolStatus", "ProTool-CSV wird analysiert...");
  clearProToolReport();
  try {
    const response = await fetch("/assistant/protool/analyze", {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_path: filePath,
        panel: elements.protoolPanel.value,
        text_column: textColumn,
        encoding: elements.protoolEncoding.value,
        include_preview: Boolean(elements.protoolIncludePreview?.checked),
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw createProToolHttpError(response.status, payload);
    }
    renderProToolReport(payload);
    if (elements.protoolIncludePreview?.checked) {
      openProToolPanelWindow(payload);
    }
  } catch (error) {
    setProToolError(proToolErrorMessage(error));
  }
}

async function analyzeSelectedProToolFile(textColumn) {
  setText("protoolStatus", "Ausgewaehlte ProTool-CSV wird hochgeladen und analysiert...");
  clearProToolReport();
  const formData = new FormData();
  formData.append("file", selectedProToolFile, selectedProToolFile.name);
  formData.append("panel", elements.protoolPanel.value);
  formData.append("text_column", String(textColumn));
  formData.append("encoding", elements.protoolEncoding.value);
  formData.append("include_preview", String(Boolean(elements.protoolIncludePreview?.checked)));
  try {
    const response = await fetch("/assistant/protool/upload-analyze", {
      method: "POST",
      cache: "no-store",
      body: formData,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw createProToolHttpError(response.status, payload);
    }
    renderProToolReport(payload);
    if (elements.protoolIncludePreview?.checked) {
      openProToolPanelWindow(payload);
    }
  } catch (error) {
    setProToolError(proToolErrorMessage(error));
  }
}

async function analyzeProToolBatch() {
  const filePaths = parseProToolBatchPaths();
  const textColumn = Number.parseInt(elements.protoolTextColumn?.value || "2", 10);
  if (!filePaths.length) {
    setProToolError("Bitte mindestens einen CSV-Dateipfad fuer die Batch-Analyse eingeben.");
    return;
  }
  if (!Number.isInteger(textColumn) || textColumn < 1) {
    setProToolError("Die Textspalte muss eine Zahl groesser oder gleich 1 sein.");
    return;
  }

  setText("protoolStatus", "ProTool-Projekt wird analysiert...");
  clearProToolReport();
  try {
    const response = await fetch("/assistant/protool/analyze-batch", {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_paths: filePaths,
        panel: elements.protoolPanel.value,
        text_column: textColumn,
        encoding: elements.protoolEncoding.value,
        include_preview: Boolean(elements.protoolIncludePreview?.checked),
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw createProToolHttpError(response.status, payload);
    }
    renderProToolBatchReport(payload);
  } catch (error) {
    setProToolError(proToolErrorMessage(error));
  }
}

async function importProToolToGraph() {
  const filePath = text(elements.protoolFilePath?.value, "").trim();
  const textColumn = Number.parseInt(elements.protoolTextColumn?.value || "2", 10);
  if (selectedProToolFile) {
    setProToolError("Import in den Engineering Graph benötigt aktuell einen lokalen Dateipfad. Upload-Dateien können weiterhin analysiert werden.");
    return;
  }
  if (!filePath) {
    setProToolError("Bitte einen lokalen CSV-Dateipfad fuer den Import eingeben.");
    return;
  }
  if (!Number.isInteger(textColumn) || textColumn < 1) {
    setProToolError("Die Textspalte muss eine Zahl groesser oder gleich 1 sein.");
    return;
  }

  setText("protoolStatus", "ProTool-CSV wird read-only in den Engineering Graph importiert...");
  clearProToolReport();
  try {
    const response = await fetch("/assistant/protool/import", {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_path: filePath,
        panel: elements.protoolPanel.value,
        text_column: textColumn,
        encoding: elements.protoolEncoding.value,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw createProToolHttpError(response.status, payload);
    }
    renderProToolImportResult(payload);
    await refreshCommandCenter();
  } catch (error) {
    setProToolError(proToolErrorMessage(error));
  }
}

function parseProToolBatchPaths() {
  return text(elements.protoolBatchFilePaths?.value, "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function createProToolHttpError(status, payload) {
  const error = new Error(text(payload?.detail, `HTTP ${status}`));
  error.status = status;
  return error;
}

function proToolErrorMessage(error) {
  if (error?.status === 404) {
    return `Datei nicht gefunden: ${text(error.message, "Der angegebene Pfad wurde nicht gefunden.")}`;
  }
  if (error?.status === 400) {
    return `Eingabe ungueltig: ${text(error.message, "Bitte Dateipfad, Panel, Textspalte und Encoding pruefen.")}`;
  }
  if (error?.status) {
    return `Serverfehler bei der ProTool-Analyse: HTTP ${error.status}`;
  }
  return "ProTool-Analyse fehlgeschlagen. Bitte Backend und Eingaben pruefen.";
}

function setProToolError(message) {
  setText("protoolStatus", message);
  clearProToolReport();
}

function clearProToolReport() {
  if (elements.protoolSummary) {
    elements.protoolSummary.textContent = "";
  }
  if (elements.protoolIssuesBody) {
    elements.protoolIssuesBody.textContent = "";
  }
  if (elements.protoolProjectSummary) {
    elements.protoolProjectSummary.textContent = "";
  }
  if (elements.protoolFileReports) {
    elements.protoolFileReports.textContent = "";
  }
  if (elements.protoolNoIssues) {
    elements.protoolNoIssues.hidden = true;
  }
}

function renderProToolImportResult(importResult) {
  const count = importResult.text_resource_count ?? 0;
  setText("protoolStatus", `${count} ProTool-TextResource(s) in den Engineering Graph importiert.`);
  if (elements.protoolSummary) {
    elements.protoolSummary.textContent = "";
    const entries = [
      ["Datei", importResult.file],
      ["Panel", importResult.panel],
      ["TextResources", count],
    ];
    for (const [label, value] of entries) {
      const group = document.createElement("div");
      const term = document.createElement("dt");
      const detail = document.createElement("dd");
      term.textContent = label;
      detail.textContent = text(value);
      group.append(term, detail);
      elements.protoolSummary.appendChild(group);
    }
  }
  if (elements.protoolNoIssues) {
    elements.protoolNoIssues.hidden = true;
  }
}

function renderProToolReport(report) {
  setText("protoolStatus", `${report.issues?.length ?? 0} Issue(s) gefunden.`);
  if (elements.protoolProjectSummary) {
    elements.protoolProjectSummary.textContent = "";
  }
  if (elements.protoolFileReports) {
    elements.protoolFileReports.textContent = "";
  }
  renderProToolSummary(report);
  renderProToolIssues(report.issues || []);
  renderProToolPreviews(elements.protoolFileReports, report.previews || []);
}

function renderProToolSummary(report) {
  if (!elements.protoolSummary) {
    return;
  }
  elements.protoolSummary.textContent = "";
  const entries = [
    ["Datei", report.file],
    ["Panel", report.panel],
    ["Encoding", report.encoding],
    ["Delimiter", report.delimiter],
    ["rows", report.rows],
    ["checked_rows", report.checked_rows],
    ["Issues", report.issues?.length ?? 0],
  ];
  for (const [label, value] of entries) {
    const group = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = label;
    detail.textContent = text(value);
    group.append(term, detail);
    elements.protoolSummary.appendChild(group);
  }
}

function renderProToolBatchReport(batchReport) {
  const files = batchReport.files || [];
  const totalIssues = batchReport.summary?.total_issues ?? 0;
  setText("protoolStatus", `${files.length} Datei(en) analysiert, ${totalIssues} Issue(s) gefunden.`);
  renderProToolProjectSummary(batchReport.summary || {});
  if (elements.protoolSummary) {
    elements.protoolSummary.textContent = "";
  }
  if (elements.protoolIssuesBody) {
    elements.protoolIssuesBody.textContent = "";
  }
  if (elements.protoolNoIssues) {
    elements.protoolNoIssues.hidden = totalIssues !== 0;
  }
  renderProToolFileReports(files);
}

function renderProToolProjectSummary(summary) {
  if (!elements.protoolProjectSummary) {
    return;
  }
  elements.protoolProjectSummary.textContent = "";
  const entries = [
    ["Dateien", summary.file_count],
    ["Gesamtzeilen", summary.total_rows],
    ["Gepruefte Textzeilen", summary.total_checked_rows],
    ["Gesamtprobleme", summary.total_issues],
  ];
  for (const [label, value] of entries) {
    const group = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = label;
    detail.textContent = text(value);
    group.append(term, detail);
    elements.protoolProjectSummary.appendChild(group);
  }
}

function renderProToolFileReports(files) {
  if (!elements.protoolFileReports) {
    return;
  }
  elements.protoolFileReports.textContent = "";
  for (const fileReport of files) {
    elements.protoolFileReports.appendChild(renderProToolFileReport(fileReport));
  }
}

function renderProToolFileReport(report) {
  const wrapper = document.createElement("section");
  wrapper.className = "protool-file-report";
  const title = document.createElement("h3");
  title.textContent = report.file || "ProTool CSV";
  wrapper.appendChild(title);
  wrapper.appendChild(createProToolSummaryList(report));
  const previewRows = getProToolPreviewRows(report);
  if (previewRows.length) {
    const button = document.createElement("button");
    button.className = "ghost-button";
    button.type = "button";
    button.textContent = "Panel öffnen";
    button.addEventListener("click", () => openProToolPanelWindow(report));
    wrapper.appendChild(button);
  }
  wrapper.appendChild(createProToolIssueTable(report.issues || []));
  renderProToolPreviews(wrapper, report.previews || []);
  return wrapper;
}

function createProToolSummaryList(report) {
  const summary = document.createElement("dl");
  summary.className = "protool-summary";
  const entries = [
    ["Panel", report.panel],
    ["Encoding", report.encoding],
    ["Delimiter", report.delimiter],
    ["rows", report.rows],
    ["checked_rows", report.checked_rows],
    ["Issues", report.issues?.length ?? 0],
  ];
  for (const [label, value] of entries) {
    const group = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = label;
    detail.textContent = text(value);
    group.append(term, detail);
    summary.appendChild(group);
  }
  return summary;
}

function createProToolIssueTable(issues) {
  const table = document.createElement("table");
  table.className = "protool-issues-table";
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const label of ["row", "type", "line", "max", "actual", "text"]) {
    const cell = document.createElement("th");
    cell.textContent = label;
    headRow.appendChild(cell);
  }
  head.appendChild(headRow);
  const body = document.createElement("tbody");
  for (const issue of issues) {
    body.appendChild(createProToolIssueRow(issue));
  }
  table.append(head, body);
  if (!issues.length) {
    const caption = document.createElement("caption");
    caption.textContent = "Keine Probleme gefunden.";
    table.appendChild(caption);
  }
  return table;
}

function renderProToolIssues(issues) {
  if (!elements.protoolIssuesBody) {
    return;
  }
  elements.protoolIssuesBody.textContent = "";
  if (!issues.length) {
    if (elements.protoolNoIssues) {
      elements.protoolNoIssues.hidden = false;
    }
    return;
  }
  if (elements.protoolNoIssues) {
    elements.protoolNoIssues.hidden = true;
  }
  for (const issue of issues) {
    elements.protoolIssuesBody.appendChild(createProToolIssueRow(issue));
  }
}

function createProToolIssueRow(issue) {
  const row = document.createElement("tr");
  for (const key of ["row", "type", "line", "max", "actual", "text"]) {
    const cell = document.createElement("td");
    cell.textContent = text(issue?.[key], "");
    row.appendChild(cell);
  }
  return row;
}

function renderProToolPreviews(target, previews) {
  if (!target || !previews.length) {
    return;
  }
  const list = document.createElement("div");
  list.className = "protool-preview-list";
  for (const preview of previews) {
    const item = document.createElement("div");
    item.className = "protool-preview";
    const label = document.createElement("strong");
    label.textContent = `Zeile ${text(preview.row)}${preview.truncated ? " | abgeschnitten" : ""}`;
    const block = document.createElement("pre");
    block.textContent = (preview.preview || []).join("\n");
    item.append(label, block);
    list.appendChild(item);
  }
  target.appendChild(list);
}

function getProToolPreviewRows(report) {
  return report?.preview_rows || report?.previews || [];
}

function openProToolPanelWindow(report) {
  const previewRows = getProToolPreviewRows(report);
  const panelWindow = window.open("", "_blank", "width=760,height=560,noopener=false");
  if (!panelWindow) {
    setText("protoolStatus", "Panel-Vorschaufenster konnte nicht geöffnet werden.");
    return;
  }
  const panelDocument = panelWindow.document;
  panelDocument.open();
  panelDocument.write("<!doctype html><html lang=\"de\"><head><meta charset=\"UTF-8\"><title>ProTool Panel-Vorschau</title></head><body></body></html>");
  panelDocument.close();
  buildProToolPanelWindow(panelDocument, report, previewRows);
}

function buildProToolPanelWindow(panelDocument, report, previewRows) {
  if (report?.panel === "OP7") {
    buildProToolOp7PanelWindow(panelDocument, report, previewRows);
    return;
  }
  buildGenericProToolPanelWindow(panelDocument, report, previewRows);
}

function buildProToolOp7PanelWindow(panelDocument, report, previewRows) {
  const dimensions = PROTOOL_PANEL_DIMENSIONS.OP7;
  const style = panelDocument.createElement("style");
  style.textContent = `
    body {
      margin: 0;
      background: #101316;
      color: #e6edf2;
      font-family: "Segoe UI", Arial, sans-serif;
    }
    .shell {
      min-height: 100vh;
      padding: 24px;
      background:
        radial-gradient(circle at 50% 18%, rgba(190, 220, 80, 0.14), transparent 34%),
        linear-gradient(145deg, #0b0f13, #161b20 55%, #080a0c);
    }
    .op7-stage {
      display: grid;
      justify-items: center;
      gap: 14px;
    }
    .meta, .status, .controls, .zoom-controls {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 10px;
      color: #d4dee8;
    }
    .op7-scale {
      transform: scale(var(--op7-zoom, 1));
      transform-origin: top center;
      transition: transform 140ms ease;
    }
    .op7-case {
      width: 620px;
      border-radius: 24px;
      padding: 24px 28px 28px;
      background:
        linear-gradient(145deg, #4c535a 0%, #2e343a 42%, #171b20 100%);
      border: 2px solid #6d747a;
      box-shadow:
        0 28px 90px rgba(0, 0, 0, 0.58),
        inset 0 1px 0 rgba(255, 255, 255, 0.16),
        inset 0 -24px 48px rgba(0, 0, 0, 0.28);
    }
    .op7-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      margin-bottom: 18px;
      color: #f4f8fb;
      letter-spacing: 0.03em;
    }
    .op7-brand {
      font-size: 28px;
      font-weight: 900;
    }
    .op7-model {
      text-align: right;
      font-size: 18px;
      font-weight: 800;
    }
    .op7-leds {
      display: flex;
      gap: 12px;
      justify-content: flex-end;
      margin-top: 8px;
      font-size: 11px;
      color: #cbd4dc;
    }
    .op7-led {
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }
    .op7-led::before {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      content: "";
      background: #273035;
      border: 1px solid rgba(255, 255, 255, 0.2);
      box-shadow: inset 0 0 5px rgba(0, 0, 0, 0.7);
    }
    .op7-led.run::before {
      background: #39d353;
      box-shadow: 0 0 12px rgba(57, 211, 83, 0.8);
    }
    .op7-led.stop::before {
      background: #3a2422;
    }
    .op7-led.sf::before {
      background: #4a2e17;
    }
    .op7-display-frame {
      border-radius: 12px;
      padding: 16px;
      background: #111518;
      border: 2px solid #07090b;
      box-shadow: inset 0 0 18px rgba(0, 0, 0, 0.75);
    }
    .op7-lcd {
      display: grid;
      gap: 5px;
      border: 3px solid #2c3215;
      border-radius: 7px;
      padding: 16px 18px;
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.12), transparent 24%),
        #becf62;
      color: #17210c;
      font-family: Consolas, "Courier New", monospace;
      box-shadow: inset 0 0 22px rgba(35, 48, 12, 0.55);
    }
    .op7-lcd-row {
      display: grid;
      grid-template-columns: repeat(20, 1ch);
      font-size: 25px;
      line-height: 1.16;
      white-space: pre;
    }
    .op7-lcd-char {
      display: inline-block;
      width: 1ch;
      text-align: center;
    }
    .op7-keyboard {
      display: grid;
      grid-template-columns: repeat(8, 1fr);
      gap: 10px;
      margin-top: 20px;
    }
    .op7-key {
      min-height: 38px;
      border-radius: 7px;
      display: grid;
      place-items: center;
      background: linear-gradient(180deg, #3e464d, #171c21);
      border: 1px solid #69737c;
      color: #edf4f8;
      font-weight: 800;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.18), 0 4px 8px rgba(0, 0, 0, 0.35);
    }
    .op7-control-grid {
      display: grid;
      grid-template-columns: 1fr 120px 1fr;
      gap: 18px;
      margin-top: 16px;
      align-items: center;
    }
    .op7-nav-cluster {
      display: grid;
      grid-template-columns: repeat(3, 42px);
      grid-template-rows: repeat(3, 34px);
      justify-content: center;
      gap: 5px;
    }
    .op7-nav-cluster .up { grid-column: 2; }
    .op7-nav-cluster .left { grid-column: 1; grid-row: 2; }
    .op7-nav-cluster .right { grid-column: 3; grid-row: 2; }
    .op7-nav-cluster .down { grid-column: 2; grid-row: 3; }
    button {
      border: 1px solid #8fa15c;
      border-radius: 5px;
      padding: 9px 12px;
      background: #1d252a;
      color: #eef7df;
      cursor: pointer;
    }
    .screenshot-mode .op7-stage > .meta,
    .screenshot-mode .op7-stage > .status,
    .screenshot-mode .op7-stage > .controls,
    .screenshot-mode .op7-stage > .zoom-controls {
      display: none;
    }
    .notice {
      border: 1px solid #d1b24a;
      padding: 14px;
      color: #ffeaa0;
      background: rgba(209, 178, 74, 0.12);
    }
  `;
  panelDocument.head.appendChild(style);

  const shell = panelDocument.createElement("main");
  shell.className = "shell";
  const stage = panelDocument.createElement("section");
  stage.className = "op7-stage";
  shell.appendChild(stage);

  if (!previewRows.length) {
    const notice = panelDocument.createElement("p");
    notice.className = "notice";
    notice.textContent = "Keine Panel-Vorschau im Report vorhanden. Bitte Checkbox 'Panel-Vorschau anzeigen' aktivieren.";
    stage.appendChild(notice);
    panelDocument.body.appendChild(shell);
    return;
  }

  let index = 0;
  const meta = panelDocument.createElement("div");
  meta.className = "meta";
  const status = panelDocument.createElement("div");
  status.className = "status";
  const scaleWrapper = panelDocument.createElement("div");
  scaleWrapper.className = "op7-scale";
  scaleWrapper.style.setProperty("--op7-zoom", "1");
  const op7Case = panelDocument.createElement("div");
  op7Case.className = "op7-case";
  const header = panelDocument.createElement("div");
  header.className = "op7-header";
  const brand = panelDocument.createElement("div");
  brand.className = "op7-brand";
  brand.textContent = "SIEMENS";
  const modelBlock = panelDocument.createElement("div");
  modelBlock.className = "op7-model";
  const model = panelDocument.createElement("div");
  model.textContent = "SIMATIC OP7";
  const leds = panelDocument.createElement("div");
  leds.className = "op7-leds";
  for (const [label, className] of [["RUN", "run"], ["STOP", "stop"], ["SF", "sf"]]) {
    const led = panelDocument.createElement("span");
    led.className = `op7-led ${className}`;
    led.textContent = label;
    leds.appendChild(led);
  }
  modelBlock.append(model, leds);
  header.append(brand, modelBlock);

  const displayFrame = panelDocument.createElement("div");
  displayFrame.className = "op7-display-frame";
  const lcd = panelDocument.createElement("div");
  lcd.className = "op7-lcd";
  displayFrame.appendChild(lcd);

  const functionKeys = panelDocument.createElement("div");
  functionKeys.className = "op7-keyboard";
  for (const label of ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8"]) {
    functionKeys.appendChild(createOp7Key(panelDocument, label));
  }

  const controlGrid = panelDocument.createElement("div");
  controlGrid.className = "op7-control-grid";
  controlGrid.appendChild(createOp7Key(panelDocument, "ESC"));
  const navCluster = panelDocument.createElement("div");
  navCluster.className = "op7-nav-cluster";
  for (const [label, className] of [["↑", "up"], ["←", "left"], ["→", "right"], ["↓", "down"]]) {
    const key = createOp7Key(panelDocument, label);
    key.classList.add(className);
    navCluster.appendChild(key);
  }
  controlGrid.appendChild(navCluster);
  controlGrid.appendChild(createOp7Key(panelDocument, "ENTER"));

  op7Case.append(header, displayFrame, functionKeys, controlGrid);
  scaleWrapper.appendChild(op7Case);

  const controls = panelDocument.createElement("div");
  controls.className = "controls";
  const previousButton = panelDocument.createElement("button");
  previousButton.type = "button";
  previousButton.textContent = "Vorherige";
  const nextButton = panelDocument.createElement("button");
  nextButton.type = "button";
  nextButton.textContent = "Nächste";
  const screenshotButton = panelDocument.createElement("button");
  screenshotButton.type = "button";
  screenshotButton.textContent = "Screenshot vorbereiten";
  controls.append(previousButton, nextButton, screenshotButton);

  const zoomControls = createProToolZoomControls(panelDocument, scaleWrapper);

  function renderPanelPreview() {
    const current = previewRows[index];
    meta.textContent = `CSV-Zeile ${current.row ?? "-"} / ${previewRows.length} | Datei: ${report.file || "-"}`;
    const statusParts = [current.truncated ? "Text abgeschnitten" : "OK"];
    if ((current.placeholders || []).length) {
      statusParts.push("Platzhalter vorhanden");
    }
    status.textContent = `Status: ${statusParts.join(" | ")}`;
    lcd.textContent = "";
    for (const line of normalizePanelPreviewLines(current.preview || [], dimensions)) {
      const row = panelDocument.createElement("div");
      row.className = "op7-lcd-row";
      for (const char of line) {
        const cell = panelDocument.createElement("span");
        cell.className = "op7-lcd-char";
        cell.textContent = char === " " ? "\u00a0" : char;
        row.appendChild(cell);
      }
      lcd.appendChild(row);
    }
    previousButton.disabled = index === 0;
    nextButton.disabled = index >= previewRows.length - 1;
  }

  previousButton.addEventListener("click", () => {
    if (index > 0) {
      index -= 1;
      renderPanelPreview();
    }
  });
  nextButton.addEventListener("click", () => {
    if (index < previewRows.length - 1) {
      index += 1;
      renderPanelPreview();
    }
  });
  screenshotButton.addEventListener("click", () => {
    panelDocument.body.classList.toggle("screenshot-mode");
  });
  panelDocument.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") {
      previousButton.click();
    }
    if (event.key === "ArrowRight") {
      nextButton.click();
    }
  });

  stage.append(meta, status, scaleWrapper, zoomControls, controls);
  panelDocument.body.appendChild(shell);
  renderPanelPreview();
}

function createOp7Key(panelDocument, label) {
  const key = panelDocument.createElement("div");
  key.className = "op7-key";
  key.textContent = label;
  return key;
}

function createProToolZoomControls(panelDocument, target) {
  const wrapper = panelDocument.createElement("div");
  wrapper.className = "zoom-controls";
  for (const [label, scale] of [["75 %", "0.75"], ["100 %", "1"], ["150 %", "1.5"], ["200 %", "2"]]) {
    const button = panelDocument.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", () => target.style.setProperty("--op7-zoom", scale));
    wrapper.appendChild(button);
  }
  return wrapper;
}

function buildGenericProToolPanelWindow(panelDocument, report, previewRows) {
  const dimensions = PROTOOL_PANEL_DIMENSIONS[report?.panel] || inferProToolPreviewDimensions(previewRows);
  const style = panelDocument.createElement("style");
  style.textContent = `
    body {
      margin: 0;
      background: #080b0d;
      color: #d7f8c8;
      font-family: "Segoe UI", Arial, sans-serif;
    }
    .shell {
      min-height: 100vh;
      padding: 24px;
      background: radial-gradient(circle at center, rgba(161, 255, 88, 0.12), transparent 48%), #080b0d;
    }
    .panel-case {
      max-width: 680px;
      margin: 0 auto;
      border: 12px solid #171b20;
      border-radius: 18px;
      padding: 20px;
      background: linear-gradient(145deg, #242a30, #0f1318);
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.55), inset 0 0 30px rgba(255, 255, 255, 0.04);
    }
    .lcd {
      display: grid;
      gap: 4px;
      border: 4px solid #0b0f0a;
      border-radius: 8px;
      padding: 14px;
      background: #b8cf63;
      color: #14230c;
      box-shadow: inset 0 0 22px rgba(0, 0, 0, 0.42);
      font-family: Consolas, "Courier New", monospace;
    }
    .lcd-row {
      display: grid;
      grid-template-columns: repeat(var(--columns), 1ch);
      gap: 0;
      font-size: ${dimensions.columns > 20 ? "17px" : "24px"};
      line-height: 1.2;
      white-space: pre;
    }
    .lcd-char {
      display: inline-block;
      width: 1ch;
      text-align: center;
    }
    .meta, .status, .controls {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 12px 0;
      color: #d7f8c8;
    }
    button {
      border: 1px solid #8fbf50;
      border-radius: 4px;
      padding: 9px 12px;
      background: #202821;
      color: #e9ffd8;
      cursor: pointer;
    }
    .notice {
      border: 1px solid #d1b24a;
      padding: 14px;
      color: #ffeaa0;
      background: rgba(209, 178, 74, 0.12);
    }
  `;
  panelDocument.head.appendChild(style);

  const shell = panelDocument.createElement("main");
  shell.className = "shell";
  const panel = panelDocument.createElement("section");
  panel.className = "panel-case";
  const title = panelDocument.createElement("h1");
  title.textContent = "ProTool Panel-Vorschau";
  panel.appendChild(title);

  if (!previewRows.length) {
    const notice = panelDocument.createElement("p");
    notice.className = "notice";
    notice.textContent = "Keine Panel-Vorschau im Report vorhanden. Bitte Checkbox 'Panel-Vorschau anzeigen' aktivieren.";
    panel.appendChild(notice);
    shell.appendChild(panel);
    panelDocument.body.appendChild(shell);
    return;
  }

  let index = 0;
  const meta = panelDocument.createElement("div");
  meta.className = "meta";
  const status = panelDocument.createElement("div");
  status.className = "status";
  const lcd = panelDocument.createElement("div");
  lcd.className = "lcd";
  lcd.style.setProperty("--columns", String(dimensions.columns));
  const controls = panelDocument.createElement("div");
  controls.className = "controls";
  const previousButton = panelDocument.createElement("button");
  previousButton.type = "button";
  previousButton.textContent = "Vorherige";
  const nextButton = panelDocument.createElement("button");
  nextButton.type = "button";
  nextButton.textContent = "Nächste";
  controls.append(previousButton, nextButton);

  function renderPanelPreview() {
    const current = previewRows[index];
    meta.textContent = `Panel: ${report.panel || "-"} | Datei: ${report.file || "-"} | CSV-Zeile: ${current.row ?? "-"}`;
    const statusParts = [current.truncated ? "truncated" : "OK"];
    if ((current.placeholders || []).length) {
      statusParts.push("Placeholder vorhanden");
    }
    status.textContent = `Status: ${statusParts.join(" | ")}`;
    lcd.textContent = "";
    for (const line of normalizePanelPreviewLines(current.preview || [], dimensions)) {
      const row = panelDocument.createElement("div");
      row.className = "lcd-row";
      for (const char of line) {
        const cell = panelDocument.createElement("span");
        cell.className = "lcd-char";
        cell.textContent = char === " " ? "\u00a0" : char;
        row.appendChild(cell);
      }
      lcd.appendChild(row);
    }
    previousButton.disabled = index === 0;
    nextButton.disabled = index >= previewRows.length - 1;
  }

  previousButton.addEventListener("click", () => {
    if (index > 0) {
      index -= 1;
      renderPanelPreview();
    }
  });
  nextButton.addEventListener("click", () => {
    if (index < previewRows.length - 1) {
      index += 1;
      renderPanelPreview();
    }
  });
  panelDocument.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") {
      previousButton.click();
    }
    if (event.key === "ArrowRight") {
      nextButton.click();
    }
  });

  panel.append(meta, status, lcd, controls);
  shell.appendChild(panel);
  panelDocument.body.appendChild(shell);
  renderPanelPreview();
}

function inferProToolPreviewDimensions(previewRows) {
  const firstPreview = previewRows?.[0]?.preview || [];
  return {
    rows: Math.max(firstPreview.length || 4, 4),
    columns: Math.max(...firstPreview.map((line) => String(line).length), 20),
  };
}

function normalizePanelPreviewLines(lines, dimensions) {
  const normalized = [];
  for (const line of lines.slice(0, dimensions.rows)) {
    normalized.push(String(line).slice(0, dimensions.columns).padEnd(dimensions.columns, " "));
  }
  while (normalized.length < dimensions.rows) {
    normalized.push(" ".repeat(dimensions.columns));
  }
  return normalized;
}

function knowledgeErrorMessage(reason, fallback = "Die Dokumentverarbeitung ist fehlgeschlagen.") {
  return {
    invalid_filename: "Der Dateiname ist ungültig.",
    unsupported_extension: "Dieser Dateityp wird nicht unterstützt.",
    unsupported_file_type: "Dieser Dateityp wird nicht unterstützt.",
    empty_file: "Die Datei ist leer.",
    file_too_large: "Die Datei überschreitet das erlaubte Größenlimit.",
    invalid_pdf_header: "Die Datei ist kein gültiges PDF.",
    ocr_required: "Das PDF enthält keinen extrahierbaren Text. OCR wird noch nicht unterstützt.",
    upload_write_failed: "Die Datei konnte lokal nicht gespeichert werden.",
    index_write_failed: "Der Wissensindex konnte nicht aktualisiert werden.",
    index_recovery_failed: "Der lokale Wissensindex muss überprüft werden.",
  }[String(reason || "")] || fallback;
}

function renderKnowledgeUploadQueue(items) {
  renderList(elements.knowledgeUploadQueue, items, (item) => {
    const wrapper = document.createElement("span");
    wrapper.textContent = `${item.name}: ${item.status}`;
    if (item.message) {
      const detail = document.createElement("div");
      detail.className = "muted";
      detail.textContent = item.message;
      wrapper.appendChild(detail);
    }
    return wrapper;
  }, "");
}

async function uploadKnowledgeFiles(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;
  const queue = files.map((file) => ({ name: file.name, status: "wird hochgeladen", message: "" }));
  renderKnowledgeUploadQueue(queue);
  setText("knowledgeUploadSummary", `0 von ${files.length} Dateien verarbeitet.`);
  const activityId = `knowledge-upload-${Date.now()}`;
  startActivity(activityId, `${files.length} Dokument(e) werden hochgeladen`, {
    category: "knowledge",
    detail: "Lokale Uploads werden verarbeitet.",
    progress: `0 von ${files.length} Dateien verarbeitet`,
  });
  try {
    const formData = new FormData();
    for (const file of files) formData.append("files", file, file.name);
    for (const item of queue) item.status = "wird verarbeitet";
    renderKnowledgeUploadQueue(queue);
    const response = await fetch("/assistant/knowledge/upload", { method: "POST", body: formData, cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(knowledgeErrorMessage(data?.detail?.reason, "Upload konnte nicht ausgeführt werden."));
    const byName = new Map(queue.map((item) => [item.name, item]));
    for (const document of data.documents || []) {
      const item = byName.get(document.original_name || document.name);
      if (!item) continue;
      item.status = document.duplicate ? "Duplikat" : document.extraction_status === "ocr_required" ? "OCR erforderlich" : "bereit";
      item.message = document.duplicate ? "Bereits vorhanden." : document.extraction_status === "ocr_required" ? knowledgeErrorMessage("ocr_required") : "Lokal gespeichert und indexiert.";
    }
    for (const error of data.errors || []) {
      const item = byName.get(error.filename || error.name);
      if (!item) continue;
      item.status = "Fehler";
      item.message = knowledgeErrorMessage(error.reason, error.message);
    }
    renderKnowledgeUploadQueue(queue);
    const complete = Number(data.success_count || 0) + Number(data.failed_count || 0);
    setText("knowledgeUploadSummary", `${complete} von ${files.length} Dateien verarbeitet.`);
    finishActivity(activityId, `${data.success_count || 0} Dokument(e) verarbeitet.`);
    await refreshKnowledge();
  } catch (error) {
    for (const item of queue) {
      if (item.status !== "bereit" && item.status !== "Duplikat" && item.status !== "OCR erforderlich") {
        item.status = "Fehler";
        item.message = "Die Datei konnte nicht zum lokalen Wissensspeicher hochgeladen werden.";
      }
    }
    renderKnowledgeUploadQueue(queue);
    setText("knowledgeUploadSummary", "Upload fehlgeschlagen.");
    failActivity(activityId, "Dokument-Upload fehlgeschlagen.");
  } finally {
    if (elements.knowledgeFileInput) elements.knowledgeFileInput.value = "";
  }
}

async function reindexKnowledgeDocument(document, button) {
  if (!document?.document_id || knowledgeBusyDocumentIds.has(document.document_id)) return;
  knowledgeBusyDocumentIds.add(document.document_id);
  if (button) button.disabled = true;
  const activityId = `knowledge-reindex-${document.document_id}`;
  startActivity(activityId, "Dokument wird neu indexiert", { category: "knowledge", detail: "Wird neu indexiert ..." });
  try {
    const response = await fetch(`/assistant/knowledge/documents/${encodeURIComponent(document.document_id)}/reindex`, { method: "POST", cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(knowledgeErrorMessage(data?.detail?.reason));
    const detail = data.document?.extraction_status === "ocr_required"
      ? "Das Dokument wurde geprüft, benötigt aber lokale OCR-Unterstützung."
      : "Dokument wurde neu indexiert.";
    setText("knowledgeUploadSummary", detail);
    finishActivity(activityId, detail);
    await refreshKnowledge();
  } catch (error) {
    setText("knowledgeUploadSummary", "Dokument konnte nicht neu indexiert werden.");
    failActivity(activityId, "Neuindexierung fehlgeschlagen.");
  } finally {
    knowledgeBusyDocumentIds.delete(document.document_id);
    if (button) button.disabled = false;
  }
}

async function deleteKnowledgeDocument(document, button) {
  if (!document?.document_id || knowledgeBusyDocumentIds.has(document.document_id)) return;
  const detail = document.source_type === "upload"
    ? "Die von Jarvis verwaltete lokale Kopie wird ebenfalls entfernt."
    : "Die Originaldatei bleibt erhalten. Nur der Wissensindex wird entfernt.";
  if (!window.confirm(`Soll dieses Dokument wirklich aus Jarvis’ Wissensspeicher entfernt werden?\n\n${detail}`)) return;
  knowledgeBusyDocumentIds.add(document.document_id);
  if (button) button.disabled = true;
  const activityId = `knowledge-delete-${document.document_id}`;
  startActivity(activityId, "Dokument wird entfernt", { category: "knowledge", detail: "Wird entfernt ..." });
  try {
    const response = await fetch(`/assistant/knowledge/documents/${encodeURIComponent(document.document_id)}`, { method: "DELETE", cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(knowledgeErrorMessage(data?.detail?.reason));
    const message = data.cleanup_pending
      ? "Dokument entfernt. Die lokale Bereinigung wird abgeschlossen."
      : data.physical_file_deleted
        ? "Dokument und verwaltete lokale Kopie wurden entfernt."
        : "Dokument wurde aus dem Wissensspeicher entfernt.";
    setText("knowledgeUploadSummary", message);
    clearList(elements.knowledgeResults);
    finishActivity(activityId, message);
    await refreshKnowledge();
  } catch (error) {
    setText("knowledgeUploadSummary", "Dokument konnte nicht entfernt werden.");
    failActivity(activityId, "Entfernen fehlgeschlagen.");
  } finally {
    knowledgeBusyDocumentIds.delete(document.document_id);
    if (button) button.disabled = false;
  }
}

async function showKnowledgeDetails(document) {
  if (!document?.document_id) return;
  try {
    const data = await fetchJson(`/assistant/knowledge/documents/${encodeURIComponent(document.document_id)}`);
    const previews = (data.chunks || data.chunk_previews || []).map((chunk) => chunk.preview).filter(Boolean);
    setText("knowledgeUploadSummary", previews.length ? previews.join(" | ") : "Keine Chunk-Vorschau verfügbar.");
  } catch (error) {
    setText("knowledgeUploadSummary", "Dokumentdetails konnten nicht geladen werden.");
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
  const activityId = contentMode ? "file-content-search" : "file-search";
  setText("fileStatus", contentMode ? "Dateiinhalte werden durchsucht..." : "Dateien werden gesucht...");
  try {
    const response = await fetchJson(`${endpoint}?q=${encodeURIComponent(query)}`, {
      activityId,
      activityTitle: contentMode ? "Dateiinhalte werden durchsucht" : "Dateien werden gesucht",
      activityDetail: `Suchbegriff: ${query}`,
      timeoutMs: contentMode ? 45000 : 20000,
    });
    setText("fileStatus", response.message || "Suche abgeschlossen.");
    renderList(elements.fileSearchResults, response.files || [], renderFile, "Keine passenden Dateien.");
    finishActivity(activityId, response.message || "Dateisuche abgeschlossen.");
  } catch (error) {
    setText("fileStatus", "Dateisuche fehlgeschlagen.");
    if (error.kind === "timeout") {
      timeoutActivity(activityId, error.message);
    } else {
      failActivity(activityId, "Dateisuche fehlgeschlagen.");
    }
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
    const response = await postJson("/assistant/web/research", { query }, {
      activityId: "web-research",
      activityTitle: "Internetrecherche läuft",
      activityDetail: `Recherche: ${query}`,
      timeoutMs: 45000,
    });
    setText("webResearchStatus", response.message || "Recherche abgeschlossen.");
    setText("webResearchAnswer", response.answer || response.summary || response.message || "Keine Zusammenfassung verfügbar.");
    renderList(elements.webResearchSources, response.sources || [], renderWebSource, "Keine Quellen.");
    finishActivity("web-research", response.message || "Recherche abgeschlossen.");
  } catch (error) {
    setText("webResearchStatus", "Internetrecherche fehlgeschlagen.");
    if (error.kind === "timeout") {
      timeoutActivity("web-research", error.message);
    } else {
      failActivity("web-research", "Internetrecherche fehlgeschlagen.");
    }
  }
}

async function refreshDashboard() {
  if (dashboardRefreshInFlight) {
    return;
  }
  dashboardRefreshInFlight = true;
  const activityId = "dashboard-refresh";
  try {
    elements.errorPanel.hidden = true;
    const taskDefinitions = [
      ["Systemstatus", refreshSystemStatus],
      ["EcoFlow", refreshEcoFlow],
      ["Home Assistant", refreshHomeAssistant],
      ["Alerts", refreshAlerts],
      ["Dateien", refreshRecentFiles],
      ["Gmail", refreshEmail],
      ["TimeTree", refreshTimeTree],
      ["Smart Home", refreshSmartHomeActions],
      ["Auto-Policy", refreshSmartHomeAutoPolicy],
      ["HA-Control", refreshHaControlPolicy],
      ["Memory", refreshMemory],
      ["Knowledge", refreshKnowledge],
      ["Aktionen", refreshActions],
      ["Performance", refreshPerformance],
    ];
    const now = Date.now();
    if (now - lastEntityCatalogRefresh >= entityCatalogRefreshMs) {
      lastEntityCatalogRefresh = now;
      taskDefinitions.push(["HA-Entity-Katalog", refreshHaEntityCatalog]);
    }
    let completed = 0;
    let failed = 0;
    const total = taskDefinitions.length;
    startActivity(activityId, "Dashboard wird aktualisiert", {
      detail: "Dashboard-Daten werden geladen",
      progress: `0 von ${total} Bereichen`,
      category: "dashboard",
      timeoutMs: 20000,
    });
    await Promise.all(taskDefinitions.map(async ([name, task]) => {
      try {
        await task();
      } catch (error) {
        failed += 1;
        console.warn(`[Hammer Jarvis Dashboard] ${name} konnte nicht aktualisiert werden.`, error);
      } finally {
        completed += 1;
        updateActivity(activityId, {
          detail: failed > 0 ? `${failed} Bereich(e) fehlgeschlagen.` : "Dashboard-Daten werden geladen",
          progress: `${completed} von ${total} Bereichen`,
        });
      }
    }));
    if (failed > 0) {
      failActivity(activityId, `Dashboard bereit, ${failed} Bereich(e) konnten nicht geladen werden.`);
      elements.errorPanel.hidden = false;
    } else {
      finishActivity(activityId, "Dashboard bereit.");
    }
  } catch (error) {
    failActivity(activityId, "Dashboard konnte nicht aktualisiert werden.");
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
  try {
    wireDashboardEvents();
  } catch (error) {
    console.error("[Hammer Jarvis] Event-Handler konnten nicht vollständig registriert werden.", error);
  }
}

function wireDashboardEvents() {
  elements.openCommandPalette?.addEventListener("click", openCommandPalette);
  elements.closeCommandPalette?.addEventListener("click", closeCommandPalette);
  elements.commandPaletteInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      parseCommandPaletteIntent();
    }
    if (event.key === "Escape") {
      closeCommandPalette();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.ctrlKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openCommandPalette();
    }
    if (event.key === "Escape" && elements.commandPalette && !elements.commandPalette.hidden) {
      closeCommandPalette();
    }
  });
  elements.sendCommand.addEventListener("click", () => withButtonLoading(
    elements.sendCommand,
    "Senden...",
    () => sendChatMessage(elements.commandInput.value),
  ));
  elements.commandInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      sendChatMessage(elements.commandInput.value);
    }
  });
  elements.voiceButton.addEventListener("click", () => startCommandRecognition({ source: "button", autoSend: true }));
  elements.chatMicButton.addEventListener("click", () => startCommandRecognition({ source: "button", autoSend: true }));
  elements.handsFreeToggle?.addEventListener("click", toggleHandsFreeMode);
  elements.handsFreeChatToggle?.addEventListener("click", toggleHandsFreeMode);
  elements.desktopReconnectButton?.addEventListener("click", () => {
    desktopEventReconnectAttempt = 0;
    connectDesktopEventBridge();
  });
  elements.clearActivities.addEventListener("click", () => {
    recentActivities.length = 0;
    renderActivities();
  });
  elements.speechToggle.addEventListener("click", () => {
    speechOutputEnabled = !speechOutputEnabled;
    if (!speechOutputEnabled) {
      cancelSpeechOutput(false);
    }
    elements.speechToggle.textContent = speechOutputEnabled ? "Sprachausgabe: Ein" : "Sprachausgabe: Aus";
    setVoiceStatus(speechOutputEnabled ? "Sprachausgabe ist eingeschaltet." : "Sprachausgabe ist ausgeschaltet.");
  });
  if (elements.voiceSelect) {
    elements.voiceSelect.addEventListener("change", () => {
      if (elements.voiceSelect.value) {
        storeVoiceId(elements.voiceSelect.value);
      } else {
        removeStoredVoiceId();
      }
      const selectedVoice = getSelectedSpeechVoice();
      setText("voiceSelectStatus", selectedVoice ? `Aktive Stimme: ${selectedVoice.name || "Browserstandard"}` : "Browserstandard wird verwendet.");
    });
  }
  if (elements.reloadVoices) {
    elements.reloadVoices.addEventListener("click", reloadSpeechVoices);
  }
  for (const button of elements.quickCommands) {
    button.addEventListener("click", () => runQuickCommand(button.dataset.command || button.textContent));
  }
  for (const button of elements.fileButtons) {
    button.addEventListener("click", () => runQuickCommand(button.dataset.command || "erstelle eine Excel fuer Ausgaben"));
  }
  elements.fileSearchButton.addEventListener("click", () => withButtonLoading(elements.fileSearchButton, "Suche...", searchFiles));
  elements.fileContentSearchButton.addEventListener("click", () => withButtonLoading(elements.fileContentSearchButton, "Suche Inhalte...", () => {
    elements.fileSearchMode.value = "content";
    return searchFiles();
  }));
  elements.fileSearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      withButtonLoading(elements.fileSearchButton, "Suche...", searchFiles);
    }
  });
  elements.openLatestFile.addEventListener("click", () => withButtonLoading(elements.openLatestFile, "Öffne...", async () => {
    try {
      const response = await postJson("/assistant/files/open-latest", {}, {
        activityId: "open-latest-file",
        activityTitle: "Letzte Datei wird geöffnet",
        activityDetail: "Dateiaktion wird gesendet",
      });
      setText("fileStatus", response.message || "Letzte Datei wurde geöffnet.");
      finishActivity("open-latest-file", response.message || "Letzte Datei wurde geöffnet.");
    } catch (error) {
      setText("fileStatus", "Letzte Datei konnte nicht geöffnet werden.");
      failActivity("open-latest-file", "Letzte Datei konnte nicht geöffnet werden.");
    }
  }));
  elements.webResearchButton.addEventListener("click", () => withButtonLoading(elements.webResearchButton, "Recherchiere...", runWebResearch));
  elements.webResearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      withButtonLoading(elements.webResearchButton, "Recherchiere...", runWebResearch);
    }
  });
  elements.refreshWatchers.addEventListener("click", () => withButtonLoading(elements.refreshWatchers, "Lade...", refreshAlerts));
  elements.refreshPerformance.addEventListener("click", () => withButtonLoading(elements.refreshPerformance, "Messe...", refreshPerformance));
  elements.runOllamaBenchmark.addEventListener("click", () => withButtonLoading(elements.runOllamaBenchmark, "Benchmark...", runOllamaBenchmark));
  elements.researchAnswerButton?.addEventListener("click", () => withButtonLoading(elements.researchAnswerButton, "Baue Antwort...", buildResearchAnswer));
  elements.syncHaEntities.addEventListener("click", () => withButtonLoading(elements.syncHaEntities, "Sync...", syncHaEntities));
  elements.haEntitySearchButton.addEventListener("click", () => withButtonLoading(elements.haEntitySearchButton, "Suche...", searchHaEntities));
  elements.haEntitySearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      withButtonLoading(elements.haEntitySearchButton, "Suche...", searchHaEntities);
    }
  });
  for (const button of elements.haEntityFilters) {
    button.addEventListener("click", () => filterHaEntities(button.dataset.filter));
  }
  for (const button of elements.topNavButtons || []) {
    if (button.matches(".top-tab:not(:disabled)") && button.dataset.target) {
      button.addEventListener("click", () => navigateDashboardSection(button.dataset.target, button));
    }
  }
  elements.refreshSmartHomeActions.addEventListener("click", () => withButtonLoading(elements.refreshSmartHomeActions, "Lade...", refreshSmartHomeActions));
  elements.discoverSmartHomeCandidates.addEventListener("click", () => withButtonLoading(elements.discoverSmartHomeCandidates, "Suche...", discoverSmartHomeCandidates));
  elements.refreshSmartHomeAutoPolicy.addEventListener("click", () => withButtonLoading(elements.refreshSmartHomeAutoPolicy, "Lade...", refreshSmartHomeAutoPolicy));
  elements.refreshHaControlPolicy.addEventListener("click", () => withButtonLoading(elements.refreshHaControlPolicy, "Lade...", refreshHaControlPolicy));
  elements.haControlPrepareButton.addEventListener("click", () => withButtonLoading(elements.haControlPrepareButton, "Prüfe...", prepareHaControlCommand));
  elements.haControlCommandInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      withButtonLoading(elements.haControlPrepareButton, "Prüfe...", prepareHaControlCommand);
    }
  });
  elements.refreshMemory.addEventListener("click", () => withButtonLoading(elements.refreshMemory, "Lade...", refreshMemory));
  elements.memorySearchButton.addEventListener("click", () => withButtonLoading(elements.memorySearchButton, "Suche...", searchMemory));
  elements.memoryAddButton.addEventListener("click", () => withButtonLoading(elements.memoryAddButton, "Speichere...", addMemory));
  elements.memorySearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      withButtonLoading(elements.memorySearchButton, "Suche...", searchMemory);
    }
  });
  elements.memoryAddInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      withButtonLoading(elements.memoryAddButton, "Speichere...", addMemory);
    }
  });
  elements.refreshKnowledge.addEventListener("click", () => withButtonLoading(elements.refreshKnowledge, "Lade...", refreshKnowledge));
  elements.knowledgeSelectFilesButton?.addEventListener("click", () => elements.knowledgeFileInput?.click());
  elements.knowledgeFileInput?.addEventListener("change", () => uploadKnowledgeFiles(elements.knowledgeFileInput.files));
  elements.knowledgeDropZone?.addEventListener("dragover", (event) => {
    event.preventDefault();
    elements.knowledgeDropZone.classList.add("is-dragging");
  });
  elements.knowledgeDropZone?.addEventListener("dragleave", () => elements.knowledgeDropZone.classList.remove("is-dragging"));
  elements.knowledgeDropZone?.addEventListener("drop", (event) => {
    event.preventDefault();
    elements.knowledgeDropZone.classList.remove("is-dragging");
    uploadKnowledgeFiles(event.dataTransfer?.files);
  });
  elements.knowledgeDropZone?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      elements.knowledgeFileInput?.click();
    }
  });
  elements.knowledgeSearchButton.addEventListener("click", () => withButtonLoading(elements.knowledgeSearchButton, "Suche...", searchKnowledge));
  elements.knowledgeIndexButton.addEventListener("click", () => withButtonLoading(elements.knowledgeIndexButton, "Indexiere...", indexKnowledgePath));
  elements.knowledgeSearchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      withButtonLoading(elements.knowledgeSearchButton, "Suche...", searchKnowledge);
    }
  });
  elements.knowledgeIndexInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      withButtonLoading(elements.knowledgeIndexButton, "Indexiere...", indexKnowledgePath);
    }
  });
  elements.engineeringOpenProject?.addEventListener("click", () => withButtonLoading(elements.engineeringOpenProject, "Lade...", openEngineeringProject));
  elements.runEngineeringDiagnostics?.addEventListener("click", () => withButtonLoading(elements.runEngineeringDiagnostics, "Diagnose...", runEngineeringDiagnostics));
  elements.engineeringProjectPath?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      withButtonLoading(elements.engineeringOpenProject, "Lade...", openEngineeringProject);
    }
  });
  elements.protoolAnalyzeButton?.addEventListener("click", () => withButtonLoading(elements.protoolAnalyzeButton, "Analysiere...", analyzeProToolCsv));
  elements.protoolImportButton?.addEventListener("click", () => withButtonLoading(elements.protoolImportButton, "Importiere...", importProToolToGraph));
  elements.protoolBatchAnalyzeButton?.addEventListener("click", () => withButtonLoading(elements.protoolBatchAnalyzeButton, "Analysiere Batch...", analyzeProToolBatch));
  elements.protoolFilePath?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      withButtonLoading(elements.protoolAnalyzeButton, "Analysiere...", analyzeProToolCsv);
    }
  });
  elements.protoolFilePath?.addEventListener("input", () => {
    if (text(elements.protoolFilePath?.value, "").trim()) {
      selectedProToolFile = null;
      if (elements.protoolFilePicker) {
        elements.protoolFilePicker.value = "";
      }
      setText("protoolSelectedFileName", "Ausgewählte Datei: -");
    }
  });
  elements.protoolBrowseButton?.addEventListener("click", () => elements.protoolFilePicker?.click());
  elements.protoolFilePicker?.addEventListener("change", () => {
    const selectedFile = elements.protoolFilePicker.files?.[0];
    selectedProToolFile = selectedFile || null;
    if (elements.protoolFilePath) {
      elements.protoolFilePath.value = "";
    }
    setText("protoolSelectedFileName", selectedFile ? `Ausgewählte Datei: ${selectedFile.name}` : "Ausgewählte Datei: -");
    if (selectedFile) {
      setText("protoolStatus", "Datei ausgewählt. Die Analyse wird per Upload ausgeführt.");
    }
  });
  elements.refreshActions.addEventListener("click", () => withButtonLoading(elements.refreshActions, "Lade...", refreshActions));
  elements.runWatchers.addEventListener("click", () => withButtonLoading(elements.runWatchers, "Prüfe...", async () => {
    try {
      await postJson("/assistant/watchers/run", {}, {
        activityId: "watchers-run",
        activityTitle: "Watcher werden ausgeführt",
        activityDetail: "Regeln werden geprüft",
      });
      await refreshAlerts();
      finishActivity("watchers-run", "Watcher-Prüfung abgeschlossen.");
    } catch (error) {
      elements.errorPanel.hidden = false;
      failActivity("watchers-run", "Watcher-Prüfung fehlgeschlagen.");
    }
  }));
}

function initializeSpeechRecognitionAvailability() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    setVoiceStatus("Sprachsteuerung nicht unterstützt.", "error");
  }
}

function initializeRemainingDashboardSafely() {
  try {
    initializeSpeechRecognitionAvailability();
    initializeHandsFreeStatus();
    connectDesktopEventBridge();
    updateClock();
    refreshDashboard();
    refreshCommandCenter();
    window.setInterval(updateClock, 1000);
    window.setInterval(refreshDashboard, refreshMs);
  } catch (error) {
    reportDashboardBootError(error);
  }
}

function initDashboard() {
  bindElements();
  wireEvents();
  window.addEventListener("pagehide", cleanupHandsFreeOnUnload);
  window.addEventListener("beforeunload", cleanupHandsFreeOnUnload);
  initializeVoiceSubsystemSafely();
  initializeRemainingDashboardSafely();
}

function reportDashboardBootError(error) {
  console.error("[Hammer Jarvis] Dashboard-Bootstrap fehlgeschlagen.", error);
  if (elements.errorPanel) {
    elements.errorPanel.hidden = false;
  }
}

function bootstrapDashboard() {
  if (dashboardInitialized) {
    return;
  }
  dashboardInitialized = true;
  try {
    initDashboard();
  } catch (error) {
    reportDashboardBootError(error);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootstrapDashboard, { once: true });
} else {
  bootstrapDashboard();
}

window.HammerJarvisDashboard = {
  buildDesktopEventSocketUrl,
};
