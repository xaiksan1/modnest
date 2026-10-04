"""mic_stt.py — one utterance: microphone -> silence -> Deepgram -> text.

Records with arecord (ALSA) until you stop talking (or the stop file appears),
sends the audio to Deepgram (REST) and prints ONE line: "TEXT<tab>sentence"
or "ERR<tab>reason".
The key is read from the environment (DEEPGRAM_API_KEY) or, optionally, from
an env file given with --env; it is never printed. Standard library only.
"""
import argparse
import array
import io
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import wave

RATE, CHUNK_MS = 16000, 100
CHUNK = RATE * 2 * CHUNK_MS // 1000          # octets (16 bits mono) par tranche


def out(kind: str, text: str = "") -> None:
    print(f"{kind}\t{text}", flush=True)


def load_key(env_path: str) -> str:
    key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if key:
        return key
    try:
        for line in open(env_path, encoding="utf-8"):
            m = re.match(r"\s*DEEPGRAM_API_KEY\s*=\s*(.*)", line)
            if m:
                return m.group(1).strip().strip("\"'")
    except OSError:
        pass
    return ""


def pick_device(wanted: str) -> str:
    if wanted != "auto":
        return wanted
    try:
        txt = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return "default"
    m = re.search(r"card (\d+): (\w*USB\w*) \[[^\]]*\], device (\d+)", txt)      # a USB microphone is preferred
    return f"plughw:{m.group(1)},{m.group(3)}" if m else "default"


def rms(buf: bytes) -> float:
    s = array.array("h")
    s.frombytes(buf[: len(buf) // 2 * 2])
    return math.sqrt(sum(x * x for x in s) / len(s)) if s else 0.0


def record(device: str, stop_file: str, max_s: float, wait_s: float, silence_s: float) -> bytes:
    p = subprocess.Popen(["arecord", "-q", "-D", device, "-f", "S16_LE", "-r", str(RATE), "-c", "1", "-t", "raw"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    pre, kept, started, quiet, t0 = [], [], False, 0, time.time()
    ambient = []
    try:
        while time.time() - t0 < max_s:
            buf = p.stdout.read(CHUNK)
            if not buf:
                break
            level = rms(buf)
            if len(ambient) < 4:                                   # 400 ms of background noise to calibrate
                ambient.append(level)
                pre.append(buf)
                continue
            thr = max(400.0, 3.0 * (sum(ambient) / len(ambient)))
            if not started:
                pre.append(buf)
                pre = pre[-4:]                                       # keep a little audio before the voice starts
                if level > thr:
                    started, kept, quiet = True, list(pre), 0
                elif time.time() - t0 > wait_s:
                    break
            else:
                kept.append(buf)
                quiet = quiet + 1 if level < thr else 0
                if quiet * CHUNK_MS / 1000 >= silence_s:
                    break
            if os.path.exists(stop_file):
                if not started:
                    kept = pre
                break
    finally:
        p.terminate()
        try:
            p.wait(timeout=2)
        except Exception:
            p.kill()
    return b"".join(kept) if started or kept else b""


# Words Deepgram tends to mishear, put right after transcription (only for the matching key term).
MISHEARD = {"igor": ["i car", "icar", "i-car", "ygor", "i gor", "igore"]}


def fix_terms(text: str, terms: list[str]) -> str:
    for term in terms:
        for wrong in MISHEARD.get(term.lower(), []):
            text = re.sub(rf"\b{re.escape(wrong)}\b", term, text, flags=re.I)
    return text


def transcribe(key: str, pcm: bytes, language: str, terms: list[str] | None = None, rate: int = RATE) -> str:
    terms = terms or []
    wav = io.BytesIO()
    with wave.open(wav, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate), w.writeframes(pcm)
    last = "unknown error"
    for model in ("nova-3", "nova-2"):
        boost = "".join(f"&keyterm={urllib.parse.quote(t)}" for t in terms) if model == "nova-3" else \
                "".join(f"&keywords={urllib.parse.quote(t)}:2" for t in terms)
        url = f"https://api.deepgram.com/v1/listen?model={model}&language={language}&smart_format=true{boost}"
        req = urllib.request.Request(url, data=wav.getvalue(), method="POST",
                                     headers={"Authorization": f"Token {key}", "Content-Type": "audio/wav"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.load(r)
            return fix_terms(d["results"]["channels"][0]["alternatives"][0]["transcript"].strip(), terms)
        except urllib.error.HTTPError as e:
            last = f"Deepgram HTTP {e.code}"
            if e.code in (401, 403):
                break                                                 # key refused: no point trying the other model
        except Exception as e:                                       # network, JSON...
            last = f"{type(e).__name__}"
    raise RuntimeError(last)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="auto")
    ap.add_argument("--env", default="")
    ap.add_argument("--stop-file", required=True)
    ap.add_argument("--language", default="fr")
    ap.add_argument("--keyterms", default="", help="comma-separated words Deepgram should favour (names, jargon)")
    ap.add_argument("--max-seconds", type=float, default=45)
    ap.add_argument("--wait-seconds", type=float, default=8)
    ap.add_argument("--silence-seconds", type=float, default=1.3)
    a = ap.parse_args()
    key = load_key(a.env)
    if not key:
        return out("ERR", "Deepgram API key not found")
    try:
        os.unlink(a.stop_file)
    except OSError:
        pass
    pcm = record(pick_device(a.device), a.stop_file, a.max_seconds, a.wait_seconds, a.silence_seconds)
    if len(pcm) < RATE * 2 // 2:                                      # less than half a second
        return out("ERR", "heard nothing")
    try:
        text = transcribe(key, pcm, a.language, [t.strip() for t in a.keyterms.split(",") if t.strip()])
    except Exception as e:
        return out("ERR", str(e))
    out("TEXT", text) if text else out("ERR", "no text recognised")


if __name__ == "__main__":
    main()
