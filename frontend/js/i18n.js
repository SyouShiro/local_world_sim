const LOCALE_STORAGE_KEY = "worldline.locale.v1";
const FALLBACK_LOCALE = "zh-CN";

let currentLocale = FALLBACK_LOCALE;
let fallbackMessages = {};
let activeMessages = {};
let localeRegistry = [
  { code: "en", label: "English" },
  { code: "zh-CN", label: "中文（简体）" },
];

function normalizeLocale(code) {
  const value = String(code || "").trim();
  if (!value) return "";
  if (value.toLowerCase().startsWith("zh")) return "zh-CN";
  if (value.toLowerCase().startsWith("en")) return "en";
  return value;
}

function localeAssetUrl(fileName) {
  return new URL(`../locales/${fileName}`, import.meta.url).href;
}

async function loadRegistry() {
  try {
    const response = await fetch(localeAssetUrl("registry.json"));
    if (!response.ok) return;
    const rows = await response.json();
    if (!Array.isArray(rows)) return;
    const parsed = rows
      .map((row) => ({
        code: String(row?.code || "").trim(),
        label: String(row?.label || "").trim(),
      }))
      .filter((row) => row.code && row.label);
    if (parsed.length > 0) {
      localeRegistry = parsed;
    }
  } catch (_) {
    // Keep built-in locale registry when registry file is missing.
  }
}

async function loadMessages(localeCode) {
  const response = await fetch(localeAssetUrl(`${localeCode}.json`));
  if (!response.ok) {
    throw new Error(`locale file not found: ${localeCode}`);
  }
  const payload = await response.json();
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`invalid locale payload: ${localeCode}`);
  }
  return payload;
}

function resolveSupportedLocale(code) {
  const normalized = normalizeLocale(code);
  const supported = localeRegistry.find(
    (item) => item.code.toLowerCase() === normalized.toLowerCase()
  );
  if (supported) return supported.code;
  return FALLBACK_LOCALE;
}

function interpolate(template, vars = {}) {
  return template.replace(/\{(\w+)\}/g, (_, key) =>
    vars[key] === undefined || vars[key] === null ? "" : String(vars[key])
  );
}

export async function initI18n() {
  await loadRegistry();
  fallbackMessages = await loadMessages(FALLBACK_LOCALE);

  const preferred = localStorage.getItem(LOCALE_STORAGE_KEY) || FALLBACK_LOCALE;
  await setLocale(preferred, { save: false });
}

export async function setLocale(localeCode, options = { save: true }) {
  const targetLocale = resolveSupportedLocale(localeCode);
  const loadedMessages = await loadMessages(targetLocale);
  activeMessages = loadedMessages;
  currentLocale = targetLocale;
  if (options.save !== false) {
    localStorage.setItem(LOCALE_STORAGE_KEY, targetLocale);
  }
  applyTranslations();
}

export function getCurrentLocale() {
  return currentLocale;
}

export function getSupportedLocales() {
  return [...localeRegistry];
}

export function t(key, vars = {}) {
  const value =
    activeMessages[key] ||
    fallbackMessages[key] ||
    key;
  if (typeof value !== "string") {
    return key;
  }
  return interpolate(value, vars);
}

export function applyTranslations(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.getAttribute("data-i18n");
    if (!key) return;
    node.textContent = t(key);
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
    const key = node.getAttribute("data-i18n-placeholder");
    if (!key) return;
    node.setAttribute("placeholder", t(key));
  });
}
