"""Who ordered which pages of a case, as one table (the Excerpts window, gui/excerpts.py).

Each day of the case (a job, see batch.invoice_groups) is cut into runs of pages, and each run says which firms
ordered it: the whole day by everyone ticked (the default), or excerpts - firm A the whole trial, firm B a
stretch of day 1, firm C part of B's stretch and another of day 2. A run is typed in the page numbers printed
on the transcript ("141-170"; by its place in the day, "place 40-44", when they aren't known or can't say which
page) and the runs around it make room (carve). A run removed gives its pages to the run above it (remove), and a day can be one run again
(whole_day). A run nobody ordered is billed to nobody. What is set is kept on each day as Job.portions (rows of
(last page, firms), and a run's own speeds, see store) and the attorneys ticked on it, so the invoices
(invoice.firm_invoices) bill it as before: pages ordered by several firms share the original and the judge's
index between them (the index too, when Settings.invoice_index_shared says "split"), and each firm pays its own
copy (and its own index). Whether a day gets an index is judged on every page of it, as
Settings.invoice_index_rule says (with "any", another day of the invoice reaching the threshold is enough), so a
firm that ordered 10 pages of a 100-page day pays an index of its 10 pages.

prices() works out, as the table is changed, what each run costs each firm that ordered it, what each set of
firms ordering together pays for its pages ("A + B: 15 of your pages billed (30 total pages) - each of the 2
pays ..."), and each firm's invoice.

Each firm on a run ordered it at a speed (Run.speeds; the day's, Job.speeds, unless the run has its own). A
firm billed alone may leave it unset and choose from its invoice; firms that ordered a run together commit to
theirs (courthouses.speed_upfront), and are priced at it (invoice_calc.quote_ordered): at different speeds, the
run's one original is divided as the courthouse's split rule chosen in Settings says (or the one the job was
billed by already: batch.Job.split_rule). Until a speed is
set, such a firm is priced at the agreement form's (invoice.default_speed), as Generate's question offers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from decimal import Decimal

from . import courthouses
from .batch import Job, joint_invoice, portion_row, same_entries
from .invoice import ORDERED_BY_NOBODY, default_speed, firm_invoices, index_mode, index_pages
from .invoice_calc import Share, index_days, offered, quote_ordered, quote_shares
from .models import Attorney
from .settings import Settings
from .takes import numbers_known, place_words, run_numbers

_BY_PLACE = re.compile(r"(?i)^\s*place\b")  # a run typed by its place in the day, whatever the day's numbers: "place 40-44"


@dataclass
class Day:
    """One day of the case: its job, its date, the pages Excerpts splits (Job.portion_pages; a job of several
    days: all its billed pages, Job.invoice_pages) and the number printed on each of them, as read (Job.printed_pages:
    [] when the Pages field is typed in, None for a page whose number wasn't read; a job of several days: every
    page of its transcripts, Job.page_numbers, which only show). read: the numbers on its transcripts' pages, typed
    in or not (Job.page_numbers), which a day typed in shows for its whole run."""
    job: Job
    label: str
    pages: int
    printed: list = field(default_factory=list)
    splittable: bool = True  # one day of pages (a job of several days is ordered whole)
    read: list = field(default_factory=list)

    @property
    def numbered(self) -> bool:
        """The printed page numbers can stand for the day's pages (takes.numbers_known), so runs are typed in them.
        They needn't run upward: two transcripts of a day can number apart, or a reporter's number repeat (falls)."""
        return numbers_known(self.printed, self.pages)

    def falls(self) -> bool:
        """The day's numbers fall somewhere ("1–39, 10–29"): a number can be on two pages, and the window says so."""
        return self.numbered and run_numbers(self.printed).falls

    def span(self, a: int, b: int) -> str:
        """Pages a..b of the day (places, from 1) as the table shows them: the numbers read on them, '358–377' (or
        '1–39, 10–29' over a place where they start again), else their place, 'place 1–20' (bare, it read as page
        numbers). A day whose Pages field is typed in has its places counted in that number, not in the pages read:
        its whole run shows the numbers read, a run cut out of it its place. A job of several days, ordered
        whole: the numbers printed on its transcripts, as read ('236–461, 654–848'), not a count of its billed
        pages ('1–268' read as page numbers: the user, 2026-10-30)."""
        if not self.splittable:
            return number_spans(self.printed) or "(not printed)"
        if self.numbered:
            nums = self.printed[a - 1:b]
            if numbers_known(nums):
                return run_numbers(nums).text
        elif not self.printed and (a, b) == (1, self.pages) and numbers_known(self.read):
            return run_numbers(self.read).text
        return place_words(a, b)

    def example(self) -> str:
        """A run this day takes as typed, for the Page numbers cell's tooltip: its first 20 pages as shown, or, on
        a day whose numbers repeat, where those would be refused (parse), by place."""
        text = self.span(1, min(self.pages, 20))
        try:
            self.parse(text)
        except ValueError:
            return place_words(1, min(self.pages, 20))
        return text

    def place(self, a: int, b: int) -> str:
        """Pages a..b by their place in the day: '1–20 of 85 total pages' (every reporter's: the pages split are
        every page of the day's transcripts), '1–20 of 85 pages typed' when the Pages field was typed in (the
        user's own count); a job of several days is ordered whole."""
        if not self.splittable:
            return "every page (several days)"
        of = f"of {self.pages} pages typed" if self.job.pages_typed() else f"of {self.pages} total pages"
        return f"{a}–{b} {of}" if a != b else f"{a} {of}"

    def parse(self, text: str) -> tuple[int, int]:
        """A run as typed ('141-170', '141 – 170', '141'), in the printed numbers when they are known, as
        (first, last) places in the day; 'place 40-44' is by place on any day (the way out where a number can't say
        which page: _by_number). ValueError, saying why, when it isn't one of its pages."""
        nums = [int(x) for x in re.findall(r"\d+", text or "")]
        if not nums or len(nums) > 2:
            raise ValueError("type the run as first-last page, e.g. 141-170")
        a, b = sorted((nums[0], nums[-1]))
        if self.numbered and not _BY_PLACE.match(text):
            return self._by_number(a, b)
        if a < 1 or b > self.pages:
            raise ValueError(f"{self.label} goes from place 1 to place {self.pages}")
        return a, b

    def _by_number(self, a: int, b: int) -> tuple[int, int]:
        """Page numbers a..b as (first, last) places: the first page numbered a or more to the last numbered b or
        less, passing over pages whose number wasn't read (a number printed twice, where a reporter changes, takes
        both its pages). On a day whose numbers fall the same number can be on two pages, and the first found would
        bill the wrong ones, so of the stretches between falls only one may have any of a..b, and all of a..b must
        lie within it."""
        read = [(i, n) for i, n in enumerate(self.printed, 1) if n is not None]
        stretches: list[list[tuple[int, int]]] = []
        for place, n in read:
            if not stretches or n < stretches[-1][-1][1]:
                stretches.append([])
            stretches[-1].append((place, n))
        if len(stretches) == 1 and (a < read[0][1] or b > read[-1][1]):
            raise ValueError(f"{self.label}'s printed page numbers are {read[0][1]}–{read[-1][1]}")
        found = [s for s in stretches if any(a <= n <= b for _, n in s)]
        if not found:  # (every number typed falls among numbers the transcript skips)
            unread = next((i for i, n in enumerate(self.printed, 1) if n is None), None)
            raise ValueError((f"no page of {self.label} has a printed page number in {a}–{b}" if a != b else
                              f"no page of {self.label} has the printed page number {a}")
                             + (f" (a page whose number wasn't read goes by its place: place {unread})"
                                if unread else ""))
        first, last = (next(place for place, n in found[0] if n >= a),
                       max(place for place, n in found[0] if n <= b))
        if len(found) == 1 and found[0][0][1] <= a and b <= found[0][-1][1]:
            return first, last
        typed = f"{a}–{b}" if a != b else str(a)
        raise ValueError(f"{self.label}'s printed page numbers start again ({run_numbers(self.printed).text}), and "
                         f"{typed} is {'on more than one stretch' if len(found) > 1 else 'not all on one stretch'} of "
                         f"them: type the run by its place in the day instead, e.g. place {first}-{last}")


def number_spans(printed: list) -> str:
    """Printed page numbers as the stretches they run in: '236–461, 654–848' (a page without a known number
    is left out and ends a stretch); "" when none is known."""
    spans: list[list[int]] = []
    prev = None
    for n in printed:
        if n is not None and prev is not None and n == prev + 1:
            spans[-1][1] = n
        elif n is not None:
            spans.append([n, n])
        prev = n
    return ", ".join(f"{a}–{b}" if a != b else str(a) for a, b in spans)


@dataclass
class Run:
    """A run of pages of one day (places a..b, from 1), the firms (Attorney.key()) that ordered it (none = nobody
    ordered it: it is billed to nobody) and the speed each ordered it at, by key (only those set: the day's,
    Job.speeds, or the run's own)."""
    day: Day
    start: int
    end: int
    keys: list[str] = field(default_factory=list)
    speeds: dict[str, str] = field(default_factory=dict)

    def speed(self, key: str) -> str:
        """The speed firm `key` ordered the run at ("" = not set)."""
        return self.speeds.get(key, "")


def case_days(group: list[Job]) -> list[Day]:
    """The days of a case (the jobs of one invoice, see batch.invoice_groups), in order: a Day per job. A job of
    several days (Settings.batch_combine_dates) is one Day of all its pages, labelled with its dates, that can't
    be split (ordered whole)."""
    out = []
    for job in group:
        days = job.invoice_days()
        label = days[0][0] if len(days) == 1 else job.case.get("dates") or job.title()
        out.append(Day(job, label or "(no date)", job.portion_pages() if len(days) == 1 else job.invoice_pages(),
                       job.printed_pages() if len(days) == 1 else job.page_numbers(), len(days) == 1,
                       job.page_numbers()))
    return out


def firms_of(group: list[Job]) -> list[Attorney]:
    """The table's columns: every attorney of the case's days who can be billed (ticked or not), each once. The
    same firm on two days is one column: batch.same_entries runs first, as the prices and invoices see the
    firms (else a firm spelled two ways was two columns, and a tick stored its key twice)."""
    if len(group) > 1:
        same_entries(group)
    out, seen = [], set()
    for job in group:
        for a in job.case.attorneys:
            if not a.is_placeholder() and a.key() and a.key() not in seen:
                seen.add(a.key())
                out.append(a)
    return out


def runs_of(day: Day, firms: list[Attorney] | None = None) -> list[Run]:
    """A day's runs as kept (Job.portions, when they still end on its pages), else the whole day ordered by the
    attorneys ticked on it; each with the speeds set for its firms (Job.speed_of: the run's own, else the day's).
    firms: the table's columns (firms_of); each run's firms are put in their order, so
    the same firms read the same on every day ("Dana + Pat", not also "Pat + Dana")."""
    job = day.job
    order = {a.key(): i for i, a in enumerate(firms or [])}

    def keys_of(keys) -> list[str]:
        """A row's firms in the table's order; ORDERED_BY_NOBODY becomes no firms."""
        return sorted((k for k in keys if k != ORDERED_BY_NOBODY), key=lambda k: order.get(k, len(order)))

    def speeds_of(keys, row: int | None = None) -> dict[str, str]:
        """The speeds set for these firms on the run (Job.speed_of)."""
        return {k: job.speed_of(k, row) for k in keys if job.speed_of(k, row)}

    if day.splittable and job.portions is not None and job.portions_fit_pages():
        out, start = [], 1
        for i, (last, keys, *_) in enumerate(job.portions):
            ks = keys_of(keys)
            out.append(Run(day, start, int(last), ks, speeds_of(ks, i)))
            start = int(last) + 1
        return out
    ks = keys_of(job.ticked_keys())
    return [Run(day, 1, day.pages, ks, speeds_of(ks))]


def carve(runs: list[Run], i: int, a: int, b: int) -> list[Run]:
    """The day's runs with run i set to pages a..b (places): the runs around it make room, and pages it no
    longer covers stay with the firms that had them, at their speeds (a new run). ValueError when a..b isn't
    within the day."""
    day = runs[i].day
    if a < 1 or b > day.pages or a > b:
        raise ValueError(f"{day.label} goes from place 1 to place {day.pages}")
    keys, speeds = list(runs[i].keys), dict(runs[i].speeds)
    out: list[Run] = []
    for k, r in enumerate(runs):  # the other runs, less the pages a..b
        own_keys, own_speeds = (keys, speeds) if k == i else (r.keys, r.speeds)
        if r.start < a:
            out.append(Run(day, r.start, min(r.end, a - 1), list(own_keys), dict(own_speeds)))
        if r.end > b:
            out.append(Run(day, max(r.start, b + 1), r.end, list(own_keys), dict(own_speeds)))
    out.append(Run(day, a, b, keys, speeds))
    out.sort(key=lambda r: r.start)
    return out


def remove(runs: list[Run], i: int) -> list[Run]:
    """The day's runs without run i, every page still in one run (Remove run). Its pages go to the run above it,
    or to the run below for the day's first run: "21-30" of "1-20 Alex, 21-30 Alex + Dana, 31-40 Sam" joins
    "1-20 Alex". When that run was ordered by nobody and the run on the other side by a firm, they go to the
    other side instead (a run removed isn't left to nobody when a firm can have it). The run that grew is then
    joined with the runs touching it ordered by the same firms at the same speeds: "1-20 Alex, 21-30 Alex +
    Dana, 31-40 Alex" without "21-30" is "1-40 Alex". Runs of the same firms elsewhere in the day stay apart.
    ValueError when run i is the day's only run."""
    day = runs[i].day
    if len(runs) < 2:
        raise ValueError(f"{day.label} is one run: nothing to remove. Untick its firms to bill it to nobody.")
    out = [Run(day, r.start, r.end, list(r.keys), dict(r.speeds)) for r in runs]
    gone = out.pop(i)
    above = i - 1 if i > 0 else None
    below = i if i < len(out) else None  # (the run below is at i once run i is out)
    j, other = (above, below) if above is not None else (below, None)
    if not out[j].keys and other is not None and out[other].keys:
        j = other
    grown = out[j]
    grown.start, grown.end = min(grown.start, gone.start), max(grown.end, gone.end)
    same = (set(grown.keys), grown.speeds)
    lo = hi = j
    while lo > 0 and (set(out[lo - 1].keys), out[lo - 1].speeds) == same:
        lo -= 1
    while hi + 1 < len(out) and (set(out[hi + 1].keys), out[hi + 1].speeds) == same:
        hi += 1
    return out[:lo] + [Run(day, out[lo].start, out[hi].end, list(grown.keys), dict(grown.speeds))] + out[hi + 1:]


def whole_day(day: Day, runs: list[Run], ticked: list[str], firms: list[Attorney] | None = None) -> list[Run]:
    """The day as one run of all its pages (Make this day whole), ordered by every firm that ordered any
    of its runs: "1-20 Alex, 21-40 Alex + Dana" is "1-40 Alex + Dana", each at the speed of its first run that
    has one. When no run was ordered by anyone, by the firms ticked on the day (ticked: Job.ticked_keys). firms:
    the table's columns (firms_of), to put the firms in their order, as runs_of does."""
    keys = list(dict.fromkeys(k for r in runs for k in r.keys)) or list(dict.fromkeys(ticked))
    if firms:
        order = {a.key(): n for n, a in enumerate(firms)}
        keys.sort(key=lambda k: order.get(k, len(order)))
    speeds: dict[str, str] = {}
    for r in runs:
        for k, sp in r.speeds.items():
            if k in keys and sp:
                speeds.setdefault(k, sp)
    return [Run(day, 1, day.pages, keys, speeds)]


def store(day: Day, runs: list[Run], firms: list[Attorney], s: Settings | None = None) -> None:
    """Keeps a day's runs on its job: Job.portions (None when the whole day was ordered by one set of firms; a
    day that can't be split keeps none), and the attorneys ticked on it are those who ordered any of its pages
    (an attorney of another day is added to it, ticked). The runs' speeds: the day's own (Job.speeds) for a day
    of one run (a day that can't be split is one), else a run's speed that isn't its firm's on the day is kept in
    its row. A Parties number below the firms that now order the whole day is cleared. The attorney table is
    then the user's (Job.att_touched). With the settings `s`, the day's No. of copies follows the parties now
    ordering (Job.refresh_copies; the window passes them)."""
    job = day.job
    used = list(dict.fromkeys(k for r in runs for k in r.keys))
    if day.splittable:
        whole = len(runs) == 1 and runs[0].keys
        if whole:
            job.speeds.update({k: sp for k, sp in runs[0].speeds.items() if k in runs[0].keys and sp})
        job.portions = None if whole else [
            portion_row(r.end, list(dict.fromkeys(r.keys)) or [ORDERED_BY_NOBODY],
                        {k: sp for k, sp in r.speeds.items() if k in r.keys and sp and sp != job.speeds.get(k)})
            for r in runs]
        if whole and job.parties and job.parties < len(used):
            job.parties = 0
    else:  # (a job of several days is ordered whole: its one run's speeds are the day's own)
        job.speeds.update({k: sp for r in runs for k, sp in r.speeds.items() if k in r.keys and sp})
    have = {a.key() for a in job.case.attorneys}
    for a in job.case.attorneys:
        if not a.is_placeholder() and a.key():
            a.checked = a.key() in used
    # (a firm left out of the day here doesn't order it: it isn't spread back to it, batch.spread_orders)
    job.not_ordered = (job.not_ordered | {a.key() for a in firms if a.key() and a.key() not in used}) - set(used)
    for k in used:
        if k not in have:
            other = next((a for a in firms if a.key() == k), None)
            if other is not None:
                job.case.attorneys.append(replace(other, checked=True))
    job.att_touched = True
    if s is not None:
        job.refresh_copies(s)  # No. of copies follows the parties ordering now


def billed_in(day: Day, run: Run) -> int:
    """The pages billed in a run: on a transcript of several reporters only those Whose pages... bills (the
    user's, by default; Job.day_mask)."""
    mask = day.job.day_mask() if day.splittable else None
    return sum(mask[run.start - 1:run.end]) if mask is not None else run.end - run.start + 1


def sharers(run: Run) -> int:
    """How many ways a run's original is split: the firms that ordered it, or the day's Parties number when that
    is more (Parties shares a day ordered whole). What prices() divides by, so what the table says beside a price."""
    n = len(run.keys)
    if run.day.job.portions is None and run.day.job.parties:
        n = max(n, run.day.job.parties)
    return max(1, n)


@dataclass
class Counts:
    """A run's pages, as the Who ordered window counts them (the user, 2026-10-29: "Pages billed" read as every
    reporter's): the user's own invoice bills (0 when nobody ordered the run, or when Whose pages... bills other
    reporters' pages only: no invoice of the user's is made); the user wrote (None when that
    can't be told: a transcript of several reporters while the user's initials aren't known, or whose first pages
    Whose pages... hasn't said whose they are, or the Pages field typed in); every reporter's; every reporter's a
    firm ordered."""
    your_billed: int
    your_transcribed: int | None
    total_transcribed: int
    total_billed: int


def count_runs(runs: list[Run]) -> dict[int, Counts]:
    """Counts of each run, by id(run). Each day's masks are worked out once: the pages the user's own invoice
    bills (Job.billed_by("me"), as Whose pages... says) and those the user wrote (Job.your_mask)."""
    masks: dict[int, tuple] = {}
    out = {}
    for run in runs:
        day = run.day
        if id(day) not in masks:
            job = day.job
            if day.splittable:
                masks[id(day)] = (job.billed_by("me").day_mask(), job.your_mask(), None)
            else:
                # (a job of several days is ordered whole, its one run as long as the pages its invoice bills
                # (Day.pages): its counts are the job's, every reporter's pages being all the transcripts')
                theirs = [job.your_pages_of(d) for d in job.transcripts()]
                mine = None if job.pages_typed() or not theirs or None in theirs else sum(theirs)
                total = job.invoice_pages() if job.pages_typed() else job.transcript_pages()
                masks[id(day)] = (None, None, (job.billed_by("me").invoice_pages(), mine, total))
        billed, yours, whole = masks[id(day)]
        ordered = bool(run.keys)
        # (Whose pages... bills other reporters only: no invoice of the user's bills these pages, typed in or not;
        # billed_by("me") of a day typed in would still count the typed number)
        mine_billed = "me" in day.job.bill_reporters()
        if day.splittable:
            n = run.end - run.start + 1
            mine = sum(yours[run.start - 1:run.end]) if yours is not None else None
            own = sum(billed[run.start - 1:run.end]) if billed is not None else n
        else:
            own, mine, n = whole
        out[id(run)] = Counts(own if ordered and mine_billed else 0, mine, n, n if ordered else 0)
    return out


@dataclass
class Prices:
    """What the table costs. Runs priced at each speed offered (their firms choose from the invoice): each run's
    price for each firm that ordered it and each set of firms ordering together (their pages, and what each of
    them pays for those pages). Runs whose firms are priced at the speeds they ordered (`ordered`: a speed set,
    a split order that commits to one, or a firm billed one speed for its other pages, its run alone too): what each
    firm pays for the run at its speed, and each set of firms and speeds ordering together. And each firm's invoice (as invoiced: rounded as Settings -> Invoice -> Rounding
    says)."""
    speeds: list[str]
    runs: dict[int, dict[str, Decimal]] = field(default_factory=dict)  # id(run) -> speed -> each pays
    # (firm keys, pages, speed -> what each of those firms pays), fewest firms first
    groups: list[tuple[tuple[str, ...], int, dict[str, Decimal]]] = field(default_factory=list)
    firms: list[tuple[str, dict[str, Decimal]]] = field(default_factory=list)  # (key, speed -> invoice)
    # id(run) -> firm key -> (its speed, what it pays for the run): runs priced at the speeds ordered
    ordered: dict[int, dict[str, tuple[str, Decimal]]] = field(default_factory=dict)
    # ((key, speed) of each firm, pages, key -> what it pays for those pages), fewest firms first
    ordered_groups: list[tuple[tuple[tuple[str, str], ...], int, dict[str, Decimal]]] = field(default_factory=list)
    # (the speed a firm is priced at while none is set for it: the agreement form's, see invoice.default_speed)
    fallback: str = ""
    committed: set[str] = field(default_factory=set)  # the firms whose invoice bills the speeds they ordered
    # the runs (by id) of each set in groups and ordered_groups, by its firm keys (or its (key, speed) pairs): the
    # window counts their pages as count_runs does, yours and every reporter's
    members: dict[tuple, list[int]] = field(default_factory=dict)


def prices(days: list[Day], runs: list[Run], s: Settings) -> Prices:
    """The prices of the runs as they are (see Prices). A firm's share of a run is worked out exactly, and the
    invoices round each firm's total up to the cent (invoice_calc.quote_shares, quote_ordered); with each price a
    page rounded to the cent (Settings.invoice_rounding "page"), a share is that price times its pages, as the
    invoice has it ($6.6125 a page -> $6.61 x 30 = $198.30, not $198.375). Only one set of
    invoices is priced (batch.joint_invoice): on a transcript of several reporters, the pages of the first
    reporter Whose pages... bills (the user, when ticked), not each reporter's set (batch.joint_invoice_sets)."""
    group = [d.job for d in days]
    try:
        case, opts = joint_invoice(group)
        orders = [(d, o) for d in days for o in d.job.invoice_orders()]
    except Exception:  # (a day with nothing to bill yet)
        return Prices([])
    sheet = s.sheet()
    speeds = offered(sheet, s.invoice_speeds, case.get("delivery") or s.agreement_speed())
    # The index is decided date by date, as the invoices do (invoice.firm_invoices): a job of several days
    # isn't indexed on its total when no one of its days has the pages for it; each day on every page of its
    # transcripts, whoever wrote them (invoice.index_pages)
    indexed = index_days(index_pages([o for _, o in orders]), index_mode(opts, s), s.invoice_index_rule,
                         s.invoice_index_threshold)
    dates: dict[int, list[tuple[int, bool]]] = {}  # id(day) -> (pages, indexed) of each date it bills
    for (d, o), x in zip(orders, indexed):
        dates.setdefault(id(d), []).append((o.pages, x))
    email = s.invoice_include_email if opts.email is None else opts.email
    split = s.invoice_index_shared != "each"
    by_page = s.invoice_rounding == "page"

    def amount(q) -> Decimal:
        """A share as shown: exact, or its prices a page rounded to the cent (by_page), as invoiced."""
        return q.per_party if by_page else q.total

    out = Prices([sp.name for sp in speeds], fallback=default_speed(case, s))
    # (the job's split rule once it was billed: batch.Job.split_rule)
    upfront, rule = courthouses.speed_upfront(), courthouses.split_rule(opts.split_rule or s.invoice_split_rule)
    names = {a.key(): a.label() for a in firms_of(group)}

    def shares_of(run: Run, key: str | None = None) -> list[Share]:
        """A run's pages for quote_shares, each share split as many ways as firms ordered the run; for firm
        `key`, as quote_ordered prices them: at its speed, with the other firms' (unset: the form's)."""
        n = sharers(run)
        own = dates.get(id(run.day), [])
        speed, others = "", ()
        if key is not None:
            speed = run.speed(key) or out.fallback
            others = tuple((names.get(o, o), run.speed(o) or out.fallback) for o in run.keys if o != key)
        if not run.day.splittable and len(own) > 1:  # (ordered whole: a share per date, each indexed or not)
            return [Share(p, n, x, speed, others) for p, x in own]
        return [Share(billed_in(run.day, run), n, any(x for _, x in own), speed, others)]

    # The firms billed one speed for all their pages, as invoice.firm_invoices has it: a speed set on any of them,
    # or a run shared with another firm where firms commit (the rest of their pages too, alone or not)
    commit = {k for r in runs for k in r.keys if r.speed(k) or (upfront and len(r.keys) > 1)}

    def at_speeds(run: Run) -> bool:
        """The run's firms are priced at the speeds they ordered (as invoice.firm_invoices bills them): a speed
        is set for one of them, they ordered it together and must commit to theirs, or each is billed one speed
        for its other pages anyway (a firm alone on this run offered no choice of speeds on its invoice)."""
        return any(run.speed(k) for k in run.keys) or (len(run.keys) > 1 and upfront) \
            or all(k in commit for k in run.keys)

    for r in runs:
        if not r.keys:
            continue
        if at_speeds(r):
            try:
                out.ordered[id(r)] = {k: (r.speed(k) or out.fallback,
                                          amount(quote_ordered(shares_of(r, k), s.sheet(), rule, email, split,
                                                               by_page=by_page)))
                                      for k in r.keys}
            except ValueError:  # (a speed the sheet lacks, or too many speeds: the window says why)
                pass
        else:
            out.runs[id(r)] = {sp.name: amount(quote_shares(shares_of(r), sp, email, split, by_page=by_page))
                               for sp in speeds}
    together: dict[tuple[str, ...], list[Run]] = {}
    at: dict[tuple[tuple[str, str], ...], list[Run]] = {}
    order = {a.key(): i for i, a in enumerate(firms_of(group))}
    for r in runs:
        if not r.keys:
            continue
        keys = tuple(sorted(r.keys, key=lambda k: order.get(k, len(order))))  # (whatever order each day's has)
        if id(r) in out.ordered:
            at.setdefault(tuple((k, out.ordered[id(r)][k][0]) for k in keys), []).append(r)
        elif id(r) in out.runs:
            together.setdefault(keys, []).append(r)
    out.members = {keys: [id(r) for r in rs] for keys, rs in (*together.items(), *at.items())}
    for keys, rs in together.items():
        shares = [x for r in rs for x in shares_of(r)]
        out.groups.append((keys, sum(x.pages for x in shares),
                           {sp.name: amount(quote_shares(shares, sp, email, split, by_page=by_page))
                            for sp in speeds}))
    out.groups.sort(key=lambda g: (len(g[0]), g[0]))
    for pairs, rs in at.items():
        pages = sum(billed_in(r.day, r) for r in rs)
        out.ordered_groups.append((pairs, pages, {k: sum((out.ordered[id(r)][k][1] for r in rs), Decimal(0))
                                                  for k, _ in pairs}))
    out.ordered_groups.sort(key=lambda g: (len(g[0]), g[0]))
    try:
        for f in firm_invoices(case, s, opts):
            if f.atty is not None:
                out.firms.append((f.atty.key(), {q.speed: q.per_party for q in f.quotes}))
                if any(q.ordered for q in f.quotes):
                    out.committed.add(f.atty.key())
    except Exception:  # (nothing to bill, or a speed the sheet lacks: no firm totals to show)
        pass
    return out
