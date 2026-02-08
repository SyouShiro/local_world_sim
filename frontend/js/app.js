import {
  createSession,
  getTimeline,
  getModels,
  pauseSession,
  resumeSession,
  selectModel,
  setProvider,
  startSession,
} from "./api.js";
import { connectWebSocket, closeWebSocket } from "./ws.js";
import { appendMessage, setStore, setTimeline, store } from "./store.js";
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
  createBtn: document.getElementById("createSession"),
  providerSelect: document.getElementById("providerSelect"),
  apiKey: document.getElementById("apiKey"),
  baseUrl: document.getElementById("baseUrl"),
  loadModelsBtn: document.getElementById("loadModels"),
  modelSelect: document.getElementById("modelSelect"),
  startBtn: document.getElementById("startSession"),
  pauseBtn: document.getElementById("pauseSession"),
  resumeBtn: document.getElementById("resumeSession"),
  refreshBtn: document.getElementById("refreshTimeline"),
};

const providerDefaults = {
  openai: "https://api.openai.com",
  ollama: "http://localhost:11434",
  deepseek: "https://api.deepseek.com",
  gemini: "https://generativelanguage.googleapis.com",
};

function setControlsEnabled(enabled) {
  const hasModel = Boolean(store.provider && store.provider.model);
  elements.startBtn.disabled = !enabled || !hasModel;
  elements.pauseBtn.disabled = !enabled;
  elements.resumeBtn.disabled = !enabled || !hasModel;
  elements.refreshBtn.disabled = !enabled;
  elements.loadModelsBtn.disabled = !enabled;
  elements.modelSelect.disabled = !enabled;
}

function renderModelOptions(models) {
  elements.modelSelect.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "Select model...";
  elements.modelSelect.appendChild(placeholder);
  models.forEach((model) => {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    elements.modelSelect.appendChild(option);
  });
}

function applyProviderDefaults(provider) {
  const defaultUrl = providerDefaults[provider] || "";
  elements.baseUrl.placeholder = defaultUrl || "Base URL";
  elements.baseUrl.value = defaultUrl;
}

async function handleCreateSession() {
  try {
    const payload = {
      title: elements.title.value || null,
      world_preset: elements.worldPreset.value,
      tick_label: elements.tickLabel.value || null,
      post_gen_delay_sec: elements.postDelay.value
        ? Number(elements.postDelay.value)
        : null,
    };
    const result = await createSession(payload);
    setStore({
      session: result,
      branches: [{ id: result.active_branch_id, name: "main" }],
      activeBranchId: result.active_branch_id,
      runnerState: "idle",
      provider: {
        name: elements.providerSelect.value,
        baseUrl: elements.baseUrl.value || "",
        model: null,
        models: [],
      },
    });
    setSessionId(result.session_id);
    setRunnerState("idle");
    addLog("Session created.");
    renderModelOptions([]);
    setControlsEnabled(true);
    await loadTimeline();
    connectWebSocket(result.session_id, {
      onOpen: () => {
        setConnectionState("connected");
        addLog("WebSocket connected.");
      },
      onClose: () => {
        setConnectionState("disconnected");
        addLog("WebSocket disconnected. Reconnecting...");
      },
      onEvent: handleWsEvent,
      onError: (err) => addLog(`WebSocket error: ${err.message || err}`),
    });
  } catch (err) {
    addLog(`Create failed: ${err.message || err}`);
  }
}

function handleProviderChange() {
  const provider = elements.providerSelect.value;
  applyProviderDefaults(provider);
  elements.apiKey.value = "";
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
  addLog(`Provider switched to ${provider}. Load models again.`);
}

async function handleLoadModels() {
  if (!store.session) return;
  try {
    const payload = {
      provider: elements.providerSelect.value,
      api_key: elements.apiKey.value || null,
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
    addLog("Models loaded.");
    setControlsEnabled(true);
  } catch (err) {
    addLog(`Load models failed: ${err.message || err}`);
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
    addLog(`Model selected: ${modelName}`);
    setControlsEnabled(true);
  } catch (err) {
    addLog(`Select model failed: ${err.message || err}`);
  }
}

async function loadTimeline() {
  if (!store.session) return;
  try {
    const data = await getTimeline(store.session.session_id, store.activeBranchId);
    setTimeline(store.activeBranchId, data.messages);
    renderTimeline(data.messages);
  } catch (err) {
    addLog(`Timeline load failed: ${err.message || err}`);
  }
}

async function handleStart() {
  if (!store.session) return;
  try {
    const state = await startSession(store.session.session_id);
    setRunnerState(state.running ? "running" : "idle");
    addLog("Runner started.");
  } catch (err) {
    addLog(`Start failed: ${err.message || err}`);
  }
}

async function handlePause() {
  if (!store.session) return;
  try {
    const state = await pauseSession(store.session.session_id);
    setRunnerState(state.running ? "running" : "paused");
    addLog("Runner paused.");
  } catch (err) {
    addLog(`Pause failed: ${err.message || err}`);
  }
}

async function handleResume() {
  if (!store.session) return;
  try {
    const state = await resumeSession(store.session.session_id);
    setRunnerState(state.running ? "running" : "idle");
    addLog("Runner resumed.");
  } catch (err) {
    addLog(`Resume failed: ${err.message || err}`);
  }
}

function handleWsEvent(event) {
  if (event.event === "session_state") {
    setRunnerState(event.running ? "running" : "paused");
    return;
  }
  if (event.event === "message_created") {
    appendMessage(event.branch_id, event.message);
    if (event.branch_id === store.activeBranchId) {
      appendTimelineMessage(event.message);
    }
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
        models: event.models,
      },
    });
    renderModelOptions(event.models || []);
    addLog("Models loaded via WebSocket.");
    return;
  }
  if (event.event === "error") {
    addLog(`Runner error: ${event.message}`);
  }
}

elements.createBtn.addEventListener("click", handleCreateSession);
elements.providerSelect.addEventListener("change", handleProviderChange);
elements.loadModelsBtn.addEventListener("click", handleLoadModels);
elements.modelSelect.addEventListener("change", handleModelChange);
elements.startBtn.addEventListener("click", handleStart);
elements.pauseBtn.addEventListener("click", handlePause);
elements.resumeBtn.addEventListener("click", handleResume);
elements.refreshBtn.addEventListener("click", loadTimeline);

setControlsEnabled(false);
setConnectionState("disconnected");
setRunnerState("idle");
renderModelOptions([]);
applyProviderDefaults(elements.providerSelect.value);

window.addEventListener("beforeunload", () => {
  closeWebSocket();
});
