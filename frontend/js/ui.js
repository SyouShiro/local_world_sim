import { getCurrentLocale, t } from "./i18n.js";

const sessionIdEl = document.getElementById("sessionId");
const runnerStateEl = document.getElementById("runnerState");
const connectionStateEl = document.getElementById("connectionState");
const timelineListEl = document.getElementById("timelineList");
const logListEl = document.getElementById("logList");
const keyEventsListEl = document.getElementById("keyEventsList");

const MAX_LOG_ENTRIES = 4;
const MAX_KEY_EVENTS = 10;

let timelineEditHandler = null;

export function setSessionId(sessionId) {
  sessionIdEl.textContent = sessionId || t("status.not_created");
}

export function setRunnerState(state) {
  runnerStateEl.textContent = t(`state.runner.${state}`);
}

export function setConnectionState(state) {
  connectionStateEl.textContent = t(`state.connection.${state}`);
}

export function setTimelineEditHandler(handler) {
  timelineEditHandler = typeof handler === "function" ? handler : null;
}

export function renderTimeline(messages, timelineConfig = null) {
  timelineListEl.innerHTML = "";
  [...messages].reverse().forEach((message) => {
    timelineListEl.appendChild(buildTimelineCard(message, timelineConfig));
  });
  renderKeyEvents(messages);
}

export function appendTimelineMessage(message, timelineConfig = null, messagesForSidebar = null) {
  timelineListEl.prepend(buildTimelineCard(message, timelineConfig));
  if (Array.isArray(messagesForSidebar)) {
    renderKeyEvents(messagesForSidebar);
  }
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
  const parsed = message.role === "system_report" ? resolveReportSnapshot(message) : null;
  const reportTitle = parsed?.title || t("timeline.card.system_report_default_title");
  const messageTime = formatMessageTime(message.created_at);
  const timeAdvance = parsed?.time_advance || message.time_jump_label || "";

  const item = document.createElement("article");
  item.className = "timeline-card";

  const head = document.createElement("div");
  head.className = "timeline-card-head";

  const title = document.createElement("h3");
  title.className = "timeline-card-title";
  title.textContent = messageTime
    ? `#${message.seq} · ${messageTime} · ${reportTitle}`
    : `#${message.seq} · ${reportTitle}`;
  head.appendChild(title);

  const badgeWrap = document.createElement("div");
  badgeWrap.className = "timeline-card-badge-wrap";

  if (message.is_user_edited) {
    const edited = document.createElement("span");
    edited.className = "timeline-card-edited";
    edited.textContent = t("timeline.card.edited");
    badgeWrap.appendChild(edited);
  }

  const badge = document.createElement("span");
  badge.className = "timeline-card-badge";
  badge.textContent = roleLabel;
  badgeWrap.appendChild(badge);

  head.appendChild(badgeWrap);
  item.appendChild(head);

  if (timeAdvance) {
    item.appendChild(createTextSection(t("setup.tick_label"), timeAdvance));
  }

  if (message.role === "user_intervention") {
    item.appendChild(createTextSection(t("timeline.card.intervention"), message.content));
    item.appendChild(createEditSection(message, null));
    return item;
  }

  if (!parsed) {
    const fallbackSummary = toHeadlineSentence(sanitizeReportText(message.content));
    if (fallbackSummary) {
      item.appendChild(createTextSection(t("timeline.card.summary"), fallbackSummary));
    }
    item.appendChild(
      createTextSection(
        t("timeline.card.raw"),
        toNewsBrief(sanitizeReportText(message.content)) || message.content
      )
    );
    item.appendChild(createEditSection(message, null));
    return item;
  }

  const summary = toHeadlineSentence(parsed.summary || parsed.title || "");
  if (summary) {
    item.appendChild(createTextSection(t("timeline.card.summary"), summary));
  }

  const metrics = deriveSituationMetrics(parsed, timelineConfig);
  item.appendChild(createMetricsSection(metrics.tensionPercent, metrics.crisisFocus));

  if (parsed.events.length > 0) {
    item.appendChild(createEventSection(t("timeline.card.events"), parsed.events, timelineConfig));
  }
  if (parsed.risks.length > 0) {
    item.appendChild(
      createListSection(
        t("timeline.card.risks"),
        parsed.risks.map((row) => toHeadlineSentence(row.description)).filter(Boolean)
      )
    );
  }

  if (!summary && parsed.events.length === 0 && parsed.risks.length === 0) {
    item.appendChild(createTextSection(t("timeline.card.raw"), toNewsBrief(message.content)));
  }

  item.appendChild(createEditSection(message, parsed));
  return item;
}

function createEditSection(message, parsed) {
  const wrap = document.createElement("div");
  wrap.className = "timeline-card-edit";

  const header = document.createElement("div");
  header.className = "timeline-card-edit-head";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "ghost small timeline-card-edit-btn";
  button.textContent = t("timeline.card.edit");
  if (!timelineEditHandler) {
    button.disabled = true;
  }
  header.appendChild(button);
  wrap.appendChild(header);

  const panel = document.createElement("div");
  panel.className = "timeline-card-edit-panel";
  panel.hidden = true;

  if (message.role === "system_report" && parsed) {
    panel.appendChild(createSystemReportEditor(message, parsed, panel, button));
  } else {
    panel.appendChild(createPlainTextEditor(message, panel, button));
  }

  button.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) {
      button.textContent = t("timeline.card.edit_close");
    } else {
      button.textContent = t("timeline.card.edit");
    }
  });

  wrap.appendChild(panel);
  return wrap;
}

function createSystemReportEditor(message, parsed, panel, toggleButton) {
  const form = document.createElement("div");
  form.className = "timeline-card-edit-form";

  const titleInput = createLabeledInput(t("timeline.card.edit_title"), parsed.title || "");
  const summaryInput = createLabeledTextarea(
    t("timeline.card.edit_summary"),
    parsed.summary || "",
    2
  );
  const tensionInput = createLabeledInput(
    t("timeline.card.edit_tension"),
    String(clampPercent(parsed.tension_percent ?? 0))
  );
  tensionInput.input.type = "number";
  tensionInput.input.min = "0";
  tensionInput.input.max = "100";

  const crisisInput = createLabeledInput(
    t("timeline.card.edit_crisis"),
    parsed.crisis_focus || ""
  );
  const eventsInput = createLabeledTextarea(
    t("timeline.card.edit_events"),
    formatEditableEntries(parsed.events),
    4
  );
  const risksInput = createLabeledTextarea(
    t("timeline.card.edit_risks"),
    formatEditableEntries(parsed.risks),
    3
  );

  form.appendChild(titleInput.wrap);
  form.appendChild(summaryInput.wrap);
  form.appendChild(tensionInput.wrap);
  form.appendChild(crisisInput.wrap);
  form.appendChild(eventsInput.wrap);
  form.appendChild(risksInput.wrap);

  const actions = document.createElement("div");
  actions.className = "timeline-card-edit-actions";

  const save = document.createElement("button");
  save.type = "button";
  save.className = "primary small";
  save.textContent = t("timeline.card.edit_save");

  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "ghost small";
  cancel.textContent = t("timeline.card.edit_cancel");

  actions.appendChild(save);
  actions.appendChild(cancel);
  form.appendChild(actions);

  cancel.addEventListener("click", () => {
    panel.hidden = true;
    toggleButton.textContent = t("timeline.card.edit");
  });

  save.addEventListener("click", () => {
    if (!timelineEditHandler) return;
    const payload = {
      report_snapshot: {
        title: titleInput.input.value.trim() || parsed.title || t("timeline.card.system_report_default_title"),
        time_advance: parsed.time_advance || message.time_jump_label || "",
        summary: summaryInput.input.value.trim(),
        tension_percent: clampPercent(tensionInput.input.value),
        crisis_focus: crisisInput.input.value.trim(),
        events: parseEditableEntries(eventsInput.input.value, "neutral", "medium"),
        risks: parseEditableEntries(risksInput.input.value, "negative", "high"),
      },
    };
    save.disabled = true;
    Promise.resolve(timelineEditHandler(message, payload))
      .then(() => {
        panel.hidden = true;
        toggleButton.textContent = t("timeline.card.edit");
      })
      .finally(() => {
        save.disabled = false;
      });
  });

  return form;
}

function createPlainTextEditor(message, panel, toggleButton) {
  const form = document.createElement("div");
  form.className = "timeline-card-edit-form";

  const contentInput = createLabeledTextarea(
    t("timeline.card.edit_content"),
    String(message.content || ""),
    4
  );
  form.appendChild(contentInput.wrap);

  const actions = document.createElement("div");
  actions.className = "timeline-card-edit-actions";

  const save = document.createElement("button");
  save.type = "button";
  save.className = "primary small";
  save.textContent = t("timeline.card.edit_save");

  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "ghost small";
  cancel.textContent = t("timeline.card.edit_cancel");

  actions.appendChild(save);
  actions.appendChild(cancel);
  form.appendChild(actions);

  cancel.addEventListener("click", () => {
    panel.hidden = true;
    toggleButton.textContent = t("timeline.card.edit");
  });

  save.addEventListener("click", () => {
    if (!timelineEditHandler) return;
    save.disabled = true;
    Promise.resolve(
      timelineEditHandler(message, {
        content: contentInput.input.value.trim(),
      })
    )
      .then(() => {
        panel.hidden = true;
        toggleButton.textContent = t("timeline.card.edit");
      })
      .finally(() => {
        save.disabled = false;
      });
  });
  return form;
}

function createLabeledInput(labelText, value) {
  const wrap = document.createElement("label");
  wrap.className = "timeline-card-edit-field";
  const label = document.createElement("span");
  label.textContent = labelText;
  const input = document.createElement("input");
  input.type = "text";
  input.value = value || "";
  wrap.appendChild(label);
  wrap.appendChild(input);
  return { wrap, input };
}

function createLabeledTextarea(labelText, value, rows) {
  const wrap = document.createElement("label");
  wrap.className = "timeline-card-edit-field";
  const label = document.createElement("span");
  label.textContent = labelText;
  const input = document.createElement("textarea");
  input.rows = rows;
  input.value = value || "";
  wrap.appendChild(label);
  wrap.appendChild(input);
  return { wrap, input };
}

function formatEditableEntries(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return "";
  return rows
    .map((row) => {
      const category = normalizeEventCategory(row.category);
      const severity = normalizeEventSeverity(row.severity) || "medium";
      const description = String(row.description || "").replace(/\s+/g, " ").trim();
      return `${category}|${severity}|${description}`;
    })
    .filter(Boolean)
    .join("\n");
}

function parseEditableEntries(rawValue, defaultCategory, defaultSeverity) {
  const lines = String(rawValue || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const rows = [];
  lines.forEach((line) => {
    const segments = line.split("|");
    if (segments.length >= 3) {
      const [category, severity, ...rest] = segments;
      const description = rest.join("|").trim();
      if (!description) return;
      rows.push({
        category: normalizeEventCategory(category) || defaultCategory,
        severity: normalizeEventSeverity(severity) || defaultSeverity,
        description,
      });
      return;
    }
    rows.push({
      category: defaultCategory,
      severity: defaultSeverity,
      description: line,
    });
  });
  return rows;
}

function renderKeyEvents(messages) {
  if (!keyEventsListEl) return;
  keyEventsListEl.innerHTML = "";
  const rows = collectKeyEvents(messages);
  if (rows.length === 0) {
    const empty = document.createElement("div");
    empty.className = "key-event-empty";
    empty.textContent = t("sidebar.key_events_empty");
    keyEventsListEl.appendChild(empty);
    return;
  }

  rows.forEach((row) => {
    const item = document.createElement("article");
    item.className = "key-event-item";
    const title = document.createElement("strong");
    title.textContent = `${row.time} · ${row.category}`;
    const summary = document.createElement("span");
    summary.textContent = row.summary;
    item.appendChild(title);
    item.appendChild(summary);
    keyEventsListEl.appendChild(item);
  });
}

function collectKeyEvents(messages) {
  if (!Array.isArray(messages) || messages.length === 0) {
    return [];
  }

  const rows = [];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== "system_report") continue;
    const parsed = resolveReportSnapshot(message);
    if (!parsed) continue;
    const category = dominantEventCategory(parsed.events || []);
    const label = eventCategoryLabel(category);
    const summary = toHeadlineSentence(
      parsed.summary || parsed.events?.[0]?.description || parsed.risks?.[0]?.description
    );
    if (!summary) continue;
    rows.push({
      time: formatMessageTime(message.created_at) || `#${message.seq}`,
      category: label,
      summary,
    });
    if (rows.length >= MAX_KEY_EVENTS) break;
  }
  return rows;
}

function dominantEventCategory(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return "neutral";
  const score = { positive: 0, negative: 0, neutral: 0 };
  rows.forEach((item) => {
    const category = normalizeEventCategory(item.category);
    score[category] += 1;
  });
  if (score.negative >= score.positive && score.negative >= score.neutral) return "negative";
  if (score.positive >= score.neutral) return "positive";
  return "neutral";
}

function resolveReportSnapshot(message) {
  if (message && message.report_snapshot && typeof message.report_snapshot === "object") {
    return normalizeReportPayload(message.report_snapshot);
  }
  return parseReport(message?.content || "");
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
    return normalizeReportPayload(payload);
  } catch (_) {
    return null;
  }
}

function normalizeReportPayload(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return null;
  }
  const normalized = {
    title: toSafeText(payload.title),
    time_advance: toSafeText(payload.time_advance),
    summary: toSafeText(payload.summary),
    events: normalizeEventList(payload.events),
    risks: normalizeEventList(payload.risks),
    tension_percent: parseNumber(
      payload.tension_percent ?? payload.tension_index ?? payload.tension
    ),
    crisis_focus: toSafeText(
      payload.crisis_focus ?? payload.crisis_focus_event ?? payload.focus_event
    ),
  };
  return normalized;
}

function parseNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return null;
  const normalized = value.replace("%", "").trim();
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function toSafeText(value) {
  if (typeof value !== "string") return "";
  return value.trim();
}

function normalizeEventList(value) {
  if (!Array.isArray(value)) return [];
  const rows = [];
  value.forEach((item) => {
    if (typeof item === "string") {
      const description = item.trim();
      if (!description) return;
      rows.push({
        category: "neutral",
        severity: "medium",
        description,
      });
      return;
    }
    if (item && typeof item === "object") {
      const category = normalizeEventCategory(item.category);
      const severity = normalizeEventSeverity(item.severity) || "medium";
      const description = toSafeText(item.description || item.detail || item.content || item.label || item.title);
      if (!description) return;
      rows.push({
        category,
        severity,
        description,
      });
    }
  });
  return rows;
}

function deriveSituationMetrics(parsed, timelineConfig) {
  const explicitTension = parseNumber(parsed.tension_percent);
  if (typeof explicitTension === "number") {
    return {
      tensionPercent: clampPercent(explicitTension),
      crisisFocus: deriveCrisisFocus(parsed),
    };
  }

  let score = 28;
  parsed.events.forEach((row) => {
    const severity = inferEventSeverity(row, timelineConfig).level;
    const unit = severity === "high" ? 24 : severity === "medium" ? 15 : 8;
    if (row.category === "negative") {
      score += unit;
    } else if (row.category === "positive") {
      score -= Math.round(unit * 0.6);
    } else {
      score += Math.round(unit * 0.2);
    }
  });
  score += parsed.risks.length * 8;

  return {
    tensionPercent: clampPercent(score),
    crisisFocus: deriveCrisisFocus(parsed),
  };
}

function clampPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(100, Math.round(numeric)));
}

function deriveCrisisFocus(parsed) {
  const explicit = toHeadlineSentence(parsed.crisis_focus);
  if (explicit) return explicit;

  const highNegative = parsed.events.find(
    (item) =>
      normalizeEventCategory(item.category) === "negative" &&
      normalizeEventSeverity(item.severity) === "high"
  );
  if (highNegative) return toHeadlineSentence(highNegative.description);

  const negative = parsed.events.find(
    (item) => normalizeEventCategory(item.category) === "negative"
  );
  if (negative) return toHeadlineSentence(negative.description);

  const risk = parsed.risks[0];
  if (risk) return toHeadlineSentence(risk.description);

  const firstEvent = parsed.events[0];
  if (firstEvent) return toHeadlineSentence(firstEvent.description);

  return toHeadlineSentence(parsed.summary) || t("timeline.card.crisis_focus_none");
}

function createMetricsSection(tensionPercent, crisisFocus) {
  const wrap = document.createElement("div");
  wrap.className = "timeline-metrics";

  const tension = document.createElement("article");
  tension.className = "timeline-metric";
  const tensionTitle = document.createElement("h4");
  tensionTitle.textContent = t("timeline.card.tension");
  const tensionValue = document.createElement("p");
  tensionValue.textContent = `${clampPercent(tensionPercent)}%`;
  tension.appendChild(tensionTitle);
  tension.appendChild(tensionValue);

  const focus = document.createElement("article");
  focus.className = "timeline-metric";
  const focusTitle = document.createElement("h4");
  focusTitle.textContent = t("timeline.card.crisis_focus");
  const focusValue = document.createElement("p");
  focusValue.textContent = crisisFocus;
  focus.appendChild(focusTitle);
  focus.appendChild(focusValue);

  wrap.appendChild(tension);
  wrap.appendChild(focus);
  return wrap;
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
  const sentences =
    normalized
      .match(/[^。！？!?\.]+[。！？!?\.]?/g)
      ?.map((part) => part.trim())
      .filter(Boolean) || [normalized];
  return sentences.slice(0, 3).join(" ");
}

function toHeadlineSentence(text) {
  const normalized = String(text || "").trim().replace(/\s+/g, " ");
  if (!normalized) return "";
  const sentenceMatch = normalized.match(/[^。！？!?\.]+[。！？!?\.]?/);
  const first = sentenceMatch && sentenceMatch[0] ? sentenceMatch[0].trim() : "";
  if (!first) return normalized.slice(0, 90);
  return first.length > 120 ? `${first.slice(0, 120)}...` : first;
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
    return raw.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();
  }
  return raw;
}

function extractJsonObject(content) {
  const start = content.indexOf("{");
  const end = content.lastIndexOf("}");
  if (start === -1 || end === -1 || end <= start) return "";
  return content.slice(start, end + 1).trim();
}

function formatMessageTime(createdAt) {
  const raw = String(createdAt || "").trim();
  if (!raw) return "";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return "";
  return new Intl.DateTimeFormat(getCurrentLocale(), {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}
