"""G502 Spectrum HID++ 0x8070 runtime LED control; no onboard-profile writes.

Protocol references: libratbag hidpp20.c/h and OpenRGB G502 packet captures.
SetZoneEffect uses an enumerated zone effect INDEX, not the public effect ID.
"""
import fcntl
import os
from pathlib import Path
import select
import struct
import time

EFFECT_IDS = {'off': 0, 'static': 1, 'breathing': 10, 'cycle': 3}


def report_ids(descriptor):
    """Decode HID short items, skipping long items and payload bytes."""
    result = set()
    i = 0
    while i < len(descriptor):
        prefix = descriptor[i]
        i += 1
        if prefix == 0xfe:
            if i + 2 > len(descriptor):
                break
            i += 2 + descriptor[i]
            continue
        size = (0, 1, 2, 4)[prefix & 3]
        if i + size > len(descriptor):
            break
        if prefix == 0x85 and size == 1:
            result.add(descriptor[i])
        i += size
    return result


def g502_endpoints():
    found = []
    for node in sorted(Path('/sys/class/hidraw').glob('hidraw*')):
        try:
            if 'HID_ID=0003:0000046D:0000C332' not in (node/'device/uevent').read_text().splitlines():
                continue
            if 0x11 in report_ids((node/'device/report_descriptor').read_bytes()):
                found.append('/dev/' + node.name)
        except (FileNotFoundError, PermissionError):
            continue
    return found


def effect_payload(zone, effect_index, mode, color, brightness, period_ms):
    if mode not in EFFECT_IDS or type(zone) is not int or not 0 <= zone < 256 or type(effect_index) is not int or not 0 <= effect_index < 256:
        raise ValueError('Invalid lighting zone/effect.')
    if type(brightness) is not int or not 0 <= brightness <= 255 or type(period_ms) is not int or not 1000 <= period_ms <= 10000:
        raise ValueError('Brightness must be 0–255 and period 1000–10000 ms.')
    if not isinstance(color, str) or len(color) != 6 or any(c not in '0123456789abcdefABCDEF' for c in color):
        raise ValueError('RGB color must contain six hexadecimal digits.')
    p = bytearray(16)
    p[0], p[1] = zone, effect_index
    rgb = bytes.fromhex(color)
    if mode == 'static':
        p[2:5] = bytes(round(v * brightness / 255) for v in rgb)
        p[5] = 2
    elif mode == 'breathing':
        p[2:5] = rgb
        p[5:7] = period_ms.to_bytes(2, 'big')
        p[8] = max(1, round(brightness * 100 / 255))
    elif mode == 'cycle':
        p[7:9] = period_ms.to_bytes(2, 'big')
        p[9] = max(1, round(brightness * 100 / 255))
    # p[12] is persistence: 0 = runtime RAM; NEVER set the flash flag here.
    return bytes(p)


class G502Lighting:
    def __init__(self, path):
        self.path = path
        self.fd = None
        self.feature = None
        self.zones = []

    def __enter__(self):
        if self.path not in g502_endpoints():
            raise RuntimeError('Selected G502 HID++ endpoint is unavailable; refresh devices.')
        try:
            self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
            # Validate the opened descriptor too: hidraw names can be reused on replug.
            identity = struct.unpack('=IHH',fcntl.ioctl(self.fd,0x80084803,b'\0'*8))
            if identity != (3,0x046d,0xc332):
                raise RuntimeError('Opened HID device is not the selected USB G502 Spectrum.')
            self.feature = self.request(0, 0, b'\x80\x70')[0]
            if not self.feature:
                raise RuntimeError('G502 does not expose Color LED Effects 0x8070.')
            self.zones = self.read_zones()
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def request(self, feature, function, payload=b''):
        if len(payload) > 16:
            raise ValueError('HID++ payload exceeds long report size.')
        address = (function << 4) | 0xb  # Different software ID from ratbagd (0x8).
        packet = bytes((0x11, 0xff, feature, address)) + payload.ljust(16, b'\0')
        if os.write(self.fd, packet) != len(packet):
            raise RuntimeError('Incomplete G502 HID++ write.')
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.fd], [], [], max(0, deadline-time.monotonic()))
            if not ready:
                break
            try:
                reply = os.read(self.fd, 64)
            except BlockingIOError:
                continue
            if len(reply) < 7 or reply[0] not in (0x10, 0x11) or reply[1] != 0xff:
                continue
            if reply[2] in (0x8f, 0xff) and reply[3] == feature and reply[4] == address:
                raise RuntimeError(f'G502 rejected HID++ command {feature:02x}:{function:x} (error {reply[5]:02x}).')
            if reply[2] == feature and reply[3] == address:
                if reply[0] != 0x11 or len(reply) != 20:
                    raise RuntimeError('Truncated G502 HID++ long response.')
                return reply[4:]
        raise TimeoutError('G502 did not acknowledge the command. Close other lighting editors and refresh.')

    def read_zones(self):
        count = self.request(self.feature, 0)[0]
        if not 1 <= count <= 16:
            raise RuntimeError('Unexpected G502 lighting zone count.')
        zones = []
        for zone in range(count):
            info = self.request(self.feature, 1, bytes((zone,)))
            if info[0] != zone or not 1 <= info[3] <= 32:
                raise RuntimeError('Invalid G502 lighting zone information.')
            indexes = {}
            for index in range(info[3]):
                effect = self.request(self.feature, 2, bytes((zone, index)))
                if effect[:2] != bytes((zone, index)):
                    raise RuntimeError('G502 returned mismatched zone effect information.')
                effect_id = int.from_bytes(effect[2:4], 'big')
                for mode, known_id in EFFECT_IDS.items():
                    if effect_id == known_id:
                        indexes[mode] = index
            location = int.from_bytes(info[1:3], 'big')
            name = {1:'DPI indicators', 2:'Logo'}.get(location, f'LED {zone}')
            zones.append(dict(id=str(zone), name=name, modes=list(indexes), indexes=indexes))
        return zones

    def state(self, zone):
        data = self.request(self.feature, 0xe, bytes((zone,)))
        if data[0] != zone:
            raise RuntimeError('G502 returned a mismatched LED state.')
        return data

    def apply(self, mode, color, brightness, period_ms, zone='all'):
        if mode not in EFFECT_IDS or type(brightness) is not int or not 0 <= brightness <= 255:
            raise ValueError('Invalid mouse lighting mode or brightness.')
        if brightness == 0:
            mode = 'off'  # Firmware percentage 0 can mean full brightness, not blackout.
        targets = [z for z in self.zones if zone == 'all' or z['id'] == zone]
        if not targets or any(mode not in z['indexes'] for z in targets):
            raise ValueError('Selected LED or lighting mode is unavailable on this device.')
        updates = [(int(z['id']), effect_payload(int(z['id']), z['indexes'][mode], mode, color, brightness, period_ms)) for z in targets]
        previous = [(number, self.state(number)) for number, _ in updates]
        written = []
        try:
            for number, payload in updates:
                written.append(number)
                self.request(self.feature, 3, payload)
                actual = self.state(number)
                relevant = {'off':(1,), 'static':(1,2,3,4), 'breathing':(1,2,3,4,5,6,8), 'cycle':(1,7,8,9)}[mode]
                if any(actual[i] != payload[i] for i in relevant):
                    raise RuntimeError(f'G502 LED {number} acknowledged but current effect readback did not match.')
        except Exception as error:
            restore_errors = []
            for number, old in previous:
                if number in written:
                    try:
                        self.request(self.feature, 3, old[:12] + b'\0'*4)
                    except Exception as e:
                        restore_errors.append(str(e))
            if restore_errors:
                raise RuntimeError(f'{error} Previous lighting could not be fully restored: {"; ".join(restore_errors)}') from error
            raise
        return 'G502 acknowledged and verified current LED settings. Runtime RAM only; no onboard-profile commit.'
