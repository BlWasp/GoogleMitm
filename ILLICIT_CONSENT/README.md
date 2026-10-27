# Illicit Consent Grant -- Google OAuth2 Attack

## Principle

The attacker creates an OAuth2 application in their own GCP project, configures access scopes (emails, Drive, GCP...), and tricks the victim into clicking a "Sign in with Google" link. The victim sees an official Google consent screen. By clicking **Allow**, they deliver an `access_token` and a `refresh_token` to the attacker, who can then call Google REST APIs without ever knowing their password.

**Key difference from cookie theft:**
- Cookie theft -> access to the web UI (Gmail, GCP Console) via Playwright
- Illicit Consent -> direct access to **REST APIs** (Gmail API, Drive API, Cloud Resource Manager) with a real Bearer token

---

## Architecture

```
Victim
  |
  |  (1) Clicks lure URL
  v
http://localhost:8080/
  |
  |  (2) Redirect to Google
  v
https://accounts.google.com/o/oauth2/v2/auth
  |
  |  (3) Victim consents + authenticates
  v
Google
  |
  |  (4) Redirect with code
  v
http://localhost:8080/callback?code=XXX
  |
  |  (5) Exchange code -> tokens
  v
Attacker (oauth_app.py)
  |
  |  (6) REST API calls
  v
https://gmail.googleapis.com / drive.googleapis.com / ...
```

---

## Setup

### 1. Create the OAuth2 application in GCP

1. Go to https://console.cloud.google.com/apis/credentials
2. Click **Create Credentials** -> **OAuth client ID**
3. If not already done, create a *Consent Screen*
  - Click "**Configure consent screen**"
  - On the Google Auth Platform page, **create a Branding**
  - Provide an application name, a support email, select **External**, and a contact email
4. Once the Branding is created, click "**Create an OAuth client ID**"
5. Type: **Web application**
6. Name: anything you want (e.g., "Auth Service")
7. **Authorized redirect URIs**: add the callback URL. `http://localhost:8080/callback` for local testing, then a real callback domain. The domain must be verified in **Google Search Console** to move the app to production, **but not if it stays in test mode**
6. Click **Create**
7. Copy the **Client ID** and **Client Secret**
8. Go to "**Audience**" and add the users who will be allowed to authenticate on the application (**required as long as the app is not published publicly**)

Publishing a public external application requires completing the "Branding" section, then going through the Google verification process. This is a manual review, quite lengthy, during which Google will ask many questions about the code, the purpose of the app, etc. Suffice to say, the app is likely to remain in test mode.

### 2. Enable the required APIs

In the same GCP project, enable via API -> Library:
- Gmail API (for `--action list-emails`)
- Google Drive API (for `--action list-drive`)
- Cloud Resource Manager API (for `--action list-gcp`)

Then, back in API -> Credentials, go to "Data access" and grant the desired non-sensitive and sensitive scopes. Restricted scopes require a paid security assessment from Google.

### 3. Configure the scripts

Edit `oauth_app.py` and replace:
```python
CLIENT_ID     = "YOUR_CLIENT_ID.apps.googleusercontent.com"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
```

Or use environment variables:
```bash
export GOOGLE_CLIENT_ID="xxx.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="xxx"
```

### 4. Start the server

```bash
cd ILLICIT_CONSENT
python3 oauth_app.py
```

Open `http://localhost:8080/` in a browser (or send the link to the victim). Click **"Sign in with Google"**, authenticate, accept the requested scopes (authentication may take a few minutes at this stage, probably because the app is still in test mode).

Tokens are saved in `tokens.json`.

### 5. Exfiltrate data

```bash
# User information
python3 exfil_tokens.py -a userinfo

# List recent emails (if gmail.readonly scope was granted)
python3 exfil_tokens.py -a list-emails -l 5

# List Drive files (if drive.readonly scope was granted)
python3 exfil_tokens.py -a list-drive -l 10

# List GCP projects (if cloud-platform scope was granted)
python3 exfil_tokens.py -a list-gcp

# All actions
python3 exfil_tokens.py -a all

# Refresh the access_token
python3 exfil_tokens.py -a refresh
```

Depending on the requested scopes, the obtained access token can also be used with the gcloud CLI to interact with GCP.

---

## Available scopes

| Scope | Level | Description |
|-------|-------|-------------|
| `openid` | Non-sensitive | OpenID Connect authentication |
| `email` | Non-sensitive | Email address |
| `profile` | Non-sensitive | Name, photo |
| `https://www.googleapis.com/auth/gmail.readonly` | Sensitive | Read emails |
| `https://www.googleapis.com/auth/drive.readonly` | Sensitive | Read Drive files |
| `https://www.googleapis.com/auth/cloud-platform` | Sensitive | Full GCP access |

**Warning:** "Sensitive" scopes display a "Google hasn't verified this app" warning if the app is not in production. The victim must click **"Continue"** to bypass it.

---

## Detection

On the Google Workspace side, the admin can see in the logs:
- **Security Investigation Tool** -> `oauth2.authorize` events
- **Admin Console** -> Reports -> OAuth -> authorized applications
- `application_name` field = the malicious app's name

---

## Limitations vs Azure

| Aspect | Azure | Google |
|--------|-------|--------|
| Multi-tenant app | No verification needed | "Testing" mode = aggressive warning |
| Tokens | Access + Refresh JWT | Access + Refresh + ID token |
| Accessible APIs | MS Graph, ARM... | Gmail, Drive, GCP... |
| Admin control | Admin consent | App access control + Context-Aware |
| Attack realism | Very high | Medium (visible warning) |

---

## Google constraints (2019+ hardening)

1. **Publishing status**: "Testing" mode = max 100 users + warning
2. **Google verification**: 4-6 weeks for Production mode
3. **Security assessment**: required for Restricted scopes in production ($15k-$75k)
4. **Verified domain**: `redirect_uri` must belong to a Google Search Console domain for production (or `localhost` for dev)

---

## Cleanup

```bash
rm tokens.json
```
