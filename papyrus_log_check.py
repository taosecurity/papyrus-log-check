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

It reports PASS / FAIL / NOT SEEN for each rule in each mod's rule file (FOUND for explain rules, such as the
starter pack in the rules folder for the engine's own messages), plus general problems (Papyrus errors naming the mod's
scripts, crash logs, suspended stacks).

Read-only: it never changes the logs or the rule files.
Standard library only. MIT license (see LICENSE).

Usage:
  python -I papyrus_log_check.py INPUT --rules mymod.logrules.json [--rules other.json]
  python -I papyrus_log_check.py INPUT --root DIR [--mods A,B]
  python -I papyrus_log_check.py --logs-dir DIR ...      (newest zip in DIR)
Exit code: 0 = no FAIL, 1 = at least one FAIL, 2 = usage, rule file or input error.
"""

import argparse
import datetime
import errno
import hashlib
import json
import os
import re
import sys
import traceback
import zipfile

TOOL = "papyrus-log-check"
VERSION = "0.4.2"
# Attribution (the author's request, 2026-11-11): in the report's first line, --version and the JSON.
AUTHOR = "Richard Bejtlich"
LICENSE_NAME = "MIT"
URL = "https://github.com/taosecurity/papyrus-log-check"
BYLINE = f"{TOOL} {VERSION} by {AUTHOR} - {LICENSE_NAME} - {URL}"

PASS, FAIL, NOT_SEEN, NOT_LOADED = "PASS", "FAIL", "NOT SEEN", "NOT LOADED"
FOUND = "FOUND"   # 0.4.0: an "explain" rule matched; worth reading, but not a failure
# The base game's master file is always loaded, and the game never lists it in plugins.txt.
ALWAYS_LOADED = {"starfield.esm"}
# 0.4.1: the other official masters (the DLC, the SFBGS* updates and BlueprintShips-<official>.esm) are also
# loaded by the game whenever their file is in Data, with no plugins.txt line.
OFFICIAL_RE = re.compile(r"^(starfield|constellation|oldmars|shatteredspace|sfbgs[0-9a-z]{3})\.esm$", re.I)
BLUEPRINT_RE = re.compile(r"^blueprintships-(.+)$", re.I)


def is_official(name):
    """An official master the game loads by itself. BlueprintShips-X.esm counts only when X.esm is official."""
    if OFFICIAL_RE.match(name):
        return True
    m = BLUEPRINT_RE.match(name)
    return bool(m and OFFICIAL_RE.match(m.group(1)))

STAMP_RE = re.compile(r"(\d{8}-\d{6})")
PAPYRUS_RE = re.compile(r"(?:^|/)papyrus\.(\d+)\.log$", re.I)
ERRLINE_RE = re.compile(r"^\[(\d\d:\d\d:\d\d)\]\s+(error|warning):\s*(.*)$", re.I)
TIME_RE = re.compile(r"^\[(\d\d:\d\d:\d\d)\]")
SUSPENDED_RE = re.compile(r"suspended stack|dumping stack", re.I)
CRASH_RE = re.compile(r"(?:^|/)(?:crashlogs/[^/]+|crashlog[^/]*\.txt|crash-[^/]*\.log)$", re.I)
EVENT_HEAD_RE = re.compile(r"^====\s+(\S+)\s+(.+?)\s+ID\s+(\d+)\s*$")

ZIP, FOLDER, LOG_FILE = "zip", "folder", "log file"
IGNORED = object()  # 0.4.1: a manifest listing that was there but had the wrong shape (says nothing, like an empty one)

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def safe(text):
    """Text from logs, rule files and manifests with control characters shown as \\xNN, so escape codes hidden in
    an input can't fake lines or change the terminal (2026-11-16 security review). Tabs and line breaks stay."""
    return _CONTROL_RE.sub(lambda m: f"\\x{ord(m.group(0)):02X}", str(text))


class Log:
    """The troubleshooting log (0.3.0): what was read, what was decided and why a run stopped. Off unless asked for:
    --verbose prints it on stderr ("log: ..."), --log FILE writes it to FILE. The report and the summary on stdout
    are the same with or without it."""
    to_stderr = False
    file = None

    @classmethod
    def on(cls):
        return cls.to_stderr or cls.file is not None

    @classmethod
    def write(cls, text):
        if not cls.on():
            return
        for line in str(text).splitlines() or [""]:
            line = safe(line)
            if cls.to_stderr:
                print(f"log: {line}", file=sys.stderr)
            if cls.file is not None:
                try:
                    cls.file.write(f"{datetime.datetime.now():%H:%M:%S}  {line}\n")
                    cls.file.flush()
                except OSError as e:  # a log that stops working must not stop the check
                    cls.file = None
                    print(f"{TOOL}: stopped writing the log file: {e}", file=sys.stderr)

    @classmethod
    def open(cls, path, inputs):
        """Opens the log file, refusing one that would overwrite an input (a Papyrus log, the zip, a rule file)."""
        full = os.path.abspath(path)
        base = os.path.basename(full).lower()
        for i in inputs:
            i = os.path.abspath(i)
            if full == i or (os.path.isdir(i) and full.startswith(os.path.join(i, ""))):
                raise ValueError(f"--log {path} is inside the input {i}; give the log a place of its own, e.g. --log papyrus-log-check.log.txt")
        if PAPYRUS_RE.search(base) or base.endswith((".zip", ".json", ".esm", ".esp", ".esl")):
            raise ValueError(f"--log {path} looks like an input file; give it a .txt name, e.g. --log papyrus-log-check.log.txt")
        folder = os.path.dirname(full)
        if not os.path.isdir(folder):
            raise ValueError(f"--log {path}: the folder {folder} doesn't exist. Make it, or give --log a path in a folder that exists.")
        cls.file = open(full, "w", encoding="utf-8")

    @classmethod
    def close(cls):
        if cls.file is not None:
            try:
                cls.file.close()
            except OSError:
                pass
            cls.file = None


# ----------------------------------------------------------------------------- input

def clean_manifest(m):
    """A collector manifest with every field in the shape the report expects; a field of another shape is dropped
    (and logged), so a damaged or hand-made manifest.json can't crash the run."""
    shapes = {"window": dict, "listing": dict, "versions": dict, "warnings": list}
    out = {}
    for k, v in m.items():
        want = shapes.get(k)
        if want is not None and not isinstance(v, want):
            Log.write(f"manifest.json: '{k}' should be a {want.__name__}, not {type(v).__name__}; ignored")
            if k == "listing":   # a listing was there, so stray .dll files in the input mustn't stand in for its lists
                out[k] = {"sfsePluginDlls": IGNORED, "dataPlugins": IGNORED}
            continue
        if k in ("created", "user", "computer", "note", "tool") and v is not None and not isinstance(v, str):
            v = str(v)
        out[k] = v
    listing = out.get("listing")
    if listing:
        listing = dict(listing)
        for key in ("sfsePluginDlls", "dataPlugins"):
            if key not in listing:
                continue
            v = listing[key]
            if v is not IGNORED and not isinstance(v, list):   # null too: the key was there, so it isn't "no listing"
                Log.write(f"manifest.json: listing.{key} should be a list; ignored")
                listing[key] = IGNORED
        out["listing"] = listing
    return out


def _by_depth(keys):
    """Shallowest path first, then alphabetical."""
    return sorted(keys, key=lambda k: (k.count("/"), k))


class Package:
    """The logs to check: a zip (read in memory, entry names may use \\ or /), a folder, or one log file."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(os.path.normpath(path))
        self.zf = None
        self._logged = set()  # keys of the notes _log_once has written
        self.entries = {}  # lower-case path with / -> (key for _raw, path with /)
        try:
            self._load(path)
        except BaseException:
            self.close()  # 0.4.2: a constructor that fails part-way must not leave the zip open (locked on Windows)
            raise

    def _load(self, path):
        if os.path.isdir(path):
            self.kind = FOLDER
            for dirpath, dirnames, filenames in os.walk(path):
                dirnames.sort()
                for fn in filenames:
                    full = os.path.join(dirpath, fn)
                    norm = os.path.relpath(full, path).replace("\\", "/")
                    self.entries[norm.lower()] = (full, norm)
        elif not os.path.isfile(path):
            raise FileNotFoundError(f"{path} was not found.")
        elif path.lower().endswith(".zip") or zipfile.is_zipfile(path):
            self.kind = ZIP
            try:
                self.zf = zipfile.ZipFile(path)
            except zipfile.BadZipFile as e:
                raise ValueError(f"{self.name} is not a readable zip ({e}).")
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
        Log.write(f"input: {self.kind} {path}: {len(self.entries)} files, {len(self.logs)} Papyrus log(s), "
                  f"plugins.txt {'found' if self.plugins is not None else 'none'}, manifest {'found' if self.manifest else 'none'}")

    def close(self):
        """Lets go of the zip file (0.4.2: run() calls this, so a run that stops on an error doesn't keep the zip locked)."""
        if self.zf is not None:
            self.zf.close()

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

    def _sha256(self, extra_names=()):
        """A zip or log file: the file's hash. A folder: one hash over the logs, plugins.txt and any other log
        files the rule files name (their 'logs') that were read."""
        h = hashlib.sha256()
        if self.kind != FOLDER:
            with open(self.path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            return h.hexdigest()
        used = [log["path"].lower() for log in self.logs]
        if self._plugins_key:
            used.append(self._plugins_key)
        want = {n.lower() for n in extra_names}
        used += [k for k in self.entries if os.path.basename(k) in want]
        for key in sorted(set(used)):
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
        if not (isinstance(m, dict) and m.get("tool")):
            return {}
        return clean_manifest(m)

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
        """SFSE plugin DLL names (lower case): from a collector's manifest listing. Only an input whose manifest has
        no listing at all (no manifest, or one without 'listing') uses the .dll files in the folder or zip instead.
        None when nothing says anything, and whenever a manifest listing was there but its DLL list is missing,
        null, empty because the game folder wasn't found, of the wrong shape or without a usable name (a collector
        package doesn't copy the DLLs, so stray .dll files in it say nothing)."""
        present, listing = self._listing("sfsePluginDlls")
        if present:
            return listing
        dlls = {os.path.basename(k) for k in self.entries if k.endswith(".dll")}
        return dlls or None

    def data_plugins(self):
        """0.4.1: the plugin files in the game's Data folder (lower case), from a collector's manifest listing
        (listing.dataPlugins). None when the input has no such listing, or one without Starfield.esm (a real Data
        folder always holds it, so such a list says nothing). A list cut short after Starfield.esm can't be told apart."""
        _, listing = self._listing("dataPlugins")
        if listing is not None and "starfield.esm" not in listing:
            self._log_once("dataPlugins-nosf", "manifest.json: listing.dataPlugins has no Starfield.esm; ignored")
            return None
        return listing

    def _log_once(self, key, text):
        if key not in self._logged:
            self._logged.add(key)
            Log.write(text)

    def _listing(self, key):
        """0.4.1: (present, names) for the manifest's listing.<key>, whose entries are {"name": ...} objects or
        plain strings (a path is cut to its file name). present is False when there is no listing; names is None
        when there is none, when the collector didn't find the game folder (an empty gamePath, so its empty lists
        say nothing), when the manifest's listing lacks this key (round 4: a listing was there, so stray files in
        the input don't stand in for it) or when no entry has a usable name. Each reason is logged once."""
        whole = self.manifest.get("listing")
        if not isinstance(whole, dict):
            return False, None
        if key not in whole:
            self._log_once(key, f"manifest.json: listing has no {key}; ignored")
            return True, None
        listing = whole[key]
        if listing is IGNORED:
            return True, None
        if not listing and "gamePath" in self.manifest and not self.manifest.get("gamePath"):
            self._log_once(key, f"manifest.json: listing.{key} is empty because the game folder wasn't found; ignored")
            return True, None
        names = set()
        for d in listing:
            name = d.get("name") if isinstance(d, dict) else d
            if isinstance(name, str):
                base = os.path.basename(name.strip().replace("\\", "/")).strip().lower()
                if base and base not in (".", ".."):
                    names.add(base)
        if listing and not names:
            self._log_once(key, f"manifest.json: listing.{key} has no entry with a name; ignored")
            return True, None
        return True, names

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
        try:
            r = json.load(f)
        except UnicodeDecodeError as e:
            raise ValueError(f"{path} is not UTF-8 text ({e.reason} at byte {e.start}). Save it as UTF-8 (a UTF-16 file from Notepad's "
                             f"Unicode option won't do).")
        except ValueError as e:
            raise ValueError(f"{path} is not valid JSON ({e}). Check its commas and quotes.")
    if not isinstance(r, dict):
        raise ValueError(f"{path} should hold one JSON object {{...}} with 'mod', 'prefix' and the rules, not a {type(r).__name__}.")
    for key in ("mod", "prefix"):
        if key not in r:
            raise ValueError(f"{path} has no '{key}' field.")
        if not isinstance(r[key], str):
            raise ValueError(f"{path}: '{key}' should be text in quotes.")
    r.setdefault("plugins", [])
    r.setdefault("dlls", [])
    r.setdefault("logs", [])
    r.setdefault("version", "")
    r.setdefault("names", [])
    r.setdefault("scripts", "")
    r.setdefault("expect", [])
    r.setdefault("order", [])
    r.setdefault("forbid", [])
    r.setdefault("explain", [])
    r.setdefault("ignore", [])
    r["_path"] = path
    check_shape(r)
    Log.write(f"rule file {path}: mod {r['mod']} {r['version']}, {len(r['expect'])} expect, {len(r['forbid'])} forbid, "
              f"{len(r['order'])} order, {len(r['explain'])} explain rule(s)")
    return r


def check_shape(r):
    """Raises ValueError naming the rule file and the field when a field has the wrong shape."""
    path = r["_path"]

    def text_list(key):
        v = r[key]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ValueError(f"{path}: '{key}' should be a list of names in quotes, like [\"MyMod.esm\"].")
    for key in ("plugins", "dlls", "logs", "names"):
        text_list(key)
    for key in ("version", "scripts"):
        if not isinstance(r[key], str):
            raise ValueError(f"{path}: '{key}' should be text in quotes.")
    for kind in ("expect", "forbid", "explain"):
        if not isinstance(r[kind], list):
            raise ValueError(f"{path}: '{kind}' should be a list of rules [{{\"id\": ..., \"re\": ...}}].")
        for n, e in enumerate(r[kind], 1):
            if not isinstance(e, dict) or not isinstance(e.get("id"), str) or not isinstance(e.get("re"), str):
                raise ValueError(f"{path}: {kind} rule {n} needs an \"id\" and an \"re\" (both text in quotes).")
            # 0.4.1: 'min' and 'always' belong to expect rules. These checks run before the generic 'min' type
            # check, so a bad 'min' on an explain or forbid rule gives one clear error, not two in turn.
            if kind == "explain":
                # 'min': 1 and 'always': false say what an explain rule does anyway, so they are accepted.
                noop = {"min": 1, "always": False}
                for key in ("min", "always"):
                    if key in e and not (type(e[key]) is type(noop[key]) and e[key] == noop[key]):
                        raise ValueError(f"{path}: explain rule '{e['id']}' has '{key}' {e[key]!r}, which only expect rules use. "
                                         f"Remove '{key}' from it, or make it an expect rule.")
            elif kind == "forbid":
                for key in ("min", "always"):
                    if key in e:
                        raise ValueError(f"{path}: forbid rule '{e['id']}' has '{key}', which only expect rules use "
                                         f"(a forbid rule fails on any matching line). Remove '{key}' from it, "
                                         f"or make it an expect rule.")
            if "min" in e and (not isinstance(e["min"], int) or e["min"] < 1):
                raise ValueError(f"{path}: {kind} rule '{e['id']}' has 'min' {e['min']!r}; it should be a whole number, 1 or more.")
    if not isinstance(r["order"], list) or not all(isinstance(q, list) and all(isinstance(x, str) for x in q) for q in r["order"]):
        raise ValueError(f"{path}: 'order' should be a list of lists of expect ids, like [[\"start\", \"done\"]].")
    if not isinstance(r["ignore"], list) or not all(isinstance(x, str) or (isinstance(x, dict) and isinstance(x.get("re"), str))
                                                    for x in r["ignore"]):
        raise ValueError(f"{path}: 'ignore' should be a list of patterns in quotes (or {{\"re\": ...}} entries).")
    if not r["plugins"] and not r["dlls"]:
        raise ValueError(f"{path} needs 'plugins' (.esm files) or 'dlls' (SFSE plugin DLLs).")


def prepare(r):
    """Compiles every pattern in a rule file (after --set-version, so {version} is final) and checks the order
    rules. Raises ValueError naming the file and the pattern."""
    r["_prefix_rx"] = compile_re(r["prefix"], r, "prefix")
    r["_expect_rx"] = [compile_re(e["re"], r, f"expect '{e['id']}'") for e in r["expect"]]
    r["_forbid_rx"] = [compile_re(fb["re"], r, f"forbid '{fb['id']}'") for fb in r["forbid"]]
    r["_explain_rx"] = [compile_re(x["re"], r, f"explain '{x['id']}'") for x in r["explain"]]
    r["_scripts_rx"] = compile_re(r["scripts"], r, "scripts", re.I) if r["scripts"] else None
    r["_ignore_rx"] = [compile_re(x["re"] if isinstance(x, dict) else x, r, "ignore", re.I) for x in r["ignore"]]
    known = {e["id"] for e in r["expect"]}
    for seq in r["order"]:
        unknown = [x for x in seq if x not in known]
        if unknown:
            raise ValueError(f"{r['_path']} has an order rule that names unknown expect ids {unknown}.")


def fill(pattern, rules):
    return pattern.replace("{version}", re.escape(rules.get("version", "")))


def compile_re(pattern, rules, where, flags=0):
    try:
        return re.compile(fill(pattern, rules), flags)
    except re.error as e:
        raise ValueError(f"{rules['_path']} has a bad regex in {where}: {e}.")


def find_rule_files(root, mods=None):
    """Rule files: --mods names (project folders, which may be nested like Group\\Mod, or .json paths), else every
    <root>/*/testplan/logrules.json and <root>/*/*/testplan/logrules.json (mods kept inside a group folder)."""
    if mods:
        out = []
        for m in mods:
            p = m if m.lower().endswith(".json") else os.path.join(root, m, "testplan", "logrules.json")
            if not os.path.isfile(p):
                raise FileNotFoundError(f"There is no rule file for '{m}' (it looked for {p}).")
            out.append(p)
        return out
    if not os.path.isdir(root):
        raise FileNotFoundError(f"--root {root} is not a folder. Give --root the folder that holds your project folders, "
                                f"or use --rules FILE.")
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
            block = {"log": log["name"], "log_index": i, "line": k + 1, "kind": m.group(2).lower(),
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


FRAME_RE = re.compile(r' - "[^"]+" Line \S+$')


def script_frame(stack):
    """The stack line that names the script behind an error: the first frame in a script file, else the first
    frame of any kind (a built-in function's frame says "<native>"). None for a stack dump or no stack."""
    frames = [s for s in stack if FRAME_RE.search(s)]
    for s in frames:
        if '"<native>"' not in s:
            return s
    return frames[0] if frames else None


def plugin_state(rules, pkg):
    """'active', 'inactive', 'missing' or 'unknown' (the input can't tell: no plugins.txt / no usable DLL list).
    .esm plugins are looked up in plugins.txt, SFSE DLLs in the DLL listing. Starfield.esm is always active
    (0.4.0): the game loads it without listing it, so a rule file for the base game's own messages always runs.
    It counts only for a rule file whose only plugins are always-loaded ones: a file that also names its own
    plugins or DLLs is active only when one of those is.
    0.4.1: the other official masters (is_official) are always loaded too, the same way, when their file is in
    Data: the collector's listing.dataPlugins decides, and without that listing they count as loaded, as
    Starfield.esm always does."""
    states = []
    own = [p for p in rules["plugins"] if not is_official(p)]
    if rules["plugins"] and not own and not rules["dlls"]:
        data = pkg.data_plugins()
        for p in rules["plugins"]:
            states.append(True if p.lower() in ALWAYS_LOADED or data is None or p.lower() in data else "missing")
    elif own:
        if pkg.plugins is None:
            states.append(None)
        else:
            states += [pkg.plugins.get(p.lower(), "missing") for p in own]
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


def not_loaded_reason(rules):
    """0.4.1: why a mod is NOT LOADED, naming what was really checked: its own .esm plugins in plugins.txt,
    its DLLs in the input's SFSE plugin DLL list (the collector's manifest listing; the .dll files in the input
    only when the manifest has no listing at all), or both. Official masters aren't named: in a file with other plugins or DLLs they don't count. A file
    that names only official masters is NOT LOADED only when the input's Data plugin list lacks them."""
    own = [p for p in rules["plugins"] if not is_official(p)]
    parts = []
    if rules["plugins"] and not own and not rules["dlls"]:
        parts.append("its official master is not in the input's Data plugin list" if len(rules["plugins"]) == 1
                     else "none of its official masters is in the input's Data plugin list")
    if own:
        parts.append("the plugin is not active in plugins.txt" if len(own) == 1
                     else "none of its plugins is active in plugins.txt")
    if rules["dlls"]:
        parts.append("its DLL is not among the SFSE plugin DLLs in the input" if len(rules["dlls"]) == 1
                     else "none of its DLLs is among the SFSE plugin DLLs in the input")
    text = " and ".join(parts) or "none of its plugins is loaded"
    return text[0].upper() + text[1:] + ", so its rules were not checked."


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

    if "_prefix_rx" not in rules:
        prepare(rules)
    prefix = rules["_prefix_rx"]
    prefix_hits = [(i, n, t) for i, n, t in all_lines(src) if prefix.search(t)]
    res["prefix_lines"] = len(prefix_hits)
    if prefix_hits:
        res["first_prefix"] = ref(src, *prefix_hits[0])
        res["last_prefix"] = ref(src, *prefix_hits[-1])
    ran = bool(prefix_hits)

    if res["plugin_state"] in ("inactive", "missing"):
        res["status"] = NOT_LOADED
        res["not_loaded_reason"] = not_loaded_reason(rules)
        return res

    # expect rules
    first_pos = {}
    for e, rx in zip(rules["expect"], rules["_expect_rx"]):
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
    for seq in rules["order"]:
        missing = [x for x in seq if x not in first_pos]
        if missing:
            status, detail = NOT_SEEN, "not all seen: " + ", ".join(missing)
        else:
            pos = [first_pos[x] for x in seq]
            bad = [f"{seq[k]} before {seq[k - 1]}" for k in range(1, len(seq)) if pos[k] < pos[k - 1]]
            status, detail = (FAIL, "; ".join(bad)) if bad else (PASS, "in order")
        res["rules"].append({"kind": "order", "id": " > ".join(seq), "status": status, "detail": detail})

    # forbid rules
    for fb, rx in zip(rules["forbid"], rules["_forbid_rx"]):
        hits = [(i, n, t) for i, n, t in all_lines(src) if rx.search(t)]
        status = FAIL if hits else (PASS if ran else NOT_SEEN)
        res["rules"].append({"kind": "forbid", "id": fb["id"], "status": status, "count": len(hits),
                             "pattern": fill(fb["re"], rules), "means": fb.get("means", ""),
                             "lines": [ref(src, *h) for h in hits[:keep]]})

    # explain rules (0.4.0): lines worth knowing about, such as the engine's own error messages. A match is FOUND,
    # which is shown with the rule's 'means' but never fails the mod. Error lines also get the script that raised
    # them (the top line of the stack that follows), so the reader knows whose error it is.
    top_frame = {}
    if rules["explain"] and not rules["logs"]:
        top_frame = {(b["log_index"], b["line"]): script_frame(b["stack"]) for b in blocks
                     if not SUSPENDED_RE.search(b["message"])}   # a stack dump names many scripts
    for x, rx in zip(rules["explain"], rules["_explain_rx"]):
        hits = [(i, n, t) for i, n, t in all_lines(src) if rx.search(t)]
        status = FOUND if hits else (PASS if ran else NOT_SEEN)
        lines = []
        for h in hits[:keep]:
            line = ref(src, *h)
            frame = top_frame.get((h[0], h[1]))
            if frame:
                line["at"] = frame
            lines.append(line)
        res["rules"].append({"kind": "explain", "id": x["id"], "status": status, "count": len(hits),
                             "pattern": fill(x["re"], rules), "means": x.get("means", ""), "lines": lines})

    # script errors naming our scripts
    if rules["_scripts_rx"] is not None:
        srx = rules["_scripts_rx"]
        ign = rules["_ignore_rx"]
        ours = [b for b in blocks
                if (srx.search(b["message"]) or any(srx.search(s) for s in b["stack"]))
                and not any(r.search(b["message"]) for r in ign)]
        res["_block_ids"] = {id(b) for b in ours}   # for the "other scripts" counts; not in the JSON
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
    seen = ran or PASS in statuses   # a PASS (an expect line without the prefix) still counts as seen
    explain_only = not (rules["expect"] or rules["forbid"] or rules["order"] or rules["_scripts_rx"] is not None)
    if FAIL in statuses:
        res["status"] = FAIL
    elif FOUND in statuses and (seen or explain_only):
        res["status"] = FOUND   # a mod that never logged stays NOT SEEN; its FOUND lines still show in the body
    elif not seen:
        res["status"] = NOT_SEEN
    else:
        res["status"] = PASS
    # 0.4.1: the lines the explain rules found (the sum of their counts), so a NOT SEEN mod can say
    # "NOT SEEN (N found)" on stdout and in the summary. A new key; the status stays as it was.
    res["explain_found"] = sum(r["count"] for r in res["rules"] if r["kind"] == "explain")
    return res


def shown_status(r):
    """The status as stdout and the report summary show it: NOT SEEN gets "(N found)" when explain rules matched."""
    if r["status"] == NOT_SEEN and r.get("explain_found"):
        return f"{NOT_SEEN} ({r['explain_found']} found)"
    return r["status"]


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


def our_block_ids(results):
    """The error blocks check_mod counted for the mods in the report (after each mod's ignore list)."""
    ids = set()
    for r in results:
        ids |= r.pop("_block_ids", set())
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
    out.append(BYLINE)
    out.append(f"Run {data['run']}")
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
        out.append("  There is no plugins.txt, so plugin checks are skipped and every rule file is checked.")
    out.append("")
    out.append("Summary")
    for r in data["mods"]:
        counts = {}
        for x in r["rules"]:
            counts[x["status"]] = counts.get(x["status"], 0) + 1
        c = ", ".join(f"{v} {k.lower()}" for k, v in counts.items()) or "-"
        note = "named in note" if r["named_in_note"] else "not in note"
        out.append(f"  {shown_status(r):<10} {r['mod']} {r['version']}  ({note}; {c})")
    out.append("")
    for r in data["mods"]:
        out.append(f"== {r['mod']} {r['version']}: {r['status']}")
        out.append(f"   Rules: {r['rules_file']}")
        if r["rule_file_version"] != r["version"]:
            out.append(f"   This mod was checked as version {r['version']} (--set-version); the rule file is for {r['rule_file_version']}.")
        out.append(f"   Plugin: {', '.join(r['plugins'])} ({r['plugin_state']})")
        if r["logs"] != ["Papyrus logs"]:
            out.append(f"   Log checked: {', '.join(r['logs'])}" + (" (it is not in the input)" if r.get("logs_missing") else ""))
        if r["status"] == NOT_LOADED:
            out.append("   " + r.get("not_loaded_reason", "The plugin is not active in plugins.txt, so its rules were not checked."))
            out.append("")
            continue
        explain_only = bool(r["rules"]) and all(x["kind"] == "explain" for x in r["rules"])
        if r["prefix_lines"]:
            label = "Lines read" if explain_only else "Mod log lines"   # a rule pack for the game's own messages
            out.append(f"   {label}: {r['prefix_lines']} (first {r['first_prefix']['log']}:{r['first_prefix']['line']}, "
                       f"last {r['last_prefix']['log']}:{r['last_prefix']['line']})")
        elif explain_only:
            out.append("   Lines read: none. No line matched this rule file's prefix.")
        else:
            out.append("   Mod log lines: none. The mod never logged, so its features were probably not tested, or logging is off.")
            if r["rules"] and all(x["status"] == NOT_SEEN for x in r["rules"]):
                out.append(f"   All {len(r['rules'])} rules are NOT SEEN, and its scripts logged no errors.")
                out.append("")
                continue
        for x in r["rules"]:
            if x["kind"] == "expect":
                req = f"at least {x['min']}" + (", always" if x["always"] else "")
                out.append(f"   {x['status']:<9} expect {x['id']} ({req}): {x['count']} found")
            elif x["kind"] == "forbid":
                out.append(f"   {x['status']:<9} forbid {x['id']}: {x['count']} found")
            elif x["kind"] == "explain":
                out.append(f"   {x['status']:<9} explain {x['id']}: {x['count']} found")
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
                if ln.get("at"):
                    out.append(f"                at {ln['at'][:160]}")
            if x.get("count", 0) > len(shown):
                out.append(f"             ... and {x['count'] - len(shown)} more")
            if x.get("other_version_lines"):
                out.append("             The same line was found with another version (was a different build installed?):")
                for ln in x["other_version_lines"][:max_lines]:
                    out.append(f"             {fmt_line(ln)}")
        out.append("")
    if data.get("not_loaded"):
        out.append("Not loaded: these rule files were found under --root, but none of their plugins or DLLs is loaded,")
        out.append("so they were not checked.")
        for n in data["not_loaded"]:
            out.append(f"  NOT LOADED {n['mod']} {n['version']}  ({', '.join(n['plugins'])}: {n['plugin_state']}; rules {n['path']})")
            if n.get("not_loaded_reason"):
                out.append(f"    {n['not_loaded_reason']}")
        out.append("")
    for e in data.get("rule_errors", []):
        out.append(f"SKIPPED rule file {e['path']}: {e['error']}")
    if data.get("rule_errors"):
        out.append("")
    out.append("Package checks")
    if not data["flags"]:
        out.append("  The input has no crash logs, Windows crash events or suspended stacks.")
    for f in data["flags"]:
        out.append(f"  FLAG {f['kind']}: {f['text']}")
    for i in data["other_errors"]:
        out.append(f"  Info: {i['log']} has {i['error']} error(s) and {i['warning']} warning(s) from other scripts "
                   f"(the base game or other mods). They are not counted.")
    out.append("")
    out.append("PASS means a line was seen as expected. FAIL means a required line is missing, a forbidden line")
    out.append("was seen, lines are out of order, or a Papyrus error names the mod's scripts. NOT SEEN means no")
    out.append("line matched, which usually means the feature wasn't tested. FOUND means an explain rule matched: the")
    out.append("lines are worth reading, but they don't fail the mod. This report helps you read the logs; it is not a verdict.")
    return "\n".join(safe(line) for line in out) + "\n"


# ----------------------------------------------------------------------------- main

def newest_zip(folder, *, from_env=False):
    """The newest .zip in a folder: by the yyyymmdd-hhmmss stamp in its name, then by file time.
    `from_env` is True when the folder came from PAPYRUS_LOG_CHECK_LOGS (not --logs-dir), for the error text."""
    if not os.path.isdir(folder):
        if from_env:
            raise FileNotFoundError(f"PAPYRUS_LOG_CHECK_LOGS is set to '{folder}', which is not a folder. "
                                    f"Set it to an existing folder that holds log zips, or give --logs-dir.")
        raise FileNotFoundError(f"--logs-dir '{folder}' is not a folder. Give an existing folder that holds log zips "
                                f"(or set PAPYRUS_LOG_CHECK_LOGS).")
    zips = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".zip")]
    if not zips:
        raise FileNotFoundError(f"There is no .zip in {folder}.")

    def key(p):
        m = STAMP_RE.search(os.path.basename(p))
        return (m.group(1) if m else "", os.path.getmtime(p))
    return max(zips, key=key)


# Report-write errors by cause (0.4.2): the disk itself, the path or its permissions; any other errno gets generic text.
_DISK_ERRNOS = frozenset((errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC), errno.EIO))
_PATH_ERRNOS = frozenset(getattr(errno, name) for name in (
    "ENOENT", "ENOTDIR", "EISDIR", "EINVAL", "EACCES", "EPERM", "EBUSY", "EROFS", "ENAMETOOLONG", "ELOOP", "EEXIST"))


def run(args):
    opened = []  # the Package, so it is closed even when the run stops on an error
    try:
        return _run(args, opened)
    finally:
        for pkg in opened:
            pkg.close()


def _run(args, opened):
    root = os.path.abspath(args.root)
    zpath = args.input
    if not zpath:
        logs_dir = args.logs_dir
        from_env = False
        if not logs_dir:
            logs_dir = os.environ.get("PAPYRUS_LOG_CHECK_LOGS")
            from_env = True
        if not logs_dir:
            raise ValueError("Give a log file, a folder or a zip, or use --logs-dir, or set PAPYRUS_LOG_CHECK_LOGS.")
        zpath = newest_zip(logs_dir, from_env=from_env)
    pkg = Package(zpath)
    opened.append(pkg)
    if not pkg.logs:
        raise ValueError(f"No Papyrus.N.log was found in {pkg.name}. (You can also give a single log file with any name.)")

    explicit_rules = split_list(args.rules)
    mods = split_list([args.mods]) if args.mods else None
    for p in explicit_rules:
        if not os.path.isfile(p):
            raise FileNotFoundError(f"The rule file {p} was not found.")
    rule_files = list(explicit_rules)
    if mods or not explicit_rules:
        rule_files += find_rule_files(root, mods)
    if not rule_files:
        raise ValueError(f"No rule files were found. Give --rules FILE, or keep <project>\\testplan\\logrules.json under --root ({root}).")
    explicit = bool(explicit_rules or mods)
    rules_list, kept_files, rule_errors = [], [], []
    for p in rule_files:
        try:
            rules_list.append(load_rules(p))
            kept_files.append(p)
        except (ValueError, OSError) as e:
            if explicit and (p in explicit_rules or mods):
                raise
            rule_errors.append({"path": rel(p, root), "error": str(e)})
            Log.write(f"skipped rule file {p}: {e}")
    rule_files = kept_files
    overrides = {}
    for s in args.set_version or []:
        name, _, ver = s.partition("=")
        if not ver:
            raise ValueError(f"--set-version needs Mod=version, but it got '{s}'.")
        overrides[name.strip().lower()] = ver.strip()
    used = set()
    for path, r in zip(rule_files, rules_list):
        if path not in explicit_rules:
            r["_path"] = rel(r["_path"], root)
        project = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(path)))).lower()
        keys = [k for k in dict.fromkeys((project, r["mod"].lower())) if k in overrides]   # once, even when both match
        if keys:
            versions = {overrides[k] for k in keys}
            if len(versions) > 1:
                raise ValueError(f"--set-version gives {r['mod']} two versions ({', '.join(sorted(versions))}): "
                                 f"once by its folder and once by its mod name. Give one.")
            r["_rule_version"], r["version"] = r["version"], overrides[keys[0]]
            used.update(keys)
            Log.write(f"{r['mod']}: checked as version {r['version']} (--set-version; the rule file says {r['_rule_version']})")
    unused = set(overrides) - used
    if unused:
        raise ValueError(f"--set-version names a mod that wasn't checked: {', '.join(sorted(unused))}.")

    pairs = list(zip(rule_files, rules_list))
    not_loaded = []
    if not explicit:  # rule files found under --root: only mods whose plugin is loaded (all when there is no plugins.txt)
        before = len(pairs)
        kept = []
        for p, r in pairs:
            state = plugin_state(r, pkg)
            if state in ("active", "unknown"):
                kept.append((p, r))
            else:   # 0.4.0: listed as NOT LOADED (one line each), so a run that checks nothing says why
                not_loaded.append({"mod": r["mod"], "version": r["version"], "path": r["_path"],
                                   "plugins": r["plugins"] + r["dlls"], "plugin_state": state,
                                   "not_loaded_reason": not_loaded_reason(r)})
        pairs = kept
        not_loaded.sort(key=lambda n: n["mod"].lower())
        Log.write(f"--root: {len(pairs)} of {before} rule file(s) are for loaded mods")
    # Only the mods being checked are compiled: a bad pattern in a rule file of a mod that isn't loaded can't stop the
    # run, while one in a loaded mod's file still does (exit 2, naming the file and the pattern).
    rules_list = [r for _, r in pairs]
    for r in rules_list:
        prepare(r)
    pkg.sha256 = pkg._sha256([n for r in rules_list for n in r["logs"]])
    blocks = error_blocks(pkg)
    Log.write(f"Papyrus errors and warnings: {len(blocks)}")
    results = [check_mod(r, pkg, blocks) for r in rules_list]
    for r in results:
        Log.write(f"{r['mod']}: {r['status']} (plugin {r['plugin_state']}, {r['prefix_lines']} mod log line(s))")
    order = {FAIL: 0, FOUND: 1, PASS: 2, NOT_SEEN: 3, NOT_LOADED: 4}
    results.sort(key=lambda r: (order[r["status"]], r["mod"].lower()))

    flags, other = package_checks(pkg, blocks, our_block_ids(results))
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
        "tool": TOOL, "version": VERSION, "author": AUTHOR, "license": LICENSE_NAME, "url": URL, "run": run_stamp,
        "package": {"name": pkg.name, "kind": pkg.kind, "sha256": pkg.sha256, "stamp": pkg.stamp(),
                    "plugins_txt": pkg.plugins is not None,
                    "manifest": {"created": m.get("created"), "user": m.get("user"), "computer": m.get("computer"),
                                 "note": m.get("note"), "window": m.get("window"), "game": game,
                                 "tool": m.get("tool")} if m else {},
                    "logs": [{"name": l["name"], "path": l["path"], "count": len(l["lines"]),
                              "first": l["first"], "last": l["last"]} for l in pkg.logs]},
        "rule_files": [{"mod": r["mod"], "version": r["version"], "path": r["_path"],
                        "rule_file_version": r.get("_rule_version", r["version"])} for r in rules_list],
        "mods": results, "not_loaded": not_loaded, "flags": flags, "other_errors": other, "rule_errors": rule_errors,
        "overall": FAIL if any(r["status"] == FAIL for r in results) else "OK",
    }
    out_dir = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    base = os.path.join(out_dir, f"logcheck-{pkg.stamp()}-run{run_stamp}")
    report = text_report(data, args.max_lines)
    # 0.4.2: each file is created exclusively ("x"), so a run never truncates another run's report, and a file is
    # listed in `partial` only once this run created it. A failed write removes the file it was writing; a report
    # that was written completely stays, and the error names it.
    kept = []
    partial = None
    try:
        os.makedirs(out_dir, exist_ok=True)
        n = 2
        while True:  # two runs in one second: take the next free name (lexists also sees a dangling link)
            while os.path.lexists(base + ".txt") or os.path.lexists(base + ".json"):
                base = os.path.join(out_dir, f"logcheck-{pkg.stamp()}-run{run_stamp}-{n}")
                n += 1
            try:
                f = open(base + ".txt", "x", encoding="utf-8")
            except FileExistsError:  # another run took the name between the check and now
                base = os.path.join(out_dir, f"logcheck-{pkg.stamp()}-run{run_stamp}-{n}")
                n += 1
                continue
            break
        with f:
            partial = base + ".txt"
            f.write(report)
        partial = None
        kept.append(base + ".txt")
        with open(base + ".json", "x", encoding="utf-8") as f:
            partial = base + ".json"
            json.dump(data, f, indent=1, ensure_ascii=False)
        partial = None
    except BaseException as e:  # also a non-OSError (unserializable data, Ctrl+C) removes its half-written file
        if partial:
            try:
                os.remove(partial)
            except OSError:
                pass
        if not isinstance(e, OSError):
            raise
        saved = f" The text report was written in full and is kept: {kept[0]}." if kept else ""
        why = e.strerror or e
        if isinstance(e, FileExistsError) and kept:  # the .txt was ours, the .json name was taken by another run
            raise ValueError(f"Can't write the report in {out_dir}: another run took the name {base}.json while this "
                             f"one was writing. Run the check again.{saved}")
        if e.errno in _DISK_ERRNOS:
            raise ValueError(f"Can't write the report in {out_dir} ({why}). The folder is fine as a path, so check "
                             f"that the disk has room, or give --out another folder.{saved}")
        if e.errno in _PATH_ERRNOS:
            raise ValueError(f"Can't write the report in {out_dir} ({why}). Give --out a folder you can write to "
                             f"(a path that is not a file, has no characters Windows refuses, and is not locked or protected).{saved}")
        raise ValueError(f"Can't write the report in {out_dir} ({why}). Check the folder and the disk, or give --out "
                         f"another folder.{saved}")
    Log.write(f"wrote {base}.txt and {base}.json; overall {data['overall']}")

    print(safe(pkg.name))
    for r in results:
        print(safe(f"  {shown_status(r):<10} {r['mod']} {r['version']}"))
    for n in not_loaded:
        print(safe(f"  {NOT_LOADED:<10} {n['mod']} {n['version']}"))
    for e in rule_errors:
        print(safe(f"  SKIPPED    rule file {e['path']}: {e['error']}"))
    for fl in flags:
        print(safe(f"  FLAG       {fl['kind']}: {fl['text'][:120]}"))
    print(f"Report: {base}.txt")
    print(f"JSON:   {base}.json")
    return 1 if data["overall"] == FAIL else 0


class _VersionShown(Exception):
    """Raised by --version while the arguments are parsed; main() prints the version text and returns 0."""


class _VersionAction(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        super().__init__(option_strings, dest, nargs=0, default=argparse.SUPPRESS, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        raise _VersionShown()


def main(argv=None):
    """Runs the tool. 0.4.2: for the whole call, a character the console's code page can't show prints as ? instead
    of stopping the run (argparse's own usage and error text included); the streams' old error mode comes back after."""
    saved = []
    for stream in (sys.stdout, sys.stderr):
        try:
            old = stream.errors
            stream.reconfigure(errors="replace")
            saved.append((stream, old))
        except (AttributeError, ValueError):
            pass
    try:
        return _main(argv)
    finally:
        for stream, old in saved:
            try:
                stream.reconfigure(errors=old)  # a stream closed during the run raises ValueError: skipped
            except (AttributeError, ValueError, OSError):
                pass


def _main(argv):
    ap = argparse.ArgumentParser(prog=TOOL, description="papyrus-log-check checks Starfield Papyrus logs against per-mod rule files.")
    ap.add_argument("input", nargs="?",
                    help="This is the Papyrus log file, folder of Papyrus.N.log files, or zip to check. "
                         "Without it, the newest zip in --logs-dir is checked.")
    ap.add_argument("--rules", action="append", metavar="FILE",
                    help="This names a rule file to check against. Repeat it, or give a comma list. "
                         "Without --rules or --mods, rule files are searched for under --root.")
    ap.add_argument("--logs-dir", metavar="FOLDER",
                    help="This folder holds log zips, and the newest one is checked. "
                         "The environment variable PAPYRUS_LOG_CHECK_LOGS does the same.")
    ap.add_argument("--root", default=".", metavar="FOLDER",
                    help="This folder holds mod project folders with <project>\\testplan\\logrules.json. "
                         "The default is the current folder.")
    ap.add_argument("--mods", metavar="A,B",
                    help="This lists project folder names under --root, or rule file paths, separated by commas.")
    ap.add_argument("--out", metavar="FOLDER",
                    help="This sets the output folder. The default is out\\ next to this script.")
    ap.add_argument("--max-lines", type=int, default=5, metavar="N",
                    help="This sets how many matching lines the text report shows per rule.")
    ap.add_argument("--set-version", action="append", metavar="MOD=VERSION",
                    help="This checks a mod (project folder or mod name) as another version than its rule file says, "
                         "for rechecking older logs. You can repeat it.")
    ap.add_argument("--verbose", action="store_true",
                    help="This prints a troubleshooting log on stderr: what was read, what was decided, and why a run stopped.")
    ap.add_argument("--log", metavar="FILE",
                    help="This writes the same troubleshooting log to FILE (overwritten each run), e.g. --log papyrus-log-check.log.txt")
    # --version uses its own action, not argparse's version action, which re-wraps the text into one paragraph.
    # Like that action it answers as soon as it is parsed (so a bad option after it doesn't matter), and argparse
    # still handles short forms (--vers), --help before it and "--" as for any option.
    ap.add_argument("--version", action=_VersionAction, help="This prints the version and license, then exits.")
    try:
        args = ap.parse_args(argv)
    except _VersionShown:
        print(BYLINE)
        print("Free software under the MIT license. It comes with no warranty.")
        return 0
    print(BYLINE, file=sys.stderr)  # on stderr, so the summary on stdout stays the same for scripts
    try:
        Log.to_stderr = args.verbose
        if args.log:
            Log.open(args.log, [x for x in [args.input] + split_list(args.rules) if x])
        Log.write(f"{BYLINE}; Python {sys.version.split()[0]} on {sys.platform}")
        Log.write(f"arguments: {' '.join(sys.argv[1:] if argv is None else argv)}")
        return run(args)
    except (OSError, ValueError, zipfile.BadZipFile, KeyError) as e:
        print(f"{TOOL}: {safe(e)}", file=sys.stderr)
        Log.write("stopped:\n" + traceback.format_exc())
        return 2
    finally:
        Log.close()


if __name__ == "__main__":
    sys.exit(main())
