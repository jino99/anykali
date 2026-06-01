"""
repo_manager.py — Safe repo/GPG/pinning management with backup & rollback.
"""
from __future__ import annotations
import os
import shutil
import tempfile
import time
from pathlib import Path

from core import log, run, is_dry_run
from os_detector import OSInfo

# ── Kali repo constants ────────────────────────────────────────────────────────
KALI_KEYRING_URL  = "https://archive.kali.org/archive-key.asc"
KALI_KEYRING_PATH = Path("/etc/apt/keyrings/kali-archive-keyring.asc")
KALI_SOURCES_FILE = Path("/etc/apt/sources.list.d/kali-rolling.list")
KALI_PREFS_FILE   = Path("/etc/apt/preferences.d/kali-pinning")

KALI_SOURCES_CONTENT = (
    f"deb [signed-by={KALI_KEYRING_PATH}] "
    "http://http.kali.org/kali kali-rolling main contrib non-free non-free-firmware\n"
)

# Three independent pins — belt, suspenders, and a second belt:
#   o=Kali   matches the Origin field
#   l=Kali   matches the Label field
#   a=kali-rolling matches the Suite/Codename
# Priority 50: below 100 (installed), below 500 (default candidate).
# apt upgrade will NEVER pull from Kali. Only explicit -t kali-rolling installs work.
KALI_PINNING_CONTENT = """\
# APT Pinning: prevent Kali packages from overwriting host packages.
# Priority 50 < 100 (installed) < 500 (default candidate).
# 'apt upgrade' will never touch Kali packages.
Package: *
Pin: release o=Kali
Pin-Priority: 50

Package: *
Pin: release l=Kali
Pin-Priority: 50

Package: *
Pin: release a=kali-rolling
Pin-Priority: 50
"""

BLACKARCH_STRAP_URL = "https://blackarch.org/strap.sh"


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    ts = time.time_ns()
    backup = path.with_suffix(f".bak_{ts}")
    shutil.copy2(path, backup)
    log.info("Backed up %s → %s", path, backup)
    return backup


def _write(path: Path, content: str) -> None:
    if is_dry_run():
        print(f"[DRY-RUN] write {path}")
        log.debug("DRY-RUN write: %s", path)
    else:
        tmp_path = path.with_suffix(f".tmp_{time.time_ns()}")
        tmp_path.write_text(content)
        os.replace(tmp_path, path)


def _unlink(path: Path) -> None:
    if is_dry_run():
        print(f"[DRY-RUN] unlink {path}")
    elif path.exists():
        path.unlink()


# ── Debian/Ubuntu ──────────────────────────────────────────────────────────────

def add_kali_repo_debian() -> None:
    """
    Import GPG key → write sources → write pinning → apt-get update.
    Rolls back sources+pinning if any step fails.
    """
    KALI_KEYRING_PATH.parent.mkdir(parents=True, exist_ok=True)

    log.info("Importing Kali GPG key...")
    try:
        run(["curl", "-fsSL", KALI_KEYRING_URL, "-o", str(KALI_KEYRING_PATH)])
    except Exception:
        # Key download failed — clean up partial file and abort
        if KALI_KEYRING_PATH.exists():
            KALI_KEYRING_PATH.unlink()
        raise RuntimeError(
            "Failed to download Kali GPG key. "
            "Check your internet connection. No changes were made."
        )

    # Validate key is non-empty (curl -f exits 0 even on some errors)
    if not is_dry_run() and (
        not KALI_KEYRING_PATH.exists() or KALI_KEYRING_PATH.stat().st_size < 100
    ):
        KALI_KEYRING_PATH.unlink(missing_ok=True)
        raise RuntimeError("Downloaded GPG key appears corrupt. Aborting.")

    _backup(KALI_SOURCES_FILE)
    _backup(KALI_PREFS_FILE)

    try:
        _write(KALI_SOURCES_FILE, KALI_SOURCES_CONTENT)
        _write(KALI_PREFS_FILE, KALI_PINNING_CONTENT)
        run(["apt-get", "update", "-qq"])
    except Exception:
        log.error("apt-get update failed — rolling back repo files.")
        _unlink(KALI_SOURCES_FILE)
        _unlink(KALI_PREFS_FILE)
        _unlink(KALI_KEYRING_PATH)
        raise

    log.info("Kali repo configured with APT pinning (priority 50).")


def remove_kali_repo_debian() -> None:
    for path in (KALI_SOURCES_FILE, KALI_PREFS_FILE, KALI_KEYRING_PATH):
        existed = path.exists()
        _unlink(path)
        if existed or is_dry_run():
            log.info("Removed %s", path)
    run(["apt-get", "update", "-qq"])
    log.info("Kali repo purged from host.")


# ── Arch / BlackArch ───────────────────────────────────────────────────────────

def add_blackarch_repo() -> None:
    log.info("Fetching BlackArch strap script...")
    import os as _os
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".sh", delete=False) as tmp:
            tmp_path = tmp.name
        run(["curl", "-fsSL", BLACKARCH_STRAP_URL, "-o", tmp_path])
        run(["chmod", "+x", tmp_path])
        run(["bash", tmp_path])
        log.info("BlackArch repo added.")
    finally:
        if tmp_path and _os.path.exists(tmp_path):
            try:
                _os.unlink(tmp_path)
            except Exception:
                log.warning("Failed to remove temporary file %s", tmp_path)


def remove_blackarch_repo() -> None:
    pacman_conf = Path("/etc/pacman.conf")
    if not pacman_conf.exists():
        log.warning("pacman.conf not found — skipping BlackArch removal.")
        return
    _backup(pacman_conf)
    lines = pacman_conf.read_text().splitlines()
    cleaned, skip = [], False
    for line in lines:
        if line.strip() in ("[blackarch]", "[blackarch-testing]"):
            skip = True
        elif skip and line.startswith("["):
            skip = False
        if not skip:
            cleaned.append(line)
    _write(pacman_conf, "\n".join(cleaned) + "\n")
    log.info("BlackArch repo removed from pacman.conf.")


# ── Fedora / openSUSE — Distrobox fallback ────────────────────────────────────

def ensure_distrobox(os_info: OSInfo) -> None:
    import shutil as sh
    if sh.which("distrobox"):
        return
    log.info("Installing Distrobox...")
    if os_info.pkg_manager == "dnf":
        run(["dnf", "install", "-y", "distrobox"])
    elif os_info.pkg_manager == "zypper":
        run(["zypper", "--non-interactive", "install", "distrobox"])
    else:
        log.warning(
            "Unknown package manager '%s'. Trying common alternatives...", os_info.pkg_manager
        )
        for pm in ("yum", "pacman", "apt", "apk"):
            if sh.which(pm):
                run([pm, "install", "-y", "distrobox"])
                return
        raise RuntimeError(
            "Could not install Distrobox automatically. "
            "Please install it manually for your package manager."
        )


def create_kali_distrobox() -> None:
    run(["distrobox", "create", "--name", "kali-anykali",
         "--image", "docker.io/kalilinux/kali-rolling", "--yes"])
    log.info("Kali Distrobox container created.")


def remove_kali_distrobox() -> None:
    run(["distrobox", "rm", "--name", "kali-anykali", "--force"], check=False)
    log.info("Kali Distrobox container removed.")


# ── Dispatchers ───────────────────────────────────────────────────────────────

def setup_repos(os_info: OSInfo) -> None:
    if os_info.family == "debian":
        add_kali_repo_debian()
    elif os_info.family == "arch":
        add_blackarch_repo()
    elif os_info.family in ("fedora", "suse"):
        ensure_distrobox(os_info)
        create_kali_distrobox()
    else:
        raise NotImplementedError(f"Unsupported OS family: {os_info.family}")


def teardown_repos(os_info: OSInfo) -> None:
    if os_info.family == "debian":
        remove_kali_repo_debian()
    elif os_info.family == "arch":
        remove_blackarch_repo()
    elif os_info.family in ("fedora", "suse"):
        remove_kali_distrobox()
    else:
        log.warning("teardown_repos: unsupported OS family '%s' — nothing to remove.", os_info.family)
