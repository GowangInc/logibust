"""Opt-in, memory-only speaker-monitor, X11 screen and physical-key inputs.

No source is enabled by constructing this object. Failed sources stay stopped until
explicitly disabled/reconfigured; selecting an effect never starts capture. Key
capture requires X11/XInput 2.1 and an exact USB-port-to-Device-Node match, not
access to /dev/input or a global keyboard listener. No grabs are made.
"""
from collections import deque
import json
import math
import os
from pathlib import Path
import re
import select
import struct
import subprocess
import sys
import threading
import time


_AUDIO_ZERO = {'level': 0.0, 'bands': (0.0, 0.0, 0.0), 'beat': 0.0}
_SCREEN_ZERO = {'width': 24, 'height': 12, 'pixels': ()}
_KEY_LIFETIME = 6.0
_KEY_PACKET = struct.Struct('!Bddd')


def _command(command):
    try:
        result = subprocess.run(command, capture_output=True, timeout=3, check=False)
    except (OSError,subprocess.TimeoutExpired) as error:
        raise RuntimeError('Output-monitor discovery failed: '+str(error)) from error
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace').strip() or
                           f'{command[0]} exited with status {result.returncode}')
    return result.stdout


def _monitors(run=_command):
    sources = json.loads(run(['pactl', '--format=json', 'list', 'sources']))
    sinks = json.loads(run(['pactl', '--format=json', 'list', 'sinks']))
    default = run(['pactl', 'get-default-sink']).decode().strip()
    by_name = {source['name']:source for source in sources}
    by_index = {str(source['index']):source for source in sources}
    monitors = []
    for sink in sinks:
        # PulseAudio uses a monitor index; PipeWire's pactl JSON uses its name.
        # Both are explicit sink->monitor relationships, never a name heuristic.
        reference = sink.get('monitor_source')
        if type(reference) is int:
            source = by_index.get(str(reference))
        elif isinstance(reference,str):
            source = by_name.get(reference)
        else:
            continue
        if source is None:
            continue
        name = source['name']
        label = source.get('description') or name
        monitors.append((sink['name'] != default,name,label))
    monitors.sort(key=lambda item: (item[0], item[2].casefold(), item[1]))
    return [(name, label) for _, name, label in monitors]


def audio_sources():
    """Return speaker-output monitors only, default sink's monitor first.

    PulseAudio/PipeWire discovery errors are deliberately surfaced to the UI.
    There is never a fallback to the default recording source (microphone).
    """
    return _monitors()


def _terminate(process):
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=.6)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        process.wait(timeout=.6)


class _Capture:
    """One independently cancellable source; its thread owns all pipe reads."""
    def __init__(self, kind, spec):
        self.kind = kind
        self.spec = spec
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.process = None
        self.value = None
        self.updated = 0.0
        self.message = 'starting'
        self.failed = False
        self.thread = threading.Thread(target=self._work, name='logibust-' + kind,
                                       daemon=True)
        self.thread.start()

    def publish(self, value):
        with self.lock:
            if not self.stopped.is_set():
                self.value = value
                self.updated = time.monotonic()
                self.message = 'live'

    def _work(self):
        try:
            {'audio': self._audio, 'screen': self._screen,
             'keyboard': self._keyboard}[self.kind]()
        except Exception as error:
            with self.lock:
                if not self.stopped.is_set():
                    self.value = None
                    self.updated = 0.0
                    self.failed = True
                    self.message = str(error).replace('\n', ' ')[:240]
        finally:
            with self.lock:
                process = self.process
            if process is not None:
                _terminate(process)

    def stop(self):
        # Clear the public value BEFORE waiting for any worker or process.
        with self.lock:
            self.stopped.set()
            self.value = None
            self.updated = 0.0
            process = self.process
        if process is not None:
            _terminate(process)
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            raise RuntimeError(f'{self.kind} capture did not stop within two seconds')

    def read(self, now):
        with self.lock:
            value, updated, message, failed = (self.value, self.updated,
                                             self.message, self.failed)
        ttl = .75 if self.kind == 'audio' else 1.0
        if value is not None and now - updated > ttl:
            return None, 'waiting for fresh input'
        return value, ('error: ' + message if failed else message)

    def _pipe(self, command, frame_size=None, consume=None, deadline=None):
        """Read bounded raw frames or a small command result, draining stderr.

        All subprocesses (including discovery commands) are registered for
        cancellation, have no stdin, and are reaped on every exit path.
        """
        with self.lock:
            if self.stopped.is_set():
                return b''
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       bufsize=0)
            self.process = process
        buffer = bytearray()
        errors = bytearray()
        output = bytearray()
        started = last_frame = time.monotonic()
        streams = [process.stdout, process.stderr]
        try:
            while not self.stopped.is_set():
                now = time.monotonic()
                if deadline is not None and now - started > deadline:
                    raise RuntimeError(f'{command[0]} discovery timed out')
                if frame_size is not None and now - last_frame > 3:
                    raise RuntimeError(f'{command[0]} stopped supplying capture frames')
                ready, _, _ = select.select(streams, [], [], .1)
                for stream in ready:
                    chunk = os.read(stream.fileno(), 16384)
                    if not chunk:
                        streams.remove(stream)
                    elif stream is process.stderr:
                        errors.extend(chunk)
                        del errors[:-4096]
                    elif frame_size is None:
                        output.extend(chunk)
                        if len(output) > 1024 * 1024:
                            raise RuntimeError('Capture discovery response exceeds 1 MiB')
                    else:
                        buffer.extend(chunk)
                        while len(buffer) >= frame_size:
                            if self.stopped.is_set():
                                return b''
                            consume(bytes(buffer[:frame_size]))
                            del buffer[:frame_size]
                            last_frame = time.monotonic()
                if not streams:
                    code = process.wait(timeout=.2)
                    detail = errors.decode(errors='replace').strip()
                    if code or frame_size is not None:
                        raise RuntimeError(detail or f'{command[0]} capture exited ({code})')
                    return bytes(output)
            return b''
        finally:
            _terminate(process)
            process.stdout.close()
            process.stderr.close()
            with self.lock:
                if self.process is process:
                    self.process = None

    def _query(self, command):
        result = self._pipe(command, deadline=3)
        if self.stopped.is_set():
            raise RuntimeError('Capture stopped')
        return result

    def _audio(self):
        import numpy as np
        monitors = _monitors(self._query)
        if not monitors:
            raise RuntimeError('No speaker-output monitor sources are available')
        source = self.spec or monitors[0][0]
        if source not in {item[0] for item in monitors}:
            raise RuntimeError('Selected speaker-output monitor is no longer available')
        size = 1024
        window = np.hanning(size)
        frequencies = np.fft.rfftfreq(size, 1 / 16000)
        masks = [(frequencies >= lo) & (frequencies < hi)
                 for lo, hi in ((20, 250), (250, 2000), (2000, 8001))]
        normalization = size * float(np.sum(window * window))
        smooth = np.zeros(4)
        baseline = beat = 0.0

        def consume(raw):
            nonlocal baseline, beat
            samples = np.frombuffer(raw, dtype='<f4')
            if not np.all(np.isfinite(samples)):
                raise RuntimeError('Audio monitor supplied non-finite samples')
            samples = samples.astype(np.float64)
            samples -= np.mean(samples)
            rms = math.sqrt(float(np.mean(samples * samples)))
            spectrum = np.abs(np.fft.rfft(samples * window)) ** 2
            bands = [math.sqrt(2 * float(np.sum(spectrum[mask])) / normalization)
                     for mask in masks]
            # Map -12 dBFS RMS to full lighting level; renderer gain remains
            # user-controlled, and true digital silence still produces zero.
            measured = np.clip(np.multiply([rms, *bands], 4.0), 0, 1)
            smooth[:] = np.maximum(measured, smooth * .72)
            bass = bands[0]
            onset = max(0, (bass - baseline * 1.35) / max(.015, baseline * 2))
            beat = min(1.0, max(onset, beat * .76))
            baseline = baseline * .94 + bass * .06
            self.publish({'level': float(smooth[0]),
                          'bands': tuple(float(v) for v in smooth[1:]), 'beat': beat})

        self._pipe(['parec', '--raw', '--device=' + source, '--format=float32le',
                    '--rate=16000', '--channels=1', '--channel-map=mono',
                    '--latency-msec=50', '--client-name=Logibust lighting'],
                   size * 4, consume)

    def _screen(self):
        display, x, y, width, height = self.spec

        def consume(raw):
            self.publish({'width': 24, 'height': 12,
                          'pixels': tuple(zip(raw[0::3], raw[1::3], raw[2::3]))})

        self._pipe(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                    '-threads', '1', '-f', 'x11grab', '-draw_mouse', '0',
                    '-framerate', '8', '-video_size', f'{width}x{height}',
                    '-i', f'{display}+{x},{y}', '-vf', 'scale=24:12:flags=area',
                    '-filter_threads', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo',
                    'pipe:1'], 24 * 12 * 3, consume)

    def _keyboard(self):
        recent = deque(maxlen=96)

        def consume(raw):
            kind, x, y, stamp = _KEY_PACKET.unpack(raw)
            now = time.monotonic()
            if kind == 1:
                recent.append((x, y, stamp))
            while recent and now - recent[0][2] > _KEY_LIFETIME:
                recent.popleft()
            self.publish(tuple(recent))

        # Isolate Xlib's synchronous connection/reply calls as well as event
        # capture: even a wedged X server cannot leave a thread behind on close.
        self._pipe([sys.executable, str(Path(__file__).resolve()), '--keyboard-worker',
                    json.dumps(self.spec)], _KEY_PACKET.size, consume)

    def _keyboard_events(self):
        from Xlib import display as xdisplay
        from Xlib.ext import xinput
        from Xlib.protocol import rq
        from evdev import ecodes
        from effects import KEYS

        port, usb_ids, display_name = self.spec
        usb = Path('/sys/bus/usb/devices') / port
        usb_token = _usb_identity(usb, usb_ids)
        centres = {key.name: (key.x + key.w / 2, key.y + key.h / 2) for key in KEYS}
        keymap = _keymap(ecodes, centres)
        connection = xdisplay.Display(display_name)
        try:
            extension = connection.query_extension(xinput.extname)
            if not extension or not extension.present:
                raise RuntimeError('XInput2 is unavailable on the selected X11 display')
            version = xinput.XIQueryVersion(display=connection.display,
                                           opcode=extension.major_opcode,
                                           major_version=2, minor_version=1)
            if (version.major_version, version.minor_version) < (2, 1):
                raise RuntimeError('Physical keyboard capture requires XInput 2.1')
            # python-xlib does not register raw-event parsers itself. This is
            # the fixed xXIRawEvent prefix after the ten-byte GE header; key
            # events have no valuator data, and no translated text is requested.
            raw_event = rq.Struct(rq.Card16('deviceid'), rq.Card32('time'),
                                  rq.Card32('detail'), rq.Card16('sourceid'),
                                  rq.Card16('valuators_len'), rq.Card32('flags'),
                                  rq.Pad(4))
            for event_type in (xinput.RawKeyPress, xinput.RawKeyRelease):
                connection.ge_add_event_data(extension.major_opcode, event_type, raw_event)
            atom = connection.intern_atom('Device Node', only_if_exists=True)
            if not atom:
                raise RuntimeError('XInput devices do not expose Device Node identity')
            devices = {}
            for device in connection.xinput_query_device(xinput.AllDevices).devices:
                if device.use != xinput.SlaveKeyboard or not device.enabled:
                    continue
                node = _device_node(connection, device.deviceid, atom)
                if node is None:
                    continue
                token = _input_identity(node, usb, usb_ids)
                if token is not None:
                    devices[device.deviceid] = (node, token)
            if not devices:
                raise RuntimeError('Selected USB keyboard has no verified XInput Device Node')
            root = connection.screen().root
            mask = xinput.RawKeyPressMask | xinput.RawKeyReleaseMask | xinput.PropertyEventMask
            root.xinput_select_events([(deviceid, mask) for deviceid in devices] +
                                      [(xinput.AllDevices, xinput.HierarchyChangedMask)])
            connection.sync()
            held = set()
            self.publish(())
            while not self.stopped.is_set():
                _verify_keyboard(connection, usb, usb_ids, usb_token, devices, atom)
                if not connection.pending_events():
                    select.select([connection.fileno()], [], [], .1)
                count = 0
                while not self.stopped.is_set() and connection.pending_events():
                    event = connection.next_event()
                    count += 1
                    if getattr(event, 'extension', None) != extension.major_opcode:
                        continue
                    event_type = getattr(event, 'evtype', None)
                    data = event.data
                    if event_type == xinput.HierarchyChanged:
                        if any(info.deviceid in devices and info.flags &
                               (xinput.SlaveRemoved | xinput.DeviceDisabled |
                                xinput.SlaveDetached | xinput.SlaveAttached)
                               for info in data.info):
                            raise RuntimeError('Selected keyboard changed or disconnected; re-enable capture')
                        continue
                    if event_type == xinput.PropertyEvent and data.deviceid in devices:
                        if data.property == atom:
                            raise RuntimeError('Selected keyboard Device Node changed; re-enable capture')
                        continue
                    if event_type not in (xinput.RawKeyPress, xinput.RawKeyRelease):
                        continue
                    if data.sourceid not in devices or data.deviceid not in devices:
                        continue
                    # Revalidate at the exact point of accepting a press; neither
                    # a reused event node nor a newly attached USB device inherits
                    # permission from the originally selected keyboard.
                    _verify_keyboard(connection, usb, usb_ids, usb_token, devices, atom,
                                     query=False)
                    identity = (data.sourceid, data.detail)
                    if event_type == xinput.RawKeyRelease:
                        held.discard(identity)
                    elif not data.flags & xinput.KeyRepeat and identity not in held:
                        held.add(identity)
                        centre = keymap.get(data.detail - 8)
                        if centre is not None:
                            self.keypress(*centre, time.monotonic())
                    if count >= 256:
                        break
                self.publish(())
        finally:
            connection.close()


class _KeyboardWorker:
    """Private pipe transport; packets contain positions/times, never keycodes."""
    def __init__(self, spec):
        self.spec = spec
        self.stopped = threading.Event()

    def publish(self, _value):
        os.write(sys.stdout.fileno(), _KEY_PACKET.pack(0, 0, 0, 0))

    def keypress(self, x, y, stamp):
        os.write(sys.stdout.fileno(), _KEY_PACKET.pack(1, x, y, stamp))

    run = _Capture._keyboard_events


def _usb_identity(usb, usb_ids):
    path = usb.resolve(strict=True)
    stat = path.stat()
    identity = ((path / 'idVendor').read_text().strip() + ':' +
                (path / 'idProduct').read_text().strip()).lower()
    if identity not in usb_ids:
        raise RuntimeError('USB device at the selected port does not match the keyboard')
    return (str(path), stat.st_ino, stat.st_ctime_ns, identity,
            (path / 'busnum').read_text().strip(),
            (path / 'devnum').read_text().strip())


def _device_node(connection, deviceid, atom):
    reply = connection.xinput_get_device_property(deviceid, atom, 0, 0, 1024)
    value = reply.value
    if not value or value[0] != 8 or reply.bytes_after:
        return None
    node = bytes(value[1]).rstrip(b'\0').decode('utf-8')
    return node if re.fullmatch(r'/dev/input/event\d+', node) else None


def _input_identity(node, usb, usb_ids):
    event = Path('/sys/class/input') / Path(node).name / 'device'
    path = event.resolve(strict=True)
    selected = usb.resolve(strict=True)
    if selected not in path.parents:
        return None
    _usb_identity(usb, usb_ids)
    stat = Path(node).stat()
    sys_stat = path.stat()
    return (str(path), stat.st_ino, stat.st_rdev, stat.st_ctime_ns,
            sys_stat.st_ino, sys_stat.st_ctime_ns)


def _verify_keyboard(connection, usb, usb_ids, usb_token, devices, atom, query=True):
    if _usb_identity(usb, usb_ids) != usb_token:
        raise RuntimeError('Selected USB keyboard disconnected or changed; re-enable capture')
    for deviceid, (node, token) in devices.items():
        if _input_identity(node, usb, usb_ids) != token:
            raise RuntimeError('Keyboard event node was removed or reused; re-enable capture')
        if query:
            info = connection.xinput_query_device(deviceid).devices
            if len(info) != 1 or not info[0].enabled or info[0].use != 4:
                raise RuntimeError('Selected XInput keyboard is no longer available')
            if _device_node(connection, deviceid, atom) != node:
                raise RuntimeError('Selected XInput keyboard identity changed')


def _keymap(ecodes, centres):
    names = {name: 'KEY_' + name.upper() for name in centres
             if len(name) == 1 or re.fullmatch(r'f\d+', name)}
    names.update({
        'escape': 'KEY_ESC', 'tilde': 'KEY_GRAVE', 'minus': 'KEY_MINUS',
        'equal': 'KEY_EQUAL', 'backspace': 'KEY_BACKSPACE', 'tab': 'KEY_TAB',
        'open_bracket': 'KEY_LEFTBRACE', 'close_bracket': 'KEY_RIGHTBRACE',
        'backslash': 'KEY_BACKSLASH', 'caps_lock': 'KEY_CAPSLOCK',
        'semicolon': 'KEY_SEMICOLON', 'quote': 'KEY_APOSTROPHE', 'enter': 'KEY_ENTER',
        'shift_left': 'KEY_LEFTSHIFT', 'shift_right': 'KEY_RIGHTSHIFT',
        'comma': 'KEY_COMMA', 'period': 'KEY_DOT', 'slash': 'KEY_SLASH',
        'ctrl_left': 'KEY_LEFTCTRL', 'ctrl_right': 'KEY_RIGHTCTRL',
        'win_left': 'KEY_LEFTMETA', 'win_right': 'KEY_RIGHTMETA',
        'alt_left': 'KEY_LEFTALT', 'alt_right': 'KEY_RIGHTALT', 'space': 'KEY_SPACE',
        'menu': 'KEY_COMPOSE', 'insert': 'KEY_INSERT', 'home': 'KEY_HOME',
        'page_up': 'KEY_PAGEUP', 'delete': 'KEY_DELETE', 'end': 'KEY_END',
        'page_down': 'KEY_PAGEDOWN', 'arrow_top': 'KEY_UP', 'arrow_bottom': 'KEY_DOWN',
        'arrow_left': 'KEY_LEFT', 'arrow_right': 'KEY_RIGHT', 'print_screen': 'KEY_SYSRQ',
        'scroll_lock': 'KEY_SCROLLLOCK', 'pause_break': 'KEY_PAUSE',
        'num_lock': 'KEY_NUMLOCK', 'num_slash': 'KEY_KPSLASH',
        'num_asterisk': 'KEY_KPASTERISK', 'num_minus': 'KEY_KPMINUS',
        'num_plus': 'KEY_KPPLUS', 'num_dot': 'KEY_KPDOT', 'numenter': 'KEY_KPENTER',
        'previous': 'KEY_PREVIOUSSONG', 'play_pause': 'KEY_PLAYPAUSE',
        'stop': 'KEY_STOPCD', 'next': 'KEY_NEXTSONG', 'mute': 'KEY_MUTE',
        'intl_backslash': 'KEY_102ND', 'abnt_slash': 'KEY_RO',
    })
    names.update({f'num{i}': f'KEY_KP{i}' for i in range(10)})
    return {ecodes.ecodes[code]: centres[name] for name, code in names.items()
            if code in ecodes.ecodes and name in centres}


class ReactiveInputs:
    """Configure is idempotent, including when called on every UI tick.

    A keyboard dict may additionally carry ``display`` so keyboard capture does
    not depend on screen capture being enabled. close() is final and idempotent.
    Snapshots contain only normalized audio, 24x12 pixels and bounded key centres
    with real monotonic ages; callers cannot mutate any retained source state.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._configure_lock = threading.Lock()
        self._sources = {}
        self._closed = False

    def configure(self, *, audio=False, audio_source=None, screen=None, keyboard=None):
        desired = {}
        if audio:
            if audio_source is not None and (not isinstance(audio_source, str) or not audio_source):
                raise ValueError('Choose a speaker-output monitor source')
            desired['audio'] = audio_source
        if screen is not None:
            display = screen.get('display')
            if not isinstance(display, str) or not display:
                raise ValueError('Screen capture requires an explicit X11 display')
            values = tuple(screen.get(name) for name in ('x', 'y', 'width', 'height'))
            if any(type(value) is not int for value in values) or min(values[2:]) <= 0:
                raise ValueError('Screen capture requires a positive-sized integer rectangle')
            desired['screen'] = (display, *values)
        if keyboard is not None:
            match = re.fullmatch(r'usb:(\d+-\d+(?:\.\d+)*)', keyboard.get('id', ''))
            ids = tuple(sorted(str(item).lower() for item in keyboard.get('usb_ids', ())))
            if (not match or not ids or keyboard.get('kind', 'keyboard') != 'keyboard' or
                    any(not re.fullmatch(r'[0-9a-f]{4}:[0-9a-f]{4}', item) for item in ids)):
                raise ValueError('Typing capture requires a selected physical USB keyboard')
            display = keyboard.get('display') or os.environ.get('DISPLAY') or ':0'
            desired['keyboard'] = (match.group(1), ids, display)
        with self._configure_lock:
            if self._closed:
                if desired:
                    raise RuntimeError('Reactive inputs are closed')
                return
            with self._lock:
                removed = [self._sources.pop(kind) for kind in tuple(self._sources)
                           if kind not in desired or self._sources[kind].spec != desired[kind]]
            errors = []
            for source in removed:
                try:
                    source.stop()
                except Exception as error:
                    errors.append(str(error))
            if errors:
                raise RuntimeError('; '.join(errors))
            with self._lock:
                for kind, spec in desired.items():
                    if kind not in self._sources:
                        self._sources[kind] = _Capture(kind, spec)

    def snapshot(self):
        now = time.monotonic()
        with self._lock:
            values = {kind: source.read(now)[0] for kind, source in self._sources.items()}
        keys = values.get('keyboard') or ()
        return {'audio': dict(values.get('audio') or _AUDIO_ZERO),
                'screen': dict(values.get('screen') or _SCREEN_ZERO),
                'keys': tuple((x, y, max(0.0, now - stamp)) for x, y, stamp in keys
                              if now - stamp <= _KEY_LIFETIME)}

    def status(self):
        with self._lock:
            if self._closed:
                return 'Capture closed'
            if not self._sources:
                return 'Capture disabled'
            now = time.monotonic()
            return ' · '.join(f'{kind}: {source.read(now)[1]}'
                              for kind, source in self._sources.items())

    def close(self):
        with self._configure_lock:
            with self._lock:
                self._closed = True
                sources = tuple(self._sources.values())
                self._sources.clear()
            errors = []
            for source in sources:
                try:
                    source.stop()
                except Exception as error:
                    errors.append(str(error))
            if errors:
                raise RuntimeError('; '.join(errors))


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--keyboard-worker':
        raise SystemExit('This module is used by Logibust, not a capture command.')
    try:
        _KeyboardWorker(json.loads(sys.argv[2])).run()
    except Exception as error:
        # Do not emit a traceback containing locals, translated keys or records.
        sys.stderr.write(str(error).replace('\n', ' ')[:240] + '\n')
        raise SystemExit(1)
