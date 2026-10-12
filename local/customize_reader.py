"""One-shot reader setup for this beelink install.

Disables the US-centric default wires, enables New Zealand headlines plus
science/tech from Reuters, CNN and BBC, and teaches the classifier those
topics. Insert-only upstream seeding will not undo enabled=False or an edited
prompt.
"""

from __future__ import annotations

from datetime import datetime

from aggregator import db
from aggregator.app import app
from aggregator.models import PromptTemplate, RssFeed, ScheduledFetch, Topic
from local.feed_topics import FEED_LABELS, FEED_TOPICS

NZ_RULES = """- New Zealand means news about New Zealand / Aotearoa: its government, politics, economy, courts, weather, sport, society, or events happening there. Prefer New Zealand over International News, US News, and US Politics. A New Zealand outlet covering a domestic story is New Zealand, not US News.
- Sci/Tech means science, research, space, climate science, technology, AI, chips, software, and cybersecurity. Reuters, CNN, BBC, Science (AAAS), and The Conversation science or technology stories belong here even when they mention a company or a country. Do not file them as US News or US Politics unless the story is primarily about US government action.
- Health means medicine, public health, disease, nutrition, mental health, and the health system. The Conversation NZ Health stories belong here.
- Longevity means ageing research, lifespan and healthspan, senescence, longevity biotech, and anti-ageing interventions. Lifespan.io and similar stories belong here, even when they are also Health or Sci/Tech.
- A story can be both New Zealand and Sci/Tech when it is a New Zealand science or technology story.
"""


def main() -> None:
    with app.app_context():
        wanted = set(FEED_TOPICS)
        disabled = 0
        for feed in RssFeed.query.all():
            if feed.url not in wanted and feed.enabled:
                feed.enabled = False
                disabled += 1

        added = 0
        now = datetime.utcnow()
        for url, topic in FEED_TOPICS.items():
            row = RssFeed.query.filter_by(url=url, bucket="general").first()
            if row is None:
                db.session.add(RssFeed(
                    url=url,
                    bucket="general",
                    label=FEED_LABELS.get(url),
                    enabled=True,
                    added_at=now,
                ))
                added += 1
            else:
                row.enabled = True
                row.label = FEED_LABELS.get(url) or row.label

        nz = Topic.query.filter_by(name="New Zealand").first()
        if nz is None:
            db.session.add(Topic(name="New Zealand", icon="NZ", sort_order=0, is_active=True))
        else:
            nz.sort_order = 0
            nz.icon = nz.icon or "NZ"
            nz.is_active = True

        sci = Topic.query.filter_by(name="Sci/Tech").first()
        if sci is not None:
            sci.sort_order = 1
            sci.is_active = True

        for name, sort_order in (("Health", 2), ("Longevity", 3)):
            topic = Topic.query.filter_by(name=name).first()
            if topic is None:
                db.session.add(Topic(name=name, is_active=True, sort_order=sort_order))
            else:
                topic.sort_order = sort_order
                topic.is_active = True

        fetches_off = 0
        for fetch in ScheduledFetch.query.filter_by(is_active=True).all():
            fetch.is_active = False
            fetches_off += 1

        prompt = PromptTemplate.query.filter_by(key="topic_classifier").first()
        prompt_updated = False
        if prompt and "New Zealand means" not in (prompt.current_text or ""):
            prompt.current_text = (prompt.current_text or "").replace("Rules:\n", "Rules:\n" + NZ_RULES, 1)
            prompt.updated_at = datetime.utcnow()
            prompt_updated = True

        db.session.commit()
        enabled = RssFeed.query.filter_by(bucket="general", enabled=True).count()
        print(
            f"customized: disabled_feeds={disabled} added_feeds={added} "
            f"enabled_general={enabled} scheduled_fetches_off={fetches_off} "
            f"prompt_updated={prompt_updated}"
        )


if __name__ == "__main__":
    main()
