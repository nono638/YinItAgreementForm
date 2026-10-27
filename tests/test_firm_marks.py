"""Each firm of a trial marked alike wherever the window names it (firm_marks, gui.badges; the user, 2026-10-21):
by its side and its place among that side's firms, shown as a colour only (2026-10-26: no number or letter); the
same firm however its attorneys are listed, and the same mark on every day of the trial; their colours (each its
own on a side, never the amber of a field to check), and the square and stripe the window's tables show. All names
are made up."""
import pytest

from minute_filler.batch import Job, trial_marks
from minute_filler.firm_marks import DEFENSE, OTHER, PLAINTIFF, Mark, firm_id, marks, side
from minute_filler.models import Attorney

from helpers import ROE, make_case


def att(name="", firm="", party=""):
    """An attorney row, ticked as ordering."""
    return Attorney(name=name, firm=firm, party=party, checked=True)


def test_the_side_of_a_party():
    """Plaintiffs, petitioners and claimants are one side, defendants and respondents the other, by the role
    named first ('Defendant/Third-Party Plaintiff' is the defense); anything else is OTHER."""
    assert side("Attorneys for Plaintiff") == side("Petitioners") == side("claimant") == PLAINTIFF
    assert side("Defendants") == side("Attorneys for Respondent") == DEFENSE
    assert side("Defendant/Third-Party Plaintiff") == side("Defendants/Counterclaimants") == DEFENSE  # (named first)
    assert side("Plaintiff/Counterclaim Defendant") == side("Plaintiffs-Counterclaim-Defendants") == PLAINTIFF
    assert side("") == side("sender") == side("orderer (invoice)") == OTHER


def test_a_firm_is_one_however_it_is_listed():
    """'Smith Law, LLP' and 'smith law' are one firm, whoever its attorney; an entry without a firm is its
    attorney's name, and one naming neither is no firm ("")."""
    assert firm_id(att("Dana Smith", "Smith Law, LLP")) == firm_id(att("", "smith law")) == "smith law"
    assert firm_id(att("Pat Doe, Esq.", "Doe & Roe, P.C.")) == "doe and roe"
    assert firm_id(att("Sam Poe")) == "sam poe" and firm_id(att()) == ""
    # as Attorney.key() reads a firm: '&' is 'and', a leading 'The' goes (and 'Attorneys at Law' at the end too)
    assert firm_id(att("", "Counsel & Counsel, LLP")) == firm_id(att("", "Counsel and Counsel"))
    assert firm_id(att("", "The Smith Law Firm")) == firm_id(att("", "Smith Law Firm, Attorneys at Law"))
    assert firm_id(att("", "Attorneys at Law")) == "attorneys at law"
    # endings of both kinds, one after the other
    assert firm_id(att("", "Smith Law, LLP, Attorneys at Law")) == firm_id(att("", "Smith Law")) == "smith law"
    assert firm_id(att("", "Counsel & Counsel, P.C., Attorneys at Law")) == "counsel and counsel"
    assert firm_id(att("Dana Smith, Esq.")) == firm_id(att("dana  smith esq")) == "dana smith"


def test_each_side_counts_its_own_firms_in_order():
    """Each side counts its firms in the order they come: Smith Law the plaintiffs' first (its second attorney too)
    and Sam Poe their second (no firm: by name); Counsel & Counsel the defense's first and Park PLLC its second;
    Court Watch Inc., the sender, the others' first. A placeholder row ("Unrepresented") gets no mark."""
    got = marks([att("Dana Smith", "Smith Law", "Plaintiff"), att("Alex B. Counsel", "Counsel & Counsel",
                                                                   "Defendants"),
                 att("Lee Jones", "Smith Law, LLP", "Plaintiff"),  # (Smith Law again: its mark)
                 att("Kim Park", "Park PLLC", "Defendant"), att("Sam Poe", "", "Plaintiffs"),
                 att("", "Court Watch Inc.", "sender"), att("Unrepresented", "", "Defendant")])
    assert got == {"smith law": Mark(PLAINTIFF, 0), "counsel and counsel": Mark(DEFENSE, 0),
                   "park": Mark(DEFENSE, 1), "sam poe": Mark(PLAINTIFF, 1), "court watch": Mark(OTHER, 0)}


def day(date, attorneys, index="712345/2021"):
    """A job of one day of Jane Roe's case (another case with another index) with these attorneys."""
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
        assert {k: (m.side, m.shade) for k, m in got.items()} == {
            d1.case.attorneys[0].key(): (PLAINTIFF, 0), d1.case.attorneys[1].key(): (DEFENSE, 0), d1.case.attorneys[2].key(): (DEFENSE, 1),
            d2.case.attorneys[0].key(): (DEFENSE, 1), d2.case.attorneys[1].key(): (DEFENSE, 0), d2.case.attorneys[2].key(): (PLAINTIFF, 0)}


def test_a_firm_written_two_ways_keeps_one_mark_on_every_day():
    """'Counsel & Counsel, LLP' on day 1 and 'Counsel and Counsel' on day 2 are one entry (Attorney.key()) and one
    firm: the plaintiffs' first on both days, Smith Law their second. A row of the same entry without its firm keeps the firm's mark."""
    d1 = day("6/3/2026", [att("Alex B. Counsel", "Counsel & Counsel, LLP", "Plaintiff"),
                          att("Dana Smith", "Smith Law", "Plaintiff")])
    d2 = day("6/4/2026", [att("Alex B. Counsel", "Counsel and Counsel", "Plaintiff"),
                          att("Dana Smith", "Smith Law", "Plaintiff"), att("Smith Law", "", "Plaintiff")])
    got = {k: (m.side, m.shade) for k, m in trial_marks(d2, [d1, d2]).items()}
    assert got == {"counsel and counsel": (PLAINTIFF, 0), "smith law": (PLAINTIFF, 1)}


def test_a_firm_named_in_the_name_column_takes_no_colour_of_its_own():
    """Day 1 Smith Law; day 2 a row naming 'Smith Law' with no firm (the same entry: Attorney.key()), then Counsel &
    Counsel: Counsel & Counsel is the plaintiffs' second (it was third, the row having taken a place of its own)."""
    d1 = day("6/3/2026", [att("Dana Smith", "Smith Law", "Plaintiff")])
    d2 = day("6/4/2026", [att("Smith Law", "", "Plaintiff"), att("Alex B. Counsel", "Counsel & Counsel", "Plaintiff")])
    got = {k: (m.side, m.shade) for k, m in trial_marks(d2, [d1, d2]).items()}
    assert got == {"smith law": (PLAINTIFF, 0), "counsel and counsel": (PLAINTIFF, 1)}


def test_the_colours_are_the_sides_and_never_the_amber_of_a_field_to_check(qt):
    """Warm colours for the plaintiffs, cool ones for the defense, each firm of a side a colour of its own (nothing
    is written on the square to tell them apart: the user, 2026-10-26); none of them the amber the window marks a
    field to check with (the user, 2026-10-22: a pale orange shade read as one)."""
    from PySide6.QtGui import QImage
    from minute_filler.firm_marks import SHADES
    from minute_filler.gui.badges import badge_html, badge_icon, badge_size, side_name, tag_color
    from minute_filler.gui.theme import DARK, LIGHT
    plaintiff, defense = Mark(PLAINTIFF, 0), Mark(DEFENSE, 0)
    assert tag_color(plaintiff).hue() in range(15, 45)  # (orange)
    assert tag_color(defense).hue() in range(190, 240)  # (blue)
    for side_, row in SHADES.items():
        assert len(set(row)) == len(row), side_  # (each firm of a side its own colour)
        for n in range(len(row)):
            hue = tag_color(Mark(side_, n)).hue()
            if side_ == PLAINTIFF:  # (the sides stay apart: warm against cool)
                assert hue < 60 or hue > 300, row[n]
            elif side_ == DEFENSE:
                assert 160 < hue < 300, row[n]
    ambers = {LIGHT["review"].lower(), DARK["review"].lower(), "#b45309", "#f59e0b", "#fcd34d", "#fde68a"}
    assert not ambers & {c.lower() for row in SHADES.values() for c in row}
    assert badge_size(14) == (14, 14)  # (a square: no '001' to make room for)
    img = badge_icon(Mark(OTHER, 0), 14).pixmap(14, 14).toImage().convertToFormat(QImage.Format_ARGB32)
    colours = {img.pixelColor(x, y).name() for x in range(3, 11) for y in range(3, 11)}
    assert colours == {tag_color(Mark(OTHER, 0)).name()}  # (its colour all over: nothing written on it)
    html_ = badge_html(defense, "Counsel & Counsel")
    assert f"color:{tag_color(defense).name()}" in html_ and "&#9632;" in html_ and "Counsel &amp; Counsel" in html_
    assert "background-color" not in html_ and "&nbsp;A&nbsp;" not in html_
    assert badge_html(None, "A & B") == "A &amp; B"
    assert side_name(plaintiff) == "A plaintiffs' firm" and side_name(defense) == "A defense firm"


def test_the_window_marks_each_firm_in_its_tables(qt, tmp_path, monkeypatch, make_window):
    """Who ordered's table: each firm's square beside its name (its side in the tooltip) and a stripe of its colour
    at the name's left edge, no shade behind it; Who pays what: its square and a stripe."""
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
    assert win.att.item(0, 1).toolTip() == "A plaintiffs' firm" and win.att.item(1, 1).toolTip() == "A defense firm"
    assert f"<span style='color:{stripes[0]}'>&#9632;</span>" in win.pays.text()
    assert f"<span style='color:{stripes[1]}'>&#9632;</span>" in win.pays.text()
    assert f"bgcolor='{stripes[0]}'" in win.pays.text()
