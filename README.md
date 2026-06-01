<div align="center">

```
 █████╗ ███╗   ██╗██╗   ██╗██╗  ██╗ █████╗ ██╗     ██╗
██╔══██╗████╗  ██║╚██╗ ██╔╝██║ ██╔╝██╔══██╗██║     ██║
███████║██╔██╗ ██║ ╚████╔╝ █████╔╝ ███████║██║     ██║
██╔══██║██║╚██╗██║  ╚██╔╝  ██╔═██╗ ██╔══██║██║     ██║
██║  ██║██║ ╚████║   ██║   ██║  ██╗██║  ██║███████╗██║
╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝
```

**Kali Linux toolkit installer for any Linux distribution**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux-FCC624?style=flat-square&logo=linux&logoColor=black)](https://kernel.org/)
[![Distros](https://img.shields.io/badge/Distros-Debian%20%7C%20Arch%20%7C%20Fedora%20%7C%20openSUSE-blue?style=flat-square)](https://github.com/jino99/anykali)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square)](https://github.com/jino99/anykali/pulls)

</div>

---

## Overview

**anykali** brings the full Kali Linux security toolkit to any Linux distribution — no dual-boot, no VM required. It auto-detects your distro, configures the appropriate repositories or containers, and gives you an interactive menu to browse, install, launch, and remove 50+ professional security tools across 11 categories.

| Distro Family | Strategy |
|---|---|
| Debian / Ubuntu / Mint / Pop!_OS | Adds the official `kali-rolling` APT repo with pinning |
| Arch / Manjaro / EndeavourOS | Bootstraps the BlackArch repository |
| Fedora / RHEL / AlmaLinux / Rocky | Spins up a Kali `distrobox` container |
| openSUSE | Spins up a Kali `distrobox` container |

---

## Features

- **Auto-detection** — reads `/etc/os-release` to identify distro, family, and package manager
- **Interactive TUI** — numbered menus, search, per-tool install / launch / remove actions
- **Meta-package installer** — one-click `kali-linux-default`, `kali-linux-large`, or `kali-linux-everything`
- **Safe APT pinning** — Kali packages are pinned at priority 50; your host packages are never overridden
- **Dry-run mode** — simulate every operation with `--dry-run` before touching the system
- **Full rollback** — `Purge` menu option removes all repos, GPG keys, and pinning rules
- **Structured logging** — all actions logged to `/var/log/anykali.log`
- **Zero runtime dependencies** — pure Python 3.10+ stdlib

---

## Tool Categories

<details>
<summary>Click to expand all 11 categories (50+ tools)</summary>

| Category | Tools |
|---|---|
| 🔍 Information Gathering | nmap, masscan, recon-ng, maltego, theHarvester, amass, dmitry, netdiscover |
| 🛡️ Vulnerability Analysis | nikto, openvas, lynis, nessus, legion |
| 💥 Exploitation | metasploit, sqlmap, beef-xss, exploitdb, commix |
| 📡 Wireless Attacks | aircrack-ng, wifite, kismet, reaver, fern-wifi-cracker |
| 🌐 Web Application Analysis | burpsuite, zaproxy, wpscan, dirb, gobuster, ffuf |
| 🔑 Password Attacks | hashcat, john, hydra, medusa, crunch |
| 🕵️ Sniffing & Spoofing | wireshark, tcpdump, ettercap, bettercap, responder |
| 🎯 Post Exploitation | empire, weevely, mimikatz, crackmapexec |
| 🔬 Forensics | autopsy, volatility, binwalk, foremost, bulk-extractor |
| ⚙️ Reverse Engineering | ghidra, radare2, gdb, pwndbg, jadx |
| 🎭 Social Engineering | setoolkit, gophish |

</details>

---

## Requirements

- Linux (any distro listed above)
- Python 3.10+
- Root / sudo access
- `curl` (all distros)
- `gpg` (Debian-based)
- `distrobox` (Fedora / openSUSE)

---

## Installation

```bash
git clone https://github.com/jino99/anykali.git
cd anykali
sudo python3 anykali.py
```

No pip install needed — zero external dependencies.

---

## Usage

```
sudo python3 anykali.py [OPTIONS]

Options:
  -d, --dry-run    Simulate all operations without making any changes
  -h, --help       Show this help message and exit
```

### Main Menu

```
══════════════════ MAIN MENU ══════════════════
  1) Browse tools by category
  2) Search and install a specific tool
  3) Install ALL Kali tools (meta-package)
  4) Update package repositories
  5) Purge Kali setup (full rollback)
  6) Exit
```

### Dry-run example

```bash
sudo python3 anykali.py --dry-run
# [*] DRY-RUN mode active — no changes will be made.
# [DRY-RUN] apt-get install -y --no-install-recommends -t kali-rolling nmap
```

---

## Project Structure

```
anykali/
├── anykali.py        # Entry point — arg parsing, dep checks, bootstrap
├── cli.py            # Interactive TUI menus and ASCII banner
├── core.py           # Privilege management, logging, subprocess runner
├── installer.py      # Install/remove wrappers for all package managers
├── launcher.py       # Binary discovery and tool launcher
├── os_detector.py    # Distro detection via /etc/os-release
├── repo_manager.py   # Repository setup and teardown per OS family
├── data/
│   └── tools.json    # Tool catalogue (name, package, description)
└── requirements.txt  # Dev notes (no runtime deps)
```

---

## How It Works

```
sudo python3 anykali.py
        │
        ├─ detect OS  (/etc/os-release)
        │
        ├─ check deps  (curl / gpg / distrobox)
        │
        ├─ first-run setup (if needed)
        │     ├─ Debian  → add kali-rolling APT repo + GPG key + pin
        │     ├─ Arch    → bootstrap BlackArch repo
        │     └─ Other   → create kali distrobox container
        │
        └─ interactive CLI loop
              ├─ browse / search / install / launch / remove tools
              ├─ install meta-packages
              ├─ update repos
              └─ purge (full rollback)
```

---

## Safety & Ethics

> **For authorized security testing and educational use only.**

- anykali never overrides host system packages (APT pinning at priority 50)
- Full rollback available at any time via the Purge menu
- Dry-run mode lets you inspect every command before execution
- All actions are logged to `/var/log/anykali.log`

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m 'Add my feature'`
4. Push to the branch: `git push origin feature/my-feature`
5. Open a Pull Request

To add tools, edit `data/tools.json` following the existing schema.

---

## License

[MIT](LICENSE) © 2026 [jino99](https://github.com/jino99)
