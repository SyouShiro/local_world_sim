import {
  createSession,
  deleteLastMessage,
  forkBranch,
  getModels,
  getTimeline,
  listBranches,
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
  tickLabel: document.getElementById("tickLabel"),
  postDelay: document.getElementById("postDelay"),
  languageSelect: document.getElementById("languageSelect"),
  createBtn: document.getElementById("createSession"),
  providerSelect: document.getElementById("providerSelect"),
  apiKey: document.getElementById("apiKey"),
  rememberApiKey: document.getElementById("rememberApiKey"),
  baseUrl: document.getElementById("baseUrl"),
  loadModelsBtn: document.getElementById("loadModels"),
  modelSelect: document.getElementById("modelSelect"),
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

function applyProviderDefaults(provider) {
  const defaultUrl = providerDefaults[provider] || "";
  elements.baseUrl.placeholder = defaultUrl || t("provider.base_url_placeholder");
  elements.baseUrl.value = defaultUrl;
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
    renderTimeline(data.messages);
  } catch (err) {
    logError("error.timeline_load_failed", err);
  }
}

async function handleCreateSession() {
  try {
    const payload = {
      title: elements.title.value || null,
      world_preset: elements.worldPreset.value,
      tick_label: elements.tickLabel.value || null,
      post_gen_delay_sec: elements.postDelay.value ? Number(elements.postDelay.value) : null,
      output_language: getCurrentLocale(),
    };
    const result = await createSession(payload);

    closeWebSocket();

    setStore({
      session: result,
      branches: [{ id: result.active_branch_id, name: "main" }],
      activeBranchId: result.active_branch_id,
      runnerState: "idle",
      timelineByBranch: {},
      provider: {
        name: elements.providerSelect.value,
        baseUrl: elements.baseUrl.value || "",
        model: null,
        models: [],
      },
    });

    setSessionId(result.session_id);
    syncRunnerState("idle");
    syncConnectionState("disconnected");
    renderModelOptions([]);
    renderBranchTabs();
    setControlsEnabled(true);
    logInfo("log.session_created");

    await loadBranches();
    await loadTimeline();

    connectWebSocket(result.session_id, {
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
    const apiKey = elements.apiKey.value || null;
    const payload = {
      provider,
      api_key: apiKey,
      base_url: elements.baseUrl.value || null,
      model_name: null,
    };
    await setProvider(store.session.session_id, payload);
    const response = await getModels(store.session.session_id, payload.provider);
    const models = response.models || [];
    setStore({
      provider: {
        name: payload.provider,
        baseUrl: payload.base_url || "",
        model: null,
        models,
      },
    });
    renderModelOptions(models);
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
      appendTimelineMessage(event.message);
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
    setStore({
      provider: {
        ...store.provider,
        name: event.provider,
        model: null,
        models: event.models,
      },
    });
    renderModelOptions(event.models || []);
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
  setSessionId(store.session?.session_id || null);
  syncRunnerState(store.runnerState);
  syncConnectionState(store.connectionState);
  renderModelOptions(store.provider.models || []);
  renderBranchTabs();
  const activeTimeline = store.timelineByBranch[store.activeBranchId] || [];
  renderTimeline(activeTimeline);
  if (store.session?.session_id) {
    try {
      await updateSettings(store.session.session_id, { output_language: getCurrentLocale() });
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

elements.createBtn.addEventListener("click", handleCreateSession);
elements.languageSelect.addEventListener("change", () => {
  handleLanguageChange().catch((err) => logError("log.language_sync_failed", err));
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

async function bootstrap() {
  await initI18n();
  applyTranslations();
  fillLanguageOptions();
  setStore({ locale: getCurrentLocale() });

  elements.rememberApiKey.checked = getRememberApiKey();

  setControlsEnabled(false);
  setSessionId(null);
  syncConnectionState("disconnected");
  syncRunnerState("idle");
  renderModelOptions([]);
  renderBranchTabs();
  applyProviderDefaults(elements.providerSelect.value);
  loadLocalApiKeyForProvider(elements.providerSelect.value, true);
}

bootstrap().catch((err) => {
  addLog(`bootstrap failed: ${normalizeError(err)}`);
});

window.addEventListener("beforeunload", () => {
  closeWebSocket();
});
