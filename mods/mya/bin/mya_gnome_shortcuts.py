#!/usr/bin/env python3
"""mya_gnome_shortcuts.py install|remove|status — the three MYA hotkeys, as ordinary GNOME keyboard shortcuts.

Under Wayland no program may watch the keyboard, so MYA cannot read "Right Ctrl" itself. GNOME can, though: it detects its own
shortcuts and runs a command. These three shortcuts run `mya-key toggle|translate|lock`, which drops one word into MYA's
private socket (see hotkey.py). Nothing here reads a key.

    install [--toggle ACCEL] [--translate ACCEL] [--lock ACCEL] [--dry-run]
    remove      take away only the three entries this tool created
    status      show them

It only ever touches its own three entries (mya-toggle, mya-translate, mya-lock under GNOME's custom keybindings), never
replaces an existing shortcut (a combination already in use is skipped and reported), and refuses anything that is not a plain
GTK accelerator such as <Primary><Alt>m. Exit codes: 0 done, 2 bad usage, 3 some combination was already taken, 4 no gsettings.
"""
import argparse
import ast
import os
import re
import shlex
import subprocess
import sys

MEDIA = "org.gnome.settings-daemon.plugins.media-keys"
LIST_KEY = "custom-keybindings"
ENTRY_SCHEMA = MEDIA + ".custom-keybinding"
BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
MYA_KEY = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mya-key"))

# word, slug, name, default key combination (Ctrl+Alt+M: M for MYA; the two others stay in the same family)
ACTIONS = (
    ("toggle", "mya-toggle", "MYA dictate", "<Primary><Alt>m"),
    ("translate", "mya-translate", "MYA translate", "<Primary><Alt><Shift>m"),
    ("lock", "mya-lock", "MYA hotkey on/off", "<Primary><Alt>k"),
)
ACCEL = re.compile(r"(?:<[A-Za-z]{3,10}>)*[A-Za-z0-9_]{1,24}")
ALIASES = {"control": "primary", "ctrl": "primary", "primary": "primary"}


class Fail(Exception):
    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code


def normalise(accel: str) -> tuple[frozenset, str]:
    """<Alt><Primary>T, <Control><Alt>t, <Ctrl><Alt>t are the same combination."""
    mods = [m.lower() for m in re.findall(r"<([A-Za-z]+)>", accel)]
    key = re.sub(r"<[A-Za-z]+>", "", accel).lower()
    return frozenset(ALIASES.get(m, m) for m in mods), key


def gvariant_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def gvariant_list(values) -> str:
    return "[" + ", ".join(gvariant_string(v) for v in values) + "]"


def gsettings(*args: str) -> str:
    try:
        done = subprocess.run(["gsettings", *args], capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise Fail("gsettings not found (this tool is for GNOME)", 4)
    except subprocess.TimeoutExpired:
        raise Fail("gsettings did not answer", 4)
    if done.returncode != 0:
        raise Fail(f"gsettings {' '.join(args[:3])} failed: {done.stderr.strip()[:200]}", 4)
    return done.stdout


def parse_gvariant(text: str):
    text = text.strip()
    return ast.literal_eval(text[3:].strip() if text.startswith("@as") else text)


def read_list() -> list:
    return list(parse_gvariant(gsettings("get", MEDIA, LIST_KEY)))


def read_entry(path: str, key: str) -> str:
    return parse_gvariant(gsettings("get", f"{ENTRY_SCHEMA}:{path}", key))


def ours() -> dict:
    return {slug: BASE + slug + "/" for _, slug, _, _ in ACTIONS}


def conflicts(wanted: dict) -> dict:
    """word -> who already uses that combination (in a GNOME setting, or in somebody else's custom shortcut)."""
    taken = {normalise(a): word for word, a in wanted.items()}
    found = {}
    own_paths = set(ours().values())
    for line in gsettings("list-recursively").splitlines():
        parts = line.split(" ", 2)
        if len(parts) < 3 or not parts[2].lstrip().startswith(("[", "@as [")):
            continue                                              # only lists of strings can be keyboard shortcuts
        try:
            values = parse_gvariant(parts[2])
        except (ValueError, SyntaxError):
            continue
        for value in values:
            if isinstance(value, str) and ACCEL.fullmatch(value) and normalise(value) in taken:
                found.setdefault(taken[normalise(value)], f"{parts[0]} {parts[1]}")
    for path in read_list():
        if path in own_paths:
            continue
        binding = read_entry(path, "binding")
        if binding and ACCEL.fullmatch(binding) and normalise(binding) in taken:
            found.setdefault(taken[normalise(binding)], f"your shortcut \"{read_entry(path, 'name')}\"")
    return found


def command_for(word: str) -> str:
    return f"{shlex.quote(MYA_KEY)} {word}"


def install(args) -> int:
    wanted = {}
    for word, _, _, default in ACTIONS:
        accel = getattr(args, word)
        if accel is None:                                    # absent: the default ; present but empty: refused below
            accel = default
        if not ACCEL.fullmatch(accel):
            raise Fail(f"not a key combination: {accel!r} (expected something like <Primary><Alt>m)", 2)
        wanted[word] = accel
    if len({normalise(a) for a in wanted.values()}) != len(wanted):
        raise Fail("two actions were given the same key combination", 2)
    if not os.access(MYA_KEY, os.X_OK):
        raise Fail(f"{MYA_KEY} is missing or not executable", 4)

    clashes = conflicts(wanted)
    current = read_list()
    plan = {}
    for word, slug, name, _ in ACTIONS:
        if word in clashes:
            print(f"SKIPPED {word}: {wanted[word]} is already used by {clashes[word]}")
            continue
        plan[word] = (ours()[slug], name, command_for(word), wanted[word])

    changed = False
    for word, (path, name, command, binding) in plan.items():
        have = (path in current and read_entry(path, "name") == name and read_entry(path, "command") == command
                and read_entry(path, "binding") == binding)
        if have:
            print(f"already installed: {word} = {binding}")
            continue
        changed = True
        print(f"{'would install' if args.dry_run else 'installed'}: {word} = {binding}  ->  {command}")
    if changed and not args.dry_run:
        wanted_list = current + [p for p, *_ in plan.values() if p not in current]
        if wanted_list != current:
            gsettings("set", MEDIA, LIST_KEY, gvariant_list(wanted_list))
        for path, name, command, binding in plan.values():
            for key, value in (("name", name), ("command", command), ("binding", binding)):
                if read_entry(path, key) != value:
                    gsettings("set", f"{ENTRY_SCHEMA}:{path}", key, gvariant_string(value))
    return 3 if clashes else 0


def remove(_args) -> int:
    current = read_list()
    mine = [p for p in current if p in ours().values()]
    if not mine:
        print("nothing to remove: MYA shortcuts are not installed")
        return 0
    gsettings("set", MEDIA, LIST_KEY, gvariant_list([p for p in current if p not in mine]))
    for path in mine:
        for key in ("name", "command", "binding"):
            gsettings("reset", f"{ENTRY_SCHEMA}:{path}", key)
        print(f"removed: {path.rstrip('/').rsplit('/', 1)[-1]}")
    return 0


def status(_args) -> int:
    current = read_list()
    shown = 0
    for word, slug, name, _ in ACTIONS:
        path = ours()[slug]
        if path in current:
            print(f"{word}: {read_entry(path, 'binding')}  ->  {read_entry(path, 'command')}")
            shown += 1
    if not shown:
        print("not installed")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="MYA hotkeys as GNOME keyboard shortcuts (Wayland-safe: no key is ever read)")
    sub = p.add_subparsers(dest="command", required=True)
    i = sub.add_parser("install", help="add the three shortcuts")
    for word, _, _, default in ACTIONS:
        i.add_argument(f"--{word}", metavar="ACCEL", help=f"key combination for {word} (default {default})")
    i.add_argument("--dry-run", action="store_true", help="show what would be done, change nothing")
    sub.add_parser("remove", help="remove the three shortcuts, and only them")
    sub.add_parser("status", help="show the installed shortcuts")
    args = p.parse_args(argv)
    try:
        return {"install": install, "remove": remove, "status": status}[args.command](args)
    except Fail as e:
        print(f"mya_gnome_shortcuts: {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
