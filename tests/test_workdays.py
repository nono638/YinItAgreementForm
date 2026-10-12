"""Business days (the user, 2026-10-11): minute agreement forms and invoices made on a weekend or a court holiday are
dated the next business day, turnaround days count business days (from the form's date, or the real day), and,
when Settings -> Dates says so, one made after the evening hour is dated the next day. The court holidays are rules
in plain words (New York's courts at first: Saturday's closed the Friday before, Sunday's the Monday after), worked
out for any year, and editable; the window says under the dates what moved them, and the Saved message too.
Every test here sees the real calendar (marked workdays: not conftest's every_day_open) at a time it sets. All
names and numbers are made up."""
import time
from datetime import date, datetime
from pathlib import Path

import pymupdf
import pytest

from helpers import pat_settings, transcript_pdf
from minute_filler import workdays
from minute_filler.models import FieldState
from minute_filler.settings import Settings
from minute_filler.workdays import (add_business_days, date_warning, delivery_day, document_day, next_business_day,
                                    parse_rule, quick_day)

pytestmark = pytest.mark.workdays

SUNDAY = datetime(2026, 10, 11, 10)  # (Monday 10/12/2026 is Columbus Day)


def clock(monkeypatch, at: datetime) -> None:
    """The time it is for the code under test."""
    monkeypatch.setattr(workdays, "now", lambda: at)


def holidays(year: int, s: Settings | None = None) -> list[tuple[str, str]]:
    """The court holidays of a year as ("10/12", "Columbus Day")."""
    hol = (s or Settings()).holiday_calendar()
    return [(f"{d.month}/{d.day}", n) for d, n in hol.between(date(year, 1, 1), date(year, 12, 31))]


# ------------------------------------------------------------------ the rules

@pytest.mark.parametrize("text, y2026, y2027", [
    ("January 1", date(2026, 1, 1), date(2027, 1, 1)),
    ("Jan 1", date(2026, 1, 1), date(2027, 1, 1)),
    ("1/1", date(2026, 1, 1), date(2027, 1, 1)),
    ("3rd Monday of January", date(2026, 1, 19), date(2027, 1, 18)),
    ("third Monday in January", date(2026, 1, 19), date(2027, 1, 18)),
    ("last Monday of May", date(2026, 5, 25), date(2027, 5, 31)),
    ("Tuesday after the 1st Monday of November", date(2026, 11, 3), date(2027, 11, 2)),
    ("day after the 4th Thursday of November", date(2026, 11, 27), date(2027, 11, 26)),
    ("Friday before July 4", date(2026, 7, 3), date(2027, 7, 2)),
    ("12/24/2026", date(2026, 12, 24), None),
    ("December 24, 2026", date(2026, 12, 24), None),
    ("2026-12-24", date(2026, 12, 24), None),
    ("5th Monday of February", None, None),
])
def test_a_holiday_rule_in_plain_words(text, y2026, y2027):
    rule = parse_rule(text)
    assert rule is not None and (rule.on(2026), rule.on(2027)) == (y2026, y2027)
    assert parse_rule("Feb 29").on(2028) == date(2028, 2, 29) and parse_rule("Feb 29").on(2027) is None


@pytest.mark.parametrize("text", ["", "nonsense", "Feb 30", "13/1", "2nd Funday of May", "Tuesday after Fooday",
                                  "2/30/2026", "the 9th Monday of June"])
def test_a_rule_that_cant_be_read(text):
    assert parse_rule(text) is None


def test_new_yorks_court_holidays_with_the_weekend_ones_moved():
    """nycourts.gov's 2026 list (Independence Day, a Saturday, closed Friday 7/3) and 2027's (Juneteenth and
    Christmas on a Saturday: the Fridays before; July 4 on a Sunday: Monday 7/5; New Year's Day 2028, a Saturday:
    Friday 12/31/2027)."""
    assert holidays(2026) == [
        ("1/1", "New Year's Day"), ("1/19", "Martin Luther King Jr. Day"), ("2/12", "Lincoln's Birthday"),
        ("2/16", "Washington's Birthday"), ("5/25", "Memorial Day"), ("6/19", "Juneteenth"),
        ("7/3", "Independence Day"), ("9/7", "Labor Day"), ("10/12", "Columbus Day"), ("11/3", "Election Day"),
        ("11/11", "Veterans Day"), ("11/26", "Thanksgiving Day"), ("12/25", "Christmas Day")]
    got = dict(holidays(2027))
    assert got["6/18"] == "Juneteenth" and got["7/5"] == "Independence Day" and got["12/24"] == "Christmas Day"
    assert got["12/31"] == "New Year's Day" and len(got) == 14
    s = Settings()
    s.holiday_weekend = "none"  # (not moved: no day off)
    assert "7/3" not in dict(holidays(2026, s)) and dict(holidays(2026, s))["7/4"] == "Independence Day"


def test_the_holidays_follow_the_list():
    s = Settings()
    hol = s.holiday_calendar()
    assert s.holiday_calendar() is hol  # (worked out once)
    s.holidays = s.holidays + [{"name": "Day after Thanksgiving", "when": "Friday after the 4th Thursday of November"},
                               {"name": "Typo", "when": "2nd Funday of May"}]
    assert s.holiday_calendar().name(date(2026, 11, 27)) == "Day after Thanksgiving"
    s.holidays = [h for h in s.holidays if h["name"] != "Columbus Day"]
    assert s.holiday_calendar().name(date(2026, 10, 12)) == ""


def test_business_days():
    hol = Settings().holiday_calendar()
    assert next_business_day(date(2026, 10, 11), hol) == date(2026, 10, 13)  # Sunday, then Columbus Day
    assert next_business_day(date(2026, 10, 14), hol) == date(2026, 10, 14)
    assert add_business_days(date(2026, 10, 13), 5, hol) == date(2026, 10, 20)
    assert add_business_days(date(2026, 11, 9), 3, hol) == date(2026, 11, 13)  # (Veterans Day, Wednesday)


# ------------------------------------------------------------------ the day a form is dated

@pytest.mark.parametrize("at, day, note", [
    (SUNDAY, date(2026, 10, 13),
     "Dated Tue 10/13/2026, the next business day: today is a Sunday and Mon 10/12 is Columbus Day."),
    (datetime(2026, 10, 12, 9), date(2026, 10, 13), "Dated Tue 10/13/2026, the next business day: today is "
                                                    "Columbus Day."),
    (datetime(2026, 10, 14, 23, 30), date(2026, 10, 14), ""),
])
def test_a_form_made_on_a_weekend_or_a_holiday_is_dated_the_next_business_day(at, day, note):
    dating = document_day(Settings(), at)
    assert (dating.day, dating.note(), dating.moved()) == (day, note, bool(note))


@pytest.mark.parametrize("at, day, note", [
    (datetime(2026, 10, 16, 17, 1), date(2026, 10, 19),
     "Dated Mon 10/19/2026, the next business day: it is after 5:00 PM and the weekend comes next."),
    (datetime(2026, 10, 16, 16, 59), date(2026, 10, 16), ""),
    (datetime(2026, 11, 25, 18), date(2026, 11, 27),
     "Dated Fri 11/27/2026, the next business day: it is after 5:00 PM and Thu 11/26 is Thanksgiving Day."),
    (datetime(2026, 12, 31, 18), date(2027, 1, 4), "Dated Mon 1/4/2027, the next business day: it is after "
                                                   "5:00 PM, Fri 1/1 is New Year's Day and the weekend comes next."),
])
def test_made_after_the_evening_hour_it_is_dated_the_next_day(at, day, note):
    s = Settings()
    assert s.after_hours is False  # (off at first)
    s.after_hours = True
    dating = document_day(s, at)
    assert (dating.day, dating.note()) == (day, note)


def test_each_part_can_be_switched_off():
    s = Settings()
    s.business_day_dating = False
    assert document_day(s, SUNDAY).day == date(2026, 10, 11)  # (as before: the day it is made)
    s.after_hours, s.after_hours_from = True, "18:30"
    friday = document_day(s, datetime(2026, 10, 16, 18, 31))
    assert friday.day == date(2026, 10, 17) and friday.note() == "Dated Sat 10/17/2026, the next day: it is after " \
                                                                 "6:30 PM."
    assert document_day(s, datetime(2026, 10, 16, 18, 29)).day == date(2026, 10, 16)


def test_the_turnaround_in_business_days_from_the_forms_date_or_today():
    s = Settings()
    assert (s.days_expedited, s.days_regular) == (5, 15)  # (one and three working weeks)
    assert delivery_day(s, 5, at=SUNDAY) == (date(2026, 10, 20), "5 business days from Tue 10/13/2026")
    assert delivery_day(s, 3, date(2026, 11, 9), at=SUNDAY) == (
        date(2026, 11, 13), "3 business days from Mon 11/9/2026 (Veterans Day on Wed 11/11 not counted)")
    s.turnaround_from = "today"
    assert delivery_day(s, 5, at=SUNDAY) == (
        date(2026, 10, 19), "5 business days from today (Columbus Day on Mon 10/12 not counted)")
    assert delivery_day(s, 0, at=SUNDAY) == (date(2026, 10, 13), "Today isn't a business day: moved to Tue 10/13/2026")
    s.turnaround_from, s.turnaround_business_days = "form", False  # calendar days, the last one moved
    assert delivery_day(s, 21, date(2026, 10, 10), at=SUNDAY) == (
        date(2026, 11, 2), "21 days from Sat 10/10/2026 is Sat 10/31/2026: moved to Mon 11/2/2026")
    assert delivery_day(s, 7, date(2026, 10, 14), at=SUNDAY) == (date(2026, 10, 21), "")


def test_a_day_typed_on_a_weekend_or_a_holiday_is_warned_about():
    s = Settings()
    assert date_warning("11/11/2026", s) == "⚠ 11/11/2026 is Veterans Day, a court holiday."
    assert date_warning("10/17/2026", s) == "⚠ 10/17/2026 is a Saturday."
    assert date_warning("10/14/2026", s) == "" and date_warning("next week", s) == ""


def test_the_quick_buttons_skip_weekends_and_holidays():
    s = Settings()
    assert quick_day(s, 0, at=SUNDAY) == "10/13/2026"  # Today: the form's date
    assert quick_day(s, 7, at=SUNDAY) == "10/20/2026"
    s.turnaround_from = "today"
    assert quick_day(s, 1, at=SUNDAY) == "10/13/2026"


# ------------------------------------------------------------------ settings

def test_old_settings_get_business_days():
    old = Settings.from_dict({"settings_version": 13, "days_expedited": 7, "days_regular": 21})
    assert (old.days_expedited, old.days_regular) == (5, 15)  # the old defaults: one and three working weeks
    own = Settings.from_dict({"settings_version": 13, "days_expedited": 10})
    assert (own.days_expedited, own.days_regular) == (10, 15)  # (a turnaround of the user's own stays)
    since = Settings.from_dict({"settings_version": 14, "days_expedited": 7})
    assert since.days_expedited == 7  # (chosen since)
    assert old.business_day_dating and old.turnaround_business_days and not old.after_hours
    assert len(old.holidays) == 13 and old.holidays[8] == {"name": "Columbus Day", "when": "2nd Monday of October"}


def test_the_dates_settings_are_cleaned_and_kept(tmp_path):
    s = Settings.from_dict({"after_hours_from": "5 pm", "holiday_weekend": "sideways", "turnaround_from": "never",
                            "holidays": [{"name": " Founders Day ", "when": " March 3 "}, {"name": 5, "when": "x"},
                                         "Columbus Day", {"name": "", "when": ""}]})
    assert (s.after_hours_from, s.holiday_weekend, s.turnaround_from) == ("17:00", "nearest", "form")
    assert s.holidays == [{"name": "Founders Day", "when": "March 3"}]
    s.after_hours, s.after_hours_from, s.holidays = True, "18:30", []
    s.save()
    got = Settings.load()
    assert (got.after_hours, got.after_hours_from, got.holidays) == (True, "18:30", [])  # (no holidays: allowed)
    assert Settings.from_dict({"after_hours_from": "9:05"}).after_hours_from == "09:05"


def test_an_unedited_template_rate_sheet_gets_the_new_days(tmp_path):
    from minute_filler import rates
    bundled = rates.bundled_dir() / "Rate Sheet TEMPLATE.csv"
    now = bundled.read_bytes()
    assert b"Expedite,,,,,5\r\n" in now and b"Regular,,,,,15\r\n" in now
    old = now.replace(b"Expedite,,,,,5", b"Expedite,,,,,7").replace(b"Regular,,,,,15", b"Regular,,,,,21")
    assert rates.is_old_bundled(bundled.name, old)  # (as 1.0.0 to 2.7.0 shipped it)
    plain, edited = tmp_path / "a", tmp_path / "b"
    for d, data in ((plain, old), (edited, old.replace(b"Daily,,,,,1", b"Daily,,,,,2"))):
        d.mkdir()
        (d / bundled.name).write_bytes(data)
        rates.seed(d)
    assert (plain / bundled.name).read_bytes() == now
    assert b"Daily,,,,,2" in (edited / bundled.name).read_bytes()  # (the user's own: kept)


# ------------------------------------------------------------------ the files

@pytest.fixture
def roe(tmp_path, monkeypatch):
    """Settings and a job read on Sunday 10/11/2026: a made-up transcript, Alex B. Counsel ticked."""
    from minute_filler.batch import expand_paths, group, read_docs
    clock(monkeypatch, SUNDAY)
    s = pat_settings()
    s.output_dir, s.records_dir = str(tmp_path / "out"), str(tmp_path / "records")
    (tmp_path / "in").mkdir()
    transcript_pdf(tmp_path / "in" / "Roe transcript.pdf")
    docs, errors = read_docs(expand_paths([str(tmp_path / "in")]), s)
    assert not errors
    job = group(docs, s)[0]
    for a in job.case.attorneys:
        a.checked = "Counsel" in (a.firm or "")
    return s, job


def fields(path) -> dict:
    """A PDF's fields by name."""
    with pymupdf.open(path) as doc:
        return {w.field_name: w.field_value for p in doc for w in p.widgets()}


def test_every_file_made_on_a_sunday_is_dated_the_next_business_day(roe):
    from minute_filler.batch import fill_jobs
    from minute_filler.deliver import ledger_for
    s, job = roe
    assert job.case.get("agreement_date") == "10/13/2026"  # (as read: the window shows it)
    assert job.case.get("delivery_date") == "10/20/2026"   # Expedited: 5 business days from it
    fill_jobs([job], s, outputs=["agreement", "mofr", "invoice"])
    agreement, mofr, invoice = job.saved[:3]
    assert fields(agreement)["Date of Agreement"] == "10/13/2026"
    assert fields(agreement)["9 Estimated Delivery Date"] == "10/20/2026"
    assert fields(invoice)["date"] == "10/13/2026"
    assert all("10-13-2026" in p.name for p in (agreement, mofr))  # ({today} in the file names)
    lg = ledger_for(s)
    assert lg.invoices()[0].created == "2026-10-13" and lg.invoices()[0].invoice_no.startswith("2026-")


def test_an_invoice_made_on_new_years_eve_evening_is_next_years(roe, monkeypatch):
    from minute_filler.batch import fill_jobs
    from minute_filler.deliver import ledger_for
    s, job = roe
    s.after_hours = True
    clock(monkeypatch, datetime(2026, 12, 31, 18))
    fill_jobs([job], s, outputs=["agreement", "invoice"])
    agreement, invoice = job.saved[:2]
    assert fields(agreement)["Date of Agreement"] == "1/4/2027"  # (worked out again as the files were made)
    assert fields(invoice)["date"] == "1/4/2027"
    got = ledger_for(s).invoices()[0]
    assert got.invoice_no == "2027-0001" and got.created == "2027-01-04"


def test_a_form_filled_on_its_own_is_dated_the_next_business_day(tmp_path, monkeypatch):
    from minute_filler.fill import fill
    from minute_filler.models import CaseInfo
    clock(monkeypatch, SUNDAY)
    made = fill(CaseInfo(), None, pat_settings(), tmp_path)
    assert fields(made)["Date of Agreement"] == "10/13/2026" and made.name.endswith("10-13-2026.pdf")


def test_a_form_of_two_speeds_is_delivered_by_the_later_one():
    """An agreement naming Daily for one day and Regular for the other (fill.speeds_case): its delivery date is
    Regular's, 15 business days from the form's date (Election Day not counted)."""
    from minute_filler.fill import speeds_case
    from minute_filler.models import CaseInfo
    s = Settings()
    case = CaseInfo()
    case.set("delivery", "Expedited")
    out = speeds_case(case, [("Daily", "6/3/2026"), ("Regular", "6/4/2026")], s, date(2026, 10, 13))
    assert [sp for sp, _, _ in out.form_speeds] == ["Daily", "Regular"]
    assert out.get("delivery_date") == "11/4/2026"


def test_the_forms_of_several_days_are_dated_when_they_are_made(tmp_path, monkeypatch):
    """A trial's agreement (one for both days, batch.case_forms) read on Sunday and made on Wednesday 10/14/2026:
    dated that Wednesday, its delivery date 5 business days from it."""
    from minute_filler.batch import expand_paths, fill_jobs, group, read_docs
    clock(monkeypatch, SUNDAY)
    s = pat_settings()
    s.output_dir, s.records_dir, s.save_math = str(tmp_path / "out"), str(tmp_path / "records"), "off"
    d = tmp_path / "in"
    d.mkdir()
    transcript_pdf(d / "Roe day 1.pdf")
    transcript_pdf(d / "Roe day 2.pdf", date="June 4, 2026")
    docs, errors = read_docs(expand_paths([str(d)]), s)
    jobs = group(docs, s)
    assert not errors and len(jobs) == 2 and jobs[0].case.get("delivery_date") == "10/20/2026"
    for j in jobs:
        for a in j.case.attorneys:
            a.checked = "Counsel" in (a.firm or "")
    clock(monkeypatch, datetime(2026, 10, 14, 10))
    fill_jobs(jobs, s, outputs=["agreement", "invoice"])
    agreement = next(p for p in jobs[0].saved if p.name.startswith("Minute Agreement"))
    assert "6-3-2026 to 6-4-2026" in agreement.name and "10-14-2026" in agreement.name  # (the trial's one)
    got = fields(agreement)
    assert got["Date of Agreement"] == "10/14/2026" and got["9 Estimated Delivery Date"] == "10/21/2026"


def test_a_date_typed_is_kept_and_a_given_day_is_used(roe, tmp_path):
    from minute_filler.deliver import generate
    s, job = roe
    job.case.fields["agreement_date"] = FieldState("10/20/2026", "you", 1.0, ["10/20/2026"])
    made = generate(job.case, s, tmp_path / "x", ["agreement"], job.invoice_sets(), ordered=job.ordered_pages(),
                    day=date(2026, 10, 14))
    got = fields(made[0])
    assert got["Date of Agreement"] == "10/20/2026"  # the user's
    assert got["9 Estimated Delivery Date"] == "10/21/2026"  # 5 business days from the day given
    assert "10-14-2026" in made[0].name


# ------------------------------------------------------------------ the window

@pytest.fixture
def window(tmp_path, monkeypatch, make_window):
    """The window on Sunday 10/11/2026, a made-up transcript read (Alex B. Counsel ticked)."""
    from PySide6 import QtWidgets
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)
    clock(monkeypatch, SUNDAY)
    s = pat_settings(initials="pr")
    s.use_ai = s.open_after = False
    s.output_dir, s.records_dir = str(tmp_path / "out"), str(tmp_path / "records")
    win = make_window(s)
    win.add_files([str(transcript_pdf(tmp_path / "Roe.pdf"))])
    end = time.time() + 20
    while time.time() < end and not (win.cur.docs and not win.runner._live):
        QtWidgets.QApplication.processEvents()
        time.sleep(0.01)
    assert win.cur.docs
    for a in win.cur.case.attorneys:
        a.checked = "Counsel" in (a.firm or "")
    win.cur.att_touched = True
    win._show_case()
    return win


def shown(win, key) -> str:
    """The note under a date, "" when its row is hidden."""
    note = win.date_notes[key]
    return note.text() if win.date_form.isRowVisible(note) else ""


def test_the_window_says_why_the_dates_moved(window):
    assert window.rows["agreement_date"].text() == "10/13/2026"
    assert shown(window, "agreement_date") == ("Dated Tue 10/13/2026, the next business day: today is a Sunday and "
                                               "Mon 10/12 is Columbus Day.")
    assert window.rows["delivery_date"].text() == "10/20/2026"
    assert shown(window, "delivery_date") == "5 business days from Tue 10/13/2026"
    window.rows["delivery_date"].choose("11/11/2026")  # (picked by hand: never moved, only warned about)
    assert window.rows["delivery_date"].text() == "11/11/2026"
    assert shown(window, "delivery_date") == "⚠ 11/11/2026 is Veterans Day, a court holiday."
    window.rows["delivery_date"].choose("11/12/2026")
    assert shown(window, "delivery_date") == ""
    tip = next(b for b, label, _, _ in window.quick_buttons if label == "1 week").toolTip()
    assert tip.startswith("Estimated delivery 10/20/2026 - a week from the form's date")


def test_the_dates_follow_the_clock_but_not_a_date_typed(window, monkeypatch):
    window.s.after_hours = True
    window.rows["delivery_date"].choose("11/12/2026")
    clock(monkeypatch, datetime(2026, 10, 13, 16, 59))
    window._redate()
    assert window.rows["agreement_date"].text() == "10/13/2026" and shown(window, "agreement_date") == ""
    clock(monkeypatch, datetime(2026, 10, 13, 17, 1))  # (the minute's timer, or the window active again)
    window._redate()
    assert window.rows["agreement_date"].text() == "10/14/2026"
    assert window.cur.case.get("agreement_date") == "10/14/2026"
    assert shown(window, "agreement_date") == "Dated Wed 10/14/2026, the next business day: it is after 5:00 PM."
    assert window.rows["delivery_date"].text() == "11/12/2026"  # the user's


def test_settings_saved_date_the_jobs_again(window):
    """Settings -> Dates saved: the job's dates and the quick buttons' days follow."""
    window.s.business_day_dating = False  # (Settings -> Dates, saved)
    window._settings_changed()
    assert window.rows["agreement_date"].text() == "10/11/2026" and shown(window, "agreement_date") == ""
    assert window.rows["delivery_date"].text() == "10/19/2026"  # 5 business days from Sunday (Columbus Day skipped)
    tip = next(b for b, label, _, _ in window.quick_buttons if label == "1 week").toolTip()
    assert tip.startswith("Estimated delivery 10/19/2026 - a week from the form's date")  # (Sunday 10/18: Monday)


def test_the_saved_message_says_the_date(window, monkeypatch):
    said = []
    monkeypatch.setattr(window, "_saved_box", lambda title, text, *a, **k: said.append(text))
    window.output_boxes["agreement"].setChecked(True)
    window.fill()
    assert said and said[0].startswith("Dated Tue 10/13/2026, the next business day: today is a Sunday and Mon "
                                       "10/12 is Columbus Day.\n\nSaved ")
    assert fields(window.cur.saved[0])["Date of Agreement"] == "10/13/2026"


def wait(win, until, seconds=30):
    """Runs the event loop until no work is running and `until()` holds; fails after `seconds`."""
    from PySide6 import QtWidgets
    end = time.time() + seconds
    while time.time() < end:
        QtWidgets.QApplication.processEvents()
        if not win.runner._live and until():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


@pytest.mark.parametrize("all_jobs", [False, True])
def test_the_files_are_dated_as_the_preview_showed_them(window, monkeypatch, qt, all_jobs):
    """The evening hour passes while the preview is open (Generate, Generate all): the files are saved dated as
    they were shown."""
    from minute_filler.gui.preview import PreviewDialog
    window.s.after_hours = window.s.preview_before_saving = True
    clock(monkeypatch, datetime(2026, 10, 13, 16, 59))
    window._redate()

    def later(dlg):
        clock(monkeypatch, datetime(2026, 10, 13, 17, 1))
        return qt.QDialog.Accepted
    monkeypatch.setattr(PreviewDialog, "exec", later)
    monkeypatch.setattr(window, "_saved_box", lambda *a, **k: None)
    window.output_boxes["agreement"].setChecked(True)
    if all_jobs:  # (a second day of the case: with one job, Generate all is Generate)
        window.add_files([str(transcript_pdf(Path(window.s.output_dir).parent / "Roe 2.pdf", date="June 4, 2026"))],
                         batch=True)
        wait(window, lambda: len(window.jobs) == 2)
        for job in window.jobs:
            for a in job.case.attorneys:
                a.checked = "Counsel" in (a.firm or "")
            job.att_touched = True
        window.fill_all_jobs()
        wait(window, lambda: all(j.saved for j in window.jobs))
    else:
        window.fill()
    assert fields(window.cur.saved[0])["Date of Agreement"] == "10/13/2026"


def test_the_calendar_marks_the_court_holidays(window):
    from PySide6.QtCore import QDate
    row = window.rows["agreement_date"]
    row.calendar.menu().aboutToShow.emit()  # (the month of 10/13/2026)
    assert row.month.dateTextFormat(QDate(2026, 10, 12)).toolTip() == "Columbus Day"
    assert row.month.dateTextFormat(QDate(2026, 11, 11)).toolTip() == "Veterans Day"  # (the next month's days)
    assert row.month.dateTextFormat(QDate(2026, 10, 14)).toolTip() == ""
    row.month.setCurrentPage(2026, 12)
    assert row.month.dateTextFormat(QDate(2026, 12, 25)).toolTip() == "Christmas Day"


# ------------------------------------------------------------------ Settings -> Dates

def test_the_dates_tab_round_trip(qt, monkeypatch):
    from PySide6.QtCore import QTime
    from minute_filler.gui.dialogs import SettingsDialog
    s = pat_settings()
    s.save()
    dlg = SettingsDialog(s)
    dlg.show_tab("Dates")
    assert dlg.tabs.tabText(dlg.tabs.currentIndex()) == "Dates"
    assert dlg.t_dating.isChecked() and dlg.t_business.isChecked() and not dlg.t_after.isChecked()
    assert not dlg.t_time.isEnabled() and dlg.t_time.time() == QTime(17, 0)
    dlg.t_dating.setChecked(False)
    dlg.t_after.setChecked(True)
    assert dlg.t_time.isEnabled()
    dlg.t_time.setTime(QTime(18, 30))
    dlg.t_from.setCurrentIndex(dlg.t_from.findData("today"))
    ed = dlg.t_holidays
    ed._add()
    r = ed.table.rowCount() - 1
    ed.table.item(r, 0).setText("Day after Thanksgiving")
    ed.table.item(r, 1).setText("Friday after the 4th Thursday of November")
    dlg.accept()
    got = Settings.load()
    assert not got.business_day_dating and got.after_hours and got.after_hours_from == "18:30"
    assert got.turnaround_from == "today" and got.holidays[-1] == {"name": "Day after Thanksgiving",
                                                                    "when": "Friday after the 4th Thursday of November"}


def test_the_holiday_editor(qt, monkeypatch):
    from minute_filler.courthouses import holiday_rows
    from minute_filler.gui.holiday_editor import NOT_UNDERSTOOD, HolidayEditor
    ed = HolidayEditor(holiday_rows(), today=date(2026, 10, 11))
    names = [ed.table.item(r, 0).text() for r in range(ed.table.rowCount())]
    nxt = {n: ed.table.item(r, 2).text() for r, n in enumerate(names)}
    assert nxt["Columbus Day"] == "Mon 10/12/2026" and nxt["New Year's Day"] == "Fri 1/1/2027"
    assert nxt["Independence Day"] == "Mon 7/5/2027"  # (a Sunday next year: the Monday after)
    assert ed.coming.text().startswith("Coming up: Columbus Day Mon 10/12/2026, Election Day Tue 11/3/2026, "
                                       "Veterans Day Wed 11/11/2026")
    r = names.index("Columbus Day")
    ed.table.item(r, 1).setText("2nd Funday of October")
    assert ed.table.item(r, 2).text() == NOT_UNDERSTOOD and "3rd Monday of January" in ed.table.item(r, 2).toolTip()
    assert "Columbus Day" not in ed.coming.text()
    assert ed.rows()[r] == {"name": "Columbus Day", "when": "2nd Funday of October"}  # (kept, to be put right)
    ed.table.setCurrentCell(0, 0)
    ed._remove()
    assert len(ed.rows()) == 12 and ed.rows()[0]["name"] == "Martin Luther King Jr. Day"
    ed.weekend_box.setCurrentIndex(ed.weekend_box.findData("none"))
    assert ed.weekend() == "none"
    monkeypatch.setattr(qt.QMessageBox, "question", lambda *a, **k: qt.QMessageBox.Yes)
    ed._restore()
    assert ed.rows() == holiday_rows() and ed.weekend() == "nearest"
    once = HolidayEditor([{"name": "Closed", "when": "3/2/2026"}], today=date(2026, 10, 11))
    assert once.table.item(0, 2).text() == "(past)" and once.coming.text() == ("No court holidays in the next "
                                                                                "three months.")
