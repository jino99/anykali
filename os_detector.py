"""
os_detector.py — Identify distro, OS family, and package manager.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


FAMILY_MAP = {
    # id / id_like → (family, package_manager)
    "debian":   ("debian", "apt"),
    "ubuntu":   ("debian", "apt"),
    "kali":     ("debian", "apt"),
    "linuxmint":("debian", "apt"),
    "raspbian": ("debian", "apt"),
    "pop":      ("debian", "apt"),
    "arch":     ("arch",   "pacman"),
    "manjaro":  ("arch",   "pacman"),
    "endeavouros": ("arch","pacman"),
    "fedora":   ("fedora", "dnf"),
    "rhel":     ("fedora", "dnf"),
    "centos":   ("fedora", "dnf"),
    "almalinux":("fedora", "dnf"),
    "rocky":    ("fedora", "dnf"),
    "opensuse": ("suse",   "zypper"),
    "suse":     ("suse",   "zypper"),
}


@dataclass
class OSInfo:
    id: str
    id_like: list[str]
    pretty_name: str
    version_id: str
    family: str
    pkg_manager: str


def detect() -> OSInfo:
    fields: dict[str, str] = {}
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        raise RuntimeError("/etc/os-release not found — cannot detect OS.")

    for line in os_release.read_text().splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            fields[k.strip()] = v.strip().strip('"')

    distro_id = fields.get("ID", "unknown").lower()
    id_like = [x.lower() for x in fields.get("ID_LIKE", "").split()]

    family, pkg_manager = _resolve_family(distro_id, id_like)

    return OSInfo(
        id=distro_id,
        id_like=id_like,
        pretty_name=fields.get("PRETTY_NAME", distro_id),
        version_id=fields.get("VERSION_ID", ""),
        family=family,
        pkg_manager=pkg_manager,
    )


def _resolve_family(distro_id: str, id_like: list[str]) -> tuple[str, str]:
    for key in [distro_id] + id_like:
        if key in FAMILY_MAP:
            return FAMILY_MAP[key]
    return ("unknown", "unknown")
