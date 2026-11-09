# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Richard Bejtlich
"""Tests for papyrus_log_check on small made-up logs, folders and zips (no game files needed)."""

import json
import os
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
