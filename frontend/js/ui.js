import { getCurrentLocale, t } from "./i18n.js";

const sessionIdEl = document.getElementById("sessionId");
const runnerStateEl = document.getElementById("runnerState");
const connectionStateEl = document.getElementById("connectionState");
const timelineListEl = document.getElementById("timelineList");
const logListEl = document.getElementById("logList");
const MAX_LOG_ENTRIES = 10;

export function setSessionId(sessionId) {
  sessionIdEl.textContent = sessionId || t("status.not_created");
}

export function setRunnerState(state) {
  runnerStateEl.textContent = t(`state.runner.${state}`);
}

export function setConnectionState(state) {
  connectionStateEl.textContent = t(`state.connection.${state}`);
}

export function renderTimeline(messages, timelineConfig = null) {
  timelineListEl.innerHTML = "";
  [...messages].reverse().forEach((message) => {
    timelineListEl.appendChild(buildTimelineCard(message, timelineConfig));
  });
}

export function appendTimelineMessage(message, timelineConfig = null) {
  timelineListEl.prepend(buildTimelineCard(message, timelineConfig));
}

export function addLog(message) {
  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.textContent = message;
  logListEl.prepend(entry);
  while (logListEl.children.length > MAX_LOG_ENTRIES) {
    logListEl.removeChild(logListEl.lastElementChild);
  }
}

function buildTimelineCard(message, timelineConfig = null) {
  const roleLabel = t(`timeline.card.role.${message.role}`) || message.role;
  const parsed = message.role === "system_report" ? parseReport(message.content) : null;
  const reportTitle = parsed?.title || t("timeline.card.system_report_default_title");
  const simulatedTime = computeSimulatedTimeLabel(message.seq, timelineConfig);
  const timeAdvance = parsed?.time_advance || message.time_jump_label || "";

  const item = document.createElement("div");
  item.className = "timeline-card";

  const head = document.createElement("div");
  head.className = "timeline-card-head";

  const title = document.createElement("h3");
  title.className = "timeline-card-title";
  title.textContent = simulatedTime
    ? `#${message.seq} · ${simulatedTime} · ${reportTitle}`
    : `#${message.seq} · ${reportTitle}`;
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
    item.appendChild(createEventSection(t("timeline.card.events"), parsed.events, timelineConfig));
  }
  if (parsed.risks.length > 0) {
    item.appendChild(
      createListSection(
        t("timeline.card.risks"),
        parsed.risks.map((row) => row.description || row.label)
      )
    );
  }

  if (!parsed.summary && parsed.events.length === 0 && parsed.risks.length === 0) {
    item.appendChild(createCodeSection(t("timeline.card.raw"), message.content));
  }

  return item;
}

function parseReport(content) {
  const normalized = sanitizeReportText(content);
  const candidates = [normalized];
  const extracted = extractJsonObject(normalized);
  if (extracted && extracted !== normalized) {
    candidates.push(extracted);
  }

  for (const candidate of candidates) {
    const parsed = parseCandidate(candidate);
    if (parsed) return parsed;
  }
  return null;
}

function parseCandidate(content) {
  try {
    const payload = JSON.parse(content);
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return null;
    }
    return {
      title: toSafeText(payload.title),
      time_advance: toSafeText(payload.time_advance),
      summary: toSafeText(payload.summary),
      events: normalizeEventList(payload.events),
      risks: normalizeEventList(payload.risks),
    };
  } catch (_) {
    return null;
  }
}

function toSafeText(value) {
  if (typeof value !== "string") return "";
  return value.trim();
}

function normalizeEventList(value) {
  if (!Array.isArray(value)) return [];
  const rows = [];
  value.forEach((item, index) => {
    if (typeof item === "string") {
      const description = item.trim();
      if (!description) return;
      rows.push({
        category: "neutral",
        label: eventCategoryLabel("neutral"),
        severity: "medium",
        description,
      });
      return;
    }
    if (item && typeof item === "object") {
      const category = normalizeEventCategory(item.category);
      const severity = normalizeEventSeverity(item.severity);
      const label = toSafeText(item.title || item.label || "");
      const description = toSafeText(item.description || item.detail || item.content || "");
      if (!label && !description) return;
      rows.push({
        category,
        label: label || eventCategoryLabel(category),
        severity,
        description: description || label,
      });
    }
  });
  return rows;
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

function createEventSection(title, rows, timelineConfig) {
  const section = createSectionShell(title);
  const wrap = document.createElement("div");
  wrap.className = "timeline-events";
  rows.forEach((row) => {
    const severity = inferEventSeverity(row, timelineConfig);
    const categoryClass = `category-${normalizeEventCategory(row.category)}`;
    const severityClass = `severity-${severity.level}`;
    const details = document.createElement("details");
    details.className = `timeline-event ${categoryClass} ${severityClass}`;
    details.open = true;

    const bar = document.createElement("span");
    bar.className = `timeline-event-bar ${categoryClass} ${severityClass}`;
    details.appendChild(bar);

    const summary = document.createElement("summary");
    const summaryWrap = document.createElement("div");
    summaryWrap.className = "timeline-event-summary";
    const summaryTitle = document.createElement("span");
    summaryTitle.className = "timeline-event-title";
    summaryTitle.textContent = eventCategoryLabel(row.category);
    const summarySeverity = document.createElement("span");
    summarySeverity.className = "timeline-event-severity";
    summarySeverity.textContent = `${t("timeline.card.severity")}: ${severity.label}`;
    summaryWrap.appendChild(summaryTitle);
    summaryWrap.appendChild(summarySeverity);
    summary.appendChild(summaryWrap);
    details.appendChild(summary);
    const content = document.createElement("p");
    content.textContent = toNewsBrief(row.description);
    details.appendChild(content);
    wrap.appendChild(details);
  });
  section.appendChild(wrap);
  return section;
}

function toNewsBrief(text) {
  const normalized = String(text || "").trim().replace(/\s+/g, " ");
  if (!normalized) return "";
  const sentences = normalized
    .match(/[^。！？!?\.]+[。！？!?\.]?/g)
    ?.map((part) => part.trim())
    .filter(Boolean) || [normalized];
  return sentences.slice(0, 3).join(" ");
}

function createCodeSection(title, rawText) {
  const section = createSectionShell(title);
  const code = document.createElement("pre");
  code.textContent = rawText;
  section.appendChild(code);
  return section;
}

function buildTagLabel(text, index) {
  if (!text) return `${t("timeline.card.event_tag")} ${index}`;
  const first = text.split(/[.。!?！；;]/)[0].trim();
  const compact = first.replace(/\s+/g, " ");
  if (!compact) return `${t("timeline.card.event_tag")} ${index}`;
  return compact.length > 18 ? `${compact.slice(0, 18)}...` : compact;
}

function normalizeEventCategory(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (raw === "positive" || raw === "good") return "positive";
  if (raw === "negative" || raw === "bad") return "negative";
  return "neutral";
}

function normalizeEventSeverity(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (raw === "low" || raw === "minor" || raw === "低") return "low";
  if (raw === "high" || raw === "critical" || raw === "severe" || raw === "高") return "high";
  if (raw === "medium" || raw === "moderate" || raw === "中") return "medium";
  return "";
}

function eventCategoryLabel(category) {
  if (category === "positive") {
    return t("timeline.card.event_positive");
  }
  if (category === "negative") {
    return t("timeline.card.event_negative");
  }
  return t("timeline.card.event_neutral");
}

function inferEventSeverity(row, timelineConfig) {
  const explicit = normalizeEventSeverity(row.severity);
  if (explicit) {
    return {
      level: explicit,
      label: severityLabel(explicit),
    };
  }

  const intervalDays = estimateIntervalDays(timelineConfig);
  let score = 1;
  if (intervalDays >= 30) score += 1;
  if (intervalDays >= 365) score += 1;
  if (row.category === "negative") score += 1;
  if (row.category === "positive" && intervalDays <= 7) score -= 1;
  score = Math.max(1, Math.min(3, score));

  const level = score <= 1 ? "low" : score === 2 ? "medium" : "high";
  return {
    level,
    label: severityLabel(level),
  };
}

function severityLabel(level) {
  if (level === "high") return t("timeline.card.severity_high");
  if (level === "low") return t("timeline.card.severity_low");
  return t("timeline.card.severity_medium");
}

function estimateIntervalDays(timelineConfig) {
  if (!timelineConfig) return 30;
  const stepValue = Math.max(1, Number(timelineConfig.stepValue || 1));
  const unit = String(timelineConfig.stepUnit || "month").toLowerCase();
  if (unit === "day") return stepValue;
  if (unit === "week") return stepValue * 7;
  if (unit === "year") return stepValue * 365;
  return stepValue * 30;
}

function sanitizeReportText(content) {
  const raw = String(content || "").trim();
  if (!raw) return raw;
  if (raw.startsWith("```")) {
    return raw
      .replace(/^```(?:json)?\s*/i, "")
      .replace(/\s*```$/, "")
      .trim();
  }
  return raw;
}

function extractJsonObject(content) {
  const start = content.indexOf("{");
  const end = content.lastIndexOf("}");
  if (start === -1 || end === -1 || end <= start) return "";
  return content.slice(start, end + 1).trim();
}

function computeSimulatedTimeLabel(seq, timelineConfig) {
  if (!timelineConfig || !timelineConfig.initialTimeISO) return "";
  const base = new Date(timelineConfig.initialTimeISO);
  if (Number.isNaN(base.getTime())) return "";

  const stepValue = Math.max(1, Number(timelineConfig.stepValue || 1));
  const offset = Math.max(0, Number(seq || 1) - 1);
  const unit = String(timelineConfig.stepUnit || "month").toLowerCase();

  const value = stepValue * offset;
  const simulated = new Date(base.getTime());
  if (unit === "day") {
    simulated.setDate(simulated.getDate() + value);
  } else if (unit === "week") {
    simulated.setDate(simulated.getDate() + value * 7);
  } else if (unit === "year") {
    simulated.setFullYear(simulated.getFullYear() + value);
  } else {
    simulated.setMonth(simulated.getMonth() + value);
  }

  return new Intl.DateTimeFormat(getCurrentLocale(), {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(simulated);
}
