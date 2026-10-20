from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT_DIR / "data" / "tmp" / "services"
PID_FILE = LOG_DIR / "services.json"


def port_is_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(0.2)
        return client.connect_ex(("127.0.0.1", port)) == 0


def listening_process_id(port: int) -> int | None:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"(Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return int(result.stdout.strip()) if result.stdout.strip().isdigit() else None


def command_line(process_id: int) -> str:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"(Get-CimInstance Win32_Process -Filter 'ProcessId={process_id}').CommandLine",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return result.stdout.strip()


def read_pid_file() -> dict[str, int]:
    if not PID_FILE.is_file():
        return {}
    try:
        return {name: int(process_id) for name, process_id in json.loads(PID_FILE.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def write_pid_file(processes: dict[str, int]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(json.dumps(processes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def service_definitions() -> dict[str, dict[str, object]]:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise RuntimeError("找不到 npm。请先安装 Node.js，或确认 npm 已加入 PATH。")
    python = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        raise RuntimeError(f"找不到虚拟环境 Python：{python}")
    return {
        "frontend": {
            "port": 8122,
            "cwd": ROOT_DIR / "canvas-react",
            "command": [npm, "run", "dev", "--", "--host", "127.0.0.1"],
            "marker": "vite",
        },
        "backend": {
            "port": 8123,
            "cwd": ROOT_DIR,
            "command": [str(python), "backend\\main.py"],
            "marker": "backend\\main.py",
        },
        "mcp": {
            "port": 8124,
            "cwd": ROOT_DIR,
            "command": [str(python), "backend\\mcp_main.py"],
            "marker": "backend\\mcp_main.py",
        },
    }


def start_services() -> None:
    services = service_definitions()
    processes = read_pid_file()
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    for name, service in services.items():
        port = service["port"]
        if port is not None and port_is_listening(int(port)):
            print(f"{name}: 已在端口 {port} 运行。")
            continue
        stdout = (LOG_DIR / f"{name}.stdout.log").open("w", encoding="utf-8")
        stderr = (LOG_DIR / f"{name}.stderr.log").open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(
                service["command"],
                cwd=service["cwd"],
                stdout=stdout,
                stderr=stderr,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
            )
        finally:
            stdout.close()
            stderr.close()
        for _ in range(20):
            time.sleep(0.5)
            if port_is_listening(int(port)):
                listener_pid = listening_process_id(int(port)) or process.pid
                processes[name] = listener_pid
                print(f"{name}: 已启动，端口 {port}，PID {listener_pid}。")
                break
        else:
            print(f"{name}: 启动失败，请查看 {LOG_DIR / f'{name}.stderr.log'}", file=sys.stderr)

    write_pid_file(processes)
    print("\n前端  http://127.0.0.1:8122")
    print("后端  http://127.0.0.1:8123/api/health")
    print("MCP    http://127.0.0.1:8124/mcp")


def stop_services() -> None:
    services = service_definitions()
    processes = read_pid_file()
    remaining: dict[str, int] = {}

    for name, service in services.items():
        port = service["port"]
        process_id = processes.get(name) or listening_process_id(int(port))
        if not process_id:
            continue
        current_command = command_line(process_id).lower().replace("/", "\\")
        marker = str(service["marker"]).lower()
        if marker not in current_command:
            print(f"{name}: PID {process_id} 已不存在或不属于该服务，未停止。")
            continue
        subprocess.run(["taskkill", "/PID", str(process_id), "/T", "/F"], capture_output=True, text=True, check=False)
        print(f"{name}: 已停止（PID {process_id}）。")

    for name, service in services.items():
        port = service["port"]
        if port_is_listening(int(port)):
            print(f"{name}: 端口 {service['port']} 仍在监听，但不是本脚本启动的进程，未停止。")
    write_pid_file(remaining)


def show_status() -> None:
    for name, service in service_definitions().items():
        port = int(service["port"])
        print(f"{name}: {'运行中' if port_is_listening(port) else '未运行'}（端口 {port}）")


def main() -> None:
    parser = argparse.ArgumentParser(description="管理 SketchToUI 前端、Flask 与 Remote MCP 服务。")
    parser.add_argument("command", choices=("start", "stop", "status"))
    args = parser.parse_args()
    {"start": start_services, "stop": stop_services, "status": show_status}[args.command]()


if __name__ == "__main__":
    main()
