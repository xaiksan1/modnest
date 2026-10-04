import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
from mic_stt import fix_terms


class FixTerms(unittest.TestCase):
    def test_puts_mya_right(self):
        self.assertEqual(fix_terms("Là c'est mélangeant parce que je dis Mia", ["Mya"]), "Là c'est mélangeant parce que je dis Mya")
        self.assertEqual(fix_terms("Salut mia, ça va ?", ["Mya"]), "Salut Mya, ça va ?")

    def test_leaves_other_words_alone(self):
        self.assertEqual(fix_terms("la voiture est rapide", ["Mya"]), "la voiture est rapide")

    def test_does_nothing_without_the_term(self):
        self.assertEqual(fix_terms("Mia", []), "Mia")


if __name__ == "__main__":
    unittest.main()
