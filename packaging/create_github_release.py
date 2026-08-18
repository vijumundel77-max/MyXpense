"""
Expenzo — GitHub Release builder (Task 1 infrastructure).

Prepares and prints everything needed to publish a release from the build
outputs, and keeps the repo-side update metadata in sync.

Run after a successful `packaging/build_release.ps1`:

    python packaging/create_github_release.py [--version 1.0.1] [--notes-file NOTES.md] [--publish]

With --publish it runs the `gh release create` command itself (requires the
GitHub CLI and a logged-in gh).  Without it, the exact command is printed.

What it does:
  1. Resolves the release version from the central version service.
  2. Validates dist/ExpenzoSetup-<version>.exe and dist/release.json.
  3. Writes the release notes body (from --notes-file or a template).
  4. Updates updates/latest.json (repo metadata the app checks) + the
     .github/release/release-metadata.json release index.
  5. Prints the `gh release create` command (tag v<version>, installer
     asset + release.json asset).

The installer must be built first; this script never rebuilds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from version_service import VERSION, is_valid_version  # noqa: E402

REPO = "vijumundel77-max/MyXpense"
ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
UPDATES_JSON = ROOT / "updates" / "latest.json"
RELEASE_INDEX = ROOT / ".github" / "release" / "release-metadata.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _installer_name(version: str) -> str:
    return f"ExpenzoSetup-{version}.exe"


def build_release_notes(version: str, notes_file: Path | None) -> str:
    if notes_file and notes_file.is_file():
        return notes_file.read_text(encoding="utf-8").strip()
    return (
        f"## Expenzo {version}\n\n"
        f"Installer: `{_installer_name(version)}`\n\n"
        "### What's new\n- \n\n"
        "### Fixes\n- \n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=None,
                        help="Release version (default: central VERSION)")
    parser.add_argument("--notes-file", default=None,
                        help="Path to a markdown file with release notes")
    parser.add_argument("--publish", action="store_true",
                        help="Run `gh release create` (requires GitHub CLI)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate and print the command without writing files")
    args = parser.parse_args()

    version = (args.version or VERSION).strip().lstrip("v")
    if not is_valid_version(version):
        print(f"ERROR: invalid version {version!r} (expected MAJOR.MINOR.PATCH)", file=sys.stderr)
        return 1

    notes_file = Path(args.notes_file) if args.notes_file else None

    installer = DIST / _installer_name(version)
    release_json = DIST / "release.json"
    if not installer.is_file():
        print(f"ERROR: installer not found: {installer}", file=sys.stderr)
        print("Build it first: powershell -File packaging\\build_release.ps1", file=sys.stderr)
        return 1
    if not release_json.is_file():
        print(f"ERROR: release metadata not found: {release_json}", file=sys.stderr)
        return 1

    sha = _sha256(installer)
    installer_url = (f"https://github.com/{REPO}/releases/download/"
                     f"v{version}/{_installer_name(version)}")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Release metadata dict (also the schema the app's update check reads).
    metadata = {
        "schema_version": 1,
        "app": "Expenzo",
        "version": version,
        "installer_name": _installer_name(version),
        "installer_url": installer_url,
        "release_notes": "",
        "published_at": now,
        "sha256": sha,
    }

    notes = build_release_notes(version, notes_file)

    if not args.dry_run:
        # Keep the repo-side metadata files in sync with this release.
        UPDATES_JSON.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        try:
            index = json.loads(RELEASE_INDEX.read_text(encoding="utf-8"))
        except Exception:
            index = {"schema_version": 1, "app": "Expenzo", "current_version": "", "releases": []}
        index["current_version"] = version
        index["releases"] = [r for r in index.get("releases", []) if r.get("version") != version]
        index["releases"].append({
            "version": version,
            "tag": f"v{version}",
            "installer_name": _installer_name(version),
            "installer_url": installer_url,
            "release_notes": notes,
            "published_at": now,
        })
        index["releases"].sort(key=lambda r: r["version"])
        RELEASE_INDEX.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
        print(f"Updated {UPDATES_JSON.relative_to(ROOT)}")
        print(f"Updated {RELEASE_INDEX.relative_to(ROOT)}")

    command = (
        f"gh release create v{version} "
        f'"{installer}" "{release_json}" '
        f"--repo {REPO} "
        f'--title "Expenzo {version}" '
        f"--notes-file -"
    )
    print()
    print("GitHub release command:")
    print("  " + command)
    print()
    print("Release notes to pipe into the command (or pass --notes-file):")
    print("-" * 60)
    print(notes)
    print("-" * 60)

    if args.publish:
        import subprocess
        result = subprocess.run(
            ["gh", "release", "create", f"v{version}",
             str(installer), str(release_json),
             "--repo", REPO,
             "--title", f"Expenzo {version}",
             "--notes-file", "-"],
            input=notes.encode("utf-8"),
        )
        return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
