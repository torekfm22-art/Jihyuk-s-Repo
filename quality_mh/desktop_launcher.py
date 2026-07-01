"""품질 표준인원 산출 시스템 — 데스크톱 앱 런처 (브라우저 없이 독립 창)."""
from __future__ import annotations

import atexit
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

APP_TITLE = "품질 표준인원 산출 시스템"
DEFAULT_PORT = 8501
WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900

_ROOT = Path(__file__).resolve().parent
_APP_SCRIPT = _ROOT / "app.py"
_SERVER_PROC: subprocess.Popen | None = None


def _find_free_port(start: int = DEFAULT_PORT) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("사용 가능한 포트를 찾을 수 없습니다.")


def _server_healthy(port: int) -> bool:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/_stcore/health", method="GET")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _wait_for_server(port: int, proc: subprocess.Popen, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        if _server_healthy(port):
            return True
        time.sleep(0.3)
    return False


def _stop_server() -> None:
    global _SERVER_PROC
    if _SERVER_PROC is None:
        return
    try:
        _SERVER_PROC.terminate()
        _SERVER_PROC.wait(timeout=8)
    except Exception:
        try:
            _SERVER_PROC.kill()
        except Exception:
            pass
    _SERVER_PROC = None


def _start_streamlit(port: int) -> subprocess.Popen:
    global _SERVER_PROC
    os.chdir(_ROOT)
    env = os.environ.copy()
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    config_dir = _ROOT / ".streamlit"
    if config_dir.exists():
        env["STREAMLIT_CONFIG_DIR"] = str(config_dir)

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(_APP_SCRIPT),
        "--server.headless",
        "true",
        "--server.port",
        str(port),
        "--server.address",
        "127.0.0.1",
        "--browser.gatherUsageStats",
        "false",
        "--global.developmentMode",
        "false",
    ]
    kwargs: dict = {
        "cwd": str(_ROOT),
        "env": env,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

    _SERVER_PROC = subprocess.Popen(cmd, **kwargs)
    atexit.register(_stop_server)
    return _SERVER_PROC


def _show_error(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_TITLE, message)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)
    sys.exit(1)


def _open_desktop_window(url: str) -> None:
    import webview

    webview.create_window(
        APP_TITLE,
        url,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=(1024, 700),
        text_select=True,
    )
    if sys.platform == "win32":
        webview.start(gui="edgechromium")
    else:
        webview.start()


def main() -> None:
    if not _APP_SCRIPT.exists():
        _show_error(f"앱 파일을 찾을 수 없습니다:\n{_APP_SCRIPT}")

    try:
        import webview  # noqa: F401
    except ImportError:
        _show_error(
            "데스크톱 창 실행에 필요한 pywebview가 없습니다.\n\n"
            "다음 명령으로 설치 후 다시 실행하세요:\n"
            "pip install pywebview"
        )

    try:
        port = _find_free_port()
    except RuntimeError as exc:
        _show_error(str(exc))

    proc = _start_streamlit(port)
    if proc.poll() is not None:
        _show_error("Streamlit 서버 시작에 실패했습니다.")

    if not _wait_for_server(port, proc):
        _stop_server()
        _show_error("Streamlit 서버 준비 시간이 초과되었습니다.\n잠시 후 다시 실행해 주세요.")

    url = f"http://127.0.0.1:{port}"
    try:
        _open_desktop_window(url)
    finally:
        _stop_server()


if __name__ == "__main__":
    main()
