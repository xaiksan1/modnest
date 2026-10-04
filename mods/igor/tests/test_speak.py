import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
from speak import build_filter


class BuildFilter(unittest.TestCase):
    def test_slowing_down_comes_before_the_robot_effect(self):
        chain = build_filter("robot", 0.85)
        self.assertTrue(chain.startswith("atempo=0.850,"))
        self.assertIn("afftfilt", chain)

    def test_normal_speed_adds_no_tempo(self):
        self.assertNotIn("atempo", build_filter("robot", 1.0))

    def test_plain_voice_at_normal_speed_needs_no_ffmpeg(self):
        self.assertEqual(build_filter("plain", 1.0), "")

    def test_plain_voice_can_still_be_slowed(self):
        self.assertEqual(build_filter("plain", 0.8), "atempo=0.800")

    def test_speed_is_kept_in_the_range_ffmpeg_accepts(self):
        self.assertIn("atempo=0.500", build_filter("soft", 0.1))
        self.assertIn("atempo=2.000", build_filter("soft", 9))


if __name__ == "__main__":
    unittest.main()
