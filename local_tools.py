"""
local_tools.py — Mac-local tools for Oracle's full user-account capability mode.

Tools run as the currently logged-in macOS user. They do not elevate to root
or bypass macOS privacy prompts/TCC permissions.
"""

from __future__ import annotations

import fnmatch
import json
from datetime import datetime, timezone
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


MAX_COMMAND_TIMEOUT = 300
MAX_FILE_READ_BYTES = 2 * 1024 * 1024
MAX_FILE_WRITE_BYTES = 2 * 1024 * 1024
MAX_TOOL_OUTPUT = 12000
BLOCKED_COMMAND_MARKERS = (
    "sudo", "doas", "csrutil", "tccutil", "spctl", "profiles",
    "parental control", "parental-control", "screentime", "screen time",
    "familycontrols", "age restriction", "age verification",
)
PROTECTED_PATH_MARKERS = (
    "screentime", "screen time", "parental", "familycontrols",
    "managed preferences", "configurationprofiles",
)

ALLOWED_COMMANDS = {
    "git": {"status", "diff", "log", "branch", "show", "rev-parse", "ls-files",
            "grep", "check-ignore", "add", "commit", "switch", "checkout", "fetch", "pull", "tag"},
    "npm": {"--version", "-v", "test", "run"},
    "node": {"--version", "-v"},
    "go": {"version", "test", "vet", "fmt", "build", "list"},
    "ollama": {"version", "list", "ps", "show", "run", "pull"},
    "brew": {"list", "info"},
}
ALLOWED_PYTHON_MODULES = {"pytest", "compileall", "unittest"}


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
    {
        "tool_id": "local.get_system_info",
        "name": "Inspect Mac system",
        "description": "قراءة معلومات النظام والموارد الأساسية دون تغيير إعدادات الجهاز.",
        "input_schema": {},
    },
    {
        "tool_id": "local.list_processes",
        "name": "List running processes",
        "description": "عرض قائمة محدودة بالعمليات دون سطر الأوامر أو معاملات قد تحتوي أسرارًا.",
        "input_schema": {"max_results": "integer?"},
    },
    {
        "tool_id": "local.list_applications",
        "name": "List installed applications",
        "description": "عرض أسماء تطبيقات macOS الموجودة في مجلدات التطبيقات القياسية.",
        "input_schema": {},
    },
    {
        "tool_id": "local.get_mac_intelligence_status",
        "name": "Mac Intelligence policy status",
        "description": "عرض مساحات العمل الموثوقة والأدوات المسموح بتشغيلها تلقائيًا.",
        "input_schema": {},
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



def _validate_command(command: list[str]) -> None:
    """Allow common development commands without exposing an unrestricted shell."""
    executable = Path(command[0]).name.casefold()
    args = command[1:]
    if executable.startswith("python"):
        if len(args) >= 2 and args[0] == "-m":
            module = args[1]
            if module in ALLOWED_PYTHON_MODULES:
                return
            if module == "pip" and len(args) >= 3 and args[2] in {"list", "show", "check"}:
                return
        raise PermissionError(
            "Only test, compile and Python package-inspection commands are available to the agent."
        )
    if executable in ALLOWED_COMMANDS:
        if args and args[0] in ALLOWED_COMMANDS[executable]:
            if executable == "npm" and args[0] == "run":
                if len(args) >= 2 and args[1] in {"test", "lint", "build", "typecheck"}:
                    return
            elif executable == "git" and args[0] in {"commit", "add", "switch", "checkout"}:
                return
            elif executable != "npm":
                return
        raise PermissionError(f"Command is not enabled for local agent execution: {executable}")
    raise PermissionError(
        "This executable is not enabled for autonomous command execution. "
        "Use Oracle's file and application tools or run the command yourself."
    )



def _execute_unchecked(tool_id: str, tool_input: str | dict) -> dict[str, Any]:
    """Execute a named local capability as the current macOS user."""
    data = _payload(tool_input)
    started = time.monotonic()
    try:
        if tool_id == "local.list_directory":
            target = _path(data.get("path"))
            _reject_protected_path(target)
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
            _reject_protected_path(target)
            size = target.stat().st_size
            if size > MAX_FILE_READ_BYTES:
                raise ValueError(f"file is larger than {MAX_FILE_READ_BYTES} bytes")
            output = target.read_text(encoding="utf-8", errors="replace")
            return _success(tool_id, _clip(output), started)

        if tool_id == "local.write_file":
            target = _path(data.get("path"))
            _reject_protected_path(target)
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
            _reject_protected_path(source)
            _reject_protected_path(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            return _success(tool_id, f"Moved {source} to {destination}", started)

        if tool_id == "local.delete_path":
            target = _path(data.get("path"))
            _reject_protected_path(target)
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
            _reject_protected_path(root)
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
            command_text = " ".join(command).casefold()
            blocked = next((marker for marker in BLOCKED_COMMAND_MARKERS if marker in command_text), None)
            if blocked:
                raise PermissionError(
                    "This command targets system or age-safety protections and is not available to Oracle."
                )
            _validate_command(command)
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

        if tool_id == "local.get_system_info":
            usage = shutil.disk_usage(Path.home())
            info = {
                "os": platform.system(),
                "os_release": platform.release(),
                "architecture": platform.machine(),
                "python_version": platform.python_version(),
                "cpu_count": os.cpu_count(),
                "home_disk_total_bytes": usage.total,
                "home_disk_free_bytes": usage.free,
            }
            return _success(tool_id, json.dumps(info, ensure_ascii=False, indent=2), started)

        if tool_id == "local.list_processes":
            maximum = data.get("max_results", 200)
            if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 300:
                raise ValueError("max_results must be from 1 to 300")
            completed = subprocess.run(
                ["/bin/ps", "-axo", "pid=,ppid=,user=,stat=,comm="],
                capture_output=True, text=True, timeout=10, check=False, shell=False,
            )
            if completed.returncode != 0:
                raise RuntimeError("Process inventory command failed.")
            rows = []
            for line in completed.stdout.splitlines()[:maximum]:
                parts = line.strip().split(None, 4)
                if len(parts) == 5:
                    rows.append({"pid": parts[0], "parent_pid": parts[1], "user": parts[2],
                                 "state": parts[3], "executable": parts[4]})
            return _success(tool_id, json.dumps(rows, ensure_ascii=False, indent=2), started)

        if tool_id == "local.list_applications":
            roots = [Path("/Applications"), Path("/System/Applications"), Path.home() / "Applications"]
            applications = set()
            for root in roots:
                if root.is_dir():
                    try:
                        applications.update(item.name[:-4] for item in root.iterdir() if item.is_dir() and item.name.endswith(".app"))
                    except OSError:
                        continue
            return _success(tool_id, json.dumps(sorted(applications, key=str.casefold), ensure_ascii=False, indent=2), started)

        if tool_id == "local.get_mac_intelligence_status":
            import mac_intelligence
            return _success(tool_id, json.dumps(mac_intelligence.get_status(), ensure_ascii=False, indent=2), started)

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



def _reject_protected_path(target: Path) -> None:
    normalized = str(target).casefold().replace("_", " ")
    if any(marker in normalized for marker in PROTECTED_PATH_MARKERS):
        raise PermissionError(
            "This path is related to system or age-safety protections and is not available to Oracle."
        )


def _append_audit(tool_id: str, result: dict[str, Any]) -> None:
    """Keep a private, content-free audit trail of local tool execution."""
    try:
        audit_dir = Path(os.environ.get(
            "ORACLE_AUDIT_DIR",
            str(Path.home() / ".personal_ai_oracle" / "logs"),
        )).expanduser()
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_file = audit_dir / "local-actions.jsonl"
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool_id": tool_id,
            "status": str(result.get("status", "unknown")),
            "duration_seconds": result.get("duration_seconds"),
        }
        with audit_file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        os.chmod(audit_file, 0o600)
    except OSError:
        return


MUTATING_TOOLS = frozenset({
    "local.write_file", "local.move_path", "local.delete_path",
    "local.run_command", "local.open_app",
})


def _validate_command_before_authorization(tool_input: str | dict) -> None:
    """Reject malformed or explicitly blocked commands before creating approval requests."""
    data = _payload(tool_input)
    command = data.get("command")
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(part, str) for part in command)
    ):
        raise ValueError("command must be a non-empty array of strings")
    command_text = " ".join(command).casefold()
    blocked = next((marker for marker in BLOCKED_COMMAND_MARKERS if marker in command_text), None)
    if blocked:
        raise PermissionError(
            "This command targets system or age-safety protections and is not available to Oracle."
        )
    _validate_command(command)


def _execute(
    tool_id: str,
    tool_input: str | dict,
    *,
    execution_grant: str | None = None,
) -> dict[str, Any]:
    """Enforce the owner policy at the local execution boundary, including direct callers."""
    if tool_id not in MUTATING_TOOLS:
        return _execute_unchecked(tool_id, tool_input)

    try:
        payload = _payload(tool_input)
        if tool_id == "local.run_command":
            _validate_command_before_authorization(payload)
        import execution_policy

        scope = (
            os.environ.get("ORACLE_MEMORY_SCOPE")
            or os.environ.get("ORACLE_WORKFLOW_SCOPE")
            or "user:oracle-owner"
        ).strip()
        if execution_grant is None:
            authorization = execution_policy.authorize_action(
                tool_id, payload, scope=scope
            )
            if not authorization.get("allowed"):
                if authorization.get("reason") == "human_approval_required":
                    return {
                        "name": tool_id,
                        "status": "awaiting_approval",
                        "result": "Paused before the local action. Approve this exact operation in Oracle Control Center, then retry or resume the task.",
                        "approval_id": authorization.get("approval_id", ""),
                        "action_digest": authorization.get("action_digest", ""),
                        "preview": authorization.get("preview", {}),
                    }
                return {
                    "name": tool_id,
                    "status": "blocked",
                    "result": "The local execution policy did not authorize this operation.",
                }
            execution_grant = authorization.get("execution_grant")
        if not execution_policy.consume_execution_grant(
            execution_grant or "", tool_id, payload, scope=scope
        ):
            return {
                "name": tool_id,
                "status": "blocked",
                "result": "The local execution grant is missing, expired, already used, or does not match this exact operation.",
            }
        return _execute_unchecked(tool_id, payload)
    except Exception as exc:
        return {
            "name": tool_id,
            "status": "error",
            "result": f"{type(exc).__name__}: {exc}",
        }


def execute(
    tool_id: str,
    tool_input: str | dict,
    *,
    execution_grant: str | None = None,
) -> dict[str, Any]:
    """Run a policy-checked local tool and append a content-free audit record."""
    result = _execute(tool_id, tool_input, execution_grant=execution_grant)
    _append_audit(tool_id, result)
    return result



def _success(tool_id: str, output: str, started: float) -> dict[str, Any]:
    return {
        "name": tool_id,
        "status": "success",
        "result": output,
        "duration_seconds": round(time.monotonic() - started, 3),
    }
