import re

import pytest

from apps.kit.views import LAYOUTS, MOCKUPS, icon_names


@pytest.fixture
def kit_on(settings):
    settings.KIT_ENABLED = True


@pytest.mark.parametrize("slug", list(MOCKUPS))
def test_mockup_renders_with_one_h1(client, kit_on, vite_build, slug):
    response = client.get(f"/_kit/mockups/{slug}/")
    body = response.content.decode()
    assert response.status_code == 200
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    assert body.count("<h1") == 1
    assert body.count('<main id="main"') == 1


def test_unknown_mockup_is_404(client, kit_on, vite_build):
    assert client.get("/_kit/mockups/nope/").status_code == 404


def test_mockup_index_links_every_mockup(client, kit_on, vite_build):
    body = client.get("/_kit/mockups/").content.decode()
    for slug in MOCKUPS:
        assert f'href="/_kit/mockups/{slug}/"' in body


def test_kit_pages_only_use_icons_in_the_sprite(client, kit_on, vite_build):
    urls = ["/_kit/", "/_kit/mockups/"]
    urls += [f"/_kit/layouts/{name}/" for name in LAYOUTS]
    urls += [f"/_kit/mockups/{slug}/" for slug in MOCKUPS]
    known = set(icon_names())
    for url in urls:
        used = set(re.findall(r'icons\.svg#([a-z0-9-]+)"', client.get(url).content.decode()))
        assert used <= known, (url, used - known)


def test_review_mockup_acts_only_on_waiting_documents(client, kit_on, vite_build):
    body = client.get("/_kit/mockups/application-review/").content.decode()
    assert "Application APP-2026-0147 to LANI" in body
    assert "Not met: holds TCU CEAA" in body
    hidden = '<span class="visually-hidden"> Certificate of enrollment</span>'
    assert f"Approve{hidden}" in body
    assert f"Decline{hidden}" in body
    assert "Decline</button>" not in body
    assert body.count('class="btn btn--primary">Approve') == 1
    assert body.count('class="btn btn--danger">Decline') == 1


@pytest.fixture
def office(client, kit_on, vite_build):
    return client.get("/_kit/mockups/office-dashboard/").content.decode()


def test_office_overview_has_no_subtitle(office):
    assert "page-header__meta" not in office
    assert "Good morning, Jessica" in office


def test_office_figures_are_label_and_value_only(office):
    figures = office.split('<div class="figures">')[1].split('<div class="split')[0]
    assert figures.count('class="figure__label"') == 4
    assert figures.count('class="figure__value') == 4
    assert "figure__hint" not in figures and "<svg" not in figures
    for text in ("Scholars", "Applications", "Waiting over 7 days", "Reports to review"):
        assert f">{text}</p>" in figures


def test_attention_rows_are_links_with_severity(office):
    rows = re.findall(r'<a class="row-link".*?</a>', office, re.S)
    assert len(rows) == 3
    assert all("#arrow-right" in row for row in rows)
    assert "status--danger" in rows[1] and "window closes 15 November" in rows[1]
    assert "status--warning" in rows[0] and "status--warning" in rows[2]


def test_activity_has_no_dots(office):
    activity = office.split('id="activity-title"')[1].split("</section>")[0]
    assert "timeline__dot" not in activity
    assert "<svg" not in activity


def test_chart_has_a_table_fallback(office):
    assert '<ul class="bar-chart" aria-hidden="true"' in office
    details = re.search(r'<details class="chart-table".*?</details>', office, re.S)
    assert details and "<table" in details.group(0)
    for month in ("June", "July", "August", "September", "October"):
        assert f">{month}</th>" in details.group(0)


def test_chart_percent_steps_are_multiples_of_five(office):
    percents = [int(p) for p in re.findall(r'data-percent="(\d+)"', office)]
    assert len(percents) == 5
    assert all(p % 5 == 0 and 0 <= p <= 100 for p in percents)


@pytest.fixture
def review(client, kit_on, vite_build):
    return client.get("/_kit/mockups/application-review/").content.decode()


def test_review_has_a_checks_progress_and_no_step_pills(review):
    assert '<progress class="progress progress--secondary" max="8" value="5"' in review
    assert "5 of 8 passed (63%)" in review
    assert "steps" not in review
    assert "·" not in review.split('<main id="main"')[1]  # the tab title may keep its dot


def test_review_decision_is_a_radio_group(review):
    decision = review.split('id="decision-title"')[1].split("</section>")[0]
    assert "<fieldset" in decision
    assert decision.count('type="radio"') == 3
    for label in ("Approve", "Return to applicant", "Reject"):
        assert label in decision
    assert decision.count('type="radio" name="decision"') == 3
    assert decision.count(" checked") == 1
    assert 'class="btn btn--primary" type="submit">Submit decision' in decision
    assert "btn--danger" not in decision


def test_review_history_has_no_dots(review):
    history = review.split('id="history-title"')[1].split("</section>")[0]
    assert 'class="timeline"' in history
    assert "dot" not in history


@pytest.fixture
def student(client, kit_on, vite_build):
    return client.get("/_kit/mockups/student-dashboard/").content.decode()


def test_student_award_card_status_is_text(student):
    card = student.split('class="award-card"')[1].split("</section>")[0]
    assert '<span class="award-card__status">Active</span>' in card
    assert 'class="status' not in card


def test_student_next_release_is_large_yellow_text(student):
    assert 'class="award-card__release"' in student
    assert "Next release" in student


def test_student_dashboard_keeps_its_banner_and_notifications(student):
    assert "LANI returned your application" in student
    assert "Fix application</a>" in student
    assert 'class="progress progress--secondary" max="100" value="85"' in student
    assert "<meter" not in student
