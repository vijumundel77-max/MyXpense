# Expenzo — GitHub Release & Update Infrastructure

Expenzo ships as a per-user Windows installer (`ExpenzoSetup-X.X.X.exe`)
built with PyInstaller + Inno Setup.  GitHub Releases are the official
update source: the app later detects newer versions from the metadata below.

## Version management

One central version string drives everything:

- **`version_service.py`** (repo root) — `VERSION = "1.0.0"` is the single
  source of truth.  Bump it for each release (1.0.1, 1.0.2, …).
- The build script, installer, PyInstaller file-properties and release
  metadata all read this value; `config.APP_VERSION` reports the installed
  version (per-user `%APPDATA%\Expenzo\version.json` wins over the
  compiled-in default).

Bump for a new release:

```powershell
# Option A: edit version_service.py VERSION, then
powershell.exe -ExecutionPolicy Bypass -File packaging\build_release.ps1

# Option B: one-shot override without editing the source
powershell.exe -ExecutionPolicy Bypass -File packaging\build_release.ps1 -Version 1.0.1

# Option C: automated bump
python packaging\bump_version.py 1.0.1
```

## Release flow

1. **Build** — `packaging/build_release.ps1` produces:
   - `dist\Expenzo\Expenzo.exe` (frozen app)
   - `dist\ExpenzoSetup-<version>.exe` (Inno installer, per-user, no admin)
   - `dist\release.json` (release metadata + SHA256)
   - `updates\latest.json` (repo-side metadata the app checks)
2. **Publish** — `packaging/create_github_release.py`:
   - validates the installer + metadata,
   - syncs `updates/latest.json` and `.github/release/release-metadata.json`,
   - prints (or runs with `--publish`) the `gh release create` command that
     tags `v<version>` and attaches `ExpenzoSetup-<version>.exe` +
     `release.json`.

```powershell
python packaging\create_github_release.py --publish --notes-file RELEASE_NOTES.md
```

## Metadata schema

`release.json` attached to each GitHub Release (also mirrored at
`updates/latest.json` on `main`):

```json
{
  "schema_version": 1,
  "app": "Expenzo",
  "version": "1.0.1",
  "installer_name": "ExpenzoSetup-1.0.1.exe",
  "installer_url": "https://github.com/vijumundel77-max/MyXpense/releases/download/v1.0.1/ExpenzoSetup-1.0.1.exe",
  "release_notes": "…",
  "published_at": "2026-01-15T10:00:00Z",
  "sha256": "…"
}
```

GitHub Release convention:

| Field | Value |
|---|---|
| Tag | `v1.0.1` |
| Title | `Expenzo 1.0.1` |
| Assets | `ExpenzoSetup-1.0.1.exe`, `release.json` |

The app reads this via `services/update_service.py`
(`check_for_updates()`) — see Task 2 for the UI that consumes it.

## User-data safety

- User data lives in `%APPDATA%\Expenzo` (database + exports).
- The installer never touches it; updates only overlay program files.
- `version.json` is written next to the database and is never deleted,
  reset, or overwritten by the update/release process.
