# papyrus-log-check

papyrus-log-check checks Starfield Papyrus logs against rules you write for your mod. It says
PASS, FAIL or NOT SEEN for every rule. It also points out general trouble: Papyrus errors that
name your mod's scripts, crash logs and suspended stacks.

The tool is a reading aid for mod authors and testers, and its report is not a verdict. It only
reads: it never changes the logs or the rule files.

- It needs Python 3.9 or newer and uses only the standard library. There is nothing to install,
  because it is one script.
- It works on Windows and Linux (for example, on logs copied from a Steam Deck).
- It is released under the MIT licence.

This tool was built with [Claude Code](https://claude.com/claude-code).

## Quick start

Download the release zip, unpack it, and try the made-up example:

```
python papyrus_log_check.py examples\Papyrus.0.log --rules examples\example-beacon.logrules.json
```

It prints a one-line result per mod and writes a full report to `out\`:

```
Papyrus.0.log
  PASS       Example Beacon 1.0.0
Report: ...\out\logcheck-20261101-210500-run20261109-101500.txt
JSON:   ...\out\logcheck-20261101-210500-run20261109-101500.json
```

Then point it at your own log and your own rule file:

```
python papyrus_log_check.py "C:\Users\<you>\Documents\My Games\Starfield\Logs\Script\Papyrus.0.log" --rules MyMod.logrules.json
```

## Turn on Papyrus logging first

Starfield writes no Papyrus log until you ask it to. Add these lines to
`Documents\My Games\Starfield\StarfieldCustom.ini` (make the file if it isn't there):

```ini
[Papyrus]
bEnableLogging=1
bEnableTrace=1
bLoadDebugInformation=1
```

Start the game, play the part you want to check, and quit. The logs are in
`Documents\My Games\Starfield\Logs\Script\`: `Papyrus.0.log` is the newest session,
`Papyrus.1.log` is the one before, and so on.

Your mod's own lines come from `Debug.Trace` calls in its scripts. If you compile with the
`-release` flag, the compiler removes every `Debug` call, so nothing of yours reaches the log.

## What it can read

You can give it any of these three kinds of input:

| Input | What it reads |
|---|---|
| A log file (`Papyrus.0.log`, or any file in the same format, whatever its name) | It reads that one log. |
| A folder (for example `Logs\Script`) | It reads every `Papyrus.N.log` in the folder and its subfolders, oldest first. It skips logs in `User\` folders. |
| A zip | It reads the zip the same way as a folder. It reads the zip in memory and unpacks nothing. |

A folder or zip may also hold these files:

- **`plugins.txt`** is the game's plugin list, with `*` before each active plugin. When it is
  there, a mod whose plugin isn't active is shown as NOT LOADED and isn't checked. When it is
  missing, every rule file is checked.
- **Crash logs** (`Crashlog*.txt`, `crash-*.log`, or files in a `crashlogs` folder) are listed as
  FLAG lines.
- **An SFSE plugin's own log** is checked when a rule file names it in `logs`.

## Running it

```
python papyrus_log_check.py INPUT --rules FILE [--rules FILE ...]
python papyrus_log_check.py INPUT --root FOLDER [--mods A,B]
python papyrus_log_check.py --logs-dir FOLDER --rules FILE
```

| Option | What it does |
|---|---|
| `INPUT` | This is the log file, folder or zip to check (see above). |
| `--rules FILE` | This names a rule file to check against. Repeat it, or give a comma list, for several mods. |
| `--root FOLDER` | If you keep many mods as `<FOLDER>\<project>\testplan\logrules.json` (or one level deeper, `<FOLDER>\<group>\<project>\...`), this option finds all of their rule files. Without `--mods`, only mods whose plugin is active in `plugins.txt` are reported. The default is the current folder, and it is used only when no `--rules` is given. |
| `--mods A,B` | With `--root`, this checks only the project folders you name. |
| `--logs-dir FOLDER` | When no INPUT is given, this checks the newest `.zip` in the folder. "Newest" goes by the `yyyymmdd-hhmmss` stamp in the file name, or else by file time. The environment variable `PAPYRUS_LOG_CHECK_LOGS` does the same. |
| `--out FOLDER` | This sets where the reports go. The default is `out\` next to the script. |
| `--max-lines N` | This sets how many matching lines the text report shows per rule. The default is 5, and the JSON report keeps up to 50. |
| `--set-version MyMod=0.9.1` | This checks a mod as another version than its rule file says (give the mod name or project folder). It is for rechecking older logs, and you can repeat it. |

When a rule with `{version}` finds nothing, the report also shows the same line logged with any
other version. That usually means a different build was installed.

Each run writes two files, named after the input's time stamp and the time of the run, so
nothing is ever overwritten:

```
logcheck-20261101-210500-run20261109-101500.txt   plain-text report
logcheck-20261101-210500-run20261109-101500.json  the same data for other tools
```

The exit code tells scripts what happened:

- 0 means no rule failed.
- 1 means at least one rule failed.
- 2 means the arguments were wrong, a rule file was bad, or the input couldn't be read.

## Rule files

Each mod has one JSON rule file.
[`examples/example-beacon.logrules.json`](examples/example-beacon.logrules.json) is a complete
one for a made-up mod, and this one has the same shape:

```json
{
  "mod": "My Mod",
  "version": "1.2.0",
  "plugins": ["MyMod.esm"],
  "names": ["MyMod"],
  "prefix": "MYMOD:",
  "scripts": "^MYMOD_|\\bMYMOD_",
  "expect": [
    {"id": "setup", "re": "MYMOD: setup \\((new game|game loaded)\\), version {version}",
     "min": 1, "always": true,
     "show": "MYMOD: setup (new game / game loaded), version …",
     "means": "The mod writes this line at a new game and at every load."},
    {"id": "picked", "re": "MYMOD: picked target", "means": "The main feature ran."}
  ],
  "order": [["setup", "picked"]],
  "forbid": [
    {"id": "conflict", "re": "MYMOD: WARNING .* is also active", "means": "An older version is still enabled."}
  ],
  "ignore": [{"re": "Cannot call Delete\\(\\) on a None object", "why": "This error is harmless on cleanup."}]
}
```

| Field | What it means |
|---|---|
| `mod`, `version` | The report shows them. `{version}` in any regex is replaced by the version, so a wrong build shows up as a FAIL. |
| `plugins` | These are the mod's plugin files. If none of them is active in plugins.txt, the mod is NOT LOADED. |
| `dlls` | These are the DLL names of an SFSE plugin. Without a DLL listing, `.dll` files in the input count as installed. Give `plugins`, `dlls` or both. |
| `logs` | These are log file names to check instead of the Papyrus logs, for example `["my_sfse_plugin.log"]`. |
| `names` | These are words to look for in the input's name. A match shows as "named in note" in the summary. |
| `prefix` | This required regex matches the mod's own log lines. If nothing matches anywhere, the mod never logged. |
| `scripts` | This regex matches the mod's script names. Papyrus errors whose message or stack matches it count as the mod's errors. |
| `expect` | These are lines that should appear. Each has an `id`, a regex `re`, an optional `min` (default 1) and an optional `always` (the line must appear whenever the mod logged at all). |
| `order` | Each entry lists `expect` ids whose first lines must appear in that order. |
| `forbid` | These are lines that must not appear. Each has an `id` and a regex `re`. |
| `ignore` | These regexes (or `{"re", "why"}` pairs) match errors of the mod's scripts that are known and harmless. |
| `show`, `means` | These hold free text for people. The report prints `means` when a rule isn't PASS. |

Regexes use Python syntax and match anywhere in a log line. Double the backslashes in JSON.
Papyrus sometimes changes the case of a string it has seen before ("Started" can come out as
"started"), so use `(?i:...)` around such words.

## Results

Each mod gets one of four results:

- **NOT LOADED** means none of its plugins is active in plugins.txt. Nothing else is checked.
- **NOT SEEN** means no line matches `prefix`. Usually the mod's features weren't tested, or the
  debug lines don't reach the log.
- **FAIL** means at least one rule failed.
- **PASS** means the mod logged and no rule failed. Some rules may still be NOT SEEN.

Each rule gets its own result:

- An **expect** rule passes when its line is found at least `min` times. It fails when an
  `always` line is missing, or when the line is found fewer than `min` times. It is NOT SEEN
  when the line isn't found at all, which usually means the feature wasn't tested.
- An **order** rule passes when all its lines are found in order, and fails when they are found
  out of order. It is NOT SEEN when some of them aren't found.
- A **forbid** rule fails when its line is found. It passes when the line isn't found and the mod
  logged, and it is NOT SEEN when the mod never logged.
- The **script errors** check fails when an `error:` line names the mod's scripts, and passes
  when none does.

Warnings that name the mod's scripts are listed, but they don't fail the mod. Errors from other
scripts (the base game, other mods) are only counted.

FLAG lines at the end of the report aren't tied to one mod. They report crash logs in the input
and suspended-stack lines, which mean the Papyrus engine was falling behind.

## Privacy

It runs offline and only reads the files you give it. It writes nothing but its two report
files. It never looks up your user name, computer name or anything else about your PC.

Reports quote lines from your logs (and, if your log zip has a collector's manifest, its user
and computer names), so read a report before you post it.

## Tests

```
python -I tests/test_papyrus_log_check.py
```

The tests build small made-up logs, folders and zips, so no game files are needed. The GitHub
workflow runs them on Windows and Linux.

## Licence

The tool is released under the MIT licence; see [LICENSE](LICENSE). Changes are listed in
[CHANGELOG.md](CHANGELOG.md).
