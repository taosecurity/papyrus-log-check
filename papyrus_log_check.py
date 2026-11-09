#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Richard Bejtlich
"""papyrus-log-check: check Starfield Papyrus logs against per-mod rules.

Input is one of:
  - a Papyrus log file (Papyrus.0.log, or any text file in that format),
  - a folder holding Papyrus.N.log files (subfolders are searched; User\\ logs are skipped),
  - a zip holding the same, read in memory without unpacking.
A folder or zip may also hold plugins.txt (which plugins were active) and crash logs. Optional
metadata a log collector may add (manifest.json, events.txt) is read when present.

It reports PASS / FAIL / NOT SEEN for each rule in each mod's rule file, plus general problems
(Papyrus errors naming the mod's scripts, crash logs, suspended stacks).

Read-only: it never changes the logs or the rule files.
Standard library only. MIT licence (see LICENSE).

Usage:
  python -I papyrus_log_check.py INPUT --rules mymod.logrules.json [--rules other.json]
  python -I papyrus_log_check.py INPUT --root DIR [--mods A,B]
  python -I papyrus_log_check.py --logs-dir DIR ...      (newest zip in DIR)
Exit code: 0 = no FAIL, 1 = at least one FAIL, 2 = usage, rule file or input error.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import zipfile

TOOL = "papyrus-log-check"
VERSION = "0.2.0"

PASS, FAIL, NOT_SEEN, NOT_LOADED = "PASS", "FAIL", "NOT SEEN", "NOT LOADED"

STAMP_RE = re.compile(r"(\d{8}-\d{6})")
PAPYRUS_RE = re.compile(r"(?:^|/)papyrus\.(\d+)\.log$", re.I)
ERRLINE_RE = re.compile(r"^\[(\d\d:\d\d:\d\d)\]\s+(error|warning):\s*(.*)$", re.I)
TIME_RE = re.compile(r"^\[(\d\d:\d\d:\d\d)\]")
SUSPENDED_RE = re.compile(r"suspended stack|dumping stack", re.I)
CRASH_RE = re.compile(r"(?:^|/)(?:crashlogs/[^/]+|crashlog[^/]*\.txt|crash-[^/]*\.log)$", re.I)
EVENT_HEAD_RE = re.compile(r"^====\s+(\S+)\s+(.+?)\s+ID\s+(\d+)\s*$")

ZIP, FOLDER, LOG_FILE = "zip", "folder", "log file"


# ----------------------------------------------------------------------------- input

def _by_depth(keys):
    """Shallowest path first, then alphabetical."""
    return sorted(keys, key=lambda k: (k.count("/"), k))


class Package:
    """The logs to check: a zip (read in memory, entry names may use \\ or /), a folder, or one log file."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(os.path.normpath(path))
        self.zf = None
        self.entries = {}  # lower-case path with / -> (key for _raw, path with /)
        if os.path.isdir(path):
            self.kind = FOLDER
            for dirpath, dirnames, filenames in os.walk(path):
                dirnames.sort()
                for fn in filenames:
                    full = os.path.join(dirpath, fn)
                    norm = os.path.relpath(full, path).replace("\\", "/")
                    self.entries[norm.lower()] = (full, norm)
        elif not os.path.isfile(path):
            raise FileNotFoundError(f"not found: {path}")
        elif path.lower().endswith(".zip") or zipfile.is_zipfile(path):
            self.kind = ZIP
            try:
                self.zf = zipfile.ZipFile(path)
            except zipfile.BadZipFile as e:
                raise ValueError(f"{self.name}: not a readable zip ({e})")
            for info in self.zf.infolist():
                if info.is_dir():
                    continue
                norm = info.filename.replace("\\", "/").lstrip("/")
                self.entries[norm.lower()] = (info.filename, norm)
        else:
            self.kind = LOG_FILE
            self.entries[self.name.lower()] = (path, self.name)
        self.manifest = self._collector_manifest()
        self.plugins = self._plugins()
        self.logs = self._papyrus_logs()
        self.sha256 = self._sha256()

    def _raw(self, key):
        if self.zf is not None:
            return self.zf.read(key)
        with open(key, "rb") as f:
            return f.read()

    def has(self, norm_lower):
        return norm_lower in self.entries

    def text(self, norm_lower):
        raw = self._raw(self.entries[norm_lower][0])
        for enc in ("utf-8-sig", "cp1252"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                pass
        return raw.decode("utf-8", errors="replace")

    def _sha256(self):
        """A zip or log file: the file's hash. A folder: one hash over the logs and plugins.txt that were read."""
        h = hashlib.sha256()
        if self.kind != FOLDER:
            with open(self.path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            return h.hexdigest()
        used = [log["path"].lower() for log in self.logs]
        if self._plugins_key:
            used.append(self._plugins_key)
        for key in sorted(used):
            h.update(self.entries[key][1].encode("utf-8") + b"\0")
            h.update(self._raw(self.entries[key][0]))
        return h.hexdigest()

    def _json(self, name):
        if not self.has(name):
            return None
        try:
            return json.loads(self.text(name))
        except ValueError:
            return None

    def _collector_manifest(self):
        """A log collector's manifest.json at the top level, or {}. A manifest.json without a 'tool' field
        belongs to something else and is ignored."""
        m = self._json("manifest.json")
        return m if isinstance(m, dict) and m.get("tool") else {}

    def _find(self, basename):
        keys = [k for k in self.entries if os.path.basename(k) == basename]
        return _by_depth(keys)[0] if keys else None

    def _plugins(self):
        """plugins.txt as {lower name: active}, or None when there is none."""
        self._plugins_key = None if self.kind == LOG_FILE else self._find("plugins.txt")
        if self._plugins_key is None:
            return None
        out = {}
        for line in self.text(self._plugins_key).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            active = line.startswith("*")
            out[line.lstrip("*").strip().lower()] = active
        return out

    def _read_log(self, key, norm):
        lines = self.text(key).splitlines()
        times = [m.group(1) for m in (TIME_RE.match(l) for l in lines) if m]
        return {"name": os.path.basename(norm), "path": norm, "lines": lines,
                "first": times[0] if times else "", "last": times[-1] if times else ""}

    def _papyrus_logs(self):
        """Papyrus.N.log files, oldest first (.2 before .1 before .0). A log file given directly is used whatever its name."""
        if self.kind == LOG_FILE:
            key, (_, norm) = next(iter(self.entries.items()))
            return [self._read_log(key, norm)]
        found = []
        for key, (_, norm) in self.entries.items():
            m = PAPYRUS_RE.search(key)
            if m and "/user/" not in "/" + key:
                found.append((int(m.group(1)), key.count("/"), norm))
        found.sort(key=lambda x: (-x[0], x[1], x[2]))
        return [self._read_log(norm.lower(), norm) for _, _, norm in found]

    def named_logs(self, names):
        """Other log files (e.g. an SFSE plugin's own log), matched by file name, case-insensitive."""
        want = {n.lower() for n in names}
        logs = []
        for key, (_, norm) in sorted(self.entries.items()):
            if os.path.basename(key) in want:
                logs.append(dict(self._read_log(key, norm), first="", last=""))
        return logs

    def sfse_dlls(self):
        """SFSE plugin DLL names (lower case): from a collector's manifest listing, else the .dll files in the
        folder or zip. None when neither says anything."""
        listing = (self.manifest.get("listing") or {}).get("sfsePluginDlls")
        if listing is not None:
            return {str(d.get("name", "")).lower() for d in listing if isinstance(d, dict)}
        dlls = {os.path.basename(k) for k in self.entries if k.endswith(".dll")}
        return dlls or None

    def crash_logs(self):
        out = []
        for key, (_, norm) in sorted(self.entries.items()):
            if CRASH_RE.search(key):
                txt = self.text(key)
                code = re.search(r"Exception Code:\s*(\S+)", txt)
                addr = re.search(r"Exception Address:\s*(.+)", txt)
                out.append({"file": norm,
                            "exception": code.group(1) if code else "",
                            "address": addr.group(1).strip() if addr else ""})
        return out

    def events(self):
        """Windows Application Error / Hang entries from a collector's events.txt."""
        key = None if self.kind == LOG_FILE else self._find("events.txt")
        if key is None:
            return []
        out = []
        for line in self.text(key).splitlines():
            m = EVENT_HEAD_RE.match(line)
            if m:
                out.append({"time": m.group(1), "source": m.group(2), "id": int(m.group(3))})
            elif out and line.strip() and "detail" not in out[-1]:
                out[-1]["detail"] = line.strip()[:200]
        return out

    def stamp(self):
        """yyyymmdd-hhmmss for report names: from the input's name, a manifest, or the newest log's file time."""
        m = STAMP_RE.search(self.name)
        if m:
            return m.group(1)
        created = str(self.manifest.get("created", ""))
        digits = re.sub(r"\D", "", created)
        if len(digits) >= 14:
            return digits[:8] + "-" + digits[8:14]
        if self.kind == ZIP:
            when = os.path.getmtime(self.path)
        else:
            times = [os.path.getmtime(self.entries[log["path"].lower()][0]) for log in self.logs]
            when = max(times) if times else os.path.getmtime(self.path)
        return datetime.datetime.fromtimestamp(when).strftime("%Y%m%d-%H%M%S")


# ----------------------------------------------------------------------------- rules

def load_rules(path):
    with open(path, encoding="utf-8-sig") as f:
        r = json.load(f)
    for key in ("mod", "prefix"):
        if key not in r:
            raise ValueError(f"{path}: missing '{key}'")
    r.setdefault("plugins", [])
    r.setdefault("dlls", [])
    r.setdefault("logs", [])
    if not r["plugins"] and not r["dlls"]:
        raise ValueError(f"{path}: needs 'plugins' (.esm) or 'dlls' (SFSE plugin DLLs)")
    r.setdefault("version", "")
    r.setdefault("names", [])
    r.setdefault("scripts", "")
    r.setdefault("expect", [])
    r.setdefault("order", [])
    r.setdefault("forbid", [])
    r.setdefault("ignore", [])
    r["_path"] = path
    return r


def fill(pattern, rules):
    return pattern.replace("{version}", re.escape(rules.get("version", "")))


def compile_re(pattern, rules, where):
    try:
        return re.compile(fill(pattern, rules))
    except re.error as e:
        raise ValueError(f"{rules['_path']}: bad regex in {where}: {e}")


def find_rule_files(root, mods=None):
    """Rule files: --mods names (project folders, which may be nested like Group\\Mod, or .json paths), else every
    <root>/*/testplan/logrules.json and <root>/*/*/testplan/logrules.json (mods kept inside a group folder)."""
    if mods:
        out = []
        for m in mods:
            p = m if m.lower().endswith(".json") else os.path.join(root, m, "testplan", "logrules.json")
            if not os.path.isfile(p):
                raise FileNotFoundError(f"no rule file for '{m}' (looked for {p})")
            out.append(p)
        return out
    out = []
    for d in sorted(os.listdir(root)):
        top = os.path.join(root, d)
        p = os.path.join(top, "testplan", "logrules.json")
        if os.path.isfile(p):
            out.append(p)
        if os.path.isdir(top):
            try:
                subs = sorted(os.listdir(top))
            except OSError:
                continue
            for s in subs:
                q = os.path.join(top, s, "testplan", "logrules.json")
                if os.path.isfile(q):
                    out.append(q)
    return out


def split_list(values):
    """Repeated options that may also hold comma lists: ['a,b', 'c'] -> ['a', 'b', 'c']."""
    return [x.strip() for v in values or [] for x in v.split(",") if x.strip()]


# ----------------------------------------------------------------------------- analysis

def all_lines(pkg):
    """(log index, line number 1-based, text) for every line, oldest log first."""
    for i, log in enumerate(pkg.logs):
        for n, text in enumerate(log["lines"], 1):
            yield i, n, text


def ref(pkg, i, n, text):
    return {"log": pkg.logs[i]["name"], "line": n, "text": text}


def error_blocks(pkg):
    """Papyrus error/warning lines with the stack frames that follow them."""
    blocks = []
    for i, log in enumerate(pkg.logs):
        lines = log["lines"]
        k = 0
        while k < len(lines):
            m = ERRLINE_RE.match(lines[k])
            if not m:
                k += 1
                continue
            block = {"log": log["name"], "line": k + 1, "kind": m.group(2).lower(),
                     "message": m.group(3).strip(), "text": lines[k], "stack": []}
            k += 1
            while k < len(lines) and not TIME_RE.match(lines[k]):
                s = lines[k].strip()
                if s and s.lower() != "stack:":
                    block["stack"].append(s)
                k += 1
            blocks.append(block)
    return blocks


def normalise_message(msg):
    """Group similar errors: drop FormIDs and numbers."""
    msg = re.sub(r"\([0-9A-Fa-f]{8}\)", "(…)", msg)
    return re.sub(r"\b\d+(\.\d+)?\b", "N", msg)


def normalise_frame(frame):
    """Group stack frames of different objects: '[ (FF00145F)].myscript.OnDeath() - ...' -> 'myscript.OnDeath() - ...'."""
    return re.sub(r"^\[.*?\]\.", "", frame)


def plugin_state(rules, pkg):
    """'active', 'inactive', 'missing' or 'unknown' (the input can't tell: no plugins.txt / no DLL listing).
    .esm plugins are looked up in plugins.txt, SFSE DLLs in the DLL listing."""
    states = []
    if rules["plugins"]:
        if pkg.plugins is None:
            states.append(None)
        else:
            states += [pkg.plugins.get(p.lower(), "missing") for p in rules["plugins"]]
    if rules["dlls"]:
        dlls = pkg.sfse_dlls()
        if dlls is None:
            states.append(None)
        else:
            states += [True if d.lower() in dlls else "missing" for d in rules["dlls"]]
    if any(s is True for s in states):
        return "active"
    if any(s is None for s in states):
        return "unknown"
    if any(s is False for s in states):
        return "inactive"
    return "missing"


class LogView:
    """The logs one mod's rules search: the Papyrus logs, or the files named in the rule file's 'logs'."""

    def __init__(self, logs):
        self.logs = logs


def in_note(rules, pkg):
    hay = (str(pkg.manifest.get("note", "")) + " " + pkg.name).lower()
    squash = re.sub(r"[^a-z0-9]", "", hay)
    for n in rules["names"] + [rules["mod"]] + [os.path.splitext(p)[0] for p in rules["plugins"] + rules["dlls"]]:
        n = n.lower()
        if n and (n in hay or (len(re.sub(r"[^a-z0-9]", "", n)) >= 4 and re.sub(r"[^a-z0-9]", "", n) in squash)):
            return True
    return False


def check_mod(rules, pkg, blocks, keep=50):
    res = {"mod": rules["mod"], "version": rules["version"], "rules_file": rules["_path"],
           "rule_file_version": rules.get("_rule_version", rules["version"]),
           "plugins": rules["plugins"] + rules["dlls"], "plugin_state": plugin_state(rules, pkg),
           "named_in_note": in_note(rules, pkg), "rules": [], "prefix_lines": 0,
           "first_prefix": None, "last_prefix": None,
           "logs": rules["logs"] or ["Papyrus logs"]}
    src = LogView(pkg.named_logs(rules["logs"])) if rules["logs"] else pkg
    if rules["logs"] and not src.logs:
        res["logs_missing"] = True

    prefix = compile_re(rules["prefix"], rules, "prefix")
    prefix_hits = [(i, n, t) for i, n, t in all_lines(src) if prefix.search(t)]
    res["prefix_lines"] = len(prefix_hits)
    if prefix_hits:
        res["first_prefix"] = ref(src, *prefix_hits[0])
        res["last_prefix"] = ref(src, *prefix_hits[-1])
    ran = bool(prefix_hits)

    if res["plugin_state"] in ("inactive", "missing"):
        res["status"] = NOT_LOADED
        return res

    # expect rules
    first_pos = {}
    for e in rules["expect"]:
        rx = compile_re(e["re"], rules, f"expect '{e['id']}'")
        hits = [(i, n, t) for i, n, t in all_lines(src) if rx.search(t)]
        need = int(e.get("min", 1))
        if len(hits) >= need:
            status = PASS
        elif e.get("always") and ran:
            status = FAIL
        elif hits:
            status = FAIL  # seen, but fewer times than required
        else:
            status = NOT_SEEN
        if hits:
            first_pos[e["id"]] = (hits[0][0], hits[0][1])
        other_version = []
        if not hits and "{version}" in e["re"]:  # seen with another version = wrong build installed?
            any_rx = re.compile(e["re"].replace("{version}", r"[0-9][\w.\-]*"))
            other_version = [ref(src, i, n, t) for i, n, t in all_lines(src) if any_rx.search(t)][:keep]
        res["rules"].append({"kind": "expect", "id": e["id"], "status": status, "min": need,
                             "always": bool(e.get("always")), "count": len(hits),
                             "pattern": fill(e["re"], rules), "means": e.get("means", ""),
                             "lines": [ref(src, *h) for h in hits[:keep]],
                             "other_version_lines": other_version})

    # order rules
    known = {e["id"] for e in rules["expect"]}
    for seq in rules["order"]:
        unknown = [x for x in seq if x not in known]
        if unknown:
            raise ValueError(f"{rules['_path']}: order names unknown expect ids {unknown}")
        missing = [x for x in seq if x not in first_pos]
        if missing:
            status, detail = NOT_SEEN, "not all seen: " + ", ".join(missing)
        else:
            pos = [first_pos[x] for x in seq]
            bad = [f"{seq[k]} before {seq[k - 1]}" for k in range(1, len(seq)) if pos[k] < pos[k - 1]]
            status, detail = (FAIL, "; ".join(bad)) if bad else (PASS, "in order")
        res["rules"].append({"kind": "order", "id": " > ".join(seq), "status": status, "detail": detail})

    # forbid rules
    for fb in rules["forbid"]:
        rx = compile_re(fb["re"], rules, f"forbid '{fb['id']}'")
        hits = [(i, n, t) for i, n, t in all_lines(src) if rx.search(t)]
        status = FAIL if hits else (PASS if ran else NOT_SEEN)
        res["rules"].append({"kind": "forbid", "id": fb["id"], "status": status, "count": len(hits),
                             "pattern": fill(fb["re"], rules), "means": fb.get("means", ""),
                             "lines": [ref(src, *h) for h in hits[:keep]]})

    # script errors naming our scripts
    if rules["scripts"]:
        srx = re.compile(rules["scripts"], re.I)
        ign = [re.compile(x["re"] if isinstance(x, dict) else x, re.I) for x in rules["ignore"]]
        ours = [b for b in blocks
                if (srx.search(b["message"]) or any(srx.search(s) for s in b["stack"]))
                and not any(r.search(b["message"]) for r in ign)]
        groups = {}
        for b in ours:
            key = (b["kind"], normalise_message(b["message"]), normalise_frame(b["stack"][0]) if b["stack"] else "")
            g = groups.setdefault(key, {"kind": b["kind"], "message": b["message"],
                                        "frame": key[2], "count": 0, "first": None})
            g["count"] += 1
            if g["first"] is None:
                g["first"] = {"log": b["log"], "line": b["line"], "text": b["text"]}
        errors = [g for g in groups.values() if g["kind"] == "error"]
        warnings = [g for g in groups.values() if g["kind"] == "warning"]
        status = FAIL if errors else (PASS if ran else NOT_SEEN)
        res["rules"].append({"kind": "script-errors", "id": "script errors", "status": status,
                             "count": sum(g["count"] for g in errors),
                             "warnings": sum(g["count"] for g in warnings),
                             "groups": sorted(groups.values(), key=lambda g: (g["kind"] != "error", -g["count"]))})

    statuses = [r["status"] for r in res["rules"]]
    if FAIL in statuses:
        res["status"] = FAIL
    elif not ran:
        res["status"] = NOT_SEEN
    else:
        res["status"] = PASS
    return res


def package_checks(pkg, blocks, our_blocks_ids):
    flags = []
    for c in pkg.crash_logs():
        flags.append({"kind": "crash log", "text": f"{c['file']} ({c['exception']} at {c['address']})"
                      if c["exception"] else c["file"], "data": c})
    for e in pkg.events():
        flags.append({"kind": "windows event", "text": f"{e['time']} {e['source']} ID {e['id']}: {e.get('detail', '')}",
                      "data": e})
    susp = [ref(pkg, i, n, t) for i, n, t in all_lines(pkg) if SUSPENDED_RE.search(t)]
    if susp:
        flags.append({"kind": "suspended stacks", "text": f"{len(susp)} line(s), first {susp[0]['log']}:{susp[0]['line']}",
                      "data": susp[:20]})
    for w in pkg.manifest.get("warnings", []) or []:
        flags.append({"kind": "collector warning", "text": str(w)})
    other = {}
    for b in blocks:
        if id(b) in our_blocks_ids:
            continue
        other.setdefault(b["log"], {"error": 0, "warning": 0})[b["kind"]] += 1
    info = [{"log": k, **v} for k, v in other.items()]
    return flags, info


def our_block_ids(results, blocks, rules_list):
    ids = set()
    for rules in rules_list:
        if not rules["scripts"]:
            continue
        srx = re.compile(rules["scripts"], re.I)
        for b in blocks:
            if srx.search(b["message"]) or any(srx.search(s) for s in b["stack"]):
                ids.add(id(b))
    return ids


# ----------------------------------------------------------------------------- report

def rel(path, root):
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path


def fmt_line(r):
    return f"{r['log']}:{r['line']}  {r['text'].strip()}"


def text_report(data, max_lines):
    out = []
    p = data["package"]
    m = p.get("manifest", {})
    out.append(f"{TOOL} {VERSION}, run {data['run']}")
    label = {ZIP: "Package", FOLDER: "Folder", LOG_FILE: "Log file"}.get(p.get("kind"), "Package")
    out.append(f"{label}: {p['name']}")
    out.append(f"  SHA-256 {p['sha256']}" + ("  (of the logs and plugins.txt read)" if p.get("kind") == FOLDER else ""))
    if m:
        w = m.get("window") or {}
        out.append(f"  Made {m.get('created', '?')} by {m.get('user', '?')} on {m.get('computer', '?')}; "
                   f"logs since {w.get('since', '?')} ({w.get('how', '?')})")
        if m.get("note"):
            out.append(f"  Note: {m['note']}")
        if m.get("game"):
            out.append(f"  Game {m['game']}")
    for log in p["logs"]:
        out.append(f"  {log['name']}: {log['count']} lines, {log['first']} to {log['last']}")
    if p["plugins_txt"] is False:
        out.append("  No plugins.txt: plugin checks skipped, every rule file is checked.")
    out.append("")
    out.append("Summary")
    for r in data["mods"]:
        counts = {}
        for x in r["rules"]:
            counts[x["status"]] = counts.get(x["status"], 0) + 1
        c = ", ".join(f"{v} {k.lower()}" for k, v in counts.items()) or "-"
        note = "named in note" if r["named_in_note"] else "not in note"
        out.append(f"  {r['status']:<10} {r['mod']} {r['version']}  ({note}; {c})")
    out.append("")
    for r in data["mods"]:
        out.append(f"== {r['mod']} {r['version']}: {r['status']}")
        out.append(f"   Rules: {r['rules_file']}")
        if r["rule_file_version"] != r["version"]:
            out.append(f"   Checked as version {r['version']} (--set-version; the rule file is for {r['rule_file_version']})")
        out.append(f"   Plugin: {', '.join(r['plugins'])} ({r['plugin_state']})")
        if r["logs"] != ["Papyrus logs"]:
            out.append(f"   Log checked: {', '.join(r['logs'])}" + (" (not found)" if r.get("logs_missing") else ""))
        if r["status"] == NOT_LOADED:
            out.append("   Not active in plugins.txt; rules not checked.")
            out.append("")
            continue
        if r["prefix_lines"]:
            out.append(f"   Mod log lines: {r['prefix_lines']} (first {r['first_prefix']['log']}:{r['first_prefix']['line']}, "
                       f"last {r['last_prefix']['log']}:{r['last_prefix']['line']})")
        else:
            out.append("   Mod log lines: none (the mod never logged: feature probably not tested, or logging is off)")
            if r["status"] == NOT_SEEN:
                out.append(f"   All {len(r['rules'])} rules NOT SEEN; no errors from its scripts.")
                out.append("")
                continue
        for x in r["rules"]:
            if x["kind"] == "expect":
                req = f"at least {x['min']}" + (", always" if x["always"] else "")
                out.append(f"   {x['status']:<9} expect {x['id']} ({req}): {x['count']} found")
            elif x["kind"] == "forbid":
                out.append(f"   {x['status']:<9} forbid {x['id']}: {x['count']} found")
            elif x["kind"] == "order":
                out.append(f"   {x['status']:<9} order {x['id']}: {x['detail']}")
            else:
                out.append(f"   {x['status']:<9} script errors: {x['count']} error(s), {x['warnings']} warning(s)")
                for g in x["groups"][:max_lines * 2]:
                    out.append(f"             {g['count']}x {g['kind']}: {g['message'][:160]}")
                    if g["frame"]:
                        out.append(f"                at {g['frame'][:160]}")
                    out.append(f"                first {g['first']['log']}:{g['first']['line']}")
                continue
            if x.get("means") and x["status"] != PASS:
                out.append(f"             ({x['means']})")
            shown = x.get("lines", [])[:max_lines]
            for ln in shown:
                out.append(f"             {fmt_line(ln)}")
            if x.get("count", 0) > len(shown):
                out.append(f"             ... and {x['count'] - len(shown)} more")
            if x.get("other_version_lines"):
                out.append(f"             Found with another version (wrong build installed?):")
                for ln in x["other_version_lines"][:max_lines]:
                    out.append(f"             {fmt_line(ln)}")
        out.append("")
    out.append("Package checks")
    if not data["flags"]:
        out.append("  No crash logs, Windows crash events or suspended stacks.")
    for f in data["flags"]:
        out.append(f"  FLAG {f['kind']}: {f['text']}")
    for i in data["other_errors"]:
        out.append(f"  Info: {i['log']} has {i['error']} error(s) and {i['warning']} warning(s) from other scripts "
                   f"(vanilla or other mods; not counted)")
    out.append("")
    out.append("PASS = seen as expected. FAIL = a required line missing, a forbidden line seen, lines out of order,")
    out.append("or a Papyrus error naming the mod's scripts. NOT SEEN = no matching line; usually the feature")
    out.append("wasn't tested. This report is a helper for reading the logs, not a verdict.")
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------------------- main

def newest_zip(folder):
    """The newest .zip in a folder: by the yyyymmdd-hhmmss stamp in its name, then by file time."""
    zips = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".zip")]
    if not zips:
        raise FileNotFoundError(f"no .zip in {folder}")

    def key(p):
        m = STAMP_RE.search(os.path.basename(p))
        return (m.group(1) if m else "", os.path.getmtime(p))
    return max(zips, key=key)


def run(args):
    root = os.path.abspath(args.root)
    zpath = args.input
    if not zpath:
        logs_dir = args.logs_dir or os.environ.get("PAPYRUS_LOG_CHECK_LOGS")
        if not logs_dir:
            raise ValueError("give a log file, a folder or a zip, or --logs-dir, or set PAPYRUS_LOG_CHECK_LOGS")
        zpath = newest_zip(logs_dir)
    pkg = Package(zpath)
    if not pkg.logs:
        raise ValueError(f"{pkg.name}: no Papyrus.N.log found (a single log file with any name can be given directly)")

    explicit_rules = split_list(args.rules)
    mods = split_list([args.mods]) if args.mods else None
    for p in explicit_rules:
        if not os.path.isfile(p):
            raise FileNotFoundError(f"rule file not found: {p}")
    rule_files = list(explicit_rules)
    if mods or not explicit_rules:
        rule_files += find_rule_files(root, mods)
    if not rule_files:
        raise ValueError(f"no rule files: give --rules FILE, or keep <project>\\testplan\\logrules.json under --root ({root})")
    explicit = bool(explicit_rules or mods)
    rules_list = [load_rules(p) for p in rule_files]
    overrides = {}
    for s in args.set_version or []:
        name, _, ver = s.partition("=")
        if not ver:
            raise ValueError(f"--set-version needs Mod=version, got '{s}'")
        overrides[name.strip().lower()] = ver.strip()
    used = set()
    for path, r in zip(rule_files, rules_list):
        if path not in explicit_rules:
            r["_path"] = rel(r["_path"], root)
        project = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(path)))).lower()
        for key in (project, r["mod"].lower()):
            if key in overrides:
                r["_rule_version"], r["version"] = r["version"], overrides[key]
                used.add(key)
    unused = set(overrides) - used
    if unused:
        raise ValueError(f"--set-version names no checked mod: {', '.join(sorted(unused))}")

    blocks = error_blocks(pkg)
    results = [check_mod(r, pkg, blocks) for r in rules_list]
    if not explicit:  # rule files found under --root: only mods whose plugin is loaded (all when there is no plugins.txt)
        results = [r for r in results if r["plugin_state"] in ("active", "unknown")]
    order = {FAIL: 0, PASS: 1, NOT_SEEN: 2, NOT_LOADED: 3}
    results.sort(key=lambda r: (order[r["status"]], r["mod"].lower()))

    flags, other = package_checks(pkg, blocks, our_block_ids(results, blocks, rules_list))
    m = pkg.manifest
    game = ""
    v = m.get("versions") or {}
    if isinstance(v.get("starfield"), dict):
        game = str(v["starfield"].get("version", ""))
        ef = v.get("engineFixes")
        if isinstance(ef, dict) and ef.get("version"):
            game += f"; Engine Fixes {ef['version']}"
    run_stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    data = {
        "tool": TOOL, "version": VERSION, "run": run_stamp,
        "package": {"name": pkg.name, "kind": pkg.kind, "sha256": pkg.sha256, "stamp": pkg.stamp(),
                    "plugins_txt": pkg.plugins is not None,
                    "manifest": {"created": m.get("created"), "user": m.get("user"), "computer": m.get("computer"),
                                 "note": m.get("note"), "window": m.get("window"), "game": game,
                                 "tool": m.get("tool")} if m else {},
                    "logs": [{"name": l["name"], "path": l["path"], "count": len(l["lines"]),
                              "first": l["first"], "last": l["last"]} for l in pkg.logs]},
        "rule_files": [{"mod": r["mod"], "version": r["version"], "path": r["_path"],
                        "rule_file_version": r.get("_rule_version", r["version"])} for r in rules_list],
        "mods": results, "flags": flags, "other_errors": other,
        "overall": FAIL if any(r["status"] == FAIL for r in results) else "OK",
    }
    out_dir = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, f"logcheck-{pkg.stamp()}-run{run_stamp}")
    n = 2
    while os.path.exists(base + ".txt") or os.path.exists(base + ".json"):  # two runs in one second
        base = os.path.join(out_dir, f"logcheck-{pkg.stamp()}-run{run_stamp}-{n}")
        n += 1
    report = text_report(data, args.max_lines)
    with open(base + ".txt", "w", encoding="utf-8") as f:
        f.write(report)
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)

    print(f"{pkg.name}")
    for r in results:
        print(f"  {r['status']:<10} {r['mod']} {r['version']}")
    for fl in flags:
        print(f"  FLAG       {fl['kind']}: {fl['text'][:120]}")
    print(f"Report: {base}.txt")
    print(f"JSON:   {base}.json")
    return 1 if data["overall"] == FAIL else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog=TOOL, description="Check Starfield Papyrus logs against per-mod rule files.")
    ap.add_argument("input", nargs="?",
                    help="a Papyrus log file, a folder with Papyrus.N.log files, or a zip of them "
                         "(default: the newest zip in --logs-dir)")
    ap.add_argument("--rules", action="append", metavar="FILE",
                    help="a rule file to check against (repeat, or give a comma list); "
                         "without --rules or --mods, rule files are searched under --root")
    ap.add_argument("--logs-dir", help="folder with log zips; the newest is checked (or env PAPYRUS_LOG_CHECK_LOGS)")
    ap.add_argument("--root", default=".",
                    help="folder holding mod project folders with <project>\\testplan\\logrules.json (default: current folder)")
    ap.add_argument("--mods", help="comma-separated project folder names under --root, or rule file paths")
    ap.add_argument("--out", help="output folder (default: out\\ next to this script)")
    ap.add_argument("--max-lines", type=int, default=5, help="matching lines shown per rule in the text report")
    ap.add_argument("--set-version", action="append", metavar="MOD=VERSION",
                    help="check a mod against another version than its rule file says (project folder or mod name); "
                         "for rechecking older logs. Can be repeated.")
    ap.add_argument("--version", action="version", version=f"{TOOL} {VERSION}")
    args = ap.parse_args(argv)
    try:
        return run(args)
    except (OSError, ValueError, zipfile.BadZipFile, KeyError) as e:
        print(f"{TOOL}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
