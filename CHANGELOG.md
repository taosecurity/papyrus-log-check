# Changelog

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
