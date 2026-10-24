import unittest

from dota_analysis.classify import classify


class TestClassifier(unittest.TestCase):
    def test_english_complaint(self):
        c = classify("", "My behavior score dropped for no reason, this system is broken and unfair")
        self.assertTrue(c.relevant)
        self.assertEqual(c.stance, "complaint")

    def test_russian_complaint(self):
        c = classify("", "Почему упал рейтинг поведения? Кинули репорты ни за что")
        self.assertTrue(c.relevant)
        self.assertEqual(c.stance, "complaint")
        self.assertEqual(c.theme, "behavior_score")

    def test_question(self):
        c = classify("", "How does the behavior score work?")
        self.assertTrue(c.relevant)
        self.assertEqual(c.stance, "question")

    def test_positive(self):
        c = classify("", "Behavior score system works well, fair and deserved")
        self.assertEqual(c.stance, "positive")

    def test_off_topic(self):
        c = classify("", "I bought a battle pass yesterday and the new arcana is nice")
        self.assertFalse(c.relevant)
        self.assertEqual(c.stance, "off_topic")

    def test_theme_reports(self):
        c = classify("", "got banned for 6 months after false reports, valve support is useless")
        self.assertEqual(c.theme, "bans")
        self.assertEqual(c.stance, "complaint")

    def test_low_priority_theme(self):
        c = classify("", "Stuck in low priority for 5 games because of false reports")
        self.assertIn(c.theme, ("low_priority", "false_reports"))

    def test_body_question_without_title(self):
        c = classify("", "Кто знает, как поднять рейтинг поведения?")
        self.assertEqual(c.stance, "question")


if __name__ == "__main__":
    unittest.main()
