"""Opens the WebGL build in headless Edge as a phone (landscape, touch) and drives it with real touch
events over the DevTools protocol: load, one-finger drag, two-finger pinch, tap on the 案台.
Saves a screenshot after each step.

    python -m http.server 8765 --bind 127.0.0.1   (in Builds/WebGL)
    python Unity/Tools/webgl_touch_test.py http://127.0.0.1:8765/ <out_dir>
Needs: pip install websocket-client; Microsoft Edge.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

import websocket

URL, OUT = sys.argv[1], sys.argv[2]
EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
W, H = 844, 390  # iPhone 14 landscape, CSS pixels
os.makedirs(OUT, exist_ok=True)

profile = tempfile.mkdtemp()
edge = subprocess.Popen([EDGE, '--headless=new', '--remote-debugging-port=9333', f'--user-data-dir={profile}',
                         '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist',
                         f'--window-size={W},{H}', 'about:blank'])
try:
    for _ in range(50):
        try:
            tabs = json.load(urllib.request.urlopen('http://127.0.0.1:9333/json'))
            page = next(t for t in tabs if t['type'] == 'page')
            break
        except Exception:
            time.sleep(0.2)
    ws = websocket.create_connection(page['webSocketDebuggerUrl'], suppress_origin=True)
    seq = [0]

    def cdp(method, **params):
        seq[0] += 1
        ws.send(json.dumps({'id': seq[0], 'method': method, 'params': params}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get('id') == seq[0]:
                if 'error' in msg:
                    raise RuntimeError(f'{method}: {msg["error"]}')
                return msg.get('result', {})

    def shot(name):
        data = cdp('Page.captureScreenshot', format='png')['data']
        with open(os.path.join(OUT, name + '.png'), 'wb') as f:
            f.write(base64.b64decode(data))
        print('shot', name, flush=True)

    def touch(kind, points):
        cdp('Input.dispatchTouchEvent', type=kind, touchPoints=[{'x': x, 'y': y, 'id': i} for i, (x, y) in enumerate(points)])

    def gesture(start, end, steps=12):
        touch('touchStart', start)
        for k in range(1, steps + 1):
            t = k / steps
            touch('touchMove', [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for a, b in zip(start, end)])
            time.sleep(0.03)
        touch('touchEnd', [])

    cdp('Page.enable')
    cdp('Runtime.enable')
    cdp('Emulation.setDeviceMetricsOverride', width=W, height=H, deviceScaleFactor=2, mobile=True,
        screenOrientation={'type': 'landscapePrimary', 'angle': 90})
    cdp('Emulation.setTouchEmulationEnabled', enabled=True, maxTouchPoints=5)
    cdp('Emulation.setUserAgentOverride', userAgent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1')
    cdp('Page.navigate', url=URL)
    t0 = time.time()
    while time.time() - t0 < 120:  # wait for the Unity player to finish loading
        r = cdp('Runtime.evaluate', expression="document.querySelector('#unity-loading-bar') ? "
                "getComputedStyle(document.querySelector('#unity-loading-bar')).display : 'none'", returnByValue=True)
        if r['result'].get('value') == 'none' and time.time() - t0 > 3:
            break
        time.sleep(1)
    print(f'loaded in {time.time() - t0:.0f} s', flush=True)
    time.sleep(6)
    shot('1_loaded')
    gesture([(W * 0.6, H * 0.5)], [(W * 0.35, H * 0.55)])
    time.sleep(1.5)
    shot('2_after_drag')
    gesture([(W * 0.45, H * 0.5), (W * 0.55, H * 0.5)], [(W * 0.3, H * 0.5), (W * 0.7, H * 0.5)])
    time.sleep(1.5)
    shot('3_after_pinch')
    logs = cdp('Runtime.evaluate', expression='document.title', returnByValue=True)
    print('title', logs['result'].get('value'))
finally:
    edge.kill()
