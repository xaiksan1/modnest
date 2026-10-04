"""speak.py — IGOR's voice: Cartesia text-to-speech -> ffmpeg robot effect -> aplay.

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

VOICE = "87286a8d-7ea7-4235-a41a-dd9fa6630feb"     # Cartesia "Henry", a flat male voice: the base of IGOR (used when --voice is not given)
MODEL, VERSION = "sonic-3", "2025-04-16"

# IGOR's voice: ffmpeg effects over the synthesized speech.
# robot = phase zeroed in the spectrum (a constant ~125 Hz buzz, the classic 1990s computer voice) + digital grit + metallic echo.
# soft  = no buzz, just grit and echo.
STYLES = {
    "robot": "aresample=16000,afftfilt=real='hypot(re,im)*sin(0)':imag='hypot(re,im)*cos(0)':win_size=128:overlap=0.75,"
             "acrusher=bits=11:mode=lin:aa=1:mix=0.35,aecho=0.8:0.85:7:0.35,volume=2.2",
    "soft": "aresample=16000,acrusher=bits=9:mode=lin:aa=1:mix=0.5,aecho=0.8:0.8:12:0.3,volume=1.4",
}


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
    ap.add_argument("--style", default="robot", choices=["robot", "soft", "plain"])
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
    played = f.name
    paths = [f.name]
    try:
        if a.style != "plain":
            played = f.name + ".igor.wav"
            paths.append(played)
            try:
                done = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f.name, "-af", STYLES[a.style], "-ar", "24000", played],
                                      capture_output=True, timeout=30)
                if done.returncode != 0:
                    played = f.name
                    print("ERR\tffmpeg failed, plain voice used", flush=True)
            except (OSError, subprocess.TimeoutExpired):
                played = f.name
                print("ERR\tffmpeg not found, plain voice used", flush=True)
        subprocess.run(["aplay", "-q", "-D", a.device, played], check=False)
    finally:
        for path in paths:
            try:
                os.unlink(path)
            except OSError:
                pass


if __name__ == "__main__":
    main()
