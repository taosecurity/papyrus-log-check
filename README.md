# papyrus-log-check

Checks Starfield Papyrus logs against rules you write for your mod, and says PASS, FAIL or NOT
SEEN for every rule. It also points out general trouble: Papyrus errors that name your mod's
scripts, crash logs and suspended stacks.

It's a reading aid for mod authors and testers, not a verdict. It only reads: it never changes
the logs or the rule files.

- Python 3.9 or newer, standard library only. Nothing to install: it's one script.
- Works on Windows and Linux (for example, logs copied from a Steam Deck).
- MIT licence.

Built with [Claude Code](https://claude.com/claude-code).

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
`Papyrus.1.log` the one before, and so on.

Your mod's own lines come from `Debug.Trace` calls in its scripts. If you compile with the
`-release` flag, the compiler removes every `Debug` call, so nothing of yours reaches the log.

## What it can read

| Input | What is used |
|---|---|
| a log file (`Papyrus.0.log`, or any file in the same format, whatever its name) | that one log |
| a folder (for example `Logs\Script`) | every `Papyrus.N.log` in it and its subfolders, oldest first; logs in `User\` folders are skipped |
| a zip | the same as a folder, read in memory; nothing is unpacked |

A folder or zip may also hold:

- `plugins.txt` (the game's list, with `*` before each active plugin): a mod whose plugin isn't
  active is shown as NOT LOADED and not checked. Without it, every rule file is checked.
- crash logs (`Crashlog*.txt`, `crash-*.log`, or files in a `crashlogs` folder): listed as FLAG lines.
- an SFSE plugin's own log, for rule files that name it in `logs`.

## Running it

```
python papyrus_log_check.py INPUT --rules FILE [--rules FILE ...]
python papyrus_log_check.py INPUT --root FOLDER [--mods A,B]
python papyrus_log_check.py --logs-dir FOLDER --rules FILE
```

| Option | Meaning |
|---|---|
| `INPUT` | a log file, a folder or a zip (see above) |
| `--rules FILE` | a rule file to check against. Repeat it, or give a comma list, for several mods. |
| `--root FOLDER` | if you keep many mods as `<FOLDER>\<project>\testplan\logrules.json` (or one level deeper, `<FOLDER>\<group>\<project>\...`), it finds all of them. Without `--mods`, only mods whose plugin is active in `plugins.txt` are reported. Default: the current folder, used only when no `--rules` is given. |
| `--mods A,B` | with `--root`: only these project folders |
| `--logs-dir FOLDER` | no INPUT given: check the newest `.zip` in this folder (by the `yyyymmdd-hhmmss` stamp in its name, else by file time). The environment variable `PAPYRUS_LOG_CHECK_LOGS` does the same. |
| `--out FOLDER` | where the reports go (default `out\` next to the script) |
| `--max-lines N` | matching lines shown per rule in the text report (default 5; the JSON keeps up to 50) |
| `--set-version MyMod=0.9.1` | check a mod as another version than its rule file says (by mod name or project folder), for rechecking older logs. Can be repeated. |

When a rule with `{version}` finds nothing, the report also shows the same line logged with any
other version, which usually means a different build was installed.

Each run writes two files, named after the input's time stamp and the time of the run, so
nothing is ever overwritten:

```
logcheck-20261101-210500-run20261109-101500.txt   plain-text report
logcheck-20261101-210500-run20261109-101500.json  the same data for other tools
```

Exit code: 0 = no FAIL, 1 = at least one FAIL, 2 = bad arguments, a bad rule file, or input it
can't read.

## Rule files

One JSON file per mod. [`examples/example-beacon.logrules.json`](examples/example-beacon.logrules.json)
is a complete one for a made-up mod; this is the same shape:

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
     "means": "Written at a new game and every load."},
    {"id": "picked", "re": "MYMOD: picked target", "means": "The main feature ran."}
  ],
  "order": [["setup", "picked"]],
  "forbid": [
    {"id": "conflict", "re": "MYMOD: WARNING .* is also active", "means": "An older version is still enabled."}
  ],
  "ignore": [{"re": "Cannot call Delete\\(\\) on a None object", "why": "harmless on cleanup"}]
}
```

| Field | Meaning |
|---|---|
| `mod`, `version` | shown in the report. `{version}` in any regex is replaced by the version, so a wrong build shows up as a FAIL. |
| `plugins` | the mod's plugin files; if none is active in plugins.txt, the mod is NOT LOADED |
| `dlls` | for SFSE plugins: DLL names. Without a DLL listing, `.dll` files in the input count. Give `plugins`, `dlls` or both. |
| `logs` | log file names to check instead of the Papyrus logs, for example `["my_sfse_plugin.log"]` |
| `names` | words to look for in the input's name ("named in note" in the summary) |
| `prefix` | regex for the mod's own log lines; no match anywhere = the mod never logged (required) |
| `scripts` | regex for the mod's script names; Papyrus errors whose message or stack matches it are the mod's errors |
| `expect` | lines that should appear: `id`, `re` (regex), `min` (default 1), `always` (must appear whenever the mod logged at all) |
| `order` | lists of `expect` ids whose first lines must appear in that order |
| `forbid` | lines that must not appear: `id`, `re` |
| `ignore` | regexes (or `{"re", "why"}`) for errors of the mod's scripts that are known and harmless |
| `show`, `means` | free text for people. The report prints `means` when a rule isn't PASS. |

Regexes use Python syntax and match anywhere in a log line. Double the backslashes in JSON.
Papyrus sometimes changes the case of a string it has seen before ("Started" can come out as
"started"); use `(?i:...)` around such words.

## Results

Per mod:

- **NOT LOADED**: none of its plugins is active in plugins.txt. Nothing else is checked.
- **NOT SEEN**: no line matches `prefix`. Usually the mod's features weren't tested, or the
  debug lines don't reach the log.
- **FAIL**: at least one rule failed.
- **PASS**: the mod logged, and no rule failed (some may be NOT SEEN).

Per rule:

| Rule | PASS | FAIL | NOT SEEN |
|---|---|---|---|
| expect | found at least `min` times | `always` and missing, or found fewer than `min` times | not found (feature probably not tested) |
| order | all found, in order | found, out of order | not all found |
| forbid | not found, mod logged | found | not found, mod never logged |
| script errors | none | an `error:` naming the mod's scripts | – |

Warnings naming the mod's scripts are listed but don't fail the mod. Errors from other scripts
(the base game, other mods) are only counted.

FLAG lines at the end aren't tied to one mod: crash logs in the input and suspended-stack lines
(the Papyrus engine falling behind).

## Tests

```
python -I tests/test_papyrus_log_check.py
```

The tests build small made-up logs, folders and zips; no game files are needed. The GitHub
workflow runs them on Windows and Linux.

## Licence

MIT; see [LICENSE](LICENSE). Changes are listed in [CHANGELOG.md](CHANGELOG.md).
