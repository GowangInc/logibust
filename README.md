# Logibust Lighting Studio

Native GTK3 Linux Mint lighting app for the connected **Logitech G610 (046d:c338)** and **G502 Proteus Spectrum (046d:c332)**. This is an independent Linux application, not a patched or redistributed Logitech installer.

## Open

Find **Logibust Lighting Studio** in the applications menu, or run from this directory:

```sh
/usr/bin/python3 app.py
```

Launching, loading profiles, and login startup **never apply lighting automatically**. Device output needs an explicit **Start keyboard** or **Apply mouse lighting**. Do not run the application as root.

## Controls

- **G610:** steady light, breathing, horizontal/vertical wave, concentric ripple, scanner, starlight, falling rain, checkerboard, WASD focus, selected keys, orbit, heartbeat, diagonal sweep.
- White intensity, speed and reverse direction; interactive physical-key preview. Click keys or use the named-key selector and **Toggle selected key**. Selection switches to the selected-keys preset.
- **Pause animation** freezes preview and the animation clock. **Stop output / freeze** stops further animation writes, leaving the last hardware frame. An already-running write can finish. **Keyboard off** sends a blackout independently of preview.
- Keyboard edits update hardware while output is running. Frames are capped at 10 Hz, unchanged frames skipped, pending frames replaced by the latest; one worker serializes device I/O.
- **G502:** independent driver LED 0 / LED 1 or both; steady RGB, breathing, color cycle and off. RGB picker, intensity, and 1–10-second firmware period. The color picker is disabled for cycle/off; period disabled for steady/off.
- Mouse settings change only on **Apply**, never on every preview frame. Static intensity scales the RGB channels because that firmware mode has no independent brightness field.
- Named profiles store the visible controls, including the chosen mouse LED target; not a snapshot of every device/onboard profile. Save uses atomic JSON replacement. Loading stops keyboard output and changes preview only. Invalid profile files are preserved and errors shown.
- Close hides to the tray **when a tray is available**; otherwise close quits. **Quit** stops host-generated animations, leaving the final keyboard frame. Mouse firmware effects continue independently.
- Optional **Open at login (preview only)** creates a user-local autostart entry. It is off unless explicitly enabled. Reduced-motion desktop settings pause animation initially. Some presets flash; use steady light if sensitive to flashing.

## Hardware boundaries

**G610 has white LEDs, not RGB.** The preview is a physical-key reference, not automatic language/layout detection. ISO/ABNT extra key controls are shown separately; absent physical keys cannot light. Lock-status indicators remain outside the animation map.

**G502 uses libratbag's exposed firmware modes.** This app does not host-stream arbitrary RGB animations, synchronize mouse/keyboard frames, or claim audio/typing-reactive effects. Repeated ratbag commits can write onboard profiles; they must not be used as an animation clock. Physical names for LED indices are unverified, so the UI deliberately uses LED 0/1 instead of guessing logo/DPI order.

Ratbagd commits are asynchronous. A successful apply means the service accepted the request; it is **not optical feedback or a guaranteed hardware completion acknowledgement**. Avoid editing the same mouse simultaneously in Piper/other lighting utilities: ratbagd commits shared staged device state. Logibust itself sets only LED properties, never DPI, button actions, firmware or profile activation.

## Dependencies / machine changes

Uses system `/usr/bin/python3`, GTK3/PyGObject/Cairo, and the already-installed ratbagd service. No web server, root daemon, new Python packages or global input monitoring.

`g810-led` is used as a separate upstream executable. To prepare the keyboard driver without system package installation:

```sh
./prepare-driver.sh
```

This downloads Ubuntu/Mint amd64 `g810-led`, `libg810-led0`, and `libhidapi-hidraw0` packages through the configured apt repositories, extracting them under `~/.cache/logibust/g810-led/`. Nothing is installed in `/usr`, and package service/udev scripts do not run. The app prefers an installed `g610-led`, otherwise this local copy. Upstream licensing remains in the extracted package documentation.

The user explicitly approved `/etc/udev/rules.d/70-logibust-g610.rules`: `uaccess` for **only USB 046d:c338**, with udev reloaded and only that USB device triggered. No world-writable device permissions were added. The packaged driver uses hidraw; this machine's G610 hidraw nodes were already accessible. On another machine, inspect hidraw access if discovery fails; the supplied USB rule alone does not grant every possible backend's required access. Never work around this by running the entire GUI as root.

User data:

- Profiles: `${XDG_CONFIG_HOME:-~/.config}/logibust/profiles.json`.
- Menu entry: `${XDG_DATA_HOME:-~/.local/share}/applications/logibust.desktop`.
- Optional autostart: `${XDG_CONFIG_HOME:-~/.config}/autostart/logibust.desktop`. Disabling sets `Hidden=true`; does not delete the file.

After moving this project directory, regenerate the menu entry:

```sh
/usr/bin/python3 app.py --install-desktop
```

## Checks and observed results

```sh
/usr/bin/python3 selfcheck.py
/usr/bin/python3 devices.py --diagnose
```

Verified on this machine:

- Native desktop window rendered, keyboard preview and both ready statuses inspected. Desktop input verification was stopped with Escape before any automated UI clicks; no further desktop control was attempted.
- Separate Xvfb GTK runtime exercised actual widgets: discovery, selected-key preview, animation pause, profile save/load-to-preview, mouse control sensitivity and accessible field names. This did not change lighting.
- Self-check passed for all 14 effects: white intensity boundaries, deterministic frames, animation changes, reverse direction, exact custom selection, profile round-trip/corruption preservation and valid driver frame construction.
- Real G610 driver accepted five animated frames and a steady 128/255 frame in approximately 0.30 seconds. Last smoke-test state: steady 128/255.
- Real G502 LED 0 request accepted, with expected staged RGB/mode readback; other LED unchanged. Prior mouse lighting restored in ratbagd. Button mappings, resolutions and active-profile metadata read back unchanged.
- A further isolated GTK run activated Start, Stop, Keyboard off and Apply mouse: actual G610 write/blackout completion callbacks and ratbagd acceptance reached their expected UI states. Afterwards G610 was set back to steady 128/255. No further host-desktop input automation was used.
- Explicit blackout scheduling survives an in-flight frame failure; this regression is retained in `selfcheck.py`.
- User-local driver preparation, desktop-file validation and Python compilation succeeded.

The physical light output was **not measured or visually confirmed**. Tray integration, suspend/resume, unplug/replug, login launch and every mouse firmware mode were not separately exercised on the desktop.

## Installer investigation / evidence boundary

Original file left untouched: `/home/nicholas/Downloads/logioptionsplus_installer.exe`.

Observed with `file`, `sha256sum`, `7z l` and `objdump -p`:

- 49,944,728 bytes; SHA-256 `ebdc8c4d9647a9d17652d2129563c4251d8c74adeee5d3dedca4551633437f7a`.
- Native PE32+ x64 Windows GUI outer executable, Options+ metadata version 2.8.981479.
- Resource `.rsrc/RCDATA/101` contains another Windows PE named `logioptionsplus_setup.exe` (49,057,944 bytes).
- Windows API imports, including `COMCTL32.dll`; no CLR runtime header in the outer executable.

**Inference:** changing installer bytes is not a practical route to a native Linux lighting stack; a Linux UI plus existing Linux device drivers avoids depending on Windows application/driver services. Logitech's official Options+ page offers Windows, macOS and Googlebook downloads, not a Linux desktop release.

REA doctor reported stale OMP registration and missing native engines; no REA MCP tools were exposed. No configuration repair, analysis-engine installation, Windows execution, decompilation, firmware extraction, or vendor source recovery was performed. Therefore there are no REA-issued Evidence IDs to cite. The static package inventory does not establish the full installed Options+ architecture or runtime behavior. Independent implementation uses public driver interfaces, not recovered proprietary code.

Primary references:

- [g810-led support, G610 intensity and batched profiles](https://github.com/MatMoul/g810-led#readme)
- [g810-led profile parser and command handling](https://github.com/MatMoul/g810-led/blob/master/src/main.cpp)
- [g810-led key names](https://github.com/MatMoul/g810-led/blob/master/src/helpers/help.cpp)
- [libratbag HID++ LED/profile commit implementation](https://github.com/libratbag/libratbag/blob/master/src/driver-hidpp20.c)
- [Official Options+ platform downloads](https://www.logitech.com/en-us/software/logi-options-plus)

## Initial delivery

Independent native lighting studio, bounded device I/O, 14 white-light presets, per-key editor, G502 firmware controls, profiles, tray/login integration, focused self-check and user-local launcher. Windows installer and firmware unchanged.
