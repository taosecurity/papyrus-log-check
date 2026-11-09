# Changelog

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
