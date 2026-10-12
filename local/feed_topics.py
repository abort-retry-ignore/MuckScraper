"""Map this install's RSS feeds onto reader topics.

The upstream classifier is US-centric and slow on a small local model, so
ingestion also tags stories from the feed they came in on. That is what makes
the New Zealand and Sci/Tech sidebar filters reliable.
"""

from __future__ import annotations

FEED_TOPICS = {
    # New Zealand headlines
    "https://www.rnz.co.nz/rss/national.xml": "New Zealand",
    "https://www.rnz.co.nz/rss/top.xml": "New Zealand",
    "https://www.rnz.co.nz/rss/political.xml": "New Zealand",
    "https://www.rnz.co.nz/rss/business.xml": "New Zealand",
    "https://www.rnz.co.nz/rss/teao.xml": "New Zealand",
    "https://www.stuff.co.nz/rss/national": "New Zealand",
    "https://www.nzherald.co.nz/arc/outboundfeeds/rss/section/nz/?outputType=xml": "New Zealand",
    "https://www.nzherald.co.nz/arc/outboundfeeds/rss/section/kahu/?outputType=xml": "New Zealand",
    "https://www.1news.co.nz/arc/outboundfeeds/rss/?outputType=xml": "New Zealand",
    "https://www.newsroom.co.nz/feed/": "New Zealand",
    "https://www.newstalkzb.co.nz/news/rss": "New Zealand",
    "https://www.interest.co.nz/rss": "New Zealand",
    "https://www.theguardian.com/world/newzealand/rss": "New Zealand",
    "https://www.waateanews.com/rss": "New Zealand",
    # Science and technology
    "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml": "Sci/Tech",
    "https://feeds.bbci.co.uk/news/technology/rss.xml": "Sci/Tech",
    "https://www.science.org/rss/news_current.xml": "Sci/Tech",
    "http://feed-proxy:8080/lifespan.xml": "Longevity",
    "https://theconversation.com/nz/health/articles.atom": "Health",
    "http://feed-proxy:8080/reuters.xml": "Sci/Tech",
    "http://feed-proxy:8080/cnn.xml": "Sci/Tech",
}

FEED_LABELS = {
    "https://www.rnz.co.nz/rss/national.xml": "RNZ New Zealand",
    "https://www.rnz.co.nz/rss/top.xml": "RNZ Top Stories",
    "https://www.rnz.co.nz/rss/political.xml": "RNZ Politics",
    "https://www.rnz.co.nz/rss/business.xml": "RNZ Business",
    "https://www.rnz.co.nz/rss/teao.xml": "RNZ Te Ao Maori",
    "https://www.stuff.co.nz/rss/national": "Stuff NZ News",
    "https://www.nzherald.co.nz/arc/outboundfeeds/rss/section/nz/?outputType=xml": "NZ Herald New Zealand",
    "https://www.nzherald.co.nz/arc/outboundfeeds/rss/section/kahu/?outputType=xml": "NZ Herald Kahu",
    "https://www.1news.co.nz/arc/outboundfeeds/rss/?outputType=xml": "1News",
    "https://www.newsroom.co.nz/feed/": "Newsroom",
    "https://www.newstalkzb.co.nz/news/rss": "Newstalk ZB",
    "https://www.interest.co.nz/rss": "Interest.co.nz",
    "https://www.theguardian.com/world/newzealand/rss": "Guardian New Zealand",
    "https://www.waateanews.com/rss": "Waatea News",
    "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml": "BBC Science",
    "https://feeds.bbci.co.uk/news/technology/rss.xml": "BBC Technology",
    "https://www.science.org/rss/news_current.xml": "Science (AAAS) News",
    "http://feed-proxy:8080/lifespan.xml": "Lifespan.io",
    "https://theconversation.com/nz/articles.atom": "The Conversation NZ",
    "https://theconversation.com/nz/health/articles.atom": "The Conversation NZ Health",
    "http://feed-proxy:8080/reuters.xml": "Reuters Science and Technology",
    "http://feed-proxy:8080/cnn.xml": "CNN Science and Technology",
}


TOPIC_SORT = {"New Zealand": 0, "Sci/Tech": 1, "Health": 2, "Longevity": 3}


def topic_for_feed(url: str) -> str | None:
    return FEED_TOPICS.get(url)


def apply_feed_topic(feed_url: str, articles: list[dict]) -> None:
    """Attach the feed's topic to stories just stored from that feed."""
    topic_name = topic_for_feed(feed_url)
    if not topic_name or not articles:
        return

    from aggregator import db
    from aggregator.models import Article, Topic
    from news_fetcher.fetch_and_store_articles.ingestion import normalize_url

    topic = Topic.query.filter_by(name=topic_name).first()
    if topic is None:
        topic = Topic(name=topic_name, is_active=True, sort_order=TOPIC_SORT.get(topic_name, 10))
        db.session.add(topic)
        db.session.flush()

    changed = False
    for article in articles:
        url = normalize_url(article.get("url") or "")
        if not url:
            continue
        row = Article.query.filter_by(url=url).first()
        if row is None or row.story is None:
            continue
        if topic not in row.story.topics:
            row.story.topics.append(topic)
            changed = True
    if changed:
        db.session.commit()
