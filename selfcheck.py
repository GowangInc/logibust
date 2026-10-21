#!/usr/bin/python3
"""Run with /usr/bin/python3 selfcheck.py. No devices touched."""
import tempfile
import threading
from pathlib import Path
from effects import DEFAULTS, EFFECTS, KEYS, KEY_NAMES, Profiles, frame, validate
from devices import keyboard_profile
from app import DeviceIO

assert len(KEY_NAMES) == len(KEYS), 'Duplicate physical key identifier'
for effect in EFFECTS:
    settings = validate({**DEFAULTS, 'effect': effect})
    for brightness in (0, 1, 128, 255):
        settings['brightness'] = brightness
        for t in (-99, 0, .125, 1, 7, 10000):
            values = frame(settings, t)
            assert set(values) == KEY_NAMES
            assert all(type(v) is int and 0 <= v <= brightness for v in values.values())
            assert values == frame(settings, t), 'Effect depends on call order'
    settings['brightness'] = 255
    if effect not in ('static', 'wasd', 'custom'):
        assert any(frame(settings, .125) != frame(settings, t) for t in (.625, 1.371)), effect+' does not animate'

selected = validate({**DEFAULTS, 'effect': 'custom', 'selected': ['w', 'space'], 'brightness': 128})
assert {k for k, v in frame(selected, 0).items() if v} == {'w', 'space'}
assert all(v == 128 for v in frame({**DEFAULTS, 'effect':'static', 'brightness':128}, 1).values())
assert frame({**DEFAULTS, 'effect':'wave', 'reverse':True}, 1) == frame({**DEFAULTS, 'effect':'wave'}, -1)

for bad in [dict(speed=float('nan')), dict(speed=True), dict(brightness=256), dict(mouse_period=20000), dict(mouse_color='gg0000'), dict(selected=['not_a_key']), dict(effect=[]), dict(reverse='yes')]:
    try:
        validate({**DEFAULTS, **bad})
    except ValueError:
        pass
    else:
        raise AssertionError(f'Accepted malformed profile: {bad}')

with tempfile.TemporaryDirectory(prefix='logibust-check-') as directory:
    path = Path(directory)/'profiles.json'
    p = Profiles(path)
    p.save('Night', selected)
    p.save('Day', DEFAULTS)
    assert p.load()['Night'] == selected
    assert p.load()['Day'] == validate(DEFAULTS)
    corrupt = '{"version": 99, "profiles": {}}'
    path.write_text(corrupt)
    try:
        p.save('New', DEFAULTS)
    except ValueError:
        pass
    else:
        raise AssertionError('Overwrote unsupported profile file')
    assert path.read_text() == corrupt

profile = keyboard_profile(frame(selected, 0))
assert 'k w 80\n' in profile and 'k space 80\n' in profile and 'k a 00\n' in profile
try:
    keyboard_profile({'w':255, 'x\nc':255})
except ValueError:
    pass
else:
    raise AssertionError('Accepted incomplete/injected hardware frame')
# Explicit Off must survive an unplug failure in an older, in-flight frame.
io = DeviceIO()
entered, release, blacked = threading.Event(), threading.Event(), threading.Event()
def failed_frame(manager):
    entered.set()
    if not release.wait(5):
        raise TimeoutError('Self-check did not release the in-flight frame.')
    raise RuntimeError('Device disconnected.')
try:
    io.submit('keyboard', failed_frame, lambda *_: False)
    assert entered.wait(5)
    io.submit('blackout', lambda manager: blacked.set(), lambda *_: False)
    release.set()
    assert blacked.wait(5), 'Explicit blackout was discarded after an old frame failed.'
finally:
    release.set()
    io.close()

print(f'PASS: {len(EFFECTS)} effects, white intensity boundaries, direction, custom keys, profile persistence/corruption, safe driver frames and blackout failure ordering.')
