"""Local desktop launcher. Provider credentials never leave the private .env file."""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser

ROOT = Path(__file__).resolve().parent


def environment_python(directory: Path) -> Path:
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def install() -> None:
    tools = ROOT / ".launcher-env"
    executable = environment_python(tools)
    if not executable.exists():
        venv.EnvBuilder(with_pip=True).create(tools)
    subprocess.run([str(executable), "-m", "pip", "install", "uv==0.12.23"], check=True, cwd=ROOT)
    subprocess.run([str(executable), "-m", "uv", "sync", "--frozen", "--no-dev"], check=True, cwd=ROOT)


def main() -> None:
    if sys.version_info < (3, 12):
        raise SystemExit("Install Python 3.12 or newer from https://www.python.org/downloads/ first.")
    import tkinter as tk
    from tkinter import messagebox

    os.chdir(ROOT)
    window = tk.Tk()
    window.title("J.A.R.V.I.S. · Local launcher")
    window.geometry("520x350")
    window.configure(bg="#0c141d")
    frame = tk.Frame(window, bg="#0c141d", padx=28, pady=24)
    frame.pack(fill="both", expand=True)
    tk.Label(frame, text="J.A.R.V.I.S.", font=("Arial", 23), fg="#62e4ed", bg="#0c141d").pack(anchor="w")
    tk.Label(frame, text="Your assistant, running on this computer.", fg="#a6b9c7", bg="#0c141d").pack(anchor="w", pady=(8, 20))
    tk.Label(frame, text="Groq API key (first launch only)", fg="#dae5eb", bg="#0c141d").pack(anchor="w")
    entry = tk.Entry(frame, show="*", width=55)
    entry.pack(fill="x", pady=8)
    tk.Label(frame, text="Your key is stored privately in this folder's .env file.\nAI responses use Groq online; the interface runs locally.", justify="left", fg="#8ca2b1", bg="#0c141d").pack(anchor="w")
    status = tk.StringVar(value="Click Start to install dependencies and open your interface.")
    tk.Label(frame, textvariable=status, wraplength=450, justify="left", fg="#62e4ed", bg="#0c141d").pack(anchor="w", pady=14)
    process: subprocess.Popen | None = None
    token = ""
    stopping = threading.Event()

    def configure(key: str) -> str:
        path = ROOT / ".env"
        lines = path.read_text().splitlines() if path.exists() else []
        current = dict(line.split("=", 1) for line in lines if "=" in line and not line.lstrip().startswith("#"))
        stored_key = current.get("JARVIS_PROVIDER_API_KEY", "").strip().strip('"').strip("'")
        if not key and not stored_key:
            raise ValueError("Enter your Groq API key for the first launch.")
        if any(char in key for char in '\n\r"\''):
            raise ValueError("API key must be a single value without quotes or newlines.")
        access_token = current.get("JARVIS_API_TOKEN", "").strip().strip('"').strip("'") or secrets.token_urlsafe(48)
        updates = {"JARVIS_API_TOKEN": access_token}
        if key or not path.exists():
            updates.update({"JARVIS_PROVIDER": "openai_compatible",
                            "JARVIS_PROVIDER_API_KEY": key or stored_key,
                            "JARVIS_PROVIDER_BASE_URL": "https://api.groq.com/openai/v1",
                            "JARVIS_MODEL": "openai/gpt-oss-20b"})
        seen = set()
        output = []
        for line in lines:
            name = line.split("=", 1)[0] if "=" in line else ""
            if name in updates:
                if name not in seen:
                    output.append(name + "=" + updates[name])
                    seen.add(name)
            else:
                output.append(line)
        output += [name + "=" + value for name, value in updates.items() if name not in seen]
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as file:
            file.write("\n".join(output) + "\n")
        if os.name != "nt":
            path.chmod(0o600)
        return access_token

    def ready() -> None:
        status.set("Ready. Click Copy access token, then paste it into the interface's ⚙ settings and Connect.")
        start_button.configure(text="Open interface", state="normal", command=lambda: webbrowser.open("http://127.0.0.1:8000/"))
        copy_button.configure(state="normal")
        webbrowser.open("http://127.0.0.1:8000/")

    def failed(message: str) -> None:
        status.set(message)
        start_button.configure(state="normal")

    def worker() -> None:
        nonlocal process
        try:
            install()
            if stopping.is_set():
                return
            try:
                with socket.create_connection(("127.0.0.1", 8000), timeout=1):
                    raise RuntimeError("Port 8000 is already in use. Close the other launcher or service, then retry.")
            except OSError:
                pass
            process = subprocess.Popen([str(environment_python(ROOT / ".venv")), "-m", "uvicorn",
                                        "jarvis.main:app", "--host", "127.0.0.1", "--port", "8000",
                                        "--workers", "1", "--no-access-log"], cwd=ROOT)
            for _ in range(100):
                if stopping.is_set():
                    process.terminate()
                    return
                if process.poll() is not None:
                    raise RuntimeError("Server could not start. Port 8000 may already be in use; close the other launcher and retry.")
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=1) as response:
                        if response.status == 200:
                            window.after(0, ready)
                            return
                except OSError:
                    pass
                time.sleep(0.2)
            process.terminate()
            raise RuntimeError("The server did not become ready. Check the terminal output.")
        except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
            if not stopping.is_set():
                message = str(error) if isinstance(error, RuntimeError) else "Installation failed. Check your internet connection and the terminal output, then retry."
                window.after(0, lambda message=message: failed(message))

    def start() -> None:
        nonlocal token
        try:
            token = configure(entry.get().strip())
        except ValueError as error:
            messagebox.showerror("Configuration needed", str(error))
            return
        entry.delete(0, "end")
        start_button.configure(state="disabled")
        status.set("Installing verified dependencies… the first launch may take a few minutes.")
        threading.Thread(target=worker, daemon=True).start()

    def copy_token() -> None:
        window.clipboard_clear()
        window.clipboard_append(token)
        status.set("Access token copied. Paste it into the interface's ⚙ settings, then click Connect.")

    buttons = tk.Frame(frame, bg="#0c141d")
    buttons.pack(anchor="w")
    start_button = tk.Button(buttons, text="Start J.A.R.V.I.S.", command=start, padx=12, pady=7)
    start_button.pack(side="left")
    copy_button = tk.Button(buttons, text="Copy access token", command=copy_token, state="disabled", padx=12, pady=7)
    copy_button.pack(side="left", padx=10)

    def close() -> None:
        stopping.set()
        if process and process.poll() is None:
            process.terminate()
        try:
            if token and window.clipboard_get() == token:
                window.clipboard_clear()
        except tk.TclError:
            pass
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", close)
    window.mainloop()


if __name__ == "__main__":
    main()
