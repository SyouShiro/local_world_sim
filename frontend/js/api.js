const API_BASE = "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

export async function createSession(payload) {
  return request("/api/session/create", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getSessionDetail(sessionId) {
  return request(`/api/session/${sessionId}`);
}

export async function listSessionHistory(limit = 30) {
  const query = new URLSearchParams({ limit: String(limit) });
  return request(`/api/session/history?${query.toString()}`);
}

export async function startSession(sessionId) {
  return request(`/api/session/${sessionId}/start`, { method: "POST" });
}

export async function pauseSession(sessionId) {
  return request(`/api/session/${sessionId}/pause`, { method: "POST" });
}

export async function resumeSession(sessionId) {
  return request(`/api/session/${sessionId}/resume`, { method: "POST" });
}

export async function updateSettings(sessionId, payload) {
  return request(`/api/session/${sessionId}/settings`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function getTimeline(sessionId, branchId, limit = 200) {
  const query = new URLSearchParams({ branch_id: branchId, limit: String(limit) });
  return request(`/api/timeline/${sessionId}?${query.toString()}`);
}

export async function listBranches(sessionId) {
  return request(`/api/branch/${sessionId}`);
}

export async function forkBranch(sessionId, payload) {
  return request(`/api/branch/${sessionId}/fork`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function switchBranch(sessionId, payload) {
  return request(`/api/branch/${sessionId}/switch`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteLastMessage(sessionId, branchId) {
  const query = new URLSearchParams({ branch_id: branchId });
  return request(`/api/message/${sessionId}/last?${query.toString()}`, {
    method: "DELETE",
  });
}

export async function patchMessage(sessionId, messageId, payload) {
  return request(`/api/message/${sessionId}/${messageId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function submitIntervention(sessionId, payload) {
  return request(`/api/intervention/${sessionId}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function setProvider(sessionId, payload) {
  return request(`/api/provider/${sessionId}/set`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getModels(sessionId, provider) {
  const query = new URLSearchParams({ provider });
  return request(`/api/provider/${sessionId}/models?${query.toString()}`);
}

export async function selectModel(sessionId, payload) {
  return request(`/api/provider/${sessionId}/select-model`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getCurrentProvider(sessionId) {
  return request(`/api/provider/${sessionId}/current`);
}

export async function getRuntimeSettings() {
  return request("/api/debug/settings");
}

export async function patchRuntimeSettings(payload) {
  return request("/api/debug/settings", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
