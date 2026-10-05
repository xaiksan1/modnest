import io, os, stat, sys, tempfile, types, unittest
from contextlib import redirect_stdout
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
import speak


class Chunk:
    def __init__(self, data, rate=22050):
        self.audio_int16_bytes, self.sample_rate = data, rate


class FakeVoice:
    """Stands in for piper.PiperVoice: each sentence becomes two chunks of recognisable bytes."""
    seen = []

    @classmethod
    def load(cls, path):
        cls.loaded = path
        return cls()

    def synthesize(self, text):
        FakeVoice.seen.append(text)
        tag = text[:1].encode()
        yield Chunk(tag * 4)
        yield Chunk(tag * 2)


def run_piper(text, model="/fake/model.onnx", exists=True, has_piper=True):
    FakeVoice.seen = []
    with tempfile.TemporaryDirectory() as d:
        out, count = os.path.join(d, "audio.raw"), os.path.join(d, "calls")
        fake = os.path.join(d, "aplay")
        with open(fake, "w") as f:
            f.write(f"#!/bin/sh\necho x >> {count}\necho \"$@\" > {d}/args\ncat >> {out}\n")
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
        old_path, old_mod, old_exists = os.environ["PATH"], sys.modules.get("piper"), os.path.exists
        os.environ["PATH"] = d + ":" + old_path
        if has_piper:
            sys.modules["piper"] = types.SimpleNamespace(PiperVoice=FakeVoice)
        else:
            sys.modules["piper"] = None            # makes `import piper` raise ImportError
        os.path.exists = lambda p: True if p == model and exists else old_exists(p)
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                speak.speak_piper(text, SimpleNamespace(piper_model=model, device="default", speed=1.0))
        finally:
            os.environ["PATH"], os.path.exists = old_path, old_exists
            if old_mod is None:
                sys.modules.pop("piper", None)
            else:
                sys.modules["piper"] = old_mod
        audio = open(out, "rb").read() if os.path.exists(out) else b""
        calls = len(open(count).read().split()) if os.path.exists(count) else 0
        args = open(os.path.join(d, "args")).read() if os.path.exists(os.path.join(d, "args")) else ""
    return buf.getvalue(), audio, calls, args


class Sentences(unittest.TestCase):
    def test_splits_after_sentence_ends(self):
        self.assertEqual(speak.sentences("Bonjour. Ça va ? Oui ! Très bien…"), ["Bonjour.", "Ça va ?", "Oui !", "Très bien…"])

    def test_a_long_run_without_punctuation_is_cut_at_a_space(self):
        parts = speak.sentences(("mot " * 200).strip(), limit=100)
        self.assertTrue(all(len(p) <= 100 for p in parts) and " ".join(parts) == ("mot " * 200).strip())

    def test_empty_gives_nothing(self):
        self.assertEqual(speak.sentences("   "), [])


class SpeakPiper(unittest.TestCase):
    def test_every_sentence_is_spoken_in_order_through_ONE_player(self):
        out, audio, calls, args = run_piper("Alpha. Bravo. Charlie.")
        self.assertEqual(out, "")
        self.assertEqual(FakeVoice.seen, ["Alpha.", "Bravo.", "Charlie."])
        self.assertEqual(audio, b"AAAAAA" + b"BBBBBB" + b"CCCCCC")      # no gap, no reordering
        self.assertEqual(calls, 1)                                       # one continuous playback, never cut between sentences
        self.assertIn("-t raw", args)
        self.assertIn("-r 22050", args)

    def test_missing_model_file_reports_an_error_and_plays_nothing(self):
        out, audio, calls, _ = run_piper("Alpha.", exists=False)
        self.assertTrue(out.startswith("ERR\t") and "model" in out.lower())
        self.assertEqual((audio, calls), (b"", 0))

    def test_missing_piper_package_says_how_to_install_it(self):
        out, audio, calls, _ = run_piper("Alpha.", has_piper=False)
        self.assertTrue(out.startswith("ERR\t") and "piper" in out.lower())
        self.assertEqual((audio, calls), (b"", 0))

    def test_no_model_configured_is_an_error_not_a_crash(self):
        out, _, calls, _ = run_piper("Alpha.", model="")
        self.assertTrue(out.startswith("ERR\t") and calls == 0)


if __name__ == "__main__":
    unittest.main()
