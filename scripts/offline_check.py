"""Offline rehearsal: run the app as if Wi-Fi were off, and check every page.

    python scripts/offline_check.py            # Wi-Fi off, offline switch NOT set (the real case)
    python scripts/offline_check.py --switch   # same, with MOSHARI_OFFLINE=1 (the kill switch)

What it does, in about 30 seconds, without touching your files:
1. Starts the real app (`streamlit run app.py`) on a free local port with the internet cut off
   for that process, and waits for it to answer its health check.
2. Opens each of the 10 pages (Streamlit's built-in test runner, no browser needed), still with
   the internet cut off, and records any page that crashes or tries to go online.

"Internet cut off" means every connection or DNS lookup to anything but this computer is refused,
exactly what happens with Wi-Fi off, and proxy settings are ignored. Only Live outlook is allowed
to try (it asks Open-Meteo once, then falls back to saved weather or a friendly message).

Prints one line per page and "OFFLINE CHECK: <ok>/10 pages OK". Exits 0 only when the server
started and all 10 pages passed.
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

PAGES = [
    ("ui/views/ward_net.py", "Overview"),
    ("ui/views/ward_map.py", "Ward map"),
    ("ui/views/resources.py", "Resources"),
    ("ui/views/hospital.py", "Hospital beds"),
    ("ui/views/simulator.py", "Simulator"),
    ("ui/views/dispatch.py", "Dispatch"),
    ("ui/views/live.py", "Live outlook"),
    ("ui/views/ward_forecast.py", "Ward forecast"),
    ("ui/views/model_check.py", "Model accuracy"),
    ("ui/views/data_source.py", "Data"),
]
LIVE = "ui/views/live.py"
LIVE_HOSTS = {"api.open-meteo.com"}
LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}
PROXY_VARS = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy")

# The same guard, written as a sitecustomize module so it also runs inside the server process.
GUARD_SOURCE = textwrap.dedent('''
    import os, socket
    _LOG = os.environ.get("MOSHARI_GUARD_LOG")
    _LOOP = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}
    _connect, _connect_ex = socket.socket.connect, socket.socket.connect_ex
    _create, _getaddrinfo = socket.create_connection, socket.getaddrinfo

    def _refuse(host):
        if host not in _LOOP:
            if _LOG:
                with open(_LOG, "a", encoding="utf-8") as f:
                    f.write(host + "\\n")
            raise OSError(101, "Network is unreachable (" + host + ")")

    def _h(a):
        return str(a[0]) if isinstance(a, tuple) and a else str(a)

    def connect(self, a):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            _refuse(_h(a))
        return _connect(self, a)

    def connect_ex(self, a):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            _refuse(_h(a))
        return _connect_ex(self, a)

    def create_connection(a, *args, **kw):
        _refuse(_h(a))
        return _create(a, *args, **kw)

    def getaddrinfo(host, *args, **kw):
        _refuse(str(host or ""))
        return _getaddrinfo(host, *args, **kw)

    socket.socket.connect, socket.socket.connect_ex = connect, connect_ex
    socket.create_connection, socket.getaddrinfo = create_connection, getaddrinfo
''')


def offline_env(switch: bool, guard_dir: Path, log: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in PROXY_VARS and k != "MOSHARI_OFFLINE"}
    if switch:
        env["MOSHARI_OFFLINE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join([str(guard_dir), str(ROOT / "src"), env.get("PYTHONPATH", "")])
    env["MOSHARI_GUARD_LOG"] = str(log)
    return env


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _read_log(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").split() if log.exists() else []


def check_server(work: Path, switch: bool) -> tuple[bool, str]:
    """Start `streamlit run app.py` with the internet cut off and wait for its health check."""
    log = work / "server_attempts.log"
    port = _free_port()
    cmd = [sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"), "--server.headless", "true",
           "--server.port", str(port), "--server.address", "127.0.0.1", "--browser.gatherUsageStats", "false"]
    proc = subprocess.Popen(cmd, cwd=ROOT, env=offline_env(switch, work, log),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    local = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # this computer only
    start = time.time()
    try:
        while time.time() - start < 60:
            if proc.poll() is not None:
                return False, f"server exited with code {proc.returncode} before answering"
            try:
                health = local.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=2).read().decode()
                home = local.open(f"http://127.0.0.1:{port}/", timeout=5).status
                if health.strip() == "ok" and home == 200:
                    lookups = sorted(set(_read_log(log)))
                    note = f"; Streamlit's own start-up lookups refused: {', '.join(lookups)}" if lookups else ""
                    return True, f"server booted offline, health ok in {time.time() - start:.0f}s{note}"
            except OSError:
                time.sleep(0.5)
        return False, "server did not answer its health check within 60 s"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def check_pages(work: Path, switch: bool) -> list[tuple[str, bool, str]]:
    """Render each page in-process with the internet cut off; returns (title, ok, detail)."""
    log = work / "page_attempts.log"
    for var in PROXY_VARS:
        os.environ.pop(var, None)
    os.environ.pop("MOSHARI_OFFLINE", None)
    if switch:
        os.environ["MOSHARI_OFFLINE"] = "1"
    os.environ["MOSHARI_GUARD_LOG"] = str(log)
    exec(compile(GUARD_SOURCE, "offline_guard", "exec"), {})   # cut the internet for this process

    from streamlit.testing.v1 import AppTest

    results = []
    for page, title in PAGES:
        log.write_text("", encoding="utf-8")
        start = time.time()
        try:
            at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
            at.run()
            at.switch_page(page)
            at.run()
            errors = [str(e.value).splitlines()[0] if str(e.value) else "error" for e in at.exception]
            warning = next((str(w.value) for w in at.warning), "")
        except Exception as exc:  # the test runner itself failed on this page
            errors, warning = [f"{type(exc).__name__}: {exc}"], ""
        tried = sorted(set(_read_log(log)))
        took = f"{time.time() - start:.1f}s"
        allowed = set() if switch else (LIVE_HOSTS if page == LIVE else set())
        if errors:
            results.append((title, False, f"CRASH {took}: {errors[0][:120]}"))
        elif set(tried) - allowed:
            results.append((title, False, f"ONLINE {took}: tried {', '.join(tried)}"))
        else:
            detail = f"OK {took}"
            if page == LIVE:
                detail += f" - shows: {warning[:90]}" if warning else " - shows saved weather"
                if tried:
                    detail += " (asked Open-Meteo once, refused, handled)"
            results.append((title, True, detail))
    return results


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--switch", action="store_true", help="also set MOSHARI_OFFLINE=1 (the kill switch)")
    args = ap.parse_args(argv)
    mode = "Wi-Fi off, MOSHARI_OFFLINE=1" if args.switch else "Wi-Fi off, offline switch not set"
    print(f"Offline rehearsal ({mode})\n")
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="moshari-offline-") as tmp:
        work = Path(tmp)
        (work / "sitecustomize.py").write_text(GUARD_SOURCE, encoding="utf-8")
        server_ok, server_msg = check_server(work, args.switch)
        print(f"{'PASS' if server_ok else 'FAIL'} {server_msg}")
        results = check_pages(work, args.switch)
    width = max(len(t) for t, _, _ in results)
    for title, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} {title:<{width}}  {detail}")
    passed = sum(ok for _, ok, _ in results)
    print(f"\nOFFLINE CHECK: {passed}/{len(results)} pages OK, server {'booted' if server_ok else 'FAILED'}, "
          f"{time.time() - t0:.0f}s")
    return 0 if server_ok and passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
