"""
cli.py — Interactive numbered menu and ASCII banner.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from os_detector import OSInfo
import installer
import launcher

TOOLS_JSON = Path(__file__).parent / "data" / "tools.json"

BANNER = r"""
 █████╗ ███╗   ██╗██╗   ██╗██╗  ██╗ █████╗ ██╗     ██╗
██╔══██╗████╗  ██║╚██╗ ██╔╝██║ ██╔╝██╔══██╗██║     ██║
███████║██╔██╗ ██║ ╚████╔╝ █████╔╝ ███████║██║     ██║
██╔══██║██║╚██╗██║  ╚██╔╝  ██╔═██╗ ██╔══██║██║     ██║
██║  ██║██║ ╚████║   ██║   ██║  ██╗██║  ██║███████╗██║
╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝
  Kali Linux Toolkit Installer for Any Linux Distro
"""


def _load_tools() -> dict[str, list[dict]]:
    try:
        tools = json.loads(TOOLS_JSON.read_text())
    except FileNotFoundError:
        sys.exit(f"[!] Tool catalogue not found: {TOOLS_JSON}")
    except json.JSONDecodeError as e:
        sys.exit(f"[!] Tool catalogue is corrupt: {e}")
    _validate_tools_schema(tools)
    return tools
def _validate_tools_schema(tools: dict[str, list[dict]]) -> None:
    """Validate that each tool entry has the required keys: name, pkg, desc."""
    required_keys = {"name", "pkg", "desc"}
    for category, tool_list in tools.items():
        if not isinstance(tool_list, list):
            sys.exit(f"[!] Invalid tool catalogue: category '{category}' is not a list.")
        for i, tool in enumerate(tool_list):
            if not isinstance(tool, dict):
                sys.exit(f"[!] Invalid tool catalogue: tool at index {i} in category '{category}' is not a dict.")
            missing = required_keys - tool.keys()
            if missing:
                sys.exit(f"[!] Invalid tool catalogue: tool '{tool.get('name', 'unknown')}' in category '{category}' missing keys: {missing}")


def _print_banner(os_info: OSInfo) -> None:
    print(BANNER)
    dry_tag = "  [DRY-RUN MODE]\n" if launcher.is_dry_run() else ""
    print(f"{dry_tag}  Detected: {os_info.pretty_name}  |  "
          f"Family: {os_info.family}  |  PM: {os_info.pkg_manager}\n")


def _prompt(msg: str) -> str:
    try:
        return input(msg).strip()
    except (KeyboardInterrupt, EOFError):
        print("\n[*] Aborted.")
        sys.exit(0)


def _pick(options: list[str], prompt: str = "Select") -> int | None:
    """
    Print numbered options and return 0-based index of user's choice.
    Returns None for '0' (back) or any invalid input.
    Loops until a valid choice or '0' is entered.
    """
    for i, opt in enumerate(options, 1):
        print(f"  {i}) {opt}")
    while True:
        raw = _prompt(f"\n{prompt} (0=back): ")
        if raw == "0":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print(f"[!] Enter a number between 1 and {len(options)}, or 0 to go back.")


# ── Sub-menus ──────────────────────────────────────────────────────────────────

def _menu_browse(tools: dict, os_info: OSInfo) -> None:
    categories = list(tools.keys())
    while True:
        print("\n── Browse by Category ──")
        idx = _pick(categories, "Category")
        if idx is None:
            return
        cat = categories[idx]
        tool_list = tools[cat]
        while True:
            print(f"\n── {cat} ──")
            names = [f"{t['name']:20s} — {t['desc']}" for t in tool_list]
            tidx = _pick(names, "Tool")
            if tidx is None:
                break
            _tool_action(tool_list[tidx], os_info)


def _tool_action(tool: dict, os_info: OSInfo) -> None:
    installed = launcher.is_installed(tool["name"])
    status = "installed" if installed else "not installed"
    print(f"\n  {tool['name']} [{status}]  —  {tool['desc']}")
    actions = (["Launch", "Remove"] if installed else ["Install"]) + ["Back"]
    idx = _pick(actions, "Action")
    if idx is None or actions[idx] == "Back":
        return
    action = actions[idx]
    if action == "Install":
        try:
            installer.install([tool["pkg"]], os_info)
            print(f"[+] {tool['name']} installed.")
        except Exception as e:
            print(f"[!] Installation failed: {e}")
    elif action == "Launch":
        launcher.launch(tool["name"])
    elif action == "Remove":
        if _prompt(f"Remove {tool['name']}? [y/N]: ").lower() == "y":
            try:
                installer.remove([tool["pkg"]], os_info)
                print(f"[-] {tool['name']} removed.")
            except Exception as e:
                print(f"[!] Removal failed: {e}")


def _menu_search(tools: dict, os_info: OSInfo) -> None:
    query = _prompt("\nSearch tool name: ").lower()
    if not query:
        return
    results = [
        t for tlist in tools.values() for t in tlist
        if query in t["name"].lower() or query in t["desc"].lower()
    ]
    if not results:
        print("[!] No tools found.")
        return
    names = [f"{t['name']:20s} — {t['desc']}" for t in results]
    idx = _pick(names, "Select tool")
    if idx is not None:
        _tool_action(results[idx], os_info)


def _menu_install_all(os_info: OSInfo) -> None:
    print("\n── Install All Kali Tools ──")
    print("  This will install a Kali meta-package (may be several GB).")
    options = [
        "kali-linux-default     (~600 MB)",
        "kali-linux-large       (~3 GB)",
        "kali-linux-everything  (~15 GB)",
    ]
    keys = ["default", "large", "everything"]
    idx = _pick(options, "Meta-package")
    if idx is None:
        return
    if _prompt(f"Install '{options[idx].strip()}'? [y/N]: ").lower() == "y":
        try:
            installer.install_meta(keys[idx], os_info)
            print("[+] Meta-package installation complete.")
        except Exception as e:
            print(f"[!] Installation failed: {e}")


def _menu_update(os_info: OSInfo) -> None:
    from core import run
    print("\n[*] Updating package repositories...")
    try:
        match os_info.family:
            case "debian":  run(["apt-get", "update", "-qq"])
            case "arch":    run(["pacman", "-Sy", "--noconfirm"])
            case "fedora":  run(["dnf", "check-update"], check=False)
            case "suse":    run(["zypper", "refresh"])
            case _:
                print("[!] Update not supported for this OS family.")
                return
        print("[+] Done.")
    except Exception as e:
        print(f"[!] Update failed: {e}")


def _menu_purge(os_info: OSInfo) -> None:
    from repo_manager import teardown_repos
    print("\n── Purge Kali Setup ──")
    print("  This removes all Kali repos, GPG keys, and pinning rules.")
    if _prompt("Type 'PURGE' to confirm: ") == "PURGE":
        try:
            teardown_repos(os_info)
            print("[+] Kali setup purged. Host system restored.")
        except Exception as e:
            print(f"[!] Purge failed: {e}")
    else:
        print("[*] Cancelled.")


# ── Main loop ──────────────────────────────────────────────────────────────────

def run_cli(os_info: OSInfo) -> None:
    tools = _load_tools()
    _print_banner(os_info)

    MAIN_MENU = [
        "Browse tools by category",
        "Search and install a specific tool",
        "Install ALL Kali tools (meta-package)",
        "Update repositories",
        "Purge Kali setup (full rollback)",
        "Exit",
    ]

    while True:
        print("\n══════════════════ MAIN MENU ══════════════════")
        for i, item in enumerate(MAIN_MENU, 1):
            print(f"  {i}) {item}")
        choice = _prompt("\nSelect option: ")
        match choice:
            case "1": _menu_browse(tools, os_info)
            case "2": _menu_search(tools, os_info)
            case "3": _menu_install_all(os_info)
            case "4": _menu_update(os_info)
            case "5": _menu_purge(os_info)
            case "6": print("Goodbye."); sys.exit(0)
            case _:   print("[!] Enter a number between 1 and 6.")
