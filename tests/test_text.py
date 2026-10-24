import unittest

from dota_analysis.text import (MinHash, clean_text, content_hash, detect_lang,
                                is_probable_spam, strip_html)


class TestText(unittest.TestCase):
    def test_strip_html(self):
        self.assertEqual(strip_html("<b>hello</b> <i>world</i>"), "hello world")

    def test_clean_urls(self):
        self.assertNotIn("http", clean_text("look https://example.com/a here"))

    def test_lang_ru(self):
        self.assertEqual(detect_lang("рейтинг поведения не работает"), "ru")

    def test_lang_en(self):
        self.assertEqual(detect_lang("behavior score is broken"), "en")

    def test_spam_short(self):
        self.assertTrue(is_probable_spam("ok"))

    def test_spam_ads(self):
        self.assertTrue(is_probable_spam("free skins cheap mmr boost your account now"))

    def test_not_spam(self):
        text = ("I lost behavior score after a game where nobody talked, "
                "the system seems broken and support ignores tickets")
        self.assertFalse(is_probable_spam(text))

    def test_content_hash_same(self):
        self.assertEqual(content_hash("Hello, World!"), content_hash("hello world"))

    def test_minhash_near_dup(self):
        mh = MinHash(perms=32, bands=8)
        a = "behavior score dropped for no reason after my last game and support ignores me"
        b = "behavior score dropped for no reason after my last game and support ignores us"
        c = "completely different topic about battle pass rewards and arcana items"
        sa, sb, sc = mh.signature(a), mh.signature(b), mh.signature(c)
        self.assertGreater(MinHash.jaccard(sa, sb), MinHash.jaccard(sa, sc))


if __name__ == "__main__":
    unittest.main()
