import os, stat, subprocess, sys, tempfile, unittest

HOTKEY = os.path.join(os.path.dirname(__file__), "..", "bin", "hotkey.py")


def ev(kind, code):
    names = {2: "KeyPress", 3: "KeyRelease", 4: "ButtonPress", 5: "ButtonRelease"}
    return f"EVENT type {kind} ({names[kind]})\n    device: 3 (13)\n    detail: {code}\n    flags: \n"


def run(events, args=()):
    """Run hotkey.py against a fake `xinput` that replays the given events."""
    with tempfile.TemporaryDirectory() as d:
        fake = os.path.join(d, "xinput")
        with open(fake, "w") as f:
            f.write("#!/bin/sh\ncat <<'EOT'\n" + "".join(events) + "EOT\n")
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
        out = subprocess.run([sys.executable, HOTKEY, *map(str, args)], env={**os.environ, "PATH": d + ":" + os.environ["PATH"]},
                             capture_output=True, text=True, timeout=20).stdout
    return [w for w in out.split("\n") if w and not w.startswith("ERR")]


class Hotkey(unittest.TestCase):
    def test_a_quick_tap_toggles(self):
        self.assertEqual(run([ev(2, 105), ev(3, 105)]), ["TOGGLE"])

    def test_ctrl_plus_space_translates_and_does_not_toggle(self):
        self.assertEqual(run([ev(2, 105), ev(2, 65), ev(3, 65), ev(3, 105)]), ["TRANSLATE"])

    def test_ctrl_plus_right_shift_locks(self):
        self.assertEqual(run([ev(2, 105), ev(2, 62), ev(3, 62), ev(3, 105)]), ["LOCK"])

    def test_copy_paste_is_not_a_tap(self):
        self.assertEqual(run([ev(2, 105), ev(2, 54), ev(3, 54), ev(2, 55), ev(3, 55), ev(3, 105)]), [])

    def test_ctrl_click_is_not_a_tap(self):
        self.assertEqual(run([ev(2, 105), ev(4, 1), ev(5, 1), ev(3, 105)]), [])

    def test_ctrl_scroll_is_not_a_tap(self):
        self.assertEqual(run([ev(2, 105), ev(4, 4), ev(5, 4), ev(3, 105)]), [])

    def test_a_click_without_ctrl_is_ignored(self):
        self.assertEqual(run([ev(4, 1), ev(5, 1)]), [])

    def test_a_held_ctrl_is_not_a_tap(self):
        # a zero-length limit: any press is "too long"
        self.assertEqual(run([ev(2, 105), ev(3, 105)], args=(105, 65, 62, 0)), [])

    def test_auto_repeat_gives_one_tap(self):
        self.assertEqual(run([ev(2, 105), ev(2, 105), ev(3, 105)]), ["TOGGLE"])


if __name__ == "__main__":
    unittest.main()
