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

The tray menu offers **Open Logibust**, **Stop lighting + capture**, and **Quit Logibust**. Closing the window hides it when a tray is available. Without a tray, background startup shows the window after a short grace period instead of leaving an inaccessible process. The login checkbox can disable startup without deleting its configuration file.

Startup and profile loading are **preview only**: no lighting changes happen until **Start keyboard** or **Apply lighting**. Capture starts disabled and is never enabled by a profile or effect selection. No keys are selected initially; saved selections load only through an explicit profile load. The application does not depend on Solaar.

## Device-first interface

- Connected peripherals appear first in the left sidebar. The connected G610 is preferred on this setup; otherwise the first ready connected device is selected.
- One device panel is shown at a time, with a keyboard, mouse, headset, mousepad or generic peripheral illustration and relevant controls.
- **Browse device library** exposes 108 model entries from 10 brands: Logitech, ASUS, SteelSeries, Roccat, Glorious, G.Skill, Etekcity, Nubwo, SinoWealth and openinput. Search filters the sidebar.
- The library is an identification/reference catalog, **not a claim that all 108 devices have lighting or have been hardware-tested**. Offline entries are labeled catalog previews and cannot receive hardware commands. Connected devices without a lighting driver remain identifiable, with actions disabled.
- Selecting a different device stops outgoing keyboard and software mouse streaming. Pending writes retain their original target; stale callbacks cannot mark a newly selected device live. Duplicate physical instances are not collapsed into a single catalog entry.

The interface borrows the white/pale-gray, purple-accent, device-first approach described in [Logitech's official Options+ device setup guide](https://hub.sync.logitech.com/options/post/device-setup-in-options-ESnKTSDRb8xy7mL). The artwork is original Cairo drawing, not copied product photographs or logos. Illustrations and the ANSI/ISO keyboard reference are not exact product/language-layout detection.

## Lighting controls

### Keyboards

Twenty-eight keyboard effects: the original steady light, breathing, horizontal/vertical waves, concentric ripple, scanner, starlight, falling rain, checkerboard, WASD focus, selected keys, orbit, heartbeat and diagonal sweep, plus the scenes and live effects below.

Brightness, speed, direction, animation pause, selectable keys and clear selection. Use the graphic or the keyboard-accessible named-key selector. A selected-keys preset with an empty selection lights nothing. Choosing WASD focus is an explicit preset choice, not an automatic key selection.

**G610 LEDs are white only.** RGB color controls are disabled for it. Documented RGB g810-led models get an RGB color picker. Whole-board-only keyboards, such as G213/G413, do not expose per-key effects. The reference key map covers standard keys, media keys and ISO/ABNT extras, not every model's extra macro keys or lock-status indicators.

**Start keyboard** sends frames to the selected device. Live effect edits update it. **Stop / freeze** stops future keyboard and software mouse frames, leaving the last frame; an in-flight write can finish. **Keyboard off** sends a blackout independently of the preview. Frames are capped at 10 Hz, unchanged frames skipped, and stale pending frames coalesced by one I/O worker. Capture can continue for preview after freezing; use **Stop lighting + disable capture** to end both.

Some presets flash. Use steady light if sensitive to flashes. Desktop reduced-motion preferences pause the preview initially.

### G502 Proteus Spectrum

The dedicated runtime backend targets only USB **046d:c332**. It discovers the HID++ lighting feature and its zone/effect indices from the device, validates the opened HID descriptor's USB identity, waits for matching command acknowledgements, then checks the current hardware effect state.

The two detected zones are **DPI indicators** and **Logo**. Each can use steady RGB, breathing, color cycle or off; controls include brightness and a 1–10-second period. An all-zones target is also available. Brightness zero sends Off rather than relying on the firmware's ambiguous zero-percentage convention.

The corrected path uses HID++ **0x8070 runtime RAM writes**, with the persistence byte kept zero. No onboard-profile commit, DPI/button change, profile activation or firmware update is used. Effects can reset on unplug/power loss; apply again when needed. Software scenes use one persistent HID session with cached capabilities and verified, independently colored zone updates, never repeated profile commits. Software scenes require Logibust to remain running; firmware effects continue without it.

### Scenes and linked playback

Eight additional scenes are available on both devices: **Aurora Drift**, **Ember Bed**, **Ocean Glass**, **Lava Cells**, **Interference**, **Eclipse**, **Gravity Well**, and **Comet Relay**. The G610 renders brightness patterns in white; the G502 renders their paired RGB/brightness patterns across DPI and logo zones.

For coordinated playback, select the keyboard, choose a scene, enable **Link mouse to this keyboard scene**, check the named mouse target, then **Start keyboard**. Both outputs use one animation clock and one bounded I/O queue. This is shared scene timing, not hardware frame-lock: USB requests are sequential. Comet relay crosses the keyboard before handing off to DPI and then logo.

For mouse-only playback, select the G502, choose a mode marked **software**, select a zone or all zones, then **Apply lighting**. Its period/tempo slider controls software speed relative to the default value of eight; it does not specify an exact cycle length. Linked scenes instead use keyboard speed. No generic ratbagd backend receives software frame streams.

### Sound, monitor and typing effects

The **LIVE INPUTS · OPT IN** card controls capture independently of effect choice. Inputs can drive preview before any hardware output is started. Status distinguishes starting, live, disabled, stale and failed sources. A failed source must be explicitly disabled/re-enabled or changed; it is not silently replaced.

- **Audio level** follows output loudness; **Audio spectrum** maps bass/mid/treble across the board; **Audio pulse** follows bass onsets. Enable **Listen to speaker output** and select the output monitor. Only sources explicitly associated with an output sink are accepted; the microphone is never selected as a fallback.
- **Screen ambient** uses monitor-average brightness on the white keyboard and average RGB on the mouse. **Screen map** projects monitor brightness onto key positions and samples screen-side colors for the two mouse zones. Enable **Read monitor colors** and select the monitor. Capture is downscaled to 24×12 RGB at 8 Hz, with the pointer excluded.
- **Typing ripple** produces expanding, overlapping raindrop rings centred on each physically pressed key, not random drops or ripples from the keyboard centre. Enable **Listen to physical key presses**, check the named USB keyboard, then Start. Speed controls expansion; **Ripple lifetime** controls expiry; sensitivity controls response strength. Held-key repeats and releases do not create new drops.

Capture requires explicit session opt-in. Profiles save effect choices, sensitivity, lifetime and linking preference, **not capture permissions**. No audio recordings, screenshots or typed text are written to disk. The input worker retains at most 96 recent key positions for six seconds and discards them when disabled. Screen/audio buffers are transient and stale samples become dark.

Typing capture is device-filtered but works across applications, **including password fields**; disable it before sensitive typing. It observes physical key positions, not translated characters, and never grabs/suppresses normal input. XInput Device Node and USB-port identities are checked so another keyboard or a replugged device does not silently inherit capture.


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

Linux with GTK3/PyGObject/Cairo and `/usr/bin/python3`. Optional live inputs additionally use installed `pactl`/`parec`, NumPy, FFmpeg with x11grab, python-xlib and python-evdev (key-code constants only). The tested Mint host already supplies these; no packages or input permissions were changed. Screen and device-filtered typing capture require **X11/XInput 2.1**, not Wayland. Missing dependencies/permissions are reported rather than replaced with simulated input. Use ratbagd for generic ratbag lighting devices. No web server or root Logibust daemon is required.

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
- All 28 frame effects, mouse scene boundaries/animation, silent reactive inputs, key-origin propagation/overlap/expiry, spatial screen mapping, mid-band mouse response, intensity boundaries, direction, custom keys, persisted-profile validation/corruption preservation, catalog/live-instance merging, output-monitor classification and blackout/failure ordering.
- Real keyboard writes through GTK Start, switching-device stop, Off and steady-light paths. Stale completions do not update another device's state.
- The G502's live effect enumeration reports breathing **effect ID 10 at wire index 2**. Old ratbag profile cache values did not match the mouse's live state. The new runtime path correctly translates effect indices, acknowledges writes and checks the live effect readback.
- The user visually confirmed the G502 turned steady red. Breathing was also exercised through the new app's Apply action with device acknowledgement/readback. No claim is made that every firmware mode or every library model was visually tested.
- Profile save/load-to-preview, offline actions disabled, and selected-device navigation exercised in isolated GTK runs. Actual keyboard/mouse panel renders inspected. Desktop input automation was not performed because its approval prompts were unanswered.
- Real desktop background launch remained windowless, and Gtk.StatusIcon reported embedding into the desktop tray. Autostart/menu entries validated. Tray menu click interaction was not manually exercised.
- Real speaker-monitor capture checked with isolated 90/900/4000 Hz tones: each reached its expected FFT band, only the bass tone triggered the bass envelope, and disabling capture cleared samples/workers. Temporary test sinks were unloaded.
- Actual X11 capture of red/blue screen regions verified 24×12 RGB sampling, keyboard luminance mapping and independent mouse-zone colors.
- All eight scenes and all five sound/screen modes exercised through actual GTK controls and linked G610/G502 hardware playback. G502 writes were acknowledged/read back. DPI-only software playback left the logo unchanged.
- The physical G610 XInput worker connected and remained live without new input permissions. No physical press occurred during the timed check; actual press-to-ripple behaviour still needs a user check. Key-origin, expansion, overlapping events and expiry were verified with explicit renderer input snapshots.
- Startup capture-off state, opt-in controls, stop-all teardown, source idempotence and actual GTK surface layout exercised. Test teardown left no capture workers, restored the previous G502 runtime lighting and set the G610 to steady 128/255. New scene output was not optically measured.

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

Eight coordinated software scenes, output-monitor audio level/spectrum/bass pulse, monitor ambient/spatial mapping, physical-key raindrop ripples, session-only capture controls, persistent RAM-only G502 streaming, and a shared clock for opt-in linked playback. Earlier device-first dashboard, empty selection, device catalog and background tray/login startup are retained.
