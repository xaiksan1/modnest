"""hotkey.py — watches Right Ctrl (and Right Ctrl + Space) under X11.

Reads X keyboard events with `xinput test-xi2 --root` and prints only two
words: TOGGLE (Right Ctrl tapped alone) and TRANSLATE (Space pressed while
Right Ctrl is held). Every other key is read and dropped on the spot: nothing
is stored, nothing is written, nothing leaves this process.
"""
import os
import re
import subprocess
import sys

# X11 keycodes (default: Control_R and the space bar; see `xmodmap -pke`)
CTRL_R = int(sys.argv[1]) if len(sys.argv) > 1 else 105
SPACE = int(sys.argv[2]) if len(sys.argv) > 2 else 65
os.environ.setdefault("DISPLAY", ":0")


def main() -> None:
    try:
        p = subprocess.Popen(["xinput", "test-xi2", "--root"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, bufsize=1)
    except OSError as e:
        print(f"ERR\txinput not found ({e.__class__.__name__})", flush=True)
        return
    kind, down, ctrl_down, chord_used = None, set(), False, False
    for line in p.stdout:
        m = re.match(r"EVENT type \d+ \((KeyPress|KeyRelease)\)", line)
        if m:
            kind = m.group(1)
            continue
        m = re.match(r"\s+detail: (\d+)", line)
        if not m or kind is None:
            continue
        code, pressed, kind = int(m.group(1)), kind == "KeyPress", None
        if pressed:
            if code in down:                       # auto-repeat or duplicate from another device
                continue
            down.add(code)
            if code == CTRL_R:
                ctrl_down, chord_used = True, False
            elif ctrl_down:
                chord_used = True
                if code == SPACE:
                    print("TRANSLATE", flush=True)
        else:
            down.discard(code)
            if code == CTRL_R and ctrl_down:
                ctrl_down = False
                if not chord_used:
                    print("TOGGLE", flush=True)
    print("ERR\txinput stopped", flush=True)


if __name__ == "__main__":
    main()
