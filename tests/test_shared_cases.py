# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Richard Bejtlich
"""Runs the PMT shared test sets (tests/shared, adopted in 0.5.0) against papyrus-log-check.

One test per case, so a failure names the case id. A case listed under "known_limits" in tests/shared/ADOPTION.json
is skipped and its reason is printed. Run: python -I tests/test_shared_cases.py -v

Set 1 (output paths) runs against --log, the one option that names a file to write. Set 2 (damaged inputs) feeds the
JSON files to --rules and the text files to the log input. Set 4 (terminal text) runs one_line(). Set 5 (programs
and path spellings) has nothing to run: the tool starts no program and compares paths only for --log (set 1).
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHARED = os.path.join(HERE, "shared")
sys.path.insert(0, ROOT)
import papyrus_log_check as plc  # noqa: E402

SCRIPT = os.path.join(ROOT, "papyrus_log_check.py")
LOG_TEXT = "[10:00:00] Papyrus log opened (PC-64)\n[10:00:01] TEST: step one\n"
VALID_RULES = {"mod": "Test Mod", "version": "1.2.0", "plugins": ["TestMod.esm"], "names": ["TestMod"],
               "prefix": "TEST:", "scripts": "^TEST_",
               "expect": [{"id": "one", "re": "TEST: step one", "always": True, "min": 1}],
               "order": [], "forbid": [{"id": "bad", "re": "TEST: .*failed"}]}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


ADOPTION = load(os.path.join(SHARED, "ADOPTION.json"))
LIMITS = ADOPTION.get("known_limits", {})
EXIT_OK = set(ADOPTION["exit_codes"]["ok"] + ADOPTION["exit_codes"]["finding"])
EXIT_REFUSE = set(ADOPTION["exit_codes"]["refuse"])


def run_tool(args, cwd, timeout=60):
    p = subprocess.run([sys.executable, "-I", SCRIPT] + args, cwd=cwd, capture_output=True, timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def no_crash(test, code, err, label):
    test.assertNotIn("Traceback", err, f"{label}: traceback")
    test.assertTrue(0 <= code < 128, f"{label}: exit code {code}")


def known(test, case_id):
    if case_id in LIMITS:
        test.skipTest(f"known limit: {LIMITS[case_id]}")


def link_made(kind, src, dst):
    try:
        if kind == "symlink":
            os.symlink(src, dst)
        else:
            os.link(src, dst)
        return True
    except (OSError, NotImplementedError, AttributeError):
        return False


def case_insensitive(folder):
    p = os.path.join(folder, "CaseProbe.tmp")
    open(p, "w").close()
    return os.path.exists(os.path.join(folder, "caseprobe.TMP"))


class OutPaths(unittest.TestCase):
    pass


def _out_test(case):
    def test(self):
        known(self, case["id"])
        if case.get("only_if") == "windows" and os.name != "nt":
            self.skipTest("Windows only")
        if "option_kind" in case or "clean_dir" in case:
            self.skipTest("the tool empties no folder and --log names a file")
        with tempfile.TemporaryDirectory() as t:
            if case.get("only_if") == "case_insensitive_fs" and not case_insensitive(t):
                self.skipTest("case-sensitive file system")
            for d in case.get("dirs", []):
                os.makedirs(os.path.join(t, d), exist_ok=True)
            for f in case.get("files", []):
                with open(os.path.join(t, f), "w", encoding="utf-8") as fh:
                    fh.write("input")
            for ln in case.get("links", []):
                if not link_made(ln["kind"], os.path.join(t, ln["to"]), os.path.join(t, ln["from"])):
                    self.skipTest(f"this system can't make a {ln['kind']}")
            log = os.path.join(t, "Papyrus.0.log")
            with open(log, "w", encoding="utf-8") as fh:
                fh.write(LOG_TEXT)
            rules = os.path.join(t, "rules.logrules.json")
            with open(rules, "w", encoding="utf-8") as fh:
                json.dump(VALID_RULES, fh)
            args = [log, "--rules", rules, "--out", os.path.join(t, "out")]
            if case.get("input"):
                args += ["--rules", os.path.join(t, case["input"])]
            out = case["out"]
            if case["expect"] == "write":
                # A .json name is refused for --log by design (it looks like an input), so the control uses .txt.
                out = out.replace(".json", ".txt")
            before = {f: open(os.path.join(t, f), "rb").read() for f in case.get("files", [])}
            code, so, se = run_tool(args + ["--log", os.path.join(t, out)], t)
            no_crash(self, code, se, case["id"])
            if case["expect"] == "write":
                self.assertIn(code, EXIT_OK, se)
                self.assertTrue(os.path.isfile(os.path.join(t, out)), "the log was not written")
            else:
                self.assertIn(code, EXIT_REFUSE, f"expected a refusal, got {code}: {se}")
                self.assertIn("--log", se, "the message must name the option")
            for f, data in before.items():
                with open(os.path.join(t, f), "rb") as fh:
                    self.assertEqual(fh.read(), data, f"{f} was changed")
    return test


for _c in load(os.path.join(SHARED, "out-paths.json"))["cases"]:
    setattr(OutPaths, "test_" + _c["id"].replace("-", "_"), _out_test(_c))


class DamagedInputs(unittest.TestCase):
    pass


MANIFEST2 = load(os.path.join(SHARED, "damaged-inputs", "manifest.json"))


def _input_test(entry):
    def test(self):
        known(self, entry["file"])
        src = os.path.join(SHARED, "damaged-inputs", entry["file"])
        with tempfile.TemporaryDirectory() as t:
            log = os.path.join(t, "Papyrus.0.log")
            with open(log, "w", encoding="utf-8") as fh:
                fh.write(LOG_TEXT)
            if entry["kind"] == "json":
                args = [log, "--rules", src, "--out", os.path.join(t, "out")]
            else:
                with open(src, "rb") as fh:
                    data = fh.read()
                with open(log, "wb") as fh:
                    fh.write(data)
                args = [log, "--rules", _write_rules(t), "--out", os.path.join(t, "out")]
            start = time.time()
            code, so, se = run_tool(args, t, timeout=MANIFEST2["time_limit_s"] * 6)
            self.assertLess(time.time() - start, MANIFEST2["time_limit_s"] * 3, "too slow")
            no_crash(self, code, se, entry["file"])
            ans = entry["answer"]
            if ans == "refuse":
                self.assertIn(code, EXIT_REFUSE, f"expected a refusal, got {code}: {se}")
                if entry["kind"] == "json":
                    self.assertIn(entry["file"], se, "the message must name the file")
            elif ans == "read":
                self.assertIn(code, EXIT_OK, se)
            else:
                self.assertIn(code, EXIT_OK | EXIT_REFUSE, se)
    return test


def _write_rules(folder):
    p = os.path.join(folder, "rules.logrules.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(VALID_RULES, fh)
    return p


for _e in MANIFEST2["files"]:
    setattr(DamagedInputs, "test_" + _e["file"].replace("-", "_").replace(".", "_"), _input_test(_e))


def _mutations():
    """(id, changed copy) for each mutation of the sample's keys at depth 1 and 2 (shared-tests/reference/ref_guards.py)."""
    import copy

    def walk(node, path, d):
        if not isinstance(node, dict) or d > 2:
            return
        for k in list(node):
            yield path + [k]
            yield from walk(node[k], path + [k], d + 1)

    def change(doc, keys, how):
        doc = copy.deepcopy(doc)
        parent = doc
        for k in keys[:-1]:
            parent = parent[k]
        k = keys[-1]
        if how == "m-drop-key":
            del parent[k]
        elif how == "m-null-value":
            parent[k] = None
        elif how == "m-empty-object":
            parent[k] = {}
        else:
            parent[k] = "false" if isinstance(parent[k], bool) else "12"
        return doc

    for keys in walk(VALID_RULES, [], 1):
        for how in ("m-null-value", "m-empty-object", "m-wrong-type-string", "m-drop-key"):
            yield how, keys, change(VALID_RULES, keys, how)


class Mutations(unittest.TestCase):
    def test_mutations_of_a_valid_rule_file(self):
        """One run per mutation: a normal read or a plain refusal that names the file, never a traceback; a wrong
        type for a true/false value ("always": "false") must be refused, not counted as true."""
        for mid in ("m-null-value", "m-empty-object", "m-wrong-type-string", "m-drop-key"):
            known(self, mid)
        with tempfile.TemporaryDirectory() as t:
            log = os.path.join(t, "Papyrus.0.log")
            with open(log, "w", encoding="utf-8") as fh:
                fh.write(LOG_TEXT)
            n = 0
            for how, keys, doc in _mutations():
                rules = os.path.join(t, "mutated.logrules.json")
                with open(rules, "w", encoding="utf-8") as fh:
                    json.dump(doc, fh)
                code, so, se = run_tool([log, "--rules", rules, "--out", os.path.join(t, "out")], t)
                label = f"{how} at {'/'.join(map(str, keys))}"
                no_crash(self, code, se, label)
                self.assertIn(code, EXIT_OK | EXIT_REFUSE, f"{label}: exit {code}")
                if code in EXIT_REFUSE:
                    self.assertIn("mutated.logrules.json", se, f"{label}: the message must name the file")
                n += 1
            self.assertGreater(n, 20)


class TerminalText(unittest.TestCase):
    pass


LINE_BREAKS = {"\n", "\r", "\x0b", "\x0c", "\x85", " ", " "}


def _needs_escape(ch):
    return unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp")


def _text_of(case):
    rep = case.get("repeat")
    return rep["text"] * rep["count"] if rep else case["text"]


def _terminal_test(case, limit):
    def test(self):
        known(self, case["id"])
        text = _text_of(case)
        start = time.time()
        shown = plc.one_line(text)
        self.assertLess(time.time() - start, limit, "bounded_time")
        for rule in case["rules"]:
            if rule == "no_raw":
                self.assertFalse([c for c in shown if _needs_escape(c) and c != "\t"], "no_raw: a raw control or format character")
            elif rule == "one_line":
                self.assertFalse([c for c in shown if c in LINE_BREAKS], "one_line: a raw line break")
            elif rule == "visible_kept":
                it = iter(shown)
                self.assertTrue(all(any(c == s for s in it) for c in text if not _needs_escape(c)), "visible_kept")
            elif rule == "unchanged":
                self.assertEqual(shown, text)
            elif rule == "unchanged_or_marked_cut":
                if shown != text:
                    self.assertTrue(("..." in shown or "[cut]" in shown or "…" in shown) and len(shown) < len(text))
    return test


_T = load(os.path.join(SHARED, "terminal-text.json"))
for _c in _T["cases"]:
    setattr(TerminalText, "test_" + _c["id"].replace("-", "_"), _terminal_test(_c, _T["time_limit_s"]))


class Adoption(unittest.TestCase):
    def test_every_case_id_in_adoption_exists(self):
        ids = {c["id"] for c in load(os.path.join(SHARED, "out-paths.json"))["cases"]}
        ids |= {c["id"] for c in _T["cases"]} | {f["file"] for f in MANIFEST2["files"]}
        ids |= {m["id"] for m in MANIFEST2["mutations"]["list"]}
        pp = load(os.path.join(SHARED, "paths-and-programs.json"))
        ids |= {c["id"] for part in ("lookup", "spellings", "case_twins", "policy") for c in pp.get(part, [])}
        for cid in list(ADOPTION["known_limits"]) + list(ADOPTION["not_applicable"]):
            self.assertIn(cid, ids)


if __name__ == "__main__":
    unittest.main()
