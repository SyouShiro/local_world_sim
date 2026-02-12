from __future__ import annotations

import contextlib
import http.server
import os
from pathlib import Path
import secrets
import signal
import socket
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn


def main() -> None:
    """Run backend + frontend servers and open the UI in the default browser.

    This entrypoint is designed for PyInstaller (optionally via PyArmor obfuscation).
    """

    config_dir = _config_dir()
    resource_dir = _resource_dir(config_dir)

    # Ensure relative paths (.env / worldline.db) go next to the exe.
    os.chdir(config_dir)

    ui_port = _pick_free_port(preferred=int(os.getenv("UI_PORT", "5500")))
    backend_host = "127.0.0.1"
    backend_port = 8000
    os.environ["APP_HOST"] = backend_host
    os.environ["APP_PORT"] = str(backend_port)

    _ensure_app_secret_key(config_dir)
    _ensure_cors_origins(ui_port)

    backend_thread, backend_server = _start_backend(host=backend_host, port=backend_port)
    frontend_root = resource_dir / "frontend"
    frontend_thread, frontend_server = _start_frontend(frontend_root, port=ui_port)

    ui_url = f"http://127.0.0.1:{ui_port}/"
    _wait_http_ready(f"http://127.0.0.1:{backend_port}/docs", timeout_sec=20)
    _wait_http_ready(ui_url, timeout_sec=10)
    _open_browser(ui_url)

    stop_event = threading.Event()

    def _handle_exit(*_: object) -> None:
        stop_event.set()

    with contextlib.suppress(Exception):
        signal.signal(signal.SIGINT, _handle_exit)
        signal.signal(signal.SIGTERM, _handle_exit)

    try:
        while not stop_event.is_set():
            time.sleep(0.25)
    finally:
        _shutdown_frontend(frontend_server, frontend_thread)
        _shutdown_backend(backend_server, backend_thread)


def _config_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _resource_dir(config_dir: Path) -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return config_dir


def _pick_free_port(preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])


def _ensure_app_secret_key(config_dir: Path) -> None:
    if os.getenv("APP_SECRET_KEY"):
        return

    env_path = config_dir / ".env"
    existing = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    for line in existing:
        if line.strip().startswith("APP_SECRET_KEY="):
            raw_value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if raw_value:
                return

    secret_value = secrets.token_urlsafe(48)
    _upsert_env_value(env_path, "APP_SECRET_KEY", secret_value)


def _ensure_cors_origins(ui_port: int) -> None:
    origins = {
        f"http://127.0.0.1:{ui_port}",
        f"http://localhost:{ui_port}",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    }
    current = os.getenv("CORS_ORIGINS", "").strip()
    if current:
        for item in current.split(","):
            candidate = item.strip()
            if candidate:
                origins.add(candidate)
    os.environ["CORS_ORIGINS"] = ",".join(sorted(origins))


def _start_backend(*, host: str, port: int) -> tuple[threading.Thread, uvicorn.Server]:
    backend_dir = _config_dir() / "backend"
    if backend_dir.exists():
        sys.path.insert(0, str(backend_dir))

    from app.main import create_app  # local import for PyInstaller analysis

    app = create_app()
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, name="worldline-backend", daemon=True)
    thread.start()
    return thread, server


class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_: object) -> None:  # noqa: D401
        # Avoid noisy access logs in the launcher console.
        return


def _start_frontend(frontend_root: Path, *, port: int) -> tuple[threading.Thread, socketserver.TCPServer]:
    if not frontend_root.exists():
        raise FileNotFoundError(f"frontend directory not found: {frontend_root}")

    handler = lambda *args, **kwargs: _SilentHandler(  # noqa: E731
        *args, directory=str(frontend_root), **kwargs
    )

    class _ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        daemon_threads = True
        allow_reuse_address = True

    server: socketserver.TCPServer = _ThreadingServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, name="worldline-frontend", daemon=True)
    thread.start()
    return thread, server


def _wait_http_ready(url: str, *, timeout_sec: int) -> None:
    deadline = time.time() + timeout_sec
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if 200 <= int(response.status) < 500:
                    return
        except (urllib.error.URLError, ValueError) as err:
            last_error = err
            time.sleep(0.25)
    raise RuntimeError(f"Service not ready: {url}") from last_error


def _open_browser(url: str) -> None:
    with contextlib.suppress(Exception):
        webbrowser.open(url, new=1, autoraise=True)


def _shutdown_frontend(server: socketserver.TCPServer, thread: threading.Thread) -> None:
    with contextlib.suppress(Exception):
        server.shutdown()
    with contextlib.suppress(Exception):
        server.server_close()
    thread.join(timeout=2.0)


def _shutdown_backend(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    thread.join(timeout=4.0)


def _upsert_env_value(env_path: Path, key: str, value: str) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updated: list[str] = []
    found = False
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            updated.append(line)
            continue
        if line.strip().startswith(f"{key}="):
            updated.append(f'{key}="{value}"')
            found = True
            continue
        updated.append(line)

    if not found:
        if updated and updated[-1].strip():
            updated.append("")
        updated.append(f'{key}="{value}"')

    env_path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
