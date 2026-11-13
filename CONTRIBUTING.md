# Contributing to Ghostpad

Thanks for helping improve Ghostpad. This guide covers setup, standards and
the release process.

## Development setup

You need Windows 10 version 2004 or later, Python 3.10 or later, and Git.

```powershell
git clone https://github.com/rahullsing/GhostPad.git ghostpad
cd ghostpad
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Run the app from source:

```powershell
python ghostpad.pyw   # python, not pythonw, so tracebacks reach the console
```

## Before you open a pull request

Run all four checks. CI runs the same ones.

```powershell
python -m ruff format .                     # auto-format
python -m ruff check .                      # lint
python -m mypy                              # type-check
python -m unittest discover -s tests -v     # tests
```

All four must pass. If you change the UI, also launch the app and test the
change by hand.

## Coding standards

- **Standard library only.** Don't add runtime dependencies. The app must keep
  working as a single file with plain Python. Dev tools belong in
  `requirements-dev.txt`.
- **Formatting and linting.** Code is formatted with `ruff format` at line
  length 120. Lint rules are in `pyproject.toml`.
- **Type hints.** Add them to all new functions. `mypy` must stay clean.
- **Win32 calls.** Declare `argtypes` and `restype` with `_proto(...)` for
  every new `user32` or `kernel32` function. Without them, 64-bit handles get
  truncated.
- **Threads.** Only the main thread may touch Tk. Background threads talk to it
  through `queue`/`threading.Event`, and the main thread polls with
  `root.after`.
- **Hooks and callbacks.** Anything Windows calls into, such as hooks,
  WinEvents or enum callbacks, must never raise.
- **Capture protection.** Any new top-level window, such as a dialog or
  tooltip, must stay protected. The shield covers windows automatically, but
  run the app and check that the status-bar indicator stays green.
- **Pure logic.** Keep pure logic like parsing, file I/O and stats in
  module-level functions so it can be unit-tested without Tk.

## Tests

- **Location:** tests are in `tests/test_ghostpad.py` and use `unittest`.
- **Pure helpers:** test them directly.
- **App behaviour:** construct `GhostpadApp(data_dir=<temp dir>)` so tests
  never touch the real `%APPDATA%\Ghostpad`.
- **Windows-only tests:** decorate them with
  `@unittest.skipUnless(sys.platform == "win32", ...)`.

## Commit messages

Use the imperative mood, with a short summary line of 72 characters or fewer,
then a blank line and the details:

```text
Add Ctrl+G to jump to a line

Opens a small prompt in the find bar and moves the cursor to the
requested line, clamped to the document length.
```

Keep each commit focused on one logical change.

## Changing the icon

Edit the shapes or colours in `tools/make_icon.py`, then regenerate:

```powershell
python tools/make_icon.py   # rewrites assets/ghostpad.ico and assets/ghostpad.png
```

## Release process

1. Update the version in **both** `pyproject.toml` and `__version__` in
   `ghostpad.pyw`.
2. Move the `Unreleased` entries in `CHANGELOG.md` under a new version heading
   with today's date.
3. Build everything. This runs the tests, then creates the exe, the portable
   zip and the installer:

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\build.ps1
   ```

4. Smoke-test on a clean PC or VM if possible:
   - Run the installer.
   - Launch Ghostpad and check that the indicator shows 🟢 **Hidden**.
   - Do a test screen share.
   - Uninstall it from **Settings → Apps**.
5. If you have a certificate, sign the exe and the installer. See
   [docs/BUILDING.md](docs/BUILDING.md#6-code-signing-recommended-for-distribution).
6. Commit, then tag the release (for example `git tag v1.1.0`) and push the tag.
7. Attach `dist\installer\Ghostpad-Setup-<version>.exe` and
   `dist\Ghostpad-<version>-portable.zip` to the release. Don't commit `dist/`.

The full build and installer guide is [docs/BUILDING.md](docs/BUILDING.md).
