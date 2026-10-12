"""Business days: the court holidays, the day a minute agreement form or an invoice is dated, and the estimated
delivery date counted in business days.

A holiday is a rule in plain words ("4th Thursday of November", see parse_rule), so the list in Settings -> Dates
holds for every year without a new list each January. The courthouse gives the first list (courthouses.Courthouse
.holidays: New York's court holidays). A holiday that falls on a Saturday is closed the Friday before, one on a
Sunday the Monday after, as New York's courts do (Settings.holiday_weekend).

What Settings -> Dates switches on, and where it is used:
- document_day: a form or invoice made on a weekend or a court holiday is dated the next business day
  (Settings.business_day_dating), and one made after the evening hour the next day (Settings.after_hours). One
  day for every file of a run: deliver.generate and batch.fill_jobs take it (`day`), worked out once as the run
  starts, so a preview and the files saved after it have the same date even across midnight.
- delivery_day: the estimated delivery date, the turnaround days counted in business days
  (Settings.turnaround_business_days) from the form's date or the real day (Settings.turnaround_from).
- quick_day: the window's quick buttons ("1 week"), whose day moves past weekends and holidays.
- date_warning: a date typed or picked by hand is never moved, only warned about ("is Veterans Day").

now() is the one clock everything here reads, so a test can set it (tests/conftest.py: every_day_open)."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import MAXYEAR, MINYEAR, date, datetime, time, timedelta
from typing import TYPE_CHECKING

from .dates import add_months, us_date

if TYPE_CHECKING:
    from .settings import Settings

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
ORDINALS = {"1st": 1, "first": 1, "2nd": 2, "second": 2, "3rd": 3, "third": 3, "4th": 4, "fourth": 4, "5th": 5,
            "fifth": 5, "last": -1}
# what Settings -> Dates shows under the holidays, and a rule it can't read says in its tooltip
RULE_EXAMPLES = ("January 1", "3rd Monday of January", "last Monday of May",
                 "Tuesday after the 1st Monday of November", "12/24/2026")
AFTER_HOURS = "17:00"  # Settings.after_hours_from when it can't be read
DAY = timedelta(days=1)


def now() -> datetime:
    """The time on this computer's clock: the one clock of this module (a test sets it)."""
    return datetime.now()


@dataclass(frozen=True)
class Rule:
    """When a holiday falls, read from its words by parse_rule. kind:
    "date": the same day each year (month, day: "July 4"), moved off a weekend as Settings.holiday_weekend says;
    "nth": the n-th weekday of a month (n -1: the last; "4th Thursday of November");
    "after" / "before": the first `weekday` after (or before) the day of `inner`, or the very next (previous) day
    with weekday -1 ("Tuesday after the 1st Monday of November", "day after ...");
    "once": that day only (year, month, day: "12/24/2026"), never moved."""
    kind: str
    month: int = 0
    day: int = 0
    n: int = 0
    weekday: int = -1
    year: int = 0
    inner: "Rule | None" = None

    def on(self, year: int) -> date | None:
        """The day it falls on in `year`, before any move off a weekend; None when there is none (a "once" rule of
        another year, February 29 outside a leap year, a 5th Monday a month hasn't got)."""
        if self.kind == "once":
            return date(self.year, self.month, self.day) if year == self.year else None
        if self.kind == "date":
            return date(year, self.month, self.day) if self.day <= calendar.monthrange(year, self.month)[1] else None
        if self.kind == "nth":
            last = calendar.monthrange(year, self.month)[1]
            days = [d for d in range(1, last + 1) if date(year, self.month, d).weekday() == self.weekday]
            if self.n == -1:
                return date(year, self.month, days[-1])
            return date(year, self.month, days[self.n - 1]) if self.n <= len(days) else None
        base = self.inner.on(year) if self.inner is not None else None
        if base is None:
            return None
        step = DAY if self.kind == "after" else -DAY
        d = base + step
        while self.weekday != -1 and d.weekday() != self.weekday:
            d += step
        return d


def _month(word: str) -> int:
    """'November' or 'nov' -> 11; 0 when it names no month."""
    word = word.lower().rstrip(".")
    return next((i + 1 for i, m in enumerate(MONTHS) if len(word) >= 3 and m.lower().startswith(word)), 0)


def _weekday(word: str) -> int:
    """'Thursday', 'thu' or 'Thursdays' -> 3; -1 when it names no day of the week."""
    word = word.lower().rstrip(".")
    word = word[:-1] if word.endswith("days") else word
    return next((i for i, w in enumerate(WEEKDAYS) if len(word) >= 3 and w.lower().startswith(word)), -1)


def _real(year: int, month: int, day: int) -> bool:
    """Whether that day exists (year 0: in some year, so February 29 does)."""
    if not (1 <= month <= 12 and day >= 1):
        return False
    return day <= calendar.monthrange(year or 2024, month)[1]


def parse_rule(text: str) -> Rule | None:
    """A holiday's rule from its words; None when they can't be read:
    'January 1', 'Jan 1', '1/1' (each year); '3rd Monday of January', 'third Monday in January', 'last Monday of
    May'; 'Tuesday after the 1st Monday of November', 'day after the 4th Thursday of November', 'day before
    July 4'; '12/24/2026', 'December 24, 2026', '2026-12-24' (that day only)."""
    t = " ".join(str(text or "").lower().replace(",", " ").split()).rstrip(".")
    if not t:
        return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", t) or re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        a, b, c = (int(x) for x in m.groups())
        y, mo, d = (a, b, c) if len(m.group(1)) == 4 else (c, a, b)
        return Rule("once", mo, d, year=y) if _real(y, mo, d) else None
    m = re.fullmatch(r"([a-z.]+) (\d{1,2})(?:st|nd|rd|th)? (\d{4})", t)
    if m and _month(m.group(1)):
        mo, d, y = _month(m.group(1)), int(m.group(2)), int(m.group(3))
        return Rule("once", mo, d, year=y) if _real(y, mo, d) else None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", t)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        return Rule("date", mo, d) if _real(0, mo, d) else None
    m = re.fullmatch(r"([a-z.]+) (\d{1,2})(?:st|nd|rd|th)?", t)
    if m and _month(m.group(1)):
        mo, d = _month(m.group(1)), int(m.group(2))
        return Rule("date", mo, d) if _real(0, mo, d) else None
    m = re.fullmatch(r"(?:the )?([a-z0-9]+) ([a-z.]+) (?:of|in) ([a-z.]+)", t)
    if m and m.group(1) in ORDINALS and _weekday(m.group(2)) != -1 and _month(m.group(3)):
        return Rule("nth", _month(m.group(3)), n=ORDINALS[m.group(1)], weekday=_weekday(m.group(2)))
    m = re.fullmatch(r"(?:the )?([a-z.]+) (after|before) (?:the )?(.+)", t)
    if m and (m.group(1) == "day" or _weekday(m.group(1)) != -1):
        inner = parse_rule(m.group(3))
        if inner is not None:
            return Rule(m.group(2), weekday=-1 if m.group(1) == "day" else _weekday(m.group(1)), inner=inner)
    return None


class Holidays:
    """The court holidays of Settings -> Dates, for any year: rows {"name", "when"} (Settings.holidays; a row
    whose rule can't be read is left out), and weekend, what a holiday on a weekend does (Settings.holiday_weekend:
    "nearest", the Friday before or the Monday after, or "none"). Worked out a year at a time, from the rules of the
    year before and after too: New Year's Day 2028, a Saturday, is closed on Friday 12/31/2027."""

    def __init__(self, rows: list[dict], weekend: str = "nearest"):
        self.rules = [(str(r.get("name", "")).strip() or str(r.get("when", "")), rule) for r in rows
                      if isinstance(r, dict) and (rule := parse_rule(r.get("when", ""))) is not None]
        self.weekend = weekend
        self._years: dict[int, dict[date, str]] = {}

    def _moved(self, d: date, rule: Rule) -> date:
        """The day a holiday of the same date each year is closed on (Saturday: the Friday before; Sunday: the
        Monday after), as Settings.holiday_weekend says; any other rule's day as it is."""
        if rule.kind != "date" or self.weekend != "nearest":
            return d
        return d - DAY if d.weekday() == 5 else d + DAY if d.weekday() == 6 else d

    def _year(self, year: int) -> dict[date, str]:
        """The days closed in `year` -> the holiday's name (the first listed, when two fall on one day)."""
        if year not in self._years:
            out: dict[date, str] = {}
            # (a date typed as 12/31/9999 asks for year 10000 here, which date() refuses: those years are skipped)
            for y in range(max(year - 1, MINYEAR), min(year + 1, MAXYEAR) + 1):
                for name, rule in self.rules:
                    try:
                        d = rule.on(y)
                        if d is not None and (d := self._moved(d, rule)).year == year:
                            out.setdefault(d, name)
                    except (ValueError, OverflowError):  # (a "day after" stepping past 12/31/9999)
                        pass
            self._years[year] = out
        return self._years[year]

    def name(self, d: date) -> str:
        """The holiday on `d` ("Columbus Day"); "" when it is none."""
        return self._year(d.year).get(d, "")

    def between(self, first: date, last: date) -> list[tuple[date, str]]:
        """The holidays from `first` to `last` (both counted), in order: [(date, name)]."""
        return sorted((d, n) for y in range(first.year, last.year + 1) for d, n in self._year(y).items()
                      if first <= d <= last)


def is_business_day(d: date, hol: Holidays | None = None) -> bool:
    """A weekday that isn't a holiday."""
    return d.weekday() < 5 and not (hol is not None and hol.name(d))


def next_business_day(d: date, hol: Holidays | None = None) -> date:
    """d itself when it is a business day, else the first one after it."""
    for _ in range(3660):  # (a list closing every day for ten years: given up on, rather than a loop for good)
        if is_business_day(d, hol):
            return d
        d += DAY
    return d


def add_business_days(d: date, n: int, hol: Holidays | None = None) -> date:
    """The n-th business day after d (d itself doesn't count): Tue 10/13/2026 + 5 -> Tue 10/20/2026."""
    for _ in range(max(0, n)):
        d = next_business_day(d + DAY, hol)
    return d


def short(d: date) -> str:
    """'Mon 10/12' (no year: said next to a date that has one)."""
    return f"{WEEKDAYS[d.weekday()][:3]} {d.month}/{d.day}"


def full(d: date) -> str:
    """'Tue 10/13/2026'."""
    return f"{WEEKDAYS[d.weekday()][:3]} {us_date(d)}"


def _and(parts: list[str]) -> str:
    """'a', 'a and b', 'a, b and c'."""
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def cutoff(s: "Settings") -> time:
    """Settings.after_hours_from as a time ("17:00" -> 5 PM); 5 PM when it can't be read."""
    for text in (s.after_hours_from, AFTER_HOURS):
        try:
            return datetime.strptime(text.strip(), "%H:%M").time()
        except (ValueError, AttributeError):
            continue
    return time(17)


def clock(t: time) -> str:
    """time(17, 0) -> '5:00 PM'."""
    return f"{t.hour % 12 or 12}:{t.minute:02} {'AM' if t.hour < 12 else 'PM'}"


class Day(date):
    """The day files are dated, as document_day gives it, which also knows the real day it was worked out on
    (made_on). With the turnaround counted from the day the files are made (Settings.turnaround_from "today"), a
    run that passes midnight between its preview and its save still counts from the day it was worked out, as the
    run's day goes everywhere the files are dated. Any other date counts from the clock's day, and so does a Day
    made from one by arithmetic or copied (Day + DAY, copy.deepcopy, pickle): those come without made_on."""
    made_on: date | None = None


@dataclass(frozen=True)
class Dating:
    """The day the files of a Generate are dated (document_day): day; today, the day they are made; why, what
    moved it ("today is a Sunday", "Mon 10/12 is Columbus Day"); business, whether it moved to a business day
    (Settings.business_day_dating) or only to the next day (after hours)."""
    day: date
    today: date
    why: tuple[str, ...] = ()
    business: bool = True

    def moved(self) -> bool:
        """Whether the files are dated another day than the one they are made on."""
        return self.day != self.today

    def note(self) -> str:
        """'Dated Tue 10/13/2026, the next business day: today is a Sunday and Mon 10/12 is Columbus Day.' ("" when
        the day is today), for the window to say."""
        if not self.moved():
            return ""
        what = "the next business day" if self.business else "the next day"
        return f"Dated {full(self.day)}, {what}" + (f": {_and(list(self.why))}." if self.why else ".")


def _skipped(first: date, day: date, today: date, hol: Holidays) -> list[str]:
    """Why each day from `first` up to `day` (not counted) isn't a business day, as Dating.why says it: the
    weekend once ("today is a Saturday", or "the weekend comes next"), each holiday by name."""
    out, weekend = [], False
    d = first
    while d < day:
        name = hol.name(d)
        if name:
            out.append(f"{'today' if d == today else short(d)} is {name}")
        elif d.weekday() >= 5 and not weekend:
            weekend = True
            out.append(f"today is a {WEEKDAYS[d.weekday()]}" if d == today else "the weekend comes next")
        d += DAY
    return out


def document_day(s: "Settings", at: datetime | None = None) -> Dating:
    """The day a minute agreement form or an invoice made at `at` (default: now) is dated. Today; after
    Settings.after_hours_from, when Settings.after_hours says so, tomorrow; then, when
    Settings.business_day_dating says so, the next business day from there (a weekend and the court holidays
    of Settings -> Dates skipped). Made on Sunday 10/11/2026 (Monday 10/12 is Columbus Day): Tuesday 10/13."""
    at = at or now()
    today = d = at.date()
    why: list[str] = []
    if s.after_hours and at.time() >= cutoff(s):
        d += DAY
        why.append(f"it is after {clock(cutoff(s))}")
    if s.business_day_dating:
        hol = s.holiday_calendar()
        first, d = d, next_business_day(d, hol)
        why += _skipped(first, d, today, hol)
    day = Day(d.year, d.month, d.day)
    day.made_on = today
    return Dating(day, today, tuple(why), s.business_day_dating)


def turnaround_start(s: "Settings", form_day: date | None = None, at: datetime | None = None) -> date:
    """The day the turnaround is counted from: the form's date (form_day, else document_day's), or the real
    today when Settings.turnaround_from is "today" (the one form_day was worked out on, when it is a Day)."""
    if s.turnaround_from == "today":
        made_on = form_day.made_on if isinstance(form_day, Day) else None
        return at.date() if at else made_on or now().date()
    return form_day or document_day(s, at).day


def delivery_day(s: "Settings", days: int, form_day: date | None = None,
                 at: datetime | None = None) -> tuple[date, str]:
    """The estimated delivery date `days` turnaround days after turnaround_start, and what the window says of it.
    In business days (Settings.turnaround_business_days): 5 from Tue 10/13/2026 -> Tue 10/20/2026, "5 business
    days from Tue 10/13/2026"; a holiday on the way is named (15 from it -> Wed 11/4/2026, "(Election Day on Tue
    11/3 not counted)"). Else in calendar days, the last one moved to the next business day ("15 days from Sat
    10/10/2026 is Sun 10/25/2026: moved to Mon 10/26/2026"; "" when it didn't move). 0 days (Immediate): the
    start itself, moved off a weekend or a holiday ("Sat 10/10/2026 isn't a business day: moved to Tue
    10/13/2026")."""
    hol = s.holiday_calendar()
    start = turnaround_start(s, form_day, at)
    real = (at or now()).date()
    since = "today" if start == real else full(start)
    if days <= 0:
        end = next_business_day(start, hol)
        return end, "" if end == start else f"{since[0].upper() + since[1:]} isn't a business day: moved to {full(end)}"
    if s.turnaround_business_days:
        end = add_business_days(start, days, hol)
        off = [f"{n} on {short(d)}" for d, n in hol.between(start + DAY, end) if d.weekday() < 5]
        note = f"{days} business day{'' if days == 1 else 's'} from {since}"
        return end, note + (f" ({_and(off)} not counted)" if off else "")
    raw = start + timedelta(days=days)
    end = next_business_day(raw, hol)
    return end, "" if end == raw else f"{days} days from {since} is {full(raw)}: moved to {full(end)}"


def quick_day(s: "Settings", days: int = 0, months: int = 0, at: datetime | None = None) -> str:
    """A quick button's estimated delivery date as M/D/YYYY: `days` and `months` from turnaround_start
    ("Today": that day), in calendar days, moved to the next business day when it falls on a weekend or a
    court holiday. "Tomorrow" on Wed 11/25/2026 -> '11/27/2026' (Thursday is Thanksgiving)."""
    start = turnaround_start(s, at=at)
    d = add_months(start, months) if months else start
    return us_date(next_business_day(d + timedelta(days=days), s.holiday_calendar()))


def date_warning(text: str, s: "Settings") -> str:
    """For a date typed or picked by hand (never moved): '⚠ 11/11/2026 is Veterans Day, a court holiday.' or
    '⚠ 10/17/2026 is a Saturday.'; "" for a business day or text that isn't a M/D/YYYY date."""
    try:
        d = datetime.strptime(str(text).strip(), "%m/%d/%Y").date()
    except ValueError:
        return ""
    name = s.holiday_calendar().name(d)
    if name:
        return f"⚠ {us_date(d)} is {name}, a court holiday."
    if d.weekday() >= 5:
        return f"⚠ {us_date(d)} is a {WEEKDAYS[d.weekday()]}."
    return ""
