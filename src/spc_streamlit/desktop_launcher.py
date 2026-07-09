"""
SPC 공정 안정성 점검 — 데스크톱 앱 런처 (공장 배포용)

Streamlit은 별도 프로세스에서 실행합니다.
"""
from __future__ import annotations

import argparse
import atexit
import logging
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

if not getattr(sys, "frozen", False):
    _ROOT = Path(__file__).resolve().parent.parent.parent
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))

from config.app_paths import get_project_root, get_resource_root, is_frozen

APP_TITLE = "SPC 공정 안정성 점검"
WORKER_FLAG = "--streamlit-worker"
DEFAULT_PORT = 8501
logger = logging.getLogger("spc.desktop")

_server_proc: subprocess.Popen | None = None
_worker_log_path: Path | None = None


def _app_script_path() -> Path:
    if is_frozen():
        bundled = get_resource_root() / "src" / "spc_streamlit" / "app.py"
        if bundled.exists():
            return bundled
    return Path(__file__).resolve().parent / "app.py"


def _find_free_port(start: int = DEFAULT_PORT, attempts: int = 30) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"사용 가능한 포트 없음 ({start}~{start + attempts - 1})")


def _server_healthy(port: int) -> bool:
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/_stcore/health",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _wait_for_server(port: int, proc: subprocess.Popen, timeout: float = 120.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        if _server_healthy(port):
            return True
        time.sleep(0.3)
    return False


def _read_worker_log_tail(max_lines: int = 30) -> str:
    if _worker_log_path is None or not _worker_log_path.exists():
        return "(워커 로그 없음)"
    try:
        lines = _worker_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:]) if lines else "(로그 비어 있음)"
    except OSError:
        return "(로그 읽기 실패)"


def _streamlit_worker(app_path: Path, port: int) -> None:
    """PyInstaller 번들용 워커 — bootstrap.run (메인 스레드)."""
    root_dir = get_project_root()
    os.chdir(root_dir)
    if is_frozen():
        res = str(get_resource_root())
        if res not in sys.path:
            sys.path.insert(0, res)

    from streamlit.web import bootstrap

    flag_options = {
        "server.headless": True,
        "server.port": port,
        "server.address": "127.0.0.1",
        "server.enableXsrfProtection": False,
        "browser.serverAddress": "127.0.0.1",
        "browser.serverPort": port,
        "browser.gatherUsageStats": False,
        "global.developmentMode": False,
    }
    bootstrap.run(str(app_path), False, [], flag_options)


def _stop_server() -> None:
    global _server_proc
    if _server_proc is None:
        return
    try:
        _server_proc.terminate()
        _server_proc.wait(timeout=10)
    except Exception:
        try:
            _server_proc.kill()
        except Exception:
            pass
    _server_proc = None


def _dev_streamlit_command(app_path: Path, port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
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


def _worker_command(app_path: Path, port: int) -> list[str]:
    if is_frozen():
        return [
            sys.executable,
            WORKER_FLAG,
            "--app",
            str(app_path),
            "--port",
            str(port),
        ]
    return _dev_streamlit_command(app_path, port)


def _start_server_subprocess(app_path: Path, port: int) -> subprocess.Popen:
    global _server_proc, _worker_log_path
    root_dir = get_project_root()
    log_dir = root_dir / "data" / "output"
    log_dir.mkdir(parents=True, exist_ok=True)
    _worker_log_path = log_dir / "streamlit_worker.log"

    cmd = _worker_command(app_path, port)
    log_file = open(_worker_log_path, "w", encoding="utf-8", buffering=1)
    log_file.write(f"# cmd: {' '.join(cmd)}\n")
    log_file.flush()

    kwargs: dict = {
        "cwd": str(root_dir),
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

    logger.info("Streamlit 워커 시작: %s", " ".join(cmd))
    logger.info("워커 로그: %s", _worker_log_path)
    _server_proc = subprocess.Popen(cmd, **kwargs)
    atexit.register(_stop_server)
    return _server_proc


class _StartupSplash:
    """서버 기동 중 상태 표시."""

    def __init__(self) -> None:
        self._root = None

    def show(self, message: str) -> None:
        try:
            import tkinter as tk
            from tkinter import ttk

            if self._root is None:
                self._root = tk.Tk()
                self._root.title(APP_TITLE)
                self._root.geometry("420x120")
                self._root.resizable(False, False)
                self._label = ttk.Label(self._root, text=message, wraplength=380, justify="center")
                self._label.pack(expand=True, fill="both", padx=16, pady=16)
                self._root.update()
            else:
                self._label.config(text=message)
                self._root.update()
        except Exception:
            pass

    def close(self) -> None:
        if self._root is not None:
            try:
                self._root.destroy()
            except Exception:
                pass
            self._root = None


def _open_webview(url: str) -> None:
    import webview

    webview.create_window(
        APP_TITLE,
        url,
        width=1400,
        height=920,
        min_size=(1024, 700),
        text_select=True,
    )
    webview.start(gui="edgechromium")


def _open_browser_fallback(url: str) -> None:
    webbrowser.open(url)
    try:
        import tkinter as tk
        from tkinter import ttk

        root = tk.Tk()
        root.title(APP_TITLE)
        root.geometry("480x160")
        root.resizable(False, False)
        frm = ttk.Frame(root, padding=16)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=APP_TITLE, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(
            frm,
            text=f"브라우저에서 실행 중입니다.\n{url}\n\n창을 닫으면 프로그램이 종료됩니다.",
            wraplength=440,
        ).pack(anchor="w", pady=(8, 12))
        ttk.Button(frm, text="브라우저 다시 열기", command=lambda: webbrowser.open(url)).pack(anchor="e")
        root.protocol("WM_DELETE_WINDOW", root.quit)
        root.mainloop()
    except Exception:
        input("브라우저에서 앱을 사용하세요. 종료하려면 Enter...")


def _show_fatal(message: str) -> None:
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


def _parse_worker_args() -> argparse.Namespace | None:
    if WORKER_FLAG not in sys.argv:
        return None
    parser = argparse.ArgumentParser()
    parser.add_argument(WORKER_FLAG, action="store_true")
    parser.add_argument("--app", required=True)
    parser.add_argument("--port", type=int, required=True)
    return parser.parse_args()


def main() -> None:
    worker_args = _parse_worker_args()
    if worker_args is not None:
        _streamlit_worker(Path(worker_args.app), worker_args.port)
        return

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    root_dir = get_project_root()
    os.chdir(root_dir)
    if is_frozen():
        res = str(get_resource_root())
        if res not in sys.path:
            sys.path.insert(0, res)
    for sub in ("data/input", "data/output", "data/output/charts", "config"):
        (root_dir / sub).mkdir(parents=True, exist_ok=True)

    app_path = _app_script_path()
    if not app_path.exists():
        _show_fatal(f"앱 스크립트를 찾을 수 없습니다:\n{app_path}")

    try:
        port = _find_free_port()
    except RuntimeError as exc:
        _show_fatal(str(exc))

    url = f"http://127.0.0.1:{port}"
    splash = _StartupSplash()
    splash.show(f"Streamlit 서버 시작 중...\n포트 {port}")

    proc = _start_server_subprocess(app_path, port)

    if proc.poll() is not None:
        splash.close()
        _show_fatal(
            "Streamlit 워커가 즉시 종료되었습니다.\n\n"
            f"{_read_worker_log_tail()}"
        )

    splash.show(f"서버 준비 대기 중...\n{url}")
    if not _wait_for_server(port, proc):
        splash.close()
        _stop_server()
        tail = _read_worker_log_tail()
        if proc.poll() is not None:
            _show_fatal(f"Streamlit 워커 오류로 종료되었습니다.\n\n{tail}")
        _show_fatal(
            "Streamlit 서버 시작 시간 초과 (120초).\n"
            f"로그: { _worker_log_path }\n\n{tail}"
        )

    splash.close()
    logger.info("서버 준비 완료: %s", url)

    try:
        _open_webview(url)
    except ImportError:
        logger.warning("pywebview 미설치 — 기본 브라우저로 실행")
        _open_browser_fallback(url)
    except Exception as exc:
        logger.exception("내장 창 실행 실패: %s", exc)
        _open_browser_fallback(url)
    finally:
        _stop_server()


if __name__ == "__main__":
    main()
