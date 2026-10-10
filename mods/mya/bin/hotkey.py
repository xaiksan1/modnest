"""hotkey.py — turns a hotkey into three words, under X11 or under Wayland.

X11 mode (the default on an X11 session): reads X input events with `xinput test-xi2 --root` and prints only three words:
  TOGGLE    Right Ctrl tapped alone (quickly, no other key, no mouse button)
  TRANSLATE the space bar pressed while Right Ctrl is held
  LOCK      Right Shift pressed while Right Ctrl is held (switches the hotkey on/off)
Every other key and mouse event is read and dropped on the spot: nothing is stored,
nothing is written, nothing leaves this process. A Ctrl that is held for a while, or used
with a key or a mouse click (copy-paste, Ctrl+click, Ctrl+scroll), is not a tap.

Socket mode (the default on a Wayland session, or MYA_HOTKEY_MODE=socket): NO KEY IS EVER READ. Wayland does not let a program
watch the keyboard, and reading /dev/input would need a group that can log every password. Instead the desktop itself
(GNOME custom shortcuts, see mya_gnome_shortcuts.py) runs `mya-key toggle|translate|lock` when its own key combination
is pressed; that command drops the word into a private socket ($XDG_RUNTIME_DIR/mya-hotkey.sock, mode 0600), and this
helper prints it. Only those three words are accepted; anything else is refused and prints nothing.
Mode is chosen by MYA_HOTKEY_MODE = auto (default) | x11 | socket; auto looks at XDG_SESSION_TYPE.
"""
import os
import re
import signal
import socket
import subprocess
import sys
import time

# X11 keycodes (defaults: Control_R, space, Shift_R; see `xmodmap -pke`) and the longest press that still counts as a tap
CTRL_R = int(sys.argv[1]) if len(sys.argv) > 1 else 105
SPACE = int(sys.argv[2]) if len(sys.argv) > 2 else 65
LOCK = int(sys.argv[3]) if len(sys.argv) > 3 else 62
MAX_TAP = float(sys.argv[4]) if len(sys.argv) > 4 else 0.8
os.environ.setdefault("DISPLAY", ":0")

WORDS = {"toggle": "TOGGLE", "translate": "TRANSLATE", "lock": "LOCK"}
MAX_LINE = 32            # the longest valid line is "translate" + a newline: anything longer is refused


def mode() -> str:
    chosen = os.environ.get("MYA_HOTKEY_MODE", "auto")
    if chosen in ("x11", "socket"):
        return chosen
    return "socket" if os.environ.get("XDG_SESSION_TYPE") == "wayland" else "x11"


def socket_path() -> str | None:
    explicit = os.environ.get("MYA_HOTKEY_SOCKET")
    if explicit:
        return explicit
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    return os.path.join(runtime, "mya-hotkey.sock") if runtime else None


def parse(raw: bytes) -> str | None:
    """The word for one request, or None. Exactly one line, exactly one of the three words (case and spaces aside)."""
    if len(raw) > MAX_LINE:
        return None
    line, _, rest = raw.partition(b"\n")
    if rest.strip():
        return None                                       # a second line: refused whole
    try:
        text = line.decode("ascii")
    except UnicodeDecodeError:
        return None
    return WORDS.get(text.strip().lower())


def serve_socket() -> None:
    path = socket_path()
    if path is None:
        print("ERR\tno runtime dir", flush=True)
        return
    if os.path.exists(path):
        probe = socket.socket(socket.AF_UNIX)
        try:
            probe.connect(path)
        except OSError:
            os.unlink(path)                               # nobody listens: a leftover of a dead helper
        else:
            print("ERR\talready running", flush=True)
            return
        finally:
            probe.close()
    previous = os.umask(0o177)                            # the socket is created private (0600), never briefly open
    try:
        server = socket.socket(socket.AF_UNIX)
        server.bind(path)
    finally:
        os.umask(previous)
    server.listen(8)
    server.settimeout(0.5)
    stop = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.append(1))
    print("MODE\tsocket", flush=True)
    try:
        while not stop:
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                conn.settimeout(1.0)
                data = b""
                try:
                    while b"\n" not in data and len(data) <= MAX_LINE:
                        chunk = conn.recv(64)
                        if not chunk:
                            break
                        data += chunk
                except OSError:
                    continue                                  # a client that never finishes its line: dropped, nobody waits for it
                word = parse(data)
                try:
                    conn.sendall(b"ok\n" if word else b"no\n")
                except OSError:
                    pass
                if word:
                    try:
                        print(word, flush=True)
                    except BrokenPipeError:
                        break                                 # the parent is gone
    finally:
        server.close()
        if os.path.exists(path):
            os.unlink(path)


def main() -> None:
    if mode() == "socket":
        serve_socket()
        return
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
