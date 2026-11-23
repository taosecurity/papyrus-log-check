# AGENTS.md: papyrus-log-check for AI assistants

Plain steps for an AI assistant helping someone use papyrus-log-check. Every command here was run once on
papyrus-log-check 0.4.0 before release. The [README](README.md) has the full description.

## 1. What it is for

papyrus-log-check reads Starfield Papyrus logs (`Papyrus.0.log` and older ones, a folder of them, or a zip) and
checks them against a rule file the mod author writes (`*.logrules.json`). For each rule it says PASS, FAIL or
NOT SEEN, and it points out Papyrus errors that name the mod's scripts, crash logs and suspended stacks. Its
starter rule pack (`rules\`) explains the game's own Papyrus error and warning lines on any log; its matches show
as FOUND and never fail a run.

Use it when a mod author or tester wants to know whether a test session logged what the mod should log. Don't use
it to judge whether a mod is "good": its report is a reading aid, not a verdict.

## 2. Prerequisites

- Python 3.9 or newer (tested on 3.9, 3.10 and 3.13). Standard library only: nothing to install.
- Windows or Linux.
- Papyrus logging turned on in the game (README section "Turn on Papyrus logging first").

## 3. Install

Download `papyrus-log-check-0.4.0.zip` from https://github.com/taosecurity/papyrus-log-check/releases and check it
against the `.sha256` file:

    certutil -hashfile papyrus-log-check-0.4.0.zip SHA256

Unpack it anywhere. On Linux, `sha256sum -c papyrus-log-check-0.4.0.zip.sha256` checks it.

## 4. Prove the install works

From the unpacked folder:

    python -I papyrus_log_check.py examples/Papyrus.0.log --rules examples/example-beacon.logrules.json --out out

It prints `PASS       Example Beacon 1.0.0` and the two report paths, and exits with code 0.

## 5. Common tasks

- Check one log against one rule file:

      python -I papyrus_log_check.py "<path>\Papyrus.0.log" --rules MyMod.logrules.json

- Check a log zip or a folder of logs (it finds Papyrus.N.log, plugins.txt and crash logs inside):

      python -I papyrus_log_check.py logs.zip --rules MyMod.logrules.json

- Explain the engine's error and warning lines in any log (no rule file of your own needed). Run it from the
  unpacked tool folder, where the `rules` folder is, or put the tool folder's path in front of each `rules/...`
  path. The pack's three files can be given together with the mod's own rule file:

      python -I papyrus_log_check.py "<path>\Papyrus.0.log" --rules rules/papyrus-runtime-errors.logrules.json --rules rules/papyrus-scripts-and-properties.logrules.json --rules rules/papyrus-saves-and-load.logrules.json

  On the shipped sample (`examples/starter-pack-sample.log` in place of the path) it prints `FOUND` for all three
  (`Papyrus runtime errors 1.0.0`, `Papyrus saves and engine load 1.0.0`, `Papyrus scripts and properties 1.0.0`)
  and a `FLAG suspended stacks` line, and exits with code 0. The base game writes many of these lines too: the
  report's `at ...` line under each error names the script that raised it, so look there before blaming a mod.

- Check every mod kept as `<root>\<project>\testplan\logrules.json` whose plugin is active in the input's plugins.txt:

      python -I papyrus_log_check.py logs.zip --root C:\Modding\Projects

  Each rule file found whose plugin isn't active (inactive or not in plugins.txt) is not checked and gets one
  `NOT LOADED <mod> <version>` line. A run where every line says NOT LOADED checked nothing, and exits with code 0.
  A rule file whose only plugins are official masters (Starfield.esm, the DLC, SFBGS*.esm,
  BlueprintShips-<official>.esm) counts as loaded without a plugins.txt line; only a collector manifest's
  `listing.dataPlugins` that lacks the master makes it NOT LOADED (Starfield.esm always counts). A
  `dataPlugins` list without Starfield.esm, an empty list in a manifest whose `gamePath` is empty, a `listing`
  that isn't an object, a `dataPlugins` or `sfsePluginDlls` value that is missing or isn't a list, counts as no
  list (stray .dll files in the input never stand in for it).

- Recheck an older log as an older version of the mod:

      python -I papyrus_log_check.py old.zip --rules MyMod.logrules.json --set-version "My Mod=0.9.1"

  Expect `FAIL` (exit code 1) when the log was written by yet another version: a rule with `{version}` (such as
  the start line) then finds nothing, and the report shows the line with the version the log has. For example,
  `examples/Papyrus.0.log --rules examples/example-beacon.logrules.json --set-version "Example Beacon=0.9.1"`
  prints `FAIL       Example Beacon 0.9.1`, because that log says version 1.0.0.

- Start a rule file for a mod that doesn't log yet: follow the README section "Add logging to a Creation Kit mod"
  (one prefix, a `Log` helper, never `-release`), then copy `examples/starter-mymod.logrules.json` and change
  `mod`, `version`, `plugins`, `prefix` and the patterns. Check that the copy loads (exit 2 names a bad field):

      python -I papyrus_log_check.py examples/Papyrus.0.log --rules MyMod.logrules.json

  The example log is from another mod, so a good copy shows `NOT SEEN` with exit code 0.
  `examples/Papyrus.0.log --rules examples/example-quiet.logrules.json` shows the case where such a mod's explain
  rules still matched: it prints `NOT SEEN (2 found) Example Quiet 0.2.0` and exits with code 0.
  `min` and `always` belong to expect rules only: on a forbid rule either one is a bad field (exit 2), and on an
  explain rule only `"min": 1` and `"always": false` are accepted (they change nothing).

- Troubleshoot a run: add `--verbose` (log on stderr) or `--log papyrus-log-check.log.txt` (log to a file).

## 6. Inputs, outputs, exit codes, log

- **Input:** a Papyrus log file, a folder holding Papyrus.N.log files, or a zip of them (read in memory, never
  unpacked). Rule files: `--rules FILE` (repeatable) or `--root FOLDER`.
- **Output:** two files in `--out` (default `out\` next to the script): `logcheck-<input stamp>-run<run stamp>.txt`
  and `.json`. They are never overwritten. stdout gets one line per mod (`PASS`, `FAIL`, `FOUND`, `NOT SEEN`,
  `NOT LOADED`), any `SKIPPED` rule files and `FLAG` lines, then the two report paths. stderr gets the byline.
  A mod that never logged but whose explain rules matched shows `NOT SEEN (N found)` there and in the report's
  summary (N = the matches its explain rules found; a line two rules match counts twice); its JSON `status` stays `NOT SEEN`, and every checked mod has
  the number in `explain_found`.
  The JSON lists checked mods in `mods` and, with `--root`, the unchecked ones in `not_loaded`. Each NOT LOADED
  entry (in either list) has `not_loaded_reason`, a sentence that names what was checked (plugins.txt, the SFSE
  plugin DLL list, or both).
- **Exit codes:** 0 = no rule failed (FOUND counts as no failure); 1 = at least one FAIL; 2 = bad arguments, a bad
  rule file (the message names the file and the field) or an input that couldn't be read.
- **Log:** only when asked: `--verbose` to stderr, `--log FILE` to that file (overwritten each run; a name that
  would overwrite an input is refused).

## 7. Limits

- It never changes the logs, the rule files or the game. It writes only its two reports (and the log you ask for).
- It makes no network connections and uploads nothing.
- Reports quote log lines, and a log collector's manifest may add a user and computer name: read a report before
  posting it (PRIVACY.md).
- NOT SEEN usually means a feature wasn't tested, not that it's broken.
- It can only check what the mod logs. A mod without `Debug.Trace` lines gives NOT SEEN for everything.
- The starter pack explains messages; it doesn't decide whose fault they are. A FOUND line from the base game's
  own scripts is normal in every session.
