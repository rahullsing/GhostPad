# Security and privacy

## What Ghostpad protects against

Ghostpad hides its windows from **software screen capture** on the same
machine, using `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`. Windows
enforces this in the desktop compositor. It applies to every capture method
that reads composed desktop frames:

- Desktop Duplication API (DXGI)
- Windows.Graphics.Capture, used by modern meeting apps and browsers
- GDI `BitBlt` and `PrintWindow`-style screenshots

That covers screen sharing in Zoom, Microsoft Teams, Google Meet and other
browser-based tools, Webex, Discord and Slack. It also covers recording tools
such as OBS, and screenshots taken with the Snipping Tool or
<kbd>PrtScn</kbd>.

Ghostpad also protects its own popup menus, message boxes and file dialogs. A
status-bar indicator re-verifies protection four times a second. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the mechanism.

## What it does *not* protect against

- **Cameras.** A camera or phone pointed at the screen sees everything.
- **Hardware capture.** HDMI capture cards, KVM capture, and mirroring to a
  projector or TV all receive the raw video signal.
- **Remote-desktop and remote-control software.** Behaviour depends on the
  product and hasn't been verified. Test yours.
- **Capture that bypasses the compositor.** This includes kernel-mode drivers
  and anything with administrative control of the machine.
- **Old Windows.** Before Windows 10 version 2004, the best available mode
  renders Ghostpad as a black box instead of hiding it. The indicator shows
  **Blacked out** in that case.
- **Sharing the Ghostpad window itself.** Viewers see a blank or black area,
  which tells them a hidden window exists.

**Always do a test share before a meeting that matters.**

## Data handling

- **No network:** Ghostpad makes no network connections and has no telemetry.
- **Local storage only:** notes and settings stay in `%APPDATA%\Ghostpad`, in
  plain text and JSON. They are **not encrypted**. Anyone with access to your
  Windows account can read them.
- **Your own files:** files you open or save stay where you put them.
  Ghostpad never writes to them without an explicit Save.

## Responsible use

Ghostpad is meant for private presenter notes, talking points and personal
reminders. Don't use it to break the rules of an exam, interview or other
setting where hidden material is prohibited.

## Reporting a vulnerability

Please report security issues **privately** through
[GitHub's private vulnerability reporting](https://github.com/rahullsing/GhostPad/security/advisories/new),
not in a public issue. Include:

- the Windows version and build (run `winver`),
- the capture tool and version you used,
- the steps to reproduce,
- what the status-bar indicator showed.

You should get an acknowledgement within a few days.
