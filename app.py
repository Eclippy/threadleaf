"""Threadleaf: a local, read-only Reddit client using Python's standard library."""
import base64
import html
import json
import queue
import re
import secrets
import threading
import time
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

REDIRECT = "http://127.0.0.1:8765/callback"
DEMO = [
    {"id": "demo1", "title": "Welcome to Threadleaf", "author": "demo",
     "score": 42, "num_comments": 2, "selftext":
     "A small, focused reader for Reddit. Choose a community, select Hot, New, or Top, "
     "then load its latest posts. Select a post to read its text and top-level comments.\n\n"
     "These are fictional sample posts. Connect your approved Reddit client ID to load live content.",
     "permalink": "", "subreddit": "sample"},
    {"id": "demo2", "title": "A calmer way to follow a community", "author": "demo",
     "score": 18, "num_comments": 1, "selftext":
     "Threadleaf only loads content when you ask. Tokens and posts stay in memory. "
     "There is no background collection, posting, voting, or analytics.",
     "permalink": "", "subreddit": "sample"},
]


def request_json(url, headers, data=None):
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        messages = {401: "Session expired or credentials rejected. Connect again.",
                    403: "Reddit denied access. Check your approval and community access.",
                    404: "That community or post could not be found.",
                    429: "Reddit's rate limit was reached. Wait before trying again."}
        raise RuntimeError(messages.get(error.code, f"Reddit returned HTTP {error.code}.")) from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("Could not reach Reddit. Check your connection and try again.") from None


def validate_callback(path, expected):
    parsed = urllib.parse.urlsplit(path)
    query = urllib.parse.parse_qs(parsed.query)
    if parsed.path != "/callback":
        raise ValueError("Unknown callback path.")
    state = query.get("state", [""])[0]
    if not state or not secrets.compare_digest(state, expected):
        raise ValueError("Sign-in state did not match. Start sign-in again.")
    if "error" in query:
        raise RuntimeError("Reddit sign-in was declined.")
    code = query.get("code", [""])[0]
    if not code:
        raise ValueError("Reddit did not return an authorization code.")
    return code


class Reddit:
    def __init__(self):
        self.token = ""
        self.expires = 0
        self.user_agent = "desktop:threadleaf:0.1"

    def connect(self, client_id, username):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", client_id):
            raise ValueError("Enter your approved installed-app client ID.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,20}", username):
            raise ValueError("Enter your Reddit username without u/.")
        self.token = ""
        self.user_agent = f"desktop:threadleaf:0.1 (by /u/{username})"
        state = secrets.token_urlsafe(32)
        result = {}

        class Callback(BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    result["code"] = validate_callback(self.path, state)
                    status, body = 200, "Authorization received. Return to Threadleaf to check connection status."
                except ValueError as error:
                    status, body = 400, str(error)
                except RuntimeError as error:
                    result["error"] = str(error)
                    status, body = 400, str(error)
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body.encode())

            def log_message(self, *_):
                pass  # Never log authorization codes or callback URLs.

        try:
            server = HTTPServer(("127.0.0.1", 8765), Callback)
        except OSError:
            raise RuntimeError("Port 8765 is in use. Close the other client and try again.") from None
        with server:
            server.timeout = 1
            url = "https://www.reddit.com/api/v1/authorize?" + urllib.parse.urlencode({
                "client_id": client_id, "response_type": "code", "state": state,
                "redirect_uri": REDIRECT, "duration": "temporary", "scope": "read"})
            if not webbrowser.open(url):
                raise RuntimeError("Could not open the browser. Set a default browser and try again.")
            deadline = time.monotonic() + 180
            while not result and time.monotonic() < deadline:
                server.handle_request()
        if "error" in result:
            raise RuntimeError(result["error"])
        if "code" not in result:
            raise RuntimeError("Sign-in timed out. Try connecting again.")
        basic = base64.b64encode((client_id + ":").encode()).decode()
        token = request_json("https://www.reddit.com/api/v1/access_token", {
            "Authorization": "Basic " + basic, "User-Agent": self.user_agent,
            "Content-Type": "application/x-www-form-urlencoded"},
            urllib.parse.urlencode({"grant_type": "authorization_code", "code": result["code"],
                                    "redirect_uri": REDIRECT}).encode())
        if not token.get("access_token"):
            raise RuntimeError("Reddit did not issue an access token. Verify the app registration.")
        self.token = token["access_token"]
        self.expires = time.monotonic() + int(token.get("expires_in", 3600)) - 30
        return "Connected. Choose a community and load posts."

    def get(self, path):
        if not self.token or time.monotonic() >= self.expires:
            raise RuntimeError("Connect to Reddit first; sessions expire after about an hour.")
        return request_json("https://oauth.reddit.com" + path, {
            "Authorization": "bearer " + self.token, "User-Agent": self.user_agent})

    def posts(self, community, sort):
        if not re.fullmatch(r"[A-Za-z0-9_]{2,21}", community):
            raise ValueError("Enter a community name without r/, spaces, or links.")
        if sort not in ("hot", "new", "top"):
            raise ValueError("Choose Hot, New, or Top.")
        data = self.get(f"/r/{community}/{sort}?limit=25&raw_json=1&t=day")
        return [item["data"] for item in data["data"]["children"] if item["kind"] == "t3"]

    def comments(self, post_id):
        if not re.fullmatch(r"[a-z0-9]+", post_id):
            raise ValueError("Invalid post ID.")
        data = self.get(f"/comments/{post_id}?limit=20&depth=1&raw_json=1")
        return [item["data"] for item in data[1]["data"]["children"] if item["kind"] == "t1"]


class App:
    def __init__(self, root):
        self.root, self.api = root, Reddit()
        self.events, self.posts = queue.Queue(), []
        self.busy, self.demo, self.selected = False, True, None
        root.title("Threadleaf — Reddit reader")
        root.geometry("1060x720")
        root.minsize(760, 520)
        root.configure(bg="#f5f5ef")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f5f5ef")
        style.configure("TLabel", background="#f5f5ef", foreground="#223c31", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=6)
        outer = ttk.Frame(root, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Threadleaf", font=("Segoe UI", 26, "bold")).pack(anchor="w")
        ttk.Label(outer, text="A little space to read.").pack(anchor="w", pady=(0, 15))
        auth = ttk.Frame(outer)
        auth.pack(fill="x")
        ttk.Label(auth, text="Client ID").pack(side="left")
        self.client_id = ttk.Entry(auth, width=27)
        self.client_id.pack(side="left", padx=8)
        ttk.Label(auth, text="Reddit username").pack(side="left")
        self.username = ttk.Entry(auth, width=20)
        self.username.pack(side="left", padx=8)
        self.connect_button = ttk.Button(auth, text="Connect", command=self.connect)
        self.connect_button.pack(side="left")
        ttk.Button(auth, text="Demo", command=self.load_demo).pack(side="right")
        bar = ttk.Frame(outer)
        bar.pack(fill="x", pady=15)
        ttk.Label(bar, text="r/").pack(side="left")
        self.community = ttk.Entry(bar, width=24)
        self.community.insert(0, "Python")
        self.community.pack(side="left", padx=(4, 12))
        self.sort = ttk.Combobox(bar, values=["hot", "new", "top"], state="readonly", width=8)
        self.sort.set("hot")
        self.sort.pack(side="left")
        ttk.Button(bar, text="Load posts", command=self.load_posts).pack(side="left", padx=8)
        ttk.Button(bar, text="Open on Reddit ↗", command=self.open_post).pack(side="right")
        panes = ttk.Panedwindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes)
        self.listbox = tk.Listbox(left, font=("Segoe UI", 11), bg="#ffffff", fg="#223c31",
                                 selectbackground="#285d49", selectforeground="white",
                                 borderwidth=0, highlightthickness=0, exportselection=False)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.show_post)
        panes.add(left, weight=2)
        self.reader = ScrolledText(panes, wrap="word", font=("Segoe UI", 11), padx=20, pady=16,
                                   bg="#ffffff", fg="#223c31", relief="flat", state="disabled")
        panes.add(self.reader, weight=3)
        self.status = tk.StringVar()
        ttk.Label(outer, textvariable=self.status, wraplength=960).pack(anchor="w", pady=(12, 0))
        self.load_demo()
        root.after(80, self.poll)

    def run(self, work, done, message):
        if self.busy:
            return
        self.busy = True
        self.status.set(message)
        self.connect_button.configure(state="disabled")
        def worker():
            try:
                self.events.put((done, work(), None))
            except Exception as error:
                self.events.put((done, None, str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            done, value, error = self.events.get_nowait()
            self.busy = False
            self.connect_button.configure(state="normal")
            if error:
                self.status.set(error)
                messagebox.showerror("Threadleaf", error)
            else:
                done(value)
        except queue.Empty:
            pass
        self.root.after(80, self.poll)

    def connect(self):
        client_id, username = self.client_id.get().strip(), self.username.get().strip()
        self.run(lambda: self.api.connect(client_id, username), self.status.set,
                 "Finish sign-in in your browser. Waiting up to three minutes…")

    def load_demo(self):
        if self.busy:
            return
        self.demo = True
        self.populate(DEMO)
        self.status.set("Demo mode · Fictional sample content · No API access required")

    def populate(self, posts):
        self.posts, self.selected = posts, None
        self.listbox.delete(0, "end")
        for post in posts:
            self.listbox.insert("end", html.unescape(post.get("title", "Untitled")))
        self.write("Select a post to read." if posts else "No posts returned for this community.")
        self.status.set(f"Loaded {len(posts)} posts. Select a title to read.")

    def load_posts(self):
        community, sort = self.community.get().strip(), self.sort.get()
        def done(posts):
            self.demo = False
            self.populate(posts)
        self.run(lambda: self.api.posts(community, sort), done, "Loading posts…")

    def write(self, text):
        self.reader.configure(state="normal")
        self.reader.delete("1.0", "end")
        self.reader.insert("1.0", html.unescape(text))
        self.reader.configure(state="disabled")

    def show_post(self, _event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        post = self.posts[selection[0]]
        self.selected = post
        body = (f"{post['title']}\n\nr/{post['subreddit']} · u/{post['author']}\n"
                f"{post.get('score', 0)} points · {post.get('num_comments', 0)} comments\n\n"
                f"{post.get('selftext') or 'Link post — open on Reddit to view the linked content.'}")
        self.write(body)
        if self.demo:
            self.write(body + "\n\nSAMPLE COMMENT\n\ndemo: This is fictional preview content.")
            return
        if self.busy:
            self.status.set("Another request is running. Select this post again when it finishes.")
            return
        def done(comments):
            if self.selected is not post:
                self.status.set("Ready. Select a post to load its comments.")
                return
            text = "\n\nTOP-LEVEL COMMENTS\n"
            for comment in comments:
                text += f"\nu/{comment.get('author', '[deleted]')}\n{comment.get('body', '')}\n"
            self.write(body + text + ("\nNo comments yet." if not comments else ""))
            self.status.set(f"Loaded {len(comments)} top-level comments. Replies are available on Reddit.")
        self.run(lambda: self.api.comments(post["id"]), done, "Loading comments…")

    def open_post(self):
        if self.selected and re.fullmatch(r"/r/[A-Za-z0-9_]+/comments/[^\s]*",
                                         self.selected.get("permalink", "")):
            webbrowser.open("https://www.reddit.com" + self.selected["permalink"])
        else:
            self.status.set("Select a live post first. Sample posts have no Reddit URL.")


if __name__ == "__main__":
    window = tk.Tk()
    App(window)
    window.mainloop()
