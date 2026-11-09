# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2026 Richard Bejtlich
"""Build the release zip and its SHA-256 checksum file.

  python -I build_release.py                 build dist/papyrus-log-check-<version>.zip (+ .sha256)
  python -I build_release.py --tag v0.2.0    the same, but first check that the tag matches the script's
                                             VERSION and that CHANGELOG.md has a dated entry for it

Also writes build/release-notes.md (the CHANGELOG entry), used as the GitHub release text.
The zip holds one folder, papyrus-log-check-<version>/, with fixed file times, so the same sources
give the same zip.
"""
import argparse
import hashlib
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = [
    "papyrus_log_check.py", "README.md", "LICENSE", "CHANGELOG.md",
    "examples/example-beacon.logrules.json", "examples/Papyrus.0.log",
    "tests/test_papyrus_log_check.py",
]
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def script_version():
    with open(os.path.join(HERE, "papyrus_log_check.py"), encoding="utf-8") as f:
        m = re.search(r'^VERSION = "([^"]+)"', f.read(), re.M)
    if not m:
        raise SystemExit("VERSION not found in papyrus_log_check.py")
    return m.group(1)


def changelog_entry(version):
    """(heading, body) of the CHANGELOG entry for this version."""
    with open(os.path.join(HERE, "CHANGELOG.md"), encoding="utf-8") as f:
        text = f.read()
    m = re.search(rf"^## {re.escape(version)}\b(.*)$\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        raise SystemExit(f"CHANGELOG.md has no entry for {version}")
    return m.group(1).strip(), m.group(2).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", help="the git tag being released, e.g. v0.2.0")
    args = ap.parse_args()

    version = script_version()
    heading, notes = changelog_entry(version)
    if args.tag is not None:
        if args.tag != "v" + version:
            raise SystemExit(f"tag {args.tag} doesn't match VERSION {version} (expected v{version})")
        if "not yet released" in heading.lower() or not re.search(r"\d{4}-\d\d-\d\d", heading):
            raise SystemExit(f"CHANGELOG.md entry for {version} needs a release date, e.g. '## {version} (2026-11-10)'")

    dist = os.path.join(HERE, "dist")
    build = os.path.join(HERE, "build")
    os.makedirs(dist, exist_ok=True)
    os.makedirs(build, exist_ok=True)
    top = f"papyrus-log-check-{version}"
    zpath = os.path.join(dist, top + ".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(FILES):
            with open(os.path.join(HERE, rel), "rb") as f:
                data = f.read()
            info = zipfile.ZipInfo(f"{top}/{rel}", FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    with open(zpath, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    with open(zpath + ".sha256", "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{digest}  {os.path.basename(zpath)}\n")
    with open(os.path.join(build, "release-notes.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(notes + "\n\n" + f"SHA-256 of `{os.path.basename(zpath)}`: `{digest}`\n")

    print(zpath)
    print(f"SHA-256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
