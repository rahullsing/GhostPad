"""Ghostpad: a private, always-on-top scratchpad for Windows that screen sharing cannot see.

Features
--------
* Hidden from screen capture (screen sharing, recording, screenshots), including its
  menus and dialogs, with a live indicator that verifies protection.
* Global hotkeys work while another app (e.g. PowerPoint) has focus:
  Ctrl+Space shows/hides the window, Ctrl+Alt+Up/Down scrolls the notes.
* Session restore: untitled notes autosave, and window position, size, zoom,
  opacity and the last opened file come back on the next launch.
* Find bar (Ctrl+F), single-instance launch, borderless dark UI.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import queue
import re
import sys
import tempfile
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import Any

IS_WINDOWS = sys.platform == "win32"

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
__version__ = "1.0.0"  # keep in sync with pyproject.toml and CHANGELOG.md

APP_NAME = "Ghostpad"
UNTITLED = "Untitled"

WDA_NONE = 0x00
WDA_MONITOR = 0x01  # content shows as a black box (all supported Windows)
WDA_EXCLUDEFROMCAPTURE = 0x11  # window is omitted entirely (Windows 10 2004+)
EXCLUDE_MIN_BUILD = 19041  # Windows 10 version 2004
WH_CALLWNDPROC = 4
WM_SHOWWINDOW = 0x0018
WM_WINDOWPOSCHANGING = 0x0046
SWP_SHOWWINDOW = 0x0040
GA_ROOT = 2
EVENT_OBJECT_CREATE = 0x8000
EVENT_OBJECT_SHOW = 0x8002
WINEVENT_OUTOFCONTEXT = 0x0000
OBJID_WINDOW = 0
SHIELD_SWEEP_MS = 250
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_SPACE = 0x20
VK_UP = 0x26
VK_DOWN = 0x28
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_TOGGLE = 1
HOTKEY_SCROLL_UP = 2
HOTKEY_SCROLL_DOWN = 3
SCROLL_LINES = 3
ERROR_ALREADY_EXISTS = 183
MONITOR_DEFAULTTONULL = 0
INSTANCE_MUTEX = r"Local\Ghostpad.Instance"
INSTANCE_SHOW_EVENT = r"Local\Ghostpad.Show"
AUTOSAVE_MS = 1500
SETTINGS_FILE = "settings.json"
SCRATCH_FILE = "scratch.txt"
ICON_FILE = "assets/ghostpad.ico"
HOTKEY_NAMES = {HOTKEY_TOGGLE: "Ctrl+Space", HOTKEY_SCROLL_UP: "Ctrl+Alt+Up", HOTKEY_SCROLL_DOWN: "Ctrl+Alt+Down"}

DEFAULT_SIZE = (560, 380)
MIN_SIZE = (360, 220)
DEFAULT_FONT_SIZE = 12
FONT_SIZE_RANGE = (6, 72)
DEFAULT_ALPHA = 0.94
ALPHA_RANGE = (0.2, 1.0)
ALPHA_STEP = 0.05
STATUS_FLASH_MS = 2500
HOTKEY_POLL_MS = 100

FILE_TYPES = [("Text files", "*.txt"), ("Markdown", "*.md"), ("All files", "*.*")]

ICON_FONT = "Segoe MDL2 Assets"
ICON_CLOSE = ""
ICON_PIN = ""

THEME = {
    "border": "#2d3138",
    "chrome_bg": "#1b1d22",
    "chrome_fg": "#e6e9ef",
    "muted_fg": "#8b93a1",
    "hover_bg": "#2a2e35",
    "accent": "#4c8dff",
    "danger": "#c42b1c",
    "editor_bg": "#16181c",
    "editor_fg": "#e6e9ef",
    "caret": "#f8fafc",
    "select_bg": "#264f78",
    "menu_bg": "#202329",
    "menu_active": "#2f343c",
    "thumb": "#3a3f47",
    "thumb_hover": "#4b515b",
    "ok": "#3fb950",
    "warn": "#d29922",
    "bad": "#f85149",
    "match_bg": "#4a3f1c",
    "match_current_bg": "#9e6a03",
    "entry_bg": "#24272e",
}

# --------------------------------------------------------------------------- #
# Win32 bindings (explicit prototypes so 64-bit handles are never truncated)
# --------------------------------------------------------------------------- #
if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    LRESULT = ctypes.c_ssize_t
    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    WINEVENTPROC = ctypes.WINFUNCTYPE(
        None,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.HWND,
        wintypes.LONG,
        wintypes.LONG,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    class CWPSTRUCT(ctypes.Structure):
        _fields_ = [
            ("lParam", wintypes.LPARAM),
            ("wParam", wintypes.WPARAM),
            ("message", wintypes.UINT),
            ("hwnd", wintypes.HWND),
        ]

    class WINDOWPOS(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("hwndInsertAfter", wintypes.HWND),
            ("x", ctypes.c_int),
            ("y", ctypes.c_int),
            ("cx", ctypes.c_int),
            ("cy", ctypes.c_int),
            ("flags", wintypes.UINT),
        ]

    def _proto(func, restype, *argtypes):
        func.restype = restype
        func.argtypes = argtypes
        return func

    _proto(user32.GetParent, wintypes.HWND, wintypes.HWND)
    _proto(user32.GetAncestor, wintypes.HWND, wintypes.HWND, wintypes.UINT)
    _proto(user32.IsWindow, wintypes.BOOL, wintypes.HWND)
    _proto(user32.IsWindowVisible, wintypes.BOOL, wintypes.HWND)
    _proto(user32.SetWindowDisplayAffinity, wintypes.BOOL, wintypes.HWND, wintypes.DWORD)
    _proto(user32.GetWindowDisplayAffinity, wintypes.BOOL, wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    _proto(user32.GetWindowThreadProcessId, wintypes.DWORD, wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    _proto(user32.EnumWindows, wintypes.BOOL, WNDENUMPROC, wintypes.LPARAM)
    _proto(user32.SetWindowsHookExW, wintypes.HHOOK, ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
    _proto(user32.CallNextHookEx, LRESULT, wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    _proto(user32.UnhookWindowsHookEx, wintypes.BOOL, wintypes.HHOOK)
    _proto(
        user32.SetWinEventHook,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HMODULE,
        WINEVENTPROC,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    _proto(user32.UnhookWinEvent, wintypes.BOOL, wintypes.HANDLE)
    _proto(user32.RegisterHotKey, wintypes.BOOL, wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
    _proto(user32.UnregisterHotKey, wintypes.BOOL, wintypes.HWND, ctypes.c_int)
    _proto(user32.GetMessageW, wintypes.BOOL, ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
    _proto(user32.PostThreadMessageW, wintypes.BOOL, wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    _proto(user32.MonitorFromPoint, wintypes.HANDLE, wintypes.POINT, wintypes.DWORD)
    _proto(kernel32.GetCurrentThreadId, wintypes.DWORD)
    _proto(kernel32.GetCurrentProcessId, wintypes.DWORD)
    _proto(kernel32.CreateMutexW, wintypes.HANDLE, wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    _proto(kernel32.CreateEventW, wintypes.HANDLE, wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR)
    _proto(kernel32.SetEvent, wintypes.BOOL, wintypes.HANDLE)
    _proto(kernel32.WaitForSingleObject, wintypes.DWORD, wintypes.HANDLE, wintypes.DWORD)
    _proto(kernel32.CloseHandle, wintypes.BOOL, wintypes.HANDLE)


# --------------------------------------------------------------------------- #
# Pure helpers (unit tested)
# --------------------------------------------------------------------------- #
def load_document(path: str | os.PathLike[str]) -> str:
    """Read a UTF-8 text file (a leading BOM is ignored)."""
    return Path(path).read_text(encoding="utf-8-sig")


def save_document(path: str | os.PathLike[str], content: str) -> None:
    """Write ``content`` atomically so a failed save never truncates the file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_name, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def get_text_stats(text: str) -> dict[str, int]:
    """Return character, word and line counts, ignoring trailing newlines."""
    body = text.rstrip("\n")
    return {
        "characters": len(body),
        "words": len(body.split()),
        "lines": body.count("\n") + 1,
    }


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


_GEOMETRY_RE = re.compile(r"^(\d+)x(\d+)([+-]-?\d+)([+-]-?\d+)$")


def parse_geometry(geometry: str | None) -> tuple[int, int, int, int] | None:
    """Parse a Tk ``WxH+X+Y`` string (Tk writes negative offsets as ``+-N``)."""
    match = _GEOMETRY_RE.match(geometry or "")
    if not match:
        return None
    width, height, x, y = (int(g.replace("+-", "-")) for g in match.groups())
    return (width, height, x, y) if width > 0 and height > 0 else None


@dataclass
class Settings:
    """User preferences persisted between sessions."""

    geometry: str | None = None
    font_size: int = DEFAULT_FONT_SIZE
    alpha: float = DEFAULT_ALPHA
    wrap: bool = True
    topmost: bool = True
    last_path: str | None = None

    def normalized(self) -> Settings:
        """Return a copy with every value coerced into its valid range."""
        return Settings(
            geometry=self.geometry if parse_geometry(self.geometry) else None,
            font_size=int(clamp(int(self.font_size), *FONT_SIZE_RANGE)),
            alpha=round(clamp(float(self.alpha), *ALPHA_RANGE), 2),
            wrap=bool(self.wrap),
            topmost=bool(self.topmost),
            last_path=str(self.last_path) if self.last_path else None,
        )


def load_settings(path: str | os.PathLike[str]) -> Settings:
    """Load settings, falling back to defaults for a missing or corrupt file."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()
    known = {f.name for f in fields(Settings)}
    try:
        return Settings(**{k: v for k, v in raw.items() if k in known}).normalized()
    except (TypeError, ValueError):
        return Settings()


def save_settings(path: str | os.PathLike[str], settings: Settings) -> None:
    save_document(path, json.dumps(asdict(settings), indent=2))


def default_data_dir() -> Path:
    """Per-user folder for settings and the autosaved scratch note."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return Path(base) / APP_NAME


def resource_path(relative: str) -> Path:
    """Locate a bundled resource both from source and inside a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


# --------------------------------------------------------------------------- #
# Windows integration
# --------------------------------------------------------------------------- #
def enable_dpi_awareness() -> None:
    """Render crisp text on high-DPI displays instead of blurry bitmap scaling."""
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware
    except (AttributeError, OSError):
        with contextlib.suppress(AttributeError, OSError):
            user32.SetProcessDPIAware()


def is_on_screen(x: int, y: int) -> bool:
    """True if the point lies on a connected monitor (guards against unplugged screens)."""
    if not IS_WINDOWS:
        return True
    return bool(user32.MonitorFromPoint(wintypes.POINT(x, y), MONITOR_DEFAULTTONULL))


class HotkeyListener:
    """System-wide hotkeys served by a background thread with its own message loop.

    ``bindings`` maps an id to ``(modifiers, virtual_key, allow_repeat)``. Pressed
    ids are pushed onto :attr:`events`, which the Tk thread polls; Tk is never
    touched from the listener thread.
    """

    def __init__(self, bindings: dict[int, tuple[int, int, bool]]) -> None:
        self._bindings = bindings
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self.events: queue.SimpleQueue[int] = queue.SimpleQueue()
        self.registered: list[int] = []
        self.failed: list[int] = []
        self._thread = threading.Thread(target=self._run, name="global-hotkeys", daemon=True)

    def start(self) -> None:
        self._thread.start()
        self._ready.wait(timeout=1.0)

    def stop(self) -> None:
        if self._thread_id and self._thread.is_alive():
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        for hotkey_id, (modifiers, key, allow_repeat) in self._bindings.items():
            flags = modifiers if allow_repeat else modifiers | MOD_NOREPEAT
            if user32.RegisterHotKey(None, hotkey_id, flags, key):
                self.registered.append(hotkey_id)
            else:
                self.failed.append(hotkey_id)
        self._ready.set()
        if not self.registered:
            return
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    self.events.put(int(msg.wParam))
        finally:
            for hotkey_id in self.registered:
                user32.UnregisterHotKey(None, hotkey_id)


class SingleInstance:
    """Ensures one Ghostpad per user session; later launches just reveal it."""

    def __init__(self) -> None:
        self._mutex = None
        self.show_event = None
        self.is_primary = True
        if not IS_WINDOWS:
            return
        self._mutex = kernel32.CreateMutexW(None, False, INSTANCE_MUTEX)
        self.is_primary = ctypes.get_last_error() != ERROR_ALREADY_EXISTS
        # Auto-reset event: a second launch sets it, the primary instance consumes it.
        self.show_event = kernel32.CreateEventW(None, False, False, INSTANCE_SHOW_EVENT)

    def signal_primary(self) -> None:
        if self.show_event:
            kernel32.SetEvent(self.show_event)

    def show_requested(self) -> bool:
        return bool(self.show_event) and kernel32.WaitForSingleObject(self.show_event, 0) == 0


def choose_display_affinity(windows_build: int) -> int:
    """Best capture protection the OS supports: omit the window, else black it out."""
    return WDA_EXCLUDEFROMCAPTURE if windows_build >= EXCLUDE_MIN_BUILD else WDA_MONITOR


class CaptureShield:
    """Keeps every window this process shows out of screen captures.

    ``SetWindowDisplayAffinity`` only covers the window it is applied to, and Tk
    creates separate native windows for menus, message boxes and file dialogs.
    The shield therefore protects windows in three layers:

    1. A thread-local ``WH_CALLWNDPROC`` hook on the UI thread applies protection
       synchronously when Windows is about to show a window, before its first
       frame is composed.
    2. A process-wide WinEvent hook catches windows created by other threads
       (e.g. shell helpers inside the file dialog).
    3. A periodic :meth:`sweep` re-verifies every visible window and repairs any
       whose protection was lost.
    """

    def __init__(self, affinity: int) -> None:
        self.affinity = affinity
        self._pid = kernel32.GetCurrentProcessId()
        self._call_hook = None
        self._event_hooks: list[int] = []
        self._in_hook = False
        self._enum_hwnds: list[int] = []
        # ctypes callbacks must stay referenced for as long as Windows may call them.
        self._hook_proc = HOOKPROC(self._on_call_wnd_proc)
        self._event_proc = WINEVENTPROC(self._on_win_event)
        self._enum_proc = WNDENUMPROC(self._on_enum_window)

    # ------------------------------------------------------------ lifecycle
    def install(self) -> bool:
        """Install hooks on the calling (UI) thread. Returns True if all succeeded."""
        self._call_hook = user32.SetWindowsHookExW(WH_CALLWNDPROC, self._hook_proc, None, kernel32.GetCurrentThreadId())
        for event in (EVENT_OBJECT_CREATE, EVENT_OBJECT_SHOW):
            handle = user32.SetWinEventHook(event, event, None, self._event_proc, self._pid, 0, WINEVENT_OUTOFCONTEXT)
            if handle:
                self._event_hooks.append(handle)
        return bool(self._call_hook) and len(self._event_hooks) == 2

    def uninstall(self) -> None:
        if self._call_hook:
            user32.UnhookWindowsHookEx(self._call_hook)
            self._call_hook = None
        for handle in self._event_hooks:
            user32.UnhookWinEvent(handle)
        self._event_hooks.clear()

    # ----------------------------------------------------------- protection
    def is_protected(self, hwnd: int | None) -> bool:
        current = wintypes.DWORD()
        return bool(
            hwnd and user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(current)) and current.value == self.affinity
        )

    def protect(self, hwnd: int | None) -> bool:
        """Apply protection to a top-level window. Returns True if it is protected."""
        if not hwnd or not user32.IsWindow(hwnd):
            return False
        if self.is_protected(hwnd):
            return True
        return bool(user32.SetWindowDisplayAffinity(hwnd, self.affinity))

    def sweep(self) -> list[int]:
        """Protect every visible top-level window of this process.

        Returns the handles that could not be protected.
        """
        self._enum_hwnds = []
        user32.EnumWindows(self._enum_proc, 0)
        return [hwnd for hwnd in self._enum_hwnds if not self.protect(hwnd)]

    def _protect_root(self, hwnd: int | None) -> None:
        if not hwnd or self._in_hook:
            return
        self._in_hook = True  # SetWindowDisplayAffinity may send messages: avoid re-entry
        try:
            self.protect(user32.GetAncestor(hwnd, GA_ROOT) or hwnd)
        finally:
            self._in_hook = False

    # ------------------------------------------------------------ callbacks
    @staticmethod
    def _is_about_to_show(msg: CWPSTRUCT) -> bool:
        if msg.message == WM_SHOWWINDOW:
            return bool(msg.wParam)
        if msg.message == WM_WINDOWPOSCHANGING and msg.lParam:
            return bool(WINDOWPOS.from_address(msg.lParam).flags & SWP_SHOWWINDOW)
        return False

    def _on_call_wnd_proc(self, code: int, wparam: int, lparam: int) -> int:
        # A hook must never raise: an exception here would break message delivery.
        try:
            if code >= 0:
                msg = CWPSTRUCT.from_address(lparam)
                if self._is_about_to_show(msg):
                    self._protect_root(msg.hwnd)
        except Exception:  # deliberately broad, see above
            pass
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _on_win_event(self, _hook, _event, hwnd, id_object, _id_child, _thread, _time) -> None:
        try:
            if id_object == OBJID_WINDOW:
                self._protect_root(hwnd)
        except Exception:  # callbacks invoked by Windows must never raise
            pass

    def _on_enum_window(self, hwnd: int, _lparam: int) -> bool:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == self._pid and user32.IsWindowVisible(hwnd):
            self._enum_hwnds.append(hwnd)
        return True


# --------------------------------------------------------------------------- #
# Widgets
# --------------------------------------------------------------------------- #
class FlatButton(tk.Label):
    """A flat, hover-highlighted button that looks consistent on Windows."""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], object] | None = None,
        *,
        bg: str,
        fg: str,
        hover_bg: str,
        hover_fg: str | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("cursor", "hand2")
        super().__init__(master, text=text, bg=bg, fg=fg, **kwargs)
        self.command: Callable[[], object] | None = command
        self._colors = {"bg": bg, "fg": fg, "hover_bg": hover_bg, "hover_fg": hover_fg or fg}
        self.bind("<Enter>", lambda _e: self._paint(hover=True))
        self.bind("<Leave>", lambda _e: self._paint(hover=False))
        self.bind("<ButtonRelease-1>", self._on_click)

    def set_fg(self, fg: str) -> None:
        self._colors["fg"] = fg
        self.configure(fg=fg)

    def _paint(self, hover: bool) -> None:
        c = self._colors
        self.configure(bg=c["hover_bg"] if hover else c["bg"], fg=c["hover_fg"] if hover else c["fg"])

    def _on_click(self, event: tk.Event) -> None:
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        if inside and self.command is not None:
            self.command()


@dataclass
class DocumentState:
    path: Path | None = None
    font_size: int = DEFAULT_FONT_SIZE
    alpha: float = DEFAULT_ALPHA
    visible: bool = True

    @property
    def display_name(self) -> str:
        return self.path.name if self.path else UNTITLED


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #
class GhostpadApp:
    def __init__(
        self,
        root: tk.Tk | None = None,
        *,
        data_dir: str | os.PathLike[str] | None = None,
        instance: SingleInstance | None = None,
    ) -> None:
        self.root = root or tk.Tk()
        # Stay hidden until capture protection is confirmed, so not even the first
        # frame of the window can reach a screen share.
        self.root.withdraw()
        self.shield: CaptureShield | None = None
        self._shield_hooks_ok = False
        self._shield_level = ""
        self._shield_detail = ""
        self._hwnd = 0
        if IS_WINDOWS:
            self.shield = CaptureShield(choose_display_affinity(sys.getwindowsversion().build))
            self._shield_hooks_ok = self.shield.install()
        self.state = DocumentState()
        self._data_dir = Path(data_dir) if data_dir else default_data_dir()
        self._settings_path = self._data_dir / SETTINGS_FILE
        self._scratch_path = self._data_dir / SCRATCH_FILE
        self.settings = load_settings(self._settings_path)
        self.state.font_size = self.settings.font_size
        self.state.alpha = self.settings.alpha
        self._instance = instance
        self._last_scratch: str | None = None
        self._last_settings: Settings | None = None
        self._autosave_failed = False
        self._matches: list[tuple[str, str]] = []
        self._match_index = -1
        self._scale = self.root.winfo_fpixels("1i") / 96.0
        self._flash_job: str | None = None
        self._drag_offset = (0, 0)
        self._resize_origin = (0, 0, 0, 0)

        self.topmost_var = tk.BooleanVar(self.root, value=self.settings.topmost)
        self.wrap_var = tk.BooleanVar(self.root, value=self.settings.wrap)

        self.ui_font = tkfont.Font(self.root, family="Segoe UI", size=9)
        self.editor_font = tkfont.Font(self.root, family="Consolas", size=self.state.font_size)
        has_icons = ICON_FONT in tkfont.families(self.root)
        self.icon_font = tkfont.Font(self.root, family=ICON_FONT if has_icons else "Segoe UI", size=9)
        self._icons = {"close": ICON_CLOSE, "pin": ICON_PIN} if has_icons else {"close": "✕", "pin": "Pin"}

        self._configure_window()
        self._configure_styles()
        self._build_menus()
        self._build_title_bar()
        self._build_status_bar()  # packed before the editor so it always keeps its row
        self._build_editor()
        self._build_find_bar()
        self._bind_shortcuts()

        self._restore_session()
        self._update_title()
        self._refresh_status()
        self._reveal()

        self.hotkeys: HotkeyListener | None = None
        if IS_WINDOWS:
            self.hotkeys = HotkeyListener(
                {
                    HOTKEY_TOGGLE: (MOD_CONTROL, VK_SPACE, False),
                    HOTKEY_SCROLL_UP: (MOD_CONTROL | MOD_ALT, VK_UP, True),
                    HOTKEY_SCROLL_DOWN: (MOD_CONTROL | MOD_ALT, VK_DOWN, True),
                }
            )
            self.hotkeys.start()
            if self.hotkeys.failed:
                taken = ", ".join(HOTKEY_NAMES[h] for h in self.hotkeys.failed)
                self.flash(f"{taken} already used by another app")
        self.root.after(HOTKEY_POLL_MS, self._poll_events)
        self.root.after(AUTOSAVE_MS, self._autosave_loop)

    # ----------------------------------------------------------------- setup
    def _px(self, value: float) -> int:
        return round(value * self._scale)

    def _configure_window(self) -> None:
        min_w, min_h = (self._px(v) for v in MIN_SIZE)
        saved = parse_geometry(self.settings.geometry)
        if saved and is_on_screen(saved[2] + self._px(40), saved[3] + self._px(10)):
            width, height, x, y = max(saved[0], min_w), max(saved[1], min_h), saved[2], saved[3]
        else:  # first launch, or the saved monitor is no longer connected
            width, height = (self._px(v) for v in DEFAULT_SIZE)
            x = y = self._px(120)
        self.root.title(APP_NAME)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(min_w, min_h)
        icon = resource_path(ICON_FILE)
        if icon.is_file():
            with contextlib.suppress(tk.TclError):
                self.root.iconbitmap(default=str(icon))  # also used by dialogs
        self.root.configure(bg=THEME["border"])  # shows as a 1px border around the container
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", self.settings.topmost)
        self.root.attributes("-alpha", self.state.alpha)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self.container = tk.Frame(self.root, bg=THEME["editor_bg"])
        self.container.pack(fill="both", expand=True, padx=1, pady=1)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        name = "Ghostpad.Vertical.TScrollbar"
        # Slim scrollbar: trough + thumb only, no arrow buttons.
        thumb = ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})
        trough = ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [thumb]})
        style.layout(name, [trough])  # type: ignore[list-item]  # typeshed's layout spec is too strict
        style.configure(
            name,
            background=THEME["thumb"],
            troughcolor=THEME["editor_bg"],
            bordercolor=THEME["editor_bg"],
            lightcolor=THEME["thumb"],
            darkcolor=THEME["thumb"],
            gripcount=0,
            arrowsize=self._px(10),
        )
        style.map(name, background=[("pressed", THEME["thumb_hover"]), ("active", THEME["thumb_hover"])])

    def _new_menu(self) -> tk.Menu:
        return tk.Menu(
            self.root,
            tearoff=False,
            bg=THEME["menu_bg"],
            fg=THEME["chrome_fg"],
            activebackground=THEME["menu_active"],
            activeforeground=THEME["chrome_fg"],
            selectcolor=THEME["chrome_fg"],
            bd=0,
            font=self.ui_font,
        )

    def _build_menus(self) -> None:
        self.file_menu = m = self._new_menu()
        m.add_command(label="New", accelerator="Ctrl+N", command=self.new_file)
        m.add_command(label="Open…", accelerator="Ctrl+O", command=self.open_file)
        m.add_separator()
        m.add_command(label="Save", accelerator="Ctrl+S", command=self.save)
        m.add_command(label="Save As…", accelerator="Ctrl+Shift+S", command=self.save_as)
        m.add_separator()
        m.add_command(label="Exit", command=self.quit)

        self.edit_menu = m = self._new_menu()
        m.add_command(label="Undo", accelerator="Ctrl+Z", command=lambda: self._text_event("<<Undo>>"))
        m.add_command(label="Redo", accelerator="Ctrl+Y", command=lambda: self._text_event("<<Redo>>"))
        m.add_separator()
        m.add_command(label="Cut", accelerator="Ctrl+X", command=lambda: self._text_event("<<Cut>>"))
        m.add_command(label="Copy", accelerator="Ctrl+C", command=lambda: self._text_event("<<Copy>>"))
        m.add_command(label="Paste", accelerator="Ctrl+V", command=lambda: self._text_event("<<Paste>>"))
        m.add_separator()
        m.add_command(label="Select All", accelerator="Ctrl+A", command=self.select_all)
        m.add_command(label="Clear", accelerator="Ctrl+L", command=self.clear)
        m.add_separator()
        m.add_command(label="Find\u2026", accelerator="Ctrl+F", command=self.open_find)
        m.add_command(label="Find Next", accelerator="F3", command=lambda: self.find_step(+1))
        m.add_command(label="Find Previous", accelerator="Shift+F3", command=lambda: self.find_step(-1))

        self.view_menu = m = self._new_menu()
        m.add_command(label="Zoom In", accelerator="Ctrl++", command=lambda: self.change_font_size(+1))
        m.add_command(label="Zoom Out", accelerator="Ctrl+-", command=lambda: self.change_font_size(-1))
        m.add_command(label="Reset Zoom", accelerator="Ctrl+0", command=self.reset_font_size)
        m.add_separator()
        m.add_command(label="More Opaque", command=lambda: self.change_opacity(+ALPHA_STEP))
        m.add_command(label="More Transparent", command=lambda: self.change_opacity(-ALPHA_STEP))
        m.add_separator()
        m.add_checkbutton(label="Word Wrap", variable=self.wrap_var, command=self._apply_wrap)
        m.add_checkbutton(label="Always on Top", variable=self.topmost_var, command=self._apply_topmost)
        m.add_command(label="Hide", accelerator="Ctrl+Space", command=self.toggle_visibility)
        m.add_separator()
        m.add_command(label="Scroll Notes Up", accelerator="Ctrl+Alt+Up", command=lambda: self.scroll_notes(-1))
        m.add_command(label="Scroll Notes Down", accelerator="Ctrl+Alt+Down", command=lambda: self.scroll_notes(+1))

    def _build_title_bar(self) -> None:
        bg, fg, hover = THEME["chrome_bg"], THEME["chrome_fg"], THEME["hover_bg"]
        bar = tk.Frame(self.container, bg=bg)
        bar.pack(side="top", fill="x")

        # Menus live inside the custom title bar: a native menubar cannot be
        # attached to a borderless (overrideredirect) window correctly.
        self._menu_buttons: dict[str, FlatButton] = {}
        for label, menu in (("File", self.file_menu), ("Edit", self.edit_menu), ("View", self.view_menu)):
            btn = FlatButton(
                bar,
                label,
                bg=bg,
                fg=fg,
                hover_bg=hover,
                font=self.ui_font,
                padx=self._px(10),
                pady=self._px(6),
                cursor="arrow",
            )
            btn.command = lambda b=btn, m=menu: self._show_menu(m, b)
            btn.pack(side="left")
            self._menu_buttons[label] = btn

        icon_opts: dict[str, Any] = {"font": self.icon_font, "width": 4, "pady": self._px(6)}
        self.close_btn = FlatButton(
            bar,
            self._icons["close"],
            self.quit,
            bg=bg,
            fg=fg,
            hover_bg=THEME["danger"],
            hover_fg="#ffffff",
            **icon_opts,
        )
        self.close_btn.pack(side="right", fill="y")
        self.pin_btn = FlatButton(bar, self._icons["pin"], self._toggle_pin, bg=bg, fg=fg, hover_bg=hover, **icon_opts)
        self.pin_btn.pack(side="right", fill="y")
        self._apply_topmost()

        self.title_label = tk.Label(bar, bg=bg, fg=THEME["muted_fg"], font=self.ui_font, anchor="center")
        self.title_label.pack(side="left", fill="both", expand=True)

        for widget in (bar, self.title_label):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)

        tk.Frame(self.container, bg=THEME["border"], height=1).pack(side="top", fill="x")

    def _build_status_bar(self) -> None:
        bg, fg, muted, hover = THEME["chrome_bg"], THEME["chrome_fg"], THEME["muted_fg"], THEME["hover_bg"]
        bar = tk.Frame(self.container, bg=bg)
        bar.pack(side="bottom", fill="x")
        tk.Frame(self.container, bg=THEME["border"], height=1).pack(side="bottom", fill="x")

        # Resize grip: a borderless window has no native resize edges.
        size = self._px(14)
        grip = tk.Canvas(bar, width=size, height=size, bg=bg, highlightthickness=0, cursor="size_nw_se")
        dot, gap = max(2, self._px(2)), self._px(4)
        for row in range(3):
            for col in range(3 - row):
                x = size - (col + 1) * gap
                y = size - (row + 1) * gap
                grip.create_rectangle(x, y, x + dot, y + dot, fill=muted, outline="")
        grip.pack(side="right", anchor="se", padx=(self._px(4), self._px(2)), pady=self._px(2))
        grip.bind("<ButtonPress-1>", self._resize_start)
        grip.bind("<B1-Motion>", self._resize_move)

        small: dict[str, Any] = {"font": self.ui_font, "padx": self._px(6), "pady": self._px(2)}
        FlatButton(bar, "+", lambda: self.change_opacity(+ALPHA_STEP), bg=bg, fg=fg, hover_bg=hover, **small).pack(
            side="right"
        )
        self.opacity_label = tk.Label(bar, bg=bg, fg=muted, font=self.ui_font)
        self.opacity_label.pack(side="right")
        FlatButton(bar, "−", lambda: self.change_opacity(-ALPHA_STEP), bg=bg, fg=fg, hover_bg=hover, **small).pack(
            side="right"
        )

        # Live capture-protection indicator; click it for details.
        self.shield_label = tk.Label(bar, bg=bg, fg=muted, font=self.ui_font, padx=self._px(8), cursor="hand2")
        self.shield_label.pack(side="right")
        self.shield_label.bind("<ButtonRelease-1>", lambda _e: self.flash(self._shield_detail))

        self.status_label = tk.Label(
            bar, bg=bg, fg=muted, font=self.ui_font, anchor="w", padx=self._px(10), pady=self._px(4)
        )
        self.status_label.pack(side="left", fill="x", expand=True)
        self._update_opacity_label()

    def _build_editor(self) -> None:
        self.editor_frame = frame = tk.Frame(self.container, bg=THEME["editor_bg"])
        frame.pack(side="top", fill="both", expand=True)

        self.text = tk.Text(
            frame,
            bg=THEME["editor_bg"],
            fg=THEME["editor_fg"],
            insertbackground=THEME["caret"],
            selectbackground=THEME["select_bg"],
            selectforeground=THEME["editor_fg"],
            inactiveselectbackground=THEME["select_bg"],
            font=self.editor_font,
            wrap="word" if self.wrap_var.get() else "none",
            undo=True,
            autoseparators=True,
            maxundo=-1,
            bd=0,
            relief="flat",
            highlightthickness=0,
            padx=self._px(14),
            pady=self._px(10),
            spacing1=2,
            spacing3=2,
        )
        scrollbar = ttk.Scrollbar(
            frame, orient="vertical", command=self.text.yview, style="Ghostpad.Vertical.TScrollbar"
        )
        self.text.configure(yscrollcommand=scrollbar.set)
        # Pack the scrollbar first so the expanding Text never squeezes it out.
        scrollbar.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

        self.text.bind("<<Modified>>", lambda _e: self._update_title())
        for sequence in ("<KeyRelease>", "<ButtonRelease-1>"):
            self.text.bind(sequence, lambda _e: self._refresh_status(), add="+")

    def _bind_shortcuts(self) -> None:
        # Editor-only shortcuts must not fire while typing in the find box.
        for sequence, editor_action in {"<Control-a>": self.select_all, "<Control-l>": self.clear}.items():
            self.text.bind(sequence, self._make_handler(editor_action))

        shortcuts: dict[str, Callable[[], object]] = {
            "<Control-n>": self.new_file,
            "<Control-o>": self.open_file,
            "<Control-s>": self.save,
            "<Control-S>": self.save_as,  # Ctrl+Shift+S
            "<Control-f>": self.open_find,
            "<F3>": lambda: self.find_step(+1),
            "<Shift-F3>": lambda: self.find_step(-1),
            "<Control-plus>": lambda: self.change_font_size(+1),
            "<Control-equal>": lambda: self.change_font_size(+1),
            "<Control-KP_Add>": lambda: self.change_font_size(+1),
            "<Control-minus>": lambda: self.change_font_size(-1),
            "<Control-KP_Subtract>": lambda: self.change_font_size(-1),
            "<Control-0>": self.reset_font_size,
            "<Alt-f>": lambda: self._show_menu(self.file_menu, self._menu_buttons["File"]),
            "<Alt-e>": lambda: self._show_menu(self.edit_menu, self._menu_buttons["Edit"]),
            "<Alt-v>": lambda: self._show_menu(self.view_menu, self._menu_buttons["View"]),
        }
        for sequence, action in shortcuts.items():
            handler = self._make_handler(action)
            # Bind on the Text widget so its built-in class bindings (e.g. Ctrl+O
            # inserting a newline) are suppressed, and on root for other widgets.
            self.text.bind(sequence, handler)
            self.root.bind(sequence, handler)
        self.text.bind("<Control-MouseWheel>", self._on_ctrl_wheel)

    @staticmethod
    def _make_handler(action: Callable[[], object]) -> Callable[[tk.Event], str]:
        def handler(_event: tk.Event) -> str:
            action()
            return "break"

        return handler

    def _focus_editor(self) -> None:
        self.root.focus_force()
        self.text.focus_set()

    def _build_find_bar(self) -> None:
        bg, fg, muted, hover = THEME["chrome_bg"], THEME["chrome_fg"], THEME["muted_fg"], THEME["hover_bg"]
        self.find_bar = bar = tk.Frame(self.container, bg=bg)
        self.find_separator = tk.Frame(self.container, bg=THEME["border"], height=1)

        self.find_var = tk.StringVar(self.root)
        self.find_entry = tk.Entry(
            bar,
            textvariable=self.find_var,
            font=self.ui_font,
            bg=THEME["entry_bg"],
            fg=fg,
            insertbackground=THEME["caret"],
            selectbackground=THEME["select_bg"],
            selectforeground=fg,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=THEME["border"],
            highlightcolor=THEME["accent"],
        )
        self.find_entry.pack(
            side="left", fill="x", expand=True, padx=(self._px(10), self._px(6)), pady=self._px(5), ipady=self._px(3)
        )
        self.find_count = tk.Label(bar, bg=bg, fg=muted, font=self.ui_font, width=10)
        self.find_count.pack(side="left")
        small: dict[str, Any] = {"font": self.ui_font, "padx": self._px(7), "pady": self._px(2)}
        FlatButton(bar, "\u2191", lambda: self.find_step(-1), bg=bg, fg=fg, hover_bg=hover, **small).pack(side="left")
        FlatButton(bar, "\u2193", lambda: self.find_step(+1), bg=bg, fg=fg, hover_bg=hover, **small).pack(side="left")
        FlatButton(
            bar,
            self._icons["close"],
            self.close_find,
            bg=bg,
            fg=fg,
            hover_bg=hover,
            font=self.icon_font,
            padx=self._px(8),
            pady=self._px(2),
        ).pack(side="left", padx=(0, self._px(4)))

        self.find_var.trace_add("write", lambda *_: self._update_matches(jump=True))
        self.find_entry.bind("<Return>", self._make_handler(lambda: self.find_step(+1)))
        self.find_entry.bind("<Shift-Return>", self._make_handler(lambda: self.find_step(-1)))
        self.find_entry.bind("<Escape>", self._make_handler(self.close_find))
        self.text.tag_configure("match", background=THEME["match_bg"])
        self.text.tag_configure("match_current", background=THEME["match_current_bg"], foreground="#ffffff")
        self.text.tag_raise("match_current")
        self.text.tag_raise("sel")

    # -------------------------------------------------------------- session
    def _restore_session(self) -> None:
        """Reopen the last file, or the autosaved untitled note."""
        last = self.settings.last_path
        if last and Path(last).is_file():
            try:
                self._load_into_editor(load_document(last), Path(last))
                return
            except (OSError, UnicodeDecodeError):
                pass
        try:
            content = load_document(self._scratch_path)
        except (OSError, UnicodeDecodeError):
            return
        self._load_into_editor(content, None)
        self._last_scratch = content

    def _current_settings(self) -> Settings:
        return Settings(
            geometry=self.root.geometry(),
            font_size=self.state.font_size,
            alpha=self.state.alpha,
            wrap=self.wrap_var.get(),
            topmost=self.topmost_var.get(),
            last_path=str(self.state.path) if self.state.path else None,
        )

    def _persist(self) -> None:
        """Autosave the untitled note and settings if they changed."""
        try:
            if self.state.path is None:
                content = self.text.get("1.0", "end-1c")
                if content != self._last_scratch:
                    save_document(self._scratch_path, content)
                    self._last_scratch = content
            settings = self._current_settings()
            if settings != self._last_settings:
                save_settings(self._settings_path, settings)
                self._last_settings = settings
            self._autosave_failed = False
        except OSError as exc:
            if not self._autosave_failed:  # report once, keep retrying quietly
                self._autosave_failed = True
                self.flash(f"Autosave failed: {exc.strerror or exc}")

    def _autosave_loop(self) -> None:
        self._persist()
        self.root.after(AUTOSAVE_MS, self._autosave_loop)

    # ----------------------------------------------------------------- find
    def open_find(self) -> None:
        if not self.find_bar.winfo_ismapped():
            self.find_bar.pack(side="top", fill="x", before=self.editor_frame)
            self.find_separator.pack(side="top", fill="x", before=self.editor_frame)
        try:
            selected = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            selected = ""
        if selected and "\n" not in selected:
            self.find_var.set(selected)
        self.find_entry.focus_set()
        self.find_entry.select_range(0, "end")
        self._update_matches(jump=True)

    def close_find(self) -> None:
        self.find_bar.pack_forget()
        self.find_separator.pack_forget()
        self.text.tag_remove("match", "1.0", "end")
        self.text.tag_remove("match_current", "1.0", "end")
        self._matches = []
        self.text.focus_set()

    def find_step(self, direction: int) -> None:
        if not self.find_bar.winfo_ismapped():
            self.open_find()
            return
        self._update_matches(jump=False)  # the text may have changed since the last search
        if not self._matches:
            return
        insert = self.text.index("insert")
        if direction > 0:
            starts = (i for i, (start, _) in enumerate(self._matches) if self.text.compare(start, ">", insert))
            self._match_index = next(starts, 0)
        else:
            starts = (
                i for i in reversed(range(len(self._matches))) if self.text.compare(self._matches[i][0], "<", insert)
            )
            self._match_index = next(starts, len(self._matches) - 1)
        self._highlight_current()

    def _update_matches(self, jump: bool) -> None:
        self.text.tag_remove("match", "1.0", "end")
        self.text.tag_remove("match_current", "1.0", "end")
        self._matches, self._match_index = [], -1
        query = self.find_var.get()
        if query:
            count = tk.IntVar(self.root)
            index = "1.0"
            while True:
                index = self.text.search(query, index, stopindex="end", nocase=True, count=count)
                if not index or not count.get():
                    break
                end = f"{index}+{count.get()}c"
                self._matches.append((index, end))
                self.text.tag_add("match", index, end)
                index = end
        if jump and self._matches:
            insert = self.text.index("insert")
            starts = (i for i, (start, _) in enumerate(self._matches) if self.text.compare(start, ">=", insert))
            self._match_index = next(starts, 0)
            self._highlight_current()
        else:
            self._update_find_count()

    def _highlight_current(self) -> None:
        start, end = self._matches[self._match_index]
        self.text.tag_remove("match_current", "1.0", "end")
        self.text.tag_add("match_current", start, end)
        self.text.mark_set("insert", start)  # typing more keeps this match current
        self.text.see(start)
        self._update_find_count()
        self._refresh_status()

    def _update_find_count(self) -> None:
        if not self.find_var.get():
            self.find_count.configure(text="", fg=THEME["muted_fg"])
        elif not self._matches:
            self.find_count.configure(text="No results", fg=THEME["bad"])
        else:
            current = self._match_index + 1 if self._match_index >= 0 else 0
            self.find_count.configure(text=f"{current} of {len(self._matches)}", fg=THEME["muted_fg"])

    # ------------------------------------------------------------- file ops
    def new_file(self) -> None:
        if not self._confirm_discard():
            return
        self._load_into_editor("", path=None)
        self.flash("New note")

    def open_file(self, path: str | os.PathLike[str] | None = None) -> None:
        if path is None:
            if not self._confirm_discard():
                return
            path = filedialog.askopenfilename(parent=self.root, initialdir=self._initial_dir(), filetypes=FILE_TYPES)
            if not path:
                return
        try:
            content = load_document(path)
        except (OSError, UnicodeDecodeError) as exc:
            messagebox.showerror("Open failed", f"Could not open file:\n{exc}", parent=self.root)
            return
        self._load_into_editor(content, path=Path(path))
        self.flash(f"Opened {self.state.display_name}")

    def save(self) -> bool:
        if self.state.path is None:
            return self.save_as()
        try:
            save_document(self.state.path, self.text.get("1.0", "end-1c"))
        except OSError as exc:
            messagebox.showerror("Save failed", f"Could not save file:\n{exc}", parent=self.root)
            return False
        self.text.edit_modified(False)
        self._update_title()
        self.flash(f"Saved {self.state.display_name}")
        return True

    def save_as(self) -> bool:
        path = filedialog.asksaveasfilename(
            parent=self.root,
            defaultextension=".txt",
            initialdir=self._initial_dir(),
            initialfile=self.state.display_name if self.state.path else "",
            filetypes=FILE_TYPES,
        )
        if not path:
            return False
        self.state.path = Path(path)
        return self.save()

    def _load_into_editor(self, content: str, path: Path | None) -> None:
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.mark_set("insert", "1.0")
        self.text.see("insert")
        self.text.edit_reset()  # loading a file should not be undoable
        self.text.edit_modified(False)
        self.state.path = path
        self._update_title()
        self._refresh_status()

    def _confirm_discard(self) -> bool:
        """Offer to save unsaved changes. Returns False if the user cancelled.

        Untitled notes are autosaved, so they only prompt when about to be replaced.
        """
        if self.state.path is None:
            needs_prompt = bool(self.text.get("1.0", "end-1c").strip())
        else:
            needs_prompt = self.text.edit_modified()
        if not needs_prompt:
            return True
        answer = messagebox.askyesnocancel(APP_NAME, f"Save changes to {self.state.display_name}?", parent=self.root)
        if answer is None:
            return False
        return self.save() if answer else True

    def _initial_dir(self) -> str:
        return str(self.state.path.parent if self.state.path else Path.home())

    # ------------------------------------------------------------- editing
    def _text_event(self, virtual_event: str) -> None:
        self.text.event_generate(virtual_event)
        self._refresh_status()

    def select_all(self) -> None:
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "end-1c")

    def clear(self) -> None:
        self.text.delete("1.0", "end")  # undoable with Ctrl+Z
        self._refresh_status()

    # ---------------------------------------------------------------- view
    def change_font_size(self, delta: int) -> None:
        self._set_font_size(self.state.font_size + delta)

    def reset_font_size(self) -> None:
        self._set_font_size(DEFAULT_FONT_SIZE)

    def _set_font_size(self, size: int) -> None:
        self.state.font_size = int(clamp(size, *FONT_SIZE_RANGE))
        self.editor_font.configure(size=self.state.font_size)
        self.flash(f"Font size {self.state.font_size}")

    def _on_ctrl_wheel(self, event: tk.Event) -> str:
        self.change_font_size(1 if event.delta > 0 else -1)
        return "break"

    def change_opacity(self, delta: float) -> None:
        self.state.alpha = round(clamp(self.state.alpha + delta, *ALPHA_RANGE), 2)
        self.root.attributes("-alpha", self.state.alpha)
        self._update_opacity_label()

    def _update_opacity_label(self) -> None:
        self.opacity_label.configure(text=f"Opacity {round(self.state.alpha * 100)}%")

    def _apply_wrap(self) -> None:
        self.text.configure(wrap="word" if self.wrap_var.get() else "none")

    def _toggle_pin(self) -> None:
        self.topmost_var.set(not self.topmost_var.get())
        self._apply_topmost()

    def _apply_topmost(self) -> None:
        on_top = self.topmost_var.get()
        self.root.attributes("-topmost", on_top)
        self.pin_btn.set_fg(THEME["accent"] if on_top else THEME["muted_fg"])

    def toggle_visibility(self) -> None:
        if self.state.visible:
            self.root.withdraw()
        else:
            if self.shield:
                self.shield.protect(self._hwnd)  # re-assert before the window is shown
            self.root.deiconify()
            self.root.attributes("-topmost", self.topmost_var.get())
            self.root.after(30, self._focus_editor)
        self.state.visible = not self.state.visible

    # ------------------------------------------------------ capture shield
    def _reveal(self) -> None:
        """Protect the (still withdrawn) main window, then show it."""
        self.root.update_idletasks()  # make sure the native wrapper window exists
        self._hwnd = (user32.GetAncestor(self.root.winfo_id(), GA_ROOT) if IS_WINDOWS else 0) or self.root.winfo_id()
        if self.shield:
            self.shield.protect(self._hwnd)
        self.root.deiconify()
        self.root.attributes("-topmost", self.topmost_var.get())
        self._check_shield()
        if self.shield:
            self.root.after(SHIELD_SWEEP_MS, self._shield_loop)
        self.root.after(50, self._focus_editor)

    def _shield_loop(self) -> None:
        self._check_shield()
        self.root.after(SHIELD_SWEEP_MS, self._shield_loop)

    def _check_shield(self) -> None:
        """Re-verify protection of every window and update the indicator."""
        if self.shield is None:
            self._set_shield("Visible", "bad", "Capture protection is only available on Windows.")
            return
        failures = self.shield.sweep()
        main_ok = self.shield.protect(self._hwnd)
        if not main_ok or failures:
            self._set_shield(
                "VISIBLE",
                "bad",
                "Windows refused capture protection: Ghostpad may appear in screen shares.",
            )
        elif self.shield.affinity == WDA_MONITOR:
            self._set_shield(
                "Blacked out",
                "warn",
                "This Windows version shows Ghostpad as a black box in captures. "
                "Windows 10 2004 or later hides it completely.",
            )
        elif not self._shield_hooks_ok:
            self._set_shield(
                "Hidden",
                "warn",
                "Main window hidden. Menus and dialogs may flash briefly in captures.",
            )
        else:
            self._set_shield("Hidden", "ok", "Hidden from screen sharing, recording and screenshots.")

    def _set_shield(self, text: str, level: str, detail: str) -> None:
        label = f"● {text}"
        if self.shield_label.cget("text") == label and self._shield_detail == detail:
            return
        was_ok = self._shield_level == "ok"
        self._shield_level = level
        self._shield_detail = detail
        self.shield_label.configure(text=label, fg=THEME[level])
        if level == "bad" and was_ok:
            self.flash(detail)

    # -------------------------------------------------------------- status
    def _update_title(self) -> None:
        dirty = "● " if self.state.path and self.text.edit_modified() else ""
        name = self.state.display_name
        self.title_label.configure(text=f"{dirty}{name}")
        self.root.title(f"{dirty}{name} - {APP_NAME}")

    def _refresh_status(self) -> None:
        if self._flash_job is not None:
            return
        stats = get_text_stats(self.text.get("1.0", "end-1c"))
        line, col = self.text.index("insert").split(".")
        self.status_label.configure(
            text=f"Ln {line}, Col {int(col) + 1}    {stats['words']} words    {stats['characters']} chars"
        )

    def flash(self, message: str) -> None:
        """Show a transient message in the status bar, then restore the stats."""
        if self._flash_job is not None:
            self.root.after_cancel(self._flash_job)
        self.status_label.configure(text=message)
        self._flash_job = self.root.after(STATUS_FLASH_MS, self._end_flash)

    def _end_flash(self) -> None:
        self._flash_job = None
        self._refresh_status()

    # --------------------------------------------------- window behaviour
    def _show_menu(self, menu: tk.Menu, anchor: tk.Widget) -> None:
        try:
            menu.tk_popup(anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height())
        finally:
            menu.grab_release()

    def _drag_start(self, event: tk.Event) -> None:
        self._drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag_move(self, event: tk.Event) -> None:
        dx, dy = self._drag_offset
        self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def _resize_start(self, event: tk.Event) -> None:
        self._resize_origin = (event.x_root, event.y_root, self.root.winfo_width(), self.root.winfo_height())

    def _resize_move(self, event: tk.Event) -> None:
        x0, y0, w0, h0 = self._resize_origin
        min_w, min_h = (self._px(v) for v in MIN_SIZE)
        width = max(min_w, w0 + event.x_root - x0)
        height = max(min_h, h0 + event.y_root - y0)
        self.root.geometry(f"{width}x{height}")

    def _poll_events(self) -> None:
        """Handle global hotkeys and "show" requests from a second launch."""
        if self.hotkeys:
            while True:
                try:
                    hotkey_id = self.hotkeys.events.get_nowait()
                except queue.Empty:
                    break
                if hotkey_id == HOTKEY_TOGGLE:
                    self.toggle_visibility()
                elif hotkey_id == HOTKEY_SCROLL_UP:
                    self.scroll_notes(-1)
                elif hotkey_id == HOTKEY_SCROLL_DOWN:
                    self.scroll_notes(+1)
        if self._instance and self._instance.show_requested():
            self.bring_to_front()
        self.root.after(HOTKEY_POLL_MS, self._poll_events)

    def scroll_notes(self, direction: int) -> None:
        """Scroll without taking focus, so presenters can stay in their slides."""
        if self.state.visible:
            self.text.yview_scroll(direction * SCROLL_LINES, "units")

    def bring_to_front(self) -> None:
        if not self.state.visible:
            self.toggle_visibility()
        else:
            self.root.lift()
            self._focus_editor()

    # ------------------------------------------------------------ lifecycle
    def quit(self) -> None:
        if not self.state.visible:
            self.toggle_visibility()
        if self.state.path is not None and not self._confirm_discard():
            return
        self._persist()
        if self.hotkeys:
            self.hotkeys.stop()
        if self.shield:
            self.shield.uninstall()
        for job in self.root.tk.splitlist(self.root.tk.call("after", "info")):
            self.root.after_cancel(job)  # stop timers so none fire after destroy
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    instance = SingleInstance()
    if not instance.is_primary:
        instance.signal_primary()  # reveal the running copy instead of starting another
        return
    enable_dpi_awareness()
    app = GhostpadApp(instance=instance)
    if len(sys.argv) > 1:
        app.open_file(sys.argv[1])
    app.run()


if __name__ == "__main__":
    main()
