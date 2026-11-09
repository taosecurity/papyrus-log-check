# Privacy

papyrus-log-check runs on your own computer, offline. It collects no data and sends nothing anywhere.

## What it does not do

- It makes no network connections.
- It has no telemetry, analytics, crash reporting or update checks.
- It never looks up your user name, computer name or anything else about your PC.
- It starts no other programs.

## What it reads

Only what you point it at:

- the Papyrus log file, folder of `Papyrus.N.log` files, or zip you give it (or, with `--logs-dir` or the
  `PAPYRUS_LOG_CHECK_LOGS` environment variable, the newest zip in that folder);
- the rule files you give with `--rules`, or the `<project>\testplan\logrules.json` files under `--root`.

## What it writes

Two report files (`.txt` and `.json`) in the `--out` folder, or in `out\` next to the script if you don't give one.
Nothing else.

## What the reports contain

Reports quote lines from your logs. If your log zip came from a log collector, its manifest may hold your Windows
user and computer names, and those can appear in a report too. Read a report before you post it.

## Downloading it

Downloading papyrus-log-check from GitHub is covered by GitHub's own
[privacy statement](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement). Its
author receives only the public download counts GitHub shows.

## Questions

Open an issue at https://github.com/taosecurity/papyrus-log-check/issues.
