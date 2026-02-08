let socket = null;
let reconnectTimer = null;
let shouldReconnect = false;
let reconnectAttempt = 0;

export function connectWebSocket(sessionId, handlers) {
  const { onOpen, onClose, onEvent, onError } = handlers;
  shouldReconnect = true;

  const connect = () => {
    const url = `ws://127.0.0.1:8000/ws/${sessionId}`;
    socket = new WebSocket(url);

    socket.addEventListener("open", () => {
      reconnectAttempt = 0;
      if (onOpen) onOpen();
    });

    socket.addEventListener("message", (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (onEvent) onEvent(payload);
      } catch (err) {
        if (onError) onError(err);
      }
    });

    socket.addEventListener("close", () => {
      if (onClose) onClose();
      if (shouldReconnect) {
        scheduleReconnect();
      }
    });

    socket.addEventListener("error", (err) => {
      if (onError) onError(err);
    });
  };

  const scheduleReconnect = () => {
    reconnectAttempt += 1;
    const delay = Math.min(1000 * 2 ** reconnectAttempt, 10000);
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connect, delay);
  };

  connect();
}

export function closeWebSocket() {
  shouldReconnect = false;
  clearTimeout(reconnectTimer);
  if (socket) {
    socket.close();
  }
}
