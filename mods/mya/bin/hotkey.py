"""hotkey.py — watches Right Ctrl under X11.

Reads X input events with `xinput test-xi2 --root` and prints only three words:
  TOGGLE    Right Ctrl tapped alone (quickly, no other key, no mouse button)
  TRANSLATE the space bar pressed while Right Ctrl is held
  LOCK      Right Shift pressed while Right Ctrl is held (switches the hotkey on/off)
Every other key and mouse event is read and dropped on the spot: nothing is stored,
nothing is written, nothing leaves this process. A Ctrl that is held for a while, or used
with a key or a mouse click (copy-paste, Ctrl+click, Ctrl+scroll), is not a tap.
"""
import os
import re
import subprocess
import sys
import time

# X11 keycodes (defaults: Control_R, space, Shift_R; see `xmodmap -pke`) and the longest press that still counts as a tap
CTRL_R = int(sys.argv[1]) if len(sys.argv) > 1 else 105
SPACE = int(sys.argv[2]) if len(sys.argv) > 2 else 65
LOCK = int(sys.argv[3]) if len(sys.argv) > 3 else 62
MAX_TAP = float(sys.argv[4]) if len(sys.argv) > 4 else 0.8
os.environ.setdefault("DISPLAY", ":0")


def main() -> None:
    try:
        p = subprocess.Popen(["xinput", "test-xi2", "--root"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, bufsize=1)
    except OSError as e:
        print(f"ERR\txinput not found ({e.__class__.__name__})", flush=True)
        return
    kind, down, ctrl_down, chord_used, pressed_at = None, set(), False, False, 0.0
    for line in p.stdout:
        m = re.match(r"EVENT type \d+ \((KeyPress|KeyRelease|ButtonPress|ButtonRelease)\)", line)
        if m:
            kind = m.group(1)
            continue
        m = re.match(r"\s+detail: (\d+)", line)
        if not m or kind is None:
            continue
        code, what, kind = int(m.group(1)), kind, None
        if what == "ButtonPress":                  # a mouse click or scroll while Ctrl is held: not a tap
            if ctrl_down:
                chord_used = True
            continue
        if what == "ButtonRelease":
            continue
        if what == "KeyPress":
            if code in down:                       # auto-repeat or duplicate from another device
                continue
            down.add(code)
            if code == CTRL_R:
                ctrl_down, chord_used, pressed_at = True, False, time.monotonic()
            elif ctrl_down:
                chord_used = True
                if code == SPACE:
                    print("TRANSLATE", flush=True)
                elif code == LOCK:
                    print("LOCK", flush=True)
        else:
            down.discard(code)
            if code == CTRL_R and ctrl_down:
                ctrl_down = False
                if not chord_used and time.monotonic() - pressed_at <= MAX_TAP:
                    print("TOGGLE", flush=True)
    print("ERR\txinput stopped", flush=True)


if __name__ == "__main__":
    main()
