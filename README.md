# Threadleaf

A small standalone desktop Reddit reader. Python 3.10+ and Tkinter are the only
requirements; there are no third-party Python packages.

## Run

On Windows, double-click `Launch Threadleaf.cmd`, or run `python app.py`.
The application starts with clearly labeled fictional demo posts. Demo mode
does not contact Reddit.

## Live Reddit access

1. Obtain Reddit approval and register Threadleaf as an **installed app**.
2. Register this exact redirect URI: `http://127.0.0.1:8765/callback`.
3. Enter that app's client ID and your Reddit username in Threadleaf.
4. Click **Connect** and authorize the `read` permission in your browser.
5. Enter a community name, choose hot/new/top, then click **Load posts**.

No client secret is used. Sign-in expires after approximately one hour; connect
again to continue. The callback listener binds only to loopback and closes after
sign-in or a three-minute timeout. OAuth state is checked and callback URLs are
not logged. Tokens and content are held in process memory, not saved to disk.

## Implemented scope

- Load up to 25 posts from one named subreddit; top uses the current day.
- Display post text and up to 20 top-level comments.
- Open the selected discussion on Reddit in the default browser.
- Fictional offline demo for reviewing the interface before API approval.
- User-triggered loading; no background polling, analytics, or data export.

This prototype does not implement voting, posting, saving, subscribed feeds,
refresh tokens, pagination, media rendering, or nested comment expansion.
Live authentication and API behavior require approved credentials and have not
been verified against a live account. Offline tests cover callback validation,
API request construction/error handling, and a GUI smoke check.

## Review and sharing

`APPLICATION.txt` describes this implementation for an access application.
Source repository: https://github.com/Eclippy/threadleaf
Download the source using GitHub's **Code > Download ZIP** menu.

## Tests

Run `python -m unittest discover -s tests -v` from this folder.

## API references

- https://github.com/reddit-archive/reddit/wiki/OAuth2 (archived protocol reference)
- https://www.reddit.com/dev/api/
- https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy
