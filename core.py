"""
core.py — Privilege management, logging, subprocess execution.
"""
from __future__ import annotations
import os
import shutil
import sys
import time
import logging
import subprocess
from pathlib import Path

LOG_FILE = Path("/var/log/anykali.log")
_DRY_RUN = False   # global dry-run state, toggled by CLI arg parser


def set_dry_run(value: bool) -> None:
    global _DRY_RUN
    _DRY_RUN = value


def is_dry_run() -> bool:
    return _DRY_RUN


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("anykali")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    try:
        fh = logging.FileHandler(LOG_FILE)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except PermissionError:
        print("[!] Warning: Unable to open log file for writing. Logging to file disabled.", file=sys.stderr)
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.WARNING)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


log = setup_logging()


def require_root() -> None:
    if _DRY_RUN:
        return
    if os.geteuid() != 0:
        print("[*] Root privileges required. Re-launching with sudo...")
        try:
            os.execvp("sudo", ["sudo", sys.executable] + sys.argv)
        except FileNotFoundError:
            sys.exit("[!] sudo not found. Please run as root.")
        except OSError as e:
            sys.exit(f"[!] Failed to execute sudo: {e}")


# ── Package manager lock handling ─────────────────────────────────────────────
_LOCK_WAIT     = 10   # seconds between retries
_LOCK_WAIT_MAX = 120  # seconds before force-kill

_PM_LOCKS: dict[str, list[Path]] = {
    "apt":    [Path("/var/lib/dpkg/lock-frontend"),
               Path("/var/lib/dpkg/lock"),
               Path("/var/lib/apt/lists/lock")],
    "pacman": [Path("/var/lib/pacman/db.lck")],
    "dnf":    [Path("/var/run/dnf.pid"),
               Path("/var/cache/dnf/metadata_lock.pid")],
    "zypper": [Path("/var/run/zypp-rpm.pid"),
               Path("/var/run/zypp.pid")],
}


def _pm_for_cmd(cmd0: str) -> str | None:
    if cmd0 in ("apt-get", "apt"):  return "apt"
    if cmd0 == "pacman":            return "pacman"
    if cmd0 == "dnf":               return "dnf"
    if cmd0 == "zypper":            return "zypper"
    return None


def _lock_pids(locks: list[Path]) -> list[int]:
    import shutil
    if not shutil.which("fuser"):
        return []
    pids: list[int] = []
    for lock in locks:
        if not lock.exists():
            continue
        r = subprocess.run(["fuser", str(lock)], capture_output=True, text=True)
        for p in r.stdout.split():
            try:
                pids.append(int(p))
            except ValueError:
                pass
    return list(set(pids))


def _pm_locked(locks: list[Path]) -> bool:
    import fcntl
    for lock in locks:
        if not lock.exists():
            continue
        if lock.suffix == ".pid":
            try:
                pid = int(lock.read_text().strip())
                os.kill(pid, 0)
                return True
            except (ValueError, OSError):
                pass
            continue
        # If fuser is available and reports no PIDs, the file is stale — not locked.
        if _has_fuser() and not _lock_pids([lock]):
            continue
        try:
            with open(lock, "rb") as fh:
                fcntl.lockf(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.lockf(fh, fcntl.LOCK_UN)
        except (OSError, IOError):
            return True
    return False


def _has_fuser() -> bool:
    import shutil
    return bool(shutil.which("fuser"))


def _apt_locked() -> bool:
    """Compatibility shim used by tests."""
    return _pm_locked(_PM_LOCKS["apt"])


def _release_pm_locks(pm: str) -> None:
    import signal
    locks = _PM_LOCKS.get(pm, [])

    # Phase 1: wait politely
    waited = 0
    while waited < _LOCK_WAIT_MAX and _pm_locked(locks):
        pids = _lock_pids(locks)
        print(f"[*] {pm} is locked (PID {pids or '?'}). "
              f"Waiting... ({waited}s/{_LOCK_WAIT_MAX}s)")
        time.sleep(_LOCK_WAIT)
        waited += _LOCK_WAIT

    if not _pm_locked(locks):
        return

    # Phase 2: SIGTERM then SIGKILL
    pids = _lock_pids(locks)
    if pids:
        print(f"[!] Lock still held after {_LOCK_WAIT_MAX}s. Terminating PIDs: {pids}")
        for pid in pids:
            try: os.kill(pid, signal.SIGTERM)
            except ProcessLookupError: pass
        time.sleep(3)
        for pid in _lock_pids(locks):
            try:
                os.kill(pid, signal.SIGKILL)
                log.warning("Force-killed PID %d holding %s lock", pid, pm)
            except ProcessLookupError: pass
        time.sleep(1)

    # Phase 3: remove stale lock files (no live process holds them)
    for lock in locks:
        if not lock.exists():
            continue
        pids = _lock_pids([lock])
        if pids:
            continue  # still held by a live process — leave it
        try:
            lock.unlink()
            log.info("Removed stale lock: %s", lock)
            print(f"[*] Removed stale lock: {lock}")
        except OSError as e:
            log.warning("Could not remove lock %s: %s", lock, e)

    # Phase 4: repair state
    _REPAIR_CMDS: dict[str, list[list[str]]] = {
        "apt":    [["dpkg", "--configure", "-a"]],
        "pacman": [["pacman-db-upgrade"]],
        "dnf":    [["dnf", "clean", "dbcache"]],
        "zypper": [["zypper", "--non-interactive", "refresh"]],
    }
    for repair_cmd in _REPAIR_CMDS.get(pm, []):
        if shutil.which(repair_cmd[0]):
            print(f"[*] Repairing {pm} state...")
            result = subprocess.run(repair_cmd, check=False)
            if result.returncode != 0:
                print(f"[!] Warning: {pm} repair command failed with code {result.returncode}")


def run(
    cmd: list[str],
    check: bool = True,
    capture: bool = False,
    log_output: bool = True,
) -> subprocess.CompletedProcess:
    """
    Execute a command.
    - Dry-run: print and return immediately.
    - log_output=True: tee stdout+stderr to the log file while streaming to terminal.
    - Waits/kills blocking processes if the package manager is locked.
    """
    if not cmd:
        raise ValueError("run() called with empty command list")

    log.debug("RUN: %s", " ".join(cmd))

    if _DRY_RUN:
        print(f"[DRY-RUN] {' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    pm = _pm_for_cmd(cmd[0])
    if pm and _pm_locked(_PM_LOCKS.get(pm, [])):
        _release_pm_locks(pm)
        if _pm_locked(_PM_LOCKS.get(pm, [])):
            sys.exit(f"[!] Could not release {pm} locks. Aborting.")

    if capture:
        try:
            return subprocess.run(  # noqa: S603
                cmd, check=check, capture_output=True, text=True
            )
        except subprocess.CalledProcessError as exc:
            log.error("Command failed (exit %d): %s\nstderr: %s",
                      exc.returncode, " ".join(cmd), exc.stderr)
            raise

    # Stream output to terminal AND log file simultaneously
    try:
        proc = subprocess.Popen(  # noqa: S603
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
    except FileNotFoundError:
        log.error("Command not found: %s", cmd[0])
        raise
    try:
        output_lines: list[str] = []
        if proc.stdout is not None:
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                if log_output:
                    output_lines.append(line.rstrip())
        proc.wait()
        if log_output and output_lines:
            log.debug("OUTPUT [%s]:\n%s", cmd[0], "\n".join(output_lines))
        if check and proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)
        return subprocess.CompletedProcess(cmd, proc.returncode)
    except subprocess.CalledProcessError:
        log.error("Command failed (exit %d): %s", proc.returncode, " ".join(cmd))
        raise


def check_deps(tools: list[str]) -> None:
    """Abort with a clear message if any required system binary is missing."""
    import shutil
    missing = [t for t in tools if not shutil.which(t)]
    if missing:
        sys.exit(f"[!] Missing required system utilities: {', '.join(missing)}\n"
                 f"    Please install them and re-run ANYKALI.")
