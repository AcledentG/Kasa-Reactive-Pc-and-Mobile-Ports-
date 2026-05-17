[app]

title = Kasa Reactive

package.name = kasareactive
package.domain = org.kasareactive

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.include_patterns = assets/*

version = 1.0.0

# Lean dependency list. No numpy, no python-kasa, no aiohttp.
# The audio FFT is hand-rolled in pure Python; the Kasa protocol is
# implemented directly over a socket. This dodges all the cross-
# compilation issues that the heavier dependency set was hitting.
requirements = python3,kivy==2.3.1,pyjnius,plyer

icon.filename = assets/icon.png

presplash.filename = assets/icon.png
presplash.color = #000000

orientation = all
fullscreen = 0

android.permissions = INTERNET,RECORD_AUDIO,VIBRATE,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE,WAKE_LOCK

android.api = 34
android.minapi = 24
android.archs = arm64-v8a

android.accept_sdk_license = True
android.logcat_filters = *:S python:D
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
