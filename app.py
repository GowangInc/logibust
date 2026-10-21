#!/usr/bin/python3
"""Logibust: a device-first native Linux lighting control panel."""
import argparse
from collections import OrderedDict
import os
from pathlib import Path
import threading
import time

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gio, GLib, Gtk
from catalog import load_catalog, merge_devices
from devices import DeviceManager
from effects import DEFAULTS, EFFECTS, KEYS, KEY_NAMES, Profiles, frame, validate
from graphics import DeviceIcon, KeyboardView, PeripheralView


class DeviceIO:
    """One worker; one pending request per operation, latest keyboard frame wins."""
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
                self.condition.wait_for(lambda:self.pending or self.stopping)
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
    b.connect('clicked',callback)
    if accent:
        b.get_style_context().add_class('accent')
    return b


def combo(options, name):
    c = Gtk.ComboBoxText()
    for key, text in options:
        c.append(key,text)
    c.get_accessible().set_name(name)
    return c


def scale(low, high, step, value, name):
    s = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,low,high,step)
    s.set_value(value)
    s.set_hexpand(True)
    s.get_accessible().set_name(name)
    return s


def color_button(value, name):
    b = Gtk.ColorButton()
    rgba = Gdk.RGBA(); rgba.parse('#'+value)
    b.set_rgba(rgba)
    b.set_title(name)
    b.get_accessible().set_name(name)
    return b


def field(grid, text, widget, column, row=0):
    title = label(text,'muted')
    title.set_mnemonic_widget(widget)
    grid.attach(title,column,row,1,1)
    grid.attach(widget,column,row+1,1,1)


class Studio(Gtk.ApplicationWindow):
    def __init__(self, app, background=False):
        super().__init__(application=app,title='Logibust · Device Control')
        self.set_default_size(1200,900)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.io = DeviceIO()
        self.profiles = Profiles()
        self.catalog = load_catalog()
        self.devices = []
        self.selected_device = None
        self.drafts = {}
        self.selected = set()
        self.output = False
        self.output_id = None
        self.generation = 0
        self.mouse_busy = False
        self.seconds = 0
        self.last_tick = time.monotonic()
        self.last_write = 0
        self.last_frame = None
        self.levels = {}
        self.closed = False
        self.build()
        self.make_tray()
        self.reload_profiles()
        self.connect('delete-event',self.on_delete)
        self.connect('destroy',self.shutdown)
        self.timer = GLib.timeout_add(34,self.tick)
        self.tray_timer = None
        self.probe()
        self.root.show_all()
        if background:
            self.tray_attempts = 0
            self.tray_timer = GLib.timeout_add(500,self.ensure_background_tray)
        else:
            self.show()

    def build(self):
        css = Gtk.CssProvider()
        css.load_from_data(b'''
            window { background: #f7f7fa; color: #252630; }
            .brand { font-size: 25px; font-weight: bold; color: #5e35c6; }
            .title { font-size: 25px; font-weight: bold; }
            .section { font-size: 14px; font-weight: bold; }
            .muted { color: #60636f; font-size: 12px; }
            .sidebar { background: #ffffff; border-right: 1px solid #e3e3ec; }
            .sidebar row { padding: 8px 10px; border-radius: 9px; }
            .sidebar row:selected { background: #ede6ff; color: #302044; }
            .sidebar row:hover { background: #f2eff9; }
            .card { background: #ffffff; padding: 15px; border: 1px solid #e7e7ef; border-radius: 12px; }
            .notice { padding: 9px 12px; background: #eeebf8; border-radius: 8px; color: #40395a; }
            button { padding: 6px 12px; }
            button.accent { background-image: none; background-color: #7950d7; color: #ffffff; text-shadow: none; }
        ''')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.add(self.root)
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,margin=16)
        sidebar.set_size_request(244,-1)
        sidebar.get_style_context().add_class('sidebar')
        sidebar.pack_start(label('logibust','brand'),False,False,8)
        sidebar.pack_start(label('YOUR DEVICE CONTROL PANEL','muted'),False,False,0)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text('Find a device…')
        self.search.get_accessible().set_name('Search devices and library')
        self.search.connect('search-changed',lambda *_:self.filter_devices())
        sidebar.pack_start(self.search,False,False,0)
        self.library_toggle = Gtk.CheckButton(label='Browse device library')
        self.library_toggle.connect('toggled',lambda *_:self.rebuild_sidebar())
        sidebar.pack_start(self.library_toggle,False,False,0)
        self.device_count = label('Discovering your devices…','muted')
        sidebar.pack_start(self.device_count,False,False,0)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        self.device_list = Gtk.ListBox()
        self.device_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.device_list.set_filter_func(self.row_visible)
        self.device_list.connect('row-selected',self.row_selected)
        scroller.add(self.device_list)
        sidebar.pack_start(scroller,True,True,0)
        sidebar.pack_start(button('Refresh connected devices',lambda *_:self.probe()),False,False,0)
        self.root.pack_start(sidebar,False,False,0)
        right_scroll = Gtk.ScrolledWindow()
        right_scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC)
        self.root.pack_start(right_scroll,True,True,0)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14,margin=24)
        right_scroll.add(content)
        heading = Gtk.Box(spacing=14)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
        self.device_title = label('Your devices','title')
        self.device_subtitle = label('Connect a device or browse the library.','muted')
        titles.pack_start(self.device_title,False,False,0)
        titles.pack_start(self.device_subtitle,False,False,0)
        heading.pack_start(titles,True,True,0)
        heading.pack_start(button('Quit',lambda *_:self.destroy()),False,False,0)
        content.pack_start(heading,False,False,0)
        self.device_status = label('Discovering hardware…','notice')
        self.device_status.set_line_wrap(True)
        self.device_status.set_selectable(True)
        content.pack_start(self.device_status,False,False,0)
        self.preview_stack = Gtk.Stack()
        self.keyboard = KeyboardView(self)
        self.peripheral = PeripheralView(self)
        self.preview_stack.add_named(self.keyboard,'keyboard')
        self.preview_stack.add_named(self.peripheral,'peripheral')
        self.preview_stack.get_style_context().add_class('card')
        content.pack_start(self.preview_stack,False,False,0)
        self.panel_stack = Gtk.Stack()
        self.panel_stack.add_named(self.build_keyboard_controls(),'keyboard')
        self.panel_stack.add_named(self.build_lighting_controls(),'lighting')
        self.info_panel = label('Choose a device.','muted')
        self.info_panel.set_line_wrap(True)
        self.panel_stack.add_named(self.info_panel,'info')
        self.panel_stack.get_style_context().add_class('card')
        content.pack_start(self.panel_stack,False,False,0)
        profilebar = Gtk.Box(spacing=8)
        profilebar.get_style_context().add_class('card')
        profilebar.pack_start(label('Profiles','section'),False,False,0)
        self.profile_choice = Gtk.ComboBoxText.new_with_entry()
        self.profile_choice.get_child().set_placeholder_text('Profile name')
        self.profile_choice.get_child().get_accessible().set_name('Lighting profile name')
        profilebar.pack_start(self.profile_choice,True,True,0)
        profilebar.pack_start(button('Save',self.save_profile),False,False,0)
        profilebar.pack_start(button('Load to preview',self.load_profile),False,False,0)
        content.pack_start(profilebar,False,False,0)
        self.message = label('Preview only. Start or Apply is required to change a device.','notice')
        self.message.set_line_wrap(True)
        self.message.set_selectable(True)
        content.pack_start(self.message,False,False,0)
        self.autostart = Gtk.CheckButton(label='Run in the background at login · tray beside the clock')
        self.autostart.set_active(self.autostart_enabled())
        self.autostart.connect('toggled',self.set_autostart)
        content.pack_start(self.autostart,False,False,0)
        self.tray_note = label('Close hides to tray. Mouse firmware effects continue without this window.','muted')
        self.tray_note.set_line_wrap(True)
        content.pack_start(self.tray_note,False,False,0)

    def build_keyboard_controls(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        box.pack_start(label('BACKLIGHTING','section'),False,False,0)
        grid = Gtk.Grid(column_spacing=16,row_spacing=8)
        self.effect = combo(EFFECTS.items(),'Keyboard effect')
        self.effect.set_active_id(DEFAULTS['effect'])
        self.intensity = scale(0,255,1,DEFAULTS['brightness'],'Keyboard brightness')
        self.speed = scale(.2,3,.1,1,'Animation speed')
        self.speed.set_digits(1)
        field(grid,'Effect',self.effect,0)
        field(grid,'Brightness / 255',self.intensity,1)
        field(grid,'Speed',self.speed,2)
        self.reverse = Gtk.CheckButton(label='Reverse')
        self.pause = Gtk.CheckButton(label='Pause preview / animation')
        self.pause.set_active(not Gtk.Settings.get_default().get_property('gtk-enable-animations'))
        grid.attach(self.reverse,0,2,1,1)
        grid.attach(self.pause,1,2,2,1)
        self.keyboard_color = color_button('ffffff','Keyboard RGB color')
        field(grid,'RGB color (RGB models only)',self.keyboard_color,0,3)
        self.key_choice = combo(((k.name,k.name.replace('_',' ')) for k in sorted(KEYS,key=lambda k:k.name)),'Physical key to select')
        self.key_choice.set_active(-1)
        field(grid,'Choose a key',self.key_choice,1,3)
        self.toggle_button = button('Toggle key',lambda *_:self.toggle_key(self.key_choice.get_active_id()))
        self.clear_button = button('Clear selection',self.clear_selection)
        editbar = Gtk.Box(spacing=5)
        editbar.pack_start(self.toggle_button,False,False,0)
        editbar.pack_start(self.clear_button,False,False,0)
        grid.attach(editbar,2,4,1,1)
        self.selected_status = label('No keys selected','muted')
        self.selected_status.set_ellipsize(3)
        self.selected_status.set_max_width_chars(70)
        grid.attach(self.selected_status,0,5,3,1)
        box.pack_start(grid,False,False,0)
        actions = Gtk.Box(spacing=7)
        self.start_button = button('Start keyboard',self.start_keyboard,True)
        self.stop_button = button('Stop / freeze',self.stop_keyboard)
        self.off_button = button('Keyboard off',self.keyboard_off)
        for b in (self.start_button,self.stop_button,self.off_button):
            actions.pack_start(b,False,False,0)
        box.pack_start(actions,False,False,0)
        self.output_status = label('PREVIEW ONLY','muted')
        box.pack_start(self.output_status,False,False,0)
        caution = label('Flashing-light caution: use steady light if sensitive to flashes.','muted')
        caution.set_line_wrap(True)
        box.pack_start(caution,False,False,0)
        self.start_button.set_sensitive(False)
        self.off_button.set_sensitive(False)
        return box

    def build_lighting_controls(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        box.pack_start(label('LIGHTING','section'),False,False,0)
        grid = Gtk.Grid(column_spacing=16,row_spacing=8)
        self.mouse_mode = combo([],'Peripheral lighting mode')
        self.mouse_zone = combo([],'Lighting zone')
        self.color = color_button(DEFAULTS['mouse_color'],'Peripheral RGB color')
        self.mouse_intensity = scale(0,255,1,255,'Peripheral brightness')
        self.period = scale(1,10,.1,8,'Effect period in seconds')
        self.period.set_digits(1)
        field(grid,'Mode',self.mouse_mode,0)
        field(grid,'Zone',self.mouse_zone,1)
        field(grid,'RGB color',self.color,2)
        field(grid,'Brightness / 255',self.mouse_intensity,0,2)
        field(grid,'Period / seconds',self.period,1,2)
        self.mouse_button = button('Apply lighting',self.apply_mouse,True)
        self.mouse_button.set_sensitive(False)
        grid.attach(self.mouse_button,2,3,1,1)
        box.pack_start(grid,False,False,0)
        self.lighting_note = label('Lighting runs on the device; preview does not apply changes.','muted')
        self.lighting_note.set_line_wrap(True)
        box.pack_start(self.lighting_note,False,False,0)
        self.mouse_mode.connect('changed',self.mouse_sensitivity)
        self.mouse_zone.connect('changed',lambda *_:self.populate_modes())
        return box

    def row_visible(self, row):
        d = row.device
        term = self.search.get_text().strip().casefold()
        return (d['connected'] or self.library_toggle.get_active()) and term in (d['vendor']+' '+d['name']+' '+d['kind']).casefold()

    def filter_devices(self):
        self.device_list.invalidate_filter()

    def rebuild_sidebar(self):
        self.filter_devices()
        if not self.library_toggle.get_active() and self.selected_device and not self.selected_device['connected']:
            row = next((r for r in self.device_list.get_children() if r.device['connected']),None)
            if row:
                self.device_list.select_row(row)

    def populate_sidebar(self):
        self.device_list.unselect_all()
        for child in self.device_list.get_children():
            self.device_list.remove(child)
        for d in self.devices:
            row = Gtk.ListBoxRow()
            row.device = d
            row.get_accessible().set_name(d['name']+(' connected' if d['connected'] else ' catalog preview'))
            box = Gtk.Box(spacing=10,margin=3)
            box.pack_start(DeviceIcon(d['kind']),False,False,0)
            titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
            name = label(d['name'])
            name.set_line_wrap(True)
            name.set_max_width_chars(25)
            titles.pack_start(name,False,False,0)
            status = 'Connected' if d['connected'] else 'Catalog · not connected'
            if d['connected'] and not d['ready']:
                status += ' · no lighting access'
            titles.pack_start(label(status,'muted'),False,False,0)
            box.pack_start(titles,True,True,0)
            row.add(box)
            self.device_list.add(row)
        self.device_list.show_all()
        self.filter_devices()
        connected = sum(d['connected'] for d in self.devices)
        self.device_count.set_text(f'{connected} connected · {len(self.catalog)} library models')
        target_id = self.selected_device['id'] if self.selected_device else None
        target = next((d for d in self.devices if d['id']==target_id),None)
        if target is None:
            target = next((d for d in self.devices if d['connected'] and d['ready']),None)
        if target is None:
            target = next((d for d in self.devices if d['connected']),None)
        if target:
            for row in self.device_list.get_children():
                if row.device['id'] == target['id']:
                    self.device_list.select_row(row)
                    break

    def row_selected(self, widget, row):
        if row is not None:
            self.select_device(row.device)

    def select_device(self, device):
        if self.selected_device:
            self.drafts[self.selected_device['id']] = self.settings()
        self.stop_keyboard()
        self.generation += 1
        self.selected_device = device
        self.device_title.set_text(device['name'])
        self.device_subtitle.set_text(device['vendor']+' · '+device['kind'].capitalize()+' · '+device['backend'])
        self.device_status.set_text(device['detail'] if device['connected'] else 'NOT CONNECTED · catalog preview only. Connect this model to query its actual lighting capabilities.')
        keyboard = device['backend']=='g810-led'
        lighting = device['backend'] in ('HID++ 8070','ratbagd') and bool(device['leds'])
        self.preview_stack.set_visible_child_name('keyboard' if keyboard else 'peripheral')
        self.panel_stack.set_visible_child_name('keyboard' if keyboard else 'lighting' if lighting else 'info')
        self.info_panel.set_text(('No lighting controls are exposed for this connected device.' if device['connected'] else 'Catalog reference only. Connect this model to query its real lighting controls.')+'\n\n'+device['detail'])
        s = self.drafts.get(device['id'],validate(DEFAULTS))
        self.effect.remove_all()
        for key,value in EFFECTS.items():
            if device.get('per_key') or key=='static':
                self.effect.append(key,value)
        self.effect.set_active_id(s['effect'] if device.get('per_key') else 'static')
        self.mouse_zone.remove_all()
        self.mouse_zone.append('all','All lighting zones')
        for z in device['leds']:
            self.mouse_zone.append(z['id'],z['name'])
        self.mouse_zone.set_active_id('all')
        self.populate_modes()
        self.restore_settings(s)
        self.keyboard_color.set_sensitive(device['rgb'])
        for widget in (self.key_choice,self.toggle_button,self.clear_button,self.reverse,self.speed):
            widget.set_sensitive(device.get('per_key',False))
        self.start_button.set_sensitive(device['ready'] and keyboard)
        self.off_button.set_sensitive(device['ready'] and keyboard)
        self.mouse_button.set_sensitive(device['ready'] and lighting and not self.mouse_busy)
        self.output_status.set_text('PREVIEW ONLY · select Start to send keyboard frames')
        self.lighting_note.set_text('Live HID++ acknowledgement and state verification; RAM only, no flash/profile commit.' if device['backend']=='HID++ 8070' else 'ratbagd firmware effects. Hardware commit is asynchronous; avoid other editors at the same time.')
        self.keyboard.queue_draw()
        self.peripheral.queue_draw()

    def populate_modes(self):
        d = self.selected_device or {}
        old = self.mouse_mode.get_active_id() or DEFAULTS['mouse_mode']
        zone = self.mouse_zone.get_active_id() or 'all'
        available = d.get('modes',[])
        if zone != 'all':
            available = next((z['modes'] for z in d.get('leds',[]) if z['id']==zone),[])
        self.mouse_mode.remove_all()
        for mode in ('static','breathing','cycle','off'):
            if mode in available:
                self.mouse_mode.append(mode,{'static':'Steady color','breathing':'Breathing','cycle':'Color cycle','off':'Off'}[mode])
        if not self.mouse_mode.set_active_id(old):
            self.mouse_mode.set_active(0)
        self.mouse_sensitivity()

    def mouse_sensitivity(self, *_):
        mode = self.mouse_mode.get_active_id()
        rgb = bool(self.selected_device and self.selected_device['rgb'])
        self.color.set_sensitive(rgb and mode in ('static','breathing'))
        self.period.set_sensitive(mode in ('breathing','cycle'))
        self.mouse_intensity.set_sensitive(mode not in ('off',None))

    def settings(self):
        def hex_color(widget):
            c = widget.get_rgba()
            return ''.join(f'{round(x*255):02x}' for x in (c.red,c.green,c.blue))
        return validate(dict(effect=self.effect.get_active_id() or 'static',brightness=round(self.intensity.get_value()),
            speed=self.speed.get_value(),reverse=self.reverse.get_active(),selected=sorted(self.selected),
            keyboard_color=hex_color(self.keyboard_color),mouse_mode=self.mouse_mode.get_active_id() or DEFAULTS['mouse_mode'],
            mouse_zone=self.mouse_zone.get_active_id() or 'all',mouse_color=hex_color(self.color),
            mouse_brightness=round(self.mouse_intensity.get_value()),mouse_period=round(self.period.get_value()*1000)))

    def restore_settings(self, s):
        if not self.effect.set_active_id(s['effect']):
            self.effect.set_active_id('static')
        self.intensity.set_value(s['brightness'])
        self.speed.set_value(s['speed'])
        self.reverse.set_active(s['reverse'])
        self.selected = set(s['selected'])
        self.selection_status()
        for widget,name in ((self.keyboard_color,'keyboard_color'),(self.color,'mouse_color')):
            rgba = Gdk.RGBA(); rgba.parse('#'+s[name]); widget.set_rgba(rgba)
        if not self.mouse_zone.set_active_id(s['mouse_zone']):
            self.mouse_zone.set_active_id('all')
        self.populate_modes()
        if not self.mouse_mode.set_active_id(s['mouse_mode']):
            self.mouse_mode.set_active(0)
        self.mouse_intensity.set_value(s['mouse_brightness'])
        self.period.set_value(s['mouse_period']/1000)

    def notify(self, text):
        if not self.closed:
            self.message.set_text(text)

    def tick(self):
        if self.closed:
            return False
        now = time.monotonic()
        if not self.pause.get_active():
            self.seconds += min(.2,now-self.last_tick)
        self.last_tick = now
        settings = self.settings()
        self.levels = frame(settings,self.seconds)
        self.keyboard.queue_draw()
        self.peripheral.queue_draw()
        if self.output and now-self.last_write >= .1 and (self.levels,settings['keyboard_color']) != self.last_frame:
            self.last_write = now
            levels = self.levels.copy()
            device_id,generation,color = self.output_id,self.generation,settings['keyboard_color']
            self.last_frame = (levels,color)
            self.io.submit('keyboard',lambda m:m.apply_keyboard(device_id,levels,color),
                lambda value,error:self.keyboard_result(device_id,generation,value,error))
        return True

    def keyboard_result(self, device_id, generation, value, error):
        if self.closed or generation != self.generation or not self.selected_device or self.selected_device['id'] != device_id:
            return False
        if error:
            self.stop_keyboard()
            self.notify('Keyboard output stopped: '+error)
        elif self.output:
            self.output_status.set_text('LIVE · sending frames to '+self.selected_device['name'])
        return False

    def start_keyboard(self, *_):
        d = self.selected_device
        if not d or not d['ready'] or d['backend']!='g810-led':
            self.notify('Selected device has no ready keyboard lighting backend.')
            return
        self.generation += 1
        self.output,self.output_id = True,d['id']
        self.last_frame = None
        self.output_status.set_text('STARTING · '+d['name'])
        self.notify('Keyboard output enabled for '+d['name']+'. Switching devices stops this output.')

    def stop_keyboard(self, *_):
        self.output = False
        self.output_id = None
        self.generation += 1
        self.io.cancel_keyboard()
        if hasattr(self,'output_status'):
            self.output_status.set_text('STOPPED · last frame frozen')

    def keyboard_off(self, *_):
        d = self.selected_device
        if not d or not d['ready'] or d['backend']!='g810-led':
            return
        self.stop_keyboard()
        device_id,generation = d['id'],self.generation
        self.io.submit('blackout',lambda m:m.apply_keyboard(device_id,{k:0 for k in KEY_NAMES}),
            lambda value,error:self.off_result(device_id,generation,value,error))

    def off_result(self, device_id, generation, value, error):
        if not self.closed and generation==self.generation and self.selected_device and self.selected_device['id']==device_id:
            self.notify('Blackout failed: '+error if error else 'Keyboard blackout frame sent. Preview remains independent.')
        return False

    def apply_mouse(self, *_):
        d = self.selected_device
        if not d or not d['ready'] or not d['leds'] or self.mouse_busy:
            return
        s,device_id,name = self.settings(),d['id'],d['name']
        self.mouse_busy = True
        self.mouse_button.set_sensitive(False)
        self.notify('Applying lighting to '+name+'…')
        self.io.submit('lighting',lambda m:m.apply_mouse(device_id,s['mouse_mode'],s['mouse_color'],s['mouse_brightness'],s['mouse_period'],s['mouse_zone']),
            lambda value,error:self.mouse_result(device_id,name,value,error))

    def mouse_result(self, device_id, name, value, error):
        if self.closed:
            return False
        self.mouse_busy = False
        d = self.selected_device or {}
        self.mouse_button.set_sensitive(bool(d.get('ready') and d.get('leds')))
        self.notify(name+': '+('Apply failed: '+error if error else value))
        return False

    def probe(self):
        self.io.submit('probe',lambda m:m.discover(),self.probe_result)

    def probe_result(self, result, error):
        if self.closed:
            return False
        if error:
            self.notify('Device discovery failed: '+error)
            return False
        self.devices = merge_devices(result,self.catalog)
        self.populate_sidebar()
        return False

    def selection_status(self):
        self.selected_status.set_text('Selected: '+', '.join(sorted(self.selected)) if self.selected else 'No keys selected')

    def toggle_key(self, name):
        if name not in KEY_NAMES or not self.selected_device or not self.selected_device['per_key']:
            return
        if name in self.selected:
            self.selected.remove(name)
        else:
            self.selected.add(name)
        self.effect.set_active_id('custom')
        self.selection_status()

    def clear_selection(self, *_):
        self.selected.clear()
        self.effect.set_active_id('custom')
        self.selection_status()

    def reload_profiles(self, name=''):
        try:
            self.profile_choice.remove_all()
            for n in sorted(self.profiles.load()):
                self.profile_choice.append_text(n)
            self.profile_choice.get_child().set_text(name)
        except (ValueError,OSError) as e:
            self.notify('Profiles unavailable; original file preserved: '+str(e))

    def save_profile(self, *_):
        name = self.profile_choice.get_child().get_text()
        try:
            self.profiles.save(name,self.settings())
            self.reload_profiles(name.strip())
            self.notify('Saved profile: '+name.strip())
        except (ValueError,OSError) as e:
            self.notify('Profile not saved: '+str(e))

    def load_profile(self, *_):
        try:
            name = self.profile_choice.get_child().get_text()
            profiles = self.profiles.load()
            if name not in profiles:
                raise ValueError('Choose an existing profile.')
            self.stop_keyboard()
            self.restore_settings(profiles[name])
            self.notify('Loaded '+name+' to preview only. Start or Apply is still required.')
        except (ValueError,OSError) as e:
            self.notify('Profile not loaded: '+str(e))

    def make_tray(self):
        self.tray = Gtk.StatusIcon.new_from_icon_name('input-keyboard')
        self.tray.set_title('Logibust')
        self.tray.set_tooltip_text('Logibust · Device Control')
        self.tray.connect('activate',lambda *_:self.show_studio())
        self.tray.connect('popup-menu',self.tray_menu)

    def show_studio(self):
        self.show_all()
        self.present()

    def tray_menu(self, icon, number, timestamp):
        menu = Gtk.Menu()
        for title,callback in [('Open Logibust',lambda *_:self.show_studio()),('Stop keyboard animation',self.stop_keyboard),('Quit Logibust',lambda *_:self.destroy())]:
            item = Gtk.MenuItem(label=title)
            item.connect('activate',callback)
            menu.append(item)
        menu.show_all()
        menu.popup(None,None,Gtk.StatusIcon.position_menu,icon,number,timestamp)

    def ensure_background_tray(self):
        if self.closed:
            self.tray_timer = None
            return False
        if self.tray.is_embedded():
            self.tray_timer = None
            print('Logibust: tray embedded; background startup ready.',flush=True)
            return False
        self.tray_attempts += 1
        if self.tray_attempts < 10:
            return True
        self.tray_timer = None
        self.notify('Desktop tray unavailable; showing the window so Logibust is accessible.')
        self.show_studio()
        return False

    def on_delete(self, *_):
        if self.tray.is_embedded():
            self.hide()
            return True
        return False

    def autostart_path(self):
        return Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'autostart/logibust.desktop'

    def autostart_enabled(self):
        try:
            return self.autostart_path().exists() and 'Hidden=true' not in self.autostart_path().read_text()
        except OSError:
            return False

    def set_autostart(self, *_):
        try:
            write_autostart(not self.autostart.get_active())
            self.notify('Background login launch '+('enabled.' if self.autostart.get_active() else 'disabled.'))
        except OSError as e:
            self.notify('Login preference not saved: '+str(e))

    def shutdown(self, *_):
        self.closed = True
        self.output = False
        GLib.source_remove(self.timer)
        if self.tray_timer:
            GLib.source_remove(self.tray_timer)
        self.tray.set_visible(False)
        self.io.close()


def desktop_entry(background=False, hidden=False):
    path = str(Path(__file__).resolve()).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
    return ('[Desktop Entry]\nType=Application\nName=Logibust Lighting Studio\n'
        'Comment=Native Linux peripheral lighting control\n'
        f'Exec=/usr/bin/python3 "{path}"'+(' --background' if background else '')+'\n'
        'Icon=input-keyboard\nTerminal=false\nCategories=Settings;HardwareSettings;\n'
        f'Hidden={str(hidden).lower()}\nX-GNOME-Autostart-enabled={str(not hidden).lower()}\n')


def write_autostart(hidden=False):
    dest = Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'autostart/logibust.desktop'
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(desktop_entry(background=True,hidden=hidden))
    return dest


class Application(Gtk.Application):
    def __init__(self, background=False):
        super().__init__(application_id='io.logibust.Studio',flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.background = background
        self.window = None

    def do_activate(self):
        if self.window is None:
            self.window = Studio(self,self.background)
        else:
            self.window.show_studio()


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--background',action='store_true')
    p.add_argument('--install-desktop',action='store_true')
    p.add_argument('--enable-autostart',action='store_true')
    args = p.parse_args()
    if args.install_desktop or args.enable_autostart:
        if args.install_desktop:
            dest = Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'applications/logibust.desktop'
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(desktop_entry())
            print(dest)
        if args.enable_autostart:
            print(write_autostart())
    else:
        Application(args.background).run([])
