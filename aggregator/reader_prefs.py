"""Install-wide reader preferences.

Stored in AppSetting so a signed-out visitor sees the same landing page and
list density as a signed-in one. Admins edit them at /admin/preferences.
Missing keys keep the upstream defaults: open on Headlines, comfortable cards.
"""

from flask import url_for

from aggregator import db
from aggregator.models import AppSetting, Topic

LANDING_HEADLINES = "headlines"
LANDING_ALL = "all"
LANDING_GROUPED = "grouped"
LANDING_TOPIC = "topic"

LANDING_CHOICES = (
    (LANDING_HEADLINES, "Headlines"),
    (LANDING_ALL, "All Stories"),
    (LANDING_GROUPED, "Grouped Stories"),
    (LANDING_TOPIC, "A topic"),
)

RANGES = (
    ("24h", "24 hours"),
    ("7d", "7 days"),
    ("30d", "30 days"),
    ("all", "All time"),
)

DISPLAY_COMFORTABLE = "comfortable"
DISPLAY_COMPACT = "compact"

KEY_LANDING = "reader_landing"
KEY_TOPIC = "reader_landing_topic"
KEY_RANGE = "reader_landing_range"
KEY_DISPLAY = "reader_display"

_KEYS = (KEY_LANDING, KEY_TOPIC, KEY_RANGE, KEY_DISPLAY)


class ReaderPrefs:
    def __init__(self, landing, topic, time_range, display):
        self.landing = landing
        self.topic = topic
        self.time_range = time_range
        self.display = display

    @property
    def compact(self):
        return self.display == DISPLAY_COMPACT


def _rows():
    return {
        row.key: (row.value or "")
        for row in AppSetting.query.filter(AppSetting.key.in_(_KEYS)).all()
    }


def get_reader_prefs():
    stored = _rows()
    landing = stored.get(KEY_LANDING) or LANDING_HEADLINES
    if landing not in {choice for choice, _label in LANDING_CHOICES}:
        landing = LANDING_HEADLINES
    time_range = stored.get(KEY_RANGE) or "7d"
    if time_range not in {choice for choice, _label in RANGES}:
        time_range = "7d"
    display = stored.get(KEY_DISPLAY) or DISPLAY_COMFORTABLE
    if display not in (DISPLAY_COMFORTABLE, DISPLAY_COMPACT):
        display = DISPLAY_COMFORTABLE
    return ReaderPrefs(landing, stored.get(KEY_TOPIC) or "", time_range, display)


def save_reader_prefs(landing, topic, time_range, display):
    values = {
        KEY_LANDING: landing,
        KEY_TOPIC: topic or "",
        KEY_RANGE: time_range,
        KEY_DISPLAY: display,
    }
    for key, value in values.items():
        row = AppSetting.query.get(key)
        if row is None:
            db.session.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    db.session.commit()


def landing_url():
    """Where / and a sign-in with no next page should go."""
    prefs = get_reader_prefs()
    if prefs.landing == LANDING_GROUPED:
        return url_for("admin.multi_article_stories", range=prefs.time_range)
    if prefs.landing == LANDING_ALL:
        return url_for("admin.list_articles", range=prefs.time_range)
    if prefs.landing == LANDING_TOPIC and prefs.topic:
        topic = Topic.query.filter_by(name=prefs.topic, is_active=True).first()
        if topic is not None:
            return url_for("admin.list_articles", topic=topic.name, range=prefs.time_range)
    return url_for("public.headlines_feed")


def list_page_size(kind):
    """How many stories a list page shows. Compact fits more on one screen."""
    compact = get_reader_prefs().compact
    if kind == "headlines":
        return 20 if compact else 10
    if kind == "grouped":
        return 80 if compact else 50
    return 40 if compact else 25
