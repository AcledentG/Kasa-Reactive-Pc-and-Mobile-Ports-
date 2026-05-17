"""
main.py
=======

Application entry point. Wires together audio, analyzer, controller,
reactor, and the Kivy UI.
"""

from __future__ import annotations

import os

os.environ.setdefault("KIVY_NO_CONSOLELOG", "0")
os.environ.setdefault("KIVY_LOG_LEVEL", "warning")

from kivy.app import App
from kivy.core.window import Window

from kasa_reactive import (
    AppConfig, load_config, save_config,
    BulbController, Reactor,
    PALETTES, make_default_source, IS_ANDROID,
)
from ui import build_screens


def request_android_permissions():
    if not IS_ANDROID:
        return
    try:
        from android.permissions import request_permissions, Permission
        request_permissions([
            Permission.RECORD_AUDIO,
            Permission.INTERNET,
            Permission.ACCESS_NETWORK_STATE,
            Permission.ACCESS_WIFI_STATE,
            Permission.VIBRATE,
        ])
    except Exception as e:
        print(f"[main] permission request failed (ok on desktop): {e}", flush=True)


class KasaReactiveApp(App):
    title = "Kasa Reactive"
    icon = "assets/icon.png"

    def build(self):
        request_android_permissions()
        self.config: AppConfig = load_config()
        self.palette = PALETTES[0]
        self.reactor: Reactor | None = None
        self.is_running = False
        self.rebuild_reactor()

        if self.config.use_amoled_black:
            Window.clearcolor = (0, 0, 0, 1)
        if self.config.keep_screen_on:
            self._keep_screen_on()

        self._sm = build_screens(self)
        return self._sm

    def rebuild_reactor(self):
        if self.reactor is not None:
            try: self.reactor.stop()
            except Exception: pass
            self.is_running = False

        source = make_default_source(
            sample_rate=44100, block_size=1024,
            device_name=self.config.audio_device,
        )
        controller = BulbController(
            self.config.bulbs, update_hz=self.config.update_hz,
        )
        self.reactor = Reactor(
            source=source, controller=controller,
            palette=self.palette, update_hz=30.0,
        )
        if self.config.haptics_on_beat:
            self.reactor.on_beat = self._buzz

    def start_reactor(self):
        if self.reactor is None:
            self.rebuild_reactor()
        self.reactor.start()
        self.is_running = True

    def stop_reactor(self):
        if self.reactor is not None:
            self.reactor.stop()
        self.is_running = False

    def set_palette(self, palette):
        self.palette = palette
        if self.reactor is not None:
            self.reactor.palette = palette

    def go_main(self): self._sm.current = "main"
    def go_settings(self): self._sm.current = "settings"
    def save(self): save_config(self.config)

    def _keep_screen_on(self):
        if not IS_ANDROID:
            return
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            View = autoclass("android.view.WindowManager$LayoutParams")
            activity = PythonActivity.mActivity
            Runnable = autoclass("java.lang.Runnable")
            class _R(Runnable):
                def __init__(self): super().__init__()
                def run(self):
                    activity.getWindow().addFlags(View.FLAG_KEEP_SCREEN_ON)
            activity.runOnUiThread(_R())
        except Exception as e:
            print(f"[main] keep_screen_on failed: {e}", flush=True)

    _last_buzz_time = 0.0

    def _buzz(self):
        import time as _t
        now = _t.monotonic()
        if now - self._last_buzz_time < 0.16:
            return
        self._last_buzz_time = now
        try:
            from plyer import vibrator
            vibrator.vibrate(0.04)
        except Exception:
            pass

    def on_stop(self):
        try:
            if self.reactor: self.reactor.stop()
        except Exception: pass
        try: save_config(self.config)
        except Exception: pass


if __name__ == "__main__":
    KasaReactiveApp().run()
