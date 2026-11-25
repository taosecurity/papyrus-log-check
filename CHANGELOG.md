# Changelog

## 0.4.3 (2026-11-25)

### What's new

The release zip now holds the quest-stage example, `examples/example-quest.log` and `examples/example-quest.logrules.json`, which the README's "Check a quest's stages" section describes. They were in the repository but left out of the zip, because the build listed example files by hand. The build now takes the whole `examples` folder, and a test checks that every example file is in the zip. There are no changes to how the tool checks logs.

### Example

Unpack the zip and run the quest example from the unpacked folder:

    > python papyrus_log_check.py examples\example-quest.log --rules examples\example-quest.logrules.json
    papyrus-log-check 0.4.3 by Richard Bejtlich - MIT - https://github.com/taosecurity/papyrus-log-check
    example-quest.log
      PASS       Tidewater Errand 1.0.0
    Report: out\logcheck-....txt
    JSON:   out\logcheck-....json

## 0.4.2 (2026-11-22)

### What's new

This is a fix release with no new features. The install text and sample outputs in the README and AGENTS.md now name the current version, and a test keeps them from going stale again. Bad folders, output paths, rule files and damaged zips now get an error that says what to do, and a report that can't be written gets a clear error with exit code 2. A mod name that your console can't show no longer stops the run.

### Example

`--root` on a folder that doesn't exist used to end with a raw Windows error. Now it names the option and the fix, and still exits with code 2:

    > python papyrus_log_check.py examples\Papyrus.0.log --root D:\nonexistent-folder
    papyrus-log-check 0.4.2 by Richard Bejtlich - MIT - https://github.com/taosecurity/papyrus-log-check
    papyrus-log-check: --root D:\nonexistent-folder is not a folder. Give --root the folder that holds your project folders, or use --rules FILE.

### Fixes

- The README and AGENTS.md install steps, the banner in the README's sample outputs and the "run once on" line in AGENTS.md named 0.4.0. They now name the current version.
- A new test fails when any of those version strings differs from the tool's version again. CHANGELOG.md is history and is exempt.
- `--root`, `--logs-dir` and `--out` on a path that isn't a usable folder, or on a folder that can't be read, now give one error that names the option and the fix, instead of a raw Windows error. The exit code is 2.
- `--mods` with project names and a `--root` that doesn't exist now says that `--root` is wrong. Before, it said the mod's rule file was missing.
- A folder that comes from the environment variable `PAPYRUS_LOG_CHECK_LOGS` is named as such in its error, not blamed on `--logs-dir`.
- A rule file that isn't UTF-8 (for example a UTF-16 file saved by Notepad) now gets an error that says so and tells you to save it as UTF-8. Before, the error blamed commas.
- A zip whose entries are damaged, cut short, encrypted or made with a compression method Python can't read (such as Deflate64 from Windows Explorer) now exits with code 2 and an error that names the entry and says to make the zip again. This covers Deflate, LZMA and BZIP2 entries, and a zip whose drive went away while it was read. Before, it ended in a Python traceback with exit code 1, and a damaged manifest.json was silently ignored.
- A log file in an input folder that can't be read (held by the game, or a OneDrive file that isn't on this device) now gets an error that names it and says to close the program that holds it or to copy the logs. A log file that went away during the run (the game renames its logs when it starts) says to run the check again, and a subfolder that can't be listed is named with the fix instead of being skipped without a word (a Papyrus `User` log folder is still skipped, since its logs are never checked). Before, these got a raw Windows error or were skipped.
- The log zip is now closed when a run ends, including a run that stops on an error, so the file isn't left locked on Windows.
- A character that the console's code page can't show no longer stops the run. On stdout and stderr it prints as a Python backslash escape (`\xNN`, `\uXXXX` or `\UXXXXXXXX`), so the `Report:` and `JSON:` lines and every error still name their file exactly (run `python -X utf8 ...` to get every valid character as it is; a name that isn't valid Unicode still prints as an escape). This also covers the usage text for a bad option. The report and the JSON keep the real name, and the console's old setting comes back when the run ends.
- A name that isn't valid Unicode (such as a non-UTF-8 file name on Linux) is written to the report and to the `--log` file as an escape instead of stopping the run, and a log folder with such a name can be checked, and an `--out` folder with such a name can be written to.
- Two files in a folder or zip whose names differ only in upper and lower case (possible on Linux) no longer leave one of them out without a word. When the tool reads that name, it stops with exit code 2 and names both files, with the advice to keep only one.
- The report files are now created exclusively, so a run never overwrites another run's report. A second run in the same second still gets `-2` added, as in 0.4.1, and a dangling link now counts as a taken name.
- A report that can't be written now stops with exit code 2 and one error that names the folder or file and the fix. In 0.4.1 every write error blamed the `--out` path. The advice now follows the cause:
  - a full disk or an I/O error says to check that the disk has room and is still connected;
  - a path or permission problem says to give `--out` a folder you can write to;
  - a `.json` name that is refused or busy right after its `.txt` was written says another program may be holding that name;
  - a report file of the same name made by another run or program meanwhile is named, with the advice to run again or give `--out` another folder;
  - an error that isn't a file error (a bug) says to rerun with `--log FILE` (a `.txt` file outside the input folder) and attach that log to a bug report, or names the run's own `--log` file;
  - any other error says to check the folder and the disk.
- A failed report write retries nothing and removes nothing. When the run has already created report files, the error names them and says to delete them, because that report is incomplete.
- The README and AGENTS.md now say that a failed write exits 2 and that a script should trust a report pair only from a run that exited 0 or 1.

### Internal

- Two docstrings and a comment still described the old fallback to stray `.dll` files. They now say that the files count only when the manifest has no listing at all.
- A new test checks the log line that notes a manifest listing without the key.
- The CI workflow moved off the deprecated Node.js 20 actions. It now uses the current `checkout`, `setup-python`, `upload-artifact` and `download-artifact` versions, pinned by commit.

## 0.4.1 (2026-11-22)

### What's new

This is a fix release for the four things left over from the 0.4.0 review. A NOT LOADED mod now says what was checked, a quiet mod whose explain rules matched says how many lines they found, rule-file mistakes with `min` and `always` get one clear error, and the game's official masters count as loaded without a plugins.txt line. The JSON only gains two keys, `not_loaded_reason` and `explain_found`.

### Example

The new `examples/example-quiet.logrules.json` is for a made-up mod that never logged in the example log, while its explain rule matched two lines:

    > python papyrus_log_check.py examples\Papyrus.0.log --rules examples\example-quiet.logrules.json
    papyrus-log-check 0.4.1 by Richard Bejtlich - MIT - https://github.com/taosecurity/papyrus-log-check
    Papyrus.0.log
      NOT SEEN (2 found) Example Quiet 0.2.0
    Report: ...\out\logcheck-20261109-095824-run20261122-191459.txt
    JSON:   ...\out\logcheck-20261109-095824-run20261122-191459.json

Before 0.4.1 the line said only `NOT SEEN`, so the two found lines were easy to miss.

### Fixes

- A NOT LOADED mod's report now says what was checked. Before, it always said the plugin wasn't active in plugins.txt, even for a rule file that names only an SFSE plugin DLL. Now it names plugins.txt, the input's list of SFSE plugin DLLs, or both.
- The list of rule files that weren't checked (with `--root`) gives the same sentence under each one.
- The JSON has the sentence in a new `not_loaded_reason` key, in `mods` and in `not_loaded`. No other key changed.
- A mod that never logged but whose explain rules matched now shows `NOT SEEN (N found)` on the screen and in the report's summary, so the found lines aren't missed. N is the number of matches the explain rules found (a line two rules match counts twice).
- The JSON status stays `NOT SEEN`. Each checked mod gets a new `explain_found` key with the number. The exit code doesn't change.
- A bad `min` on an explain rule now gives one clear error ("only expect rules use it") instead of a type error first and that error after the fix.
- An explain rule may now have `"min": 1` or `"always": false`. They say what an explain rule does anyway, so they change nothing.
- A forbid rule with `min` or `always` is now refused with an error that names the file, the rule and the fix. Before, both were accepted and ignored.
- A rule file whose only plugins are official masters now counts as loaded, like `Starfield.esm` before. This covers the DLC masters, the `SFBGS*.esm` updates and `BlueprintShips-<official>.esm`. The game loads them without a plugins.txt line, so before, such a file was always NOT LOADED.
- When a collector manifest lists the Data folder's plugins, an official master missing from that list makes the file NOT LOADED, and the report says so.
- An empty DLL or Data plugin list in a collector manifest whose game folder wasn't found (an empty `gamePath`) now counts as no list. Before, every rule file that names a DLL was NOT LOADED then. A Data plugin list without `Starfield.esm` always counts as no list. A listing of the wrong shape, or one missing its DLL list, now counts as no list too (it no longer falls back to stray .dll files, and a bad DLL list no longer drops a good Data plugin list).
- A manifest list may hold plain names as well as `{"name": ...}` entries, and a path is cut to its file name. A list with no usable name is ignored.

### Changes

- Rule files: a forbid rule with `min` or `always` loaded in 0.4.0 but is refused now (see Fixes). Remove the field to load the file again.
- `examples/example-quiet.logrules.json` is a new made-up rule file that shows the `NOT SEEN (N found)` line. The README's Results section and AGENTS.md use it, and a test checks its output.

### Download

Download `papyrus-log-check-0.4.1.zip` below, unpack it and follow the Install steps in the README. It needs Python 3.9 or newer and nothing else.

## 0.4.0 (2026-11-20)

### What's new

papyrus-log-check now comes with a starter rule pack. Three ready rule files in the new `rules` folder explain, in plain words, the error and warning lines that Starfield's Papyrus engine writes, so you can get something useful out of any Papyrus log before you write a rule file of your own.

The pack uses a new kind of rule, `explain`. A match shows as FOUND, with its explanation and the script that raised the error, and it never fails a run. Runs with `--root` now also say which rule files they skipped because the mod's plugin isn't active.

### Example

    > python papyrus_log_check.py examples\starter-pack-sample.log --rules rules\papyrus-runtime-errors.logrules.json --rules rules\papyrus-scripts-and-properties.logrules.json --rules rules\papyrus-saves-and-load.logrules.json
    papyrus-log-check 0.4.0 by Richard Bejtlich - MIT - https://github.com/taosecurity/papyrus-log-check
    starter-pack-sample.log
      FOUND      Papyrus runtime errors 1.0.0
      FOUND      Papyrus saves and engine load 1.0.0
      FOUND      Papyrus scripts and properties 1.0.0
      FLAG       suspended stacks: 1 line(s), first starter-pack-sample.log:62
    Report: ...\out\logcheck-20261120-220344-run20261120-220538.txt
    JSON:   ...\out\logcheck-20261120-220344-run20261120-220538.json

The report explains each line it found, for example:

       FOUND     explain none-object: 1 found
                 (A script called a function on a variable or property that was empty (None). The usual cause is a property that was never filled in the Creation Kit, or an object that was deleted or not loaded yet. The script skipped that call and went on.)
                 starter-pack-sample.log:24  [21:01:10] error: Cannot call GetReference() on a None object, aborting function call
                    at [EXB_BeaconQuest (02000801)].EXB_BeaconScript.PlaceBeacon() - "EXB_BeaconScript.psc" Line 41

### Changes

- `rules/papyrus-runtime-errors.logrules.json` explains 10 runtime errors, such as a call on a None object, array mistakes, dividing by zero and "Stack too deep".
- `rules/papyrus-scripts-and-properties.logrules.json` explains 10 messages about missing script files, scripts attached to the wrong kind of object, missing native functions, and properties that a script and its plugin disagree about.
- `rules/papyrus-saves-and-load.logrules.json` explains 6 warnings about saves made with other script versions, and the warning that the script engine was overloaded.
- `examples/starter-pack-sample.log` is a made-up log with a line for every pack rule. The tests check that each rule matches its own line and no other.
- Rule files can have `explain` rules. A match is FOUND, which is shown with the rule's `means` and never fails the mod or changes the exit code. A mod whose explain rules match and whose other rules pass is FOUND. A mod that never logged stays NOT SEEN, with its FOUND lines still in the report, unless its rule file has only explain rules. Explain rules can't have `min` or `always`; the tool says which file and rule to fix.
- Each line an explain rule finds names the script behind the error (the first script line of the stack that follows it), in the report and in the JSON (`at`).
- `Starfield.esm` always counts as active, because the game always loads it and never lists it in plugins.txt. A rule file about the game's own messages names it as its only plugin. In a rule file that also names other plugins or DLLs, it doesn't count, so the mod is checked only when one of those is loaded.
- With `--root`, each rule file whose plugin isn't active now gets a `NOT LOADED` line in the summary and in a short list at the end of the report, and the JSON lists them in `not_loaded`. Before, they were left out without a word, so a run that checked nothing looked empty.
- AGENTS.md says that the `--set-version` example prints FAIL when the log shows another version, and what a `--root` run prints for mods that aren't loaded.

### Download

Download `papyrus-log-check-0.4.0.zip` below, unpack it and follow the Install steps in the README. It needs Python 3.9 or newer and nothing else.

## 0.3.2 (2026-11-20)

### What's new

This is a small fix release. The `--version` text now spells "license" the American way and prints the same two lines however it is given, and the README agrees on the Python version you need. Nothing about how the tool checks logs has changed.

### Example

    > python papyrus_log_check.py --version
    papyrus-log-check 0.3.2 by Richard Bejtlich - MIT - https://github.com/taosecurity/papyrus-log-check
    Free software under the MIT license. It comes with no warranty.

### Fixes

- `--version` used the British spelling of "license". It now prints "MIT license", and a test checks the wording.
- `--version` now prints the same two lines however it is given: with other options (`--version --verbose`) or shortened (`--vers`). Before, those printed a shorter, wrapped byline without the license sentence. As with most command-line tools, other options given with `--version` are ignored. `--help` lists it too.
- The script's opening comment uses the same spelling.
- The README's install steps now say Python 3.9 or newer, as the rest of the documentation does.

### Download

Download `papyrus-log-check-0.3.2.zip` below, unpack it and follow the Install steps in the README. It needs Python 3.9 or newer and nothing else.

## 0.3.1 (2026-11-16)

### What's new

This release is about getting started. The README has a new section, "Add logging to a Creation Kit mod", that shows where to put `Debug.Trace` lines in a script so papyrus-log-check has something to check. It also comes with a starter rule file that fits the README's example script, so you can copy it and change it for your own mod.

### Example

Check that the starter rule file loads by running it on the example log. The log comes from another mod, so a good rule file shows NOT SEEN and exits with code 0:

    > python papyrus_log_check.py examples\Papyrus.0.log --rules examples\starter-mymod.logrules.json
    papyrus-log-check 0.3.1 by Richard Bejtlich - MIT - https://github.com/taosecurity/papyrus-log-check
    Papyrus.0.log
      NOT SEEN   My Mod 0.1.0
    Report: ...\out\logcheck-20261109-095824-run20261120-152609-2.txt
    JSON:   ...\out\logcheck-20261109-095824-run20261120-152609-2.json

### Changes

- The README's new section "Add logging to a Creation Kit mod" covers where to put `Debug.Trace` lines in a script, keeping one prefix through a small `Log` function, and never compiling with `-release`.
- `examples/starter-mymod.logrules.json` is a starter rule file for the README's example script. A test checks that it loads and fits the script's lines.
- AGENTS.md says how to start a rule file from the starter.

### Download

Download `papyrus-log-check-0.3.1.zip` below, unpack it and follow the Install steps in the README. It needs Python 3.9 or newer and nothing else.

## 0.3.0 (2026-11-16)

These changes came from a code review and a security review.

- New `--verbose` and `--log FILE` options write a troubleshooting log of what was read, what was decided and why a run
  stopped. `--log` refuses a name that would overwrite an input.
- AGENTS.md gives step-by-step instructions for AI assistants, and it is also in the release zip.
- Text from logs, rule files and the manifest is shown with control characters as `\xNN`, so escape codes hidden
  in a shared log can't change the terminal.
- Rule files are checked field by field, and every pattern (`scripts` and `ignore` too) is checked up front: a
  mistake gives exit 2 with the file and the field named, not a Python error. A file that isn't valid JSON says so.
- With `--root`, a broken rule file for a mod that isn't loaded no longer stops the run; a file that can't be read
  at all is listed as SKIPPED.
- `--set-version` is applied once when the project folder and the mod name are the same, so the report keeps the
  rule file's version. Two different versions for one mod are an error.
- A mod whose expect rules pass on lines without its prefix is PASS, not NOT SEEN.
- A manifest.json with fields of an unexpected shape no longer crashes the run.
- Errors on a mod's `ignore` list are counted with the other scripts' errors instead of vanishing.
- A folder's SHA-256 also covers the extra log files the rule files name (`logs`).
- The tool says who made it and where it lives: one line at the start of each run (on stderr, so the summary is
  unchanged), the first line of the text report, `--version`, and `author`, `license` and `url` in the JSON report.
- The release zip is stored without compression and built from the committed files, so it is the same on any
  system; CI checks that the Windows and Linux builds match.

## 0.2.1 (2026-11-09)

- A PRIVACY.md file says what the tool reads and writes, and that it makes no network connections. It is in the
  release zip.
- The release zip is now the same, byte for byte, whether it is built on Windows or Linux, so anyone can rebuild it
  and compare the checksum.

## 0.2.0 (2026-11-09)

This is the first public release.

- It reads a single Papyrus log file (any name), a folder of `Papyrus.N.log` files, or a zip of them.
- `--rules FILE` gives rule files directly (repeat it, or give a comma list).
- `--logs-dir` picks the newest `.zip` of any name.
- For SFSE plugins without a DLL listing, `.dll` files in the input count as installed.
- A `manifest.json` without a `tool` field (one not written by a log collector) is ignored.
- The README has a Privacy section.
- `examples/` holds an example rule file and log for a made-up mod.
- Tests run on Windows and Linux in GitHub Actions, and tagged releases get a zip and a SHA-256 checksum.

## 0.1.0

This was a private version and was never released.
