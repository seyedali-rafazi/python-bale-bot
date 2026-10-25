# services/chromium_maintenance.py
"""
Periodic Chromium cleanup so you do not need manual `killall chrome`.

- Restarts the shared Playwright browser on a schedule (frees RSS growth).
- Reaps leftover headless Chrome/Chromium processes (Playwright / SingleFile orphans).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from typing import List, Tuple

from services.chromium_workload import heavy_chromium_semaphore
from services.playwright_browser_manager import get_browser_manager

logger = logging.getLogger(__name__)

_MAINTENANCE_INTERVAL_SEC = max(
    300, int(os.getenv("CHROMIUM_MAINTENANCE_INTERVAL_SEC", "2700"))
)
_MAINTENANCE_ENABLED = os.getenv("CHROMIUM_MAINTENANCE_ENABLED", "1").strip().lower() in (
    "1",
    "true",
    "yes",
)
_SEMAPHORE_WAIT_SEC = max(
    30, int(os.getenv("CHROMIUM_MAINTENANCE_WAIT_SEC", "120"))
)

# Only touch processes that look like headless automation (not a desktop Chrome session).
_HEADLESS_MARKERS = (
    "--headless",
    "headless-shell",
    "ms-playwright",
    "playwright",
    "single-file",
    "single_file",
)


def _is_headless_bot_process(cmdline: str) -> bool:
    lower = cmdline.lower()
    if "chrom" not in lower and "chrome" not in lower:
        return False
    return any(m in lower for m in _HEADLESS_MARKERS)


def _parse_ps_linux() -> List[Tuple[int, int, str]]:
    """Return (pid, elapsed_seconds, cmdline) for processes."""
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid,etimes,args", "--no-headers"],
            text=True,
            timeout=15,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return []

    rows: List[Tuple[int, int, str]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^\s*(\d+)\s+(\d+)\s+(.+)$", line)
        if not m:
            continue
        pid, etimes, cmd = int(m.group(1)), int(m.group(2)), m.group(3)
        rows.append((pid, etimes, cmd))
    return rows


def _parse_tasklist_windows() -> List[Tuple[int, int, str]]:
    """
    Return (pid, elapsed_seconds, cmdline) for Chrome processes on Windows.
    Queries Win32_Process via PowerShell to accurately inspect process age and commandline.
    If process age cannot be determined, it is set to -1 so it is never reaped blindly.
    """
    ps_cmd = (
        "$now = [DateTime]::UtcNow; "
        "Get-CimInstance Win32_Process -Filter \"Name like '%chrome%'\" | "
        "ForEach-Object { "
        "  $age = if ($_.CreationDate) { [int]($now - $_.CreationDate.ToUniversalTime()).TotalSeconds } else { -1 }; "
        "  [PSCustomObject]@{ pid = [int]$_.ProcessId; age = $age; cmd = [string]$_.CommandLine } "
        "} | ConvertTo-Json -Compress"
    )

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=creationflags,
        )
        if res.returncode == 0 and res.stdout.strip():
            raw_data = json.loads(res.stdout)
            items = raw_data if isinstance(raw_data, list) else [raw_data]
            rows: List[Tuple[int, int, str]] = []
            for item in items:
                try:
                    pid = int(item.get("pid", 0))
                    age = int(item.get("age", -1))
                    cmd = str(item.get("cmd") or "")
                    if pid > 0:
                        rows.append((pid, age, cmd))
                except (ValueError, TypeError):
                    continue
            return rows
    except Exception as e:
        logger.debug("PowerShell process query failed on Windows: %s", e)

    # Safe fallback: tasklist does not provide creation times or command line,
    # so we assign age=-1 and a generic name without headless markers to avoid accidental kills.
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/FO", "CSV", "/NH"],
            text=True,
            timeout=15,
            creationflags=creationflags,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return []

    fallback_rows: List[Tuple[int, int, str]] = []
    for line in out.splitlines():
        if "chrome.exe" not in line.lower():
            continue
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        fallback_rows.append((pid, -1, "chrome.exe"))
    return fallback_rows


def reap_stale_headless_chromium(
    min_age_seconds: int = 60,
    dry_run: bool = False,
) -> int:
    """
    Terminate old headless Chrome/Chromium processes left behind by Playwright or SingleFile.
    Returns number of processes signalled.
    """
    if sys.platform == "win32":
        processes = _parse_tasklist_windows()
    else:
        processes = _parse_ps_linux()

    my_pid = os.getpid()
    killed = 0

    for pid, etimes, cmd in processes:
        if pid == my_pid or pid <= 1:
            continue
        # Unknown age (< 0) or process younger than minimum age threshold must never be reaped
        if etimes < 0 or etimes < min_age_seconds:
            continue
        if not _is_headless_bot_process(cmd):
            continue

        if dry_run:
            logger.info("Would reap headless chromium pid=%s age=%ss cmd=%s", pid, etimes, cmd[:120])
            killed += 1
            continue

        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    check=False,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                os.kill(pid, 15)
            killed += 1
            logger.info("Reaped stale headless chromium pid=%s", pid)
        except ProcessLookupError:
            pass
        except OSError as e:
            logger.warning("Could not reap pid=%s: %s", pid, e)

    return killed


async def run_chromium_maintenance_once() -> None:
    """Restart Playwright browser and reap orphans (serialized with other Chromium work)."""
    try:
        await asyncio.wait_for(
            heavy_chromium_semaphore.acquire(),
            timeout=_SEMAPHORE_WAIT_SEC,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "Chromium maintenance skipped: heavy workload busy for %ss",
            _SEMAPHORE_WAIT_SEC,
        )
        return

    try:
        logger.info("Chromium maintenance: restarting Playwright browser")
        await get_browser_manager().force_restart()
    finally:
        heavy_chromium_semaphore.release()

    reaped = await asyncio.to_thread(reap_stale_headless_chromium, 90)
    if reaped:
        logger.info("Chromium maintenance: reaped %s stale process(es)", reaped)


async def chromium_maintenance_loop() -> None:
    if not _MAINTENANCE_ENABLED:
        logger.info("Chromium periodic maintenance disabled (CHROMIUM_MAINTENANCE_ENABLED)")
        return

    logger.info(
        "Chromium maintenance loop started (every %ss)",
        _MAINTENANCE_INTERVAL_SEC,
    )
    await asyncio.sleep(60)

    while True:
        try:
            await run_chromium_maintenance_once()
        except Exception:
            logger.exception("Chromium maintenance cycle failed")
        await asyncio.sleep(_MAINTENANCE_INTERVAL_SEC)
