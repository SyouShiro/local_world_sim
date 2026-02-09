export const store = {
  session: null,
  locale: "zh-CN",
  branches: [],
  activeBranchId: null,
  timelineByBranch: {},
  timelineConfig: {
    initialTimeISO: null,
    stepValue: 1,
    stepUnit: "month",
  },
  connectionState: "disconnected",
  runnerState: "idle",
  provider: {
    name: "openai",
    baseUrl: "",
    model: null,
    models: [],
  },
};

export function setStore(patch) {
  Object.assign(store, patch);
}

export function setTimeline(branchId, messages) {
  store.timelineByBranch[branchId] = messages;
}

export function setBranches(branches, activeBranchId) {
  store.branches = branches;
  store.activeBranchId = activeBranchId;
}

export function appendMessage(branchId, message) {
  if (!store.timelineByBranch[branchId]) {
    store.timelineByBranch[branchId] = [];
  }
  store.timelineByBranch[branchId].push(message);
}

export function replaceMessage(branchId, message) {
  const list = store.timelineByBranch[branchId];
  if (!Array.isArray(list)) return;
  const index = list.findIndex((item) => item.id === message.id);
  if (index === -1) return;
  list[index] = message;
}
