"""speak.py — reads a text aloud: Cartesia text-to-speech -> aplay.

The text arrives on standard input. Markdown, code and URLs are stripped before
speaking. The key is read from CARTESIA_API_KEY (or an optional --env file) and
is never printed. Prints "ERR<tab>reason" on failure. Standard library only.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

VOICE = "f786b574-daa5-4673-aa0c-cbe3e8534c02"     # Cartesia library voice used when --voice is not given
MODEL, VERSION = "sonic-3", "2025-04-16"


def load_key(env_path: str) -> str:
    key = os.environ.get("CARTESIA_API_KEY", "").strip()
    if key:
        return key
    try:
        for line in open(env_path, encoding="utf-8"):
            m = re.match(r"\s*CARTESIA_API_KEY\s*=\s*(.*)", line)
            if m:
                return m.group(1).strip().strip("\"'")
    except OSError:
        pass
    return ""


def speakable(text: str) -> str:
    text = re.sub(r"```.*?```", " (a code block) ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"^\s{0,3}(#{1,6}|[-*+]|\d+[.)])\s+", "", text, flags=re.M)
    text = re.sub(r"[*_>|~]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="")
    ap.add_argument("--voice", default="")
    ap.add_argument("--language", default="fr")
    ap.add_argument("--device", default="default")
    a = ap.parse_args()
    text = speakable(sys.stdin.read())[:1500]
    if not text:
        return
    key = load_key(a.env)
    if not key:
        print("ERR\tCartesia API key not found", flush=True)
        return
    body = json.dumps({
        "model_id": MODEL, "transcript": text, "language": a.language,
        "voice": {"mode": "id", "id": a.voice or VOICE},
        "output_format": {"container": "wav", "encoding": "pcm_s16le", "sample_rate": 24000},
    }).encode()
    req = urllib.request.Request("https://api.cartesia.ai/tts/bytes", data=body, method="POST",
                                 headers={"X-API-Key": key, "Cartesia-Version": VERSION, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            wav = r.read()
    except urllib.error.HTTPError as e:
        print(f"ERR\tCartesia HTTP {e.code}", flush=True)
        return
    except Exception as e:
        print(f"ERR\t{e.__class__.__name__}", flush=True)
        return
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(wav)
    try:
        subprocess.run(["aplay", "-q", "-D", a.device, f.name], check=False)
    finally:
        os.unlink(f.name)


if __name__ == "__main__":
    main()
