"""espeak_say.py — a real machine voice: eSpeak NG, a formant synthesizer (no human recording anywhere).

Loads the system's libespeak-ng through ctypes (nothing to install beyond the library,
which ships with speech-dispatcher), renders the text on standard input to a WAV file and
prints the file's path. Standard library only.
"""
import argparse
import ctypes
import os
import re
import sys
import tempfile
import wave

CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p)
RATE, VOLUME, PITCH, RANGE, WORDGAP = 1, 2, 3, 4, 7        # espeak_PARAMETER
SYNCHRONOUS, CHARS_UTF8 = 2, 1


_engine: tuple | None = None


def _start():
    """Initialise the library once per process: starting it again after espeak_Terminate can hang."""
    global _engine
    if _engine is None:
        lib = ctypes.CDLL("libespeak-ng.so.1")
        lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        sample_rate = lib.espeak_Initialize(SYNCHRONOUS, 0, None, 0)
        if sample_rate <= 0:
            raise RuntimeError("eSpeak NG could not start")
        _engine = (lib, sample_rate)
    return _engine


def synth(text: str, voice: str, rate: int, pitch: int, pitch_range: int, wordgap: int) -> tuple[bytes, int]:
    lib, sample_rate = _start()
    chunks: list[bytes] = []

    def on_audio(wav, count, _events):
        if wav and count > 0:
            chunks.append(ctypes.string_at(wav, count * 2))
        return 0

    callback = CALLBACK(on_audio)                       # kept alive for the whole synthesis
    lib.espeak_SetSynthCallback(callback)
    if lib.espeak_SetVoiceByName(voice.encode()) != 0:
        raise RuntimeError(f"unknown eSpeak voice: {voice}")
    for parameter, value in ((RATE, rate), (PITCH, pitch), (RANGE, pitch_range), (WORDGAP, wordgap)):
        lib.espeak_SetParameter(parameter, value, 0)
    data = text.encode("utf-8")
    lib.espeak_Synth(data, len(data) + 1, 0, 0, 0, CHARS_UTF8, None, None)
    lib.espeak_Synchronize()
    return b"".join(chunks), sample_rate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="fr+klatt")
    ap.add_argument("--rate", type=int, default=140, help="words per minute")
    ap.add_argument("--pitch", type=int, default=40, help="0-99, lower is deeper")
    ap.add_argument("--range", type=int, default=20, help="0-99, lower is more monotone")
    ap.add_argument("--wordgap", type=int, default=2, help="pause between words, in 10 ms units")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    text = re.sub(r"\s+", " ", sys.stdin.read()).strip()
    if not text:
        return
    pcm, rate = synth(text, a.voice, a.rate, a.pitch, a.range, a.wordgap)
    if not pcm:
        raise RuntimeError("eSpeak NG produced no audio")
    path = a.out or tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    with wave.open(path, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate), w.writeframes(pcm)
    print(path)


if __name__ == "__main__":
    main()
