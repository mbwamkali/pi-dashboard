#!/usr/bin/env python3
"""One-time Google sign-in for the dashboard.

Needs client_secret.json (from Google Cloud, see README) in this folder.
Opens a browser so you can approve read-only access to Calendar and Tasks,
then saves token.json next to this script and lists your calendars and task
lists so you can pick which ones to show in config.json.

Run it on any computer with a web browser; then copy token.json to the Pi.
    python authorize.py           sign in (or reuse token.json) and list calendars
    python authorize.py --list    just list, using the existing token.json
"""

import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

HERE = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET = os.path.join(HERE, "client_secret.json")
TOKEN = os.path.join(HERE, "token.json")
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks.readonly",
]


def get_creds(list_only):
    creds = None
    if os.path.exists(TOKEN):
        creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
        if not creds.valid and creds.refresh_token:
            creds.refresh(Request())
    if not creds or not creds.valid:
        if list_only:
            sys.exit("No valid token.json yet. Run: python authorize.py")
        if not os.path.exists(CLIENT_SECRET):
            sys.exit("client_secret.json is missing. See README, step 'Google setup'.")
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    with open(TOKEN, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    return creds


def main():
    creds = get_creds("--list" in sys.argv)
    print(f"Signed in. Saved {TOKEN}\n")

    cal = build("calendar", "v3", credentials=creds, cache_discovery=False)
    print("Calendars (shown by default: the ones ticked in Google Calendar, marked *):")
    for c in cal.calendarList().list().execute().get("items", []):
        mark = "*" if c.get("selected") else " "
        print(f"  {mark} {c.get('summaryOverride') or c['summary']}\n      id: {c['id']}")

    tasks = build("tasks", "v1", credentials=creds, cache_discovery=False)
    print("\nTask lists (shown by default: the first one):")
    for l in tasks.tasklists().list().execute().get("items", []):
        print(f"    {l['title']}\n      id: {l['id']}")
    print('\nTo choose, put names or ids in config.json under "calendars" and "task_lists".')


if __name__ == "__main__":
    main()
