const PROVIDER_KEY_STORAGE = "worldline.provider.keys.v1";
const REMEMBER_FLAG_STORAGE = "worldline.provider.keys.remember.v1";

function readAllKeys() {
  const raw = localStorage.getItem(PROVIDER_KEY_STORAGE);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
  } catch (_) {
    return {};
  }
  return {};
}

function writeAllKeys(payload) {
  localStorage.setItem(PROVIDER_KEY_STORAGE, JSON.stringify(payload));
}

export function getRememberApiKey() {
  return localStorage.getItem(REMEMBER_FLAG_STORAGE) === "1";
}

export function setRememberApiKey(enabled) {
  localStorage.setItem(REMEMBER_FLAG_STORAGE, enabled ? "1" : "0");
}

export function loadProviderApiKey(provider) {
  const keyMap = readAllKeys();
  const key = keyMap[provider];
  return typeof key === "string" ? key : "";
}

export function saveProviderApiKey(provider, apiKey) {
  const trimmed = String(apiKey || "").trim();
  const keyMap = readAllKeys();
  if (!trimmed) {
    delete keyMap[provider];
  } else {
    keyMap[provider] = trimmed;
  }
  writeAllKeys(keyMap);
}

export function clearProviderApiKey(provider) {
  saveProviderApiKey(provider, "");
}
