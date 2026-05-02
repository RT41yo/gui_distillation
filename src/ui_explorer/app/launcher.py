from __future__ import annotations

import os
import shlex
import subprocess
import time


class AppLauncher:
    def launch(self, launcher: str, display: str, wait_s: float = 2.0) -> subprocess.Popen:
        env = dict(os.environ)
        env["DISPLAY"] = display
        proc = subprocess.Popen(
            shlex.split(launcher),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(wait_s)
        return proc
