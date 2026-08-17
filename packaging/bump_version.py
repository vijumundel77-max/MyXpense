"""Expenzo — bump the central release version.

Usage:
    python packaging/bump_version.py 1.0.1

Updates VERSION in version_service.py at the repo root (the single source
of truth), and refreshes the repo-side metadata stubs.  Run before building
a release; the installer/release scripts then pick up the new version
automatically.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_SERVICE = ROOT / "version_service.py"
UPDATES_JSON = ROOT / "updates" / "latest.json"
RELEASE_INDEX = ROOT / ".github" / "release" / "release-metadata.json"
_INSTALLER_RE = re.compile(r"^ExpenzoSetup-(\d+\.\d+\.\d+)\.exe$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python packaging/bump_version.py 1.0.1", file=sys.stderr)
        return 1
    new_version = sys.argv[1].strip().lstrip("v")
    if not _VERSION_RE.match(new_version):
        print(f"ERROR: invalid version {new_version!r} (expected MAJOR.MINOR.PATCH)",
              file=sys.stderr)
        return 1

    # 1) version_service.py — single source of truth.
    src = VERSION_SERVICE.read_text(encoding="utf-8")
    src, n = re.subn(r'(^VERSION\s*=\s*")[^"]+(")', rf"\g<1>{new_version}\g<2>",
                     src, count=1, flags=re.MULTILINE)
    if n != 1:
        print("ERROR: could not locate VERSION in version_service.py", file=sys.stderr)
        return 1
    VERSION_SERVICE.write_text(src, encoding="utf-8")
    print(f"  version_service.py  VERSION = {new_version}")

    installer = f"ExpenzoSetup-{new_version}.exe"
    url = (f"https://github.com/vijumundel77-max/MyXpense/releases/download/"
           f"v{new_version}/{installer}")

    # 2) updates/latest.json — repo metadata stub (sha256 filled by the build).
    try:
        meta = json.loads(UPDATES_JSON.read_text(encoding="utf-8"))
    except Exception:
        meta = {}
    meta.update({
        "schema_version": 1,
        "app": "Expenzo",
        "version": new_version,
        "installer_name": installer,
        "installer_url": url,
        "release_notes": meta.get("release_notes", ""),
        "published_at": meta.get("published_at", ""),
        "sha256": "",
    })
    UPDATES_JSON.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"  updates/latest.json  -> {new_version}")

    # 3) .github/release/release-metadata.json — release index stub.
    try:
        index = json.loads(RELEASE_INDEX.read_text(encoding="utf-8"))
    except Exception:
        index = {"schema_version": 1, "app": "Expenzo", "current_version": "", "releases": []}
    index["current_version"] = new_version
    index["releases"] = [r for r in index.get("releases", []) if r.get("version") != new_version]
    index["releases"].append({
        "version": new_version,
        "tag": f"v{new_version}",
        "installer_name": installer,
        "installer_url": url,
        "release_notes": "",
        "published_at": "",
    })
    index["releases"].sort(key=lambda r: r["version"])
    RELEASE_INDEX.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"  .github/release/release-metadata.json  -> {new_version}")

    print("\nDone. Next: powershell -File packaging\\build_release.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
