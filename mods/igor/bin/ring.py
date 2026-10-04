"""ring.py — an old-fashioned telephone bell, synthesized locally with ffmpeg, played with aplay.

Writes the sound once to a temporary WAV, then plays it `--times` times. No network, standard library only.
"""
import argparse
import os
import subprocess
import tempfile

PATH = os.path.join(tempfile.gettempdir(), "igor-ring.wav")
# Two bell tones, amplitude-modulated at 25 Hz (the clapper hitting the gongs), one burst of 1.1 s, then 1.4 s of silence.
BELL = ("aevalsrc='(0.35*sin(2*PI*1400*t)+0.25*sin(2*PI*1750*t))*(0.5+0.5*sin(2*PI*25*t))*lt(mod(t,2.5),1.1)':d=2.5:s=22050")


def make() -> None:
    if os.path.exists(PATH):
        return
    tmp = PATH + ".part"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", BELL, "-f", "wav", tmp], check=True, timeout=30)
    os.replace(tmp, PATH)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--times", type=int, default=2)
    ap.add_argument("--device", default="default")
    a = ap.parse_args()
    try:
        make()
    except (OSError, subprocess.SubprocessError):
        print("ERR\tcould not make the ring tone (ffmpeg needed)", flush=True)
        return
    for _ in range(max(1, min(a.times, 6))):
        subprocess.run(["aplay", "-q", "-D", a.device, PATH], check=False)


if __name__ == "__main__":
    main()
