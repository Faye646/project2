"""Records the demo video: starts the Windows player (Builds/Windows/BianHe.exe) with -video, which plays the demo by
itself (GameFlow.PlayForVideo: the shop opening, cooking the orders, the table eating, close-ups of the other dishes
in the wok and on the trays) and quits; records its window with ffmpeg (gdigrab, from the imageio-ffmpeg package)
meanwhile, and trims the splash screen off the start.

    python Unity/Tools/record_video.py <out.mp4>
"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

import imageio_ffmpeg

OUT = sys.argv[1]
RAW = OUT + '.raw.mp4'
EXE = 'E:/project2/Builds/Windows/BianHe.exe'
W, H = 1600, 900
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()   # physical pixels, as gdigrab sees the desktop

game = subprocess.Popen([EXE, '-screen-width', str(W), '-screen-height', str(H), '-screen-fullscreen', '0', '-video'])
hwnd = 0
for _ in range(200):
    time.sleep(0.1)
    hwnd = user32.FindWindowW(None, '汴河两岸')
    if hwnd:
        break
if not hwnd:
    game.kill()
    sys.exit('no game window')
rc = wintypes.RECT()
for _ in range(300):   # until the player has sized its window
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    if rc.right - rc.left >= W * 0.9:
        break
    time.sleep(0.05)
    hwnd = user32.FindWindowW(None, '汴河两岸') or hwnd
user32.SetForegroundWindow(hwnd)
time.sleep(0.2)
user32.GetClientRect(hwnd, ctypes.byref(rc))
pt = wintypes.POINT(0, 0)
user32.ClientToScreen(hwnd, ctypes.byref(pt))
w, h = (rc.right - rc.left) // 2 * 2, (rc.bottom - rc.top) // 2 * 2
print('window client', pt.x, pt.y, w, h, flush=True)
ff = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'error', '-f', 'gdigrab', '-framerate', '30',
                       '-draw_mouse', '0', '-offset_x', str(pt.x), '-offset_y', str(pt.y), '-video_size', f'{w}x{h}',
                       '-i', 'desktop', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
                       RAW], stdin=subprocess.PIPE)
t0 = time.time()
while game.poll() is None and time.time() - t0 < 180:
    time.sleep(0.25)
    user32.SetForegroundWindow(hwnd)
ff.communicate(b'q')
if game.poll() is None:
    game.kill()
# the first seconds are the splash screen: cut, and the rest kept as it is
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'error', '-ss', '2.6', '-i', RAW, '-c:v', 'libx264',
                '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', OUT], check=True)
os.remove(RAW)
print('recorded', round(time.time() - t0, 1), 's ->', OUT, flush=True)
