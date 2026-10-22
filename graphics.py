"""Original Cairo device illustrations; no vendor images or logos are bundled."""
import math
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gtk
from effects import KEYS, SOFTWARE_EFFECTS


def rounded(cr, x, y, w, h, radius=12):
    r = min(radius, w/2, h/2)
    cr.new_sub_path()
    for cx, cy, start in ((x+w-r,y+r,-math.pi/2), (x+w-r,y+h-r,0),
                           (x+r,y+h-r,math.pi/2), (x+r,y+r,math.pi)):
        cr.arc(cx,cy,r,start,start+math.pi/2)
    cr.close_path()


def text(cr, value, x, y, size=12, color=(.30,.32,.38)):
    cr.select_font_face('Sans')
    cr.set_font_size(size)
    cr.set_source_rgb(*color)
    cr.move_to(x,y)
    cr.show_text(value)


def silhouette(cr, kind, color=(.48,.32,.91), zone_colors=None):
    """A normalized 320 x 320 design field."""
    cr.set_line_width(2)
    if kind == 'mouse':
        cr.set_source_rgba(0,0,0,.08)
        cr.save(); cr.translate(164,293); cr.scale(1,.22); cr.arc(0,0,96,0,math.tau); cr.fill(); cr.restore()
        cr.move_to(129,20); cr.curve_to(181,4,227,38,241,94)
        cr.line_to(261,220); cr.curve_to(270,264,219,303,164,299)
        cr.curve_to(118,299,87,274,68,252); cr.line_to(47,232)
        cr.curve_to(64,198,83,183,87,139); cr.line_to(95,71)
        cr.curve_to(99,42,113,28,129,20); cr.close_path()
        cr.set_source_rgb(.14,.15,.18); cr.fill_preserve()
        cr.set_source_rgb(.29,.30,.34); cr.stroke()
        cr.move_to(157,24); cr.line_to(153,135); cr.line_to(224,148)
        cr.move_to(94,134); cr.line_to(151,137); cr.line_to(166,227)
        cr.set_source_rgb(.05,.06,.08); cr.stroke()
        rounded(cr,141,48,30,61,12); cr.set_source_rgb(.50,.51,.55); cr.fill()
        for y in range(54,104,7):
            cr.move_to(145,y); cr.line_to(167,y)
        cr.set_source_rgb(.20,.21,.25); cr.stroke()
        rounded(cr,135,119,20,14,3); cr.set_source_rgb(.34,.35,.39); cr.fill()
        for x,y in ((91,160),(85,173),(79,186)):
            rounded(cr,x,y,18,5,2); cr.set_source_rgb(*(zone_colors.get('0',color) if zone_colors else color)); cr.fill()
        # Generic light-window shape, deliberately not the Logitech trademark.
        cr.move_to(161,218); cr.line_to(185,232); cr.line_to(163,255); cr.line_to(143,236); cr.close_path()
        cr.set_source_rgb(*(zone_colors.get('1',color) if zone_colors else color)); cr.fill()
        cr.move_to(103,146); cr.line_to(128,166); cr.line_to(115,183); cr.line_to(93,177)
        cr.set_source_rgb(.32,.33,.38); cr.stroke()
    elif kind == 'keyboard':
        rounded(cr,10,87,300,140,14); cr.set_source_rgb(.17,.18,.22); cr.fill()
        for r in range(5):
            for c in range(16):
                rounded(cr,19+c*18,97+r*23,15,18,2)
                cr.set_source_rgb(.30,.31,.36); cr.fill()
        rounded(cr,93,195,99,18,2); cr.set_source_rgb(*color); cr.fill()
    elif kind == 'headset':
        cr.arc(160,140,95,math.pi,math.tau)
        cr.set_line_width(26); cr.set_source_rgb(.18,.19,.23); cr.stroke()
        cr.arc(160,140,95,math.pi,math.tau)
        cr.set_line_width(5); cr.set_source_rgb(*color); cr.stroke()
        for x in (48,221):
            rounded(cr,x,132,51,113,22); cr.set_source_rgb(.17,.18,.22); cr.fill_preserve()
            cr.set_source_rgb(.34,.35,.39); cr.set_line_width(3); cr.stroke()
            rounded(cr,x+11,147,29,83,12); cr.set_source_rgb(*color); cr.fill()
        cr.move_to(63,234); cr.curve_to(61,269,97,278,122,267)
        cr.set_source_rgb(.23,.24,.29); cr.set_line_width(9); cr.stroke()
    elif kind == 'mousepad':
        rounded(cr,16,76,288,181,20); cr.set_source_rgb(.15,.16,.19); cr.fill_preserve()
        cr.set_source_rgb(*color); cr.set_line_width(5); cr.stroke()
        rounded(cr,34,88,60,16,4); cr.set_source_rgb(.28,.29,.33); cr.fill()
    elif kind == 'speaker':
        for x in (33,182):
            rounded(cr,x,43,105,234,13); cr.set_source_rgb(.16,.17,.21); cr.fill()
            for y,r in ((100,26),(203,38)):
                cr.arc(x+52,y,r,0,math.tau); cr.set_source_rgb(.28,.29,.33); cr.fill_preserve()
                cr.set_source_rgb(*color); cr.set_line_width(4); cr.stroke()
                cr.arc(x+52,y,r*.38,0,math.tau); cr.set_source_rgb(.10,.11,.14); cr.fill()
    else:
        rounded(cr,58,100,204,129,17); cr.set_source_rgb(.19,.20,.25); cr.fill_preserve()
        cr.set_source_rgb(.38,.39,.44); cr.set_line_width(3); cr.stroke()
        cr.move_to(160,100); cr.line_to(160,50); cr.curve_to(160,25,206,40,218,17)
        cr.set_source_rgb(.30,.31,.36); cr.set_line_width(6); cr.stroke()
        for x in (96,154,212):
            cr.arc(x,165,10,0,math.tau); cr.set_source_rgb(*color); cr.fill()


class DeviceIcon(Gtk.DrawingArea):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self.set_size_request(42,46)
        self.connect('draw',self.draw)

    def draw(self, widget, cr):
        cr.save(); cr.scale(42/320,42/320)
        silhouette(cr,self.kind)
        cr.restore()
        return False


class PeripheralView(Gtk.DrawingArea):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.set_size_request(630,300)
        self.connect('draw',self.draw)
        self.get_accessible().set_name('Selected peripheral lighting illustration')

    def draw(self, widget, cr):
        w,h = self.get_allocated_width(),self.get_allocated_height()
        d = self.studio.selected_device or {}
        rgb = self.studio.color.get_rgba()
        mode = self.studio.mouse_mode.get_active_id() or 'static'
        intensity = self.studio.mouse_intensity.get_value()/255
        if mode == 'off': intensity = 0
        elif mode == 'breathing':
            intensity *= .15+.85*(1-math.cos(self.studio.seconds*math.tau/max(1,self.studio.period.get_value())))/2
        elif mode == 'cycle':
            import colorsys
            r,g,b = colorsys.hsv_to_rgb((self.studio.seconds/max(1,self.studio.period.get_value()))%1,.85,1)
            rgb.red,rgb.green,rgb.blue = r,g,b
        color = tuple(.18+(c*.82)*intensity for c in (rgb.red,rgb.green,rgb.blue))
        zones = None
        if d.get('backend')=='HID++ 8070':
            chosen = self.studio.mouse_zone.get_active_id() or 'all'
            zones = {zone:tuple(.06+.94*c/255 for c in channels) if chosen in ('all',zone) else (.22,.23,.26)
                for zone,channels in self.studio.mouse_colors.items()}
        size = min(h-18,320)
        cr.save(); cr.translate((w-size)/2,4); cr.scale(size/320,size/320)
        silhouette(cr,d.get('kind','other'),color,zones)
        cr.restore()
        text(cr,'Software scene · DPI / logo zones' if mode in SOFTWARE_EFFECTS else 'Lighting preview',26,35,12,(.43,.35,.65))
        text(cr,'Original illustration · not a product photograph',26,h-13,10,(.45,.46,.52))
        return False


class KeyboardView(Gtk.DrawingArea):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.rectangles = []
        self.set_size_request(630,285)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect('draw',self.draw)
        self.connect('button-press-event',self.click)
        self.get_accessible().set_name('Physical keyboard lighting preview; use named key selector for keyboard access')

    def draw(self, widget, cr):
        w,h = self.get_allocated_width(),self.get_allocated_height()
        unit = min((w-32)/23,(h-45)/9)
        ox,oy = (w-unit*23)/2,18
        rounded(cr,ox-7,oy-8,23*unit+14,7.8*unit+10,12)
        cr.set_source_rgb(.15,.16,.19); cr.fill()
        device = self.studio.selected_device or {}
        rgb = self.studio.keyboard_color.get_rgba()
        channels = (rgb.red,rgb.green,rgb.blue) if device.get('rgb') else (1,1,1)
        self.rectangles = []
        for k in KEYS:
            x,y,kw,kh = ox+k.x*unit+1.5,oy+k.y*unit+1.5,k.w*unit-3,k.h*unit-3
            level = self.studio.levels.get(k.name,0)/255
            rounded(cr,x,y,kw,kh,2)
            cr.set_source_rgb(*(.24+c*.70*level for c in channels)); cr.fill_preserve()
            selected = k.name in self.studio.selected
            cr.set_source_rgb(*((.52,.30,.97) if selected else (.37,.38,.43)))
            cr.set_line_width(2 if selected else .5); cr.stroke()
            cr.set_source_rgb(*((.10,.11,.15) if level>.6 else (.91,.92,.95)))
            cr.select_font_face('Sans'); cr.set_font_size(max(7,min(10,unit*.30)))
            value = k.label[3:] if k.name.startswith('num') and len(k.label)==4 else k.label
            ext = cr.text_extents(value)
            cr.move_to(x+(kw-ext.width)/2-ext.x_bearing,y+(kh-ext.height)/2-ext.y_bearing); cr.show_text(value)
            self.rectangles.append((k.name,x,y,kw,kh))
        text(cr,'ISO / ABNT extras · physical-key reference, not language detection',ox+5.2*unit,oy+8.7*unit,9,(.44,.45,.51))
        return False

    def click(self, widget, event):
        if event.button != 1:
            return False
        device = self.studio.selected_device or {}
        if not device.get('per_key'):
            return False
        for name,x,y,w,h in self.rectangles:
            if x <= event.x <= x+w and y <= event.y <= y+h:
                self.studio.toggle_key(name)
                break
        return True
