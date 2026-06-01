"""
launcher.py — Locate and launch installed tools from the CLI.
"""
from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path

from core import log, is_dry_run

EXTRA_PATHS = ["/usr/sbin", "/sbin", "/usr/local/bin", "/opt/kali/bin"]

# Tools known to require root to be useful (non-exhaustive; checked at launch)
_ROOT_TOOLS = {
    "nmap", "masscan", "tcpdump", "wireshark", "aircrack-ng", "wifite",
    "reaver", "ettercap", "bettercap", "responder", "netdiscover",
}

# Tools that open a GUI window
_GUI_TOOLS = {
    "wireshark", "burpsuite", "zaproxy", "maltego", "autopsy",
    "fern-wifi-cracker", "legion", "ghidra", "jadx",
}


def find_binary(tool: str) -> Path | None:
    found = shutil.which(tool)
    if found:
        return Path(found)
    for prefix in EXTRA_PATHS:
        candidate = Path(prefix) / tool
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def launch(tool: str) -> None:
    if is_dry_run():
        print(f"[DRY-RUN] launch {tool}")
        return

    binary = find_binary(tool)
    if binary is None:
        print(f"[!] '{tool}' not found in PATH. Is it installed?")
        return

    # GUI check — warn before attempting to open a window over SSH/headless
    if tool in _GUI_TOOLS and not _has_display():
        print(f"[!] '{tool}' is a GUI application but no display server was detected.")
        print("    Set $DISPLAY or $WAYLAND_DISPLAY, or use X11 forwarding (ssh -X).")
        ans = input("    Launch anyway? [y/N]: ").strip().lower()
        if ans != "y":
            return

    # Root check — warn if tool likely needs root and we're not root
    if tool in _ROOT_TOOLS and os.geteuid() != 0:
        print(f"[!] '{tool}' typically requires root privileges to function correctly.")
        ans = input("    Launch anyway as current user? [y/N]: ").strip().lower()
        if ans != "y":
            return

    log.info("Launching %s (%s)", tool, binary)
    try:
        subprocess.run([str(binary)], check=False)  # noqa: S603
    except KeyboardInterrupt:
        pass


def is_installed(tool: str) -> bool:
    return find_binary(tool) is not None
