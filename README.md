# Kasa Reactive — Mobile (Lean)

Audio-reactive Kasa light show as an Android app. This is the
"lean" rewrite that strips out heavy dependencies (numpy, python-kasa,
aiohttp) and replaces them with minimal pure-Python implementations,
to dodge cross-compilation issues with the python-for-android toolchain.

## What's in it

- Microphone-based audio reactivity
- Hand-rolled FFT (pure Python, no numpy)
- Direct Kasa protocol over sockets (no python-kasa, no aiohttp)
- 33 color palettes
- Spectral-flux beat detection with BPM
- LAN bulb discovery via UDP broadcast
- Add-by-IP option for manual setup
- True-black AMOLED theme
- Haptic vibration on beats

## Working bulbs

Older Kasa bulbs that use the IOT protocol:
KL130, KL135, KL125, plus any HS plugs/switches.

Newer "Tapo"-branded or SMART-protocol Kasa devices won't work
with the lean protocol — those need python-kasa, which we removed.

## Building

Push to GitHub. The Actions workflow builds an APK. Download from
the run's Artifacts section.

## Running on desktop

```
pip install -r requirements.txt
python main.py
```
