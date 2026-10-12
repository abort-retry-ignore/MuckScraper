"""Install-wide reader preferences: landing page and list density."""

from flask import flash, redirect, render_template, request, url_for

from aggregator.models import ROLE_ADMIN, Topic
from aggregator.permissions import role_required
from aggregator.reader_prefs import (
    DISPLAY_COMPACT,
    DISPLAY_COMFORTABLE,
    LANDING_CHOICES,
    LANDING_TOPIC,
    RANGES,
    get_reader_prefs,
    save_reader_prefs,
)

from . import admin


@admin.route("/preferences", methods=["GET", "POST"])
@role_required(ROLE_ADMIN)
def preferences_page():
    topics = Topic.query.filter_by(is_active=True).order_by(Topic.sort_order.asc().nullslast(), Topic.name.asc()).all()
    if request.method == "POST":
        landing = request.form.get("landing", "")
        topic = request.form.get("topic", "").strip()
        time_range = request.form.get("time_range", "7d")
        display = DISPLAY_COMPACT if request.form.get("compact") == "on" else DISPLAY_COMFORTABLE
        valid_landings = {choice for choice, _label in LANDING_CHOICES}
        valid_ranges = {choice for choice, _label in RANGES}
        topic_names = {item.name for item in topics}
        if landing not in valid_landings or time_range not in valid_ranges:
            flash("That preference was not recognised.", "error")
        elif landing == LANDING_TOPIC and topic not in topic_names:
            flash("Choose a topic for the landing page.", "error")
        else:
            save_reader_prefs(landing, topic, time_range, display)
            flash("Reader preferences saved.", "success")
        return redirect(url_for("admin.preferences_page"))

    return render_template(
        "preferences.html",
        prefs=get_reader_prefs(),
        topics=topics,
        landing_choices=LANDING_CHOICES,
        ranges=RANGES,
        landing_topic=LANDING_TOPIC,
    )
