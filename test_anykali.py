#!/usr/bin/env python3
"""
test_anykali.py — Full regression + new-feature test suite.
Run: python3 test_anykali.py
"""
import ast, io, json, os, sys, subprocess, logging, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from contextlib import redirect_stdout

sys.path.insert(0, str(Path(__file__).parent))

# Start in dry-run so no real commands execute
import core
core.set_dry_run(True)

import os_detector, repo_manager, installer, launcher, cli, anykali

PASS, FAIL = [], []

def test(name, fn):
    try:
        fn()
        PASS.append(name)
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL.append((name, e))
        print(f"  FAIL  {name}: {type(e).__name__}: {e}")

def grab(fn):
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn()
    return buf.getvalue()

def make_os(family):
    pm = {"debian":"apt","arch":"pacman","fedora":"dnf","suse":"zypper"}.get(family,"unknown")
    return os_detector.OSInfo(family, [], family.title(), "", family, pm)

def run_menu(os_info, inputs_list):
    it = iter(inputs_list)
    with patch("builtins.input", lambda _: next(it)):
        try:
            cli.run_cli(os_info)
        except SystemExit:
            pass

real_os = os_detector.detect()

# ─────────────────────────────────────────────────────────────────────────────
print("\n── Syntax ──")
for f in ["anykali.py","core.py","os_detector.py","repo_manager.py",
          "installer.py","launcher.py","cli.py"]:
    test(f"syntax:{f}", lambda x=f: ast.parse(open(x).read()))

# ─────────────────────────────────────────────────────────────────────────────
print("\n── core ──")

def _logging_idempotent():
    lg = logging.getLogger("anykali")
    lg.handlers.clear()
    core.setup_logging(); core.setup_logging(); core.setup_logging()
    assert len(lg.handlers) <= 2
test("core:logging_idempotent", _logging_idempotent)

def _run_dryrun():
    r = core.run(["echo","hi"])
    assert r.returncode == 0 and r.args == ["echo","hi"]
test("core:run_dryrun", _run_dryrun)

def _run_live_check_false():
    core.set_dry_run(False)
    core.run(["false"], check=False)
    core.set_dry_run(True)
test("core:run_check_false_no_raise", _run_live_check_false)

def _run_live_check_true():
    core.set_dry_run(False)
    try:
        core.run(["false"], check=True)
        raise AssertionError("should raise")
    except subprocess.CalledProcessError:
        pass
    finally:
        core.set_dry_run(True)
test("core:run_check_true_raises", _run_live_check_true)

def _run_capture():
    core.set_dry_run(False)
    r = core.run(["echo","hello"], capture=True)
    assert r.stdout.strip() == "hello"
    core.set_dry_run(True)
test("core:run_capture", _run_capture)

def _run_streams_output():
    """run() without capture should stream output (not swallow it)."""
    core.set_dry_run(False)
    buf = io.StringIO()
    with redirect_stdout(buf):
        core.run(["echo", "streamed"])
    assert "streamed" in buf.getvalue()
    core.set_dry_run(True)
test("core:run_streams_to_stdout", _run_streams_output)

def _check_deps_ok():
    core.check_deps(["python3", "ls"])
test("core:check_deps_present", _check_deps_ok)

def _check_deps_missing():
    try:
        core.check_deps(["__no_such_binary_xyz__"])
        raise AssertionError("should exit")
    except SystemExit as e:
        assert "__no_such_binary_xyz__" in str(e)
test("core:check_deps_missing_exits", _check_deps_missing)

def _apt_lock_detection():
    # _apt_locked() must return bool without crashing
    result = core._apt_locked()
    assert isinstance(result, bool)
test("core:apt_locked_returns_bool", _apt_lock_detection)

def _apt_lock_readonly():
    """_apt_locked must open lock file read-only, never truncate it."""
    import inspect
    src = inspect.getsource(core._apt_locked)
    assert '"w"' not in src and "'w'" not in src, \
        "_apt_locked opens lock with 'w' mode — truncates dpkg lock!"
test("core:apt_locked_opens_readonly_not_w_mode", _apt_lock_readonly)

def _run_empty_cmd():
    try:
        core.run([])
        raise AssertionError("should raise")
    except ValueError as e:
        assert "empty" in str(e).lower()
test("core:run_empty_cmd_raises_ValueError", _run_empty_cmd)

def _set_dry_run():
    core.set_dry_run(False)
    assert not core.is_dry_run()
    core.set_dry_run(True)
    assert core.is_dry_run()
test("core:set_dry_run_toggle", _set_dry_run)

# ─────────────────────────────────────────────────────────────────────────────
print("\n── os_detector ──")

def _detect_real():
    info = os_detector.detect()
    assert info.id and info.family and info.pkg_manager
test("os_detector:detect_real", _detect_real)

FAMILY_CASES = [
    ("debian",[],"debian","apt"), ("ubuntu",[],"debian","apt"),
    ("kali",[],"debian","apt"), ("linuxmint",["ubuntu"],"debian","apt"),
    ("popos",["ubuntu","debian"],"debian","apt"),
    ("arch",[],"arch","pacman"), ("manjaro",[],"arch","pacman"),
    ("endeavouros",[],"arch","pacman"),
    ("fedora",[],"fedora","dnf"), ("rhel",[],"fedora","dnf"),
    ("centos",[],"fedora","dnf"), ("almalinux",[],"fedora","dnf"),
    ("rocky",[],"fedora","dnf"),
    ("opensuse",[],"suse","zypper"), ("suse",[],"suse","zypper"),
    ("unknown_os",[],"unknown","unknown"),
]
for distro, id_like, ef, ep in FAMILY_CASES:
    def _t(d=distro,il=id_like,ef=ef,ep=ep):
        f,p = os_detector._resolve_family(d,il)
        assert (f,p)==(ef,ep), f"{d}: got ({f},{p})"
    test(f"os_detector:map:{distro}", _t)

def _detect_missing_id():
    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.read_text", return_value='PRETTY_NAME="X"\n'):
        info = os_detector.detect()
        assert info.id == "unknown"
test("os_detector:missing_ID_field", _detect_missing_id)

def _detect_no_file():
    with patch("pathlib.Path.exists", return_value=False):
        try: os_detector.detect(); raise AssertionError
        except RuntimeError: pass
test("os_detector:missing_os_release_raises", _detect_no_file)

# ─────────────────────────────────────────────────────────────────────────────
print("\n── repo_manager ──")

def _pinning_priority():
    content = repo_manager.KALI_PINNING_CONTENT
    # Must have three stanzas covering o=, l=, a=
    assert content.count("Pin-Priority: 50") == 3
    assert "Pin: release o=Kali" in content
    assert "Pin: release l=Kali" in content
    assert "Pin: release a=kali-rolling" in content
    # Priority must be < 100 (installed pkg priority)
    import re
    for prio in re.findall(r"Pin-Priority:\s*(\d+)", content):
        assert int(prio) < 100, f"Priority {prio} >= 100 — unsafe!"
test("repo_manager:pinning_three_stanzas_priority_lt_100", _pinning_priority)

def _sources_signed_by():
    assert f"signed-by={repo_manager.KALI_KEYRING_PATH}" in repo_manager.KALI_SOURCES_CONTENT
    assert "apt-key" not in repo_manager.KALI_SOURCES_CONTENT
test("repo_manager:sources_signed_by_no_apt_key", _sources_signed_by)

def _paths():
    assert str(repo_manager.KALI_SOURCES_FILE) == "/etc/apt/sources.list.d/kali-rolling.list"
    assert str(repo_manager.KALI_PREFS_FILE)   == "/etc/apt/preferences.d/kali-pinning"
    assert str(repo_manager.KALI_KEYRING_PATH) == "/etc/apt/keyrings/kali-archive-keyring.asc"
test("repo_manager:paths_correct", _paths)

def _backup_existing():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".conf") as f:
        f.write(b"data"); tmp = Path(f.name)
    bak = repo_manager._backup(tmp)
    assert bak and bak.exists() and bak.read_bytes() == b"data"
    bak.unlink(); tmp.unlink()
test("repo_manager:backup_existing", _backup_existing)

def _backup_missing():
    assert repo_manager._backup(Path("/nonexistent/xyz.conf")) is None
test("repo_manager:backup_missing_returns_none", _backup_missing)

def _write_dryrun():
    out = grab(lambda: repo_manager._write(Path("/etc/test"), "content"))
    assert "[DRY-RUN] write" in out
test("repo_manager:_write_dryrun_no_filesystem", _write_dryrun)

def _unlink_dryrun():
    out = grab(lambda: repo_manager._unlink(Path("/etc/test")))
    assert "[DRY-RUN] unlink" in out
test("repo_manager:_unlink_dryrun_no_filesystem", _unlink_dryrun)

def _remove_blackarch_no_pacman():
    repo_manager.remove_blackarch_repo()   # must not crash
test("repo_manager:remove_blackarch_no_pacman_conf", _remove_blackarch_no_pacman)

def _remove_debian_log_correct():
    """remove_kali_repo_debian must log removal even after file is deleted."""
    logged = []
    with patch.object(repo_manager.log, "info", lambda msg, *a: logged.append(msg % a if a else msg)), \
         patch.object(repo_manager, "_unlink", lambda p: None), \
         patch("pathlib.Path.exists", return_value=True):
        repo_manager.remove_kali_repo_debian()
    removal_logs = [l for l in logged if "Removed" in l]
    assert len(removal_logs) == 3, f"Expected 3 removal logs, got: {removal_logs}"
test("repo_manager:remove_debian_logs_all_three_files", _remove_debian_log_correct)

def _setup_unknown_raises():
    try:
        repo_manager.setup_repos(make_os("unknown"))
        raise AssertionError
    except NotImplementedError:
        pass
test("repo_manager:setup_unknown_raises", _setup_unknown_raises)

def _teardown_unknown_silent():
    repo_manager.teardown_repos(make_os("unknown"))
test("repo_manager:teardown_unknown_silent", _teardown_unknown_silent)

def _gpg_failure_rollback():
    """If curl fails, no sources/prefs files should be written."""
    core.set_dry_run(False)
    written = []
    def fake_run(cmd, **kw):
        if "curl" in cmd:
            raise subprocess.CalledProcessError(1, cmd)
        written.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)
    with patch("repo_manager.run", side_effect=fake_run), \
         patch("pathlib.Path.mkdir"), \
         patch("pathlib.Path.exists", return_value=False):
        try:
            repo_manager.add_kali_repo_debian()
        except RuntimeError:
            pass
    assert not any("apt-get" in str(c) for c in written), \
        "apt-get update ran despite GPG failure"
    core.set_dry_run(True)
test("repo_manager:gpg_failure_prevents_sources_write", _gpg_failure_rollback)

def _apt_update_failure_rollback():
    """If apt-get update fails after writing files, _unlink must be called for rollback."""
    core.set_dry_run(False)
    unlinked = []

    def fake_run(cmd, **kw):
        if "curl" in cmd:
            return subprocess.CompletedProcess(cmd, 0)
        if "apt-get" in cmd:
            raise subprocess.CalledProcessError(100, cmd)
        return subprocess.CompletedProcess(cmd, 0)

    def tracking_unlink(path):
        unlinked.append(str(path))

    with patch("repo_manager.run",    side_effect=fake_run), \
         patch("repo_manager._backup", return_value=None), \
         patch("pathlib.Path.mkdir"), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.stat",   return_value=MagicMock(st_size=2000)), \
         patch("pathlib.Path.write_text"), \
         patch.object(repo_manager, "_unlink", tracking_unlink):
        try:
            repo_manager.add_kali_repo_debian()
        except Exception:
            pass
    assert len(unlinked) >= 2, f"Expected rollback _unlink calls, got: {unlinked}"
    core.set_dry_run(True)
test("repo_manager:apt_update_failure_triggers_rollback", _apt_update_failure_rollback)

# ─────────────────────────────────────────────────────────────────────────────
print("\n── installer ──")

def _apt_cmd():
    out = grab(lambda: installer.install(["nmap"], make_os("debian")))
    assert "apt-get install -y --no-install-recommends -t kali-rolling nmap" in out
test("installer:apt_install_cmd", _apt_cmd)

def _apt_remove_cmd():
    out = grab(lambda: installer.remove(["nmap"], make_os("debian")))
    assert "apt-get remove -y nmap" in out and "autoremove" in out
test("installer:apt_remove_cmd", _apt_remove_cmd)

def _apt_purge_cmd():
    out = grab(lambda: installer.remove(["nmap"], make_os("debian"), purge=True))
    assert "apt-get purge -y nmap" in out
test("installer:apt_purge_cmd", _apt_purge_cmd)

for fam, expected in [
    ("arch",   "pacman -S --noconfirm --needed nmap"),
    ("fedora", "dnf install -y nmap"),
    ("suse",   "zypper --non-interactive install nmap"),
]:
    def _t(f=fam, e=expected):
        out = grab(lambda: installer.install(["nmap"], make_os(f)))
        assert e in out, f"{f}: {e!r} not in output"
    test(f"installer:{fam}_install_cmd", _t)

def _meta_all_keys():
    for key, pkg in installer.META_PACKAGES.items():
        out = grab(lambda k=key: installer.install_meta(k, make_os("debian")))
        assert pkg in out
test("installer:meta_all_keys_debian", _meta_all_keys)

def _meta_arch():
    out = grab(lambda: installer.install_meta("default", make_os("arch")))
    assert "blackarch" in out
test("installer:meta_arch_blackarch", _meta_arch)

def _distrobox_cmd():
    out = grab(lambda: installer.install(["nmap"], make_os("unknown")))
    assert "distrobox enter kali-anykali" in out
    assert "distrobox-export --bin /usr/bin/nmap" in out
test("installer:distrobox_install_cmd", _distrobox_cmd)

# ─────────────────────────────────────────────────────────────────────────────
print("\n── launcher ──")

def _find_binaries():
    for t in ["python3","ls","bash"]:
        b = launcher.find_binary(t)
        assert b and b.exists()
test("launcher:find_system_binaries", _find_binaries)

def _find_missing():
    assert launcher.find_binary("__no_such_tool_xyz__") is None
test("launcher:find_missing_none", _find_missing)

def _is_installed():
    assert launcher.is_installed("python3")
    assert not launcher.is_installed("__no_such_tool_xyz__")
test("launcher:is_installed", _is_installed)

def _launch_dryrun():
    out = grab(lambda: launcher.launch("nmap"))
    assert "[DRY-RUN] launch nmap" in out
test("launcher:launch_dryrun_prints_not_executes", _launch_dryrun)

def _launch_missing():
    core.set_dry_run(False)
    out = grab(lambda: launcher.launch("__no_such_tool_xyz__"))
    assert "not found" in out
    core.set_dry_run(True)
test("launcher:launch_missing_prints_error", _launch_missing)

def _launch_keyboard_interrupt():
    core.set_dry_run(False)
    with patch("subprocess.run", side_effect=KeyboardInterrupt):
        launcher.launch("python3")   # must not propagate
    core.set_dry_run(True)
test("launcher:launch_handles_keyboard_interrupt", _launch_keyboard_interrupt)

def _gui_tool_no_display_warns():
    """GUI tool without $DISPLAY should warn and prompt, not silently launch."""
    core.set_dry_run(False)
    env_backup = os.environ.pop("DISPLAY", None), os.environ.pop("WAYLAND_DISPLAY", None)
    try:
        # Mock find_binary so the tool appears installed regardless of system state
        with patch.object(launcher, "find_binary", return_value=Path("/usr/bin/wireshark")), \
             patch("builtins.input", return_value="n"):
            out = grab(lambda: launcher.launch("wireshark"))
        assert "display" in out.lower() or "GUI" in out, f"No display warning in: {out!r}"
    finally:
        if env_backup[0]: os.environ["DISPLAY"] = env_backup[0]
        if env_backup[1]: os.environ["WAYLAND_DISPLAY"] = env_backup[1]
        core.set_dry_run(True)
test("launcher:gui_tool_no_display_warns", _gui_tool_no_display_warns)

def _root_tool_warns_non_root():
    """Root-required tool should warn when not running as root."""
    core.set_dry_run(False)
    try:
        if os.geteuid() == 0:
            return  # can't test this as root
        with patch.object(launcher, "find_binary", return_value=Path("/usr/bin/nmap")), \
             patch("builtins.input", return_value="n"):
            out = grab(lambda: launcher.launch("nmap"))
        assert "root" in out.lower() or "privilege" in out.lower(), \
            f"No root warning in: {out!r}"
    finally:
        core.set_dry_run(True)
test("launcher:root_tool_warns_non_root", _root_tool_warns_non_root)

def _has_display_check():
    with patch.dict(os.environ, {"DISPLAY": ":0"}, clear=False):
        assert launcher._has_display()
    saved = os.environ.pop("DISPLAY", None), os.environ.pop("WAYLAND_DISPLAY", None)
    try:
        assert not launcher._has_display()
    finally:
        if saved[0]: os.environ["DISPLAY"] = saved[0]
        if saved[1]: os.environ["WAYLAND_DISPLAY"] = saved[1]
test("launcher:_has_display", _has_display_check)

# ─────────────────────────────────────────────────────────────────────────────
print("\n── cli._pick (loops on invalid input) ──")

def _pick_loops_then_valid():
    """_pick must loop on invalid input, not return None."""
    opts = ["A","B","C"]
    inputs = iter(["abc","99","","2"])
    with patch("builtins.input", lambda _: next(inputs)):
        r = cli._pick(opts)
    assert r == 1   # "2" → index 1
test("cli:pick_loops_on_invalid_then_accepts", _pick_loops_then_valid)

def _pick_zero_back():
    with patch("builtins.input", return_value="0"):
        assert cli._pick(["A","B"]) is None
test("cli:pick_zero_returns_none", _pick_zero_back)

def _pick_valid():
    with patch("builtins.input", return_value="1"):
        assert cli._pick(["A","B"]) == 0
test("cli:pick_valid_returns_index", _pick_valid)

def _prompt_ctrl_c():
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        try: cli._prompt("x: "); raise AssertionError
        except SystemExit as e: assert e.code == 0
test("cli:prompt_ctrl_c_exits_0", _prompt_ctrl_c)

def _prompt_eof():
    with patch("builtins.input", side_effect=EOFError):
        try: cli._prompt("x: "); raise AssertionError
        except SystemExit as e: assert e.code == 0
test("cli:prompt_eof_exits_0", _prompt_eof)

# ─────────────────────────────────────────────────────────────────────────────
print("\n── cli menu flows ──")

MENU_FLOWS = [
    ("browse_launch",           ['1','1','1','1','0','0','6']),
    ("browse_install",          ['1','1','2','1','0','0','6']),
    ("browse_remove_confirm",   ['1','1','1','2','y','0','0','6']),
    ("browse_remove_deny",      ['1','1','1','2','n','0','0','6']),
    ("browse_back",             ['1','0','6']),
    ("search_found_back",       ['2','nmap','0','6']),
    ("search_found_select_back",['2','nmap','1','2','6']),
    ("search_no_results",       ['2','zzznoresult999','6']),
    ("search_empty_query",      ['2','','6']),
    ("install_all_default",     ['3','1','y','6']),
    ("install_all_large",       ['3','2','y','6']),
    ("install_all_everything",  ['3','3','y','6']),
    ("install_all_cancel",      ['3','1','n','6']),
    ("install_all_back",        ['3','0','6']),
    ("update",                  ['4','6']),
    ("purge_cancelled",         ['5','no','6']),
    ("purge_confirmed",         ['5','PURGE','6']),
    ("invalid_then_exit",       ['99','abc','','6']),
]
for name, inputs in MENU_FLOWS:
    test(f"cli:menu:{name}", lambda i=inputs: run_menu(real_os, i))

def _ctrl_c():
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        try: cli.run_cli(real_os)
        except SystemExit as e: assert e.code == 0
test("cli:menu:ctrl_c_exits_0", _ctrl_c)

def _eof():
    with patch("builtins.input", side_effect=EOFError):
        try: cli.run_cli(real_os)
        except SystemExit as e: assert e.code == 0
test("cli:menu:eof_exits_0", _eof)

def _install_exception_handled():
    """Installation failure must print error, not crash the menu."""
    with patch.object(installer, "install", side_effect=RuntimeError("locked")):
        run_menu(real_os, ['1','1','2','1','0','0','6'])
test("cli:menu:install_exception_shows_error_not_crash", _install_exception_handled)

def _update_unknown_family():
    """Update on unknown family must print unsupported message, not crash."""
    run_menu(make_os("unknown"), ['4','6'])
test("cli:menu:update_unknown_family_no_crash", _update_unknown_family)

def _dry_run_banner():
    out = grab(lambda: cli._print_banner(real_os))
    assert "DRY-RUN" in out
test("cli:banner_shows_dry_run_tag", _dry_run_banner)

def _validate_bad_schema():
    """_validate_tools_schema must exit on missing required keys."""
    bad = {"cat": [{"name": "t", "pkg": "p"}]}
    try:
        cli._validate_tools_schema(bad)
        raise AssertionError("should exit")
    except SystemExit as e:
        assert "missing keys" in str(e)
test("cli:_validate_tools_schema_missing_desc_exits", _validate_bad_schema)

def _validate_bad_category_type():
    bad = {"cat": "not-a-list"}
    try:
        cli._validate_tools_schema(bad)
        raise AssertionError("should exit")
    except SystemExit as e:
        assert "not a list" in str(e)
test("cli:_validate_tools_schema_category_not_list_exits", _validate_bad_category_type)

def _validate_bad_tool_type():
    bad = {"cat": ["not-a-dict"]}
    try:
        cli._validate_tools_schema(bad)
        raise AssertionError("should exit")
    except SystemExit as e:
        assert "not a dict" in str(e)
test("cli:_validate_tools_schema_tool_not_dict_exits", _validate_bad_tool_type)

def _validate_valid_schema_no_exit():
    valid = {"cat": [{"name": "t", "pkg": "p", "desc": "d"}]}
    cli._validate_tools_schema(valid)
test("cli:_validate_tools_schema_valid_no_exit", _validate_valid_schema_no_exit)

# ─────────────────────────────────────────────────────────────────────────────
print("\n── anykali.main() ──")

def _main_family(family):
    info = make_os(family)
    mock_src = MagicMock(); mock_src.exists.return_value = False
    with patch.object(core,         "require_root",  lambda: None), \
         patch.object(core,         "setup_logging", lambda: None), \
         patch.object(core,         "check_deps",    lambda deps: None), \
         patch.object(os_detector,  "detect",        return_value=info), \
         patch.object(repo_manager, "KALI_SOURCES_FILE", mock_src), \
         patch.object(repo_manager, "setup_repos",   lambda i: None), \
         patch.object(cli,          "run_cli",        lambda i: None), \
         patch.object(anykali,      "_blackarch_present",          lambda: False), \
         patch.object(anykali,      "_distrobox_container_exists", lambda: False):
        anykali.main()

for fam in ["debian","arch","fedora","suse","unknown"]:
    test(f"anykali:main:{fam}", lambda f=fam: _main_family(f))

def _main_no_double_setup():
    info = make_os("debian")
    mock_src = MagicMock(); mock_src.exists.return_value = True
    called = []
    with patch.object(core,         "require_root",  lambda: None), \
         patch.object(core,         "setup_logging", lambda: None), \
         patch.object(core,         "check_deps",    lambda deps: None), \
         patch.object(os_detector,  "detect",        return_value=info), \
         patch.object(repo_manager, "KALI_SOURCES_FILE", mock_src), \
         patch.object(repo_manager, "setup_repos",   lambda i: called.append(1)), \
         patch.object(cli,          "run_cli",        lambda i: None):
        anykali.main()
    assert called == []
test("anykali:main:no_setup_when_already_configured", _main_no_double_setup)

def _main_setup_failure_exits():
    info = make_os("debian")
    mock_src = MagicMock(); mock_src.exists.return_value = False
    with patch.object(core,         "require_root",  lambda: None), \
         patch.object(core,         "setup_logging", lambda: None), \
         patch.object(core,         "check_deps",    lambda deps: None), \
         patch.object(os_detector,  "detect",        return_value=info), \
         patch.object(repo_manager, "KALI_SOURCES_FILE", mock_src), \
         patch.object(repo_manager, "setup_repos",   lambda i: (_ for _ in ()).throw(RuntimeError("net error"))), \
         patch.object(cli,          "run_cli",        lambda i: None):
        try:
            anykali.main()
            raise AssertionError("should have exited")
        except SystemExit as e:
            assert "net error" in str(e)
test("anykali:main:setup_failure_exits_cleanly", _main_setup_failure_exits)

def _dry_run_flag():
    """--dry-run flag must set core._DRY_RUN before anything else."""
    core.set_dry_run(False)
    info = make_os("debian")
    mock_src = MagicMock(); mock_src.exists.return_value = True
    with patch("sys.argv", ["anykali.py", "--dry-run"]), \
         patch.object(core,        "require_root",  lambda: None), \
         patch.object(core,        "setup_logging", lambda: None), \
         patch.object(core,        "check_deps",    lambda deps: None), \
         patch.object(os_detector, "detect",        return_value=info), \
         patch.object(repo_manager,"KALI_SOURCES_FILE", mock_src), \
         patch.object(cli,         "run_cli",        lambda i: None):
        anykali.main()
    assert core.is_dry_run()
    core.set_dry_run(True)
test("anykali:dry_run_flag_activates_dry_run", _dry_run_flag)

def _blackarch_no_crash():
    assert anykali._blackarch_present() is False
test("anykali:_blackarch_present_no_crash_on_debian", _blackarch_no_crash)

def _unknown_family_checks_distrobox():
    """unknown family must check for distrobox, not just curl."""
    assert "distrobox" in (anykali._COMMON_DEPS + anykali._CONTAINER_DEPS) or \
           "distrobox" in anykali._CONTAINER_DEPS
    # Verify _check_deps_for_family("unknown") includes distrobox
    checked = []
    with patch.object(core, "check_deps", lambda deps: checked.extend(deps)):
        anykali._check_deps_for_family("unknown")
    assert "distrobox" in checked, f"distrobox not checked for unknown family: {checked}"
test("anykali:unknown_family_checks_distrobox", _unknown_family_checks_distrobox)

def _distrobox_false():
    with patch("subprocess.run", return_value=MagicMock(stdout="")):
        assert anykali._distrobox_container_exists() is False
test("anykali:_distrobox_container_exists_false", _distrobox_false)

def _distrobox_true():
    with patch("shutil.which", return_value="/usr/bin/distrobox"), \
         patch("subprocess.run", return_value=MagicMock(stdout="kali-anykali  running")):
        assert anykali._distrobox_container_exists() is True
test("anykali:_distrobox_container_exists_true", _distrobox_true)

# ─────────────────────────────────────────────────────────────────────────────
total = len(PASS) + len(FAIL)
print(f"\n{'═'*52}")
print(f"  Results: {len(PASS)}/{total} passed")
if FAIL:
    print(f"\n  FAILURES ({len(FAIL)}):")
    for name, err in FAIL:
        print(f"    ✗ {name}")
        print(f"      {type(err).__name__}: {err}")
    sys.exit(1)
else:
    print("  ALL TESTS PASSED ✓")
