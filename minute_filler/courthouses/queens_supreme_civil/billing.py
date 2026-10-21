"""How Queens Supreme Court, Civil Term may bill pages that firms ordered together at different speeds (the
courthouse's split rules, Courthouse.split_rules): two ways, the user choosing one in Settings -> Invoice ->
"Split invoices" (Settings.invoice_split_rule).

The reporter bills ONE original of a page, however many firms ordered it, and a copy (and an e-mailed copy, and
an index) for each firm, at the firm's own speed. The two ways differ only in how the one original is divided
when the firms ordered the page at different speeds. The judge's index (billed once, like the original) is
divided the same way. When every firm ordered the same speed, both are the usual split: each pays the original
÷ the number of firms.

Make-Whole Split (MAKE_WHOLE, the default): the original is billed at the fastest speed ordered on the page.

1. Each firm that did NOT order the fastest speed pays what it would have paid had every firm on the page
   ordered its speed: that speed's original ÷ the number of firms (never more than the fastest speed's own
   price ÷ the number of firms: a sheet can price an index lower at a faster speed).
2. The firms that ordered the fastest speed split what is left, equally.

So a slower firm is never charged for speed it didn't ask for, the extra cost of the faster original falls only
on the firms that asked for it, and the parts add up to the one original at the fastest speed.

Same-Speed Split (SAME_SPEED): every firm pays what it would have paid had every firm on the page ordered its
speed, the fastest firms too: its speed's original ÷ the number of firms (a slower firm's never more than the
fastest speed's, as above, so a slower firm pays the same under both ways). Each firm's part is priced at its own
speed alone, so on mixed-speed pages the parts add up to the average of the firms' prices (each firm's own, or the
fastest's when that is lower), not the fastest speed's price.

Example, Sample Rates, 10 pages, no index: one firm orders Daily (original $6.50, copy and e-mailed copy $1.25
each), one Immediate (original $7.60, copy and e-mailed copy $1.45 each). The Daily firm pays $6.50 ÷ 2 = $3.25 a
page of the original under both: with its own copies $5.75 a page, $57.50. Make-Whole: the original is billed at
Immediate, $7.60 a page, and the Immediate firm pays the rest, $7.60 − $3.25 = $4.35; with its own copies $7.25
a page, $72.50; together $130.00, the whole bill (one original at Immediate, $76.00, and each firm's own copies,
$25.00 and $29.00). Same-Speed: the Immediate firm pays $7.60 ÷ 2 = $3.80; with its own copies $6.70 a page,
$67.00; together $124.50.

Both come from the reporter's own workbooks (research/Daily_Immediate_Rate_Calculator_v10.xlsx, and
"Transcript_Billing_Calculator - comparer.xlsx", which prices a job both ways side by side; git-ignored with the
questions still open, research/OPEN_QUESTIONS.md). They work for any number of speeds, but how three or more
speeds on the same pages should be billed isn't settled (the first workbook marks it open: a "layered" rule gives
other answers from three speeds up), so the profile allows two for now (speeds_together).

A third way is a subclass of SplitRule with a key of its own, added to RULES.
"""
from __future__ import annotations

from fractions import Fraction

from ...invoice_calc import money_exact
from ..base import Part, Party, SplitRule


def _all(n: int) -> str:
    """'both firms', 'all 3 firms'."""
    return "both firms" if n == 2 else f"all {n} firms"


def _fastest(parties: list[Party]) -> Party:
    """The first firm at the fastest speed ordered (the speed a charge is billed at, and its price there)."""
    top = max(p.rank for p in parties)
    return next(p for p in parties if p.rank == top)


def _capped(p: Party, billed: Party) -> Fraction:
    """The price a slower firm's share is worked out from: its own speed's, but never above the price at the
    fastest speed (a sheet can price the faster speed's index lower: the fastest firm paid less than nothing
    then)."""
    return min(p.rate, billed.rate)


def _as_if_all(mine: Party, billed: Party, n: int) -> Part:
    """A slower firm's part, the same under both ways: as if every firm had ordered its speed."""
    pays = _capped(mine, billed) / n
    if mine.rate > billed.rate:
        how = (f"This firm ordered {mine.speed}, but {billed.speed}, the fastest ordered, costs less: "
               f"{money_exact(billed.rate)} ÷ {n} = {money_exact(pays)} a page")
    else:
        how = (f"This firm ordered {mine.speed}, so it pays as if {_all(n)} had ordered {mine.speed}: "
               f"{money_exact(mine.rate)} ÷ {n} = {money_exact(pays)} a page")
    return Part(pays, ((how, pays),))


def _usual(mine: Party, n: int) -> Part:
    """Every firm at one speed: the price ÷ the number of firms."""
    pays = mine.rate / n
    return Part(pays, ((f"{money_exact(mine.rate)} ÷ {n} = {money_exact(pays)} a page", pays),))


class MakeWholeSplit(SplitRule):
    """The original billed at the fastest speed; each slower firm pays as if every firm had ordered its speed, and
    the fastest firms split the rest (see the module docstring)."""
    key = "make_whole"
    label = "Make-Whole Split: one original at the fastest speed ordered"
    tip = ("When firms order the same pages at different speeds, one original is billed, at the fastest speed.\n"
           "Each slower firm pays its share as if every firm had ordered its speed, and the firms at the fastest\n"
           "speed pay the rest.\n"
           "10 pages, Daily and Immediate: the Daily firm pays $6.50 ÷ 2 = $3.25 a page of the original, the\n"
           "Immediate firm the rest of $7.60, $4.35.")
    summary = ("one original, billed at the fastest speed ordered on them; each slower firm pays its share as if "
               "every firm had ordered its speed, and the fastest pay the rest")
    note = ("Some pages were ordered together with a firm at another speed: one original of them is billed, at the "
            "fastest speed ordered on them, and divided between the firms as each row says; each firm pays for its "
            "own copies at its own speed.")
    adds_up = ("On the pages ordered at different speeds, the firms' parts of each original (and of the judge's "
               "index) add up to one, billed at the fastest speed ordered on them.")
    invoice_note = ("Pages ordered together at different speeds: the original is billed once, at the faster speed; "
                    "you pay your share at the speed you ordered.")

    def split(self, parties: list[Party], me: int) -> Part:
        n = len(parties)
        billed = _fastest(parties)
        mine = parties[me]
        if mine.rank != billed.rank:  # a slower firm: its own speed's share
            return _as_if_all(mine, billed, n)
        slower = [p for p in parties if p.rank != billed.rank]
        if not slower:  # (every firm at one speed: the usual split)
            return _usual(mine, n)
        steps = []
        for p in slower:
            theirs = _capped(p, billed) / n
            steps.append((f"{p.name} ordered {p.speed} and pays {money_exact(_capped(p, billed))} ÷ {n} = "
                          f"{money_exact(theirs)} a page of it", theirs))
        less = " − ".join(money_exact(_capped(p, billed) / n) for p in slower)
        k = n - len(slower)  # the firms at the fastest speed, this one among them
        pays = (mine.rate - sum((_capped(p, billed) / n for p in slower), Fraction(0))) / k
        if k == 1:
            steps.append((f"This firm pays the rest: {money_exact(mine.rate)} − {less} = {money_exact(pays)} a page",
                          pays))
        else:
            steps.append((f"The {k} firms at {mine.speed} split the rest: ({money_exact(mine.rate)} − {less}) ÷ {k} "
                          f"= {money_exact(pays)} a page", pays))
        return Part(pays, tuple(steps))

    def billed(self, speed: str, rate: Fraction) -> str:
        return f"Billed once, at {speed} ({money_exact(rate)} a page)"

    def your_part(self, speed: str) -> str:
        return f"your part, billed at {speed}"

    def run_note(self, speed: str) -> str:
        return f"one original, at {speed}"


class SameSpeedSplit(SplitRule):
    """Every firm, the fastest too, pays as if every firm had ordered its speed (see the module docstring)."""
    key = "same_speed"
    label = "Same-Speed Split: each firm pays as if all had ordered its speed"
    tip = ("When firms order the same pages at different speeds, each firm, the fastest too, pays its share of the\n"
           "original as if every firm had ordered its speed (a slower firm pays the same as under Make-Whole).\n"
           "10 pages, Daily and Immediate: the Daily firm pays $6.50 ÷ 2 = $3.25 a page of the original, the\n"
           "Immediate firm $7.60 ÷ 2 = $3.80.")
    summary = "each firm pays its share of the original as if every firm had ordered its speed"
    note = ("Some pages were ordered together with a firm at another speed: each firm pays its share of their "
            "original as if every firm had ordered its speed, as each row says, and its own copies at its own speed.")
    adds_up = ("On the pages ordered at different speeds, each firm's part of the original (and of the judge's "
               "index) is priced at the speed it ordered, or at the fastest's price when that is lower.")
    invoice_note = ("Pages ordered together at different speeds: you pay your share of the original as if every "
                    "firm had ordered the speed you ordered.")

    def split(self, parties: list[Party], me: int) -> Part:
        n = len(parties)
        billed = _fastest(parties)
        mine = parties[me]
        if mine.rank != billed.rank:
            return _as_if_all(mine, billed, n)
        if all(p.rank == billed.rank for p in parties):  # (every firm at one speed: the usual split)
            return _usual(mine, n)
        pays = mine.rate / n
        return Part(pays, ((f"This firm ordered {mine.speed}, so it pays as if {_all(n)} had ordered {mine.speed}: "
                            f"{money_exact(mine.rate)} ÷ {n} = {money_exact(pays)} a page", pays),))

    def billed(self, speed: str, rate: Fraction) -> str:
        return f"At {speed}, the fastest speed ordered, it is {money_exact(rate)} a page"

    def your_part(self, speed: str) -> str:
        return "your part, at the speed you ordered"

    def run_note(self, speed: str) -> str:
        return "each as if all had ordered its speed"


MAKE_WHOLE = MakeWholeSplit()
SAME_SPEED = SameSpeedSplit()
RULES = (MAKE_WHOLE, SAME_SPEED)  # (Courthouse.split_rules: the default first)
