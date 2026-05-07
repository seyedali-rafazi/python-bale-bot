# services/warp_manager.py

import subprocess
import time
import threading

_lock = threading.Lock()


def run_cmd(args):
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def wait_for_warp(timeout=20):
    start = time.time()
    while time.time() - start < timeout:
        code, out, err = run_cmd(["warp-cli", "status"])
        status_text = f"{out}\n{err}".lower()

        if code == 0 and "connected" in status_text and "connecting" not in status_text:
            return True

        time.sleep(2)
    return False


def rotate_warp_registration():
    with _lock:
        steps = [
            ["warp-cli", "disconnect"],
            ["warp-cli", "registration", "delete"],
            ["warp-cli", "registration", "new"],
            ["warp-cli", "mode", "proxy"],
            ["warp-cli", "connect"],
        ]

        for step in steps:
            code, out, err = run_cmd(step)
            print(f"[WARP] CMD: {' '.join(step)}")
            print(f"[WARP] code={code}, out={out}, err={err}")
            if code != 0:
                return False

        return wait_for_warp(timeout=20)
