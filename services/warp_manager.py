# services/warp_manager.py

import asyncio
import logging
import subprocess
import time
import threading

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_async_lock = asyncio.Lock()


def run_cmd(args, timeout_sec: int = 25):
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"warp-cli command timed out after {timeout_sec}s"


async def async_run_cmd(args, timeout_sec: int = 25):
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_sec
        )
        return (
            proc.returncode if proc.returncode is not None else -1,
            stdout_b.decode("utf-8", errors="replace").strip() if stdout_b else "",
            stderr_b.decode("utf-8", errors="replace").strip() if stderr_b else "",
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
        return -1, "", f"warp-cli command timed out after {timeout_sec}s"


def wait_for_warp(timeout=20):
    start = time.time()
    while time.time() - start < timeout:
        code, out, err = run_cmd(["warp-cli", "status"])
        status_text = f"{out}\n{err}".lower()

        if code == 0 and "connected" in status_text and "connecting" not in status_text:
            return True

        time.sleep(2)
    return False


async def async_wait_for_warp(timeout=20):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        code, out, err = await async_run_cmd(["warp-cli", "status"])
        status_text = f"{out}\n{err}".lower()

        if code == 0 and "connected" in status_text and "connecting" not in status_text:
            return True

        await asyncio.sleep(2)
    return False


def rotate_warp_registration():
    with _lock:
        code, out, err = run_cmd(["warp-cli", "disconnect"])
        logger.debug("[WARP] disconnect code=%s out=%s err=%s", code, out, err)

        code, out, err = run_cmd(["warp-cli", "registration", "delete"])
        logger.debug("[WARP] registration delete code=%s out=%s err=%s", code, out, err)
        if code != 0 and "Missing registration" not in err:
            return False

        remaining_steps = [
            ["warp-cli", "registration", "new"],
            ["warp-cli", "mode", "proxy"],
            ["warp-cli", "connect"],
        ]

        for step in remaining_steps:
            code, out, err = run_cmd(step)
            logger.debug("[WARP] %s code=%s out=%s err=%s", " ".join(step), code, out, err)
            if code != 0:
                return False

        return wait_for_warp(timeout=20)


async def async_rotate_warp_registration():
    async with _async_lock:
        code, out, err = await async_run_cmd(["warp-cli", "disconnect"])
        logger.debug("[WARP] disconnect code=%s out=%s err=%s", code, out, err)

        code, out, err = await async_run_cmd(["warp-cli", "registration", "delete"])
        logger.debug("[WARP] registration delete code=%s out=%s err=%s", code, out, err)
        if code != 0 and "Missing registration" not in err:
            return False

        for step in (
            ["warp-cli", "registration", "new"],
            ["warp-cli", "mode", "proxy"],
            ["warp-cli", "connect"],
        ):
            code, out, err = await async_run_cmd(step)
            logger.debug("[WARP] %s code=%s out=%s err=%s", " ".join(step), code, out, err)
            if code != 0:
                return False

        return await async_wait_for_warp(timeout=20)
