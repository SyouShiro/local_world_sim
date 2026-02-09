import {
  createSession,
  deleteLastMessage,
  forkBranch,
  getCurrentProvider,
  getModels,
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
import { appendMessage, setBranches, setStore, setTimeline, store } from "./store.js";
import {
  addLog,
  appendTimelineMessage,
  renderTimeline,
  setConnectionState,
  setRunnerState,
  setSessionId,
} from "./ui.js";

const elements = {
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
  runtimeSettingsEditor: document.getElementById("runtimeSettingsEditor"),
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
};

const LAST_SESSION_ID_KEY = "worldline.lastSessionId.v1";

const providerDefaults = {
  openai: "https://api.openai.com",
  ollama: "http://localhost:11434",
  deepseek: "https://api.deepseek.com",
  gemini: "https://generativelanguage.googleapis.com",
};

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
  const offsetMs = now.getTimezoneOffset() * 60000;
  const local = new Date(now.getTime() - offsetMs);
  return local.toISOString().slice(0, 16);
}

function toIsoFromLocalInput(localInput) {
  const value = String(localInput || "").trim();
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

function fromIsoToLocalInput(iso) {
  const value = String(iso || "").trim();
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  const offsetMs = parsed.getTimezoneOffset() * 60000;
  const local = new Date(parsed.getTime() - offsetMs);
  return local.toISOString().slice(0, 16);
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

function parseRuntimeSettingsEditor() {
  const raw = String(elements.runtimeSettingsEditor.value || "").trim();
  if (!raw) return {};
  const parsed = JSON.parse(raw);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("invalid settings payload");
  }
  if (parsed.updates && typeof parsed.updates === "object" && !Array.isArray(parsed.updates)) {
    return parsed.updates;
  }
  if (parsed.settings && typeof parsed.settings === "object" && !Array.isArray(parsed.settings)) {
    return parsed.settings;
  }
  return parsed;
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
    elements.runtimeSettingsEditor.value = JSON.stringify(response.settings || {}, null, 2);
    logInfo("log.runtime_settings_loaded");
  } catch (err) {
    logError("error.runtime_settings_load_failed", err);
  }
}

async function handleApplyRuntimeSettings() {
  try {
    const updates = parseRuntimeSettingsEditor();
    const response = await patchRuntimeSettings({ updates });
    elements.runtimeSettingsEditor.value = JSON.stringify(response.settings || {}, null, 2);
    logInfo("log.runtime_settings_applied");
  } catch (err) {
    logError("error.runtime_settings_apply_failed", err);
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

function handleWsEvent(event) {
  if (event.event === "session_state") {
    syncRunnerState(event.running ? "running" : "paused");
    return;
  }

  if (event.event === "message_created") {
    appendMessage(event.branch_id, event.message);
    if (event.branch_id === store.activeBranchId) {
      appendTimelineMessage(event.message, store.timelineConfig);
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

elements.createBtn.addEventListener("click", handleCreateSession);
elements.loadSessionBtn.addEventListener("click", handleLoadSession);
elements.refreshSessionHistoryBtn.addEventListener("click", handleRefreshSessionHistory);
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
  setStore({
    timelineConfig: buildTimelineConfigFromInputs(),
  });

  elements.loadSessionId.value = loadLastSessionId();
  elements.runtimeSettingsEditor.value = "{}";
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
