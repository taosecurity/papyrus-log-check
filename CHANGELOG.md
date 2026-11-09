# Changelog

## 0.2.0 (not yet released)

First public release.

- Reads a single Papyrus log file (any name), a folder of `Papyrus.N.log` files, or a zip of them.
- `--rules FILE` gives rule files directly (repeat it, or give a comma list).
- `--logs-dir` picks the newest `.zip` of any name.
- For SFSE plugins without a DLL listing, `.dll` files in the input count as installed.
- A `manifest.json` without a `tool` field (not written by a log collector) is ignored.
- README: a Privacy section.
- An example rule file and log for a made-up mod in `examples/`.
- Tests run on Windows and Linux in GitHub Actions; tagged releases get a zip and a SHA-256 checksum.

## 0.1.0

Private version, not released.
