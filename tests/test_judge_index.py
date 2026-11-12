"""The judge's index left off the invoices (Settings.invoice_judge_index "off"): some reporters bill the firms their
own index but not the judge's. Every way an invoice is priced (quote, quote_shares, quote_ordered, quotes_for,
firm_invoices, the Excerpts window's prices) then has no "Judge's index" line, and the firms' own "Index" lines are
as they were; each firm pays exactly its share of the judge's index less. Also the words that name what the firms
split ("the original" alone), the math (no row of it, "All the firms together" still adding up, the split rule's
words without it), the Invoice card's Includes line, Peripherals... and Generate's index question, invoices in
another reporter's name, a settings file with a value it doesn't know, and the spreadsheet template's own switch.
By default ("split") nothing changes. All names and numbers are made up; prices are from the bundled "Sample Rates"
sheet (Regular: original $4.30, copy, e-mailed copy and index $1.00 a page; Expedite $5.40 and $1.10; Daily $6.50
and $1.25; Immediate $7.60 and $1.45)."""
import json
import os
import time
from decimal import Decimal
from fractions import Fraction

import pytest

from minute_filler import courthouses
from minute_filler.courthouses.queens_supreme_civil.billing import MAKE_WHOLE, SAME_SPEED
from minute_filler.invoice import (DayOrder, InvoiceOpts, Portion, firm_invoices, index_charged, job_quotes,
                                   judge_billed, shared_words, text_values)
from minute_filler.invoice_calc import Share, extra_rate, quote, quote_ordered, quote_shares, quotes_for
from minute_filler.invoice_math import explain, together
from minute_filler.models import Attorney
from minute_filler.settings import JUDGE_INDEX, Settings

from helpers import ROE, make_case, pat_settings, transcript_pdf

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

JUDGE = "Judge's index"


@pytest.fixture
def s(tmp_path):
    s = pat_settings()
    s.output_dir = str(tmp_path / "out")
    s.records_dir = str(tmp_path / "records")
    s.invoice_speeds = ["Regular"]
    s.save_math = "off"
    return s


@pytest.fixture
def sheet():
    return pat_settings().sheet()


def alex():
    return Attorney(name="Alex B. Counsel", firm="Counsel & Counsel", checked=True)


def dana():
    return Attorney(name="Dana Smith", firm="Smith Law", checked=True)


A, B = alex().key(), dana().key()


def labels(q):
    return [l.label for l in q.lines]


def amount(q, label):
    return next(l.amount for l in q.lines if l.label == label)


def lines_of(q):
    """Every line but the judge's index, as compared: its label, rate, qty, amount, pages and parts."""
    return [(l.label, l.rate, l.qty, l.amount, l.pages, l.shared, l.parts) for l in q.lines if l.charge != JUDGE]


def both(s, make):
    """What make() gives with the judge's index billed, then left off (the setting back as it was after)."""
    before = s.invoice_judge_index
    try:
        s.invoice_judge_index = "split"
        on = make()
        s.invoice_judge_index = "off"
        return on, make()
    finally:
        s.invoice_judge_index = before


def by_name(firms):
    return {f.atty.name: f for f in firms}


# ------------------------------------------------------------------ the setting
def test_the_setting_is_billed_split_by_default_and_a_value_it_doesnt_know_is_reset():
    s = Settings()
    assert s.invoice_judge_index == "split" and set(JUDGE_INDEX) == {"split", "off"} and judge_billed(s)
    for saved, loaded in (("off", "off"), ("split", "split"), ("none", "split"), ("", "split"), (0, "split"),
                          (None, "split"), (["off"], "split")):
        data = {"settings_version": Settings.settings_version, "invoice_judge_index": saved}
        assert Settings.from_dict(data).invoice_judge_index == loaded, saved
    # kept through a save and a load, and a settings file from before it was added bills it, as before
    s.invoice_judge_index = "off"
    s.save(force=True)
    assert Settings.load().invoice_judge_index == "off" and not judge_billed(Settings.load())
    s.path.write_text(json.dumps({"settings_version": 3}), encoding="utf-8")
    assert Settings.load().invoice_judge_index == "split"


def test_invoices_in_another_reporters_name_follow_the_setting(s):
    """as_reporter copies the settings: the invoices made in another reporter's name (their pages) leave the judge's
    index off too, and the user's own settings aren't changed by it."""
    s.invoice_judge_index = "off"
    theirs = s.as_reporter("ds")
    assert theirs.invoice_judge_index == "off" and theirs is not s and not judge_billed(theirs)
    case = make_case({**ROE, "delivery": "Regular"}, [alex(), dana()])
    opts = InvoiceOpts(60, 2, days=[("6/3/2026", 60)], reporter="ds")
    assert labels(job_quotes(case, theirs, opts)[0]) == ["Original", "Copy", "E-mailed copy", "Index"]
    opts.orders = [DayOrder("6/3/2026", 60, [Portion(60, [A, B])])]
    firms = firm_invoices(case, s, opts)
    assert [f.opts.reporter for f in firms] == ["ds", "ds"]
    assert all(JUDGE not in labels(q) for f in firms for q in f.quotes)
    s.invoice_judge_index = "split"  # (and billed again when the user's settings bill it)
    assert JUDGE in labels(job_quotes(case, s.as_reporter("ds"), opts)[0])


# ------------------------------------------------------------------ the arithmetic
@pytest.mark.parametrize("shared", ["each", "split"])
def test_a_whole_invoice_has_no_judges_index_and_the_same_index(sheet, shared):
    """quote: 60 pages, 2 parties. The index lines are those of the judge's index billed; the total is the judge's
    index less (60 x $1.00 at Regular, 60 x $1.10 at Expedite), whether each party pays its own index or one is
    split."""
    for sp in sheet.speeds:
        on, off = quote(60, sp, 2, index_shared=shared), quote(60, sp, 2, index_shared=shared, judge_index=False)
        assert JUDGE in labels(on) and JUDGE not in labels(off) and "Index" in labels(off)
        assert lines_of(off) == lines_of(on)
        assert on.total - off.total == amount(on, JUDGE) == 60 * extra_rate(sp, "index") > 0
    off = quote(60, sheet.find("Regular"), 2, index_shared=shared, judge_index=False)
    # each party: 4.30 / 2 + 1 + 1 + its own index 1 (or half of one): $5.15 or $4.65 a page
    assert off.prices == [(Fraction("5.15") if shared == "each" else Fraction("4.65"), 60)]
    assert off.per_party == (Decimal("309.00") if shared == "each" else Decimal("279.00"))
    # a day too short for an index: nothing changes, with the judge's index billed or not
    sp = sheet.find("Regular")
    assert lines_of(quote(30, sp, 2, judge_index=False)) == lines_of(quote(30, sp, 2)) and \
        labels(quote(30, sp, 2)) == ["Original", "Copy", "E-mailed copy"]


def test_the_price_a_page_rounding_without_the_judges_index(sheet):
    """Settings -> Invoices -> Rounding "the price a page": the judge's index is out of the price a page too. 3 parties
    at Immediate, 100 pages: $7.60 / 3 + $1.45 x 3 = $6.8833... a page, rounded to $6.88, x 100 = $688.00 (exactly:
    $688.333..., rounded up to $688.34). With it: + $1.45 / 3, $7.3666... -> $7.37 x 100 = $737.00."""
    sp = sheet.find("Immediate")
    off = quote(100, sp, 3, by_page=True, judge_index=False)
    assert off.prices == [(Fraction("7.60") / 3 + Fraction("4.35"), 100)] and off.page_rounded
    assert off.per_party == Decimal("688.00")
    assert quote(100, sp, 3, judge_index=False).per_party == Decimal("688.34")
    assert quote(100, sp, 3, by_page=True).per_party == Decimal("737.00")
    # a stretch of days without an index and one with: two prices a page, each without the judge's index
    q = quote([30, 60], sheet.find("Regular"), 2, rule="each", by_page=True, judge_index=False)
    assert q.prices == [(Fraction("4.15"), 30), (Fraction("5.15"), 60)] and q.per_party == Decimal("433.50")


def test_the_excerpt_example_each_firm_pays_its_judges_share_less(sheet):
    """100 pages: A ordered them all, B a 10-page excerpt (the user's example, 2026-10-08). With the judge's index
    A pays for 95 pages of it, B for 5; without it, A pays exactly 95 x the index price less and B 5 x, and their own
    indexes (A 100 pages, B 10) are as they were."""
    for name, rate in (("Regular", Fraction("1.00")), ("Expedite", Fraction("1.10"))):
        sp = sheet.find(name)
        a_shares, b_shares = [Share(90, 1, True), Share(10, 2, True)], [Share(10, 2, True)]
        for split in (False, True):
            a, b = quote_shares(a_shares, sp, index_split=split), quote_shares(b_shares, sp, index_split=split)
            a_off = quote_shares(a_shares, sp, index_split=split, judge_index=False)
            b_off = quote_shares(b_shares, sp, index_split=split, judge_index=False)
            assert (Fraction(amount(a, JUDGE)), Fraction(amount(b, JUDGE))) == (95 * rate, 5 * rate)
            assert JUDGE not in labels(a_off) + labels(b_off)
            assert lines_of(a_off) == lines_of(a) and lines_of(b_off) == lines_of(b)
            assert (a.due - a_off.due, b.due - b_off.due) == (95 * rate, 5 * rate)
            assert Fraction(a.per_party - a_off.per_party) == 95 * rate
            assert Fraction(b.per_party - b_off.per_party) == 5 * rate
    sp = sheet.find("Regular")
    a_off = quote_shares([Share(90, 1, True), Share(10, 2, True)], sp, judge_index=False)
    assert (amount(a_off, "Index"), a_off.per_party) == (Decimal("100.00"), Decimal("708.50"))  # 90 x 7.30 + 10 x 5.15
    assert a_off.prices == [(Fraction("7.30"), 90), (Fraction("5.15"), 10)]


def test_two_speeds_on_the_same_pages(sheet):
    """10 pages with an index, A at Daily and B at Immediate (Make-Whole Split: one judge's index at Immediate, $1.45
    a page; A pays $1.25 / 2 = $0.625 a page of it, B the rest, $0.825). Without it A pays $6.25 less, B $8.25, their
    own indexes at their own speeds as before; Same-Speed Split likewise, at each firm's own speed."""
    def priced(speed, other, rule, judge=True):
        return quote_ordered([Share(10, 2, True, speed, (other,))], sheet, rule, judge_index=judge)

    for rule, a_less, b_less in ((MAKE_WHOLE, "6.25", "8.25"), (SAME_SPEED, "6.25", "7.25")):
        a, b = priced("Daily", ("Smith Law", "Immediate"), rule), priced("Immediate", ("Counsel & Counsel", "Daily"), rule)
        a_off = priced("Daily", ("Smith Law", "Immediate"), rule, False)
        b_off = priced("Immediate", ("Counsel & Counsel", "Daily"), rule, False)
        assert JUDGE in labels(a) and JUDGE not in labels(a_off) + labels(b_off)
        assert lines_of(a_off) == lines_of(a) and lines_of(b_off) == lines_of(b)
        assert (a.due - a_off.due, b.due - b_off.due) == (Fraction(a_less), Fraction(b_less))
        assert a_off.mixed and a_off.rule is rule  # (the original is still billed once, divided by the rule)
    # a firm that ordered Daily on one day and Regular on another: no judge's index at either speed
    q = quote_ordered([Share(60, 1, True, "Daily"), Share(60, 1, True, "Regular")], sheet, judge_index=False)
    assert labels(q) == [f"{c} ({sp})" for sp in ("Daily", "Regular")
                         for c in ("Original", "Copy", "E-mailed copy", "Index")]


def test_quotes_for_leaves_it_off_on_every_speed(s):
    s.invoice_speeds = ["Regular", "Expedited", "Daily"]
    got = quotes_for([10], 1, s.sheet(), s, "Regular", email=False, index="on", judge_index=False)
    assert [q.speed for q in got] == ["Regular", "Expedite", "Daily"]
    assert all(labels(q) == ["Original", "Copy", "Index"] for q in got)
    assert labels(quotes_for([10], 1, s.sheet(), s, "Regular", email=False, index="on")[0]) == \
        ["Original", "Copy", "Index", JUDGE]


# ------------------------------------------------------------------ the invoices
def test_the_invoices_without_who_ordered_which_pages(s):
    """Two parties, 60 pages, every party ordering every page (no Excerpts): each pays $339.00 with the judge's
    index, $309.00 without. A day of 30 pages (no index) is the same either way."""
    case = make_case({**ROE, "delivery": "Regular"}, [alex(), dana()])
    on, off = both(s, lambda: firm_invoices(case, s, InvoiceOpts(60, 2, days=[("6/3/2026", 60)])))
    assert [f.quotes[0].per_party for f in on] == [Decimal("339.00")] * 2
    assert [f.quotes[0].per_party for f in off] == [Decimal("309.00")] * 2
    assert all(JUDGE not in labels(q) and index_charged([q]) for f in off for q in f.quotes)
    assert off[0].index_note == on[0].index_note == "Index: 60 total pages, 50 or more."
    on, off = both(s, lambda: firm_invoices(case, s, InvoiceOpts(30, 2, days=[("6/3/2026", 30)])))
    assert [f.quotes[0].per_party for f in on] == [f.quotes[0].per_party for f in off]


def test_firm_invoices_of_the_excerpt_example(s):
    """A ordered all 100 pages, B pages 91-100: without the judge's index A's invoice is $95.00 less ($803.50 ->
    $708.50), B's $5.00 ($56.50 -> $51.50); each still pays its own index of the pages it ordered."""
    case = make_case({**ROE, "delivery": "Regular"}, [alex(), dana()])
    opts = InvoiceOpts(100, 2, days=[("6/3/2026", 100)], orders=[
        DayOrder("6/3/2026", 100, [Portion(90, [A]), Portion(10, [A, B])])])
    on, off = (by_name(x) for x in both(s, lambda: firm_invoices(case, s, opts)))
    assert [on[n].quotes[0].per_party for n in on] == [Decimal("803.50"), Decimal("56.50")]
    assert [off[n].quotes[0].per_party for n in off] == [Decimal("708.50"), Decimal("51.50")]
    for n in on:
        assert lines_of(off[n].quotes[0]) == lines_of(on[n].quotes[0])
        assert JUDGE not in labels(off[n].quotes[0])
    assert amount(off["Alex B. Counsel"].quotes[0], "Index") == Decimal("100.00")
    assert amount(off["Dana Smith"].quotes[0], "Index") == Decimal("10.00")


def test_a_joint_invoice_of_several_days(s):
    """Two days on one invoice. Every party ordering every page: the index of both days, no judge's index. With
    Excerpts (rule "each": only the 60-page day gets an index), A alone on day 1's 30 pages and both on day 2's 60:
    each pays its own index of day 2, and $30.00 less without the judge's index (half of its 60 pages each)."""
    case = make_case({**ROE, "delivery": "Regular", "dates": "6/3/2026, 6/4/2026"}, [alex(), dana()])
    days = [("6/3/2026", 30), ("6/4/2026", 60)]
    on, off = both(s, lambda: job_quotes(case, s, InvoiceOpts(90, 1, days=days))[0])
    assert lines_of(off) == lines_of(on) and JUDGE not in labels(off) and amount(off, "Index") == Decimal("90.00")
    assert on.total - off.total == Decimal("90.00")
    s.invoice_index_rule = "each"
    opts = InvoiceOpts(90, 2, days=days, orders=[DayOrder("6/3/2026", 30, [Portion(30, [A])]),
                                                 DayOrder("6/4/2026", 60, [Portion(60, [A, B])])])
    on, off = (by_name(x) for x in both(s, lambda: firm_invoices(case, s, opts)))
    for n in on:
        q_on, q_off = on[n].quotes[0], off[n].quotes[0]
        assert lines_of(q_off) == lines_of(q_on) and JUDGE not in labels(q_off)
        assert amount(q_off, "Index") == Decimal("60.00") and q_on.per_party - q_off.per_party == Decimal("30.00")
    assert off["Alex B. Counsel"].opts.days == days and off["Dana Smith"].opts.days == [("6/4/2026", 60)]


def mixed(s):
    """60 pages (an index) ordered by A at Daily and B at Immediate: Queens bills each its own speed."""
    case = make_case({**ROE, "delivery": "Daily"}, [alex(), dana()])
    opts = InvoiceOpts(60, 2, days=[("6/3/2026", 60)], orders=[
        DayOrder("6/3/2026", 60, [Portion(60, [A, B], speeds=((A, "Daily"), (B, "Immediate")))])])
    return firm_invoices(case, s, opts)


def test_firm_invoices_at_two_speeds_on_the_same_pages(s):
    """Make-Whole Split: one judge's index at Immediate ($1.45 x 60 = $87.00): A's part $37.50, B's $49.50; without it
    A pays $420.00 (an original part of $195.00 and its own copy, e-mailed copy and index at Daily) and B $522.00."""
    on, off = (by_name(x) for x in both(s, lambda: mixed(s)))
    assert [on[n].quotes[0].per_party for n in on] == [Decimal("457.50"), Decimal("571.50")]
    assert [off[n].quotes[0].per_party for n in off] == [Decimal("420.00"), Decimal("522.00")]
    for n in on:
        assert lines_of(off[n].quotes[0]) == lines_of(on[n].quotes[0]) and off[n].quotes[0].mixed


# ------------------------------------------------------------------ the math
def excerpt_math(s):
    """The excerpt example's invoices (A all 100 pages, B pages 91-100) and their math in both layouts."""
    case = make_case({**ROE, "delivery": "Regular"}, [alex(), dana()])
    opts = InvoiceOpts(100, 2, days=[("6/3/2026", 100)], orders=[
        DayOrder("6/3/2026", 100, [Portion(90, [A]), Portion(10, [A, B])])])
    made = [(f, f"2026-00{i + 10}") for i, f in enumerate(firm_invoices(case, s, opts))]
    return made, [explain(made, layout) for layout in ("invoice", "firms")]


def test_the_math_has_no_judges_index_and_the_firms_together_still_add_up(s):
    """No row of the judge's index in either layout; each firm's own index as before; the firms together pay what
    the work costs ($708.50 + $51.50: one original of 100 pages, 110 pages of copies, e-mailed copies and indexes)."""
    s.invoice_judge_index = "off"
    made, maths = excerpt_math(s)
    for html, plain in maths:
        assert "judge" not in html.lower() and "judge" not in plain.lower()
        assert "Index: 100 pages × $1.00 = $100.00 (each firm pays for its own)" in plain
        assert "All the firms together" in html
    assert together(made) == ["As ordered (Regular): the 2 firms together pay $760.00 for work that costs $760.00"]
    s.invoice_judge_index = "split"  # (with it: $95.00 + $5.00 more, and its row)
    made, maths = excerpt_math(s)
    assert together(made) == ["As ordered (Regular): the 2 firms together pay $860.00 for work that costs $860.00"]
    assert all("Judge's index" in plain for _, plain in maths)


@pytest.mark.usefixtures("split_orders_choose")
def test_the_math_of_firms_choosing_a_speed_from_their_invoices(s):
    """Where firms sharing pages choose a speed from their invoices (quote_shares), the same: no judge's index, and
    the firms together pay what the work costs, at each speed offered."""
    s.invoice_judge_index = "off"
    s.invoice_speeds = ["Regular", "Expedited"]
    made, maths = excerpt_math(s)
    assert all(not q.ordered and JUDGE not in labels(q) for f, _ in made for q in f.quotes)
    assert all("judge" not in html.lower() + plain.lower() for html, plain in maths)
    # Expedite: 100 x 5.40 + 3 x 110 x 1.10 = $903.00
    assert together(made) == ["Regular: the 2 firms together pay $760.00 for work that costs $760.00",
                              "Expedite: the 2 firms together pay $903.00 for work that costs $903.00"]


def test_the_math_of_two_speeds_says_nothing_of_a_judges_index_not_billed(s):
    """What the firms' parts add up to, in the split rule's words, without "(and of the judge's index)"; with it,
    as before. The firms together pay what the work costs: one original at Immediate and each firm's own."""
    s.invoice_judge_index = "off"
    made = [(f, "") for f in mixed(s)]
    said = together(made)
    assert said[0] == "As ordered (Daily, Immediate): the 2 firms together pay $942.00 for work that costs $942.00"
    assert said[1:] == [MAKE_WHOLE.adds_up_words(False)] and MAKE_WHOLE.adds_up not in said
    assert MAKE_WHOLE.adds_up_words(False) == ("On the pages ordered at different speeds, the firms' parts of each "
                                               "original add up to one, billed at the fastest speed ordered on them.")
    assert SAME_SPEED.adds_up_words(False) == ("On the pages ordered at different speeds, each firm's part of the "
                                               "original is priced at the speed it ordered, or at the fastest's "
                                               "price when that is lower.")
    html, plain = explain(made)
    assert "judge" not in html.lower() and "judge" not in plain.lower()
    s.invoice_judge_index = "split"
    made = [(f, "") for f in mixed(s)]
    assert MAKE_WHOLE.adds_up in together(made) and MAKE_WHOLE.adds_up_words(True) == MAKE_WHOLE.adds_up
    assert "(and of the judge's index)" in MAKE_WHOLE.adds_up
    # without an index at all, the words are as they always were (the setting changes nothing there)
    s.invoice_include_index = False
    assert MAKE_WHOLE.adds_up in together([(f, "") for f in mixed(s)])
    # ...but made with the judge's index not billed, no index charged either, they don't name it (the review of
    # 2.18: the lines alone were read, and "no index" was taken for a judge's index billed)
    s.invoice_judge_index = "off"
    made = [(f, "") for f in mixed(s)]
    assert not any(l.charge.endswith("ndex") for f, _ in made for q in f.quotes for l in q.lines if l.amount > 0)
    assert all(not q.judge_index for f, _ in made for q in f.quotes)
    assert MAKE_WHOLE.adds_up not in together(made) and MAKE_WHOLE.adds_up_words(False) in together(made)


def test_a_rule_without_such_words_keeps_its_own():
    class Evenly(type(MAKE_WHOLE)):
        adds_up = "They add up to one."

    assert Evenly().adds_up_words(False) == "They add up to one."


# ------------------------------------------------------------------ the Excerpts window's prices
@pytest.mark.parametrize("choose", [False, True], ids=["committed", "chosen_from_the_invoice"])
def test_the_excerpts_prices_match_the_invoices(tmp_path, s, request, choose):
    """prices(): what each run costs each firm adds up to its invoice, which leaves the judge's index off as the
    invoices do: A $657.00 for its 90 pages alone (7.30 a page) and $51.50 for the 10 shared, B $51.50. Priced at
    the speeds the firms committed to (Queens), or at each speed offered where firms choose from their invoices."""
    from minute_filler.batch import group, read_docs
    from minute_filler.excerpts import Run, case_days, firms_of, prices, runs_of, store
    if choose:
        request.getfixturevalue("split_orders_choose")
    pdf = transcript_pdf(tmp_path / "Day 1.pdf", 100)
    docs, errors = read_docs([str(pdf)], s)
    assert not errors
    jobs = group(docs, s)
    jobs[0].case.attorneys = [alex(), dana()]
    jobs[0].case.set("delivery", "Regular")
    days, firms = case_days(jobs), firms_of(jobs)
    a, b = (x.key() for x in firms)
    store(days[0], [Run(days[0], 1, 90, [a]), Run(days[0], 91, 100, [a, b])], firms)

    def priced():
        runs = runs_of(days[0], firms)
        p = prices(days, runs, s)
        assert bool(p.runs) == choose and bool(p.ordered) != choose  # (priced the way meant)
        cells: dict = {}
        for r in runs:
            for k, (_, pays) in p.ordered.get(id(r), {}).items():
                cells[k] = cells.get(k, Decimal(0)) + pays
            for sp, pays in p.runs.get(id(r), {}).items():
                for k in r.keys:
                    cells[k] = cells.get(k, Decimal(0)) + pays
        sets = {keys: each["Regular"] for keys, _, each in p.groups}
        sets.update({tuple(k for k, _ in pairs): each for pairs, _, each in p.ordered_groups})
        return cells, dict(p.firms), sets

    (cells_on, firms_on, sets_on), (cells_off, firms_off, sets_off) = both(s, priced)
    assert firms_off == {a: {"Regular": Decimal("708.50")}, b: {"Regular": Decimal("51.50")}}
    assert firms_on == {a: {"Regular": Decimal("803.50")}, b: {"Regular": Decimal("56.50")}}
    assert cells_off == {k: v["Regular"] for k, v in firms_off.items()}
    assert cells_on == {k: v["Regular"] for k, v in firms_on.items()}
    # what each set of firms ordering together pays for its pages (alone: 90 x 7.30; together, each: 10 x 5.15)
    if choose:
        assert sets_off == {(a,): Decimal("657.00"), (a, b): Decimal("51.50")}
        assert sets_on == {(a,): Decimal("747.00"), (a, b): Decimal("56.50")}
    else:
        assert sets_off == {(a,): {a: Decimal("657.00")}, (a, b): {a: Decimal("51.50"), b: Decimal("51.50")}}
    # and what Generate bills, worked out from the days as it works them out
    from minute_filler.batch import joint_invoice
    s.invoice_judge_index = "off"
    case, opts = joint_invoice(jobs)
    assert {f.atty.key(): f.quotes[0].per_party for f in firm_invoices(case, s, opts)} == \
        {k: v["Regular"] for k, v in firms_off.items()}


# ------------------------------------------------------------------ the words
def test_what_the_firms_split_says_no_judges_index_when_none_is_billed():
    s = Settings()
    assert shared_words(s) == "the original and the judge's index"
    s.invoice_index_shared = "split"
    assert shared_words(s) == "the original, the index and the judge's index"
    s.invoice_judge_index = "off"
    assert shared_words(s) == "the original and the index"
    s.invoice_index_shared = "each"
    assert shared_words(s) == "the original"
    case = make_case(ROE)
    values = text_values(case, None, s, [], "2026-0001", InvoiceOpts(60, 2, days=[("6/3/2026", 60)]))
    assert values["shared"] == "the original"


def test_the_split_note_reads_right_with_one_thing_split_or_several():
    """The default note under the amounts: "the original of pages ordered together are split" read wrong with the
    judge's index not billed (2.18 rewords it); a saved copy of the old wording, unedited, takes the new one once
    (settings v18), one the user reworded is kept."""
    from minute_filler.settings import OLD_SPLIT_SHARE_TEXT, SPLIT_SHARE_TEXT, default_invoice_texts
    row = next(r for r in default_invoice_texts() if r["when"] == "split_share")
    assert row["text"] == SPLIT_SHARE_TEXT
    for shared in ("the original", "the original and the judge's index"):
        assert row["text"].replace("{shared}", shared) == (f"Amounts are your share: the cost of {shared} for pages "
                                                           "ordered together is split between the parties who ordered "
                                                           "them.")
    old = default_invoice_texts()
    old[1] = dict(old[1], text=OLD_SPLIT_SHARE_TEXT)
    mine = dict(old[2], text="My own words: {shared}.")
    s = Settings.from_dict({"settings_version": 17, "invoice_texts": old + [mine]})
    assert [r["text"] for r in s.invoice_texts if r["when"] == "split_share"] == [SPLIT_SHARE_TEXT]
    assert "My own words: {shared}." in [r["text"] for r in s.invoice_texts]
    again = Settings.from_dict({"settings_version": 18, "invoice_texts": [dict(old[1])]})
    assert again.invoice_texts[0]["text"] == OLD_SPLIT_SHARE_TEXT  # (from 2.18 on, it is the user's own)


def test_quotes_for_follows_the_settings_unless_told(s):
    """quotes_for, not told whether the judge's index is billed, does as Settings say (a caller that forgets can't
    bill it against them)."""
    s.invoice_judge_index = "off"
    assert JUDGE not in labels(quotes_for([60], 2, s.sheet(), s, "Regular", email=False, index="on")[0])
    assert JUDGE in labels(quotes_for([60], 2, s.sheet(), s, "Regular", email=False, index="on", judge_index=True)[0])


def test_the_window_tips_say_what_the_firms_split(qt):
    from minute_filler.gui.main_window import PARTIES_TIP, PAYS_TIP, WHO_TIP, _who_splits
    s = Settings()
    s.invoice_judge_index = "off"
    assert _who_splits(s) == {"shared": "the original", "own": "copy, e-mailed copy and index"}
    assert PARTIES_TIP.format(**_who_splits(s)).startswith("How many parties ordered: they split the original,\n")
    assert WHO_TIP.format(**_who_splits(s)).endswith("Pages ordered together split the original.")
    assert "(alone, or\nshared with other firms: they split the original) and" in PAYS_TIP.format(**_who_splits(s))
    s.invoice_index_shared = "split"
    assert _who_splits(s) == {"shared": "the original and the index", "own": "copy and e-mailed copy"}


def test_the_peripherals_label_names_the_judges_index_only_when_billed(qt):
    from PySide6.QtWidgets import QLabel

    from minute_filler.gui.dialogs import InvoicePeripheralsDialog
    s = Settings()

    def label(s):
        dlg = InvoicePeripheralsDialog(None, None, s)
        texts = [w.text() for w in dlg.findChildren(QLabel) if w.text().startswith("Index for this job")]
        dlg.deleteLater()
        return texts

    assert label(s) == ["Index for this job (and one for the judge):"]
    s.invoice_judge_index = "off"
    assert label(s) == ["Index for this job:"]


@pytest.fixture
def window(tmp_path, monkeypatch, make_window):
    from PySide6 import QtWidgets
    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)  # no dialogs waiting for a click
    s = pat_settings()
    s.use_ai = s.open_after = False
    s.output_dir = str(tmp_path / "out")
    s.records_dir = str(tmp_path / "records")
    s.save_math = "off"
    return make_window(s)


def test_the_includes_line_says_no_judges_index(window):
    """The Invoice card's Includes line: an index charged without the judge's says so, broken after the index's
    comma when the line would be too long (not inside "no judge's index"); no index, or the judge's index billed,
    as before."""
    from minute_filler.gui.main_window import LINE_WIDTH, _lines
    opts = InvoiceOpts(83, 1, days=[("6/3/2026", 83)])
    assert _lines(window._peripherals_text(opts)) == "E-mailed copy, index\n(83 total pages, 50 or more)"
    window.s.invoice_judge_index = "off"
    assert _lines(window._peripherals_text(opts)) == "E-mailed copy, index, no judge's index\n(83 total pages, 50 or more)"
    opts.email = False
    assert _lines(window._peripherals_text(opts)).splitlines() == [
        "No e-mailed copy (this job), index,", "no judge's index", "(83 total pages, 50 or more)"]
    assert all(len(line) <= LINE_WIDTH for line in _lines(window._peripherals_text(opts)).splitlines())
    opts.email, opts.index = None, "off"
    assert _lines(window._peripherals_text(opts)) == "E-mailed copy, no index\n(turned off for this job)"
    assert _lines(window._peripherals_text(InvoiceOpts(30, 1, days=[("6/3/2026", 30)], index="on"))) == \
        "E-mailed copy, index, no judge's index\n(turned on for this job)"
    assert _lines(window._peripherals_text(InvoiceOpts(30, 1, days=[("6/3/2026", 30)]))) == \
        "E-mailed copy, no index\n(30 total pages, under 50)"


def settle(window, until, seconds=20):
    """Runs the Qt event loop until no background task is left and until() is true."""
    from PySide6 import QtWidgets
    end = time.time() + seconds
    while time.time() < end:
        QtWidgets.QApplication.processEvents()
        if not window.runner._live and until():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


def test_generates_index_question_names_the_judges_only_when_billed(window, tmp_path, monkeypatch):
    """40 pages typed of an 83-page transcript: Generate asks whether to include an index, "(and the judge's)" only
    while Settings bill one."""
    from PySide6 import QtWidgets

    from minute_filler.models import SRC_USER, FieldState
    window.add_files([str(transcript_pdf(tmp_path / "Roe 6-3-2026.pdf", 83))])
    settle(window, lambda: window.cur.docs)
    window.output_boxes["invoice"].setChecked(True)
    window.case.attorneys = [alex()]
    window._show_attorneys()
    window.cur.case.fields["est_pages"] = FieldState("40", SRC_USER, 1.0, [])
    window._show_case()
    window._update_status()
    asked = []

    def exec_(box):
        if box.windowTitle() == "Index for this invoice?":
            asked.append(box.text())
        # (closed: as Go back)

    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", exec_)
    assert not window._ask_index([[window.cur]])
    window.s.invoice_judge_index = "off"
    assert not window._ask_index([[window.cur]])
    assert asked[0].endswith("Include an index (and the judge's) on this invoice?")
    assert asked[1].endswith("Include an index on this invoice?")
    window._update_status()
    assert window.inv_peripherals_info.text() == \
        "E-mailed copy, index? Generate asks\n(40 pages typed,\nthe transcript has 83 total pages)"


# ------------------------------------------------------------------ the spreadsheet
def test_the_spreadsheet_template_has_its_own_switch():
    """Setup's JudgeIndex (TRUE, as the app's default): FALSE leaves the judge's index column at $0, the index as
    it was."""
    from openpyxl import load_workbook

    from minute_filler.invoice import TEMPLATE
    wb = load_workbook(TEMPLATE)
    ref = wb.defined_names["JudgeIndex"].attr_text
    sheet, cell = ref.split("!")
    assert wb[sheet][cell.replace("$", "")].value is True
    assert wb[sheet][cell.replace("$", "").replace("B", "A")].value == "Judge's index"
    calc = wb["Calculation"]
    assert [calc[f"J{i}"].value for i in range(2, 6)] == [f"=IF(AND(JudgeIndex,I{i}>0),Pages*E{i},0)"
                                                         for i in range(2, 6)]
    assert all("JudgeIndex" not in str(calc[f"I{i}"].value) for i in range(2, 6))
