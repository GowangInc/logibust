"""Selected-device Linux lighting backends. No firmware/DPI/button changes."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib
from catalog import KEYBOARD_MODELS, load_catalog
from effects import KEY_NAMES
from hidpp import G502Lighting, g502_endpoints

SERVICE = 'org.freedesktop.ratbag1'
ROOT = '/org/freedesktop/ratbag1'
LOCAL_DRIVER = Path.home() / '.cache/logibust/g810-led'
MODES = {'off':0, 'static':1, 'cycle':2, 'breathing':3}


def valid_color(color):
    if not isinstance(color, str) or not re.fullmatch('[0-9a-fA-F]{6}', color):
        raise ValueError('RGB color must contain six hexadecimal digits.')
    return tuple(bytes.fromhex(color))


def keyboard_profile(levels, color='ffffff', rgb=False):
    if set(levels) != KEY_NAMES or any(type(v) is not int or not 0 <= v <= 255 for v in levels.values()):
        raise ValueError('A keyboard frame must contain every supported key, with brightness 0–255.')
    channels = valid_color(color)
    def value(level):
        return ''.join(f'{round(c*level/255):02x}' for c in channels) if rgb else f'{level:02x}'
    return ''.join(f'k {k} {value(levels[k])}\n' for k in sorted(levels)) + 'c\n'


def run_keyboard(device, args, profile=None):
    command = device['_command']
    executable = shutil.which(command)
    env = os.environ.copy()
    if not executable:
        executable = str(LOCAL_DRIVER/'usr/bin'/command)
        env['LD_LIBRARY_PATH'] = str(LOCAL_DRIVER/'usr/lib/x86_64-linux-gnu')
    if not Path(executable).is_file():
        raise RuntimeError('g810-led driver missing. Run ./prepare-driver.sh or install g810-led.')
    vendor, product = device['usb_ids'][0].split(':')
    cmd = [executable, '-dv', vendor, '-dp', product]
    if device.get('_serial'):
        cmd += ['-ds', device['_serial']]
    try:
        p = subprocess.run(cmd + args, input=profile, text=True, capture_output=True, env=env, timeout=3)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f'Keyboard driver failed: {e}') from e
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or 'Keyboard write failed; check HID access and connection.')
    return p.stdout.strip()


def usb_inputs():
    """Enumerate physical HID USB devices, not hubs; retain all separate instances."""
    found = {}
    for node in sorted(Path('/sys/class/hidraw').glob('hidraw*')):
        try:
            device = (node/'device').resolve()
            for parent in device.parents:
                if (parent/'idVendor').is_file() and (parent/'idProduct').is_file():
                    usb = parent
                    break
            else:
                continue
            usb_id = (usb/'idVendor').read_text().strip()+':'+(usb/'idProduct').read_text().strip()
            if usb.name not in found:
                name = (usb/'product').read_text().strip() if (usb/'product').is_file() else usb_id
                vendor = (usb/'manufacturer').read_text().strip() if (usb/'manufacturer').is_file() else 'USB'
                serial = (usb/'serial').read_text().strip() if (usb/'serial').is_file() else ''
                kind = 'keyboard' if 'keyboard' in name.casefold() else 'mouse' if 'mouse' in name.casefold() else 'other'
                found[usb.name] = dict(id='usb:'+usb.name, name=name, vendor=vendor, kind=kind,
                    usb_ids=[usb_id], backend='none', connected=True, ready=False, rgb=False, per_key=False,
                    modes=[], leds=[], detail='Connected USB peripheral. No lighting backend detected.',
                    _usb_path=str(usb), _serial=serial, _hidraw=[])
            found[usb.name]['_hidraw'].append('/dev/'+node.name)
        except (FileNotFoundError, PermissionError):
            continue
    return list(found.values())


class DeviceManager:
    """One serialized I/O worker owns this object; discovery never changes lighting."""
    def __init__(self):
        self.bus = None
        self.devices = {}
        self.mouse = None
        self.mouse_id = None
        self.last_keyboard = None

    def call(self, path, interface, method, value=None):
        if self.bus is None:
            self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        return self.bus.call_sync(SERVICE, path, interface, method, value, None,
                                  Gio.DBusCallFlags.NONE, 3000, None).unpack()

    def props(self, path, kind):
        return self.call(path, 'org.freedesktop.DBus.Properties', 'GetAll',
                         GLib.Variant('(s)', (SERVICE+'.'+kind,)))[0]

    def set_prop(self, path, name, signature, value):
        self.call(path, 'org.freedesktop.DBus.Properties', 'Set',
            GLib.Variant('(ssv)', (SERVICE+'.Led', name, GLib.Variant(signature, value))))

    def ratbag_leds(self, path):
        device = self.props(path, 'Device')
        profiles = [(p,self.props(p,'Profile')) for p in device['Profiles']]
        active = [(p,d) for p,d in profiles if d['IsActive']]
        if len(active) != 1:
            raise RuntimeError('Device has no unique active profile; choose one in its configuration utility.')
        return [(p,self.props(p,'Led')) for p in active[0][1]['Leds']]

    def discover(self):
        self.release_lighting()
        records = usb_inputs()
        models = load_catalog()
        for d in records:
            usb_id = d['usb_ids'][0]
            reference = next((m for m in models if usb_id in m['usb_ids']), None)
            if reference:
                d.update(name=reference['name'], vendor=reference['vendor'], kind=reference['kind'])
            if usb_id in KEYBOARD_MODELS:
                name, command, rgb, per_key = KEYBOARD_MODELS[usb_id]
                d.update(name=name, vendor='Logitech', kind='keyboard', backend='g810-led', rgb=rgb,
                         per_key=per_key, modes=['off','static'], _command=command)
                try:
                    if not d['_serial'] and sum(x['usb_ids'] == d['usb_ids'] for x in records) > 1:
                        raise RuntimeError('Multiple matching keyboards have no serial; cannot target one safely.')
                    run_keyboard(d, ['--print-device'])
                    d.update(ready=True, detail='Connected · g810-led · '+('RGB' if rgb else 'single-color')+(' per-key lighting' if per_key else ' whole-board brightness'))
                except Exception as e:
                    d['detail'] = str(e)
            elif usb_id == '046d:c332':
                d.update(name='Logitech G502 Proteus Spectrum', vendor='Logitech', kind='mouse', backend='HID++ 8070', rgb=True)
                try:
                    endpoints = [p for p in g502_endpoints() if p in d['_hidraw']]
                    if len(endpoints) != 1:
                        raise RuntimeError('Cannot identify one G502 HID++ endpoint; check HID permissions.')
                    d['_endpoint'] = endpoints[0]
                    with G502Lighting(d['_endpoint']) as mouse:
                        d['leds'] = [{k:v for k,v in z.items() if k != 'indexes'} for z in mouse.zones]
                    d['modes'] = [m for m in MODES if all(m in z['modes'] for z in d['leds'])]
                    d.update(ready=True, detail='Connected · live HID++ lighting · acknowledged RAM-only writes')
                except Exception as e:
                    d['detail'] = str(e)
        try:
            paths = self.props(ROOT,'Manager')['Devices']
        except Exception as e:
            paths = []
            for d in records:
                if d['backend'] == 'none':
                    d['detail'] += ' ratbagd unavailable: '+str(e)
        claimed = set()
        for path in paths:
            info = self.props(path,'Device')
            match = re.match(r'usb:([0-9a-fA-F]{4}:[0-9a-fA-F]{4})(?::|$)', info['Model'])
            usb_id = match.group(1).lower() if match else ''
            # Preserve the confirmed runtime G502 and g810-led keyboard backends.
            if usb_id == '046d:c332' or usb_id in KEYBOARD_MODELS:
                continue
            endpoint = '/dev/'+Path(path).name
            candidates = [d for d in records if endpoint in d.get('_hidraw',[]) and d['id'] not in claimed]
            if not candidates:
                candidates = [d for d in records if d['usb_ids'] == [usb_id] and d['id'] not in claimed]
            d = candidates[0] if len(candidates) == 1 else dict(id='ratbag:'+path, name=info['Name'], vendor=info['Name'].split()[0],
                kind='mouse', usb_ids=[usb_id] if usb_id else [], connected=True, ready=False, rgb=False, per_key=False, modes=[], leds=[])
            if d not in records:
                records.append(d)
            claimed.add(d['id'])
            d.update(backend='ratbagd', _ratbag=path)
            reference = next((m for m in models if usb_id and usb_id in m['usb_ids']),None)
            if reference:
                d.update(name=reference['name'],vendor=reference['vendor'],kind=reference['kind'])
            try:
                leds = self.ratbag_leds(path)
                d['leds'] = [dict(id=str(p['Index']), name='LED '+str(p['Index']),
                    modes=[m for m,n in MODES.items() if n in p['Modes']]) for _,p in leds]
                d['rgb'] = bool(leds and any(p['ColorDepth'] > 0 for _,p in leds))
                d['modes'] = [m for m in MODES if leds and all(MODES[m] in p['Modes'] for _,p in leds)]
                d['ready'] = bool(d['modes'])
                d['detail'] = 'Connected · ratbagd · '+(f'{len(leds)} lighting zones; commits are asynchronous' if leds else 'no lighting controls exposed')
            except Exception as e:
                d['detail'] = str(e)
        self.devices = {d['id']:d for d in records}
        return [{k:v for k,v in d.items() if not k.startswith('_')} for d in records]

    def selected(self, device_id):
        d = self.devices.get(device_id)
        if not d or not d['ready']:
            raise RuntimeError('Selected device is not ready. Refresh devices; no other device was used.')
        if d.get('_usb_path'):
            usb = Path(d['_usb_path'])
            try:
                identity = (usb/'idVendor').read_text().strip()+':'+(usb/'idProduct').read_text().strip()
                serial = (usb/'serial').read_text().strip() if (usb/'serial').is_file() else ''
            except FileNotFoundError as e:
                raise RuntimeError('Selected device was unplugged. Refresh devices.') from e
            if identity not in d['usb_ids'] or (d.get('_serial') and serial != d['_serial']):
                raise RuntimeError('The USB device at this port changed. Refresh before applying lighting.')
        return d

    def apply_keyboard(self, device_id, levels, color='ffffff'):
        d = self.selected(device_id)
        if d['backend'] != 'g810-led':
            raise ValueError('Selected device has no g810-led keyboard backend.')
        profile = keyboard_profile(levels, color, d['rgb'])
        if not d['per_key']:
            if len(set(levels.values())) != 1:
                raise ValueError('This keyboard supports whole-board brightness, not per-key animation.')
            level = next(iter(levels.values()))
            value = ''.join(f'{round(c*level/255):02x}' for c in valid_color(color)) if d['rgb'] else f'{level:02x}'
            run_keyboard(d, ['-a', value])
        else:
            run_keyboard(d, ['-pp'], profile)
        self.last_keyboard = (device_id,dict(levels),color)
        return 'Keyboard frame acknowledged by g810-led.'

    def apply_mouse(self, device_id, mode, color, brightness, period_ms, zone='all'):
        rgb = valid_color(color)
        if mode not in MODES or type(brightness) is not int or not 0 <= brightness <= 255 or type(period_ms) is not int or not 1000 <= period_ms <= 10000:
            raise ValueError('Invalid lighting mode, brightness or period.')
        d = self.selected(device_id)
        self.release_lighting()
        if d['backend'] == 'HID++ 8070':
            with G502Lighting(d['_endpoint']) as mouse:
                return mouse.apply(mode, color, brightness, period_ms, zone)
        if d['backend'] != 'ratbagd':
            raise ValueError('Selected device has no peripheral lighting backend.')
        leds = self.ratbag_leds(d['_ratbag'])
        target = [(p,v) for p,v in leds if zone == 'all' or str(v['Index']) == zone]
        if not target or any(MODES[mode] not in p['Modes'] for _,p in target):
            raise ValueError('Selected lighting zone/mode is not supported by this device.')
        if mode == 'static':
            rgb = tuple(round(c*brightness/255) for c in rgb)
        updates = [('Color','(uuu)',rgb), ('Brightness','u',brightness), ('EffectDuration','u',period_ms), ('Mode','u',MODES[mode])]
        changed = []
        try:
            for path, old in target:
                for name, sig, value in updates:
                    if old[name] != value:
                        self.set_prop(path,name,sig,value)
                        changed.append((path,name,sig,old[name]))
        except Exception:
            for path,name,sig,value in reversed(changed):
                self.set_prop(path,name,sig,value)
            raise
        if changed:
            self.call(d['_ratbag'],SERVICE+'.Device','Commit')
        return 'Lighting request accepted by ratbagd. Hardware commit is asynchronous, not confirmed.'

    def apply_scene(self, keyboard_id, levels, color, mouse_id, colors):
        if keyboard_id and (keyboard_id,levels,color) != self.last_keyboard:
            self.apply_keyboard(keyboard_id,levels,color)
        if mouse_id:
            d = self.selected(mouse_id)
            if d['backend'] != 'HID++ 8070':
                raise ValueError('Software frames require the verified G502 runtime backend.')
            if self.mouse_id != mouse_id:
                self.release_lighting()
                self.mouse = G502Lighting(d['_endpoint']).__enter__()
                self.mouse_id = mouse_id
            self.mouse.apply_frame(colors)
        return 'Runtime scene frame acknowledged.'

    def release_lighting(self):
        if self.mouse is not None:
            self.mouse.__exit__(None,None,None)
        self.mouse = None
        self.mouse_id = None
        self.last_keyboard = None

    def close(self):
        self.release_lighting()
        self.bus = None
        self.devices = {}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Read-only selected-device lighting diagnostics')
    parser.add_argument('--diagnose', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(DeviceManager().discover(), indent=2))
