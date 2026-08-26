"""Cross-platform desktop notification dispatcher."""

import platform
import subprocess
import shutil
from typing import Optional


def notify(
    title: str,
    message: str,
    icon: str = "audio-headphones",
    app_name: str = "Scout",
):
    system = platform.system().lower()

    if system == "linux":
        if shutil.which("notify-send"):
            try:
                cmd = ["notify-send", "-a", app_name, "-i", icon, title, message]
                subprocess.run(cmd, capture_output=True, timeout=3)
            except Exception:
                pass
    elif system == "darwin":
        try:
            script = f'display notification "{message}" with title "{title}" subtitle "{app_name}"'
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=3)
        except Exception:
            pass
    else:
        # Fallback or Windows
        pass
