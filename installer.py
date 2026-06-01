"""
installer.py — Safe install/remove wrapper for all supported package managers.
"""
from __future__ import annotations
import subprocess
from core import log, run, is_dry_run
from os_detector import OSInfo

META_PACKAGES = {
    "everything": "kali-linux-everything",
    "large":      "kali-linux-large",
    "default":    "kali-linux-default",
    "headless":   "kali-linux-headless",
}


def _distrobox_container_exists() -> bool:
    """Check if the kali-anykali distrobox container exists."""
    if is_dry_run():
        return True
    import shutil
    if not shutil.which("distrobox"):
        return False
    try:
        r = subprocess.run(
            ["distrobox", "list"], capture_output=True, text=True, check=False
        )
        return "kali-anykali" in r.stdout
    except OSError:
        return False


def _apt_install(packages: list[str]) -> None:
    # -t kali-rolling overrides priority 50 for explicitly named packages only.
    # --no-install-recommends prevents pulling large optional dep trees.
    run(["apt-get", "install", "-y", "--no-install-recommends",
         "-t", "kali-rolling"] + packages)


def _apt_remove(packages: list[str], purge: bool = False) -> None:
    run(["apt-get", "purge" if purge else "remove", "-y"] + packages)
    run(["apt-get", "autoremove", "-y"])


def _pacman_install(packages: list[str]) -> None:
    run(["pacman", "-S", "--noconfirm", "--needed"] + packages)


def _pacman_remove(packages: list[str]) -> None:
    run(["pacman", "-Rns", "--noconfirm"] + packages)


def _dnf_install(packages: list[str]) -> None:
    run(["dnf", "install", "-y"] + packages)


def _dnf_remove(packages: list[str]) -> None:
    run(["dnf", "remove", "-y"] + packages)


def _zypper_install(packages: list[str]) -> None:
    run(["zypper", "--non-interactive", "install"] + packages)


def _zypper_remove(packages: list[str]) -> None:
    run(["zypper", "--non-interactive", "remove"] + packages)


def _distrobox_install(packages: list[str]) -> None:
    if not _distrobox_container_exists():
        log.error("distrobox container 'kali-anykali' not found")
        print("[!] Error: distrobox container 'kali-anykali' not found")
        return
    for pkg in packages:
        run(["distrobox", "enter", "kali-anykali", "--",
             "sudo", "apt-get", "install", "-y", "--no-install-recommends", pkg])
        run(["distrobox-export", "--bin", f"/usr/bin/{pkg}",
             "--export-path", "/usr/local/bin"], check=False)


def _distrobox_remove(packages: list[str]) -> None:
    if not _distrobox_container_exists():
        log.warning("distrobox container 'kali-anykali' not found, skipping remove")
        return
    for pkg in packages:
        result = run(["distrobox", "enter", "kali-anykali", "--",
                      "sudo", "apt-get", "purge", "-y", pkg], capture=True, check=False)
        if result.returncode != 0:
            log.warning("Failed to remove package '%s' from distrobox: %s",
                        pkg, result.stderr.strip() or "unknown error")


def install(packages: list[str], os_info: OSInfo) -> None:
    log.info("Installing: %s", packages)
    match os_info.family:
        case "debian":  _apt_install(packages)
        case "arch":    _pacman_install(packages)
        case "fedora":  _dnf_install(packages)
        case "suse":    _zypper_install(packages)
        case _:         _distrobox_install(packages)


def remove(packages: list[str], os_info: OSInfo, purge: bool = False) -> None:
    log.info("Removing: %s", packages)
    match os_info.family:
        case "debian":  _apt_remove(packages, purge)
        case "arch":    _pacman_remove(packages)
        case "fedora":  _dnf_remove(packages)
        case "suse":    _zypper_remove(packages)
        case _:         _distrobox_remove(packages)


def install_meta(meta_key: str, os_info: OSInfo) -> None:
    if os_info.family == "debian":
        pkg = META_PACKAGES.get(meta_key, META_PACKAGES["default"])
        log.info("Installing meta-package: %s", pkg)
        _apt_install([pkg])
    elif os_info.family == "arch":
        _pacman_install(["blackarch"])
    else:
        _distrobox_install(["kali-linux-default"])
