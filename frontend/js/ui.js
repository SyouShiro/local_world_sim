import { t } from "./i18n.js";

const sessionIdEl = document.getElementById("sessionId");
const runnerStateEl = document.getElementById("runnerState");
const connectionStateEl = document.getElementById("connectionState");
const timelineListEl = document.getElementById("timelineList");
const logListEl = document.getElementById("logList");

export function setSessionId(sessionId) {
  sessionIdEl.textContent = sessionId || t("status.not_created");
}

export function setRunnerState(state) {
  runnerStateEl.textContent = t(`state.runner.${state}`);
}

export function setConnectionState(state) {
  connectionStateEl.textContent = t(`state.connection.${state}`);
}

export function renderTimeline(messages) {
  timelineListEl.innerHTML = "";
  [...messages].reverse().forEach((message) => {
    timelineListEl.appendChild(buildTimelineCard(message));
  });
}

export function appendTimelineMessage(message) {
  timelineListEl.prepend(buildTimelineCard(message));
}

export function addLog(message) {
  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.textContent = message;
  logListEl.prepend(entry);
}

function buildTimelineCard(message) {
  const roleLabel = t(`timeline.card.role.${message.role}`) || message.role;
  const parsed = message.role === "system_report" ? parseReport(message.content) : null;
  const reportTitle = parsed?.title || t("timeline.card.system_report_default_title");
  const timeAdvance = parsed?.time_advance || message.time_jump_label || "";

  const item = document.createElement("div");
  item.className = "timeline-card";

  const head = document.createElement("div");
  head.className = "timeline-card-head";

  const title = document.createElement("h3");
  title.className = "timeline-card-title";
  title.textContent = `#${message.seq} · ${reportTitle}`;
  head.appendChild(title);

  const badge = document.createElement("span");
  badge.className = "timeline-card-badge";
  badge.textContent = roleLabel;
  head.appendChild(badge);
  item.appendChild(head);

  if (timeAdvance) {
    item.appendChild(
      createTextSection(t("setup.tick_label"), timeAdvance)
    );
  }

  if (message.role === "user_intervention") {
    item.appendChild(createTextSection(t("timeline.card.intervention"), message.content));
    return item;
  }

  if (!parsed) {
    item.appendChild(createCodeSection(t("timeline.card.raw"), message.content));
    return item;
  }

  if (parsed.summary) {
    item.appendChild(createTextSection(t("timeline.card.summary"), parsed.summary));
  }
  if (parsed.events.length > 0) {
    item.appendChild(createListSection(t("timeline.card.events"), parsed.events));
  }
  if (parsed.risks.length > 0) {
    item.appendChild(createListSection(t("timeline.card.risks"), parsed.risks));
  }

  if (!parsed.summary && parsed.events.length === 0 && parsed.risks.length === 0) {
    item.appendChild(createCodeSection(t("timeline.card.raw"), message.content));
  }

  return item;
}

function parseReport(content) {
  try {
    const payload = JSON.parse(content);
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return null;
    }
    return {
      title: toSafeText(payload.title),
      time_advance: toSafeText(payload.time_advance),
      summary: toSafeText(payload.summary),
      events: normalizeList(payload.events),
      risks: normalizeList(payload.risks),
    };
  } catch (_) {
    return null;
  }
}

function toSafeText(value) {
  if (typeof value !== "string") return "";
  return value.trim();
}

function normalizeList(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean);
}

function createSectionShell(titleText) {
  const section = document.createElement("section");
  section.className = "timeline-card-section";
  const heading = document.createElement("h4");
  heading.textContent = titleText;
  section.appendChild(heading);
  return section;
}

function createTextSection(title, body) {
  const section = createSectionShell(title);
  const paragraph = document.createElement("p");
  paragraph.textContent = body;
  section.appendChild(paragraph);
  return section;
}

function createListSection(title, rows) {
  const section = createSectionShell(title);
  const list = document.createElement("ul");
  rows.forEach((row) => {
    const item = document.createElement("li");
    item.textContent = row;
    list.appendChild(item);
  });
  section.appendChild(list);
  return section;
}

function createCodeSection(title, rawText) {
  const section = createSectionShell(title);
  const code = document.createElement("pre");
  code.textContent = rawText;
  section.appendChild(code);
  return section;
}
