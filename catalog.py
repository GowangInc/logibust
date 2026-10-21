"""Device library metadata, kept separate from live capability discovery."""
import json
from pathlib import Path

# USB IDs and command capabilities from g810-led's udev rules and help.h.
KEYBOARD_MODELS = {
    '046d:c336': ('Logitech G213 Prodigy', 'g213-led', True, False),
    '046d:c330': ('Logitech G410 Atlas Spectrum', 'g410-led', True, True),
    '046d:c33a': ('Logitech G413', 'g413-led', False, False),
    '046d:c342': ('Logitech G512', 'g512-led', True, True),
    '046d:c33c': ('Logitech G513', 'g513-led', True, True),
    '046d:c333': ('Logitech G610 Orion Brown', 'g610-led', False, True),
    '046d:c338': ('Logitech G610 Orion Red', 'g610-led', False, True),
    '046d:c331': ('Logitech G810 Orion Spectrum', 'g810-led', True, True),
    '046d:c337': ('Logitech G810 Orion Spectrum', 'g810-led', True, True),
    '046d:c33f': ('Logitech G815 LIGHTSYNC', 'g815-led', True, True),
    '046d:c32b': ('Logitech G910 Orion Spark', 'g910-led', True, True),
    '046d:c335': ('Logitech G910 Orion Spectrum', 'g910-led', True, True),
    '046d:c339': ('Logitech G Pro Keyboard', 'gpro-led', True, True),
}


def load_catalog():
    data = json.loads((Path(__file__).parent/'data/catalog.json').read_text())
    records = []
    for item in data['devices']:
        records.append(dict(item, connected=False, ready=False, rgb=False, per_key=False,
            modes=[], leds=[], detail='Not connected · catalog reference. Lighting capabilities are checked only when connected.'))
    for usb_id, (name, _, rgb, per_key) in KEYBOARD_MODELS.items():
        records = [d for d in records if usb_id not in d['usb_ids']]
        records.append(dict(id='catalog:'+usb_id, name=name, vendor='Logitech', kind='keyboard',
            usb_ids=[usb_id], backend='g810-led', connected=False, ready=False, rgb=rgb,
            per_key=per_key, modes=['off','static'], leds=[],
            source='https://github.com/MatMoul/g810-led',
            detail='Not connected · g810-led keyboard model. Preview only until connected.'))
    return sorted(records, key=lambda d:(d['vendor'].casefold(), d['name'].casefold(), d['id']))


def merge_devices(discovered, catalog):
    """Live instances win over library entries; never deduplicate two live devices."""
    live_ids = {usb for device in discovered if device['connected'] for usb in device.get('usb_ids', [])}
    live_names = {d['name'].casefold() for d in discovered if d['connected']}
    offline = [d for d in catalog if not live_ids.intersection(d.get('usb_ids', [])) and d['name'].casefold() not in live_names]
    live = sorted(discovered, key=lambda d:(not d['connected'], not d['ready'],
        0 if '046d:c338' in d.get('usb_ids', []) else 1, d['name'].casefold(), d['id']))
    return live + offline
