"""Existing Linux drivers only. No firmware, input, DPI or button changes."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib
from effects import KEY_NAMES

SERVICE = 'org.freedesktop.ratbag1'
ROOT = '/org/freedesktop/ratbag1'
LOCAL_DRIVER = Path.home() / '.cache/logibust/g810-led'


def keyboard_command():
    exe = shutil.which('g610-led')
    env = os.environ.copy()
    if not exe:
        exe = str(LOCAL_DRIVER / 'usr/bin/g610-led')
        env['LD_LIBRARY_PATH'] = str(LOCAL_DRIVER / 'usr/lib/x86_64-linux-gnu')
    if not Path(exe).is_file():
        raise RuntimeError('Install g810-led, or run ./prepare-driver.sh for a user-local copy.')
    return [exe, '-dv', '046d', '-dp', 'c338'], env


def run_keyboard(args, profile=None):
    cmd, env = keyboard_command()
    try:
        p = subprocess.run(cmd + args, input=profile, text=True, capture_output=True, env=env, timeout=3)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f'G610 driver failed: {e}') from e
    if p.returncode:
        raise RuntimeError('G610: ' + (p.stderr.strip() or p.stdout.strip() or 'write failed; check USB/HID access and connection.'))
    return p.stdout.strip()


def keyboard_profile(levels):
    if set(levels) != KEY_NAMES or any(type(v) is not int or not 0 <= v <= 255 for v in levels.values()):
        raise ValueError('A keyboard frame must contain every supported key, with brightness 0–255.')
    return ''.join(f'k {k} {levels[k]:02x}\n' for k in sorted(levels)) + 'c\n'


class DeviceManager:
    """Calls are serialized by the app's sole I/O worker. No open USB handles."""
    def __init__(self):
        self.bus = None

    def call(self, path, interface, method, value=None):
        if self.bus is None:
            self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        return self.bus.call_sync(SERVICE, path, interface, method, value, None,
                                  Gio.DBusCallFlags.NONE, 3000, None).unpack()

    def props(self, path, kind):
        return self.call(path, 'org.freedesktop.DBus.Properties', 'GetAll',
                         GLib.Variant('(s)', (SERVICE + '.' + kind,)))[0]

    def set_prop(self, path, name, signature, value):
        self.call(path, 'org.freedesktop.DBus.Properties', 'Set',
                  GLib.Variant('(ssv)', (SERVICE + '.Led', name, GLib.Variant(signature, value))))

    def mouse(self):
        for path in self.props(ROOT, 'Manager')['Devices']:
            device = self.props(path, 'Device')
            if device['Model'] != 'usb:046d:c332:0':
                continue
            profiles = [(p, self.props(p, 'Profile')) for p in device['Profiles']]
            active = [(p, d) for p, d in profiles if d['IsActive']]
            if len(active) != 1:
                raise RuntimeError('G502 has no unique active profile; select one in Piper first.')
            profile_path, profile = active[0]
            leds = [(p, self.props(p, 'Led')) for p in profile['Leds']]
            return path, profile_path, leds
        raise RuntimeError('G502 is not available through ratbagd. Check ratbagctl list / ratbagd service.')

    def discover(self):
        present = set()
        for dev in Path('/sys/bus/usb/devices').iterdir():
            try:
                present.add(((dev / 'idVendor').read_text().strip(), (dev / 'idProduct').read_text().strip()))
            except (FileNotFoundError, PermissionError):
                continue
        result = {}
        for kind, pid in [('keyboard', 'c338'), ('mouse', 'c332')]:
            result[kind] = dict(connected=('046d', pid) in present, ready=False, detail='Not connected.')
        if result['keyboard']['connected']:
            try:
                info = run_keyboard(['--print-device'])
                if 'c338' not in info.lower():
                    raise RuntimeError('G610 driver did not identify product c338.')
                result['keyboard'].update(ready=True, detail='G610 · per-key white · g810-led ready')
            except Exception as e:
                result['keyboard']['detail'] = str(e)
        if result['mouse']['connected']:
            try:
                _, _, leds = self.mouse()
                if not leds:
                    raise RuntimeError('G502 exposes no LED controls.')
                result['mouse'].update(ready=True, detail=f'G502 Spectrum · {len(leds)} RGB LEDs · ratbagd ready',
                                       leds=[dict(index=d['Index'], modes=d['Modes']) for _, d in leds])
            except Exception as e:
                result['mouse']['detail'] = str(e)
        return result

    def apply_keyboard(self, levels):
        run_keyboard(['-pp'], keyboard_profile(levels))

    def apply_mouse(self, mode, color, brightness, period_ms, zone='all'):
        modes = dict(off=0, static=1, cycle=2, breathing=3)
        if mode not in modes or not isinstance(color, str) or not re.fullmatch('[0-9a-fA-F]{6}', color):
            raise ValueError('Invalid mouse mode or RGB color.')
        if type(brightness) is not int or not 0 <= brightness <= 255 or type(period_ms) is not int or not 1000 <= period_ms <= 10000:
            raise ValueError('Mouse brightness must be 0–255; period must be 1000–10000 ms.')
        if zone not in ('all', '0', '1'):
            raise ValueError('Select all LEDs, LED 0 or LED 1.')
        device, _, leds = self.mouse()
        target = [(p, d) for p, d in leds if zone == 'all' or str(d['Index']) == zone]
        if not target or any(modes[mode] not in d['Modes'] for _, d in target):
            raise RuntimeError('Requested LED/mode is not exposed by the G502 driver.')
        rgb = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
        # Static HID++ mode has no separate luminance field; scale its RGB channels.
        if mode == 'static':
            rgb = tuple(round(c * brightness / 255) for c in rgb)
        updates = [('Color', '(uuu)', rgb), ('Brightness', 'u', brightness),
                   ('EffectDuration', 'u', period_ms), ('Mode', 'u', modes[mode])]
        changed = []
        try:
            for path, old in target:
                for name, sig, value in updates:
                    if old[name] != value:
                        self.set_prop(path, name, sig, value)
                        changed.append((path, name, sig, old[name]))
        except Exception:
            # Roll back staged D-Bus LED properties; do not commit a partial request.
            for path, name, sig, value in reversed(changed):
                self.set_prop(path, name, sig, value)
            raise
        if changed:
            self.call(device, SERVICE + '.Device', 'Commit')
        # ratbagd's commit is asynchronous: this is driver acceptance, not optical feedback.
        return 'G502 request accepted by ratbagd; hardware commit is asynchronous.'

    def close(self):
        self.bus = None


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Read-only lighting device diagnostics')
    parser.add_argument('--diagnose', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(DeviceManager().discover(), indent=2))
