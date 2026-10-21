#!/usr/bin/python3
"""Logibust: native GTK3 lighting studio. Launching never changes device lighting."""
import argparse
from collections import OrderedDict
import math
import os
from pathlib import Path
import threading
import time

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gio, GLib, Gtk
from devices import DeviceManager
from effects import DEFAULTS, EFFECTS, KEYS, KEY_NAMES, Profiles, frame, validate


class DeviceIO:
    """One worker; at most one pending request per operation, latest frame wins."""
    def __init__(self):
        self.condition = threading.Condition()
        self.pending = OrderedDict()
        self.stopping = False
        self.manager = DeviceManager()
        self.thread = threading.Thread(target=self.work, name='logibust-device-io', daemon=True)
        self.thread.start()

    def submit(self, kind, operation, done):
        with self.condition:
            if not self.stopping:
                self.pending[kind] = (operation, done)
                self.condition.notify()

    def cancel_keyboard(self):
        with self.condition:
            self.pending.pop('keyboard', None)

    def work(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.pending or self.stopping)
                if self.stopping:
                    break
                kind, (operation, done) = self.pending.popitem(last=False)
            try:
                value, error = operation(self.manager), None
            except Exception as e:
                value, error = None, str(e)
                if kind == 'keyboard':
                    self.cancel_keyboard()
            GLib.idle_add(done, value, error)
        self.manager.close()

    def close(self):
        with self.condition:
            self.stopping = True
            self.pending.clear()
            self.condition.notify()
        self.thread.join()


def label(text, style=None):
    item = Gtk.Label(label=text, xalign=0)
    if style:
        item.get_style_context().add_class(style)
    return item


def button(text, callback, accent=False):
    b = Gtk.Button(label=text)
    b.connect('clicked', callback)
    if accent:
        b.get_style_context().add_class('accent')
    return b


def combo(options):
    c = Gtk.ComboBoxText()
    for key, text in options:
        c.append(key, text)
    return c


def scale(low, high, step, value):
    s = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, high, step)
    s.set_value(value)
    s.set_hexpand(True)
    return s


class KeyboardView(Gtk.DrawingArea):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.set_size_request(850, 340)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect('draw', self.draw_keys)
        self.connect('button-press-event', self.click_key)
        self.set_tooltip_text('Click a physical key to toggle it in Selected keys. ANSI reference; ISO extras below. A named-key selector is also available.')
        self.get_accessible().set_name('G610 white-light preview')
        self.rectangles = []

    def draw_keys(self, widget, cr):
        w, h = self.get_allocated_width(), self.get_allocated_height()
        cr.set_source_rgb(.065, .12, .13)
        cr.paint()
        unit = min((w - 36) / 23, (h - 44) / 9)
        ox, oy = (w - 23 * unit) / 2, 22
        # Fine orbital construction ties the light field to the linework visual grammar.
        cr.set_line_width(.7)
        for radius in (50, 66, 82, 98):
            cr.set_source_rgba(.32, .68, .63, .18)
            cr.arc(w - 100, h - 20, radius, math.pi, 2 * math.pi)
            cr.stroke()
        self.rectangles = []
        for k in KEYS:
            x, y, kw, kh = ox + k.x * unit + 2, oy + k.y * unit + 2, k.w * unit - 4, k.h * unit - 4
            level = self.studio.levels.get(k.name, 0) / 255
            cr.rectangle(x, y, kw, kh)
            cr.set_source_rgb(.16 + .78 * level, .20 + .75 * level, .21 + .72 * level)
            cr.fill_preserve()
            selected = k.name in self.studio.selected
            cr.set_source_rgb(*((.98, .48, .35) if selected else (.35, .43, .43)))
            cr.set_line_width(1.8 if selected else .6)
            cr.stroke()
            cr.set_source_rgb(*((.08, .13, .14) if level > .5 else (.88, .91, .87)))
            cr.select_font_face('Sans')
            cr.set_font_size(max(8, min(11, unit * .28)))
            text = k.label[3:] if k.name.startswith('num') and len(k.label) == 4 else k.label
            ext = cr.text_extents(text)
            cr.move_to(x + (kw - ext.width) / 2 - ext.x_bearing, y + (kh - ext.height) / 2 - ext.y_bearing)
            cr.show_text(text)
            self.rectangles.append((k.name, x, y, kw, kh))
        cr.set_source_rgb(.67, .76, .74)
        cr.set_font_size(10)
        cr.move_to(ox + 5.2 * unit, oy + 8.65 * unit)
        cr.show_text('ISO / ABNT extras   ·   WHITE LEDs ONLY   ·   layout is a physical-key reference')
        return False

    def click_key(self, widget, event):
        if event.button == 1:
            for name, x, y, w, h in self.rectangles:
                if x <= event.x <= x+w and y <= event.y <= y+h:
                    self.studio.toggle_key(name)
                    break
        return True


class Studio(Gtk.ApplicationWindow):
    def __init__(self, app, background=False):
        super().__init__(application=app, title='Logibust · Lighting Studio')
        self.set_default_size(1180, 1040)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.io = DeviceIO()
        self.profiles = Profiles()
        self.selected = set(DEFAULTS['selected'])
        self.output = False
        self.closed = False
        self.seconds = 0
        self.last_tick = time.monotonic()
        self.last_write = 0
        self.last_frame = None
        self.levels = {}
        self.ready = {'keyboard': False, 'mouse': False}
        self.mouse_busy = False
        self.connect('delete-event', self.on_delete)
        self.connect('destroy', self.shutdown)
        self.build()
        self.make_tray()
        self.reload_profiles()
        self.probe()
        self.timer = GLib.timeout_add(33, self.tick)
        self.show_all()
        if background:
            GLib.timeout_add(800, self.hide_if_tray)

    def build(self):
        css = Gtk.CssProvider()
        css.load_from_data(b'''
            window { background: #f4f0e6; color: #203034; }
            .title { font-family: serif; font-size: 32px; font-weight: bold; }
            .subtitle { color: #516564; font-size: 12px; }
            .section { color: #186c67; font-weight: bold; font-size: 16px; }
            .status { color: #3c5557; font-size: 12px; }
            button { padding: 6px 12px; }
            button.accent { background: #1b7169; color: white; text-shadow: none; }
            .notice { background: #e3e9df; padding: 10px; border-left: 3px solid #22766f; }
        ''')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.add(scroll)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=22)
        scroll.add(outer)
        heading = Gtk.Box(spacing=16)
        titlebox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        titlebox.pack_start(label('LOGIBUST', 'title'), False, False, 0)
        titlebox.pack_start(label('LIGHTING STUDIO   /   LINUX NATIVE', 'subtitle'), False, False, 0)
        heading.pack_start(titlebox, True, True, 0)
        heading.pack_start(button('Refresh devices', lambda *_: self.probe()), False, False, 0)
        heading.pack_start(button('Quit', lambda *_: self.destroy()), False, False, 0)
        outer.pack_start(heading, False, False, 0)
        self.device_status = label('Discovering G610 and G502…', 'status')
        self.device_status.set_line_wrap(True)
        self.device_status.set_selectable(True)
        outer.pack_start(self.device_status, False, False, 0)
        outer.pack_start(Gtk.Separator(), False, False, 0)
        outer.pack_start(label('01   G610 / white-light field', 'section'), False, False, 0)
        self.keyboard = KeyboardView(self)
        outer.pack_start(self.keyboard, False, False, 0)
        controls = Gtk.Grid(column_spacing=16, row_spacing=8)
        self.effect = combo(EFFECTS.items())
        self.effect.set_active_id(DEFAULTS['effect'])
        self.intensity = scale(0, 255, 1, DEFAULTS['brightness'])
        self.speed = scale(.2, 3, .1, DEFAULTS['speed'])
        self.speed.set_digits(1)
        for col, (text, widget) in enumerate([('Effect', self.effect), ('White intensity / 255', self.intensity), ('Speed multiplier', self.speed)]):
            widget.get_accessible().set_name(text)
            field_label = label(text)
            field_label.set_mnemonic_widget(widget)
            controls.attach(field_label, col, 0, 1, 1)
            controls.attach(widget, col, 1, 1, 1)
        self.reverse = Gtk.CheckButton(label='Reverse direction')
        self.pause = Gtk.CheckButton(label='Pause animation')
        self.pause.set_active(not Gtk.Settings.get_default().get_property('gtk-enable-animations'))
        controls.attach(self.reverse, 0, 2, 1, 1)
        controls.attach(self.pause, 1, 2, 1, 1)
        self.key_choice = combo((k.name, k.name.replace('_', ' ')) for k in sorted(KEYS, key=lambda k:k.name))
        self.key_choice.set_active_id('w')
        self.key_choice.get_accessible().set_name('Physical key to select')
        controls.attach(self.key_choice, 2, 2, 1, 1)
        controls.attach(button('Toggle selected key', lambda *_: self.toggle_key(self.key_choice.get_active_id())), 2, 3, 1, 1)
        self.selected_status = label('Selected: a, d, s, w', 'subtitle')
        self.selected_status.set_ellipsize(3)
        self.selected_status.set_max_width_chars(70)
        controls.attach(self.selected_status, 0, 3, 2, 1)
        outer.pack_start(controls, False, False, 0)
        actions = Gtk.Box(spacing=8)
        self.start_button = button('Start keyboard', self.start_keyboard, True)
        self.stop_button = button('Stop output / freeze', self.stop_keyboard)
        self.off_button = button('Keyboard off', self.keyboard_off)
        self.start_button.set_sensitive(False)
        self.off_button.set_sensitive(False)
        for b in (self.start_button, self.stop_button, self.off_button):
            actions.pack_start(b, False, False, 0)
        outer.pack_start(label('Flashing-light caution: checkerboard, starlight and heartbeat can flash. Reduce speed or use steady light.', 'subtitle'), False, False, 0)
        self.output_status = label('PREVIEW ONLY · no device changes on launch', 'status')
        actions.pack_start(self.output_status, True, True, 8)
        outer.pack_start(actions, False, False, 0)
        outer.pack_start(Gtk.Separator(), False, False, 0)
        outer.pack_start(label('02   G502 Spectrum / firmware lighting', 'section'), False, False, 0)
        mouse_grid = Gtk.Grid(column_spacing=16, row_spacing=8)
        self.mouse_mode = combo([('static', 'Steady RGB'), ('breathing', 'Breathing'), ('cycle', 'RGB cycle'), ('off', 'Off')])
        self.mouse_mode.set_active_id(DEFAULTS['mouse_mode'])
        self.mouse_zone = combo([('all', 'Both LEDs'), ('0', 'LED 0'), ('1', 'LED 1')])
        self.mouse_zone.set_active_id('all')
        self.color = Gtk.ColorButton()
        rgba = Gdk.RGBA()
        rgba.parse('#'+DEFAULTS['mouse_color'])
        self.color.set_rgba(rgba)
        self.color.set_use_alpha(False)
        self.color.set_title('G502 RGB color')
        self.color.get_accessible().set_name('G502 RGB color')
        self.mouse_intensity = scale(0, 255, 1, 255)
        self.period = scale(1, 10, .1, 8)
        self.period.set_digits(1)
        for col, (text, widget) in enumerate([('Mode', self.mouse_mode), ('LED index', self.mouse_zone), ('RGB color', self.color), ('Brightness / 255', self.mouse_intensity), ('Period / seconds', self.period)]):
            widget.get_accessible().set_name(text)
            field_label = label(text)
            field_label.set_mnemonic_widget(widget)
            mouse_grid.attach(field_label, col, 0, 1, 1)
            mouse_grid.attach(widget, col, 1, 1, 1)
        self.mouse_button = button('Apply mouse lighting', self.apply_mouse, True)
        self.mouse_button.set_sensitive(False)
        mouse_grid.attach(self.mouse_button, 0, 2, 2, 1)
        note = label('Runs on the mouse. No per-frame profile writes.\nLED indices are driver-defined; physical zone names are unverified.', 'subtitle')
        mouse_grid.attach(note, 2, 2, 3, 1)
        outer.pack_start(mouse_grid, False, False, 0)
        self.mouse_mode.connect('changed', self.mouse_sensitivity)
        self.mouse_sensitivity()
        outer.pack_start(Gtk.Separator(), False, False, 0)
        profilebar = Gtk.Box(spacing=8)
        profilebar.pack_start(label('03   Profiles', 'section'), False, False, 8)
        self.profile_choice = Gtk.ComboBoxText.new_with_entry()
        self.profile_choice.get_child().set_placeholder_text('Name a lighting profile')
        self.profile_choice.get_child().get_accessible().set_name('Lighting profile name')
        profilebar.pack_start(self.profile_choice, True, True, 0)
        profilebar.pack_start(button('Save', self.save_profile), False, False, 0)
        profilebar.pack_start(button('Load to preview', self.load_profile), False, False, 0)
        outer.pack_start(profilebar, False, False, 0)
        self.message = label('Ready for preview. Hardware output requires Start or Apply.', 'notice')
        self.message.set_line_wrap(True)
        self.message.set_selectable(True)
        outer.pack_start(self.message, False, False, 0)
        footer = Gtk.Box(spacing=16)
        self.autostart = Gtk.CheckButton(label='Open at login (preview only)')
        self.autostart.set_active(self.autostart_enabled())
        self.autostart.connect('toggled', self.set_autostart)
        footer.pack_start(self.autostart, False, False, 0)
        self.tray_note = label('Close hides to tray when available. Quit stops host animations.', 'subtitle')
        footer.pack_start(self.tray_note, True, True, 0)
        outer.pack_start(footer, False, False, 0)

    def mouse_sensitivity(self, *_):
        mode = self.mouse_mode.get_active_id()
        self.color.set_sensitive(mode in ('static', 'breathing'))
        self.period.set_sensitive(mode in ('breathing', 'cycle'))
        self.mouse_intensity.set_sensitive(mode != 'off')

    def settings(self):
        rgb = self.color.get_rgba()
        return validate(dict(effect=self.effect.get_active_id(), brightness=round(self.intensity.get_value()),
            speed=self.speed.get_value(), reverse=self.reverse.get_active(), selected=sorted(self.selected),
            mouse_mode=self.mouse_mode.get_active_id(), mouse_zone=self.mouse_zone.get_active_id(),
            mouse_color=''.join(f'{round(c * 255):02x}' for c in (rgb.red, rgb.green, rgb.blue)),
            mouse_brightness=round(self.mouse_intensity.get_value()), mouse_period=round(self.period.get_value()*1000)))

    def notify(self, text):
        if not self.closed:
            self.message.set_text(text)

    def tick(self):
        if self.closed:
            return False
        now = time.monotonic()
        if not self.pause.get_active():
            self.seconds += min(.2, now-self.last_tick)
        self.last_tick = now
        self.levels = frame(self.settings(), self.seconds)
        self.keyboard.queue_draw()
        if self.output and now-self.last_write >= .1 and self.levels != self.last_frame:
            self.last_write = now
            levels = self.levels.copy()
            self.last_frame = levels
            self.io.submit('keyboard', lambda m:m.apply_keyboard(levels), self.keyboard_result)
        return True

    def keyboard_result(self, value, error):
        if self.closed:
            return False
        if error:
            self.stop_keyboard()
            self.notify('Keyboard output stopped: '+error)
        elif self.output:
            self.output_status.set_text('LIVE · white frames sent to G610')
        return False

    def start_keyboard(self, *_):
        self.output = True
        self.last_frame = None
        self.output_status.set_text('STARTING · waiting for driver')
        self.notify('Keyboard output enabled. Effect edits now update the device. Stop freezes the last frame; Off blacks it out.')

    def stop_keyboard(self, *_):
        self.output = False
        self.io.cancel_keyboard()
        self.output_status.set_text('STOPPED · last hardware frame frozen')

    def keyboard_off(self, *_):
        self.stop_keyboard()
        levels = {k:0 for k in KEY_NAMES}
        self.io.submit('blackout', lambda m:m.apply_keyboard(levels), self.off_result)

    def off_result(self, value, error):
        self.notify('Keyboard off failed: '+error if error else 'G610 blackout frame sent. Preview remains independent.')
        return False

    def apply_mouse(self, *_):
        s = self.settings()
        self.mouse_busy = True
        self.mouse_button.set_sensitive(False)
        self.notify('Applying mouse firmware lighting…')
        self.io.submit('mouse', lambda m:m.apply_mouse(s['mouse_mode'], s['mouse_color'], s['mouse_brightness'], s['mouse_period'], s['mouse_zone']), self.mouse_result)

    def mouse_result(self, value, error):
        if self.closed:
            return False
        self.mouse_busy = False
        self.mouse_button.set_sensitive(self.ready['mouse'])
        self.notify('Mouse apply failed: '+error if error else value)
        return False

    def probe(self):
        self.device_status.set_text('Checking device drivers…')
        self.io.submit('probe', lambda m:m.discover(), self.probe_result)

    def probe_result(self, result, error):
        if self.closed:
            return False
        if error:
            self.notify('Discovery failed: '+error)
            return False
        self.ready = {k: result[k]['ready'] for k in ('keyboard', 'mouse')}
        self.device_status.set_text('\n'.join(result[k]['detail'] for k in ('keyboard', 'mouse')))
        self.start_button.set_sensitive(self.ready['keyboard'])
        self.off_button.set_sensitive(self.ready['keyboard'])
        self.mouse_button.set_sensitive(self.ready['mouse'] and not self.mouse_busy)
        if not self.ready['keyboard'] and self.output:
            self.stop_keyboard()
        return False

    def toggle_key(self, name):
        if name in self.selected:
            self.selected.remove(name)
        else:
            self.selected.add(name)
        self.effect.set_active_id('custom')
        self.selected_status.set_text('Selected: '+(', '.join(sorted(self.selected)) or 'none'))
        self.keyboard.queue_draw()

    def reload_profiles(self, name=''):
        try:
            profiles = self.profiles.load()
            self.profile_choice.remove_all()
            for n in sorted(profiles):
                self.profile_choice.append_text(n)
            self.profile_choice.get_child().set_text(name)
        except (ValueError, OSError) as e:
            self.notify('Profiles unavailable; file preserved: '+str(e))

    def save_profile(self, *_):
        name = self.profile_choice.get_child().get_text()
        try:
            self.profiles.save(name, self.settings())
            self.reload_profiles(name.strip())
            self.notify('Saved profile: '+name.strip())
        except (ValueError, OSError) as e:
            self.notify('Profile not saved: '+str(e))

    def load_profile(self, *_):
        try:
            name = self.profile_choice.get_child().get_text()
            profiles = self.profiles.load()
            if name not in profiles:
                raise ValueError('Choose an existing profile.')
            s = profiles[name]
            self.stop_keyboard()
            self.effect.set_active_id(s['effect'])
            self.intensity.set_value(s['brightness'])
            self.speed.set_value(s['speed'])
            self.reverse.set_active(s['reverse'])
            self.selected = set(s['selected'])
            self.selected_status.set_text('Selected: '+', '.join(sorted(self.selected)))
            self.mouse_mode.set_active_id(s['mouse_mode'])
            self.mouse_zone.set_active_id(s['mouse_zone'])
            rgba = Gdk.RGBA()
            rgba.parse('#'+s['mouse_color'])
            self.color.set_rgba(rgba)
            self.mouse_intensity.set_value(s['mouse_brightness'])
            self.period.set_value(s['mouse_period']/1000)
            self.notify('Loaded '+name+' to preview only. Use Start / Apply to change devices.')
        except (ValueError, OSError) as e:
            self.notify('Profile not loaded: '+str(e))

    def make_tray(self):
        self.tray = Gtk.StatusIcon.new_from_icon_name('input-keyboard')
        self.tray.set_tooltip_text('Logibust · Lighting Studio')
        self.tray.connect('activate', lambda *_: self.set_visible(not self.get_visible()))
        self.tray.connect('popup-menu', self.tray_menu)

    def tray_menu(self, icon, button_number, timestamp):
        menu = Gtk.Menu()
        for text, action in [('Show studio', lambda *_: self.present()), ('Stop keyboard output', self.stop_keyboard), ('Quit Logibust', lambda *_: self.destroy())]:
            item = Gtk.MenuItem(label=text)
            item.connect('activate', action)
            menu.append(item)
        menu.show_all()
        menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button_number, timestamp)

    def hide_if_tray(self):
        if self.tray.is_embedded():
            self.hide()
        return False

    def on_delete(self, *_):
        if self.tray.is_embedded():
            self.hide()
            return True
        return False

    def autostart_path(self):
        return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config'))) / 'autostart/logibust.desktop'

    def autostart_enabled(self):
        p = self.autostart_path()
        try:
            return p.exists() and 'Hidden=true' not in p.read_text()
        except OSError:
            return False

    def set_autostart(self, *_):
        try:
            path = self.autostart_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(desktop_entry(background=True, hidden=not self.autostart.get_active()))
            self.notify('Login launch '+('enabled (preview only).' if self.autostart.get_active() else 'disabled.'))
        except OSError as e:
            self.notify('Login preference not saved: '+str(e))

    def shutdown(self, *_):
        self.closed = True
        self.output = False
        GLib.source_remove(self.timer)
        self.tray.set_visible(False)
        self.io.close()


def desktop_entry(background=False, hidden=False):
    # Desktop Exec arguments use their own escaping, not shell quoting.
    path = str(Path(__file__).resolve()).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
    return ('[Desktop Entry]\nType=Application\nName=Logibust Lighting Studio\n'
            'Comment=G610 white-light animations and G502 RGB lighting\n'
            f'Exec=/usr/bin/python3 "{path}"'+(' --background' if background else '')+'\n'
            'Icon=input-keyboard\nTerminal=false\nCategories=Settings;HardwareSettings;\n'
            f'Hidden={str(hidden).lower()}\n')


class Application(Gtk.Application):
    def __init__(self, background=False):
        super().__init__(application_id='io.logibust.Studio', flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.background = background
        self.window = None

    def do_activate(self):
        if self.window is None:
            self.window = Studio(self, self.background)
        else:
            self.window.present()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--background', action='store_true')
    p.add_argument('--install-desktop', action='store_true', help='Install a user-local applications-menu entry and exit')
    args = p.parse_args()
    if args.install_desktop:
        dest = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))) / 'applications/logibust.desktop'
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(desktop_entry())
        print(dest)
    else:
        Application(args.background).run([])
