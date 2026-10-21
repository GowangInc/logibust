# Logibust

A native Linux peripheral-lighting control panel, with an Options+-inspired device-first interface and original device illustrations. Independent software; not affiliated with Logitech. No Logitech installer, vendor artwork, or firmware is bundled.

## Open and background startup

Open **Logibust Lighting Studio** from the applications menu, or:

```sh
/usr/bin/python3 app.py
```

Run beside the clock without opening a window:

```sh
/usr/bin/python3 app.py --background
```

Install the user-local menu entry and enable background login startup:

```sh
/usr/bin/python3 app.py --install-desktop --enable-autostart
```

The tray menu offers **Open Logibust**, **Stop keyboard animation**, and **Quit Logibust**. Closing the window hides it when a tray is available. Without a tray, background startup shows the window after a short grace period instead of leaving an inaccessible process. The login checkbox can disable startup without deleting its configuration file.

Startup and profile loading are **preview only**: no lighting changes happen until **Start keyboard** or **Apply lighting**. No keys are selected initially; saved selections load only through an explicit profile load. The application does not depend on Solaar.

## Device-first interface

- Connected peripherals appear first in the left sidebar. The connected G610 is preferred on this setup; otherwise the first ready connected device is selected.
- One device panel is shown at a time, with a keyboard, mouse, headset, mousepad or generic peripheral illustration and relevant controls.
- **Browse device library** exposes 108 model entries from 10 brands: Logitech, ASUS, SteelSeries, Roccat, Glorious, G.Skill, Etekcity, Nubwo, SinoWealth and openinput. Search filters the sidebar.
- The library is an identification/reference catalog, **not a claim that all 108 devices have lighting or have been hardware-tested**. Offline entries are labeled catalog previews and cannot receive hardware commands. Connected devices without a lighting driver remain identifiable, with actions disabled.
- Selecting a different device stops outgoing keyboard streaming. Pending writes retain their original target; stale callbacks cannot mark a newly selected device live. Duplicate physical instances are not collapsed into a single catalog entry.

The interface borrows the white/pale-gray, purple-accent, device-first approach described in [Logitech's official Options+ device setup guide](https://hub.sync.logitech.com/options/post/device-setup-in-options-ESnKTSDRb8xy7mL). The artwork is original Cairo drawing, not copied product photographs or logos. Illustrations and the ANSI/ISO keyboard reference are not exact product/language-layout detection.

## Lighting controls

### Keyboards

Fourteen presets: steady light, breathing, horizontal wave, vertical wave, concentric ripple, scanner, starlight, falling rain, checkerboard, WASD focus, selected keys, orbit, heartbeat and diagonal sweep.

Brightness, speed, direction, animation pause, selectable keys and clear selection. Use the graphic or the keyboard-accessible named-key selector. A selected-keys preset with an empty selection lights nothing. Choosing WASD focus is an explicit preset choice, not an automatic key selection.

**G610 LEDs are white only.** RGB color controls are disabled for it. Documented RGB g810-led models get an RGB color picker. Whole-board-only keyboards, such as G213/G413, do not expose per-key effects. The reference key map covers standard keys, media keys and ISO/ABNT extras, not every model's extra macro keys or lock-status indicators.

**Start keyboard** sends frames to the selected device. Live effect edits update it. **Stop / freeze** stops future animation frames, leaving the last frame; an in-flight write can finish. **Keyboard off** sends a blackout independently of the preview. Frames are capped at 10 Hz, unchanged frames skipped, and stale pending frames coalesced by one I/O worker.

Some presets flash. Use steady light if sensitive to flashes. Desktop reduced-motion preferences pause the preview initially.

### G502 Proteus Spectrum

The dedicated runtime backend targets only USB **046d:c332**. It discovers the HID++ lighting feature and its zone/effect indices from the device, validates the opened HID descriptor's USB identity, waits for matching command acknowledgements, then checks the current hardware effect state.

The two detected zones are **DPI indicators** and **Logo**. Each can use steady RGB, breathing, color cycle or off; controls include brightness and a 1–10-second period. An all-zones target is also available. Brightness zero sends Off rather than relying on the firmware's ambiguous zero-percentage convention.

The corrected path uses HID++ **0x8070 runtime RAM writes**, with the persistence byte kept zero. No onboard-profile commit, DPI/button change, profile activation or firmware update is used. Effects can reset on unplug/power loss; apply again when needed. The app does not host-stream arbitrary RGB animations or synchronize mouse and keyboard frames.

### Other lighting peripherals

The app also enumerates actual ratbagd devices, queries advertised LED zones/modes, and targets the selected backend object. This can expose lighting on additional supported mice/headsets/peripherals from the installed driver ecosystem. A model definition alone never enables controls.

Generic ratbagd commits remain asynchronous: success means **request accepted, not confirmed physical output**. They may write onboard profiles. Do not edit the same device concurrently in Piper/other lighting utilities, because ratbagd stages shared device state. The G502 Spectrum bypasses that profile path entirely.

## Profiles and local files

Named profiles store the visible lighting controls, not a snapshot of every device's onboard configuration. Save uses atomic JSON replacement. Invalid/unsupported profile files are preserved and reported, never silently replaced by defaults.

- Profiles: `$XDG_CONFIG_HOME/logibust/profiles.json`, default `~/.config/logibust/profiles.json`.
- Menu entry: `$XDG_DATA_HOME/applications/logibust.desktop`, default `~/.local/share/applications/logibust.desktop`.
- Login entry: `$XDG_CONFIG_HOME/autostart/logibust.desktop`, default `~/.config/autostart/logibust.desktop`.

After moving the project, rerun `--install-desktop --enable-autostart` to update the paths. Disabling login startup sets `Hidden=true` instead of deleting the entry. Do not run the GUI as root.

## Dependencies

Linux with GTK3/PyGObject/Cairo and `/usr/bin/python3`. Use ratbagd for generic ratbag lighting devices. No web server, root Logibust daemon, global keyboard monitoring, or new Python packages are required.

For a user-local g810-led installation on Ubuntu/Mint amd64:

```sh
./prepare-driver.sh
```

This downloads `g810-led`, `libg810-led0` and `libhidapi-hidraw0` through configured apt repositories, extracting them under `~/.cache/logibust/g810-led/`. It does not install system packages or run package udev/service hooks. The app prefers installed driver commands and otherwise uses this local copy. Upstream package licensing remains in its extracted documentation.

USB/hidraw access is required. The supplied `70-logibust-g610.rules` is a narrow USB `uaccess` example for **only 046d:c338**; it is not automatically installed. On the tested machine this rule was installed with explicit approval, and keyboard/mouse hidraw access already worked. This USB-only rule does not grant every backend's hidraw requirements on another machine. Configure a scoped device rule rather than using world-writable permissions or a root GUI.

## Verification

```sh
/usr/bin/python3 selfcheck.py
/usr/bin/python3 devices.py --diagnose
```

Completed checks on Linux Mint with G610 046d:c338 and G502 Spectrum 046d:c332:

- Empty initial selection and G610-first default; three actual connected peripherals identified, including an unsupported-lighting USB keyboard.
- All 14 frame effects, intensity boundaries, direction, custom keys, persisted-profile validation/corruption preservation, catalog/live-instance merging, and blackout/failure ordering.
- Real keyboard writes through GTK Start, switching-device stop, Off and steady-light paths. Stale completions do not update another device's state.
- The G502's live effect enumeration reports breathing **effect ID 10 at wire index 2**. Old ratbag profile cache values did not match the mouse's live state. The new runtime path correctly translates effect indices, acknowledges writes and checks the live effect readback.
- The user visually confirmed the G502 turned steady red. Breathing was also exercised through the new app's Apply action with device acknowledgement/readback. No claim is made that every firmware mode or every library model was visually tested.
- Profile save/load-to-preview, offline actions disabled, and selected-device navigation exercised in isolated GTK runs. Actual keyboard/mouse panel renders inspected. Desktop input automation was not performed because its approval prompts were unanswered.
- Real desktop background launch remained windowless, and Gtk.StatusIcon reported embedding into the desktop tray. Autostart/menu entries validated. Tray menu click interaction was not manually exercised.

The Windows Options+ installer used during the initial investigation was left unchanged. Static package metadata identified a Windows x64 PE wrapper containing another Windows setup PE, not a native Linux application. REA engines were unavailable; no decompilation, vendor source recovery, installer patching, or firmware extraction occurred. This is an independent Linux implementation using public driver/protocol information.

## Sources

- [g810-led supported keyboards, intensity/profile commands](https://github.com/MatMoul/g810-led)
- [g810-led USB rules and command feature flags](https://github.com/MatMoul/g810-led/blob/master/src/helpers/help.h)
- [libratbag device metadata](https://github.com/libratbag/libratbag/tree/master/data/devices)
- [libratbag HID++ protocol structures](https://github.com/libratbag/libratbag/blob/master/src/hidpp20.h)
- [libratbag HID++ operations](https://github.com/libratbag/libratbag/blob/master/src/hidpp20.c)
- [OpenRGB captures for this exact G502 Spectrum](https://openrgb-wiki.readthedocs.io/en/latest/Logitech-G502/)
- [Official Options+ device setup/navigation](https://hub.sync.logitech.com/options/post/device-setup-in-options-ESnKTSDRb8xy7mL)

## Changes

Device-first sidebar dashboard and original graphics; empty initial key selection; corrected, acknowledged G502 runtime lighting; broader source-backed catalog and capability-driven backends; safe target switching; background tray/login startup. Solaar is not required.
