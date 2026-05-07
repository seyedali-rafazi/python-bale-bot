import subprocess
import time
import threading

_lock = threading.Lock()


def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def rotate_warp_registration():
    with _lock:
        steps = [
            "warp-cli disconnect",
            "warp-cli registration delete",
            "warp-cli registration new",
            "warp-cli mode proxy",
            "warp-cli connect",
        ]

        for step in steps:
            code, out, err = run_cmd(step)
            print(f"[WARP] CMD: {step}")
            print(f"[WARP] code={code}, out={out}, err={err}")
            if code != 0:
                return False

        time.sleep(3)
        return True
