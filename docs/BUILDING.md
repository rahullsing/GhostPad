# Building, distributing and installing Ghostpad

This guide covers how to:

1. [run Ghostpad from source](#1-run-from-source) on any Windows PC,
2. [compile it into a standalone `.exe`](#2-compile-a-standalone-executable),
3. [run it on other PCs](#3-run-on-other-pcs) without Python,
4. [build an installer wizard](#4-build-the-installer-wizard) (`Ghostpad-Setup-<version>.exe`),
5. [install silently](#5-silent-installs-for-it) in bulk, and
6. [sign the files](#6-code-signing-recommended-for-distribution) so Windows trusts them.

For the quickest route, run one command. It runs the tests, compiles the exe,
then creates the portable zip and the installer:

```powershell
powershell -ExecutionPolicy Bypass -File tools\build.ps1
```

## Supported systems

| | Supported | Notes |
| --- | --- | --- |
| Windows 11 (x64) | ✅ | Fully supported |
| Windows 10 version 2004 (build 19041) or later (x64) | ✅ | Fully supported |
| Windows 10 before version 2004 | ⚠️ | Runs, but captures show a black box instead of hiding the window. The installer refuses to install. |
| Windows on ARM (ARM64) | ⚠️ | Expected to run the x64 build under emulation. Untested. |
| macOS, Linux | ❌ | Capture protection and global hotkeys are Windows APIs |

Run `winver` to see a PC's Windows version.

---

## 1. Run from source

The PC needs **Python 3.10 or later** from [python.org](https://www.python.org/downloads/).
During setup, tick **"Add python.exe to PATH"**. The default install includes
Tkinter. Ghostpad has no other dependencies.

```powershell
git clone https://github.com/rahullsing/GhostPad.git ghostpad
cd ghostpad
pythonw ghostpad.pyw          # starts without a console window
```

You can also double-click `ghostpad.pyw` in Explorer. To see error messages
while debugging, run `python ghostpad.pyw` instead.

## 2. Compile a standalone executable

Ghostpad is compiled with [PyInstaller](https://pyinstaller.org/). It bundles
the Python runtime, Tkinter and the app into a folder that runs on any
supported Windows PC, even one without Python.

### One-time setup

```powershell
python -m pip install -r requirements-dev.txt   # PyInstaller, ruff, mypy
```

### Build

```powershell
python -m PyInstaller --noconfirm --clean Ghostpad.spec
```

That creates:

```text
dist\Ghostpad\
├── Ghostpad.exe       ← the app
└── _internal\         ← Python runtime, Tkinter, icon (required)
```

`Ghostpad.exe` needs the `_internal` folder next to it, so always move or copy
the **whole `dist\Ghostpad` folder**. `Ghostpad.spec` controls the build:

- **Icon:** it embeds `assets\ghostpad.ico`.
- **Version details:** it adds them, read from `__version__` in
  `ghostpad.pyw`, for Explorer's Properties page and the installed-apps list.
- **No UPX compression:** packed executables trigger more antivirus false
  positives, so the build doesn't use UPX.

> **Architecture:** the exe matches the Python used to build it. A 64-bit
> Python builds a 64-bit app, which is what the installer expects. Check with
> `python -c "import struct; print(struct.calcsize('P') * 8)"`.

## 3. Run on other PCs

There are two ways to get the compiled app onto another PC. Neither needs
Python on the target PC.

| | Portable zip | Installer wizard |
| --- | --- | --- |
| File | `dist\Ghostpad-<version>-portable.zip` | `dist\installer\Ghostpad-Setup-<version>.exe` |
| Admin rights | Not needed | Not needed (optional for all users) |
| Start menu, desktop shortcut | No | Yes |
| Start with Windows | Manual | Optional checkbox |
| Uninstall | Delete the folder | **Settings → Apps → Installed apps** |
| Best for | USB sticks, quick tests | Everyday use, sharing with others |

**Portable:** unzip anywhere, for example `C:\Tools\Ghostpad`, and run
`Ghostpad\Ghostpad.exe`. `tools\build.ps1` creates the zip. To make it by hand:

```powershell
Compress-Archive -Path dist\Ghostpad -DestinationPath dist\Ghostpad-portable.zip
```

### First launch on a new PC

- **"Windows protected your PC" (SmartScreen).** This appears for unsigned
  apps downloaded from the internet. Click **More info → Run anyway**. Signing
  the files removes the warning, see [section 6](#6-code-signing-recommended-for-distribution).
- **Antivirus quarantines the exe.** PyInstaller apps are sometimes flagged as
  false positives. Signing helps. You can also submit the file to your
  antivirus vendor, or allow it locally.
- **Blocked zip.** If Windows marks the downloaded zip as blocked, right-click
  it, choose **Properties → Unblock**, and unzip again.

Each Windows user gets their own notes and settings in `%APPDATA%\Ghostpad`.

## 4. Build the installer wizard

The installer is built with [Inno Setup 6](https://jrsoftware.org/isinfo.php),
which is free. The script is [`installer/ghostpad.iss`](../installer/ghostpad.iss).

### One-time setup

Install Inno Setup, either per-user with no admin rights:

```powershell
winget install --id JRSoftware.InnoSetup -e --scope user
```

or with the normal installer from <https://jrsoftware.org/isdl.php>.
`tools\build.ps1` finds `ISCC.exe` in the usual install locations
automatically.

### Build

```powershell
# Recommended: build everything
powershell -ExecutionPolicy Bypass -File tools\build.ps1

# Or by hand, after compiling the exe (section 2):
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" /DAppVersion=1.0.0 installer\ghostpad.iss
```

Output: `dist\installer\Ghostpad-Setup-<version>.exe`, a single file of
about 10 MB that you can share.

### What the wizard does

1. **Install mode.** It offers **Install for me only (recommended)**, which
   needs no admin rights, or **Install for all users**, which asks for admin
   rights.
2. **License.** It shows the MIT license.
3. **Location.** The default is `%LOCALAPPDATA%\Programs\Ghostpad` for me
   only, or `C:\Program Files\Ghostpad` for all users.
4. **Options.** Two optional checkboxes: a desktop shortcut, and starting
   Ghostpad at Windows sign-in.
5. **Install.** It adds a Start-menu shortcut and an entry in **Installed
   apps**, then offers to launch Ghostpad.

Other behaviour:

- **Upgrades:** run a newer `Ghostpad-Setup-*.exe` over the old one. If
  Ghostpad is running, the installer asks you to close it. It also removes
  stale files from the previous version. The fixed `AppId` in the script ties
  versions together, so **never change it**.
- **Uninstall:** use **Settings → Apps → Installed apps → Ghostpad →
  Uninstall**. It removes the app and its shortcuts, then asks whether to
  delete your notes and settings too. The default is to keep them.
- **Minimum OS:** it refuses to install below Windows 10 version 2004, or on
  32-bit Windows.

### Customising the installer

Common changes in `installer/ghostpad.iss`:

| To change | Edit |
| --- | --- |
| Publisher name | `#define AppPublisher` |
| Default install folder | `DefaultDirName` |
| Optional checkboxes | `[Tasks]` and the matching `[Icons]` entries |
| Wizard images | `SetupIconFile`, `WizardSmallImageFile` |
| Output file name | `OutputBaseFilename` |

The version comes from `__version__` in `ghostpad.pyw`, which
`tools\build.ps1` passes as `/DAppVersion=`. Don't hard-code it.

## 5. Silent installs (for IT)

The installer accepts the standard Inno Setup command-line switches:

```powershell
# Current user, no UI, no shortcuts beyond the Start menu
Ghostpad-Setup-1.0.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER

# All users (run elevated), with a desktop shortcut and start-at-sign-in
Ghostpad-Setup-1.0.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /ALLUSERS /TASKS="desktopicon,startup"

# Custom folder and an install log
Ghostpad-Setup-1.0.0.exe /VERYSILENT /CURRENTUSER /DIR="D:\Apps\Ghostpad" /LOG="%TEMP%\ghostpad-install.log"
```

A silent uninstall keeps user data:

```powershell
& "$env:LOCALAPPDATA\Programs\Ghostpad\unins000.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```

For an all-users install, the uninstaller is at
`C:\Program Files\Ghostpad\unins000.exe`.

## 6. Code signing (recommended for distribution)

Unsigned apps trigger SmartScreen warnings and more antivirus false positives.
To sign, you need a code-signing certificate from a certificate authority or
through Azure Trusted Signing. Then use `signtool` from the Windows SDK.

1. Sign the app **before** building the installer:

   ```powershell
   signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a dist\Ghostpad\Ghostpad.exe
   ```

2. Build the installer, then sign it too:

   ```powershell
   signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /a dist\installer\Ghostpad-Setup-1.0.0.exe
   ```

Inno Setup can also sign automatically. See `SignTool=` in its help.
SmartScreen builds reputation over time, so even signed files may warn for
their first downloads.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `python` is not recognized | Reinstall Python with **Add python.exe to PATH**, or use the `py` launcher (`py -m PyInstaller ...`) |
| `No module named PyInstaller` | `python -m pip install -r requirements-dev.txt` |
| `build.ps1 cannot be loaded because running scripts is disabled` | Run it with `powershell -ExecutionPolicy Bypass -File tools\build.ps1` |
| Build script says Inno Setup not found | `winget install --id JRSoftware.InnoSetup -e --scope user`, or ignore it if you only need the zip |
| The exe starts and closes immediately | Run `python ghostpad.pyw` from source to see the traceback |
| No window appears on launch | Ghostpad may be hidden. Press <kbd>Ctrl</kbd>+<kbd>Space</kbd>, or launch it again to bring the running copy forward |
| The status bar shows 🔴 **VISIBLE** | Windows refused capture protection. Check the Windows version, and see [SECURITY.md](../SECURITY.md) |
| Hotkeys don't work | Another app owns the shortcut. The status bar names which ones on launch |
