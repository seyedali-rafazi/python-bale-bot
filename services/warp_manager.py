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
        # مرحله اول: Disconnect (حتی اگر خطا داد رد می‌شویم)
        code, out, err = run_cmd(["warp-cli", "disconnect"])
        print(f"[WARP] CMD: warp-cli disconnect")
        print(f"[WARP] code={code}, out={out}, err={err}")

        # مرحله دوم: Delete (از خطای نبودن اکانت چشم‌پوشی می‌کنیم)
        code, out, err = run_cmd(["warp-cli", "registration", "delete"])
        print(f"[WARP] CMD: warp-cli registration delete")
        print(f"[WARP] code={code}, out={out}, err={err}")
        # اگر خطایی غیر از "Missing registration" بود خارج شو
        if code != 0 and "Missing registration" not in err:
            return False

        # مراحل بعدی: این مراحل باید با موفقیت اجرا شوند
        remaining_steps = [
            ["warp-cli", "registration", "new"],
            ["warp-cli", "mode", "proxy"],
            ["warp-cli", "connect"],
        ]

        for step in remaining_steps:
            code, out, err = run_cmd(step)
            print(f"[WARP] CMD: {' '.join(step)}")
            print(f"[WARP] code={code}, out={out}, err={err}")
            if code != 0:
                return False

        return wait_for_warp(timeout=20)
