#!/usr/bin/env python3
"""
anykali.py — Entry point. Parses args, checks deps, bootstraps repos, runs CLI.
"""
import sys

if sys.version_info < (3, 10):
    sys.exit("ANYKALI requires Python 3.10+")

import argparse

import core
import os_detector
import repo_manager
import cli

# ── Required system utilities per OS family ───────────────────────────────────
_COMMON_DEPS  = ["curl"]
_DEBIAN_DEPS  = ["curl", "gpg"]
_ARCH_DEPS    = ["curl", "pacman"]
_CONTAINER_DEPS = ["distrobox"]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="anykali",
        description="Kali Linux toolkit installer for any Linux distribution.",
    )
    p.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="Simulate all operations without making any changes.",
    )
    return p.parse_args()


def _check_deps_for_family(family: str) -> None:
    match family:
        case "debian":          core.check_deps(_DEBIAN_DEPS)
        case "arch":            core.check_deps(_ARCH_DEPS)
        case "fedora" | "suse": core.check_deps(_CONTAINER_DEPS)
        case _:                 core.check_deps(_COMMON_DEPS + _CONTAINER_DEPS)


def _blackarch_present() -> bool:
    from pathlib import Path
    p = Path("/etc/pacman.conf")
    try:
        return p.exists() and "[blackarch]" in p.read_text()
    except OSError:
        return False


def _distrobox_container_exists() -> bool:
    import subprocess, shutil
    if not shutil.which("distrobox"):
        return False
    try:
        r = subprocess.run(
            ["distrobox", "list"], capture_output=True, text=True, check=False
        )
        return "kali-anykali" in r.stdout
    except OSError:
        return False


def main() -> None:
    args = _parse_args()

    # Apply dry-run flag globally before anything else runs
    core.set_dry_run(args.dry_run)
    if args.dry_run:
        print("[*] DRY-RUN mode active — no changes will be made.\n")

    core.require_root()
    core.setup_logging()

    os_info = os_detector.detect()

    _check_deps_for_family(os_info.family)

    needs_setup = (
        (os_info.family == "debian" and not repo_manager.KALI_SOURCES_FILE.exists()) or
        (os_info.family == "arch"   and not _blackarch_present()) or
        (os_info.family in ("fedora", "suse") and not _distrobox_container_exists())
    )
    if needs_setup:
        print(f"[*] First run on {os_info.pretty_name} — setting up repositories...")
        try:
            repo_manager.setup_repos(os_info)
        except Exception as e:
            sys.exit(f"[!] Repository setup failed: {e}")

    cli.run_cli(os_info)


if __name__ == "__main__":
    main()
