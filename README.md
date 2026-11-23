# papyrus-log-check

papyrus-log-check tells you, after a test session, whether your Starfield mod's scripts did what they should. You write a short rule file that lists the log lines your mod ought to write, and the tool reads the game's Papyrus log and marks each rule PASS, FAIL or NOT SEEN. It also points out script errors that name your mod, crash logs and signs that the script engine fell behind. Its starter rule pack explains the game's common Papyrus error lines in plain words, with no rule file of your own.

Download the latest zip from [Releases](https://github.com/taosecurity/papyrus-log-check/releases), unpack it, open a Command Prompt in the folder and run the built-in example first:

```
python papyrus_log_check.py examples\Papyrus.0.log --rules examples\example-beacon.logrules.json
```

For AI assistants: step-by-step instructions are in [AGENTS.md](AGENTS.md).

## Example

The release zip holds a made-up log and a rule file for a made-up mod called Example Beacon. This is a real run on them:

```
> python papyrus_log_check.py examples\Papyrus.0.log --rules examples\example-beacon.logrules.json
papyrus-log-check 0.4.0 by Richard Bejtlich - MIT - https://github.com/taosecurity/papyrus-log-check
Papyrus.0.log
  PASS       Example Beacon 1.0.0
Report: ...\out\logcheck-20261109-095824-run20261120-220538.txt
JSON:   ...\out\logcheck-20261109-095824-run20261120-220538.json
```

The summary gives one line per mod. The full text report in `out\` shows each rule and the log lines that matched it:

```
== Example Beacon 1.0.0: PASS
   Rules: examples\example-beacon.logrules.json
   Plugin: ExampleBeacon.esm (unknown)
   Mod log lines: 2 (first Papyrus.0.log:2, last Papyrus.0.log:3)
   PASS      expect started (at least 1, always): 1 found
             Papyrus.0.log:2  [21:00:04] [EXB] quest started, version 1.0.0
   PASS      expect beacon-placed (at least 1): 1 found
             Papyrus.0.log:3  [21:02:31] [EXB] beacon placed at 120.5, -44.0, 3.2
   NOT SEEN  expect beacon-removed (at least 1): 0 found
             (The player picked the beacon up again.)
   PASS      order started > beacon-placed: in order
   PASS      forbid no-double-start: 0 found
   PASS      script errors: 0 error(s), 0 warning(s)
...
```

Here the beacon was placed but never picked up again, so that rule is NOT SEEN: the feature simply wasn't tried in this session. Then point the tool at your own log and your own rule file:

```
python papyrus_log_check.py "C:\Users\<you>\Documents\My Games\Starfield\Logs\Script\Papyrus.0.log" --rules MyMod.logrules.json
```

## Install

The tool is one Python script that uses only Python's standard library, so there is nothing else to install. It needs Python 3.9 or newer and works on Windows and Linux (for example, on logs copied from a Steam Deck). It only reads: it never changes the logs or the rule files.

1. Install Python 3.9 or newer (the newest version is a good choice) from [python.org](https://www.python.org/downloads/). On the first screen of the installer, tick **Add python.exe to PATH**. To check that it worked, open a new Command Prompt and type `python --version`. It should print a version number.
2. Download `papyrus-log-check-0.4.0.zip` from [Releases](https://github.com/taosecurity/papyrus-log-check/releases) and unpack it anywhere.
3. Open the unpacked folder in File Explorer, click the address bar at the top, type `cmd` and press Enter. A Command Prompt window opens in that folder, ready for the commands in this README.
4. Run the example command at the top of this page. It should print `PASS       Example Beacon 1.0.0`.

## Words used here

- **Papyrus:** Starfield's scripting language. Scripts are written as `.psc` source files and compiled into `.pex` files that the game runs. The game can write what scripts do to a text file, the Papyrus log.
- **Plugin:** a mod's data file (`.esm`, `.esp` or `.esl`). It adds or changes records in the game.
- **`plugins.txt`:** the game's list of plugins, with `*` before each active one.
- **SFSE:** the Starfield Script Extender, which loads `.dll` plugins that add features the game lacks. Some SFSE plugins write their own log file, which this tool can check too.
- **Creation Kit (CK):** Bethesda's official editor for making Starfield mods.
- **Regex:** a search pattern, such as `quest started, version 1\.0`. The rule files use them to match log lines.

## Turn on Papyrus logging first

Starfield writes no Papyrus log until you ask it to. Add these lines to `Documents\My Games\Starfield\StarfieldCustom.ini` (make the file if it isn't there):

```ini
[Papyrus]
bEnableLogging=1
bEnableTrace=1
bLoadDebugInformation=1
```

- **Steam and Game Pass (Xbox app):** both use the same `Documents\My Games\Starfield` folder, so the steps are the same.
- **Vortex:** Vortex doesn't move this file, so edit it in `Documents\My Games\Starfield` as above.
- **Mod Organizer 2:** if your MO2 profile uses profile-specific INI files, edit the profile's `StarfieldCustom.ini` instead (MO2's INI editor does this). The logs still go to the `Documents` folder below.

Start the game, play the part you want to check, and quit. The logs are in `Documents\My Games\Starfield\Logs\Script\`: `Papyrus.0.log` is the newest session, `Papyrus.1.log` is the one before, and so on. The tool doesn't look for them by itself: you give it the file, folder or zip to read.

Your mod's own lines come from `Debug.Trace` calls in its scripts. If you compile with the `-release` flag, the compiler removes every `Debug` call, so nothing of yours reaches the log.

## Starter rule pack

You don't need a rule file of your own to get something out of the tool. The `rules\` folder holds three ready rule files that explain, in plain words, the error and warning lines the game's Papyrus engine writes. They work on any Papyrus log, with or without mods:

| Rule file | What it explains |
|---|---|
| [`rules/papyrus-runtime-errors.logrules.json`](rules/papyrus-runtime-errors.logrules.json) | Errors while a script runs: a call on an empty (None) variable, an object that no longer exists, an empty reference put into an alias, array mistakes, dividing by zero, None stored in a number or text variable, changing a constant global, an effect played on an object that isn't drawn, and runaway recursion ("Stack too deep"). |
| [`rules/papyrus-scripts-and-properties.logrules.json`](rules/papyrus-scripts-and-properties.logrules.json) | A missing script file ("Cannot open store ... missing file?"), a script attached to the wrong kind of object, a built-in function that nothing provides (usually a missing script extender plugin), properties that the script and the plugin disagree about, and scripts that are out of date with each other. |
| [`rules/papyrus-saves-and-load.logrules.json`](rules/papyrus-saves-and-load.logrules.json) | Warnings when a save was made with other versions of the scripts (a mod was updated or removed), and the warning that the script engine was overloaded and dumped its stacks. |

Their rules are **explain** rules. A rule that matches shows as FOUND, with its explanation, the first matching lines and, under each error, the script that raised it (`at ...`). FOUND never fails a run, so the exit code stays 0. Each file names `Starfield.esm` as its plugin, which the game always loads, so the pack is checked whatever your plugins.txt says.

The base game and most mods write some of these lines in every session, so a FOUND is not a fault by itself. Look at the `at` line to see whose script it is, and read the explanation when it names one of yours. The wording of each rule follows the Creation Kit wiki page "Papyrus Runtime Errors" and the lines Starfield actually writes.

The release zip has a made-up log, `examples\starter-pack-sample.log`, with one line for each rule. This is a real run of the whole pack on it, from the unpacked tool folder (from anywhere else, put the tool folder's path in front of `rules\` and `examples\`):

```
> python papyrus_log_check.py examples\starter-pack-sample.log --rules rules\papyrus-runtime-errors.logrules.json --rules rules\papyrus-scripts-and-properties.logrules.json --rules rules\papyrus-saves-and-load.logrules.json
papyrus-log-check 0.4.0 by Richard Bejtlich - MIT - https://github.com/taosecurity/papyrus-log-check
starter-pack-sample.log
  FOUND      Papyrus runtime errors 1.0.0
  FOUND      Papyrus saves and engine load 1.0.0
  FOUND      Papyrus scripts and properties 1.0.0
  FLAG       suspended stacks: 1 line(s), first starter-pack-sample.log:62
Report: ...\out\logcheck-20261120-220344-run20261120-220538.txt
JSON:   ...\out\logcheck-20261120-220344-run20261120-220538.json
```

The full report explains each line it found:

```
== Papyrus runtime errors 1.0.0: FOUND
   Rules: rules\papyrus-runtime-errors.logrules.json
   Plugin: Starfield.esm (active)
   Lines read: 36 (first starter-pack-sample.log:1, last starter-pack-sample.log:65)
   FOUND     explain none-object: 1 found
             (A script called a function on a variable or property that was empty (None). The usual cause is a property that was never filled in the Creation Kit, or an object that was deleted or not loaded yet. The script skipped that call and went on.)
             starter-pack-sample.log:24  [21:01:10] error: Cannot call GetReference() on a None object, aborting function call
                at [EXB_BeaconQuest (02000801)].EXB_BeaconScript.PlaceBeacon() - "EXB_BeaconScript.psc" Line 41
...
```

On the sample log every rule is FOUND. On a real log most rules find nothing, and those show as `PASS ... 0 found`. To check your own log, give the same three `--rules` with your log in place of the sample. You can also give them together with your mod's own rule file. Errors whose stack names your scripts already fail your mod through its `scripts` pattern. For a message that names the script itself, such as a missing script file, you can copy the pattern into your rule file's `forbid` list with your own script name in it, so that the line fails your mod.

## Add logging to a Creation Kit mod

The tool can only check what your mod writes to the log. If your scripts have no `Debug.Trace` lines yet, add a few. You don't need many: one when the mod starts and one at each step you want to confirm in a test.

1. **Pick one prefix and keep it.** Choose a short tag for your mod, such as `MYMOD:`, and start every line with it. The rule file's `prefix` matches it, so a line with a different spelling (`MyMod:` or `MYMOD -`) is invisible to the tool.
2. **Put the prefix in one place.** Give each script a small `Log` function that adds the prefix, and call it instead of `Debug.Trace`. Then a typo can't creep in.
3. **Log at the moments a tester would ask about.** Good places are the start of the events your mod reacts to (`OnQuestInit`, `OnInit`, `OnActivate`, `OnItemEquipped` and so on), the code in a quest stage fragment, the line just after the mod does its main job, and any branch where something goes wrong (write `WARNING` in those).
4. **Include the version in the start line.** A rule with `{version}` then catches an old build that is still installed.
5. **Never compile with `-release`.** It removes every `Debug` call. Compile normally, from the Creation Kit or with the Papyrus compiler without that flag.

Here is a quest script for a made-up mod, in the script's `.psc` source:

```papyrus
ScriptName MYMOD_QuestScript extends Quest

String Property ModVersion = "0.1.0" AutoReadOnly

Function Log(String msg)
    Debug.Trace("MYMOD: " + msg)
EndFunction

Event OnQuestInit()
    Log("quest started, version " + ModVersion)
EndEvent

Function ItemUsed(ObjectReference akUser)
    Log("item used by " + akUser)
    If akUser == None
        Log("WARNING: no user, reward skipped")
        Return
    EndIf
    ; ... the mod's real work goes here ...
    Log("reward given")
EndFunction
```

In a quest stage fragment, write the whole call, with the same prefix: `Debug.Trace("MYMOD: stage 20 reached")`.

[`examples/starter-mymod.logrules.json`](examples/starter-mymod.logrules.json) is a starter rule file for exactly these lines. The start line (with the version) must appear, "item used" and "reward given" should appear in that order, and a `WARNING` line fails the mod. The script names (`scripts`) start with the same tag, so Papyrus errors in your scripts are counted as yours.

Copy it, change `mod`, `version`, `plugins`, `prefix` and the patterns to your own, and add a rule for each new line you log. To check that your copy loads, run it on the example log. That log comes from another mod, so a good copy shows NOT SEEN and exits with code 0, while a mistake in the file stops with exit code 2 and names the field:

```
> python papyrus_log_check.py examples\Papyrus.0.log --rules examples\starter-mymod.logrules.json
papyrus-log-check 0.4.0 by Richard Bejtlich - MIT - https://github.com/taosecurity/papyrus-log-check
Papyrus.0.log
  NOT SEEN   My Mod 0.1.0
Report: ...\out\logcheck-20261109-095824-run20261120-220538-2.txt
JSON:   ...\out\logcheck-20261109-095824-run20261120-220538-2.json
```

## What it can read

You can give it any of these three kinds of input:

| Input | What it reads |
|---|---|
| A log file (`Papyrus.0.log`, or any file in the same format, whatever its name) | It reads that one log. |
| A folder (for example `Logs\Script`) | It reads every `Papyrus.N.log` in the folder and its subfolders, oldest first. It skips logs in `User\` folders. |
| A zip | It reads the zip the same way as a folder. It reads the zip in memory and unpacks nothing. |

A folder or zip may also hold these files:

- **`plugins.txt`** is the game's plugin list. When it is there, a mod whose plugin isn't active is shown as NOT LOADED and isn't checked. When it is missing, every rule file is checked. A rule file whose only plugins are official masters always counts as active, because the game loads them without listing them there: `Starfield.esm`, the DLC masters (`Constellation.esm`, `OldMars.esm`, `ShatteredSpace.esm`), the `SFBGS*.esm` updates and `BlueprintShips-<official>.esm`. When the input is a collector package whose manifest lists the Data folder's plugins (`listing.dataPlugins`), an official master that isn't in that list doesn't count (`Starfield.esm` always does). In a file that also names other plugins, only those are looked up.
- **The collector's lists** in `manifest.json` (`listing.dataPlugins` and `listing.sfsePluginDlls`) are used as above. An empty Data plugin list counts as no list, and so do both empty lists when the collector didn't find the game folder (an empty `gamePath`).
- **Crash logs** (`Crashlog*.txt`, `crash-*.log`, or files in a `crashlogs` folder) are listed as FLAG lines.
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
| `--root FOLDER` | If you keep many mods as `<FOLDER>\<project>\testplan\logrules.json` (or one level deeper, `<FOLDER>\<group>\<project>\...`), this option finds all of their rule files. Without `--mods`, only mods whose plugin is active in `plugins.txt` (or whose DLL is loaded) are checked. Each of the others gets one `NOT LOADED` line in the summary and in a short list at the end of the report. The default is the current folder, and it is used only when no `--rules` is given. |
| `--mods A,B` | With `--root`, this checks only the project folders you name. |
| `--logs-dir FOLDER` | When no INPUT is given, this checks the newest `.zip` in the folder. "Newest" goes by the `yyyymmdd-hhmmss` stamp in the file name, or else by file time. The environment variable `PAPYRUS_LOG_CHECK_LOGS` does the same. |
| `--out FOLDER` | This sets where the reports go. The default is `out\` next to the script. |
| `--max-lines N` | This sets how many matching lines the text report shows per rule. The default is 5, and the JSON report keeps up to 50. |
| `--set-version MyMod=0.9.1` | This checks a mod as another version than its rule file says (give the mod name or project folder). It is for rechecking older logs, and you can repeat it. When the log was written by yet another version, a rule with `{version}` FAILs, and the report shows the version the log has. |
| `--verbose` | This prints a troubleshooting log on stderr (see below). |
| `--log FILE` | This writes the same troubleshooting log to FILE, for example `--log papyrus-log-check.log.txt`. |
| `--version` | This prints the version and license, then exits. |

When a rule with `{version}` finds nothing, the report also shows the same line logged with any other version. That usually means a different build was installed.

Each run writes two files, named after the input's time stamp and the time of the run, so nothing is ever overwritten. A second run in the same second gets `-2` added, as in the starter example above.

```
logcheck-20261109-095824-run20261120-220538.txt   plain-text report
logcheck-20261109-095824-run20261120-220538.json  the same data for other tools
```

The exit code tells scripts what happened:

- 0 means no rule failed.
- 1 means at least one rule failed.
- 2 means the arguments were wrong, a rule file was bad, or the input couldn't be read.

With `--root`, a rule file that can't be read at all is skipped and listed as SKIPPED in the summary and the report. A bad pattern in the rule file of a mod that isn't loaded never stops the run. A bad pattern in a loaded mod's rule file does stop it, with exit code 2 and the file and pattern named.

## Rule files

Each mod has one JSON rule file. [`examples/example-beacon.logrules.json`](examples/example-beacon.logrules.json) is a complete one for a made-up mod, and this one has the same shape:

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
| `plugins` | These are the mod's plugin files. If none of them is active in plugins.txt, the mod is NOT LOADED. `Starfield.esm` always counts as active, so a rule file about the game's own messages names it as its only plugin. The other official masters (the DLC, `SFBGS*.esm` and `BlueprintShips-<official>.esm`) count the same way when their file is in Data, so a rule file about a DLC's own messages names that DLC's master. In a rule file that also names other plugins or DLLs, official masters don't count: one of the others must be loaded. |
| `dlls` | These are the DLL names of an SFSE plugin. Without a DLL listing, `.dll` files in the input count as installed. Give `plugins`, `dlls` or both. |
| `logs` | These are log file names to check instead of the Papyrus logs, for example `["my_sfse_plugin.log"]`. |
| `names` | These are words to look for in the input's name. A match shows as "named in note" in the summary. |
| `prefix` | This required regex matches the mod's own log lines. If nothing matches anywhere, the mod never logged. |
| `scripts` | This regex matches the mod's script names. Papyrus errors whose message or stack matches it count as the mod's errors. |
| `expect` | These are lines that should appear. Each has an `id`, a regex `re`, an optional `min` (default 1) and an optional `always` (the line must appear whenever the mod logged at all). |
| `order` | Each entry lists `expect` ids whose first lines must appear in that order. |
| `forbid` | These are lines that must not appear. Each has an `id` and a regex `re`. A forbid rule fails on any matching line, so it can't have `min` or `always`: the rule file is refused with a message that names the rule. |
| `explain` | These are lines worth knowing about, which don't fail the mod. Each has an `id`, a regex `re` and a `means` that says what the line means. The starter rule pack is made of them. An explain rule can't have `min` or `always`, except `"min": 1` and `"always": false`, which say what it does anyway and change nothing. |
| `ignore` | These regexes (or `{"re", "why"}` pairs) match errors of the mod's scripts that are known and harmless. |
| `show`, `means` | These hold free text for people. The report prints `means` when a rule isn't PASS. Other fields, such as the pack's `about` and `source`, are notes for people and are not read. |

Regexes use Python syntax and match anywhere in a log line. Double the backslashes in JSON. Papyrus sometimes changes the case of a string it has seen before ("Started" can come out as "started"), so use `(?i:...)` around such words.

The example log has a script error from Example Beacon (`Cannot call Delete() on a None object`), and the beacon's rule file lists it under `ignore`. That is why the Example's error is not held against the mod, and the full report ends with this "Package checks" part:

```
Package checks
  The input has no crash logs, Windows crash events or suspended stacks.
  Info: Papyrus.0.log has 1 error(s) and 1 warning(s) from other scripts (the base game or other mods). They are not counted.
```

## Results

Each mod gets one of five results:

- **NOT LOADED** means none of its plugins is active in plugins.txt and none of its DLLs is installed. Nothing else is checked. The report says which check it was: plugins.txt for a rule file that names only plugins, the input's list of SFSE plugin DLLs for one that names only DLLs, or both, and the Data plugin list for one that names only official masters. The JSON gives the same sentence in `not_loaded_reason`.
- **NOT SEEN** means no line matches `prefix` and no rule passed. Usually the mod's features weren't tested, or the debug lines don't reach the log.
- **FAIL** means at least one rule failed.
- **FOUND** means no rule failed, but at least one `explain` rule matched. Read its lines in the report. It doesn't change the exit code. A mod that never logged stays NOT SEEN even when an explain rule matched (its FOUND lines are still in the report), unless its rule file has only explain rules, as the starter pack's files do. For a mod that stays NOT SEEN this way, the screen and the report's summary show `NOT SEEN (N found)`, where N is the number of lines its explain rules found (a line two rules match counts twice). The JSON status stays `NOT SEEN`, and each checked mod has the number in `explain_found`.
- **PASS** means the mod logged and no rule failed. Some rules may still be NOT SEEN.

For example, [`examples/example-quiet.logrules.json`](examples/example-quiet.logrules.json) is for a made-up mod that never logged in the example log, but its explain rule matches two of the log's lines:

```
> python papyrus_log_check.py examples\Papyrus.0.log --rules examples\example-quiet.logrules.json
papyrus-log-check 0.4.1 by Richard Bejtlich - MIT - https://github.com/taosecurity/papyrus-log-check
Papyrus.0.log
  NOT SEEN (2 found) Example Quiet 0.2.0
Report: ...\out\logcheck-20261109-095824-run20261122-191459.txt
JSON:   ...\out\logcheck-20261109-095824-run20261122-191459.json
```

Each rule gets its own result:

- An **expect** rule passes when its line is found at least `min` times. It fails when an `always` line is missing, or when the line is found fewer than `min` times. It is NOT SEEN when the line isn't found at all, which usually means the feature wasn't tested.
- An **order** rule passes when all its lines are found in order, and fails when they are found out of order. It is NOT SEEN when some of them aren't found.
- A **forbid** rule fails when its line is found. It passes when the line isn't found and the mod logged, and it is NOT SEEN when the mod never logged.
- An **explain** rule is FOUND when its line is found, and never fails. Like a forbid rule, it passes when the line isn't found and the mod logged, and it is NOT SEEN when the mod never logged.
- The **script errors** check fails when an `error:` line names the mod's scripts, and passes when none does.

Warnings that name the mod's scripts are listed, but they don't fail the mod. Errors from other scripts (the base game, other mods), and errors on a mod's `ignore` list, are only counted.

Text from the logs, rule files and manifest is shown with control characters as `\xNN`, so escape codes hidden in a shared log can't change your terminal.

FLAG lines at the end of the report aren't tied to one mod. They report crash logs in the input and suspended-stack lines, which mean the Papyrus engine was falling behind.

The tool's report is a reading aid for mod authors and testers, not a verdict on the mod.

## Troubleshooting

When a run doesn't do what you expect, turn on the troubleshooting log. `--verbose` prints it on stderr, with each line starting `log: `. `--log FILE` writes it to a file you name, which is overwritten on each run.

The log says what was read (the input, how many logs, plugins.txt, the manifest), each rule file and what it holds, which mods were left out because their plugin isn't loaded, and each mod's result. When a run stops, it holds the full error. The report and the summary are the same with or without it.

`--log` refuses a name that would overwrite an input: a Papyrus log, the zip, a rule file or anything inside the input folder. This is the log of the Example run:

```
> python papyrus_log_check.py examples\Papyrus.0.log --rules examples\example-beacon.logrules.json --verbose
papyrus-log-check 0.4.0 by Richard Bejtlich - MIT - https://github.com/taosecurity/papyrus-log-check
log: papyrus-log-check 0.4.0 by Richard Bejtlich - MIT - https://github.com/taosecurity/papyrus-log-check; Python 3.13.15 on win32
log: arguments: examples\Papyrus.0.log --rules examples\example-beacon.logrules.json --verbose
log: input: log file examples\Papyrus.0.log: 1 files, 1 Papyrus log(s), plugins.txt none, manifest none
log: rule file examples\example-beacon.logrules.json: mod Example Beacon 1.0.0, 3 expect, 1 forbid, 1 order, 0 explain rule(s)
log: Papyrus errors and warnings: 2
log: Example Beacon: PASS (plugin unknown, 2 mod log line(s))
log: wrote ...\out\logcheck-20261109-095824-run20261120-220538-3.txt and ...\out\logcheck-20261109-095824-run20261120-220538-3.json; overall OK
...
```

## Privacy

It runs offline and only reads the files you give it. It writes nothing but its two report files (and the troubleshooting log, if you ask for one). It never looks up your user name, computer name or anything else about your PC.

Reports quote lines from your logs (and, if your log zip has a collector's manifest, its user and computer names), so read a report before you post it. [PRIVACY.md](PRIVACY.md) has the details.

## Tests

```
python -I tests/test_papyrus_log_check.py
```

The tests build small made-up logs, folders and zips, so no game files are needed. The GitHub workflow runs them on Windows and Linux.

## Found a mistake?

Open an issue: https://github.com/taosecurity/papyrus-log-check/issues

## Credits and License

papyrus-log-check was made by Richard Bejtlich and built with [Claude Code](https://claude.com/claude-code). It uses only the [Python](https://www.python.org/) standard library.

It is released under the MIT License; see [LICENSE](LICENSE). Changes are listed in [CHANGELOG.md](CHANGELOG.md).
