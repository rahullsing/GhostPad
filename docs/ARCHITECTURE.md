# Ghostpad architecture

Ghostpad is a single module, [`ghostpad.pyw`](../ghostpad.pyw), built only on
the Python standard library. The UI is `tkinter` and all Windows integration
goes through `ctypes`. The `.pyw` extension makes Windows run it with
`pythonw.exe`, so no console window opens.

## Module layout

The file is organised top to bottom in layers. Each layer depends only on the
layers above it.

| Section | Contents |
| --- | --- |
| Constants | App limits, Win32 constants, colour `THEME` |
| Win32 bindings | `ctypes` prototypes with explicit `argtypes`/`restype`, so 64-bit handles are never truncated |
| Pure helpers | File I/O, text stats, settings, geometry parsing. No Tk, fully unit tested |
| Windows integration | `HotkeyListener`, `SingleInstance`, `CaptureShield`, DPI awareness |
| Widgets | `FlatButton`, a hover-aware label button |
| Application | `GhostpadApp`: window chrome, editor, find bar, session, lifecycle |

## Threading model

Tk is single-threaded, and only the main thread ever touches Tk objects.

```text
main thread (Tk mainloop)            hotkey thread
───────────────────────────          ─────────────────────────────
UI, editor, dialogs                  RegisterHotKey(...)
CaptureShield hooks (see below)      GetMessageW loop
_poll_events() every 100 ms  ◄────── queue.SimpleQueue[int] (hotkey ids)
_autosave_loop() every 1.5 s
_shield_loop() every 250 ms
```

`RegisterHotKey` delivers `WM_HOTKEY` to the thread that registered it, so the
listener runs its own message loop. It hands pressed hotkey ids to the main
thread through a thread-safe queue. On exit, `WM_QUIT` is posted to the
listener thread and it unregisters its hotkeys.

## Capture protection: `CaptureShield`

`SetWindowDisplayAffinity` protects only the single top-level window it's
called on. Tk creates separate native windows for popup menus (`#32768`),
message boxes and file dialogs (`#32770`), and the menu drop shadow. Each of
them must be protected before its first frame is composited. The shield uses
three layers:

1. **Pre-show hook (synchronous).** A thread-local `WH_CALLWNDPROC` hook on
   the UI thread watches for `WM_SHOWWINDOW` and for `WM_WINDOWPOSCHANGING`
   with `SWP_SHOWWINDOW`. It protects the window's root ancestor *before*
   Windows shows it. A re-entrancy guard is needed because
   `SetWindowDisplayAffinity` can itself send messages.
2. **WinEvent hook (process-wide).** An out-of-context hook on
   `EVENT_OBJECT_CREATE` and `EVENT_OBJECT_SHOW` catches windows that other
   threads in the process create, such as shell helpers inside the file
   dialog.
3. **Sweep (self-healing).** Every 250 ms, `EnumWindows` checks every visible
   top-level window of the process with `GetWindowDisplayAffinity` and
   repairs any that lost protection. The result drives the status-bar
   indicator.

At startup, the main window is created withdrawn and protected first. Only
then is it shown, so no frame ever reaches a capture unprotected.

`choose_display_affinity()` picks `WDA_EXCLUDEFROMCAPTURE` on build 19041 and
later. On older builds it picks `WDA_MONITOR`, which renders as black.

Hook callbacks never raise. An exception inside a Windows callback would
break message delivery, so every callback swallows its own errors. The sweep
is the safety net for anything a hook missed.

## Window chrome

The window is borderless (`overrideredirect`), so it has no taskbar entry, no
Alt+Tab entry and a compact look. A native menu bar can't be attached to a
borderless window, so Ghostpad draws its own:

- **Title bar:** File, Edit and View menus open through `tk_popup`. The title
  bar also drags the window and holds the pin and close buttons.
- **Status bar:** stats, the protection indicator, opacity controls and a
  resize grip, which replaces the missing native resize edges.

Pack order matters: the title bar, status bar and find bar are packed before
the expanding editor, so they always keep their space.

## Persistence

| What | Where | When |
| --- | --- | --- |
| Untitled note | `%APPDATA%\Ghostpad\scratch.txt` | Every 1.5 s if changed, and on exit |
| Settings | `%APPDATA%\Ghostpad\settings.json` | Every 1.5 s if changed, and on exit |
| Named files | Wherever the user saved them | Only on explicit Save |

- **Atomic writes:** every write goes through `save_document()`. It writes a
  temporary file in the same folder, then `os.replace()`s it, so a crash
  mid-save never truncates the original.
- **Defensive loading:** `load_settings()` ignores unknown keys, clamps values
  into range and falls back to defaults on a missing or corrupt file.
- **Off-screen guard:** a saved window position is only reused if
  `MonitorFromPoint` finds a connected monitor there.
- **Named files are never written silently.** If one has unsaved changes,
  Ghostpad asks before it is closed or replaced.

## Single instance

`SingleInstance` creates the named mutex `Local\Ghostpad.Instance`. If it
already exists, the new process sets the auto-reset named event
`Local\Ghostpad.Show` and exits. The running instance checks that event in
`_poll_events()` and brings itself to the front.

## Testing strategy

Tests are in [`tests/test_ghostpad.py`](../tests/test_ghostpad.py) and use
`unittest`.

| Kind | What it covers |
| --- | --- |
| Pure helpers | File I/O, stats, settings round-trip and corruption handling, geometry parsing |
| Capture shield | Protects hidden windows, auto-protects new top-level windows through the hook, sweep reports no failures |
| App integration | Runs the real `GhostpadApp` against a temporary data folder: session restore, reopening the last file, find, and scroll |

Windows-only tests skip automatically on other platforms. Capture exclusion
was also checked manually by comparing real GDI screen captures with and
without protection. That check isn't automated, because the result depends
on the desktop.
