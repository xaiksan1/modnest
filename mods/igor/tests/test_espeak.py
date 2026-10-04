import ctypes.util, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))


@unittest.skipUnless(ctypes.util.find_library("espeak-ng"), "libespeak-ng is not installed")
class Machine(unittest.TestCase):
    def test_renders_audio_in_english_and_french(self):
        import espeak_say
        for voice, phrase in (("en-us+klatt4", "Hello Michael."), ("fr+klatt", "Bonjour Michael.")):
            pcm, rate = espeak_say.synth(phrase, voice, 140, 35, 15, 2)
            self.assertGreater(len(pcm), rate)          # more than half a second of 16-bit audio

    def test_unknown_voice_is_refused(self):
        import espeak_say
        with self.assertRaises(RuntimeError):
            espeak_say.synth("x", "no-such-voice", 140, 35, 15, 2)


if __name__ == "__main__":
    unittest.main()
