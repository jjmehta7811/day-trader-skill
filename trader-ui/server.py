#!/usr/bin/env python3
"""Trader UI: a local web page that runs the day-trader-skill tools with buttons.

Standard library only. Binds to 127.0.0.1 (your machine only).
It never places orders: the broker step only shows tickets. Approvals stay in Claude.

Run from the folder that holds (or will hold) your `trader/` data folder:
    python C:\\Janak\\Git\\day-trader-skill\\trader-ui\\server.py
"""
import argparse, json, os, re, subprocess, sys, threading, time, uuid, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
VERSION = "2026-10-28.4"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

def T(name, label, flag=None, kind="text", ph="", options=None, positional=False, multi=False, required=False, default=""):
    return dict(name=name, label=label, flag=flag, kind=kind, ph=ph, options=options or [],
                positional=positional, multi=multi, required=required, default=default)

SYM = T("symbol", "Ticker", kind="text", ph="TSLA", positional=True, required=True)
WRITE = T("write", "Save result for the next step", "--write", "flag", default="1")

ACTIONS = {
 "scan_universe": dict(group="Find", title="Download stock list", desc="One-time (then weekly): ~5,900 US symbols from Nasdaq Trader.",
     script="trader-scanner/scan.py", sub=["universe"], params=[]),
 "scan_orb": dict(group="Find", title="Opening-range breakouts", desc="Stocks that closed above their opening range today. Best run 10:15 AM ET onward. Leave Tickers empty to scan the whole universe (slow); add tickers for a quick run.",
     script="trader-scanner/scan.py", sub=["orb"], params=[
        T("symbols", "Tickers (optional)", "--symbols", ph="TSLA,NVDA,AMD"),
        T("at", "Cut the clock at (ET)", "--at", ph="10:15"),
        T("or_minutes", "Opening range minutes", "--or-minutes", "number", ph="15"),
        T("min_price", "Min price", "--min-price", "number", ph="5"),
        T("min_volume", "Min volume", "--min-volume", "number", ph="500000"),
        T("limit", "Scan first N symbols", "--limit", "number", ph="300"),
        T("show", "Hits to show", "--show", "number", ph="20")]),
 "scan_daily": dict(group="Find", title="Daily setups", desc="Pre-market setups from daily closes: flags, oversold bounces.",
     script="trader-scanner/scan.py", sub=["daily"], params=[
        T("symbols", "Tickers (optional)", "--symbols", ph="TSLA,NVDA,AMD"),
        T("min_price", "Min price", "--min-price", "number", ph="5"),
        T("min_volume", "Min volume", "--min-volume", "number", ph="500000"),
        T("limit", "Scan first N symbols", "--limit", "number", ph="300"),
        T("show", "Hits to show", "--show", "number", ph="20")]),
 "news": dict(group="Find", title="News monitor", desc="Headlines and SEC 8-Ks for your tickers, plus how far each moved today.",
     hint="News checks one ticker at a time (headlines, then SEC filings unless you tick 'Headlines only') and prints everything at the end. Roughly 1 to 3 seconds per ticker, so 10 tickers take 15 to 30 seconds and 100 tickers several minutes. Use Stop if it takes too long.",
     script="trader-news/news.py", sub=[], params=[
        T("tickers", "Tickers", "--tickers", ph="TSLA NVDA", multi=True),
        T("hours", "Look back (hours)", "--hours", "number", ph="12"),
        T("no_sec", "Headlines only (skip SEC)", "--no-sec", "flag"),
        T("all", "Include items already shown before", "--all", "flag"),
        T("json", "", "--json", "hidden")]),
 "entry_check": dict(group="Plan", title="Entry timer", desc="Is the setup waiting, triggered or expired right now?",
     script="trader-entry/entry.py", sub=["check"], params=[SYM,
        T("setup", "Setup", "--setup", "select", options=["orb", "level"]),
        T("level", "Level (for 'level')", "--level", "number", ph="364.00"),
        T("or_minutes", "Opening range minutes", "--or-minutes", "number", ph="15"),
        T("interval", "Bars", "--interval", "select", options=["5m", "1m"]), WRITE]),
 "exit_plan": dict(group="Plan", title="Exit planner", desc="Stop and target before you enter. With a saved entry, leave the boxes empty to use its defaults.",
     script="trader-exit/exit.py", sub=["plan"], params=[
        T("symbol", "Ticker (optional)", "--symbol", ph="TSLA"),
        T("entry", "Entry price", "--entry", "number"),
        T("or_high", "Range high", "--or-high", "number"),
        T("or_low", "Range low", "--or-low", "number"),
        T("stop", "Stop", "--stop", ph="or-mid | or-low | pct:1 | price:358.32"),
        T("target", "Target", "--target", ph="1R | 2R | price:370"),
        T("flat_by", "Flat by (ET)", "--flat-by", ph="15:55"), WRITE]),
 "plan_show": dict(group="Plan", title="Show current plan", desc="Print the saved stop/target plan.",
     script="trader-exit/exit.py", sub=["show"], params=[]),
 "tm_run": dict(group="Plan", title="Time Machine", desc="Replays the plan 10,000 times plus every past day the setup fired. Read the odds before risking a dollar.",
     script="trader-timemachine/timemachine.py", sub=["run"], params=[
        T("replays", "Replays", "--replays", "number", ph="10000"),
        T("seed", "Seed (repeatable)", "--seed", "number", ph="19"), WRITE]),
 "tm_chart": dict(group="Plan", title="Fan chart", desc="ASCII chart of the replays.",
     script="trader-timemachine/timemachine.py", sub=["chart"], params=[]),
 "size": dict(group="Size & check", title="Budget: size the position", desc="Shares so the stop loss stays within your max loss.",
     script="trader-budget/size.py", sub=[], params=[
        T("budget", "Budget $ (override)", "--budget", "number", ph="5000"),
        T("limit", "Limit order", "--limit", "flag"), WRITE]),
 "risk": dict(group="Size & check", title="Risk check", desc="PASS or BLOCK against your limits, with the reason.",
     script="trader-risk/check.py", sub=[], params=[]),
 "tickets": dict(group="Size & check", title="Show order tickets (read only)", desc="Plain-words tickets. Placing and approving orders stays in Claude with your explicit yes.",
     script="trader-broker/ticket.py", sub=["show"], params=[]),
 "alerts_clock": dict(group="Monitor", title="Is the market open?", desc="NYSE clock.",
     script="trader-alerts/alerts.py", sub=["clock"], params=[]),
 "alerts_quote": dict(group="Monitor", title="Quotes", desc="Latest delayed quotes.",
     script="trader-alerts/alerts.py", sub=["quote"], params=[
        T("symbols", "Tickers", None, positional=True, multi=True, ph="TSLA NVDA"),
        T("holdings", "Add holdings and plan tickers", "--holdings", "flag")]),
 "alerts_list": dict(group="Monitor", title="List alert rules", desc="Your stop, target and flat-by-close rules.",
     script="trader-alerts/alerts.py", sub=["list"], params=[]),
 "alerts_check": dict(group="Monitor", title="Check alerts now", desc="Rings whatever has hit (once).",
     script="trader-alerts/alerts.py", sub=["check"], params=[]),
 "analyst": dict(group="Research", title="Earnings analyst", desc="Quarters, growth and EPS from SEC filings. Needs your name and email in Settings.",
     script="trader-analyst/facts.py", sub=[], params=[
        T("tickers", "Tickers", None, positional=True, multi=True, required=True, ph="AAPL KO"),
        T("quarters", "Quarters", "--quarters", "number", ph="8")]),
 "pelosi_index": dict(group="Research", title="Congress trades: filings", desc="Periodic transaction reports from the House Clerk.",
     script="trader-pelosi/ptr.py", sub=["index"], params=[
        T("member", "Member", "--member", ph="pelosi"),
        T("since", "Since", "--since", ph="2026-09-01"),
        T("limit", "Limit", "--limit", "number", ph="20")]),
 "pelosi_new": dict(group="Research", title="Congress trades: new since last check", desc="Filings not seen at your last check.",
     script="trader-pelosi/ptr.py", sub=["new"], params=[
        T("member", "Member", "--member", ph="pelosi")]),
}

NUM = re.compile(r"^-?\d+(\.\d+)?$")
SAFE = re.compile(r"^[A-Za-z0-9 ,.:_\-+/%$@^=]*$")

def build_cmd(action, values):
    spec = ACTIONS.get(action)
    if not spec:
        raise ValueError("unknown action")
    script = REPO / spec["script"]
    if not script.exists():
        raise ValueError("missing " + spec["script"])
    base = [sys.executable, "-u", str(script)] + list(spec["sub"])
    cmd, positional = [], []
    for p in spec["params"]:
        v = values.get(p["name"])
        if p["kind"] == "hidden":
            cmd.append(p["flag"])
            continue
        if p["kind"] == "flag":
            if v in (True, "1", 1, "true", "on"):
                cmd.append(p["flag"])
            continue
        v = ("" if v is None else str(v)).strip()
        if not v:
            if p["required"]:
                raise ValueError(p["label"] + " is required")
            continue
        if not SAFE.match(v):
            raise ValueError(p["label"] + " has characters that are not allowed")
        if p["kind"] == "number" and not NUM.match(v):
            raise ValueError(p["label"] + " must be a number")
        if p["kind"] == "select" and v not in p["options"]:
            raise ValueError(p["label"] + " is not a valid choice")
        csv = p["name"] == "symbols" and p["flag"]  # --symbols wants TSLA,NVDA in one value
        if csv: v = ",".join(x for x in re.split(r"[ ,]+", v) if x)
        parts = re.split(r"[ ,]+", v) if p["multi"] else [v]
        parts = [x.upper() if p["name"] in ("symbol", "symbols", "tickers") else x for x in parts if x]
        if p["positional"]:
            positional += parts
        elif p["multi"]:
            cmd += [p["flag"]] + parts
        else:
            cmd += [p["flag"], parts[0]]
    return base + positional + cmd  # positionals first: --write takes an optional path

JOBS = {}
LOCK = threading.Lock()

MAX_SECONDS = 600

def watchdog(job):
    for _ in range(MAX_SECONDS):
        if job["done"]: return
        time.sleep(1)
    p = job.get("proc")
    if p and not job["done"]:
        job["out"] += "\n[ui] stopped after %d seconds: the tool was taking too long. Try fewer tickers or tick 'Headlines only'.\n" % MAX_SECONDS
        try: p.kill()
        except Exception: pass

def run_job(job, cmd, cwd):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", NO_COLOR="1")
    try:
        job["proc"] = proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for line in proc.stdout:
            job["out"] += ANSI.sub("", line)
        proc.wait()
        job["code"] = proc.returncode
    except Exception as e:
        job["out"] += "\n[ui error] %s\n" % e
        job["code"] = -1
    job["done"] = True
    job["ended"] = time.time()

CONFIG_KEYS = ["sec_user_agent", "budget", "max_loss_per_trade_usd", "max_daily_loss_usd",
               "max_trades_per_day", "min_reward_risk", "no_entries_after", "flat_by", "paper"]

class H(BaseHTTPRequestHandler):
    workdir = Path.cwd()
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)
    def _json(self, code, obj): self._send(code, json.dumps(obj))
    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")
    def _local(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")
    def cfg_path(self): return self.workdir / "trader" / "config.json"
    def read_cfg(self):
        p = self.cfg_path()
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        ex = REPO / "trader-budget" / "config.example.json"
        return json.loads(ex.read_text(encoding="utf-8")) if ex.exists() else {}
    def do_GET(self):
        if not self._local(): return self._json(403, {"error": "local only"})
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html")
        if path == "/api/spec":
            return self._json(200, dict(actions=ACTIONS, workdir=str(self.workdir), version=VERSION))
        if path == "/api/config":
            cfg = self.read_cfg()
            return self._json(200, dict(keys=CONFIG_KEYS, config={k: cfg.get(k) for k in CONFIG_KEYS},
                                        exists=self.cfg_path().exists()))
        if path in ("/api/watchlist", "/api/shortlist"):
            f = self.workdir / "trader" / ("watchlist.json" if path.endswith("watchlist") else "shortlist.json")
            try:
                return self._json(200, json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"hits": [], "tickers": []})
            except Exception as e:
                return self._json(200, {"hits": [], "tickers": [], "error": str(e)})
        if path.startswith("/api/job/"):
            j = JOBS.get(path.rsplit("/", 1)[1])
            if not j: return self._json(404, {"error": "no such job"})
            el = int((j.get("ended") or time.time()) - j["started"])
            return self._json(200, dict(out=j["out"], done=j["done"], code=j["code"], cmd=j["label"], elapsed=el))
        self._json(404, {"error": "not found"})
    def do_POST(self):
        if not self._local(): return self._json(403, {"error": "local only"})
        try:
            data = self._body()
        except Exception:
            return self._json(400, {"error": "bad json"})
        path = self.path
        if path == "/api/run":
            try:
                cmd = build_cmd(data.get("action"), data.get("values") or {})
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            (self.workdir / "trader").mkdir(exist_ok=True)
            jid = uuid.uuid4().hex[:10]
            label = " ".join(Path(cmd[2]).name if i == 2 else c for i, c in enumerate(cmd) if i != 1)
            job = dict(out="", done=False, code=None, label=label, started=time.time())
            with LOCK: JOBS[jid] = job
            threading.Thread(target=run_job, args=(job, cmd, str(self.workdir)), daemon=True).start()
            threading.Thread(target=watchdog, args=(job,), daemon=True).start()
            return self._json(200, dict(job=jid))
        if path == "/api/cancel":
            j = JOBS.get(data.get("job"))
            if j and not j["done"] and j.get("proc"):
                try: j["proc"].kill()
                except Exception: pass
            return self._json(200, {"ok": True})
        if path == "/api/shortlist":
            tk = [str(t).upper() for t in (data.get("tickers") or [])]
            if not tk or any(not re.match(r"^[A-Z0-9.\-]{1,10}$", t) for t in tk):
                return self._json(400, {"error": "pick at least one valid ticker"})
            (self.workdir / "trader").mkdir(exist_ok=True)
            doc = {"created_by": "trader-ui", "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "tickers": tk}
            (self.workdir / "trader" / "shortlist.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
            return self._json(200, {"ok": True, "count": len(tk)})
        if path == "/api/config":
            try:
                cfg = self.read_cfg()
                for k, v in (data.get("config") or {}).items():
                    if k not in CONFIG_KEYS: continue
                    if k in ("budget", "max_loss_per_trade_usd", "max_daily_loss_usd", "max_trades_per_day", "min_reward_risk"):
                        v = float(v) if "." in str(v) else int(v)
                    if k == "paper": v = bool(v)
                    cfg[k] = v
                self.cfg_path().parent.mkdir(exist_ok=True)
                self.cfg_path().write_text(json.dumps(cfg, indent=2), encoding="utf-8")
                return self._json(200, {"ok": True})
            except Exception as e:
                return self._json(400, {"error": str(e)})
        self._json(404, {"error": "not found"})

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workdir", default=os.getcwd(), help="folder that holds trader/ (default: current folder)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    H.workdir = Path(a.workdir).resolve()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    url = "http://127.0.0.1:%d" % a.port
    print("Trader UI running at %s\nData folder: %s\nPress Ctrl+C to stop." % (url, H.workdir / "trader"))
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nStopped.")

if __name__ == "__main__":
    main()
