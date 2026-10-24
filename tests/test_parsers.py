import unittest

from dota_analysis.collect import players, reddit_rss, steam

SEARCH_HTML = """
<html><body>
<div class="post_searchresult">
  <div class="forum_topic unread" data-gidforumtopic="111"
       data-tooltip-forum="&lt;div class=&quot;topic_hover_text&quot;&gt;why my behavior score is not updating&lt;/div&gt;
       &lt;div class=&quot;topic_hover_row&quot;&gt;Posted by: &lt;span class=&quot;topic_hover_data&quot;&gt;Nick&lt;/span&gt;, &lt;span&gt;8:31am&lt;/span&gt; &lt;/div&gt;">
    <a class="forum_topic_overlay" href="https://steamcommunity.com/app/570/discussions/0/111/"></a>
    <div class="forum_topic_name op_hidden">why my behavior score is not updating</div>
    <div class="forum_topic_reply_count">3 comments</div>
  </div>
  <div class="searchresult_author"><div class="searchresult_timestamp" data-timestamp="1792769519">x</div></div>
</div>
</body></html>
"""

THREAD_HTML = """
<html><body>
<div id="comment_111" class="commentthread_comment responsive_body_text">
  <div class="commentthread_comment_content">
    <a class="commentthread_author_link">Alice</a>
    <div class="commentthread_comment_timestamp" data-timestamp="1792765000">1h</div>
    <div id="comment_content_111" class="commentthread_comment_text">
      My behavior score dropped for no reason. The system is broken.
    </div>
  </div>
</div>
<div id="comment_222" class="commentthread_comment responsive_body_text">
  <div class="commentthread_comment_content">
    <a class="commentthread_author_link">Bob</a>
    <div class="commentthread_comment_timestamp" data-timestamp="1792766000">1h</div>
    <div id="comment_content_222" class="commentthread_comment_text">
      <blockquote class="bb_blockquote">quote</blockquote> Same here, false reports ruined it.
    </div>
  </div>
</div>
</body></html>
"""

CHARTS_HTML = """
<html><body><table class="common-table"><thead><tr><th>Month</th></tr></thead><tbody>
<tr class="odd"><td class="month-cell left italic">Last 30 Days</td><td>1</td><td>2</td><td>3%</td><td>4</td></tr>
<tr><td class="month-cell left">August 2026</td><td class="right num-f">617077.90</td>
<td class="right">71549.61</td><td class="right">&#43;13.12%</td><td class="right num">981123</td></tr>
<tr class="odd"><td class="month-cell left">July 2026</td><td class="right num-f">545528.29</td>
<td class="right">79526.32</td><td class="right">&#43;17.07%</td><td class="right num">860019</td></tr>
</tbody></table></body></html>
"""

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
 <entry>
  <author><name>/u/tester</name></author>
  <content type="html">&lt;p&gt;my behavior score dropped&lt;/p&gt;</content>
  <id>t3_abc</id>
  <link href="https://www.reddit.com/r/DotA2/comments/abc/x/"/>
  <updated>2026-10-20T10:00:00+00:00</updated>
  <title>Behavior score is broken</title>
 </entry>
</feed>
"""


class TestSteamParsers(unittest.TestCase):
    def test_search(self):
        rows = steam.parse_search_page(SEARCH_HTML, "behavior score")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["gid"], "111")
        self.assertEqual(r["author"], "Nick")
        self.assertEqual(r["created_utc"], 1792769519)
        self.assertIn("behavior score", r["excerpt"])
        self.assertTrue(r["url"].endswith("/111/"))

    def test_thread(self):
        docs = steam.parse_thread(THREAD_HTML, {"gid": "111", "title": "T", "url": "u",
                                                "author": "Alice", "created_utc": 1792765000,
                                                "num_comments": 1, "query": "q"})
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0]["source_type"], "thread_op")
        self.assertIn("broken", docs[0]["body"])
        self.assertEqual(docs[1]["author"], "Bob")
        self.assertNotIn("quote", docs[1]["body"])


class TestPlayers(unittest.TestCase):
    def test_steamcharts(self):
        rows = players.parse_steamcharts(CHARTS_HTML)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["month"], "2026-07")
        self.assertAlmostEqual(rows[1]["avg_players"], 617077.90)
        self.assertEqual(rows[1]["peak_players"], 981123)


class TestRedditRss(unittest.TestCase):
    def test_feed(self):
        rows = reddit_rss.parse_feed(RSS_XML)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "t3_abc")
        self.assertEqual(rows[0]["author"], "tester")
        self.assertIn("dropped", rows[0]["body"])
        self.assertGreater(rows[0]["created_utc"], 0)


if __name__ == "__main__":
    unittest.main()
