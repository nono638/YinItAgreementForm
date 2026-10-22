"""Each firm of a trial marked alike wherever the window names it (firm_marks, gui.badges; the user, 2026-10-21):
as court exhibits, plaintiffs' firms 1, 2, 3, defense firms A, B, C, others 001; the same firm however its
attorneys are listed, and the same mark on every day of the trial. All names are made up."""
import pytest

from minute_filler.batch import Job, trial_marks
from minute_filler.firm_marks import DEFENSE, OTHER, PLAINTIFF, Mark, badge, firm_id, marks, side
from minute_filler.models import Attorney

from helpers import ROE, make_case


def att(name="", firm="", party=""):
    return Attorney(name=name, firm=firm, party=party, checked=True)


def test_the_side_of_a_party():
    assert side("Attorneys for Plaintiff") == side("Petitioners") == side("claimant") == PLAINTIFF
    assert side("Defendants") == side("Attorneys for Respondent") == DEFENSE
    assert side("Defendant/Third-Party Plaintiff") == DEFENSE  # (a defendant first)
    assert side("") == side("sender") == side("orderer (invoice)") == OTHER


def test_badges_run_as_exhibits_do():
    assert [badge(PLAINTIFF, n) for n in (0, 1, 9)] == ["1", "2", "10"]
    assert [badge(DEFENSE, n) for n in (0, 1, 25, 26, 27)] == ["A", "B", "Z", "AA", "AB"]
    assert [badge(OTHER, n) for n in (0, 1, 11)] == ["001", "002", "012"]


def test_a_firm_is_one_however_it_is_listed():
    assert firm_id(att("Dana Smith", "Smith Law, LLP")) == firm_id(att("", "smith law")) == "firm:smith law"
    assert firm_id(att("Pat Doe, Esq.", "Doe & Roe, P.C.")) == "firm:doe & roe"
    assert firm_id(att("Sam Poe")) == "name:sam poe" and firm_id(att()) == ""


def test_each_side_counts_its_own_firms_in_order():
    got = marks([att("Dana Smith", "Smith Law", "Plaintiff"), att("Alex B. Counsel", "Counsel & Counsel",
                                                                   "Defendants"),
                 att("Lee Jones", "Smith Law, LLP", "Plaintiff"),  # (Smith Law again: its mark)
                 att("Kim Park", "Park PLLC", "Defendant"), att("Sam Poe", "", "Plaintiffs"),
                 att("", "Court Watch Inc.", "sender"), att("Unrepresented", "", "Defendant")])
    assert got == {"firm:smith law": Mark("1", PLAINTIFF, 0), "firm:counsel & counsel": Mark("A", DEFENSE, 0),
                   "firm:park": Mark("B", DEFENSE, 1), "name:sam poe": Mark("2", PLAINTIFF, 1),
                   "firm:court watch": Mark("001", OTHER, 0)}


def day(date, attorneys, index="712345/2021"):
    job = Job()
    job.case = make_case({**ROE, "dates": date, "index_no": index}, attorneys)
    return job


def test_a_firm_keeps_its_mark_on_every_day_of_the_trial():
    """Day 2 lists Counsel & Counsel by its firm (two attorneys), day 1 by its attorney, and the two defense firms
    the other way round; the days given out of order: the earliest day's order counts. Another case's firms are
    left out."""
    d1 = day("6/3/2026", [att("Dana Smith", "Smith Law", "Plaintiff"),
                          att("Alex B. Counsel", "Counsel & Counsel", "Defendant"),
                          att("Kim Park", "Park PLLC", "Defendant")])
    d2 = day("6/4/2026", [att("Kim Park", "Park PLLC", "Defendant"),
                          att("Alex B. Counsel, Pat Doe", "Counsel & Counsel, LLP", "Defendant"),
                          att("Dana Smith", "Smith Law", "Plaintiff")])
    other = day("6/4/2026", [att("Lee Jones", "Jones LLP", "Defendant")], "799999/2022")
    for shown in (d1, d2):
        got = trial_marks(shown, [d2, other, d1])
        assert {k: m.badge for k, m in got.items()} == {
            d1.case.attorneys[0].key(): "1", d1.case.attorneys[1].key(): "A", d1.case.attorneys[2].key(): "B",
            d2.case.attorneys[0].key(): "B", d2.case.attorneys[1].key(): "A", d2.case.attorneys[2].key(): "1"}


def test_the_colours_are_the_sides_and_never_the_amber_of_a_field_to_check(qt):
    """Oranges for the plaintiffs, blues for the defense, the next firm of a side in another colour; none of them
    the amber the window marks a field to check with (the user, 2026-10-22: a pale orange shade read as one)."""
    from minute_filler.gui.badges import SHADES, badge_html, badge_icon, tag_color
    from minute_filler.gui.theme import DARK, LIGHT
    plaintiff, defense = Mark("1", PLAINTIFF, 0), Mark("A", DEFENSE, 0)
    assert tag_color(plaintiff).hue() in range(15, 45)  # (orange)
    assert tag_color(defense).hue() in range(190, 240)  # (blue)
    assert tag_color(Mark("1", PLAINTIFF, 0)) != tag_color(Mark("2", PLAINTIFF, 1))
    ambers = {LIGHT["review"].lower(), DARK["review"].lower(), "#b45309", "#f59e0b", "#fcd34d", "#fde68a"}
    assert not ambers & {c.lower() for row in SHADES.values() for c in row}
    assert not badge_icon(Mark("001", OTHER, 0)).isNull()
    assert "&nbsp;A&nbsp;" in badge_html(defense, "Counsel & Counsel") and "Counsel &amp; Counsel" in \
        badge_html(defense, "Counsel & Counsel")
    assert "background-color" not in badge_html(defense, "Counsel & Counsel").split("</span>", 1)[1]
    assert badge_html(None, "A & B") == "A &amp; B"


def test_the_window_marks_each_firm_in_its_tables(qt, tmp_path, monkeypatch, make_window):
    """The attorney table and Who ordered what: each firm's tag beside its name and a stripe of its colour at the
    name's left edge, no shade behind it; Who pays what: its tag and a stripe."""
    from PySide6.QtCore import Qt
    from minute_filler.gui.badges import STRIPE_ROLE, StripeDelegate
    from helpers import pat_settings
    from test_sweep_270 import one_day
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    s = pat_settings()
    s.use_ai = s.open_after = False
    s.output_dir, s.records_dir = str(tmp_path / "out"), str(tmp_path / "records")
    s.outputs = ["agreement", "invoice"]
    win = make_window(s)
    job = one_day(win, qt, tmp_path, [att("Dana Smith", "Smith Law", "Plaintiff"),
                                      att("Alex B. Counsel", "Counsel & Counsel", "Defendants")])
    win._show_attorneys()
    win._update_status()
    assert not win.att.item(0, 1).icon().isNull() and not win.att.item(1, 1).icon().isNull()
    stripes = [win.att.item(r, 1).data(STRIPE_ROLE) for r in (0, 1)]
    assert all(stripes) and stripes[0] != stripes[1]
    assert all(win.att.item(r, c).background().style() == Qt.NoBrush for r in (0, 1) for c in (1, 2))
    assert isinstance(win.att.itemDelegateForColumn(1), StripeDelegate)
    assert isinstance(win.orders.itemDelegateForColumn(1), StripeDelegate)
    names = {win.orders.item(r, 1).text(): win.orders.item(r, 1) for r in range(win.orders.rowCount())}
    assert not names["Dana Smith"].icon().isNull() and not names["Alex B. Counsel"].icon().isNull()
    assert names["Dana Smith"].data(STRIPE_ROLE) == stripes[0] and names["Dana Smith"].background().style() == Qt.NoBrush
    assert "&nbsp;1&nbsp;" in win.pays.text() and "&nbsp;A&nbsp;" in win.pays.text()
    assert f"bgcolor='{stripes[0]}'" in win.pays.text()
