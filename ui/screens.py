"""
ui/screens.py
=============

Kivy GUI: main reactive view + settings.

Polish update: all sizes use dp() and sp() so widgets render at the
right physical size on high-DPI phone screens. Font sizes bumped up
to be readable at arm's length on a phone.
"""

from __future__ import annotations

import threading
from functools import partial

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.screenmanager import Screen, ScreenManager, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.properties import NumericProperty, StringProperty

from kasa_reactive import (
    BulbEntry, PALETTES, Palette, BAND_ORDER, discover_lan,
)


BG = (0, 0, 0, 1)
PANEL = (0.07, 0.07, 0.09, 1)
ACCENT = (0.95, 0.2, 0.65, 1)
ACCENT_2 = (0.15, 0.7, 0.95, 1)
TEXT = (0.95, 0.95, 0.95, 1)
TEXT_DIM = (0.6, 0.6, 0.6, 1)


def _hsv_to_rgb(h, s, v):
    if s == 0.0:
        return v, v, v
    h = h % 1.0
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    return [(v,t,p),(q,v,p),(p,v,t),(p,q,v),(t,p,v),(v,p,q)][i % 6]


class BandMeter(Widget):
    level = NumericProperty(0.0)
    label_text = StringProperty("")

    def __init__(self, label, **kwargs):
        super().__init__(**kwargs)
        self.label_text = label
        self.bind(pos=self._redraw, size=self._redraw, level=self._redraw)

    def _redraw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(0.12, 0.12, 0.14, 1)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(6)])
            bar_h = self.size[1] * max(0.02, self.level)
            r = min(1.0, 0.2 + self.level * 0.8)
            g = max(0.0, 0.6 - self.level * 0.6)
            b = min(1.0, 0.6 + (1.0 - self.level) * 0.4)
            Color(r, g, b, 1)
            RoundedRectangle(pos=self.pos, size=(self.size[0], bar_h), radius=[dp(6)])


class Card(BoxLayout):
    def __init__(self, title, **kwargs):
        kwargs.setdefault("orientation", "vertical")
        kwargs.setdefault("padding", (dp(14), dp(12), dp(14), dp(14)))
        kwargs.setdefault("spacing", dp(10))
        super().__init__(**kwargs)
        self.bind(pos=self._redraw, size=self._redraw)
        title_label = Label(
            text=f"[b]{title}[/b]", markup=True, color=TEXT,
            size_hint_y=None, height=dp(28), halign="left", valign="middle",
            font_size=sp(16),
        )
        title_label.bind(size=lambda lbl, *_: setattr(
            lbl, "text_size", (lbl.width, lbl.height)
        ))
        super().add_widget(title_label)

    def _redraw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*PANEL)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(16)])


def _draw_swatch(widget, palette, idx):
    widget.canvas.clear()
    with widget.canvas:
        hue, sat = palette.slots[idx % len(palette.slots)]
        r, g, b = _hsv_to_rgb(hue / 360.0, sat / 100.0, 1.0)
        Color(r, g, b, 1)
        RoundedRectangle(pos=widget.pos, size=widget.size, radius=[dp(10)])


class MainScreen(Screen):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._build()
        Clock.schedule_interval(self._tick, 1.0 / 30.0)

    def _build(self):
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        with root.canvas.before:
            Color(*BG)
            self._bg_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._sync_bg, size=self._sync_bg)
        self._root = root

        self.status_label = Label(
            text="Idle - set up bulbs in Settings",
            color=TEXT, size_hint_y=None, height=dp(40),
            halign="left", valign="middle", font_size=sp(16),
        )
        self.status_label.bind(size=lambda lbl, *_: setattr(
            lbl, "text_size", (lbl.width, lbl.height)
        ))
        root.add_widget(self.status_label)

        self.bpm_label = Label(
            text="BPM: --   Beat: --",
            color=TEXT_DIM, size_hint_y=None, height=dp(28),
            halign="left", valign="middle", font_size=sp(14),
        )
        self.bpm_label.bind(size=lambda lbl, *_: setattr(
            lbl, "text_size", (lbl.width, lbl.height)
        ))
        root.add_widget(self.bpm_label)

        meters_card = Card("Band Levels", size_hint_y=0.45)
        meters_row = BoxLayout(orientation="horizontal", spacing=dp(6))
        self.meters = {}
        for band in BAND_ORDER:
            col = BoxLayout(orientation="vertical", spacing=dp(4))
            meter = BandMeter(label=band)
            col.add_widget(meter)
            col.add_widget(Label(
                text=band, color=TEXT_DIM, size_hint_y=None, height=dp(22),
                font_size=sp(11),
            ))
            meters_row.add_widget(col)
            self.meters[band] = meter
        meters_card.add_widget(meters_row)
        root.add_widget(meters_card)

        palette_card = Card("Palette", size_hint_y=None, height=dp(150))
        palette_row = BoxLayout(orientation="horizontal", spacing=dp(8),
                                size_hint_y=None, height=dp(52))
        self.palette_spinner = Spinner(
            text=self.app.palette.name,
            values=[p.name for p in PALETTES],
            background_color=ACCENT, color=(1, 1, 1, 1),
            font_size=sp(15),
        )
        self.palette_spinner.bind(text=self._on_palette_picked)
        palette_row.add_widget(self.palette_spinner)
        prev_btn = Button(text="<", size_hint_x=None, width=dp(54),
                          background_color=PANEL, color=TEXT, font_size=sp(18))
        prev_btn.bind(on_release=lambda *_: self._cycle_palette(-1))
        palette_row.add_widget(prev_btn)
        next_btn = Button(text=">", size_hint_x=None, width=dp(54),
                          background_color=PANEL, color=TEXT, font_size=sp(18))
        next_btn.bind(on_release=lambda *_: self._cycle_palette(+1))
        palette_row.add_widget(next_btn)
        palette_card.add_widget(palette_row)

        self.swatch_row = BoxLayout(orientation="horizontal", spacing=dp(8),
                                    size_hint_y=None, height=dp(44))
        palette_card.add_widget(self.swatch_row)
        self._rebuild_swatches()
        root.add_widget(palette_card)

        react_card = Card("Reactivity", size_hint_y=None, height=dp(150))
        attack_row = BoxLayout(orientation="horizontal", spacing=dp(10),
                               size_hint_y=None, height=dp(40))
        attack_lbl = Label(text="Attack", color=TEXT, size_hint_x=0.3,
                           font_size=sp(14), halign="left", valign="middle")
        attack_lbl.bind(size=lambda lbl, *_: setattr(
            lbl, "text_size", (lbl.width, lbl.height)))
        attack_row.add_widget(attack_lbl)
        self.attack_slider = Slider(min=0.05, max=1.0, value=0.5,
                                    cursor_size=(dp(32), dp(32)))
        self.attack_slider.bind(value=self._on_attack)
        attack_row.add_widget(self.attack_slider)
        react_card.add_widget(attack_row)
        release_row = BoxLayout(orientation="horizontal", spacing=dp(10),
                                size_hint_y=None, height=dp(40))
        release_lbl = Label(text="Release", color=TEXT, size_hint_x=0.3,
                            font_size=sp(14), halign="left", valign="middle")
        release_lbl.bind(size=lambda lbl, *_: setattr(
            lbl, "text_size", (lbl.width, lbl.height)))
        release_row.add_widget(release_lbl)
        self.release_slider = Slider(min=0.01, max=0.5, value=0.08,
                                     cursor_size=(dp(32), dp(32)))
        self.release_slider.bind(value=self._on_release)
        release_row.add_widget(self.release_slider)
        react_card.add_widget(release_row)
        root.add_widget(react_card)

        btn_row = BoxLayout(orientation="horizontal", spacing=dp(10),
                            size_hint_y=None, height=dp(60))
        self.start_btn = Button(
            text="Start", background_color=ACCENT, color=(1, 1, 1, 1),
            font_size=sp(18),
        )
        self.start_btn.bind(on_release=self._on_start_stop)
        btn_row.add_widget(self.start_btn)
        settings_btn = Button(
            text="Settings", background_color=ACCENT_2, color=(1, 1, 1, 1),
            font_size=sp(18),
        )
        settings_btn.bind(on_release=lambda *_: self.app.go_settings())
        btn_row.add_widget(settings_btn)
        root.add_widget(btn_row)

        self.add_widget(root)

    def _sync_bg(self, *_):
        self._bg_rect.pos = self._root.pos
        self._bg_rect.size = self._root.size

    def _rebuild_swatches(self):
        self.swatch_row.clear_widgets()
        if not self.app.config.bulbs:
            self.swatch_row.add_widget(Label(
                text="(no bulbs - add them in Settings)", color=TEXT_DIM,
                font_size=sp(13),
            ))
            return
        for i in range(len(self.app.config.bulbs)):
            sw = Widget()
            sw.bind(
                pos=lambda w, *_, idx=i: _draw_swatch(w, self.app.palette, idx),
                size=lambda w, *_, idx=i: _draw_swatch(w, self.app.palette, idx),
            )
            self.swatch_row.add_widget(sw)
            _draw_swatch(sw, self.app.palette, i)

    def _on_palette_picked(self, spinner, name):
        for p in PALETTES:
            if p.name == name:
                self.app.set_palette(p)
                self._rebuild_swatches()
                return

    def _cycle_palette(self, direction):
        cur = self.app.palette.name
        names = [p.name for p in PALETTES]
        try: idx = names.index(cur)
        except ValueError: idx = 0
        new_idx = (idx + direction) % len(names)
        self.palette_spinner.text = names[new_idx]

    def _on_attack(self, slider, value):
        if self.app.reactor and self.app.reactor._analyzer:
            self.app.reactor._analyzer.attack = float(value)

    def _on_release(self, slider, value):
        if self.app.reactor and self.app.reactor._analyzer:
            self.app.reactor._analyzer.release = float(value)

    def _on_start_stop(self, *_):
        if self.app.is_running:
            self.app.stop_reactor()
            self.start_btn.text = "Start"
            self.start_btn.background_color = ACCENT
        else:
            try:
                self.app.start_reactor()
                self.start_btn.text = "Stop"
                self.start_btn.background_color = (0.7, 0.15, 0.2, 1)
            except Exception as e:
                self._popup("Error", f"Could not start: {e}")

    def _tick(self, dt):
        r = self.app.reactor
        if r is None: return
        for band, meter in self.meters.items():
            meter.level = float(r.levels.get(band, 0.0))
        if r.bpm > 0:
            self.bpm_label.text = f"BPM: {r.bpm:.0f}   Beat: {'O' if r.beat_now else '.'}"
        else:
            self.bpm_label.text = f"BPM: --   Beat: {'O' if r.beat_now else '.'}"
        n_ok = sum(1 for b in self.app.config.bulbs if b.status == "ok")
        n_total = len(self.app.config.bulbs)
        if not self.app.is_running:
            self.status_label.text = f"Stopped ({n_ok}/{n_total} bulbs ready)"
        else:
            self.status_label.text = f"Reactive  {n_ok}/{n_total} bulbs"

    def _popup(self, title, message):
        Popup(title=title, content=Label(text=message, color=TEXT,
                                         font_size=sp(15)),
              size_hint=(0.85, 0.4)).open()


class SettingsScreen(Screen):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._build()

    def _build(self):
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
        with root.canvas.before:
            Color(*BG)
            self._bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda *_: setattr(self._bg, "pos", root.pos),
                  size=lambda *_: setattr(self._bg, "size", root.size))

        header = BoxLayout(orientation="horizontal", size_hint_y=None,
                           height=dp(54), spacing=dp(10))
        back = Button(text="< Back", size_hint_x=None, width=dp(120),
                      background_color=PANEL, color=TEXT, font_size=sp(16))
        back.bind(on_release=lambda *_: self.app.go_main())
        header.add_widget(back)
        header.add_widget(Label(text="[b]Settings[/b]", markup=True, color=TEXT,
                                font_size=sp(20)))
        root.add_widget(header)

        scroll = ScrollView()
        content = BoxLayout(orientation="vertical", spacing=dp(12),
                            size_hint_y=None, padding=(0, 0, 0, dp(20)))
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)

        bulbs_card = Card("Bulbs", size_hint_y=None, height=dp(360))
        self.bulb_list = BoxLayout(orientation="vertical", spacing=dp(6),
                                   size_hint_y=None)
        self.bulb_list.bind(minimum_height=self.bulb_list.setter("height"))
        bulbs_card.add_widget(self.bulb_list)

        btns = BoxLayout(orientation="horizontal", spacing=dp(10),
                         size_hint_y=None, height=dp(52))
        b1 = Button(text="Discover on LAN", background_color=ACCENT_2,
                    color=(1, 1, 1, 1), font_size=sp(15))
        b1.bind(on_release=self._on_discover)
        btns.add_widget(b1)
        b2 = Button(text="Add by IP", background_color=PANEL, color=TEXT,
                    font_size=sp(15))
        b2.bind(on_release=self._on_add_by_ip)
        btns.add_widget(b2)
        bulbs_card.add_widget(btns)
        content.add_widget(bulbs_card)

        info_card = Card("About", size_hint_y=None, height=dp(180))
        info_lbl = Label(
            text="On Android, audio comes from the microphone.\n"
                 "Sit your phone near your speakers for best results.\n\n"
                 "Bulbs must be on the same wifi network as the phone.",
            color=TEXT_DIM, halign="left", valign="top", font_size=sp(13),
        )
        info_lbl.bind(size=lambda lbl, *_: setattr(
            lbl, "text_size", (lbl.width, lbl.height)))
        info_card.add_widget(info_lbl)
        content.add_widget(info_card)

        save_btn = Button(
            text="Save & Apply", background_color=ACCENT, color=(1, 1, 1, 1),
            size_hint_y=None, height=dp(60), font_size=sp(18),
        )
        save_btn.bind(on_release=self._on_save)
        content.add_widget(save_btn)

        root.add_widget(scroll)
        self.add_widget(root)
        self._refresh_bulb_list()

    def _refresh_bulb_list(self):
        self.bulb_list.clear_widgets()
        if not self.app.config.bulbs:
            self.bulb_list.add_widget(Label(
                text="(no bulbs yet - discover or add by IP)",
                color=TEXT_DIM, size_hint_y=None, height=dp(36),
                font_size=sp(13),
            ))
            return
        for i, b in enumerate(self.app.config.bulbs):
            row = BoxLayout(orientation="horizontal", spacing=dp(8),
                            size_hint_y=None, height=dp(48))
            dot_color = {
                "ok": (0.2, 0.9, 0.4, 1),
                "connecting": (0.95, 0.8, 0.2, 1),
                "failed": (0.95, 0.2, 0.2, 1),
            }.get(b.status, (0.4, 0.4, 0.4, 1))
            dot = Widget(size_hint_x=None, width=dp(18))
            with dot.canvas:
                Color(*dot_color)
                d = RoundedRectangle(pos=dot.pos, size=(dp(14), dp(14)), radius=[dp(7)])
            dot.bind(pos=lambda w, *_, _d=d: setattr(_d, "pos", w.pos))
            row.add_widget(dot)
            name_lbl = Label(
                text=f"{b.alias or b.ip or b.mac}",
                color=TEXT, halign="left", valign="middle", font_size=sp(14),
            )
            name_lbl.bind(size=lambda lbl, *_: setattr(
                lbl, "text_size", (lbl.width, lbl.height)))
            row.add_widget(name_lbl)
            band_spin = Spinner(
                text=b.band, values=BAND_ORDER,
                size_hint_x=None, width=dp(130),
                background_color=PANEL, color=TEXT, font_size=sp(14),
            )
            band_spin.bind(text=partial(self._on_band_change, i))
            row.add_widget(band_spin)
            rm = Button(text="X", size_hint_x=None, width=dp(54),
                        background_color=(0.4, 0.1, 0.1, 1), color=TEXT,
                        font_size=sp(16))
            rm.bind(on_release=partial(self._on_remove, i))
            row.add_widget(rm)
            self.bulb_list.add_widget(row)

    def _on_band_change(self, index, spinner, value):
        self.app.config.bulbs[index].band = value

    def _on_remove(self, index, *_):
        self.app.config.bulbs.pop(index)
        self._refresh_bulb_list()

    def _on_discover(self, *_):
        def worker():
            try:
                found = discover_lan(timeout=4.0)
                Clock.schedule_once(lambda dt: self._discover_done(found), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._popup("Error", str(e)), 0)
        threading.Thread(target=worker, daemon=True).start()
        self._popup("Searching", "Scanning your network for Kasa bulbs.\n"
                                 "This takes about 4 seconds.")

    def _discover_done(self, found):
        existing_macs = {b.mac for b in self.app.config.bulbs}
        added = 0
        for b in found:
            if b.mac and b.mac not in existing_macs:
                bands = BAND_ORDER
                b.band = bands[len(self.app.config.bulbs) % len(bands)]
                self.app.config.bulbs.append(b)
                added += 1
        self._refresh_bulb_list()
        self._popup("Done", f"Discovered {len(found)} bulb(s), added {added} new.")

    def _on_add_by_ip(self, *_):
        box = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(10))
        ti = TextInput(hint_text="192.168.x.x", multiline=False,
                       size_hint_y=None, height=dp(52), font_size=sp(16))
        box.add_widget(ti)
        ok = Button(text="Add", size_hint_y=None, height=dp(56),
                    background_color=ACCENT, color=(1, 1, 1, 1), font_size=sp(17))
        box.add_widget(ok)
        p = Popup(title="Add bulb by IP", content=box, size_hint=(0.85, 0.45))

        def do_add(*_):
            ip = ti.text.strip()
            if ip:
                bands = BAND_ORDER
                self.app.config.bulbs.append(BulbEntry(
                    ip=ip,
                    band=bands[len(self.app.config.bulbs) % len(bands)],
                ))
                self._refresh_bulb_list()
            p.dismiss()
        ok.bind(on_release=do_add)
        p.open()

    def _on_save(self, *_):
        self.app.save()
        self.app.rebuild_reactor()
        self._popup("Saved", "Settings applied.")

    def _popup(self, title, message):
        Popup(title=title, content=Label(text=message, color=TEXT,
                                         font_size=sp(15)),
              size_hint=(0.85, 0.5)).open()


def build_screens(app) -> ScreenManager:
    sm = ScreenManager(transition=SlideTransition(duration=0.18))
    sm.add_widget(MainScreen(app=app, name="main"))
    sm.add_widget(SettingsScreen(app=app, name="settings"))
    return sm
