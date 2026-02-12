import {
  createSession,
  deleteLastMessage,
  forkBranch,
  getCurrentProvider,
  getModels,
  patchMessage,
  getRuntimeSettings,
  getSessionDetail,
  getTimeline,
  listSessionHistory,
  listBranches,
  patchRuntimeSettings,
  pauseSession,
  resumeSession,
  updateSettings,
  selectModel,
  setProvider,
  startSession,
  submitIntervention,
  switchBranch,
} from "./api.js";
import {
  applyTranslations,
  getCurrentLocale,
  getSupportedLocales,
  initI18n,
  setLocale,
  t,
} from "./i18n.js";
import {
  clearProviderApiKey,
  getRememberApiKey,
  loadProviderApiKey,
  saveProviderApiKey,
  setRememberApiKey,
} from "./local_secrets.js";
import { connectWebSocket, closeWebSocket } from "./ws.js";
import {
  appendMessage,
  replaceMessage,
  setBranches,
  setStore,
  setTimeline,
  store,
} from "./store.js";
import {
  addLog,
  appendTimelineMessage,
  renderTimeline,
  setTimelineEditHandler,
  setConnectionState,
  setRunnerState,
  setSessionId,
} from "./ui.js";

const elements = {
  mainLayout: document.getElementById("mainLayout"),
  settingsPage: document.getElementById("settingsPage"),
  openSettingsTabBtn: document.getElementById("openSettingsTab"),
  closeSettingsTabBtn: document.getElementById("closeSettingsTab"),
  title: document.getElementById("sessionTitle"),
  worldPreset: document.getElementById("worldPreset"),
  initialTime: document.getElementById("initialTime"),
  timeStepValue: document.getElementById("timeStepValue"),
  timeStepUnit: document.getElementById("timeStepUnit"),
  tickLabel: document.getElementById("tickLabel"),
  postDelay: document.getElementById("postDelay"),
  languageSelect: document.getElementById("languageSelect"),
  createBtn: document.getElementById("createSession"),
  loadSessionId: document.getElementById("loadSessionId"),
  loadSessionBtn: document.getElementById("loadSession"),
  refreshSessionHistoryBtn: document.getElementById("refreshSessionHistory"),
  sessionHistoryList: document.getElementById("sessionHistoryList"),
  providerSelect: document.getElementById("providerSelect"),
  apiKey: document.getElementById("apiKey"),
  rememberApiKey: document.getElementById("rememberApiKey"),
  baseUrl: document.getElementById("baseUrl"),
  loadModelsBtn: document.getElementById("loadModels"),
  modelSelect: document.getElementById("modelSelect"),
  runtimeSettingsForm: document.getElementById("runtimeSettingsForm"),
  loadRuntimeSettingsBtn: document.getElementById("loadRuntimeSettings"),
  applyRuntimeSettingsBtn: document.getElementById("applyRuntimeSettings"),
  startBtn: document.getElementById("startSession"),
  pauseBtn: document.getElementById("pauseSession"),
  resumeBtn: document.getElementById("resumeSession"),
  refreshBtn: document.getElementById("refreshTimeline"),
  forkBtn: document.getElementById("forkBranch"),
  deleteLastBtn: document.getElementById("deleteLast"),
  interventionInput: document.getElementById("interventionInput"),
  sendInterventionBtn: document.getElementById("sendIntervention"),
  branchTabs: document.getElementById("branchTabs"),
  appVersionBadge: document.getElementById("appVersionBadge"),
  appVersionFooter: document.getElementById("appVersionFooter"),
};

const LAST_SESSION_ID_KEY = "worldline.lastSessionId.v1";
const DEFAULT_APP_VERSION = "1.0";
const settingsFieldOrder = [
  "APP_ENV",
  "APP_VERSION",
  "APP_HOST",
  "APP_PORT",
  "CORS_ORIGINS",
  "DB_URL",
  "LOG_LEVEL",
  "APP_SECRET_KEY",
  "OPENAI_BASE_URL",
  "OLLAMA_BASE_URL",
  "DEEPSEEK_BASE_URL",
  "GEMINI_BASE_URL",
  "DEFAULT_POST_GEN_DELAY_SEC",
  "DEFAULT_TICK_LABEL",
  "MEMORY_MODE",
  "MEMORY_MAX_SNIPPETS",
  "MEMORY_MAX_CHARS",
  "EMBED_PROVIDER",
  "EMBED_MODEL",
  "EMBED_DIM",
  "EMBED_OPENAI_API_KEY",
  "EVENT_DICE_ENABLED",
  "EVENT_GOOD_EVENT_PROB",
  "EVENT_BAD_EVENT_PROB",
  "EVENT_REBEL_PROB",
  "EVENT_MIN_EVENTS",
  "EVENT_MAX_EVENTS",
  "EVENT_DEFAULT_HEMISPHERE",
];
const hiddenSettingsKeys = new Set(["APP_SECRET_KEY", "EMBED_OPENAI_API_KEY"]);
let runtimeSettingsSnapshot = {};

const providerDefaults = {
  openai: "https://api.openai.com",
  ollama: "http://localhost:11434",
  deepseek: "https://api.deepseek.com",
  gemini: "https://generativelanguage.googleapis.com",
};

function setRunnerControlHighlight(activeButton) {
  const buttons = [elements.startBtn, elements.pauseBtn, elements.resumeBtn].filter(Boolean);
  buttons.forEach((button) => {
    button.classList.remove("accent");
    if (!button.classList.contains("ghost")) {
      button.classList.add("ghost");
    }
    button.setAttribute("aria-pressed", "false");
  });
  if (!activeButton) return;
  activeButton.classList.remove("ghost");
  activeButton.classList.add("accent");
  activeButton.setAttribute("aria-pressed", "true");
}

function syncRunnerState(state) {
  setStore({ runnerState: state });
  setRunnerState(state);
}

function syncConnectionState(state) {
  setStore({ connectionState: state });
  setConnectionState(state);
}

function setControlsEnabled(enabled) {
  const hasModel = Boolean(store.provider && store.provider.model);
  const hasBranch = Boolean(store.activeBranchId);

  elements.startBtn.disabled = !enabled || !hasModel;
  elements.pauseBtn.disabled = !enabled;
  elements.resumeBtn.disabled = !enabled || !hasModel;
  elements.refreshBtn.disabled = !enabled || !hasBranch;
  elements.forkBtn.disabled = !enabled || !hasBranch;
  elements.deleteLastBtn.disabled = !enabled || !hasBranch;
  elements.sendInterventionBtn.disabled = !enabled || !hasBranch;
  elements.loadModelsBtn.disabled = !enabled;
  elements.modelSelect.disabled = !enabled;
  elements.interventionInput.disabled = !enabled || !hasBranch;
}

function renderModelOptions(models) {
  elements.modelSelect.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = t("provider.model_placeholder");
  elements.modelSelect.appendChild(placeholder);
  models.forEach((model) => {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    elements.modelSelect.appendChild(option);
  });
}

function renderBranchTabs() {
  elements.branchTabs.innerHTML = "";
  store.branches.forEach((branch) => {
    const button = document.createElement("button");
    button.className = `branch-tab${branch.id === store.activeBranchId ? " active" : ""}`;
    button.textContent = branch.name;
    button.type = "button";
    button.addEventListener("click", () => {
      handleSwitchBranch(branch.id);
    });
    elements.branchTabs.appendChild(button);
  });
}

function applyProviderDefaults(provider, forceValue = true) {
  const defaultUrl = providerDefaults[provider] || "";
  elements.baseUrl.placeholder = defaultUrl || t("provider.base_url_placeholder");
  if (forceValue) {
    elements.baseUrl.value = defaultUrl;
  }
}

function renderIntervalUnitOptions() {
  const unitKeyMap = {
    day: "setup.interval_unit_day",
    week: "setup.interval_unit_week",
    month: "setup.interval_unit_month",
    year: "setup.interval_unit_year",
  };
  const current = elements.timeStepUnit.value || "month";
  elements.timeStepUnit.innerHTML = "";
  Object.entries(unitKeyMap).forEach(([value, key]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = t(key);
    if (value === current) {
      option.selected = true;
    }
    elements.timeStepUnit.appendChild(option);
  });
}

function formatIntervalLabel(stepValue, stepUnit) {
  const count = Math.max(1, Number(stepValue || 1));
  const unitText = t(`setup.interval_unit_${stepUnit}`);
  const template = t("setup.interval_label");
  return template
    .replace("{value}", String(count))
    .replace("{unit}", unitText);
}

function syncTickLabel() {
  elements.tickLabel.value = formatIntervalLabel(
    Number(elements.timeStepValue.value || 1),
    elements.timeStepUnit.value || "month"
  );
}

function nowLocalDateTimeInputValue() {
  const now = new Date();
  const year = String(now.getFullYear()).padStart(4, "0");
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  const hour = String(now.getHours()).padStart(2, "0");
  const minute = String(now.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

function toIsoFromLocalInput(localInput) {
  const value = String(localInput || "").trim();
  if (!value) return null;

  const normalized = value
    .replace(/\//g, "-")
    .replace(/年/g, "-")
    .replace(/月/g, "-")
    .replace(/日/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/-+$/, "");

  const pattern =
    /^(\d{1,4})(?:-(\d{1,2})(?:-(\d{1,2})(?:[T ](\d{1,2})(?::(\d{1,2})(?::(\d{1,2}))?)?)?)?)?(?:\s*(Z|[+-]\d{2}:\d{2}))?$/;
  const match = normalized.match(pattern);
  if (!match) return null;

  const year = Number(match[1]);
  const month = match[2] ? Number(match[2]) : 1;
  const day = match[3] ? Number(match[3]) : 1;
  const hour = match[4] ? Number(match[4]) : 0;
  const minute = match[5] ? Number(match[5]) : 0;
  const second = match[6] ? Number(match[6]) : 0;
  const timezone = match[7] ? (match[7] === "Z" ? "+00:00" : match[7]) : "+00:00";

  if (year < 1 || year > 9999) return null;
  if (month < 1 || month > 12) return null;
  if (day < 1 || day > daysInMonth(year, month)) return null;
  if (hour < 0 || hour > 23) return null;
  if (minute < 0 || minute > 59) return null;
  if (second < 0 || second > 59) return null;

  const yy = String(year).padStart(4, "0");
  const mm = String(month).padStart(2, "0");
  const dd = String(day).padStart(2, "0");
  const hh = String(hour).padStart(2, "0");
  const mi = String(minute).padStart(2, "0");
  const ss = String(second).padStart(2, "0");
  return `${yy}-${mm}-${dd}T${hh}:${mi}:${ss}${timezone}`;
}

function fromIsoToLocalInput(iso) {
  const value = String(iso || "").trim();
  if (!value) return "";
  const match = value.match(
    /^([+-]?\d{4,6})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?$/
  );
  if (!match) {
    return "";
  }
  const yearRaw = match[1].replace(/^\+/, "");
  if (yearRaw.startsWith("-")) return "";
  const year =
    yearRaw.length >= 4 ? yearRaw : String(Number(yearRaw || 0)).padStart(4, "0");
  return `${year}-${match[2]}-${match[3]}T${match[4]}:${match[5]}`;
}

function daysInMonth(year, month) {
  if ([1, 3, 5, 7, 8, 10, 12].includes(month)) return 31;
  if ([4, 6, 9, 11].includes(month)) return 30;
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  return leapYear ? 29 : 28;
}

function buildTimelineConfigFromInputs() {
  const initialTimeISO = toIsoFromLocalInput(elements.initialTime.value) || new Date().toISOString();
  const stepValue = Math.max(1, Number(elements.timeStepValue.value || 1));
  const stepUnit = elements.timeStepUnit.value || "month";
  return { initialTimeISO, stepValue, stepUnit };
}

function applyTimelineConfigToInputs(config) {
  if (!config) return;
  elements.initialTime.value = fromIsoToLocalInput(config.initialTimeISO) || nowLocalDateTimeInputValue();
  elements.timeStepValue.value = String(Math.max(1, Number(config.stepValue || 1)));
  elements.timeStepUnit.value = config.stepUnit || "month";
  syncTickLabel();
}

function fillLanguageOptions() {
  elements.languageSelect.innerHTML = "";
  getSupportedLocales().forEach((locale) => {
    const option = document.createElement("option");
    option.value = locale.code;
    option.textContent = locale.label;
    elements.languageSelect.appendChild(option);
  });
  elements.languageSelect.value = getCurrentLocale();
}

function applyLocalePresentation() {
  const locale = getCurrentLocale();
  document.documentElement.lang = locale;
  document.body.classList.toggle("locale-zh", locale.toLowerCase().startsWith("zh"));
}

function normalizeAppVersion(rawValue) {
  const raw = String(rawValue || "").trim();
  const clean = raw || DEFAULT_APP_VERSION;
  if (/^v/i.test(clean)) {
    return `V${clean.slice(1).trim()}`;
  }
  return `V${clean}`;
}

function renderAppVersion(rawValue) {
  const label = normalizeAppVersion(rawValue);
  if (elements.appVersionBadge) {
    elements.appVersionBadge.textContent = label;
  }
  if (elements.appVersionFooter) {
    elements.appVersionFooter.textContent = label;
  }
}

function applyRuntimeSettingsSnapshot(settings) {
  runtimeSettingsSnapshot = settings || {};
  renderRuntimeSettingsForm(runtimeSettingsSnapshot);
  renderAppVersion(runtimeSettingsSnapshot.APP_VERSION);
}

function normalizeError(error) {
  const raw = String(error?.message || error || "").trim();
  if (!raw) return "unknown error";
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail.trim();
    }
  } catch (_) {
    return raw;
  }
  return raw;
}

function logInfo(key, vars = {}) {
  addLog(t(key, vars));
}

function logError(key, error) {
  addLog(t(key, { error: normalizeError(error) }));
}

function loadLocalApiKeyForProvider(provider, silent = false) {
  if (!elements.rememberApiKey.checked) return;
  const localKey = loadProviderApiKey(provider);
  if (!localKey) return;
  elements.apiKey.value = localKey;
  if (!silent) {
    logInfo("log.local_key_loaded", { provider });
  }
}

function persistApiKeyIfNeeded(provider, apiKey) {
  if (elements.rememberApiKey.checked) {
    saveProviderApiKey(provider, apiKey);
    if (String(apiKey || "").trim()) {
      logInfo("log.local_key_saved", { provider });
    }
    return;
  }
  clearProviderApiKey(provider);
}

function getEffectiveApiKey(provider) {
  const inlineKey = String(elements.apiKey.value || "").trim();
  if (inlineKey) return inlineKey;
  if (!elements.rememberApiKey.checked) return "";
  return String(loadProviderApiKey(provider) || "").trim();
}

function buildCurrentProviderState() {
  const provider = elements.providerSelect.value;
  const selectedModel = elements.modelSelect.value || store.provider.model || null;
  const currentModels = store.provider.name === provider ? store.provider.models || [] : [];
  const models = [...currentModels];
  if (selectedModel && !models.includes(selectedModel)) {
    models.unshift(selectedModel);
  }
  return {
    name: provider,
    baseUrl: elements.baseUrl.value || providerDefaults[provider] || "",
    model: selectedModel,
    models,
  };
}

function connectSessionSocket(sessionId) {
  connectWebSocket(sessionId, {
    onOpen: async () => {
      syncConnectionState("connected");
      logInfo("log.ws_connected");
      await loadBranches();
      await loadTimeline();
    },
    onClose: () => {
      syncConnectionState("disconnected");
      logInfo("log.ws_disconnected_reconnecting");
    },
    onEvent: handleWsEvent,
    onError: (err) => logError("error.ws_error", err),
  });
}

async function hydrateProviderForSession(sessionId) {
  try {
    const current = await getCurrentProvider(sessionId);
    if (!current.provider) {
      const fallback = buildCurrentProviderState();
      setStore({ provider: fallback });
      renderModelOptions(fallback.models || []);
      if (fallback.model) {
        elements.modelSelect.value = fallback.model;
      }
      return;
    }

    elements.providerSelect.value = current.provider;
    applyProviderDefaults(current.provider, false);
    elements.baseUrl.value = current.base_url || providerDefaults[current.provider] || "";
    loadLocalApiKeyForProvider(current.provider, true);

    let models = [];
    if (current.has_api_key) {
      try {
        const response = await getModels(sessionId, current.provider);
        models = response.models || [];
      } catch (_) {
        models = [];
      }
    }

    const selectedModel = current.model_name || null;
    if (selectedModel && !models.includes(selectedModel)) {
      models.unshift(selectedModel);
    }

    setStore({
      provider: {
        name: current.provider,
        baseUrl: elements.baseUrl.value || "",
        model: selectedModel,
        models,
      },
    });
    renderModelOptions(models);
    if (selectedModel) {
      elements.modelSelect.value = selectedModel;
    }
  } catch (err) {
    logError("error.provider_restore_failed", err);
  }
}

async function tryRebindProviderToSession(sessionId) {
  const providerState = buildCurrentProviderState();
  if (!providerState.model) return;
  try {
    await setProvider(sessionId, {
      provider: providerState.name,
      api_key: getEffectiveApiKey(providerState.name) || null,
      base_url: providerState.baseUrl || null,
      model_name: providerState.model,
    });
    setStore({ provider: providerState });
    logInfo("log.provider_rebound", { model: providerState.model });
  } catch (err) {
    logError("log.provider_rebound_failed", err);
  }
}

function setSettingsPageOpen(opened) {
  elements.mainLayout.classList.toggle("is-hidden", opened);
  elements.settingsPage.classList.toggle("is-hidden", !opened);
}

function normalizeSettingsEntries(settings) {
  const map = settings && typeof settings === "object" ? settings : {};
  const rows = Object.entries(map);
  rows.sort(([left], [right]) => {
    const leftOrder = settingsFieldOrder.indexOf(left);
    const rightOrder = settingsFieldOrder.indexOf(right);
    const normalizedLeft = leftOrder === -1 ? Number.MAX_SAFE_INTEGER : leftOrder;
    const normalizedRight = rightOrder === -1 ? Number.MAX_SAFE_INTEGER : rightOrder;
    if (normalizedLeft !== normalizedRight) {
      return normalizedLeft - normalizedRight;
    }
    return left.localeCompare(right);
  });
  return rows;
}

function detectSettingType(value) {
  if (typeof value === "boolean") return "bool";
  if (typeof value === "number") {
    return Number.isInteger(value) ? "int" : "float";
  }
  if (Array.isArray(value) || (value && typeof value === "object")) return "json";
  return "string";
}

function getSettingDescription(settingKey) {
  const key = `settings.desc.${settingKey}`;
  const translated = t(key);
  if (translated !== key) {
    return translated;
  }
  return t("settings.desc.default");
}

function createSettingInput(settingKey, value) {
  const type = detectSettingType(value);

  if (type === "bool") {
    const select = document.createElement("select");
    select.dataset.settingKey = settingKey;
    select.dataset.settingType = type;

    const trueOption = document.createElement("option");
    trueOption.value = "true";
    trueOption.textContent = t("settings.value.true");
    select.appendChild(trueOption);

    const falseOption = document.createElement("option");
    falseOption.value = "false";
    falseOption.textContent = t("settings.value.false");
    select.appendChild(falseOption);

    select.value = value ? "true" : "false";
    return select;
  }

  const baseInput =
    type === "json" || (typeof value === "string" && String(value).length > 120)
      ? document.createElement("textarea")
      : document.createElement("input");
  baseInput.dataset.settingKey = settingKey;
  baseInput.dataset.settingType = type;
  if (type === "int" || type === "float") {
    baseInput.type = "number";
    if (type === "float") {
      baseInput.step = "0.01";
    }
  }

  if (baseInput.tagName === "TEXTAREA") {
    baseInput.rows = 3;
  }

  if (hiddenSettingsKeys.has(settingKey)) {
    if (baseInput.tagName === "INPUT") {
      baseInput.type = "password";
    }
  }

  if (type === "json") {
    baseInput.value = JSON.stringify(value, null, 2);
  } else if (value === null || value === undefined) {
    baseInput.value = "";
  } else {
    baseInput.value = String(value);
  }
  return baseInput;
}

function renderRuntimeSettingsForm(settings) {
  elements.runtimeSettingsForm.innerHTML = "";
  const rows = normalizeSettingsEntries(settings);
  rows.forEach(([settingKey, value]) => {
    const item = document.createElement("article");
    item.className = "setting-item";

    const heading = document.createElement("h3");
    heading.textContent = settingKey;
    item.appendChild(heading);

    const desc = document.createElement("p");
    desc.textContent = getSettingDescription(settingKey);
    item.appendChild(desc);

    const input = createSettingInput(settingKey, value);
    item.appendChild(input);
    elements.runtimeSettingsForm.appendChild(item);
  });
}

function parseRuntimeSettingInput(input) {
  const type = input.dataset.settingType || "string";
  const raw = String(input.value || "").trim();

  if (type === "bool") {
    return raw === "true";
  }
  if (type === "int") {
    if (!raw) {
      throw new Error(`empty integer for ${input.dataset.settingKey}`);
    }
    const parsed = Number.parseInt(raw, 10);
    if (Number.isNaN(parsed)) throw new Error(`invalid integer for ${input.dataset.settingKey}`);
    return parsed;
  }
  if (type === "float") {
    if (!raw) {
      throw new Error(`empty number for ${input.dataset.settingKey}`);
    }
    const parsed = Number.parseFloat(raw);
    if (Number.isNaN(parsed)) throw new Error(`invalid number for ${input.dataset.settingKey}`);
    return parsed;
  }
  if (type === "json") {
    if (!raw) return {};
    return JSON.parse(raw);
  }
  return raw;
}

function collectRuntimeSettingsUpdates() {
  const updates = {};
  elements.runtimeSettingsForm
    .querySelectorAll("[data-setting-key]")
    .forEach((node) => {
      const key = node.dataset.settingKey;
      if (!key) return;
      updates[key] = parseRuntimeSettingInput(node);
    });
  return updates;
}

function saveLastSessionId(sessionId) {
  const value = String(sessionId || "").trim();
  if (!value) return;
  localStorage.setItem(LAST_SESSION_ID_KEY, value);
}

function loadLastSessionId() {
  return String(localStorage.getItem(LAST_SESSION_ID_KEY) || "").trim();
}

function formatSessionTime(isoTime) {
  const raw = String(isoTime || "").trim();
  if (!raw) return "";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return "";
  return new Intl.DateTimeFormat(getCurrentLocale(), {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function renderSessionHistory(sessions) {
  elements.sessionHistoryList.innerHTML = "";
  const rows = Array.isArray(sessions) ? sessions : [];
  if (rows.length === 0) {
    const empty = document.createElement("div");
    empty.className = "session-history-empty";
    empty.textContent = t("setup.history_empty");
    elements.sessionHistoryList.appendChild(empty);
    return;
  }

  rows.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "session-history-item";

    const title = document.createElement("strong");
    title.textContent = item.title || `${t("setup.load_session_id")} ${item.session_id.slice(0, 10)}`;
    button.appendChild(title);

    const meta = document.createElement("span");
    const runnerLabel = item.running ? t("state.runner.running") : t("state.runner.paused");
    meta.textContent = `${item.session_id} · ${formatSessionTime(item.updated_at)} · ${runnerLabel}`;
    button.appendChild(meta);

    button.addEventListener("click", () => {
      elements.loadSessionId.value = item.session_id;
      handleLoadSession().catch((err) => logError("error.load_session_failed", err));
    });

    elements.sessionHistoryList.appendChild(button);
  });
}

async function handleRefreshSessionHistory() {
  try {
    const response = await listSessionHistory(50);
    renderSessionHistory(response.sessions || []);
    logInfo("log.history_loaded");
  } catch (err) {
    logError("error.history_load_failed", err);
  }
}

async function loadBranches() {
  if (!store.session) return;
  const data = await listBranches(store.session.session_id);
  setBranches(data.branches || [], data.active_branch_id || null);
  renderBranchTabs();
  setControlsEnabled(Boolean(store.session));
}

async function loadTimeline() {
  if (!store.session || !store.activeBranchId) return;
  try {
    const data = await getTimeline(store.session.session_id, store.activeBranchId);
    setTimeline(store.activeBranchId, data.messages);
    renderTimeline(data.messages, store.timelineConfig);
  } catch (err) {
    logError("error.timeline_load_failed", err);
  }
}

async function handleLoadSession() {
  const sessionId = String(elements.loadSessionId.value || "").trim();
  if (!sessionId) {
    logInfo("log.load_session_id_required");
    return;
  }
  try {
    const detail = await getSessionDetail(sessionId);
    const sessionLocale = detail.output_language || getCurrentLocale();
    if (sessionLocale !== getCurrentLocale()) {
      await setLocale(sessionLocale);
      setStore({ locale: getCurrentLocale() });
      applyLocalePresentation();
      fillLanguageOptions();
      renderIntervalUnitOptions();
    }

    elements.title.value = detail.title || "";
    elements.worldPreset.value = detail.world_preset || "";
    elements.postDelay.value = String(detail.post_gen_delay_sec || 5);

    const timelineConfig = {
      initialTimeISO: detail.timeline_start_iso || new Date().toISOString(),
      stepValue: detail.timeline_step_value || 1,
      stepUnit: detail.timeline_step_unit || "month",
    };
    setStore({
      session: {
        session_id: detail.session_id,
        active_branch_id: detail.active_branch_id,
        running: detail.running,
      },
      branches: [],
      activeBranchId: detail.active_branch_id || null,
      runnerState: detail.running ? "running" : "paused",
      timelineByBranch: {},
      timelineConfig,
      provider: buildCurrentProviderState(),
    });

    applyTimelineConfigToInputs(timelineConfig);
    elements.tickLabel.value = detail.tick_label || formatIntervalLabel(timelineConfig.stepValue, timelineConfig.stepUnit);
    elements.loadSessionId.value = detail.session_id;
    saveLastSessionId(detail.session_id);

    closeWebSocket();
    setSessionId(detail.session_id);
    syncRunnerState(detail.running ? "running" : "paused");
    syncConnectionState("disconnected");
    renderBranchTabs();
    setControlsEnabled(true);

    await hydrateProviderForSession(detail.session_id);
    await loadBranches();
    await loadTimeline();
    await handleRefreshSessionHistory();
    connectSessionSocket(detail.session_id);
    logInfo("log.session_loaded", { session: detail.session_id });
  } catch (err) {
    logError("error.load_session_failed", err);
  }
}

async function handleLoadRuntimeSettings() {
  try {
    const response = await getRuntimeSettings();
    applyRuntimeSettingsSnapshot(response.settings || {});
    logInfo("log.runtime_settings_loaded");
  } catch (err) {
    logError("error.runtime_settings_load_failed", err);
  }
}

async function handleApplyRuntimeSettings() {
  try {
    const updates = collectRuntimeSettingsUpdates();
    const response = await patchRuntimeSettings({ updates });
    applyRuntimeSettingsSnapshot(response.settings || {});
    logInfo("log.runtime_settings_applied");
  } catch (err) {
    logError("error.runtime_settings_apply_failed", err);
  }
}

async function hydrateVersionLabelSilently() {
  try {
    const response = await getRuntimeSettings();
    applyRuntimeSettingsSnapshot(response.settings || {});
  } catch (_) {
    renderAppVersion(DEFAULT_APP_VERSION);
  }
}

async function handleCreateSession() {
  try {
    const providerState = buildCurrentProviderState();
    const timelineConfig = buildTimelineConfigFromInputs();
    const payload = {
      title: elements.title.value || null,
      world_preset: elements.worldPreset.value,
      tick_label: elements.tickLabel.value || null,
      post_gen_delay_sec: elements.postDelay.value ? Number(elements.postDelay.value) : null,
      output_language: getCurrentLocale(),
      timeline_start_iso: timelineConfig.initialTimeISO,
      timeline_step_value: timelineConfig.stepValue,
      timeline_step_unit: timelineConfig.stepUnit,
    };
    const result = await createSession(payload);

    closeWebSocket();

    setStore({
      session: result,
      branches: [{ id: result.active_branch_id, name: "main" }],
      activeBranchId: result.active_branch_id,
      runnerState: "idle",
      timelineByBranch: {},
      timelineConfig: {
        initialTimeISO: result.timeline_start_iso || timelineConfig.initialTimeISO,
        stepValue: result.timeline_step_value || timelineConfig.stepValue,
        stepUnit: result.timeline_step_unit || timelineConfig.stepUnit,
      },
      provider: providerState,
    });

    applyTimelineConfigToInputs(store.timelineConfig);
    elements.loadSessionId.value = result.session_id;
    saveLastSessionId(result.session_id);

    setSessionId(result.session_id);
    syncRunnerState("idle");
    syncConnectionState("disconnected");
    renderModelOptions(providerState.models || []);
    if (providerState.model) {
      elements.modelSelect.value = providerState.model;
    }
    renderBranchTabs();
    setControlsEnabled(true);
    logInfo("log.session_created");

    await tryRebindProviderToSession(result.session_id);
    await loadBranches();
    await loadTimeline();
    await handleRefreshSessionHistory();
    connectSessionSocket(result.session_id);
  } catch (err) {
    logError("error.create_failed", err);
  }
}

function handleProviderChange() {
  const provider = elements.providerSelect.value;
  applyProviderDefaults(provider);
  elements.apiKey.value = "";
  loadLocalApiKeyForProvider(provider);
  setStore({
    provider: {
      name: provider,
      baseUrl: elements.baseUrl.value || "",
      model: null,
      models: [],
    },
  });
  renderModelOptions([]);
  setControlsEnabled(Boolean(store.session));
  logInfo("log.provider_switched", { provider });
}

async function handleLoadModels() {
  if (!store.session) return;
  try {
    const provider = elements.providerSelect.value;
    const apiKey = getEffectiveApiKey(provider) || null;
    const previousModel = store.provider.model;
    const payload = {
      provider,
      api_key: apiKey,
      base_url: elements.baseUrl.value || null,
      model_name: null,
    };
    await setProvider(store.session.session_id, payload);
    const response = await getModels(store.session.session_id, payload.provider);
    const models = response.models || [];
    const retainedModel = previousModel && models.includes(previousModel) ? previousModel : null;
    setStore({
      provider: {
        name: payload.provider,
        baseUrl: payload.base_url || "",
        model: retainedModel,
        models,
      },
    });
    renderModelOptions(models);
    if (retainedModel) {
      elements.modelSelect.value = retainedModel;
    }
    persistApiKeyIfNeeded(provider, apiKey || "");
    logInfo("log.models_loaded");
    setControlsEnabled(true);
  } catch (err) {
    logError("error.load_models_failed", err);
  }
}

async function handleModelChange() {
  if (!store.session) return;
  const modelName = elements.modelSelect.value;
  if (!modelName) return;
  try {
    await selectModel(store.session.session_id, { model_name: modelName });
    setStore({
      provider: {
        ...store.provider,
        model: modelName,
      },
    });
    logInfo("log.model_selected", { model: modelName });
    setControlsEnabled(true);
  } catch (err) {
    logError("error.select_model_failed", err);
  }
}

async function handleStart() {
  if (!store.session) return;
  setRunnerControlHighlight(elements.startBtn);
  try {
    const state = await startSession(store.session.session_id);
    syncRunnerState(state.running ? "running" : "idle");
    logInfo("log.runner_started");
  } catch (err) {
    logError("error.start_failed", err);
  }
}

async function handlePause() {
  if (!store.session) return;
  setRunnerControlHighlight(elements.pauseBtn);
  try {
    const state = await pauseSession(store.session.session_id);
    syncRunnerState(state.running ? "running" : "paused");
    logInfo("log.runner_paused");
  } catch (err) {
    logError("error.pause_failed", err);
  }
}

async function handleResume() {
  if (!store.session) return;
  setRunnerControlHighlight(elements.resumeBtn);
  try {
    const state = await resumeSession(store.session.session_id);
    syncRunnerState(state.running ? "running" : "idle");
    logInfo("log.runner_resumed");
  } catch (err) {
    logError("error.resume_failed", err);
  }
}

async function handleForkBranch() {
  if (!store.session || !store.activeBranchId) return;
  try {
    const response = await forkBranch(store.session.session_id, {
      source_branch_id: store.activeBranchId,
      from_message_id: null,
    });
    logInfo("log.forked_branch", { branch: response.branch.name });
    await loadBranches();
  } catch (err) {
    logError("error.fork_failed", err);
  }
}

async function handleSwitchBranch(branchId) {
  if (!store.session) return;
  if (branchId === store.activeBranchId) return;
  try {
    const response = await switchBranch(store.session.session_id, { branch_id: branchId });
    setBranches(store.branches, response.active_branch_id);
    renderBranchTabs();
    setControlsEnabled(Boolean(store.session));
    await loadTimeline();
    logInfo("log.switched_branch", { branch: response.active_branch_id });
  } catch (err) {
    logError("error.switch_failed", err);
  }
}

async function handleDeleteLast() {
  if (!store.session || !store.activeBranchId) return;
  if (store.runnerState === "running") {
    logInfo("log.delete_running_warning");
  }
  try {
    await deleteLastMessage(store.session.session_id, store.activeBranchId);
    logInfo("log.deleted_latest");
    await loadTimeline();
  } catch (err) {
    logError("error.delete_failed", err);
  }
}

async function handleSendIntervention() {
  if (!store.session || !store.activeBranchId) return;
  const content = elements.interventionInput.value.trim();
  if (!content) {
    logInfo("log.intervention_empty");
    return;
  }
  try {
    await submitIntervention(store.session.session_id, {
      branch_id: store.activeBranchId,
      content,
    });
    elements.interventionInput.value = "";
    logInfo("log.intervention_queued");
  } catch (err) {
    logError("error.intervention_failed", err);
  }
}

async function handleEditTimelineMessage(message, payload) {
  if (!store.session || !message?.id) return;
  const requestPayload = {
    ...(payload || {}),
    branch_id: message.branch_id || store.activeBranchId,
  };
  try {
    const response = await patchMessage(
      store.session.session_id,
      message.id,
      requestPayload
    );
    const updated = response?.message;
    if (!updated) {
      await loadTimeline();
      return;
    }
    replaceMessage(updated.branch_id, updated);
    if (updated.branch_id === store.activeBranchId) {
      const activeTimeline = store.timelineByBranch[updated.branch_id] || [];
      renderTimeline(activeTimeline, store.timelineConfig);
    }
    logInfo("log.message_updated", { seq: updated.seq });
  } catch (err) {
    logError("error.message_update_failed", err);
  }
}

function handleWsEvent(event) {
  if (event.event === "session_state") {
    syncRunnerState(event.running ? "running" : "paused");
    return;
  }

  if (event.event === "message_created") {
    appendMessage(event.branch_id, event.message);
    if (event.branch_id === store.activeBranchId) {
      const activeTimeline = store.timelineByBranch[event.branch_id] || [];
      appendTimelineMessage(event.message, store.timelineConfig, activeTimeline);
    }
    return;
  }

  if (event.event === "branch_switched") {
    setBranches(store.branches, event.active_branch_id);
    renderBranchTabs();
    setControlsEnabled(Boolean(store.session));
    loadTimeline();
    logInfo("log.switched_branch_server", { branch: event.active_branch_id });
    return;
  }

  if (event.event === "models_loaded") {
    if (event.provider !== elements.providerSelect.value) {
      return;
    }
    const models = event.models || [];
    const retainedModel =
      store.provider.model && models.includes(store.provider.model)
        ? store.provider.model
        : null;
    setStore({
      provider: {
        ...store.provider,
        name: event.provider,
        model: retainedModel,
        models,
      },
    });
    renderModelOptions(models);
    if (retainedModel) {
      elements.modelSelect.value = retainedModel;
    }
    logInfo("log.models_loaded_ws");
    setControlsEnabled(Boolean(store.session));
    return;
  }

  if (event.event === "error") {
    logInfo("error.runner_error", { error: event.message || "unknown" });
    return;
  }

  if (event.event === "message_updated") {
    const updated = event.message;
    if (!updated?.id || !event.branch_id) return;
    replaceMessage(event.branch_id, updated);
    if (event.branch_id === store.activeBranchId) {
      const activeTimeline = store.timelineByBranch[event.branch_id] || [];
      renderTimeline(activeTimeline, store.timelineConfig);
    }
  }
}

async function handleLanguageChange() {
  const nextLocale = elements.languageSelect.value;
  await setLocale(nextLocale);
  setStore({ locale: getCurrentLocale() });
  applyLocalePresentation();
  renderIntervalUnitOptions();
  syncTickLabel();
  setSessionId(store.session?.session_id || null);
  syncRunnerState(store.runnerState);
  syncConnectionState(store.connectionState);
  applyProviderDefaults(elements.providerSelect.value, false);
  renderModelOptions(store.provider.models || []);
  if (store.provider.model) {
    elements.modelSelect.value = store.provider.model;
  }
  renderBranchTabs();
  const activeTimeline = store.timelineByBranch[store.activeBranchId] || [];
  renderTimeline(activeTimeline, store.timelineConfig);
  if (Object.keys(runtimeSettingsSnapshot).length > 0) {
    renderRuntimeSettingsForm(runtimeSettingsSnapshot);
  }
  handleRefreshSessionHistory().catch(() => {});
  if (store.session?.session_id) {
    try {
      await updateSettings(store.session.session_id, {
        output_language: getCurrentLocale(),
        timeline_start_iso: store.timelineConfig?.initialTimeISO || null,
        timeline_step_value: store.timelineConfig?.stepValue || 1,
        timeline_step_unit: store.timelineConfig?.stepUnit || "month",
      });
      logInfo("log.language_synced", { language: getCurrentLocale() });
    } catch (err) {
      logError("log.language_sync_failed", err);
    }
  }
}

function handleRememberApiKeyToggle() {
  const provider = elements.providerSelect.value;
  const enabled = elements.rememberApiKey.checked;
  setRememberApiKey(enabled);
  if (enabled) {
    persistApiKeyIfNeeded(provider, elements.apiKey.value || "");
    loadLocalApiKeyForProvider(provider, true);
    return;
  }
  clearProviderApiKey(provider);
  logInfo("log.local_key_cleared", { provider });
}

async function handleTimelineConfigChange() {
  syncTickLabel();
  const config = buildTimelineConfigFromInputs();
  setStore({ timelineConfig: config });
  const activeTimeline = store.timelineByBranch[store.activeBranchId] || [];
  renderTimeline(activeTimeline, store.timelineConfig);
  if (!store.session?.session_id) return;
  try {
    await updateSettings(store.session.session_id, {
      timeline_start_iso: config.initialTimeISO,
      timeline_step_value: config.stepValue,
      timeline_step_unit: config.stepUnit,
      tick_label: elements.tickLabel.value,
    });
  } catch (_) {
    // Keep UI responsive even if backend sync fails.
  }
}

async function handleOpenSettingsTab() {
  setSettingsPageOpen(true);
  if (Object.keys(runtimeSettingsSnapshot).length > 0) {
    return;
  }
  await handleLoadRuntimeSettings();
}

function handleCloseSettingsTab() {
  setSettingsPageOpen(false);
}

elements.createBtn.addEventListener("click", handleCreateSession);
elements.loadSessionBtn.addEventListener("click", handleLoadSession);
elements.refreshSessionHistoryBtn.addEventListener("click", handleRefreshSessionHistory);
elements.openSettingsTabBtn.addEventListener("click", () => {
  handleOpenSettingsTab().catch((err) => logError("error.runtime_settings_load_failed", err));
});
elements.closeSettingsTabBtn.addEventListener("click", handleCloseSettingsTab);
elements.languageSelect.addEventListener("change", () => {
  handleLanguageChange().catch((err) => logError("log.language_sync_failed", err));
});
elements.initialTime.addEventListener("change", () => {
  handleTimelineConfigChange().catch(() => {});
});
elements.timeStepValue.addEventListener("change", () => {
  handleTimelineConfigChange().catch(() => {});
});
elements.timeStepUnit.addEventListener("change", () => {
  handleTimelineConfigChange().catch(() => {});
});
elements.providerSelect.addEventListener("change", handleProviderChange);
elements.rememberApiKey.addEventListener("change", handleRememberApiKeyToggle);
elements.loadModelsBtn.addEventListener("click", handleLoadModels);
elements.modelSelect.addEventListener("change", handleModelChange);
elements.startBtn.addEventListener("click", handleStart);
elements.pauseBtn.addEventListener("click", handlePause);
elements.resumeBtn.addEventListener("click", handleResume);
elements.refreshBtn.addEventListener("click", loadTimeline);
elements.forkBtn.addEventListener("click", handleForkBranch);
elements.deleteLastBtn.addEventListener("click", handleDeleteLast);
elements.sendInterventionBtn.addEventListener("click", handleSendIntervention);
elements.loadRuntimeSettingsBtn.addEventListener("click", handleLoadRuntimeSettings);
elements.applyRuntimeSettingsBtn.addEventListener("click", handleApplyRuntimeSettings);
setTimelineEditHandler((message, payload) => handleEditTimelineMessage(message, payload));

async function bootstrap() {
  await initI18n();
  applyTranslations();
  fillLanguageOptions();
  applyLocalePresentation();
  renderIntervalUnitOptions();
  setStore({ locale: getCurrentLocale() });

  elements.rememberApiKey.checked = getRememberApiKey();
  elements.initialTime.value = nowLocalDateTimeInputValue();
  elements.timeStepValue.value = "1";
  elements.timeStepUnit.value = "month";
  syncTickLabel();
  setRunnerControlHighlight(elements.startBtn);
  setStore({
    timelineConfig: buildTimelineConfigFromInputs(),
  });

  elements.loadSessionId.value = loadLastSessionId();
  runtimeSettingsSnapshot = {};
  renderRuntimeSettingsForm({});
  renderAppVersion(DEFAULT_APP_VERSION);
  await hydrateVersionLabelSilently();
  setSettingsPageOpen(false);
  setControlsEnabled(false);
  setSessionId(null);
  syncConnectionState("disconnected");
  syncRunnerState("idle");
  renderModelOptions([]);
  renderBranchTabs();
  applyProviderDefaults(elements.providerSelect.value);
  loadLocalApiKeyForProvider(elements.providerSelect.value, true);
  await handleRefreshSessionHistory();
}

bootstrap().catch((err) => {
  addLog(`bootstrap failed: ${normalizeError(err)}`);
});

window.addEventListener("beforeunload", () => {
  closeWebSocket();
});
