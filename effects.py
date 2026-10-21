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
EFFECTS = {
    'static': 'Steady light', 'breathing': 'Breathing', 'wave': 'Horizontal wave',
    'vertical': 'Vertical wave', 'ripple': 'Concentric ripple', 'scanner': 'Scanner',
    'sparkle': 'Starlight', 'rain': 'Falling rain', 'checkerboard': 'Checkerboard',
    'wasd': 'WASD focus', 'custom': 'Selected keys', 'orbit': 'Orbit',
    'heartbeat': 'Heartbeat', 'diagonal': 'Diagonal sweep',
}
DEFAULTS = dict(effect='wave', brightness=180, speed=1.0, reverse=False,
                selected=['w', 'a', 's', 'd'], mouse_mode='breathing',
                mouse_color='00dcff', mouse_brightness=255, mouse_period=8000,
                mouse_zone='all')


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
    if type(s['reverse']) is not bool:
        raise ValueError('Reverse must be true or false.')
    if not isinstance(s['selected'], list) or any(not isinstance(k, str) or k not in KEY_NAMES for k in s['selected']):
        raise ValueError('Profile contains an unknown key.')
    if s['mouse_mode'] not in ('static', 'off', 'breathing', 'cycle') or s['mouse_zone'] not in ('all', '0', '1'):
        raise ValueError('Unknown mouse mode or LED index.')
    color = s['mouse_color']
    if not isinstance(color, str) or len(color) != 6 or any(c not in '0123456789abcdefABCDEF' for c in color):
        raise ValueError('Mouse color must have six hexadecimal digits.')
    return {k: s[k] for k in DEFAULTS}


def frame(settings, seconds):
    s = settings
    t = seconds * s['speed'] * (-1 if s['reverse'] else 1)
    selected = set(s['selected'])
    result = {}
    for i, k in enumerate(KEYS):
        x, y = k.x + k.w / 2, k.y + k.h / 2
        phase = 2 * math.pi
        effect = s['effect']
        if effect == 'static':
            v = 1
        elif effect == 'breathing':
            v = (1 - math.cos(t * phase / 4)) / 2
        elif effect == 'wave':
            v = ((1 + math.sin(x / 4 - t * 2)) / 2) ** 2
        elif effect == 'vertical':
            v = ((1 + math.sin(y - t * 2)) / 2) ** 2
        elif effect == 'diagonal':
            v = ((1 + math.sin(x / 3 + y - t * 2)) / 2) ** 4
        elif effect == 'ripple':
            v = ((1 + math.cos(math.hypot((x - 11) / 2, y - 4) * 1.8 - t * 3)) / 2) ** 4
        elif effect == 'scanner':
            center = 11.5 + 11.5 * math.sin(t)
            v = math.exp(-((x - center) / 2) ** 2)
        elif effect == 'sparkle':
            v = max(0, math.sin(i * 12.9898 + t * (1 + (i % 7) / 8))) ** 24
        elif effect == 'rain':
            head = (t * 3 + math.sin(math.floor(x) * 73) * 17) % 11
            v = max(0, 1 - ((head - y) % 11) / 3)
        elif effect == 'checkerboard':
            v = 1 if (math.floor(x) + math.floor(y) + math.floor(t * 2)) % 2 == 0 else .08
        elif effect == 'wasd':
            v = 1 if k.name in ('w', 'a', 's', 'd', 'arrow_top', 'arrow_bottom', 'arrow_left', 'arrow_right') else .07
        elif effect == 'custom':
            v = 1 if k.name in selected else 0
        elif effect == 'orbit':
            angle = math.atan2(y - 4, (x - 11) / 2)
            v = ((1 + math.cos(angle - t * 2)) / 2) ** 8
        elif effect == 'heartbeat':
            p = t % 2
            v = min(1, math.exp(-((p - .3) / .1) ** 2) + .7 * math.exp(-((p - .65) / .12) ** 2))
        else:
            raise ValueError('Unknown effect.')
        result[k.name] = max(0, min(s['brightness'], round(v * s['brightness'])))
    return result


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
