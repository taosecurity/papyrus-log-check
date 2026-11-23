# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Richard Bejtlich
"""Tests for papyrus_log_check on small made-up logs, folders and zips (no game files needed)."""

import json
import os
import sys
import tempfile
import unittest
import unittest.mock
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import papyrus_log_check as plc  # noqa: E402

LOG1 = """[10:00:00] Papyrus log opened (PC-64)
[10:00:05] TEST: setup (new game), version 1.2.0
[10:00:06] TEST: step one
[10:00:07] error: Cannot call Foo() on a None object, aborting function call
stack:
\t[ (FF000801)].TEST_MainScript.OnInit() - "TEST_MainScript.psc" Line 12
[10:00:08] error: Cannot call Bar() on a None object, aborting function call
stack:
\t[ (00001234)].OtherScript.OnLoad() - "OtherScript.psc" Line 3
[10:00:09] TEST: step two
[10:00:10] TEST: step two
[10:00:11] Suspended stack count is over our warning threshold, dumping stacks:
"""
LOG0 = """[10:05:00] Papyrus log opened (PC-64)
[10:05:01] TEST: setup (game loaded), version 1.2.0
"""
PLUGINS = "# comment\n*Starfield.esm\n*TestMod.esm\nOffMod.esm\n"
MANIFEST = {"tool": "example-collector 1.0", "created": "2026-01-02T03:04:05",
            "listing": {"sfsePluginDlls": [{"name": "MyDll.dll", "version": "1.0.0.0"}]},
            "note": "TestMod-1.2.0 check", "warnings": ["Crash log found!"]}
EVENTS = "==== 2026-01-02T03:00:00  Application Error  ID 1000\nFaulting application name: Starfield.exe\n"

RULES = {
    "mod": "Test Mod", "version": "1.2.0", "plugins": ["TestMod.esm"], "names": ["TestMod"],
    "prefix": "TEST:", "scripts": "^TEST_|\\bTEST_",
    "expect": [
        {"id": "setup", "re": "TEST: setup \\((new game|game loaded)\\), version {version}", "min": 2, "always": True},
        {"id": "one", "re": "TEST: step one"},
        {"id": "two", "re": "TEST: step two", "min": 2},
        {"id": "three", "re": "TEST: step three"},
    ],
    "order": [["one", "two"], ["two", "one"], ["one", "three"]],
    "forbid": [{"id": "bad", "re": "TEST: .*failed"}],
}


def make_zip(folder, name="logs-20260102-030405-test.zip", events=True, crash=True, plugins=PLUGINS):
    path = os.path.join(folder, name)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("manifest.json", json.dumps(MANIFEST))
        z.writestr("Logs\\Script\\Papyrus.1.log", LOG1)
        z.writestr("Logs\\Script\\Papyrus.0.log", LOG0)
        z.writestr("Logs\\Script\\User\\Papyrus.0.log", "ignored user log")
        if plugins is not None:
            z.writestr("Plugins.txt", plugins)
        if events:
            z.writestr("events.txt", EVENTS)
        z.writestr("SFSE\\Logs\\mydll.log", "2026-01-02 03:00:00.000 [info] server started\n")
        if crash:
            z.writestr("SFSE\\Crashlog_2026-01-02.txt",
                       "Exception Address:    Game.exe + 0x10\n   Exception Code:    EXCEPTION_ACCESS_VIOLATION\n")
    return path


def make_folder(folder, plugins=PLUGINS):
    """The same logs as loose files: Papyrus.0/.1 log, a User\\ log that must be skipped, Plugins.txt."""
    os.makedirs(os.path.join(folder, "User"), exist_ok=True)
    for name, text in (("Papyrus.1.log", LOG1), ("Papyrus.0.log", LOG0), (os.path.join("User", "Papyrus.0.log"), "x")):
        with open(os.path.join(folder, name), "w", encoding="utf-8", newline="\r\n") as f:
            f.write(text)
    if plugins is not None:
        with open(os.path.join(folder, "Plugins.txt"), "w", encoding="utf-8") as f:
            f.write(plugins)
    return folder


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_rules(root, project, rules):
    d = os.path.join(root, project, "testplan")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "logrules.json"), "w", encoding="utf-8") as f:
        json.dump(rules, f)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.root = os.path.join(self.dir, "projects")
        self.out = os.path.join(self.dir, "out")
        write_rules(self.root, "TestMod", RULES)

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, rules=RULES, **zkw):
        pkg = plc.Package(make_zip(self.dir, **zkw))
        path = os.path.join(self.dir, "rules-under-test.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rules, f)
        return pkg, plc.check_mod(plc.load_rules(path), pkg, plc.error_blocks(pkg))


class TestPackage(Base):
    def test_reads_logs_oldest_first_and_skips_user_logs(self):
        pkg = plc.Package(make_zip(self.dir))
        self.assertEqual([l["name"] for l in pkg.logs], ["Papyrus.1.log", "Papyrus.0.log"])
        self.assertEqual(pkg.logs[0]["first"], "10:00:00")
        self.assertEqual(pkg.stamp(), "20260102-030405")

    def test_plugins(self):
        pkg = plc.Package(make_zip(self.dir))
        self.assertTrue(pkg.plugins["testmod.esm"])
        self.assertFalse(pkg.plugins["offmod.esm"])

    def test_error_blocks_have_stacks(self):
        pkg = plc.Package(make_zip(self.dir))
        b = plc.error_blocks(pkg)
        self.assertEqual(len(b), 2)
        self.assertIn("TEST_MainScript.OnInit()", b[0]["stack"][0])
        self.assertEqual((b[0]["log"], b[0]["line"]), ("Papyrus.1.log", 4))


class TestRules(Base):
    def by_id(self, res):
        return {x["id"]: x for x in res["rules"]}

    def test_statuses(self):
        _, res = self.check()
        r = self.by_id(res)
        self.assertEqual(r["setup"]["status"], plc.PASS)          # once in each log
        self.assertEqual(r["setup"]["lines"][1]["log"], "Papyrus.0.log")
        self.assertEqual(r["one"]["status"], plc.PASS)
        self.assertEqual(r["two"]["status"], plc.PASS)
        self.assertEqual(r["three"]["status"], plc.NOT_SEEN)
        self.assertEqual(r["one > two"]["status"], plc.PASS)
        self.assertEqual(r["two > one"]["status"], plc.FAIL)
        self.assertEqual(r["one > three"]["status"], plc.NOT_SEEN)
        self.assertEqual(r["bad"]["status"], plc.PASS)
        se = r["script errors"]
        self.assertEqual((se["status"], se["count"]), (plc.FAIL, 1))  # OtherScript's error is not ours
        self.assertEqual(res["status"], plc.FAIL)
        self.assertTrue(res["named_in_note"])

    def test_wrong_version_fails_always_rule(self):
        _, res = self.check(dict(RULES, version="9.9.9"))
        setup = self.by_id(res)["setup"]
        self.assertEqual(setup["status"], plc.FAIL)
        self.assertEqual(len(setup["other_version_lines"]), 2)  # the 1.2.0 lines are shown as a hint
        self.assertIn("version 1.2.0", setup["other_version_lines"][0]["text"])

    def test_set_version_override(self):
        z = make_zip(self.dir)
        write_rules(self.root, "TestMod", dict(RULES, version="9.9.9", order=[]))
        plc.main([z, "--root", self.root, "--out", self.out, "--set-version", "TestMod=1.2.0"])
        data = json.loads(read([os.path.join(self.out, f) for f in os.listdir(self.out) if f.endswith(".json")][0]))
        mod = data["mods"][0]
        self.assertEqual((mod["version"], mod["rule_file_version"]), ("1.2.0", "9.9.9"))
        self.assertEqual({x["id"]: x["status"] for x in mod["rules"]}["setup"], plc.PASS)
        self.assertEqual(plc.main([z, "--root", self.root, "--out", self.out, "--set-version", "Nope=1"]), 2)

    def test_ignore_removes_error(self):
        _, res = self.check(dict(RULES, ignore=[{"re": "Cannot call Foo", "why": "known"}], order=[]))
        self.assertEqual(self.by_id(res)["script errors"]["status"], plc.PASS)

    def test_mod_that_never_logged_is_not_seen(self):
        rules = dict(RULES, prefix="QUIET:", scripts="^QUIET_", order=[],
                     expect=[{"id": "x", "re": "QUIET: hello", "always": True}],
                     forbid=[{"id": "y", "re": "QUIET: bad"}])
        _, res = self.check(rules)
        self.assertEqual(res["status"], plc.NOT_SEEN)
        self.assertTrue(all(x["status"] in (plc.NOT_SEEN, plc.PASS) for x in res["rules"]))

    def test_sfse_dll_and_own_log(self):
        rules = {"mod": "Dll Mod", "version": "", "plugins": [], "dlls": ["mydll.dll"], "logs": ["mydll.log"],
                 "prefix": "\\[info\\]", "expect": [{"id": "up", "re": "server started", "always": True}]}
        _, res = self.check(rules)
        self.assertEqual(res["plugin_state"], "active")
        self.assertEqual(res["status"], plc.PASS)
        self.assertEqual(res["rules"][0]["lines"][0]["log"], "mydll.log")
        _, res = self.check(dict(rules, dlls=["otherdll.dll"]))
        self.assertEqual(res["status"], plc.NOT_LOADED)

    def test_inactive_plugin_not_loaded(self):
        _, res = self.check(dict(RULES, plugins=["OffMod.esm"]))
        self.assertEqual(res["status"], plc.NOT_LOADED)


class TestRun(Base):
    def test_end_to_end_writes_unique_files_and_flags(self):
        z = make_zip(self.dir)
        code = plc.main([z, "--root", self.root, "--out", self.out])
        self.assertEqual(code, 1)
        files = sorted(os.listdir(self.out))
        self.assertEqual(len(files), 2)
        self.assertTrue(files[0].startswith("logcheck-20260102-030405-run"))
        data = json.loads(read(os.path.join(self.out, files[0])))
        kinds = {f["kind"] for f in data["flags"]}
        self.assertEqual(kinds, {"crash log", "windows event", "suspended stacks", "collector warning"})
        self.assertEqual(data["other_errors"], [{"log": "Papyrus.1.log", "error": 1, "warning": 0}])
        txt = read(os.path.join(self.out, files[1]))
        self.assertIn("Papyrus.1.log:2  [10:00:05] TEST: setup (new game), version 1.2.0", txt)

    def test_newest_zip_from_logs_dir(self):
        make_zip(self.dir, name="logs-20260101-000000-old.zip")
        make_zip(self.dir, name="logs-20260102-030405-new.zip")
        self.assertTrue(plc.newest_zip(self.dir).endswith("-new.zip"))

    def test_bad_regex_is_usage_error(self):
        write_rules(self.root, "TestMod", dict(RULES, prefix="("))
        self.assertEqual(plc.main([make_zip(self.dir), "--root", self.root, "--out", self.out]), 2)

    def test_finds_rule_files_in_group_folders(self):
        write_rules(self.root, "TestMod", RULES)
        write_rules(self.root, os.path.join("Group", "Inner"), dict(RULES, mod="Inner"))
        found = [os.path.relpath(p, self.root) for p in plc.find_rule_files(self.root)]
        self.assertIn(os.path.join("Group", "Inner", "testplan", "logrules.json"), found)
        self.assertIn(os.path.join("TestMod", "testplan", "logrules.json"), found)
        self.assertEqual(plc.find_rule_files(self.root, [os.path.join("Group", "Inner")])[0],
                         os.path.join(self.root, "Group", "Inner", "testplan", "logrules.json"))

    def test_no_plugins_txt_checks_all(self):
        z = make_zip(self.dir, plugins=None)
        plc.main([z, "--root", self.root, "--out", self.out])
        data = json.loads(read([os.path.join(self.out, f) for f in os.listdir(self.out) if f.endswith(".json")][0]))
        self.assertEqual(data["mods"][0]["plugin_state"], "unknown")

    def test_newest_zip_any_name(self):
        make_zip(self.dir, name="logs-a.zip")
        make_zip(self.dir, name="mylogs-20260105-000000.zip")
        self.assertTrue(plc.newest_zip(self.dir).endswith("mylogs-20260105-000000.zip"))
        empty = os.path.join(self.dir, "empty")
        os.makedirs(empty)
        with self.assertRaises(FileNotFoundError):
            plc.newest_zip(empty)


class TestPlainInput(Base):
    """A single Papyrus log, or a folder of them, instead of a zip."""

    def rules_file(self, rules=RULES, name="testmod.logrules.json"):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rules, f)
        return path

    def run_main(self, *argv):
        code = plc.main(list(argv) + ["--out", self.out])
        js = [f for f in os.listdir(self.out) if f.endswith(".json")] if os.path.isdir(self.out) else []
        data = json.loads(read(os.path.join(self.out, sorted(js)[-1]))) if js else None
        return code, data

    def test_single_log_file(self):
        path = os.path.join(self.dir, "Papyrus.1.log")
        with open(path, "w", encoding="utf-8") as f:
            f.write(LOG1)
        pkg = plc.Package(path)
        self.assertEqual(pkg.kind, plc.LOG_FILE)
        self.assertEqual([l["name"] for l in pkg.logs], ["Papyrus.1.log"])
        self.assertIsNone(pkg.plugins)
        self.assertEqual(len(plc.error_blocks(pkg)), 2)
        self.assertRegex(pkg.stamp(), r"^\d{8}-\d{6}$")

    def test_log_file_with_any_name(self):
        path = os.path.join(self.dir, "copied from a friend.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(LOG0)
        code, data = self.run_main(path, "--rules", self.rules_file())
        m = data["mods"][0]
        self.assertEqual(data["package"]["kind"], "log file")
        self.assertEqual(m["plugin_state"], "unknown")
        r = {x["id"]: x for x in m["rules"]}
        self.assertEqual(r["setup"]["status"], plc.FAIL)  # always + min 2, only 1 in this log
        self.assertEqual(r["setup"]["count"], 1)
        self.assertEqual(code, 1)

    def test_folder(self):
        folder = make_folder(os.path.join(self.dir, "logs"))
        pkg = plc.Package(folder)
        self.assertEqual(pkg.kind, plc.FOLDER)
        self.assertEqual([l["name"] for l in pkg.logs], ["Papyrus.1.log", "Papyrus.0.log"])  # User\ skipped
        self.assertTrue(pkg.plugins["testmod.esm"])
        self.assertEqual(len(pkg.sha256), 64)

    def test_folder_gives_same_results_as_zip(self):
        rules = self.rules_file()
        folder = make_folder(os.path.join(self.dir, "logs"))
        _, from_folder = self.run_main(folder, "--rules", rules)
        out2 = os.path.join(self.dir, "out2")
        plc.main([make_zip(self.dir, events=False, crash=False), "--rules", rules, "--out", out2])
        js = [f for f in os.listdir(out2) if f.endswith(".json")][0]
        from_zip = json.loads(read(os.path.join(out2, js)))
        strip = lambda m: [(x["id"], x["status"], x.get("count")) for x in m["rules"]]  # noqa: E731
        self.assertEqual(strip(from_folder["mods"][0]), strip(from_zip["mods"][0]))
        self.assertEqual(from_folder["mods"][0]["status"], plc.FAIL)

    def test_unrelated_manifest_is_ignored(self):
        folder = make_folder(os.path.join(self.dir, "logs"))
        with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "something else", "note": "TestMod", "warnings": ["x"], "created": "2020-01-01T00:00:00"}, f)
        pkg = plc.Package(folder)
        self.assertEqual(pkg.manifest, {})
        self.assertNotEqual(pkg.stamp(), "20200101-000000")
        _, data = self.run_main(folder, "--rules", self.rules_file())
        self.assertEqual(data["package"]["manifest"], {})
        self.assertNotIn("collector warning", {f["kind"] for f in data["flags"]})

    def test_folder_sha_changes_with_log(self):
        folder = make_folder(os.path.join(self.dir, "logs"))
        a = plc.Package(folder).sha256
        with open(os.path.join(folder, "Papyrus.0.log"), "a", encoding="utf-8") as f:
            f.write("[10:06:00] TEST: step two\n")
        self.assertNotEqual(a, plc.Package(folder).sha256)

    def test_folder_inactive_plugin_and_folder_dll_listing(self):
        folder = make_folder(os.path.join(self.dir, "logs"))
        with open(os.path.join(folder, "MyDll.dll"), "wb") as f:
            f.write(b"MZ")
        pkg = plc.Package(folder)
        self.assertEqual(pkg.sfse_dlls(), {"mydll.dll"})
        rules = plc.load_rules(self.rules_file(dict(RULES, plugins=["OffMod.esm"])))
        self.assertEqual(plc.check_mod(rules, pkg, plc.error_blocks(pkg))["status"], plc.NOT_LOADED)

    def test_rules_repeated_and_comma_list(self):
        a = self.rules_file()
        b = self.rules_file(dict(RULES, mod="Second Mod"), name="second.json")
        c = self.rules_file(dict(RULES, mod="Third Mod"), name="third.json")
        _, data = self.run_main(make_folder(os.path.join(self.dir, "logs")), "--rules", a, "--rules", f"{b},{c}")
        self.assertEqual(sorted(m["mod"] for m in data["mods"]), ["Second Mod", "Test Mod", "Third Mod"])
        self.assertEqual(data["rule_files"][0]["path"], a)  # explicit paths are shown as given

    def test_rules_skip_root_search(self):
        write_rules(self.root, "Other", dict(RULES, mod="Found Under Root"))
        os.chdir(self.root)
        try:
            _, data = self.run_main(make_folder(os.path.join(self.dir, "logs")), "--rules", self.rules_file())
        finally:
            os.chdir(HERE)
        self.assertEqual([m["mod"] for m in data["mods"]], ["Test Mod"])

    def test_explicit_rules_keep_not_loaded_mods(self):
        _, data = self.run_main(make_folder(os.path.join(self.dir, "logs")),
                                "--rules", self.rules_file(dict(RULES, plugins=["OffMod.esm"])))
        self.assertEqual(data["mods"][0]["status"], plc.NOT_LOADED)

    def test_input_errors_exit_2(self):
        rules = self.rules_file()
        empty = os.path.join(self.dir, "empty")
        os.makedirs(empty)
        self.assertEqual(plc.main([empty, "--rules", rules, "--out", self.out]), 2)          # no logs
        self.assertEqual(plc.main([os.path.join(self.dir, "nope.log"), "--rules", rules]), 2)  # missing input
        folder = make_folder(os.path.join(self.dir, "logs"))
        self.assertEqual(plc.main([folder, "--rules", os.path.join(self.dir, "nope.json")]), 2)  # missing rules
        bad = os.path.join(self.dir, "bad.zip")
        with open(bad, "wb") as f:
            f.write(b"not a zip")
        self.assertEqual(plc.main([bad, "--rules", rules]), 2)
        os.chdir(empty)
        try:
            self.assertEqual(plc.main([folder, "--out", self.out]), 2)  # no --rules and nothing under --root
        finally:
            os.chdir(HERE)


class TestExample(unittest.TestCase):
    """The example in examples\\ (shown in the README) runs and passes."""

    def test_example(self):
        ex = os.path.join(os.path.dirname(HERE), "examples")
        with tempfile.TemporaryDirectory() as out:
            code = plc.main([os.path.join(ex, "Papyrus.0.log"), "--rules",
                             os.path.join(ex, "example-beacon.logrules.json"), "--out", out])
            js = [f for f in os.listdir(out) if f.endswith(".json")][0]
            data = json.loads(read(os.path.join(out, js)))
        self.assertEqual(code, 0)
        m = data["mods"][0]
        self.assertEqual(m["status"], plc.PASS)
        statuses = {x["id"]: x["status"] for x in m["rules"]}
        self.assertEqual(statuses["started"], plc.PASS)
        self.assertEqual(statuses["beacon-placed"], plc.PASS)
        self.assertEqual(statuses["beacon-removed"], plc.NOT_SEEN)
        self.assertEqual(statuses["no-double-start"], plc.PASS)
        self.assertEqual(statuses["script errors"], plc.PASS)  # its one error is on the ignore list

    def test_quiet_example(self):
        """0.4.1: examples\\example-quiet.logrules.json (README "Results", CHANGELOG 0.4.1 Example) shows
        NOT SEEN (2 found) on the example log, exit 0, JSON status NOT SEEN."""
        import contextlib
        import io
        ex = os.path.join(os.path.dirname(HERE), "examples")
        with tempfile.TemporaryDirectory() as out:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = plc.main([os.path.join(ex, "Papyrus.0.log"), "--rules",
                                 os.path.join(ex, "example-quiet.logrules.json"), "--out", out])
            js = [f for f in os.listdir(out) if f.endswith(".json")][0]
            data = json.loads(read(os.path.join(out, js)))
        self.assertEqual(code, 0)
        self.assertIn("  NOT SEEN (2 found) Example Quiet 0.2.0\n", buf.getvalue())
        m = data["mods"][0]
        self.assertEqual(m["status"], plc.NOT_SEEN)
        self.assertEqual(m["explain_found"], 2)


class TestStarterExample(unittest.TestCase):
    """The starter rule file in examples\\ (README "Add logging to a Creation Kit mod") loads and fits the
    README's script."""

    PATH = os.path.join(os.path.dirname(HERE), "examples", "starter-mymod.logrules.json")
    LOG = ("[10:00:00] Papyrus log opened (PC-64)\n"
           "[10:00:01] MYMOD: quest started, version 0.1.0\n"
           "[10:00:20] MYMOD: item used by [ObjectReference < (00000014)>]\n"
           "[10:00:21] MYMOD: reward given\n")

    def test_loads(self):
        r = plc.load_rules(self.PATH)
        plc.prepare(r)  # compiles every pattern and checks the order ids
        self.assertEqual(r["prefix"], "MYMOD:")
        self.assertEqual([e["id"] for e in r["expect"]], ["started", "used", "done"])

    def run_log(self, text):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "Papyrus.0.log")
            with open(log, "w", encoding="utf-8") as f:
                f.write(text)
            out = os.path.join(d, "out")
            code = plc.main([log, "--rules", self.PATH, "--out", out])
            js = [f for f in os.listdir(out) if f.endswith(".json")][0]
            return code, json.loads(read(os.path.join(out, js)))["mods"][0]

    def test_readme_lines_pass(self):
        code, m = self.run_log(self.LOG)
        self.assertEqual((code, m["status"]), (0, plc.PASS))
        statuses = {x["id"]: x["status"] for x in m["rules"]}
        self.assertEqual(statuses["started > used > done"], plc.PASS)

    def test_warning_fails(self):
        code, m = self.run_log(self.LOG + "[10:00:22] MYMOD: WARNING: no user, reward skipped\n")
        self.assertEqual((code, m["status"]), (1, plc.FAIL))


class TestReviewFixes(Base):
    """0.3.0: fixes from the 2026-11-16 code and security reviews."""

    def run_json(self, *extra, zkw=None):
        code = plc.main([make_zip(self.dir, **(zkw or {})), "--root", self.root, "--out", self.out, *extra])
        js = max((f for f in os.listdir(self.out) if f.endswith(".json")), key=lambda f: os.path.getmtime(os.path.join(self.out, f))) if os.path.isdir(self.out) else None
        return code, (json.loads(read(os.path.join(self.out, js))) if js else None)

    def test_set_version_once_when_folder_and_mod_name_match(self):
        write_rules(self.root, "TestMod", dict(RULES, mod="TestMod"))
        code, data = self.run_json("--set-version", "TestMod=1.0.0")
        m = data["mods"][0]
        self.assertEqual(m["version"], "1.0.0")
        self.assertEqual(m["rule_file_version"], "1.2.0")

    def test_set_version_two_different_values_is_an_error(self):
        write_rules(self.root, "TestMod", dict(RULES, mod="Other"))
        code = plc.main([make_zip(self.dir), "--root", self.root, "--out", self.out,
                         "--set-version", "TestMod=1.0.0", "--set-version", "Other=2.0.0"])
        self.assertEqual(code, 2)

    def test_bad_scripts_regex_is_exit_2(self):
        write_rules(self.root, "TestMod", dict(RULES, scripts="TEST_("))
        self.assertEqual(plc.main([make_zip(self.dir), "--root", self.root, "--out", self.out]), 2)

    def test_broken_rule_file_of_an_inactive_mod_is_skipped(self):
        write_rules(self.root, "OffMod", dict(RULES, mod="Off", plugins=["OffMod.esm"], prefix="("))
        code, data = self.run_json()
        self.assertEqual(code, 1)   # TestMod's own FAILs, not exit 2
        self.assertEqual([m["mod"] for m in data["mods"]], ["Test Mod"])

    def test_structure_errors_name_the_file(self):
        for bad in ([], dict(RULES, expect=[{"id": "x"}]), dict(RULES, plugins="TestMod.esm"),
                    dict(RULES, order=["one"]), dict(RULES, expect=[{"id": "x", "re": "y", "min": 0}])):
            path = os.path.join(self.dir, "bad.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(bad, f)
            with self.assertRaises(ValueError) as cm:
                plc.load_rules(path)
            self.assertIn("bad.json", str(cm.exception))

    def test_not_valid_json_names_the_file(self):
        path = os.path.join(self.dir, "broken.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{ nope")
        with self.assertRaises(ValueError) as cm:
            plc.load_rules(path)
        self.assertIn("broken.json", str(cm.exception))

    def test_pass_without_prefix_is_not_not_seen(self):
        rules = dict(RULES, prefix="NEVERLOGGED:", forbid=[], order=[], scripts="",
                     expect=[{"id": "one", "re": "TEST: step one"}])
        _, res = self.check(rules)
        self.assertEqual(res["status"], plc.PASS)

    def test_odd_manifest_shapes_do_not_crash(self):
        m = dict(MANIFEST, window="24h", listing=[], versions=["x"], warnings="oops", created=12345)
        path = os.path.join(self.dir, "odd-20260102-030405.zip")
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("manifest.json", json.dumps(m))
            z.writestr("Papyrus.0.log", LOG1)
            z.writestr("Plugins.txt", PLUGINS)
        code = plc.main([path, "--root", self.root, "--out", self.out])
        self.assertIn(code, (0, 1))

    def test_control_characters_are_escaped(self):
        self.assertEqual(plc.safe("a\x1b[2Jb\tc"), "a\\x1B[2Jb\tc")
        self.assertEqual(plc.safe("plain"), "plain")

    def test_log_option_writes_and_refuses_inputs(self):
        log = os.path.join(self.dir, "plc-log.txt")
        code = plc.main([make_zip(self.dir), "--root", self.root, "--out", self.out, "--log", log])
        self.assertEqual(code, 1)
        self.assertIn("rule file", read(log))
        self.assertEqual(plc.main([make_zip(self.dir), "--root", self.root, "--out", self.out,
                                   "--log", os.path.join(self.dir, "Papyrus.0.log")]), 2)
        z = make_zip(self.dir)
        self.assertEqual(plc.main([z, "--root", self.root, "--out", self.out, "--log", z]), 2)

    def test_ignored_errors_count_as_other_scripts(self):
        rules = dict(RULES, ignore=["Foo\\(\\)"])
        write_rules(self.root, "TestMod", rules)
        code, data = self.run_json()
        self.assertEqual(data["other_errors"], [{"log": "Papyrus.1.log", "error": 2, "warning": 0}])

    def test_folder_hash_covers_named_logs(self):
        folder = make_folder(os.path.join(self.dir, "f"))
        with open(os.path.join(folder, "mydll.log"), "w", encoding="utf-8") as f:
            f.write("one\n")
        rules = dict(RULES, logs=["mydll.log"])
        write_rules(self.root, "TestMod", rules)
        plc.main([folder, "--root", self.root, "--out", self.out])
        h1 = json.loads(read(os.path.join(self.out, max((x for x in os.listdir(self.out) if x.endswith(".json")), key=lambda x: os.path.getmtime(os.path.join(self.out, x))))))["package"]["sha256"]
        with open(os.path.join(folder, "mydll.log"), "w", encoding="utf-8") as f:
            f.write("two\n")
        plc.main([folder, "--root", self.root, "--out", self.out])
        h2 = json.loads(read(os.path.join(self.out, max((x for x in os.listdir(self.out) if x.endswith(".json")), key=lambda x: os.path.getmtime(os.path.join(self.out, x))))))["package"]["sha256"]
        self.assertNotEqual(h1, h2)


class TestVersionText(unittest.TestCase):
    def test_version_says_license_in_american_spelling(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = plc.main(["--version"])
        out = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn(plc.BYLINE, out)
        self.assertIn("MIT license", out)
        self.assertNotIn("licence", out.lower())

    def test_version_with_other_options_prints_the_same_text(self):
        import contextlib
        import io
        outs = []
        for args in (["--version"], ["--version", "--verbose"], ["--verbose", "--version"], ["--vers"]):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(plc.main(args), 0)
            outs.append(buf.getvalue())
        self.assertEqual(outs[0], outs[1])
        self.assertEqual(outs[0], outs[2])
        self.assertEqual(outs[0], outs[3])
        self.assertIn("MIT license", outs[1])

    def test_help_before_version_prints_help(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit) as cm:
            plc.main(["--help", "--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("usage:", buf.getvalue())
        self.assertNotIn("Free software", buf.getvalue())

    def test_version_after_double_dash_is_an_input_path(self):
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        old = os.getcwd()
        with tempfile.TemporaryDirectory() as empty:   # an empty folder, so no file called --version exists
            os.chdir(empty)
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = plc.main(["--", "--version"])
            finally:
                os.chdir(old)
        self.assertEqual(code, 2)   # a missing input named --version, not the version text
        self.assertNotIn("Free software", out.getvalue() + err.getvalue())
        self.assertIn("--version was not found", out.getvalue() + err.getvalue())

    def test_version_before_a_bad_option_still_answers(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(plc.main(["--version", "--bogus"]), 0)
        self.assertIn("MIT license", buf.getvalue())


TOOL_DIR = os.path.dirname(HERE)
PACK = [os.path.join(TOOL_DIR, "rules", n) for n in
        ("papyrus-runtime-errors.logrules.json", "papyrus-scripts-and-properties.logrules.json",
         "papyrus-saves-and-load.logrules.json")]
SAMPLE = os.path.join(TOOL_DIR, "examples", "starter-pack-sample.log")
# How many lines of examples\starter-pack-sample.log each pack rule must match: every rule has its own line(s),
# and no rule matches another rule's line.
PACK_COUNTS = {
    "none-object": 1, "no-native-object": 1, "none-into-alias": 1, "none-array": 1, "array-index": 1,
    "divide-by-zero": 1, "assigning-none": 1, "constant-global": 1, "no-3d": 1, "stack-too-deep": 1,
    "missing-script": 1, "base-types": 1, "unbound-native": 1, "property-removed": 2, "property-read-only": 1,
    "property-type": 1, "property-unbound": 1, "struct-changed": 1, "signature-mismatch": 1,
    "circular-inheritance": 1,
    "function-changed": 1, "function-removed": 1, "type-missing": 1, "variable-type": 1, "variable-removed": 1,
    "stacks-over-threshold": 1,
}


def run_quiet(argv):
    """main() with stdout captured: (exit code, stdout text, report JSON or None, report text or None)."""
    import contextlib
    import io
    out = next((argv[k + 1] for k, a in enumerate(argv) if a == "--out"), None)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = plc.main(argv)
    data = txt = None
    if out and os.path.isdir(out):
        newest = sorted((f for f in os.listdir(out)), key=lambda f: os.path.getmtime(os.path.join(out, f)))
        js = [f for f in newest if f.endswith(".json")]
        tx = [f for f in newest if f.endswith(".txt")]
        data = json.loads(read(os.path.join(out, js[-1]))) if js else None
        txt = read(os.path.join(out, tx[-1])) if tx else None
    return code, buf.getvalue(), data, txt


class TestStarterPack(unittest.TestCase):
    """0.4.0: the starter rule pack in rules\\ (README "Starter rule pack") on the sample log in examples\\."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.tmp.name, "out")

    def tearDown(self):
        self.tmp.cleanup()

    def pack_args(self, log):
        args = [log]
        for p in PACK:
            args += ["--rules", p]
        return args + ["--out", self.out]

    def test_every_pack_file_loads_and_is_documented(self):
        ids = []
        for p in PACK:
            r = plc.load_rules(p)
            plc.prepare(r)
            self.assertEqual(r["plugins"], ["Starfield.esm"])
            self.assertTrue(r["about"] and r["source"], p)
            self.assertEqual((r["expect"], r["forbid"], r["order"]), ([], [], []), p)  # explain rules only
            for x in r["explain"]:
                self.assertTrue(x.get("means", "").endswith("."), f"{p}: {x['id']} needs a 'means' sentence")
                ids.append(x["id"])
        self.assertEqual(sorted(ids), sorted(PACK_COUNTS))   # ids are unique and all covered here

    def test_sample_log_finds_every_rule_once_and_exits_0(self):
        code, stdout, data, txt = run_quiet(self.pack_args(SAMPLE))
        self.assertEqual(code, 0)   # FOUND never fails a run
        self.assertEqual({m["status"] for m in data["mods"]}, {plc.FOUND})
        counts = {x["id"]: x["count"] for m in data["mods"] for x in m["rules"]}
        self.assertEqual(counts, PACK_COUNTS)
        self.assertIn("  FOUND      Papyrus runtime errors 1.0.0", stdout)
        self.assertIn("FOUND     explain none-object: 1 found", txt)

    def test_lines_name_the_script_behind_the_error(self):
        _, _, data, txt = run_quiet(self.pack_args(SAMPLE))
        lines = {x["id"]: x["lines"] for m in data["mods"] for x in m["rules"]}
        self.assertIn("EXB_BeaconScript.PlaceBeacon()", lines["none-object"][0]["at"])
        # a built-in function's frame is passed over for the script that called it
        self.assertIn("EXB_BeaconScript.TrackBeacon()", lines["none-into-alias"][0]["at"])
        self.assertNotIn("at", lines["stacks-over-threshold"][0])   # a stack dump names many scripts
        self.assertNotIn("at", lines["missing-script"][0])          # no stack follows that line
        self.assertIn("   at [EXB_BeaconQuest (02000801)].EXB_BeaconScript.PlaceBeacon()", txt)

    def test_clean_log_passes(self):
        log = os.path.join(self.tmp.name, "Papyrus.0.log")
        with open(log, "w", encoding="utf-8") as f:
            f.write("[11/01/2026 - 09:00:00PM] Papyrus log opened (PC-64)\n[21:00:04] VM is freezing...\n"
                    "[21:00:04] VM is frozen\n[21:00:05] [EXB] quest started, version 1.0.0\n")
        code, stdout, data, txt = run_quiet(self.pack_args(log))
        self.assertEqual(code, 0)
        self.assertEqual({m["status"] for m in data["mods"]}, {plc.PASS})
        self.assertIn("Lines read: 4", txt)

    def test_starfield_esm_counts_as_loaded_without_a_plugins_txt_line(self):
        folder = os.path.join(self.tmp.name, "logs")
        os.makedirs(folder)
        with open(SAMPLE, encoding="utf-8") as f:
            text = f.read()
        with open(os.path.join(folder, "Papyrus.0.log"), "w", encoding="utf-8") as f:
            f.write(text)
        with open(os.path.join(folder, "plugins.txt"), "w", encoding="utf-8") as f:
            f.write("# The game never lists Starfield.esm here.\n*SomeMod.esm\n")
        code, _, data, _ = run_quiet(self.pack_args(folder))
        self.assertEqual(code, 0)
        self.assertEqual({m["plugin_state"] for m in data["mods"]}, {"active"})
        self.assertEqual({m["status"] for m in data["mods"]}, {plc.FOUND})


class TestSource(unittest.TestCase):
    def test_script_compiles_without_warnings(self):
        """A stray backslash in a docstring gives a SyntaxWarning on every run (found while writing 0.4.0)."""
        import warnings
        with open(os.path.join(TOOL_DIR, "papyrus_log_check.py"), encoding="utf-8") as f:
            source = f.read()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            compile(source, "papyrus_log_check.py", "exec")


class TestExplainRules(Base):
    """0.4.0: explain rules in a mod's own rule file."""

    def test_explain_hit_is_found_and_does_not_fail(self):
        rules = dict(RULES, expect=[], order=[], forbid=[], scripts="",
                     explain=[{"id": "none", "re": "on a None object", "means": "Something was empty."}])
        _, res = self.check(rules)
        self.assertEqual(res["status"], plc.FOUND)
        self.assertEqual(res["rules"][0]["count"], 2)

    def test_fail_still_wins_over_found(self):
        rules = dict(RULES, explain=[{"id": "none", "re": "on a None object"}])
        _, res = self.check(rules)
        self.assertEqual(res["status"], plc.FAIL)

    def test_explain_miss_is_pass_when_the_mod_logged_else_not_seen(self):
        miss = [{"id": "nothing", "re": "no such line anywhere"}]
        _, res = self.check(dict(RULES, expect=[], order=[], forbid=[], scripts="", explain=miss))
        self.assertEqual((res["status"], res["rules"][0]["status"]), (plc.PASS, plc.PASS))
        _, res = self.check(dict(RULES, prefix="NEVERLOGGED:", expect=[], order=[], forbid=[], scripts="", explain=miss))
        self.assertEqual((res["status"], res["rules"][0]["status"]), (plc.NOT_SEEN, plc.NOT_SEEN))

    def test_bad_explain_rule_names_the_file(self):
        path = os.path.join(self.dir, "bad.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dict(RULES, explain=[{"id": "x"}]), f)
        with self.assertRaisesRegex(ValueError, "bad.json: explain rule 1 needs"):
            plc.load_rules(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dict(RULES, explain=[{"id": "x", "re": "("}]), f)
        with self.assertRaisesRegex(ValueError, "bad regex in explain 'x'"):
            plc.prepare(plc.load_rules(path))


class TestRootNotLoaded(Base):
    """0.4.0 (clean-folder test of 0.3.2): with --root, a rule file whose plugin isn't active gets a NOT LOADED line."""

    def test_not_loaded_line_report_section_and_json(self):
        write_rules(self.root, "OffMod", dict(RULES, mod="Off Mod", version="0.2.0", plugins=["OffMod.esm"]))
        write_rules(self.root, "Absent", dict(RULES, mod="Absent Mod", plugins=["Absent.esm"]))
        code, stdout, data, txt = run_quiet([make_zip(self.dir), "--root", self.root, "--out", self.out])
        self.assertEqual(code, 1)   # TestMod's own FAILs
        self.assertEqual([m["mod"] for m in data["mods"]], ["Test Mod"])   # still not checked
        self.assertEqual([(n["mod"], n["plugin_state"]) for n in data["not_loaded"]],
                         [("Absent Mod", "missing"), ("Off Mod", "inactive")])
        self.assertIn("  NOT LOADED Off Mod 0.2.0\n", stdout)
        self.assertIn("  NOT LOADED Absent Mod 1.2.0\n", stdout)
        self.assertIn("  NOT LOADED Off Mod 0.2.0  (OffMod.esm: inactive; rules " + os.path.join("OffMod", "testplan", "logrules.json"), txt)

    def test_only_unloaded_mods_still_says_so(self):
        """The clean-folder case: the only rule file is for an inactive plugin, so nothing is checked."""
        root = os.path.join(self.dir, "only-off")
        write_rules(root, "OffMod", dict(RULES, mod="Off Mod", plugins=["OffMod.esm"]))
        code, stdout, data, _ = run_quiet([make_zip(self.dir), "--root", root, "--out", self.out])
        self.assertEqual(code, 0)
        self.assertEqual(data["mods"], [])
        self.assertIn("NOT LOADED Off Mod 1.2.0", stdout)

    def test_no_plugins_txt_lists_nothing_as_not_loaded(self):
        write_rules(self.root, "OffMod", dict(RULES, mod="Off Mod", plugins=["OffMod.esm"]))
        _, stdout, data, _ = run_quiet([make_zip(self.dir, plugins=None), "--root", self.root, "--out", self.out])
        self.assertEqual(data["not_loaded"], [])
        self.assertNotIn("NOT LOADED", stdout)


class TestNotLoadedWording041(Base):
    """0.4.1: the NOT LOADED sentence names what was really checked (plugins.txt, the SFSE DLL list, or both)."""

    PLUGIN = "The plugin is not active in plugins.txt, so its rules were not checked."
    DLL = "Its DLL is not among the SFSE plugin DLLs in the input, so its rules were not checked."
    BOTH = ("The plugin is not active in plugins.txt and its DLL is not among the SFSE plugin DLLs in the input, "
            "so its rules were not checked.")

    def test_reason_for_plugin_only_dll_only_and_mixed_rule_files(self):
        cases = [(["OffMod.esm"], [], self.PLUGIN),
                 (["OffMod.esm", "Absent.esm"], [],
                  "None of its plugins is active in plugins.txt, so its rules were not checked."),
                 ([], ["Nope.dll"], self.DLL),
                 (["Starfield.esm"], ["Nope.dll"], self.DLL),
                 ([], ["Nope.dll", "Gone.dll"],
                  "None of its DLLs is among the SFSE plugin DLLs in the input, so its rules were not checked."),
                 (["OffMod.esm"], ["Nope.dll"], self.BOTH)]
        for plugins, dlls, want in cases:
            with self.subTest(plugins=plugins, dlls=dlls):
                _, res = self.check(dict(RULES, plugins=plugins, dlls=dlls))
                self.assertEqual(res["status"], plc.NOT_LOADED)
                self.assertEqual(res["not_loaded_reason"], want)

    def test_report_says_the_reason_for_each_explicit_rule_file(self):
        for plugins, dlls, want in ((["OffMod.esm"], [], self.PLUGIN), ([], ["Nope.dll"], self.DLL),
                                    (["OffMod.esm"], ["Nope.dll"], self.BOTH)):
            with self.subTest(plugins=plugins, dlls=dlls):
                path = os.path.join(self.dir, "one.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(dict(RULES, plugins=plugins, dlls=dlls), f)
                out = os.path.join(self.dir, "out-%d%d" % (len(plugins), len(dlls)))
                _, stdout, data, txt = run_quiet([make_zip(self.dir), "--rules", path, "--out", out])
                self.assertEqual(data["mods"][0]["status"], plc.NOT_LOADED)
                self.assertEqual(data["mods"][0]["not_loaded_reason"], want)
                self.assertIn("   " + want + "\n", txt)
                if dlls and not plugins:
                    self.assertNotIn("plugins.txt, so its rules", txt)
                self.assertIn("NOT LOADED", stdout)

    def test_root_not_loaded_list_gives_the_reason(self):
        write_rules(self.root, "DllMod", dict(RULES, mod="Dll Mod", plugins=[], dlls=["Nope.dll"]))
        write_rules(self.root, "OffMod", dict(RULES, mod="Off Mod", plugins=["OffMod.esm"]))
        _, _, data, txt = run_quiet([make_zip(self.dir), "--root", self.root, "--out", self.out])
        self.assertEqual([(n["mod"], n["not_loaded_reason"]) for n in data["not_loaded"]],
                         [("Dll Mod", self.DLL), ("Off Mod", self.PLUGIN)])
        self.assertIn("\n    " + self.DLL + "\n", txt)
        self.assertIn("\n    " + self.PLUGIN + "\n", txt)
        # the 0.4.0 keys are all still there; only the new key is added
        self.assertEqual(set(data["not_loaded"][0]) - {"not_loaded_reason"},
                         {"mod", "version", "path", "plugins", "plugin_state"})


class TestNotSeenFound041(Base):
    """0.4.1: a mod that never logged but whose explain rules matched shows "NOT SEEN (N found)"."""

    EXPLAIN = [{"id": "none", "re": "on a None object", "means": "Something was empty."},
               {"id": "foo", "re": "Cannot call Foo\\(\\)", "means": "Foo was empty."}]
    QUIET = dict(RULES, prefix="NEVERLOGGED:", expect=[{"id": "three", "re": "TEST: step three"}],
                 order=[], forbid=[], scripts="", explain=EXPLAIN)

    def run_rules(self, rules, name="quiet.json"):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rules, f)
        return run_quiet([make_zip(self.dir), "--rules", path, "--out", self.out])

    def test_explain_found_counts_the_lines_of_all_explain_rules(self):
        _, res = self.check(self.QUIET)
        self.assertEqual(res["status"], plc.NOT_SEEN)
        self.assertEqual(res["explain_found"], 3)   # 2 "None object" lines + 1 "Foo()" line (one line counted twice)
        self.assertEqual(plc.shown_status(res), "NOT SEEN (3 found)")
        _, res = self.check(dict(self.QUIET, explain=[]))
        self.assertEqual(res["explain_found"], 0)
        self.assertEqual(plc.shown_status(res), "NOT SEEN")
        _, res = self.check(dict(self.QUIET, prefix="TEST:"))   # the mod ran: FOUND, no "(N found)"
        self.assertEqual(plc.shown_status(res), plc.FOUND)

    def test_stdout_and_summary_say_not_seen_n_found(self):
        code, stdout, data, txt = self.run_rules(self.QUIET)
        self.assertEqual(code, 0)   # explain is never a FAIL
        mod = data["mods"][0]
        self.assertEqual(mod["status"], plc.NOT_SEEN)   # the JSON status is unchanged
        self.assertEqual(mod["explain_found"], 3)
        self.assertIn("  NOT SEEN (3 found) Test Mod 1.2.0\n", stdout)
        self.assertIn("  NOT SEEN (3 found) Test Mod 1.2.0  (", txt)
        self.assertIn("== Test Mod 1.2.0: NOT SEEN\n", txt)

    def test_plain_not_seen_is_unchanged(self):
        _, stdout, data, txt = self.run_rules(dict(self.QUIET, explain=[{"id": "x", "re": "no such line"}]))
        self.assertEqual(data["mods"][0]["explain_found"], 0)
        self.assertIn("  NOT SEEN   Test Mod 1.2.0\n", stdout)
        self.assertNotIn("found)", stdout)

    def test_mods_keys_only_gain_explain_found(self):
        _, _, data, _ = self.run_rules(self.QUIET)
        self.assertEqual(set(data["mods"][0]) - {"explain_found"},
                         {"mod", "version", "rules_file", "rule_file_version", "plugins", "plugin_state",
                          "named_in_note", "rules", "prefix_lines", "first_prefix", "last_prefix", "logs", "status"})


class TestReviewFixes040(Base):
    """0.4.0 code-review fixes."""

    def test_starfield_esm_does_not_make_other_plugins_active(self):
        cases = [(["Starfield.esm", "OffMod.esm"], [], "inactive"),
                 (["Starfield.esm", "Absent.esm"], [], "missing"),
                 (["Starfield.esm", "TestMod.esm"], [], "active"),
                 (["Absent.esm", "starfield.esm"], [], "missing"),
                 (["Starfield.esm"], ["Nope.dll"], "missing"),
                 (["Starfield.esm"], ["MyDll.dll"], "active"),
                 (["Starfield.esm"], [], "active")]
        for plugins, dlls, want in cases:
            with self.subTest(plugins=plugins, dlls=dlls):
                _, res = self.check(dict(RULES, plugins=plugins, dlls=dlls))
                self.assertEqual(res["plugin_state"], want)
                if want != "active":
                    self.assertEqual(res["status"], plc.NOT_LOADED)
        _, res = self.check(dict(RULES, plugins=["Starfield.esm", "OffMod.esm"]), plugins=None)
        self.assertEqual(res["plugin_state"], "unknown")

    def test_found_does_not_beat_not_seen_for_a_mod_that_never_logged(self):
        explain = [{"id": "none", "re": "on a None object", "means": "Something was empty."}]
        rules = dict(RULES, prefix="NEVERLOGGED:", expect=[{"id": "three", "re": "TEST: step three"}],
                     order=[], forbid=[], scripts="", explain=explain)
        _, res = self.check(rules)
        self.assertEqual(res["status"], plc.NOT_SEEN)
        self.assertEqual([r["status"] for r in res["rules"] if r["kind"] == "explain"], [plc.FOUND])
        for scripts in ("", "^NOSUCH_"):
            with self.subTest(scripts=scripts):
                # forbid only / scripts only: still not explain-only, so NOT SEEN
                r2 = dict(rules, expect=[], forbid=[{"id": "bad", "re": "nothing like this"}] if not scripts else [],
                          scripts=scripts)
                _, res = self.check(r2)
                self.assertEqual(res["status"], plc.NOT_SEEN)
        _, res = self.check(dict(rules, expect=[]))   # explain rules only, like the starter pack
        self.assertEqual(res["status"], plc.FOUND)
        _, res = self.check(dict(rules, prefix="TEST:"))   # the mod ran
        self.assertEqual(res["status"], plc.FOUND)

    def test_not_seen_mod_still_shows_its_found_lines_in_the_report(self):
        path = os.path.join(self.dir, "quiet.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dict(RULES, prefix="NEVERLOGGED:", expect=[{"id": "three", "re": "TEST: step three"}],
                           order=[], forbid=[], scripts="",
                           explain=[{"id": "none", "re": "on a None object", "means": "Something was empty."}]), f)
        code, stdout, data, txt = run_quiet([make_zip(self.dir), "--rules", path, "--out", self.out])
        self.assertEqual(code, 0)
        self.assertEqual(data["mods"][0]["status"], plc.NOT_SEEN)
        self.assertIn("NOT SEEN", stdout)
        self.assertIn("explain none: 2 found", txt)
        self.assertIn("(Something was empty.)", txt)

    def test_not_loaded_heading_fits_dll_only_rule_files(self):
        write_rules(self.root, "DllMod", dict(RULES, mod="Dll Mod", plugins=[], dlls=["Nope.dll"]))
        _, _, data, txt = run_quiet([make_zip(self.dir), "--root", self.root, "--out", self.out])
        self.assertEqual([n["mod"] for n in data["not_loaded"]], ["Dll Mod"])
        self.assertIn("none of their plugins or DLLs is loaded", txt)
        self.assertNotIn("is active in plugins.txt", txt)

    def test_min_and_always_are_refused_on_explain_rules(self):
        path = os.path.join(self.dir, "bad.json")
        for key, value in (("min", 2), ("always", True)):
            with self.subTest(key=key):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(dict(RULES, explain=[{"id": "x", "re": "y", key: value}]), f)
                with self.assertRaisesRegex(ValueError, f"bad.json: explain rule 'x' has '{key}'"):
                    plc.load_rules(path)

    def test_stack_frames_are_not_read_without_explain_rules(self):
        real = plc.script_frame

        def refuse(stack):
            raise AssertionError("script_frame called for a rule file with no explain rules")
        plc.script_frame = refuse
        try:
            _, res = self.check(RULES)
        finally:
            plc.script_frame = real
        self.assertEqual(res["status"], plc.FAIL)


class TestRuleChecks041(Base):
    """0.4.1: 'min' and 'always' checks on explain and forbid rules."""

    def load(self, **kinds):
        path = os.path.join(self.dir, "rc.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dict(RULES, **kinds), f)
        return plc.load_rules(path)

    def errors(self, **kinds):
        try:
            self.load(**kinds)
        except ValueError as e:
            return str(e)
        return None

    def test_bad_min_on_an_explain_rule_gives_the_explain_error(self):
        for value in (0, "two", 2.5, -1):
            with self.subTest(value=value):
                msg = self.errors(explain=[{"id": "x", "re": "y", "min": value}])
                self.assertIsNotNone(msg)
                self.assertIn("rc.json: explain rule 'x' has 'min'", msg)
                self.assertIn("which only expect rules use", msg)
                self.assertNotIn("whole number", msg)

    def test_no_op_min_and_always_are_accepted_on_explain_rules(self):
        for extra in ({"min": 1}, {"always": False}, {"min": 1, "always": False}):
            with self.subTest(extra=extra):
                r = self.load(explain=[dict({"id": "x", "re": "y"}, **extra)])
                self.assertEqual(len(r["explain"]), 1)
        for extra in ({"min": True}, {"always": 0}, {"always": None}):   # look alike, but not the no-op values
            with self.subTest(extra=extra):
                self.assertIsNotNone(self.errors(explain=[dict({"id": "x", "re": "y"}, **extra)]))

    def test_no_op_explain_values_change_nothing_in_a_run(self):
        explain = [{"id": "none", "re": "on a None object", "means": "Something was empty."}]
        _, plain = self.check(dict(RULES, explain=explain))
        _, noop = self.check(dict(RULES, explain=[dict(explain[0], min=1, always=False)]))
        self.assertEqual(plain["status"], noop["status"])
        self.assertEqual([r for r in plain["rules"] if r["kind"] == "explain"],
                         [r for r in noop["rules"] if r["kind"] == "explain"])

    def test_min_and_always_are_refused_on_forbid_rules(self):
        for key, value in (("min", 2), ("min", 1), ("min", "x"), ("always", True), ("always", False)):
            with self.subTest(key=key, value=value):
                msg = self.errors(forbid=[{"id": "bad", "re": "y", key: value}])
                self.assertIsNotNone(msg)
                self.assertIn(f"rc.json: forbid rule 'bad' has '{key}', which only expect rules use", msg)
                self.assertIn(f"Remove '{key}' from it", msg)

    def test_min_and_always_still_work_on_expect_rules(self):
        r = self.load(expect=[{"id": "a", "re": "TEST: step one", "min": 2, "always": True}])
        self.assertEqual(r["expect"][0]["min"], 2)
        msg = self.errors(expect=[{"id": "a", "re": "y", "min": 0}])
        self.assertIn("expect rule 'a' has 'min' 0; it should be a whole number", msg)


class TestOfficialMasters041(Base):
    """0.4.1: every official master is loaded without a plugins.txt line when its file is in Data."""

    DATA = [{"name": n} for n in ("Starfield.esm", "ShatteredSpace.esm", "SFBGS003.esm",
                                  "BlueprintShips-Starfield.esm", "TestMod.esm")]

    def check_with(self, rules, data):
        """check() with a manifest that has (data is a list) or lacks (None) listing.dataPlugins."""
        global MANIFEST
        saved = MANIFEST
        try:
            listing = dict(saved["listing"])
            if data is not None:
                listing["dataPlugins"] = data
            MANIFEST = dict(saved, listing=listing)
            return self.check(rules)
        finally:
            MANIFEST = saved

    def test_is_official(self):
        for name in ("Starfield.esm", "constellation.esm", "OldMars.esm", "ShatteredSpace.esm", "SFBGS003.esm",
                     "sfbgs00d.esm", "BlueprintShips-Starfield.esm", "BlueprintShips-SFBGS050.esm"):
            self.assertTrue(plc.is_official(name), name)
        for name in ("TestMod.esm", "MyMod-ShatteredSpaceAddon.esm", "BlueprintShips-TestMod.esm", "sfta01.esm",
                     "SFBGS0031.esm", "ShatteredSpace.esp", "Starfield.esm.bak"):
            self.assertFalse(plc.is_official(name), name)

    def test_official_master_only_files_count_as_loaded(self):
        for plugins in (["ShatteredSpace.esm"], ["SFBGS003.esm"], ["BlueprintShips-Starfield.esm"],
                        ["Starfield.esm", "ShatteredSpace.esm"]):
            for data in (self.DATA, None):
                with self.subTest(plugins=plugins, data=data is not None):
                    _, res = self.check_with(dict(RULES, plugins=plugins), data)
                    self.assertEqual(res["plugin_state"], "active")
                    self.assertNotEqual(res["status"], plc.NOT_LOADED)

    def test_official_master_missing_from_data_is_not_loaded(self):
        _, res = self.check_with(dict(RULES, plugins=["Constellation.esm"]), self.DATA)
        self.assertEqual(res["plugin_state"], "missing")
        self.assertEqual(res["status"], plc.NOT_LOADED)
        self.assertEqual(res["not_loaded_reason"], "Its official master is not in the input's Data plugin list, "
                                                   "so its rules were not checked.")
        _, res = self.check_with(dict(RULES, plugins=["Constellation.esm", "OldMars.esm"]), self.DATA)
        self.assertEqual(res["not_loaded_reason"], "None of its official masters is in the input's Data plugin "
                                                   "list, so its rules were not checked.")
        # Starfield.esm stays always loaded, even when a listing lacks it (0.4.0)
        _, res = self.check_with(dict(RULES, plugins=["Starfield.esm"]), [{"name": "TestMod.esm"}])
        self.assertEqual(res["plugin_state"], "active")

    def test_official_masters_do_not_make_other_plugins_active(self):
        cases = [(["ShatteredSpace.esm", "OffMod.esm"], [], "inactive",
                  "The plugin is not active in plugins.txt, so its rules were not checked."),
                 (["SFBGS003.esm", "Absent.esm"], [], "missing", None),
                 (["ShatteredSpace.esm", "TestMod.esm"], [], "active", None),
                 (["ShatteredSpace.esm"], ["Nope.dll"], "missing",
                  "Its DLL is not among the SFSE plugin DLLs in the input, so its rules were not checked."),
                 (["ShatteredSpace.esm"], ["MyDll.dll"], "active", None)]
        for plugins, dlls, want, reason in cases:
            with self.subTest(plugins=plugins, dlls=dlls):
                _, res = self.check_with(dict(RULES, plugins=plugins, dlls=dlls), self.DATA)
                self.assertEqual(res["plugin_state"], want)
                if reason:
                    self.assertEqual(res["not_loaded_reason"], reason)

    def test_a_bad_data_listing_is_ignored(self):
        _, res = self.check_with(dict(RULES, plugins=["Constellation.esm"]), "oops")
        self.assertEqual(res["plugin_state"], "active")   # no usable listing: counts as loaded


class TestListings041Review(Base):
    """0.4.1 code review: the collector's empty listings when it found no game folder, and plain-string entries."""

    def check_manifest(self, rules, listing, **extra):
        global MANIFEST
        saved = MANIFEST
        try:
            MANIFEST = dict(saved, listing=listing, **extra)
            return self.check(rules)
        finally:
            MANIFEST = saved

    def test_empty_data_listing_counts_as_no_listing(self):
        for extra in ({"gamePath": ""}, {"gamePath": None}, {}, {"gamePath": "C:\\Games\\Starfield"}):
            with self.subTest(extra=extra):
                _, res = self.check_manifest(dict(RULES, plugins=["ShatteredSpace.esm"]),
                                             {"sfsePluginDlls": [], "dataPlugins": []}, **extra)
                self.assertEqual(res["plugin_state"], "active")
                self.assertNotEqual(res["status"], plc.NOT_LOADED)

    def test_empty_dll_listing_without_a_game_folder_is_unknown(self):
        rules = dict(RULES, plugins=[], dlls=["MyPlugin.dll"])
        for extra in ({"gamePath": ""}, {"gamePath": None}):
            with self.subTest(extra=extra):
                _, res = self.check_manifest(rules, {"sfsePluginDlls": [], "dataPlugins": []}, **extra)
                self.assertEqual(res["plugin_state"], "unknown")
                self.assertNotEqual(res["status"], plc.NOT_LOADED)
        # with a game folder, an empty SFSE plugins folder is real: the DLL is missing (0.4.0)
        _, res = self.check_manifest(rules, {"sfsePluginDlls": []}, gamePath="C:\\Games\\Starfield")
        self.assertEqual(res["plugin_state"], "missing")
        _, res = self.check_manifest(rules, {"sfsePluginDlls": []})
        self.assertEqual(res["plugin_state"], "missing")

    def test_plain_string_entries_are_names(self):
        _, res = self.check_manifest(dict(RULES, plugins=["ShatteredSpace.esm"]),
                                     {"sfsePluginDlls": ["MyDll.dll"], "dataPlugins": ["ShatteredSpace.esm"]})
        self.assertEqual(res["plugin_state"], "active")
        _, res = self.check_manifest(dict(RULES, plugins=["Constellation.esm"]),
                                     {"dataPlugins": ["ShatteredSpace.esm", {"name": "Starfield.esm"}]})
        self.assertEqual(res["plugin_state"], "missing")
        _, res = self.check_manifest(dict(RULES, plugins=[], dlls=["MyDll.dll"]), {"sfsePluginDlls": ["MyDll.dll"]})
        self.assertEqual(res["plugin_state"], "active")

    def test_a_listing_with_no_usable_names_is_ignored(self):
        _, res = self.check_manifest(dict(RULES, plugins=["Constellation.esm"]), {"dataPlugins": [1, {"size": 3}]})
        self.assertEqual(res["plugin_state"], "active")

    # round 2
    def package(self, manifest, files=()):
        global MANIFEST
        saved = MANIFEST
        try:
            MANIFEST = manifest
            path = make_zip(self.dir)
        finally:
            MANIFEST = saved
        if files:
            with zipfile.ZipFile(path, "a") as z:
                for name in files:
                    z.writestr(name, "x")
        return plc.Package(path)

    def test_an_ignored_dll_listing_does_not_fall_back_to_stray_dlls(self):
        pkg = self.package(dict(MANIFEST, gamePath="", listing={"sfsePluginDlls": []}), ["stray\\Other.dll"])
        self.assertIsNone(pkg.sfse_dlls())
        pkg = self.package({"tool": "x"}, ["stray\\Other.dll"])   # no listing at all: the .dll files count (0.4.0)
        self.assertEqual(pkg.sfse_dlls(), {"other.dll"})

    # round 4
    def test_null_or_missing_listing_values_never_fall_back_to_stray_dlls(self):
        for listing in ({"sfsePluginDlls": None}, None, {}, {"dataPlugins": [{"name": "Starfield.esm"}]},
                        {"dataPlugins": "oops"}, {"sfsePluginDlls": ["Data/SFSE/Plugins/..", "."]}):
            with self.subTest(listing=listing):
                pkg = self.package(dict(MANIFEST, listing=listing), ["stray\\Other.dll"])
                self.assertIsNone(pkg.sfse_dlls())
        pkg = self.package(dict(MANIFEST, listing={"dataPlugins": None, "sfsePluginDlls": ["A.dll"]}))
        self.assertIsNone(pkg.data_plugins())
        self.assertEqual(pkg.sfse_dlls(), {"a.dll"})

    def test_a_data_listing_without_starfield_esm_is_ignored(self):
        _, res = self.check_manifest(dict(RULES, plugins=["ShatteredSpace.esm"]), {"dataPlugins": ["Some.esp"]})
        self.assertEqual(res["plugin_state"], "active")
        pkg = self.package(dict(MANIFEST, listing={"dataPlugins": [{"name": "Some.esp"}]}))
        self.assertIsNone(pkg.data_plugins())

    def test_names_are_cut_to_the_file_name_and_must_be_strings(self):
        pkg = self.package(dict(MANIFEST, listing={
            "sfsePluginDlls": ["Data\\SFSE\\Plugins\\MyDll.dll", {"name": "C:/x/Two.dll"}, {"name": ["x"]}, 5],
            "dataPlugins": [" Starfield.esm ", {"name": 3}]}))
        self.assertEqual(pkg.sfse_dlls(), {"mydll.dll", "two.dll"})
        self.assertEqual(pkg.data_plugins(), {"starfield.esm"})

    def test_an_ignored_listing_is_logged_once(self):
        pkg = self.package(dict(MANIFEST, gamePath="", listing={"sfsePluginDlls": [], "dataPlugins": []}))
        lines = []
        with unittest.mock.patch.object(plc.Log, "write", lines.append):
            for _ in range(3):
                pkg.sfse_dlls()
                pkg.data_plugins()
        self.assertEqual(len([x for x in lines if "sfsePluginDlls" in x]), 1)
        self.assertEqual(len([x for x in lines if "dataPlugins" in x]), 1)

    def test_a_listing_without_the_key_logs_its_exact_note(self):
        pkg = self.package(dict(MANIFEST, listing={"dataPlugins": ["Starfield.esm"]}), ["stray\\Other.dll"])
        lines = []
        with unittest.mock.patch.object(plc.Log, "write", lines.append):
            self.assertIsNone(pkg.sfse_dlls())
        self.assertEqual(lines, ["manifest.json: listing has no sfsePluginDlls; ignored"])

    # round 3
    def test_a_listing_of_the_wrong_shape_does_not_fall_back_to_stray_dlls(self):
        for listing in ({"sfsePluginDlls": "oops"}, {"sfsePluginDlls": 5}, "oops", ["x"]):
            with self.subTest(listing=listing):
                pkg = self.package(dict(MANIFEST, listing=listing), ["stray\\Other.dll"])
                self.assertIsNone(pkg.sfse_dlls())
                self.assertIsNone(pkg.data_plugins())

    def test_a_bad_dll_list_keeps_a_good_data_list(self):
        pkg = self.package(dict(MANIFEST, listing={"sfsePluginDlls": 5, "dataPlugins": ["Starfield.esm"]}))
        self.assertIsNone(pkg.sfse_dlls())
        self.assertEqual(pkg.data_plugins(), {"starfield.esm"})
        _, res = self.check_manifest(dict(RULES, plugins=["ShatteredSpace.esm"]),
                                     {"sfsePluginDlls": 5, "dataPlugins": ["Starfield.esm"]})
        self.assertEqual(res["status"], plc.NOT_LOADED)

    def test_an_entry_with_no_file_name_is_skipped(self):
        pkg = self.package(dict(MANIFEST, listing={"sfsePluginDlls": ["Data\\SFSE\\Plugins\\", "  ", "a/ "]}))
        self.assertIsNone(pkg.sfse_dlls())
        pkg = self.package(dict(MANIFEST, listing={"sfsePluginDlls": ["Data/SFSE/Plugins/", "One.dll"]}))
        self.assertEqual(pkg.sfse_dlls(), {"one.dll"})


class TestBadInput042(Base):
    """0.4.2 bug hunt: a bad folder or output path says what is wrong and what to do, not a raw [WinError n]."""

    def run_main(self, argv):
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = plc.main(argv)
        return code, err.getvalue()

    def zip_and_rules(self):
        rules = os.path.join(self.dir, "r.json")
        with open(rules, "w", encoding="utf-8") as f:
            json.dump(RULES, f)
        return make_zip(self.dir), rules

    def test_a_missing_root_names_the_option(self):
        z, _ = self.zip_and_rules()
        code, err = self.run_main([z, "--root", os.path.join(self.dir, "nope"), "--out", self.out])
        self.assertEqual(code, 2)
        self.assertIn("--root", err)
        self.assertIn("is not a folder", err)
        self.assertNotIn("WinError", err)

    def test_a_missing_logs_dir_names_the_option(self):
        _, rules = self.zip_and_rules()
        code, err = self.run_main(["--logs-dir", os.path.join(self.dir, "nope"), "--rules", rules, "--out", self.out])
        self.assertEqual(code, 2)
        self.assertIn("--logs-dir", err)
        self.assertIn("is not a folder", err)
        self.assertNotIn("WinError", err)

    def test_an_out_path_that_is_a_file_says_what_to_do(self):
        z, rules = self.zip_and_rules()
        afile = os.path.join(self.dir, "afile.txt")
        with open(afile, "w") as f:
            f.write("x")
        for out in (afile, os.path.join(afile, "sub")):
            code, err = self.run_main([z, "--rules", rules, "--out", out])
            self.assertEqual(code, 2)
            self.assertIn("Can't write the report in", err)
            self.assertIn("Give --out a folder you can write to", err)
            self.assertNotIn("WinError", err)

    def test_a_mod_name_the_console_cannot_show_does_not_stop_the_run(self):
        import contextlib
        import io
        z, _ = self.zip_and_rules()
        rules = os.path.join(self.dir, "cjk.json")
        with open(rules, "w", encoding="utf-8") as f:
            json.dump(dict(RULES, mod="Mod 名前"), f, ensure_ascii=False)
        raw = io.BytesIO()
        console = io.TextIOWrapper(raw, encoding="cp1252", errors="strict", newline="")
        with contextlib.redirect_stdout(console):
            code = plc.main([z, "--rules", rules, "--out", self.out])
        console.flush()
        self.assertIn(code, (0, 1))
        self.assertIn(b"Mod ??", raw.getvalue())

    def test_a_rule_file_that_is_not_utf8_says_so(self):
        z, _ = self.zip_and_rules()
        bad = os.path.join(self.dir, "u16.json")
        with open(bad, "w", encoding="utf-16") as f:
            json.dump(RULES, f)
        code, err = self.run_main([z, "--rules", bad, "--out", self.out])
        self.assertEqual(code, 2)
        self.assertIn("is not UTF-8 text", err)
        self.assertNotIn("commas and quotes", err)


class TestReviewRound1042(Base):
    """0.4.2 /code-review round 1: error text names its real source and cause, and the console mode is lenient only during main()."""

    run_main = TestBadInput042.run_main
    zip_and_rules = TestBadInput042.zip_and_rules

    def test_a_bad_environment_folder_names_the_variable(self):
        _, rules = self.zip_and_rules()
        old = os.environ.get("PAPYRUS_LOG_CHECK_LOGS")
        os.environ["PAPYRUS_LOG_CHECK_LOGS"] = os.path.join(self.dir, "gone")
        try:
            code, err = self.run_main(["--rules", rules, "--out", self.out])
        finally:
            if old is None:
                del os.environ["PAPYRUS_LOG_CHECK_LOGS"]
            else:
                os.environ["PAPYRUS_LOG_CHECK_LOGS"] = old
        self.assertEqual(code, 2)
        self.assertIn("PAPYRUS_LOG_CHECK_LOGS", err)
        self.assertNotIn("--logs-dir " + os.path.join(self.dir, "gone"), err)

    def test_a_full_disk_does_not_blame_the_path(self):
        import errno
        from unittest import mock
        z, rules = self.zip_and_rules()
        with mock.patch.object(plc.json, "dump", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            code, err = self.run_main([z, "--rules", rules, "--out", self.out])
        self.assertEqual(code, 2)
        self.assertIn("No space left on device", err)
        self.assertIn("disk has room", err)
        self.assertNotIn("Give --out a folder you can write to", err)

    def test_argparse_text_with_an_unencodable_name_does_not_crash_and_the_mode_comes_back(self):
        import contextlib
        import io
        raw = io.BytesIO()
        console = io.TextIOWrapper(raw, encoding="cp1252", errors="strict", newline="")
        with contextlib.redirect_stderr(console):
            with self.assertRaises(SystemExit) as cm:
                plc.main(["--max-lines", "名前"])
            self.assertEqual(console.errors, "strict")
        self.assertEqual(cm.exception.code, 2)
        console.flush()
        self.assertIn(b"??", raw.getvalue())


class TestReviewRound2042(Base):
    """0.4.2 /code-review round 2: the zip is closed after a failing constructor and after a run, permission errors name
    the folder fix, the environment-variable text reads as one sentence, and main() survives a closed stream."""

    run_main = TestBadInput042.run_main
    zip_and_rules = TestBadInput042.zip_and_rules

    def test_a_constructor_that_fails_part_way_closes_the_zip(self):
        from unittest import mock
        z, _ = self.zip_and_rules()
        opened = []
        real = plc.zipfile.ZipFile

        def spy(*a, **k):
            zf = real(*a, **k)
            opened.append(zf)
            return zf
        with mock.patch.object(plc.zipfile, "ZipFile", side_effect=spy):
            with mock.patch.object(plc.Package, "_collector_manifest", side_effect=KeyError("boom")):
                with self.assertRaises(KeyError):
                    plc.Package(z)
        self.assertEqual(len(opened), 1)
        self.assertIsNone(opened[0].fp, "the zip was left open")

    def test_a_finished_run_closes_the_zip(self):
        z, rules = self.zip_and_rules()
        opened = []
        real = plc.zipfile.ZipFile
        from unittest import mock

        def spy(*a, **k):
            zf = real(*a, **k)
            opened.append(zf)
            return zf
        real_close = plc.Package.close
        closes = []

        def counting_close(pkg):
            closes.append(pkg)
            return real_close(pkg)
        with mock.patch.object(plc.zipfile, "ZipFile", side_effect=spy):
            with mock.patch.object(plc.Package, "close", counting_close):
                self.run_main([z, "--rules", rules, "--out", self.out])
        self.assertTrue(opened)
        self.assertEqual(len(closes), 1, "run() must close the Package itself")
        self.assertTrue(all(zf.fp is None for zf in opened), "the zip was left open")

    def test_a_permission_error_says_to_give_a_folder_you_can_write_to(self):
        import errno
        from unittest import mock
        z, rules = self.zip_and_rules()
        with mock.patch.object(plc.json, "dump", side_effect=PermissionError(errno.EACCES, "Permission denied")):
            code, err = self.run_main([z, "--rules", rules, "--out", self.out])
        self.assertEqual(code, 2)
        self.assertIn("Give --out a folder you can write to", err)
        self.assertNotIn("The folder is fine as a path", err)

    def test_the_environment_variable_error_is_one_clear_sentence(self):
        gone = os.path.join(self.dir, "gone")
        with self.assertRaises(FileNotFoundError) as cm:
            plc.newest_zip(gone, from_env=True)
        self.assertIn("PAPYRUS_LOG_CHECK_LOGS is set to '" + gone + "', which is not a folder.", str(cm.exception))
        with self.assertRaises(FileNotFoundError) as cm:
            plc.newest_zip(gone)
        self.assertIn("--logs-dir '" + gone + "' is not a folder", str(cm.exception))

    def test_main_survives_a_stream_that_is_closed_during_the_run(self):
        # A guard, not a test of one change: a stream closed during the run must not crash main() or change the code.
        import io
        from unittest import mock
        raw = io.BytesIO()
        console = io.TextIOWrapper(raw, encoding="utf-8", errors="strict", newline="")
        z, rules = self.zip_and_rules()
        expected, _ = self.run_main([z, "--rules", rules, "--out", self.out])
        real_run = plc._main

        def closing(argv):
            code = real_run(argv)
            console.close()
            return code
        with mock.patch.object(plc, "_main", side_effect=closing):
            with mock.patch.object(plc.sys, "stderr", console):
                code = plc.main([z, "--rules", rules, "--out", self.out])
        self.assertTrue(console.closed)
        self.assertEqual(code, expected)

    def test_a_read_only_folder_says_to_give_a_folder_you_can_write_to(self):
        import errno
        from unittest import mock
        z, rules = self.zip_and_rules()
        for number in (errno.EROFS, errno.ENAMETOOLONG):
            with mock.patch.object(plc.json, "dump", side_effect=OSError(number, "refused")):
                code, err = self.run_main([z, "--rules", rules, "--out", self.out])
            self.assertEqual(code, 2)
            self.assertIn("Give --out a folder you can write to", err)
            self.assertNotIn("disk has room", err)

    def failing_open(self, suffix, number):
        """An open() that creates the file whose name ends in `suffix`, then fails on its first write."""
        import builtins
        real_open = builtins.open

        def fake(path, *a, **k):
            f = real_open(path, *a, **k)
            if str(path).endswith(suffix):
                def broken(*_a, **_k):
                    raise OSError(number, "refused")
                f.write = broken
            return f
        return fake

    def test_a_failed_json_write_removes_the_json_and_keeps_the_complete_text_report(self):
        import errno
        from unittest import mock
        z, rules = self.zip_and_rules()
        with mock.patch.object(plc.json, "dump", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            code, err = self.run_main([z, "--rules", rules, "--out", self.out])
        self.assertEqual(code, 2)
        names = os.listdir(self.out)
        self.assertEqual([n for n in names if n.endswith(".json")], [])
        self.assertEqual(len([n for n in names if n.endswith(".txt")]), 1)
        self.assertIn("kept", err)
        with open(os.path.join(self.out, names[0]), encoding="utf-8") as f:
            self.assertIn("papyrus-log-check", f.read())

    def test_a_failed_text_write_removes_the_half_written_file(self):
        import errno
        from unittest import mock
        z, rules = self.zip_and_rules()
        with mock.patch("builtins.open", self.failing_open(".txt", errno.ENOSPC)):
            code, err = self.run_main([z, "--rules", rules, "--out", self.out])
        self.assertEqual(code, 2)
        self.assertEqual(os.listdir(self.out), [])
        self.assertNotIn("kept", err)

    def test_a_failed_open_never_removes_a_file_this_run_did_not_create(self):
        import errno
        from unittest import mock
        z, rules = self.zip_and_rules()
        os.makedirs(self.out, exist_ok=True)
        taken = []
        import builtins
        real_open = builtins.open

        def fake(path, *a, **k):
            mode = k.get("mode", a[0] if a else "r")
            # Another run creates the same report name between the exists check and our open (once).
            if str(path).endswith(".txt") and mode == "x" and not taken:
                with real_open(path, "w") as other:
                    other.write("other run")
                taken.append(path)
                raise FileExistsError(errno.EEXIST, "exists")
            return real_open(path, *a, **k)
        with mock.patch("builtins.open", fake):
            code, err = self.run_main([z, "--rules", rules, "--out", self.out])
        # The run takes the next free name and succeeds; the other run's file is untouched.
        self.assertIn(code, (0, 1))
        self.assertEqual(len(taken), 1)
        with open(taken[0], encoding="utf-8") as f:
            self.assertEqual(f.read(), "other run")
        self.assertEqual(len([n for n in os.listdir(self.out) if n.endswith("-2.txt")]), 1)
        self.assertEqual(len([n for n in os.listdir(self.out) if n.endswith("-2.json")]), 1)

    def test_a_name_taken_by_a_dangling_link_is_skipped(self):
        from unittest import mock
        z, rules = self.zip_and_rules()
        # os.path.exists says False for a dangling link; lexists says True. Simulate exists() blind to the name.
        real_lexists = os.path.lexists
        seen = []

        def fake_lexists(p):
            if str(p).endswith(".txt") and not seen:
                seen.append(p)
                return True
            return real_lexists(p)
        with mock.patch("os.path.lexists", fake_lexists):
            code, err = self.run_main([z, "--rules", rules, "--out", self.out])
        self.assertIn(code, (0, 1))
        self.assertEqual(len([n for n in os.listdir(self.out) if n.endswith("-2.txt")]), 1)

    def test_a_non_os_error_while_writing_the_json_exits_2_with_one_line_and_keeps_the_text(self):
        # Round 7: a non-OSError used to escape main() as a traceback with exit 1 (the FAIL code).
        from unittest import mock
        z, rules = self.zip_and_rules()
        with mock.patch.object(plc.json, "dump", side_effect=TypeError("not serializable")):
            code, err = self.run_main([z, "--rules", rules, "--out", self.out])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)
        self.assertIn("TypeError: not serializable", err)
        self.assertIn("This is a bug in papyrus-log-check", err)
        names = os.listdir(self.out)
        self.assertEqual([n for n in names if n.endswith(".json")], [])
        txt = [n for n in names if n.endswith(".txt")]
        self.assertEqual(len(txt), 1)
        self.assertIn("The text report was written in full and is kept: " + os.path.join(self.out, txt[0]), err)

    def test_a_json_name_taken_by_another_run_moves_the_pair_to_the_next_name(self):
        # Round 7: this used to stop with exit 2 and leave an unpaired .txt behind.
        import errno
        from unittest import mock
        z, rules = self.zip_and_rules()
        import builtins
        real_open = builtins.open
        taken = []

        def fake(path, *a, **k):
            if str(path).endswith('.json') and 'logcheck-' in str(path) and not taken:
                taken.append(path)
                raise FileExistsError(errno.EEXIST, 'exists')
            return real_open(path, *a, **k)
        with mock.patch('builtins.open', fake):
            code, err = self.run_main([z, '--rules', rules, '--out', self.out])
        self.assertIn(code, (0, 1), err)
        names = sorted(os.listdir(self.out))
        self.assertEqual(len(names), 2, names)
        self.assertTrue(names[0].endswith('-2.json') and names[1].endswith('-2.txt'), names)
        self.assertFalse(os.path.lexists(taken[0][:-len('.json')] + '.txt'), "the unpaired .txt was left behind")
        with open(os.path.join(self.out, names[1]), encoding='utf-8') as f:
            self.assertIn('papyrus-log-check', f.read())

    def test_a_resource_error_gets_neither_the_disk_text_nor_the_path_text(self):
        import errno
        from unittest import mock
        z, rules = self.zip_and_rules()
        with mock.patch.object(plc.json, "dump", side_effect=OSError(errno.EMFILE, "Too many open files")):
            code, err = self.run_main([z, "--rules", rules, "--out", self.out])
        self.assertEqual(code, 2)
        self.assertIn("Too many open files", err)
        self.assertIn("Check the folder and the disk", err)
        self.assertNotIn("disk has room", err)
        self.assertNotIn("Give --out a folder you can write to", err)

    def test_a_symbolic_link_loop_gets_the_path_text(self):
        import errno
        from unittest import mock
        z, rules = self.zip_and_rules()
        with mock.patch.object(plc.json, "dump", side_effect=OSError(errno.ELOOP, "Too many levels of symbolic links")):
            code, err = self.run_main([z, "--rules", rules, "--out", self.out])
        self.assertEqual(code, 2)
        self.assertIn("Give --out a folder you can write to", err)
        self.assertNotIn("disk has room", err)

    def test_newest_zip_takes_the_env_flag_by_keyword_only(self):
        with self.assertRaises(TypeError):
            plc.newest_zip(self.dir, "--logs-dir")

    def test_a_full_disk_still_says_to_check_the_room(self):
        import errno
        from unittest import mock
        z, rules = self.zip_and_rules()
        with mock.patch.object(plc.json, "dump", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            code, err = self.run_main([z, "--rules", rules, "--out", self.out])
        self.assertEqual(code, 2)
        self.assertIn("disk has room", err)


class TestReviewRound7042(Base):
    """0.4.2 /code-review round 7: Ctrl+C right after a report file is opened removes it and closes it, a refused
    name on Windows is retried, the name search is bounded, and a real dangling link counts as a taken name."""

    run_main = TestBadInput042.run_main
    zip_and_rules = TestBadInput042.zip_and_rules

    def test_ctrl_c_before_the_first_write_removes_and_closes_the_file(self):
        # Round 6 code set its "half-written" marker inside the with block, so an interrupt on entering it left the
        # empty file behind with its handle open.
        import builtins
        from unittest import mock
        z, rules = self.zip_and_rules()
        real_open = builtins.open
        handles = []

        class Interrupting:
            def __init__(self, f):
                self._f = f
                self.name = f.name

            @property
            def closed(self):
                return self._f.closed

            def close(self):
                self._f.close()

            def __enter__(self):
                raise KeyboardInterrupt()

            def __exit__(self, *exc):
                self._f.close()

        def fake(path, *a, **k):
            f = real_open(path, *a, **k)
            if str(path).endswith(".txt") and "logcheck-" in str(path):
                handles.append(f)
                return Interrupting(f)
            return f
        with mock.patch("builtins.open", fake):
            with self.assertRaises(KeyboardInterrupt):
                self.run_main([z, "--rules", rules, "--out", self.out])
        self.assertEqual(len(handles), 1)
        self.assertTrue(handles[0].closed, "the report file was left open")
        self.assertEqual(os.listdir(self.out), [])

    def refusing_open(self, times):
        """An open() whose first `times` exclusive report opens raise PermissionError, as a delete-pending name does."""
        import builtins
        import errno
        real_open = builtins.open
        refused = []

        def fake(path, *a, **k):
            mode = k.get("mode", a[0] if a else "r")
            if str(path).endswith(".txt") and mode == "x" and len(refused) < times:
                refused.append(path)
                raise PermissionError(errno.EACCES, "Permission denied")
            return real_open(path, *a, **k)
        return fake, refused

    def test_a_name_refused_once_is_retried_under_the_next_name(self):
        from unittest import mock
        z, rules = self.zip_and_rules()
        fake, refused = self.refusing_open(1)
        with mock.patch("builtins.open", fake):
            code, err = self.run_main([z, "--rules", rules, "--out", self.out])
        self.assertIn(code, (0, 1), err)
        self.assertEqual(len(refused), 1)
        names = sorted(os.listdir(self.out))
        self.assertEqual(len(names), 2, names)
        self.assertTrue(names[0].endswith("-2.json") and names[1].endswith("-2.txt"), names)

    def test_a_folder_that_refuses_every_name_still_gets_the_path_text(self):
        from unittest import mock
        z, rules = self.zip_and_rules()
        fake, refused = self.refusing_open(1000)
        with mock.patch("builtins.open", fake):
            code, err = self.run_main([z, "--rules", rules, "--out", self.out])
        self.assertEqual(code, 2)
        self.assertEqual(len(refused), plc._REFUSED_TRIES)
        self.assertIn("Give --out a folder you can write to", err)
        self.assertEqual(os.listdir(self.out), [])

    def test_the_name_search_stops_after_its_cap(self):
        # Round 6 code looped for as long as names looked taken. Here 150 names look taken: the old code wrote the
        # report under a far name (exit 0); now the run stops at the cap of 100 with exit 2 and says what to do.
        from unittest import mock
        z, rules = self.zip_and_rules()
        real_lexists = os.path.lexists
        calls = []

        def fake_lexists(p):
            if "logcheck-" in str(p) and len(calls) < 150:
                calls.append(p)
                return True
            return real_lexists(p)
        with mock.patch("os.path.lexists", fake_lexists):
            code, err = self.run_main([z, "--rules", rules, "--out", self.out])
        self.assertEqual(code, 2)
        self.assertEqual(len(calls), plc._NAME_TRIES)
        self.assertIn("report names for this run", err)
        self.assertIn("are all taken. Move old reports out of the folder, or give --out another folder.", err)
        self.assertEqual(os.listdir(self.out), [])

    def test_a_real_dangling_link_on_the_report_name_is_skipped_and_left_alone(self):
        import datetime
        import types
        from unittest import mock
        z, rules = self.zip_and_rules()
        os.makedirs(self.out, exist_ok=True)

        class Fixed(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 11, 22, 1, 2, 3)
        pkg = plc.Package(z)
        try:
            stamp = pkg.stamp()
        finally:
            pkg.close()
        link = os.path.join(self.out, f"logcheck-{stamp}-run20261122-010203.txt")
        target = os.path.join(self.dir, "nowhere.txt")
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("this system can't make symbolic links")
        with mock.patch.object(plc, "datetime", types.SimpleNamespace(datetime=Fixed)):
            code, err = self.run_main([z, "--rules", rules, "--out", self.out])
        self.assertIn(code, (0, 1), err)
        self.assertTrue(os.path.islink(link))
        self.assertFalse(os.path.exists(target), "the run wrote through the dangling link")
        self.assertTrue(os.path.isfile(link[:-len(".txt")] + "-2.txt"))
        self.assertTrue(os.path.isfile(link[:-len(".txt")] + "-2.json"))


class TestDocsVersion(unittest.TestCase):
    """0.4.2: the version the README and AGENTS.md name must be VERSION (CHANGELOG.md is history, exempt)."""

    PATTERNS = (
        r"papyrus-log-check-(\d+\.\d+\.\d+)\.zip",                 # the install steps
        r"papyrus-log-check (\d+\.\d+\.\d+) by ",                   # the banner in the sample outputs
        r"run once on\s+papyrus-log-check (\d+\.\d+\.\d+)",         # AGENTS.md line 4 (may wrap)
    )

    def versions(self, name):
        import re
        with open(os.path.join(TOOL_DIR, name), encoding="utf-8") as f:
            text = f.read()
        return [(p, v) for p in self.PATTERNS for v in re.findall(p, text)]

    def test_docs_name_the_current_version(self):
        for name in ("README.md", "AGENTS.md"):
            found = self.versions(name)
            self.assertTrue(found, name + " names no version at all: the patterns no longer match")
            for pattern, v in found:
                self.assertEqual(v, plc.VERSION, "%s names %s (pattern %s), but VERSION is %s: rerun the "
                                 "sample and update the text" % (name, v, pattern, plc.VERSION))

    def test_each_pattern_matches_somewhere(self):
        """A pattern that matches nothing guards nothing."""
        for p in self.PATTERNS:
            hits = [v for n in ("README.md", "AGENTS.md") for q, v in self.versions(n) if q == p]
            self.assertTrue(hits, "pattern matches neither README.md nor AGENTS.md: " + p)


if __name__ == "__main__":
    unittest.main()
