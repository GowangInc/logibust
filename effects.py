"""White-only G610 animation frames. Key identifiers follow g810-led --help-keys."""
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path


@dataclass(frozen=True)
class Key:
    name: str
    label: str
    x: float
    y: float
    w: float = 1
    h: float = 1


KEYS = []

def row(y, entries, start=0):
    x = start
    for entry in entries:
        name, label, width = entry if isinstance(entry, tuple) else (entry, entry.upper(), 1)
        if name:
            KEYS.append(Key(name, label, x, y, width))
        x += width


row(0, [('logo', 'G', 1), ('', '', 16), ('previous', 'Prev', 1), ('play_pause', 'Play', 1), ('stop', 'Stop', 1), ('next', 'Next', 1), ('mute', 'Mute', 1)])
row(1.3, [('escape', 'Esc', 1), ('', '', 1)] + ['f'+str(i) for i in range(1, 5)] + [('', '', .5)] + ['f'+str(i) for i in range(5, 9)] + [('', '', .5)] + ['f'+str(i) for i in range(9, 13)])
row(1.3, [('print_screen', 'PrtSc', 1), ('scroll_lock', 'ScrLk', 1), ('pause_break', 'Pause', 1)], 15.5)
row(2.6, [('tilde', '`', 1)] + list('1234567890') + [('minus', '-', 1), ('equal', '=', 1), ('backspace', 'Back', 2)])
row(3.6, [('tab', 'Tab', 1.5)] + list('qwertyuiop') + [('open_bracket', '[', 1), ('close_bracket', ']', 1), ('backslash', '\\', 1.5)])
row(4.6, [('caps_lock', 'Caps', 1.75)] + list('asdfghjkl') + [('semicolon', ';', 1), ('quote', "'", 1), ('enter', 'Enter', 2.25)])
row(5.6, [('shift_left', 'Shift', 2.25)] + list('zxcvbnm') + [('comma', ',', 1), ('period', '.', 1), ('slash', '/', 1), ('shift_right', 'Shift', 2.75)])
row(6.6, [('ctrl_left', 'Ctrl', 1.25), ('win_left', 'Win', 1.25), ('alt_left', 'Alt', 1.25), ('space', 'Space', 6.25), ('alt_right', 'Alt', 1.25), ('win_right', 'Win', 1.25), ('menu', 'Menu', 1.25), ('ctrl_right', 'Ctrl', 1.25)])
row(2.6, [('insert', 'Ins', 1), ('home', 'Home', 1), ('page_up', 'PgUp', 1)], 15.5)
row(3.6, [('delete', 'Del', 1), ('end', 'End', 1), ('page_down', 'PgDn', 1)], 15.5)
row(5.6, [('arrow_top', 'Up', 1)], 16.5)
row(6.6, [('arrow_left', 'Left', 1), ('arrow_bottom', 'Down', 1), ('arrow_right', 'Right', 1)], 15.5)
row(2.6, [('num_lock', 'Num', 1), ('num_slash', '/', 1), ('num_asterisk', '*', 1), ('num_minus', '-', 1)], 19)
row(3.6, ['num7', 'num8', 'num9'], 19)
row(4.6, ['num4', 'num5', 'num6'], 19)
row(5.6, ['num1', 'num2', 'num3'], 19)
row(6.6, [('num0', '0', 2), ('num_dot', '.', 1)], 19)
KEYS.extend([Key('num_plus', '+', 22, 3.6, 1, 2), Key('numenter', 'Enter', 22, 5.6, 1, 2)])
# Additional ISO/Brazilian physical positions are independently addressable.
row(8, [('intl_backslash', 'ISO \\', 1.6), ('dollar', 'ISO $', 1.6), ('abnt_slash', 'ABNT /', 1.6)])
KEY_NAMES = frozenset(k.name for k in KEYS)
BASE_EFFECTS = {
    'static': 'Steady light', 'breathing': 'Breathing', 'wave': 'Horizontal wave',
    'vertical': 'Vertical wave', 'ripple': 'Concentric ripple', 'scanner': 'Scanner',
    'sparkle': 'Starlight', 'rain': 'Falling rain', 'checkerboard': 'Checkerboard',
    'wasd': 'WASD focus', 'custom': 'Selected keys', 'orbit': 'Orbit',
    'heartbeat': 'Heartbeat', 'diagonal': 'Diagonal sweep',
}
SCENES = {
    'aurora': 'Aurora Drift', 'ember': 'Ember Bed', 'ocean': 'Ocean Glass',
    'lava': 'Lava Cells', 'interference': 'Interference', 'eclipse': 'Eclipse',
    'gravity': 'Gravity Well', 'comet': 'Comet Relay',
}
REACTIVE_EFFECTS = {
    'audio_level': 'Audio level', 'audio_spectrum': 'Audio spectrum', 'audio_pulse': 'Audio pulse',
    'screen_ambient': 'Screen ambient', 'screen_map': 'Screen map', 'typing_ripple': 'Typing ripple',
}
SOFTWARE_EFFECTS = {**SCENES, **REACTIVE_EFFECTS}
EFFECTS = {**BASE_EFFECTS, **SOFTWARE_EFFECTS}
DEFAULTS = dict(effect='wave', brightness=180, speed=1.0, reverse=False,
                selected=[], keyboard_color='ffffff', mouse_mode='breathing',
                mouse_color='00dcff', mouse_brightness=255, mouse_period=8000,
                mouse_zone='all', reactive_gain=1.0, reactive_decay=1.8,
                link_devices=False)


def validate(settings):
    if not isinstance(settings, dict):
        raise ValueError('Profile must be an object.')
    s = {**DEFAULTS, **settings}
    if not isinstance(s['effect'], str) or s['effect'] not in EFFECTS:
        raise ValueError('Unknown keyboard effect.')
    for field, lo, hi in [('brightness', 0, 255), ('mouse_brightness', 0, 255), ('mouse_period', 1000, 10000)]:
        if type(s[field]) is not int or not lo <= s[field] <= hi:
            raise ValueError(f'{field} must be an integer from {lo} to {hi}.')
    if type(s['speed']) not in (float, int) or not math.isfinite(s['speed']) or not .2 <= s['speed'] <= 3:
        raise ValueError('Speed must be between 0.2 and 3.')
    for field, lo, hi in [('reactive_gain', .2, 5), ('reactive_decay', .3, 5)]:
        if type(s[field]) not in (float, int) or not math.isfinite(s[field]) or not lo <= s[field] <= hi:
            raise ValueError(f'{field} must be between {lo} and {hi}.')
    if type(s['link_devices']) is not bool:
        raise ValueError('link_devices must be true or false.')
    if type(s['reverse']) is not bool:
        raise ValueError('Reverse must be true or false.')
    if not isinstance(s['selected'], list) or any(not isinstance(k, str) or k not in KEY_NAMES for k in s['selected']):
        raise ValueError('Profile contains an unknown key.')
    zone = s['mouse_zone']
    if s['mouse_mode'] not in ('static', 'off', 'breathing', 'cycle', *SOFTWARE_EFFECTS) or not isinstance(zone, str) or not (zone == 'all' or (zone.isascii() and zone.isdecimal() and 0 <= int(zone) < 256)):
        raise ValueError('Unknown mouse mode or LED index.')
    for field in ('mouse_color', 'keyboard_color'):
        color = s[field]
        if not isinstance(color, str) or len(color) != 6 or any(c not in '0123456789abcdefABCDEF' for c in color):
            raise ValueError(f'{field} must have six hexadecimal digits.')
    return {k: s[k] for k in DEFAULTS}


def _clamp(v):
    return max(0.0, min(1.0, v))


def _audio(inputs):
    return (inputs or {}).get('audio') or {}


def _screen(inputs):
    return (inputs or {}).get('screen') or {}


def _reactive_value(effect, x, y, inputs, settings):
    gain, decay = settings['reactive_gain'], settings['reactive_decay']
    audio, screen = _audio(inputs), _screen(inputs)
    if effect == 'audio_level':
        return _clamp(float(audio.get('level', 0) or 0) * gain)
    if effect == 'audio_spectrum':
        bands = audio.get('bands', (0, 0, 0))
        band = bands[min(2, max(0, int(x / 8)))] if len(bands) >= 3 else 0
        return _clamp(float(band or 0) * gain)
    if effect == 'audio_pulse':
        return _clamp(float(audio.get('beat', 0) or 0) * gain)
    if effect in ('screen_ambient', 'screen_map'):
        w, h, pixels = screen.get('width', 0), screen.get('height', 0), screen.get('pixels', ())
        if not w or not h or len(pixels) != w * h:
            return 0
        if effect == 'screen_ambient':
            return _clamp(sum((.2126*r + .7152*g + .0722*b) / 255 for r,g,b in pixels) / len(pixels) * gain)
        sx = min(w-1, max(0, int(x / 24 * w)))
        sy = min(h-1, max(0, int(y / 8 * h)))
        r,g,b = pixels[sy*w+sx]
        return _clamp((.2126*r + .7152*g + .0722*b) / 255 * gain)
    if effect == 'typing_ripple':
        v = 0.0
        for kx, ky, age in (inputs or {}).get('keys', ()):
            if age < 0 or age >= decay:
                continue
            d = math.hypot((x-kx)/2, y-ky)
            radius = age * 5 * settings['speed']
            v = max(v, math.exp(-age / decay) * math.exp(-((d-radius)/1.1)**2))
        return _clamp(v * gain)
    return 0


def frame(settings, seconds, inputs=None):
    s = settings
    t = seconds * s['speed'] * (-1 if s['reverse'] else 1)
    selected = set(s['selected'])
    result = {}
    ambient = _reactive_value('screen_ambient',0,0,inputs,s) if s['effect']=='screen_ambient' else 0
    particles = []
    if s['effect']=='gravity':
        for offset in (0, .33, .67):
            for trail in (0, .035, .07, .105):
                progress = (t*.15+offset-trail)%1
                radius = 6.5*(1-progress)
                angle = offset*math.tau+progress*math.tau*1.8
                particles.append((11.5+1.7*radius*math.cos(angle),
                    4+.55*radius*math.sin(angle),math.exp(-trail*13)))
    for i, k in enumerate(KEYS):
        x, y = k.x + k.w / 2, k.y + k.h / 2
        phase = 2 * math.pi
        effect = s['effect']
        if effect == 'static': v = 1
        elif effect == 'breathing': v = (1 - math.cos(t * phase / 4)) / 2
        elif effect == 'wave': v = ((1 + math.sin(x / 4 - t * 2)) / 2) ** 2
        elif effect == 'vertical': v = ((1 + math.sin(y - t * 2)) / 2) ** 2
        elif effect == 'diagonal': v = ((1 + math.sin(x / 3 + y - t * 2)) / 2) ** 4
        elif effect == 'ripple': v = ((1 + math.cos(math.hypot((x - 11) / 2, y - 4) * 1.8 - t * 3)) / 2) ** 4
        elif effect == 'scanner':
            center = 11.5 + 11.5 * math.sin(t)
            v = math.exp(-((x - center) / 2) ** 2)
        elif effect == 'sparkle': v = max(0, math.sin(i * 12.9898 + t * (1 + (i % 7) / 8))) ** 24
        elif effect == 'rain':
            head = (t * 3 + math.sin(math.floor(x) * 73) * 17) % 11
            v = max(0, 1 - ((head - y) % 11) / 3)
        elif effect == 'checkerboard': v = 1 if (math.floor(x) + math.floor(y) + math.floor(t * 2)) % 2 == 0 else .08
        elif effect == 'wasd': v = 1 if k.name in ('w', 'a', 's', 'd', 'arrow_top', 'arrow_bottom', 'arrow_left', 'arrow_right') else .07
        elif effect == 'custom': v = 1 if k.name in selected else 0
        elif effect == 'orbit':
            angle = math.atan2(y - 4, (x - 11) / 2)
            v = ((1 + math.cos(angle - t * 2)) / 2) ** 8
        elif effect == 'heartbeat':
            p = t % 2
            v = min(1, math.exp(-((p - .3) / .1) ** 2) + .7 * math.exp(-((p - .65) / .12) ** 2))
        elif effect == 'aurora': v = .08 + .92 * (((1 + math.sin(x*.33 + math.sin(y*.8+t*.5)*2-t)) / 2) ** 3) * (.35 + .65*math.sin(y*.45-t*.7)**2)
        elif effect == 'ember':
            phase0 = (t * .55 + math.sin(math.floor(x*1.7)*91.7)*5 + math.sin(x*2.13)*1.7) % 9
            rise_y = 7.5 - phase0 * .85
            spark_center = math.sin(math.floor(x*1.7)*17.3) * .22 + math.floor(x*1.7)*.58
            v = max(0, 1-abs(x-spark_center)/1.15) ** 2 * max(0, 1-abs(y-rise_y)/1.5) ** 2 * (.55+.45*abs(math.sin(i*12.7+t*.7)))
        elif effect == 'ocean': v = .12 + .88 * max(0, math.sin(x*.75+y*.9+t*1.6)*math.sin(x*.35-y*1.1-t))**3
        elif effect == 'lava':
            cx1, cy1 = 5 + 2.8*math.sin(t*.31), 3.5 + 1.5*math.sin(t*.24)
            cx2, cy2 = 18 + 3.5*math.sin(t*.27+2), 4 + 1.7*math.cos(t*.2)
            d1 = math.hypot((x-cx1)/2.4, y-cy1)
            d2 = math.hypot((x-cx2)/2.4, y-cy2)
            blob = max(math.exp(-(d1/2.8)**2), math.exp(-(d2/3.1)**2), .82*math.exp(-(math.hypot((x-(cx1+cx2)/2)/2.4,y-(cy1+cy2)/2)/2.6)**2))
            v = _clamp((blob-.2)*1.35)
        elif effect == 'interference': v = ((1+math.cos(math.hypot(x-7,y-3)*1.25-t*2)*math.cos(math.hypot(x-17,y-5)*1.1-t*1.6))/2)**2
        elif effect == 'eclipse':
            d = math.hypot((x-(11.5+3*math.sin(t*.2)))/1.8,y-4)
            v = .04 + .96*math.exp(-((d-1.3)/.32)**2)
        elif effect == 'gravity':
            v = max(weight*math.exp(-(((x-px)/1.2)**2+(y-py)**2)/.65)
                for px,py,weight in particles)
        elif effect == 'comet':
            relay = (t*2.4) % 32
            if relay < 24:
                d = abs(x-relay)
                v = math.exp(-(d/1.5)**2) * (.75+.25*math.exp(-((y-3.5)/3)**2))
            elif relay < 27:
                v = math.exp(-((x-11.5)/4)**2) * math.exp(-((y-.2)/1.1)**2) * max(0,1-abs(relay-25.5)/1.5)
            else:
                v = math.exp(-((x-.5)/1.2)**2-((y-.5)/1.2)**2) * max(0,1-abs(relay-28.5)/1.5)
        elif effect=='screen_ambient': v = ambient
        elif effect in REACTIVE_EFFECTS: v = _reactive_value(effect,x,y,inputs,s)
        else: raise ValueError('Unknown effect.')
        result[k.name] = max(0, min(s['brightness'], round(_clamp(v) * s['brightness'])))
    return result


def mouse_frame(settings, seconds, inputs=None, mode=None):
    s = settings
    effect = mode or s['mouse_mode']
    if effect not in ('off', 'static', 'breathing', 'cycle', *SOFTWARE_EFFECTS):
        raise ValueError('Unknown mouse mode.')
    brightness = s['mouse_brightness']
    if effect == 'off' or brightness == 0:
        return {'0': (0,0,0), '1': (0,0,0)}
    t = seconds * s['speed'] * (-1 if s['reverse'] else 1)
    colors = []
    for zone in (0, 1):
        x = 6 if zone == 0 else 18
        if effect in REACTIVE_EFFECTS:
            if effect == 'screen_ambient':
                pixels = _screen(inputs).get('pixels', ())
                rgb = tuple(round(min(255, max(0, sum(p[c] for p in pixels) / len(pixels) * s['reactive_gain'])) * brightness / 255) for c in range(3)) if pixels else (0, 0, 0)
            elif effect == 'screen_map':
                screen = _screen(inputs)
                w, h, pixels = screen.get('width', 0), screen.get('height', 0), screen.get('pixels', ())
                if w and h and len(pixels) == w*h:
                    sx = min(w-1, max(0, int((zone*12+6) / 24 * w)))
                    rows = [pixels[y*w+sx] for y in range(h)]
                    rgb = tuple(round(min(255, max(0, sum(pixel[c] for pixel in rows) / len(rows) * s['reactive_gain'])) * brightness / 255) for c in range(3))
                else:
                    rgb = (0, 0, 0)
            else:
                value = _reactive_value(effect,x,4,inputs,s)
                if effect=='audio_spectrum':
                    bands = _audio(inputs).get('bands',(0,0,0))
                    value = _clamp(max(bands[0 if zone==0 else 2],bands[1]*.7)*s['reactive_gain'])
                color = tuple(int(s['mouse_color'][i:i+2],16) for i in (0,2,4))
                rgb = tuple(round(c*value*brightness/255) for c in color)
        elif effect in SCENES:
            if effect == 'aurora':
                v=(1+math.sin(t*.7+zone*1.8))/2
                start,end = ((0,160,70),(0,230,220)) if zone==0 else ((25,65,210),(160,25,240))
                palette=tuple(round(a*(1-v)+b*v) for a,b in zip(start,end))
            elif effect == 'ember':
                v=max(.12,min(1,.55+.25*math.sin(t*.37+zone*2.7)+.2*math.sin(t*.13+zone*1.1)))
                palette=(255,round(30+120*v),round(3+16*v))
            elif effect == 'ocean':
                v=(1+math.sin(t*.65+zone*1.5))/2
                palette=tuple(round(a*(1-v)+b*v) for a,b in zip((0,55,190),(0,220,190)))
            elif effect == 'lava':
                v=(1+math.sin(t*.35+zone*1.3))/2
                palette=tuple(round(a*(1-v)+b*v) for a,b in zip((255,55,0),(210,0,130)))
            elif effect == 'interference':
                v=.5+.5*math.cos(t+zone*2)
                palette=tuple(round(a*(1-v)+b*v) for a,b in zip((25,0,150),(0,180,255)))
            elif effect == 'eclipse':
                phase = .5+.5*math.sin(t*.3)
                v = .08+.82*(phase if zone==0 else 1-phase)
                palette=(255,round(120*v),round(35*v))
            elif effect == 'gravity':
                v=.2+.8*abs(math.sin(t*1.1+zone*2))
                palette=(round(30+110*v),round(10+30*v),round(180+75*v))
            else:
                relay=(t*2.4)%32
                v=math.exp(-(((relay-(25 if zone==0 else 29))/1.6)**2))
                palette=(255,round(35+150*v),round(5+30*v))
            rgb=tuple(round(c*v*brightness/255) for c in palette)
        elif effect == 'static':
            color=tuple(int(s['mouse_color'][i:i+2],16) for i in (0,2,4))
            rgb=tuple(round(c*brightness/255) for c in color)
        elif effect == 'breathing':
            v=(1-math.cos(2*math.pi*t/(s['mouse_period']/1000)))/2
            color=tuple(int(s['mouse_color'][i:i+2],16) for i in (0,2,4))
            rgb=tuple(round(c*v*brightness/255) for c in color)
        elif effect == 'cycle':
            rgb=tuple(round((.5+.5*math.sin(t*2+zone*2*math.pi/3+i*2*math.pi/3))*brightness) for i in range(3))
        colors.append(tuple(max(0,min(255,int(c))) for c in rgb))
    return {'0':colors[0], '1':colors[1]}


class Profiles:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'logibust' / 'profiles.json'

    def load(self):
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text())
        if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('profiles'), dict):
            raise ValueError('Unsupported profile file. Original file has not been changed.')
        return {self.name(n): validate(s) for n, s in data['profiles'].items()}

    @staticmethod
    def name(value):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80 or any(ord(c) < 32 for c in value):
            raise ValueError('Use a profile name of 1–80 printable characters.')
        return value.strip()

    def save(self, name, settings):
        name, settings = self.name(name), validate(settings)
        profiles = self.load()  # Never overwrite a corrupt file with defaults.
        profiles[name] = settings
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.json.tmp')
        with temp.open('w') as f:
            json.dump(dict(version=1, profiles=profiles), f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        temp.replace(self.path)
