"""
local_tools.py — Mac-local tools for Oracle's full user-account capability mode.

Tools run as the currently logged-in macOS user. They do not elevate to root
or bypass macOS privacy prompts/TCC permissions.
"""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


MAX_COMMAND_TIMEOUT = 300
MAX_FILE_READ_BYTES = 2 * 1024 * 1024
MAX_FILE_WRITE_BYTES = 2 * 1024 * 1024
MAX_TOOL_OUTPUT = 12000


TOOL_DEFINITIONS = [
    {
        "tool_id": "local.list_directory",
        "name": "List local directory",
        "description": "عرض محتويات أي مجلد يستطيع حساب macOS الحالي الوصول إليه. input JSON: {path}.",
        "input_schema": {"path": "string"},
    },
    {
        "tool_id": "local.read_file",
        "name": "Read local file",
        "description": "قراءة ملف محلي يملكه أو يستطيع حساب macOS الحالي قراءته. input JSON: {path}.",
        "input_schema": {"path": "string"},
    },
    {
        "tool_id": "local.write_file",
        "name": "Write local file",
        "description": "إنشاء أو استبدال ملف محلي مع إنشاء المجلدات الأب. input JSON: {path, content}.",
        "input_schema": {"path": "string", "content": "string"},
    },
    {
        "tool_id": "local.move_path",
        "name": "Move local path",
        "description": "نقل أو إعادة تسمية ملف أو مجلد محلي. input JSON: {source, destination}.",
        "input_schema": {"source": "string", "destination": "string"},
    },
    {
        "tool_id": "local.delete_path",
        "name": "Delete local path",
        "description": "حذف ملف أو مجلد محلي بصلاحيات المستخدم الحالي. input JSON: {path, recursive}.",
        "input_schema": {"path": "string", "recursive": "boolean"},
    },
    {
        "tool_id": "local.find_files",
        "name": "Find local files",
        "description": "البحث عن أسماء ملفات داخل مجلد محلي باستخدام pattern. input JSON: {root, pattern, max_results}.",
        "input_schema": {"root": "string", "pattern": "string", "max_results": "integer"},
    },
    {
        "tool_id": "local.run_command",
        "name": "Run local command",
        "description": "تشغيل أمر محلي بأي برنامج متاح لحساب المستخدم الحالي. input JSON: {command: [arg, ...], cwd, timeout}. استخدم argv array؛ لا يوجد shell تلقائي.",
        "input_schema": {"command": "array<string>", "cwd": "string?", "timeout": "integer?"},
    },
    {
        "tool_id": "local.open_app",
        "name": "Open macOS application",
        "description": "فتح تطبيق macOS بالاسم باستخدام open -a. input JSON: {application}.",
        "input_schema": {"application": "string"},
    },
]


def available_tools() -> list[dict[str, Any]]:
    return [dict(tool) for tool in TOOL_DEFINITIONS]


def _payload(value: str | dict) -> dict[str, Any]:
    if isinstance(value, dict):
        data = value
    elif isinstance(value, str):
        try:
            data = json.loads(value)
        except ValueError as exc:
            raise ValueError("tool input must be valid JSON") from exc
    else:
        raise ValueError("tool input must be a JSON object")
    if not isinstance(data, dict):
        raise ValueError("tool input must be a JSON object")
    return data


def _path(value: Any, field: str = "path") -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty path")
    return Path(value).expanduser().resolve()


def _clip(value: str) -> str:
    if len(value) <= MAX_TOOL_OUTPUT:
        return value
    return value[:MAX_TOOL_OUTPUT] + "\n… (output truncated)"


def execute(tool_id: str, tool_input: str | dict) -> dict[str, Any]:
    """Execute a named local capability as the current macOS user."""
    data = _payload(tool_input)
    started = time.monotonic()
    try:
        if tool_id == "local.list_directory":
            target = _path(data.get("path"))
            if not target.is_dir():
                raise ValueError(f"not a directory: {target}")
            entries = []
            for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))[:500]:
                try:
                    stat = item.stat()
                    entries.append({
                        "name": item.name,
                        "path": str(item),
                        "type": "directory" if item.is_dir() else "file",
                        "size": stat.st_size,
                    })
                except OSError as exc:
                    entries.append({"name": item.name, "error": str(exc)})
            output = json.dumps(entries, ensure_ascii=False, indent=2)
            return _success(tool_id, output, started)

        if tool_id == "local.read_file":
            target = _path(data.get("path"))
            size = target.stat().st_size
            if size > MAX_FILE_READ_BYTES:
                raise ValueError(f"file is larger than {MAX_FILE_READ_BYTES} bytes")
            output = target.read_text(encoding="utf-8", errors="replace")
            return _success(tool_id, _clip(output), started)

        if tool_id == "local.write_file":
            target = _path(data.get("path"))
            content = data.get("content")
            if not isinstance(content, str):
                raise ValueError("content must be text")
            if len(content.encode("utf-8")) > MAX_FILE_WRITE_BYTES:
                raise ValueError(f"content is larger than {MAX_FILE_WRITE_BYTES} bytes")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return _success(tool_id, f"Written {len(content.encode('utf-8'))} bytes to {target}", started)

        if tool_id == "local.move_path":
            source = _path(data.get("source"), "source")
            destination = _path(data.get("destination"), "destination")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            return _success(tool_id, f"Moved {source} to {destination}", started)

        if tool_id == "local.delete_path":
            target = _path(data.get("path"))
            recursive = data.get("recursive", False)
            if not isinstance(recursive, bool):
                raise ValueError("recursive must be true or false")
            if target.is_dir():
                if recursive:
                    shutil.rmtree(target)
                else:
                    target.rmdir()
            else:
                target.unlink(missing_ok=False)
            return _success(tool_id, f"Deleted {target}", started)

        if tool_id == "local.find_files":
            root = _path(data.get("root"), "root")
            pattern = data.get("pattern", "*")
            maximum = data.get("max_results", 100)
            if not root.is_dir():
                raise ValueError(f"not a directory: {root}")
            if not isinstance(pattern, str) or not pattern:
                raise ValueError("pattern must be a non-empty string")
            if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 500:
                raise ValueError("max_results must be from 1 to 500")
            matches = []
            for current, dirs, files in os.walk(root):
                dirs[:] = [name for name in dirs if name not in {".git", "node_modules", ".venv", "__pycache__"}]
                for name in files:
                    if fnmatch.fnmatch(name, pattern):
                        matches.append(str(Path(current) / name))
                        if len(matches) >= maximum:
                            break
                if len(matches) >= maximum:
                    break
            return _success(tool_id, "\n".join(matches) or "No matching files.", started)

        if tool_id == "local.run_command":
            command = data.get("command")
            if (
                not isinstance(command, list)
                or not command
                or any(not isinstance(part, str) for part in command)
            ):
                raise ValueError("command must be a non-empty array of strings")
            timeout = data.get("timeout", 120)
            if isinstance(timeout, bool) or not isinstance(timeout, int):
                raise ValueError("timeout must be an integer")
            timeout = max(1, min(timeout, MAX_COMMAND_TIMEOUT))
            cwd_value = data.get("cwd") or os.environ.get("ORACLE_WORKSPACE") or str(Path.home())
            cwd = _path(cwd_value, "cwd")
            if not cwd.is_dir():
                raise ValueError(f"working directory does not exist: {cwd}")
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                shell=False,
            )
            output = (
                f"$ {' '.join(command)}\n"
                f"exit_code={completed.returncode}\n"
                f"--- stdout ---\n{completed.stdout}\n"
                f"--- stderr ---\n{completed.stderr}"
            )
            result = _success(tool_id, _clip(output), started)
            result["exit_code"] = completed.returncode
            return result

        if tool_id == "local.open_app":
            application = data.get("application")
            if not isinstance(application, str) or not application.strip():
                raise ValueError("application must be a non-empty name")
            completed = subprocess.run(
                ["open", "-a", application.strip()],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                shell=False,
            )
            output = completed.stdout or completed.stderr or f"open exit_code={completed.returncode}"
            result = _success(tool_id, _clip(output), started)
            result["exit_code"] = completed.returncode
            return result

        raise ValueError(f"unknown local tool: {tool_id}")

    except subprocess.TimeoutExpired:
        return {
            "name": tool_id,
            "status": "timeout",
            "result": f"Command timed out after {MAX_COMMAND_TIMEOUT} seconds or less.",
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    except Exception as exc:
        return {
            "name": tool_id,
            "status": "error",
            "result": f"{type(exc).__name__}: {exc}",
            "duration_seconds": round(time.monotonic() - started, 3),
        }


def _success(tool_id: str, output: str, started: float) -> dict[str, Any]:
    return {
        "name": tool_id,
        "status": "success",
        "result": output,
        "duration_seconds": round(time.monotonic() - started, 3),
    }
