# Changelog

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

From a code review and a security review.

- New `--verbose` and `--log FILE`: a troubleshooting log of what was read, what was decided and why a run
  stopped. `--log` refuses a name that would overwrite an input.
- AGENTS.md: step-by-step instructions for AI assistants, also in the release zip.
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
