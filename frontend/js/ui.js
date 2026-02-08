const sessionIdEl = document.getElementById("sessionId");
const runnerStateEl = document.getElementById("runnerState");
const connectionStateEl = document.getElementById("connectionState");
const timelineListEl = document.getElementById("timelineList");
const logListEl = document.getElementById("logList");

export function setSessionId(sessionId) {
  sessionIdEl.textContent = sessionId || "Not created";
}

export function setRunnerState(state) {
  runnerStateEl.textContent = state;
}

export function setConnectionState(state) {
  connectionStateEl.textContent = state;
}

export function renderTimeline(messages) {
  timelineListEl.innerHTML = "";
  messages.forEach((message) => {
    timelineListEl.appendChild(buildTimelineItem(message));
  });
}

export function appendTimelineMessage(message) {
  timelineListEl.appendChild(buildTimelineItem(message));
  timelineListEl.scrollTop = timelineListEl.scrollHeight;
}

export function addLog(message) {
  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.textContent = message;
  logListEl.prepend(entry);
}

function buildTimelineItem(message) {
  const item = document.createElement("div");
  item.className = "timeline-item";
  const title = document.createElement("h3");
  title.textContent = `#${message.seq} ${message.time_jump_label}`;
  const content = document.createElement("p");
  content.textContent = message.content;
  item.appendChild(title);
  item.appendChild(content);
  return item;
}
