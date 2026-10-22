#!/usr/bin/python3
"""Run with /usr/bin/python3 selfcheck.py. No devices touched."""
import json
import tempfile
import threading
from pathlib import Path
from effects import DEFAULTS, EFFECTS, SCENES, REACTIVE_EFFECTS, SOFTWARE_EFFECTS, KEYS, KEY_NAMES, Profiles, frame, mouse_frame, validate
from devices import keyboard_profile
from app import DeviceIO
from catalog import load_catalog, merge_devices
from hidpp import effect_payload, report_ids
from reactive import _monitors

assert len(KEY_NAMES) == len(KEYS), 'Duplicate physical key identifier'
assert validate({})['selected'] == []
assert not any(frame({**DEFAULTS, 'effect':'custom'}, 0).values()), 'Empty selection lights keys'
silent_inputs = {'audio': {'level': 0, 'bands': (0, 0, 0), 'beat': 0},
                 'screen': {'width': 2, 'height': 1, 'pixels': [(0, 0, 0), (0, 0, 0)]},
                 'keys': ()}
reactive = {**DEFAULTS, 'effect': 'typing_ripple', 'brightness': 255}
baseline = frame(reactive, 0, silent_inputs)
assert frame(reactive, 0, silent_inputs) == baseline, 'Reactive frame is not deterministic'
assert not any(baseline.values()), 'Reactive silence should remain dark'
key_xy = (KEYS[0].x + KEYS[0].w / 2, KEYS[0].y + KEYS[0].h / 2)
key_snapshot = {**silent_inputs, 'keys': ((*key_xy, 0),)}
key_frame = frame(reactive, 0, key_snapshot)
assert key_frame[KEYS[0].name] == 255, 'Physical key origin was not brightest'
later_key_frame = frame(reactive, 0, {**silent_inputs, 'keys': ((*key_xy, .5),)})
assert later_key_frame[KEYS[0].name] < key_frame[KEYS[0].name], 'Typing ripple did not decay'
assert later_key_frame['f2'] > key_frame['f2'], 'Ring did not reach a neighboring key after leaving its origin'
overlap = frame(reactive, 0, {**silent_inputs, 'keys': ((*key_xy, 0), (*key_xy, 0))})
assert overlap == key_frame, 'Overlapping key events did not retain the strongest ring'
second_xy = (KEYS[-1].x + KEYS[-1].w / 2, KEYS[-1].y + KEYS[-1].h / 2)
two_origins = frame(reactive, 0, {**silent_inputs, 'keys': ((*key_xy, 0), (*second_xy, 0))})
assert two_origins[KEYS[-1].name] == 255, 'Simultaneous physical origins were lost'
expired = frame(reactive, 0, {**silent_inputs, 'keys': ((*key_xy, DEFAULTS['reactive_decay']),)})
assert not any(expired.values()), 'Typing ripple survived its configured lifetime'
audio_frame = frame({**reactive, 'effect': 'audio_level'}, 0, {**silent_inputs, 'audio': {'level': 1, 'bands': (0, 0, 0), 'beat': 0}})
assert all(v == 255 for v in audio_frame.values()), 'Audio level did not reach full-scale brightness'
assert not any(frame({**reactive, 'effect': 'audio_level'}, 0, silent_inputs).values()), 'Audio silence was not dark'
band_frame = frame({**reactive, 'effect': 'audio_spectrum'}, 0, {**silent_inputs, 'audio': {'level': 0, 'bands': (1, 0, 0), 'beat': 0}})
left = [v for k,v in band_frame.items() if next(key for key in KEYS if key.name == k).x < 8]
right = [v for k,v in band_frame.items() if next(key for key in KEYS if key.name == k).x >= 16]
assert max(left) > 0 and not any(right), 'Audio low band did not stay spatially local'
mid_mouse = mouse_frame({**DEFAULTS,'mouse_mode':'audio_spectrum'},0,
    {**silent_inputs,'audio':{'bands':(0,1,0)}})
assert mid_mouse['0']==mid_mouse['1'] and 0<max(mid_mouse['0'])<255, 'Mouse spectrum dropped the mid band'
screen_snapshot = {**silent_inputs, 'screen': {'width': 2, 'height': 1, 'pixels': [(255, 0, 0), (0, 0, 255)]}}
screen_frame = frame({**reactive, 'effect': 'screen_map'}, 0, screen_snapshot)
left = [v for k,v in screen_frame.items() if next(key for key in KEYS if key.name == k).x < 12]
right = [v for k,v in screen_frame.items() if next(key for key in KEYS if key.name == k).x >= 12]
assert max(left) > max(right), 'Screen map did not preserve spatial luminance'
screen_mouse = mouse_frame({**DEFAULTS, 'mouse_mode':'screen_map', 'mouse_brightness':255}, 0, screen_snapshot)
assert screen_mouse == {'0':(255,0,0),'1':(0,0,255)}, 'Mouse screen map lost screen-side colors'
mouse_settings = {**DEFAULTS, 'mouse_mode': 'static', 'mouse_color': '123456', 'mouse_brightness': 255, 'mouse_zone': '0'}
mouse = mouse_frame(mouse_settings, 0)
assert set(mouse) == {'0', '1'} and mouse['0'] == (18, 52, 86) and mouse['1'] == (18, 52, 86), 'Mouse renderer did not return both zones'
off_mouse = mouse_frame({**mouse_settings, 'mouse_mode': 'off'}, 0)
assert all(color == (0, 0, 0) for color in off_mouse.values()), 'Mouse off profile is not dark'
breathing_mouse = {**mouse_settings, 'mouse_mode': 'breathing'}
assert mouse_frame(breathing_mouse, 0) != mouse_frame(breathing_mouse, 2), 'Mouse breathing profile does not animate'
cycle_mouse = {**mouse_settings, 'mouse_mode': 'cycle'}
assert mouse_frame(cycle_mouse, 0) != mouse_frame(cycle_mouse, 2), 'Mouse cycle profile does not animate'
assert validate({'mouse_zone':'7'})['mouse_zone'] == '7'
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
    if effect not in ('static', 'wasd', 'custom', *REACTIVE_EFFECTS):
        assert any(frame(settings, .125) != frame(settings, t) for t in (.625, 1.371)), effect+' does not animate'
for mode in SOFTWARE_EFFECTS:
    for brightness in (0,1,128,255):
        settings = validate({**DEFAULTS,'mouse_mode':mode,'mouse_brightness':brightness})
        for t in (-99,0,.125,1,10000):
            colors = mouse_frame(settings,t,silent_inputs)
            assert all(type(v) is int and 0<=v<=brightness for rgb in colors.values() for v in rgb)
            if mode in REACTIVE_EFFECTS:
                assert all(rgb==(0,0,0) for rgb in colors.values()), 'Silent reactive mouse effect was not dark'
    if mode in SCENES:
        assert any(mouse_frame(settings,0)!=mouse_frame(settings,t) for t in (1,3,7,11,12)), mode+' mouse scene is static'
comet = {**DEFAULTS,'mouse_mode':'comet'}
dpi_phase = mouse_frame(comet,25/2.4)
logo_phase = mouse_frame(comet,29/2.4)
assert sum(dpi_phase['0'])>sum(dpi_phase['1']) and sum(logo_phase['1'])>sum(logo_phase['0']), 'Comet did not hand off DPI then logo'

selected = validate({**DEFAULTS, 'effect': 'custom', 'selected': ['w', 'space'], 'brightness': 128})
assert {k for k, v in frame(selected, 0).items() if v} == {'w', 'space'}
assert all(v == 128 for v in frame({**DEFAULTS, 'effect':'static', 'brightness':128}, 1).values())
assert frame({**DEFAULTS, 'effect':'wave', 'reverse':True}, 1) == frame({**DEFAULTS, 'effect':'wave'}, -1)

for bad in [dict(speed=float('nan')), dict(speed=True), dict(brightness=256), dict(mouse_period=20000), dict(mouse_color='gg0000'), dict(keyboard_color='nope'), dict(mouse_zone='7\\nc'), dict(selected=['not_a_key']), dict(effect=[]), dict(reverse='yes')]:
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

# G502 advertises breathing ID 10 at effect INDEX 2; wire command needs index 2.
breathing = effect_payload(1, 2, 'breathing', 'ff0000', 128, 4000)
assert breathing[:9] == bytes((1,2,255,0,0,15,160,0,50))
assert breathing[12] == 0, 'Lighting request would persist to flash'
cycle = effect_payload(0, 3, 'cycle', '000000', 255, 1000)
assert cycle[7:10] == bytes((3,232,100)) and cycle[12] == 0
assert report_ids(b'\xfe\x02\x00\x85\x11\x85\x10') == {0x10}, 'Payload bytes mistaken for report ID'

catalog = load_catalog()
g610 = next(d for d in catalog if '046d:c338' in d['usb_ids'])
other = next(d for d in catalog if d['vendor']=='SteelSeries')
live = dict(g610,id='usb:one',connected=True,ready=True)
second = dict(live,id='usb:two')
merged = merge_devices([live,second],[g610,other])
assert {d['id'] for d in merged if '046d:c338' in d['usb_ids']} == {'usb:one','usb:two'}
assert all(d['connected'] for d in merged[:2]) and not merged[-1]['ready']

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

# Monitor names alone must never turn a microphone into a speaker-output source.
source_records = [
    {'index':3,'name':'speakers.monitor'},
    {'index':4,'name':'headphone monitor custom'},
    {'index':5,'name':'microphone.monitor'},
    {'index':6,'name':'3'},
]
sink_records = [
    {'name':'headphones','monitor_source':'headphone monitor custom'},
    {'name':'speakers','monitor_source':3},
    {'name':'no-monitor'},
]
def monitor_fixture(command):
    if command[-1]=='get-default-sink':
        return b'speakers'
    return json.dumps(source_records if command[-1]=='sources' else sink_records).encode()
assert [name for name,_ in _monitors(monitor_fixture)]==['speakers.monitor','headphone monitor custom'], 'Monitor discovery misclassified a microphone or lost the default sink'

print(f'PASS: {len(EFFECTS)} effects, empty selection, profiles, G502 runtime packets, catalog/live-instance merging, safe driver frames and blackout failure ordering.')
