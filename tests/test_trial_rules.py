"""After 2.10.0 (the user, 2026-10-21): a trial is billed one way, day after day (batch.trial_split_rules,
Job.trial_rule: a later day of the same index number is divided as its first invoiced day was, whatever Settings
says by then); a Parties number that counts parties not named on pages ordered at different speeds holds the
invoice (Job.unnamed_problem: the app doesn't choose their speed), the window saying so and lighting up the
Parties box; and the math sent to one firm shows only what that firm owes (invoice_math.explain's one_firm, in
the PDFs Generate saves for each invoice and from the math window's Save as PDF...). All names are made up."""
import json
from decimal import Decimal

import pytest

from minute_filler.batch import fill_jobs, note_trial_rules, trial_split_rules
from minute_filler.deliver import ledger_for

from test_mixed_speeds import A, B, bills, excerpt_example, typed_day
from test_split_rules import made_of
from test_sweep_270 import counsel, one_day, smith, wait, window  # noqa: F401 (window: a fixture)


@pytest.fixture
def s(tmp_path):
    from helpers import pat_settings
    s = pat_settings()
    s.output_dir = str(tmp_path / "out")
    s.records_dir = str(tmp_path / "records")
    s.invoice_include_index = False
    s.save_math = "off"
    return s


MAKE_WHOLE_SMITH = [("Immediate", Decimal("1065.00"))]  # (Smith Law's bill of the excerpt example, each way)
SAME_SPEED_SMITH = [("Immediate", Decimal("1032.00"))]


def second_day(index="712345/2021"):
    day = excerpt_example()
    day.case.set("dates", "6/4/2026", "user")
    day.case.set("index_no", index, "user")
    return day


# ------------------------------------------------------------------ one way for the whole trial


def test_a_later_day_of_a_trial_is_billed_as_its_first_day_was(s):
    """Day 1 invoiced by Make-Whole; Settings now Same-Speed; Day 2 of the same trial, billed on its own, is
    Make-Whole too and keeps it; a day of another trial is billed as Settings say."""
    fill_jobs([excerpt_example()], s, outputs=["invoice"])
    s.invoice_split_rule = "same_speed"
    lg = ledger_for(s)
    assert trial_split_rules(lg) == {"712345/2021": "make_whole"}
    day2 = second_day("712345/21")  # (the same number, written short)
    note_trial_rules([day2], trial_split_rules(lg))
    assert day2.trial_rule == "make_whole" and bills(s, day2)[B] == MAKE_WHOLE_SMITH  # (as the window prices it)
    fill_jobs([day2], s, outputs=["invoice"])
    assert day2.split_rule == "make_whole"
    day3 = second_day()  # (nobody priced it before: Generate all reads the records itself)
    day3.case.set("dates", "6/5/2026", "user")
    fill_jobs([day3], s, outputs=["invoice"])
    assert day3.split_rule == "make_whole"
    other = second_day("799999/2022")
    fill_jobs([other], s, outputs=["invoice"])
    assert other.split_rule == "same_speed" and bills(s, other)[B] == SAME_SPEED_SMITH


def test_a_day_billed_already_keeps_its_own_way(s):
    """A day billed one way before trials kept theirs (2.10.0 allowed it) stays billed that way."""
    fill_jobs([excerpt_example()], s, outputs=["invoice"])
    own = second_day()
    own.split_rule = "same_speed"
    note_trial_rules([own], trial_split_rules(ledger_for(s)))
    assert own.trial_rule == "make_whole" and own.invoice_opts().split_rule == "same_speed"


def test_the_trials_way_comes_from_invoices_not_in_the_trash(s):
    """Only invoices count, the first whose way is known: one in the trash doesn't, nor an agreement; an old
    record without its origin (before 2.9.0) was billed by the first rule."""
    lg = ledger_for(s)
    lg.log_activity("agreement", index_no="712345/2021", origin=json.dumps({"job": {"split_rule": "same_speed"}}))
    lg.log_activity("invoice", index_no="712345/2021", ts="2026-10-21T15:00:00",
                    origin=json.dumps({"job": {"split_rule": "same_speed"}}))
    assert trial_split_rules(lg) == {"712345/2021": "same_speed"}
    gone = next(a.id for a in lg.activity() if a.kind == "invoice")
    lg.delete(activity=[gone])
    assert trial_split_rules(lg) == {}
    lg.log_activity("invoice", index_no="712345/2021", ts="2026-10-01T10:00:00")  # (no origin: before 2.9.0)
    lg.log_activity("invoice", index_no="799999/2022", ts="2026-10-21T16:00:00",
                    origin=json.dumps({"joint": True, "split_rule": "same_speed"}))
    assert trial_split_rules(lg) == {"712345/2021": "make_whole", "799999/2022": "same_speed"}
    assert lg.invoice_origins()[0][0] == "712345/2021"  # (oldest first)


def test_days_billed_together_take_the_trials_way(s):
    """Two new days of a trial already invoiced, billed on one invoice: both by the trial's way."""
    from minute_filler.batch import invoice_groups
    fill_jobs([excerpt_example()], s, outputs=["invoice"])
    s.invoice_split_rule = "same_speed"
    days = [second_day(), second_day()]
    days[1].case.set("dates", "6/5/2026", "user")
    if len(invoice_groups(days, s)[0]) < 2:
        pytest.skip("the two days aren't billed together here")
    fill_jobs(days, s, outputs=["invoice"])
    assert [d.split_rule for d in days] == ["make_whole", "make_whole"]


# ------------------------------------------------------------------ parties not named, at different speeds


def unnamed_day(parties=3, speeds=("Daily", "Immediate")):
    job = typed_day()
    job.speeds = dict(zip((A, B), speeds))
    job.parties = parties
    return job


def test_parties_not_named_on_pages_at_different_speeds_hold_the_invoice(s):
    """Parties 3, two firms named at Daily and Immediate: what the third pays can't be told, so no invoice (the
    user, 2026-10-21: the app doesn't decide); at one speed, or Parties 2, it is billed as before."""
    job = unnamed_day()
    assert job.unnamed_problem() == job.invoice_hold() == (
        "Parties says 3, but 2 firms are named and they ordered different speeds, so what the other party pays "
        "can't be worked out: tick it in the attorney table with its speed, or set Parties to 2")
    assert "the other 2 parties pay" in unnamed_day(4).unnamed_problem()
    assert unnamed_day(2).unnamed_problem() == "" and unnamed_day(0).unnamed_problem() == ""
    assert unnamed_day(3, ("Daily", "Daily")).unnamed_problem() == ""
    assert unnamed_day(3, ("Daily", "")).unnamed_problem() == ""  # (a speed not set yet: Generate asks it)
    split = unnamed_day()
    split.portions = [(60, [A, B]), (120, [B])]  # (Excerpts...: the firms that ordered count, not Parties)
    assert split.unnamed_problem() == ""
    fill_jobs([job], s, outputs=["invoice"])
    assert "parties says 3" in job.error and not any("Invoice" in p.name for p in job.saved)


def test_the_window_says_so_and_lights_up_the_parties_box(window, qt, tmp_path, monkeypatch):
    job = one_day(window, qt, tmp_path, [counsel(), smith()])
    job.speeds = {A: "Daily", B: "Immediate"}
    job.parties = 3
    window._update_status()
    assert window.inv_info.text().startswith("⚠ Parties says 3, but 2 firms are named")
    assert "Parties is checked" in window.output_counts["invoice"].text()
    asked = []
    monkeypatch.setattr(qt.QMessageBox, "question", lambda parent, title, text, *a: (
        asked.append((title, text)), qt.QMessageBox.No)[1])
    flashed = []
    monkeypatch.setattr(window, "_flash", lambda w, ms=1500: flashed.append((w, ms)))
    assert window._without_unchecked_invoice(job, ["agreement", "invoice"]) == []
    assert asked[0][0] == "Parties needs checking" and "Parties says 3" in asked[0][1]
    assert flashed == [(window.inv_parties, 4000)]
    flashed.clear()
    window._go_to_problem()
    assert flashed[-1][0] is window.inv_parties


def test_the_window_prices_a_later_day_as_its_trial_was_billed(window, qt, tmp_path):
    """Day 1 invoiced by Make-Whole, Settings now Same-Speed: the window prices Day 2 of the same trial by
    Make-Whole (read from the records once until they change)."""
    fill_jobs([excerpt_example()], window.s, outputs=["invoice"])
    window.s.invoice_split_rule = "same_speed"
    window._records_changed()
    job = one_day(window, qt, tmp_path, [counsel(), smith()])
    job.speeds = {A: "Daily", B: "Immediate"}
    window._update_status()
    assert job.trial_rule == "make_whole" and job.invoice_opts().split_rule == "make_whole"


# ------------------------------------------------------------------ the math sent to one firm


def test_one_firms_math_shows_only_what_that_firm_owes(s):
    """Counsel & Counsel's math: its own row of the pages it shared at different speeds, not Smith Law's prices
    nor the firms together; everyone's has both rows and the total."""
    from minute_filler.invoice_math import OWN_HEADING, SPLIT_HEADING, explain
    made = made_of(s, excerpt_example())
    mine = next(m for m in made if m[0].atty.key() == A)
    html, plain = explain([mine], one_firm=True)
    assert (f"{OWN_HEADING}\n  60 pages ordered by Alex B. Counsel (Daily) and Dana Smith (Immediate):\n"
            "    Alex B. Counsel, at Daily: Original $3.25 + Copy $1.25 + E-mailed copy $1.25 = $5.75 a page\n") in plain
    assert "Dana Smith, at Immediate" not in plain and "Together:" not in plain and SPLIT_HEADING not in plain
    assert "$7.25" not in html and "Together, a page" not in html and "$13.00" not in html
    everyone = explain(made)[1]
    assert "Dana Smith, at Immediate" in everyone and "Together: $13.00 a page" in everyone
    assert explain(made, one_firm=True) == explain(made[:1], one_firm=True)  # (one invoice: the first)


def test_generate_saves_each_firms_own_math_and_everyones(s, tmp_path, monkeypatch):
    from minute_filler import invoice_math
    saved = {}
    monkeypatch.setattr(invoice_math, "to_pdf", lambda html, out: saved.setdefault(out.name, html) and out)
    made = [(f, f"2026-000{i}", tmp_path / f"Invoice 2026-000{i}.pdf")
            for i, (f, _) in enumerate(made_of(s, excerpt_example()), 1)]
    invoice_math.save_math(made, "both")
    own = saved["Invoice 2026-0001 - the math.pdf"]
    assert "Alex B. Counsel" in own and "$7.25" not in own and "Together, a page" not in own
    assert "Together, a page" not in saved["Invoice 2026-0002 - the math.pdf"]
    whole = next(v for k, v in saved.items() if k.startswith("Invoices"))
    assert "Together, a page" in whole and "$7.25" in whole


def test_the_math_window_saves_everyones_or_one_firms(s, qt, tmp_path, monkeypatch):
    from minute_filler.gui import preview
    from minute_filler.invoice_math import explain
    made = [(f, f"2026-000{i}") for i, (f, _) in enumerate(made_of(s, excerpt_example()), 1)]
    dlg = preview.MathDialog(made, s, None, tmp_path)
    save = next(b for b in dlg.findChildren(qt.QPushButton) if b.text() == "Save as PDF…")
    acts = [a.text() for a in save.menu().actions()]
    assert acts == ["Everyone's (2 invoices)…", "Only Alex B. Counsel (Counsel & Counsel)'s (invoice 2026-0001)…",
                    "Only Dana Smith (Smith Law)'s (invoice 2026-0002)…"]
    asked, kept = [], []
    monkeypatch.setattr(qt.QFileDialog, "getSaveFileName",
                        lambda parent, title, path, filt: (asked.append(path), (str(tmp_path / "x.pdf"), filt))[1])
    from minute_filler import invoice_math
    monkeypatch.setattr(invoice_math, "to_pdf", lambda html, out: (kept.append(html), out)[1])
    save.menu().actions()[2].trigger()
    assert asked[-1].endswith("Invoice 2026-0002 - Dana Smith (Smith Law) - the math.pdf")
    assert kept[-1] == explain([made[1]], dlg.view.layout_key, one_firm=True)[0]
    save.menu().actions()[0].trigger()
    assert asked[-1].endswith("Invoices 2026-0001 to 2026-0002 - the math.pdf") and kept[-1] == dlg.html


def test_one_invoice_without_shared_speeds_saves_as_before(s, qt, tmp_path):
    """One firm alone: Save as PDF... has no menu (there is nobody else's to leave out)."""
    from minute_filler.gui import preview
    job = typed_day(attorneys=[counsel()])
    dlg = preview.MathDialog([(f, "2026-0001") for f, _ in made_of(s, job)], s, None, tmp_path)
    save = next(b for b in dlg.findChildren(qt.QPushButton) if b.text() == "Save as PDF…")
    assert save.menu() is None


# ------------------------------------------------------------------ the speeds offered, soft locked


def test_the_speeds_offered_are_soft_locked_once_who_ordered_what_has_speeds(window, qt, tmp_path, monkeypatch):
    """A speed chosen in Who ordered what greys the Invoice panel's Speeds offered out; a click asks first (the
    user, 2026-10-21): No puts the box back and changes nothing, Yes changes it and stops asking for this job."""
    job = one_day(window, qt, tmp_path, [counsel(), smith()])
    window._update_status()
    boxes = window.inv_speed_boxes
    assert not any(cb.property("softlock") for cb in boxes.values())
    job.speeds = {A: "Daily", B: "Immediate"}
    window._update_status()
    assert all(cb.property("softlock") for cb in boxes.values())
    asked, answer = [], [qt.QMessageBox.No]
    monkeypatch.setattr(qt.QMessageBox, "question", lambda parent, title, text, *a: (asked.append(title),
                                                                                      answer[0])[1])
    name, cb = next((n, b) for n, b in boxes.items() if not b.isChecked())
    before = list(window.s.invoice_speeds)
    cb.click()
    assert asked == ["Speeds chosen in Who ordered what"] and not cb.isChecked()
    assert window.s.invoice_speeds == before
    answer[0] = qt.QMessageBox.Yes
    cb.click()
    assert cb.isChecked() and name in window.s.invoice_speeds and len(asked) == 2
    assert not cb.property("softlock")
    cb.click()  # (no more questions for this job)
    assert len(asked) == 2 and not cb.isChecked()
