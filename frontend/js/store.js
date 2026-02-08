export const store = {
  session: null,
  branches: [],
  activeBranchId: null,
  timelineByBranch: {},
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

export function appendMessage(branchId, message) {
  if (!store.timelineByBranch[branchId]) {
    store.timelineByBranch[branchId] = [];
  }
  store.timelineByBranch[branchId].push(message);
}
