import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
from mic_stt import fix_terms


class FixTerms(unittest.TestCase):
    def test_puts_igor_right(self):
        self.assertEqual(fix_terms("Là c'est mélangeant parce que je dis I car", ["Igor"]), "Là c'est mélangeant parce que je dis Igor")
        self.assertEqual(fix_terms("Salut icar, ça va ?", ["Igor"]), "Salut Igor, ça va ?")

    def test_leaves_other_words_alone(self):
        self.assertEqual(fix_terms("la voiture est rapide", ["Igor"]), "la voiture est rapide")

    def test_does_nothing_without_the_term(self):
        self.assertEqual(fix_terms("I car", []), "I car")


if __name__ == "__main__":
    unittest.main()
