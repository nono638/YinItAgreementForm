"""Who ordered which pages says what Generate bills: each test reads what the window shows a firm, makes the invoices
with the real batch.fill_jobs, and compares the two in the records (the ledger). The window priced an unset firm at the
first day's agreement form, on the days as they stood; Generate first gives such a firm its speed from its other pages,
else that day's form (batch.settle_split_speeds), so the two differed once a firm's speed was set on part of its pages
or the days' forms differed.

Prices are from the bundled "Sample Rates" sheet. A page at Expedite: $7.60 alone, $4.90 shared by two. At Daily: $9.00
alone, $5.75 shared by two. All names are made up."""
import html
import random
import re
from decimal import Decimal

import pytest

from helpers import pat_settings, transcript_pdf
from minute_filler.batch import fill_jobs, group, read_docs
from minute_filler.deliver import ledger_for
from minute_filler.excerpts import Run, case_days, firms_of, prices, runs_of, store
from minute_filler.models import Attorney

DANA = dict(name="Dana Smith", firm="Smith Law", party="Plaintiff")
ALEX = dict(name="Alex B. Counsel", firm="Counsel & Counsel", party="Defendant")
KIM = dict(name="Kim Park", firm="Park PC", party="Defendant")
D, A, K = (Attorney(**x).key() for x in (DANA, ALEX, KIM))
NAMES = {D: "Dana Smith", A: "Alex B. Counsel", K: "Kim Park"}
SPEEDS = ["Regular", "Expedite", "Daily", "Immediate"]


@pytest.fixture
def s(tmp_path):
    s = pat_settings()
    s.output_dir, s.records_dir = str(tmp_path / "out"), str(tmp_path / "records")
    s.invoice_speeds = ["Regular", "Expedite"]
    s.invoice_include_index = False
    return s


def days_of(folder, s, pages=(30,), ticked=(D, A), forms=("Expedite",), initials=None):
    """Jobs of a transcript per number in `pages`, one day each, the agreement form of each day at its speed in `forms`
    (the last one for the rest), these firms ticked."""
    folder.mkdir(parents=True, exist_ok=True)
    when = ("June 3, 2026", "June 4, 2026", "June 5, 2026")
    docs, errors = read_docs([str(transcript_pdf(folder / f"Day {i}.pdf", n, date=when[i], initials=initials))
                              for i, n in enumerate(pages)], s)
    assert not errors
    jobs = group(docs, s)
    assert len(jobs) == len(pages)
    for i, j in enumerate(jobs):
        j.case.attorneys = [Attorney(**x, checked=Attorney(**x).key() in ticked) for x in (DANA, ALEX, KIM)]
        j.case.set("delivery", forms[min(i, len(forms) - 1)])
        j.att_touched = True
    return jobs


def pump(qt, times=6):
    for _ in range(times):
        qt.QApplication.processEvents()


def open_window(qt, jobs, s, **kw):
    from minute_filler.gui.excerpts import ExcerptsWindow
    w = ExcerptsWindow(s, lambda: None, **kw)
    w.load(jobs)
    w.show()
    pump(qt)
    return w


def set_runs(w, n, *rows):
    """Day n's runs from (first place, last place, firms, their speeds) rows, kept and shown."""
    d = w.days[n]
    store(d, [Run(d, a, b, list(keys), dict(speeds)) for a, b, keys, speeds in rows], w.firms, w.s)
    w.load(w.group)


def cell(w, r, key):
    from minute_filler.gui.excerpts import FIRST_FIRM
    return w.table.item(r, FIRST_FIRM + [a.key() for a in w.firms].index(key))


def amount(text):
    """The dollars in a cell or a line: "Daily · $1,090.50 (÷2)" -> Decimal("1090.50")."""
    return Decimal(re.search(r"\$([\d,]+(?:\.\d+)?)", text).group(1).replace(",", ""))


def invoices_shown(w) -> dict:
    """The lines under "Each firm's invoice" as the window says them: firm -> speed -> amount."""
    text = w.summary.text().split("Each firm's invoice", 1)
    assert len(text) == 2, w.summary.text()
    out = {}
    for line in text[1].split("<br>")[1:]:
        name, costs = html.unescape(re.sub(r"<[^>]+>", "", line)).replace("■", "").strip().split(": ", 1)
        out[name.strip()] = {re.sub(r" \$.*", "", c).strip(): amount(c) for c in costs.split(" · ")}
    return out


def cells_of(w) -> dict:
    """What the table says each firm pays, added up over its runs, for the firms priced at one speed."""
    out = {}
    for r, run in enumerate(w.runs):
        for key in run.keys:
            text = cell(w, r, key).text()
            if text:
                out[NAMES[key]] = out.get(NAMES[key], Decimal(0)) + amount(text)
    return out


def generate(jobs, s) -> dict:
    """What Generate bills: the invoices fill_jobs makes now, as the records have them: firm -> speed -> amount."""
    before = {i.invoice_no for i in ledger_for(s).invoices()}
    fill_jobs(jobs, s, outputs=["invoice"])
    made = [i for i in ledger_for(s).invoices() if i.invoice_no not in before]
    assert len({i.bill_to for i in made}) == len(made)  # (one invoice a firm: these days are billed together)
    return {i.bill_to: {sp: Decimal(v) for sp, v in i.amounts.items()} for i in made}


def assert_as_generate(w, jobs, s) -> dict:
    """The window's invoice lines are what Generate bills each firm, and the cells of a firm at one speed add up to
    them, within rounding up to the cent."""
    shown, cells = invoices_shown(w), cells_of(w)
    billed = generate(jobs, s)
    assert shown == billed
    for name, amounts in billed.items():
        if len(amounts) == 1:
            assert abs(cells[name] - next(iter(amounts.values()))) < Decimal("0.01"), (name, cells[name], amounts)
    return billed


@pytest.fixture
def themed(qt):
    from minute_filler.gui import zoom
    from minute_filler.gui.theme import apply_theme
    app = qt.QApplication.instance()
    style, palette = app.styleSheet(), app.palette()
    apply_theme(app, "light")
    yield apply_theme
    zoom.set_zoom(1.0)
    app.setStyleSheet(style)
    app.setPalette(palette)


# ------------------------------------------------------------------ a speed on part of a firm's pages
def test_a_speed_on_one_day_is_the_firms_speed_on_the_other(qt, themed, tmp_path, s):
    """Alex Daily on day 1, alone and unset on day 2: the window said "Daily · $90.00", amber "Expedite? · $152.00",
    "(varies)" and "Daily + Expedite $242.00"; Generate bills Daily $270.00."""
    from minute_filler.gui.excerpts import AMBER
    jobs = days_of(tmp_path / "a", s, pages=(10, 20), ticked=(A, K))
    w = open_window(qt, jobs, s)
    set_runs(w, 0, (1, 10, [A], {A: "Daily"}))
    set_runs(w, 1, (1, 20, [A], {}))
    assert cell(w, 0, A).text() == "$90.00" and cell(w, 1, A).text() == "$180.00"
    assert cell(w, 1, A).foreground().color().name() != AMBER
    assert w.firm_speed_boxes[A].short_text() == "Daily"
    assert invoices_shown(w) == {"Alex B. Counsel": {"Daily": Decimal("270.00")}}
    tip = cell(w, 1, A).toolTip()
    assert "Billed at Daily, its speed on its other pages" in tip and "agreement form" not in tip
    assert "ordered with another firm" not in tip  # (he shares nothing)
    assert assert_as_generate(w, jobs, s) == {"Alex B. Counsel": {"Daily": Decimal("270.00")}}
    w.close()


def test_a_speed_on_the_shared_run_is_the_firms_speed_on_its_lone_run(qt, themed, tmp_path, s):
    """The same day: Alex alone on 10 total pages unset, sharing 20 with Dana, Daily there by right-click. The window
    said "Expedite + Daily $202.00"; Generate bills Daily $216.00."""
    jobs = days_of(tmp_path / "a", s)
    w = open_window(qt, jobs, s)
    set_runs(w, 0, (1, 10, [A], {}), (11, 30, [A, D], {A: "Daily"}))
    assert cell(w, 0, A).text() == "$90.00"
    assert cell(w, 1, A).text() == "$126.00 · shared"  # (Dana is at the form's speed, Expedite: no ÷2)
    assert invoices_shown(w)["Alex B. Counsel"] == {"Daily": Decimal("216.00")}
    assert assert_as_generate(w, jobs, s)["Alex B. Counsel"] == {"Daily": Decimal("216.00")}
    w.close()


def test_each_day_is_at_its_own_forms_speed(qt, themed, tmp_path, s):
    """Two days shared, nothing set, the forms say Expedite then Daily. The window priced both at the first form's:
    $147.00 each; Generate bills "Expedite + Daily" $164.00 each."""
    jobs = days_of(tmp_path / "a", s, pages=(10, 20), forms=("Expedite", "Daily"))
    w = open_window(qt, jobs, s)
    assert w.firm_speed_boxes[A].short_text() == "(varies)"
    assert cell(w, 0, A).text() == "Expedite · $49.00 (÷2)" and cell(w, 1, A).text() == "Daily · $115.00 (÷2)"
    both = {"Expedite + Daily": Decimal("164.00")}
    assert invoices_shown(w) == {"Alex B. Counsel": both, "Dana Smith": both}
    tip = cell(w, 1, A).toolTip()
    assert "Billed at Daily, the agreement form's speed" in tip
    assert assert_as_generate(w, jobs, s) == {"Alex B. Counsel": both, "Dana Smith": both}
    w.close()


def test_no_false_divisor_on_a_run_the_split_rule_divides(qt, themed, tmp_path, s):
    """Alex Daily on day 1, Alex + Dana unset on day 2. Day 2's cell said "Expedite? · $98.00 (÷2)". Alex is billed
    $216.00 at Daily in all, leaving $126.00 for that run, which the split rule divides with Dana at the form's speed."""
    jobs = days_of(tmp_path / "a", s, pages=(10, 20))
    w = open_window(qt, jobs, s)
    set_runs(w, 0, (1, 10, [A], {A: "Daily"}))
    set_runs(w, 1, (1, 20, [A, D], {}))
    assert cell(w, 1, A).text() == "$126.00 · shared"
    assert "÷" not in cell(w, 1, D).text() and cell(w, 1, D).text().endswith(" · shared")
    assert "Split invoices" in w.note.text()
    assert invoices_shown(w)["Alex B. Counsel"] == {"Daily": Decimal("216.00")}
    assert_as_generate(w, jobs, s)
    w.close()


def test_the_lines_by_firms_ordering_together_say_the_same_speeds(qt, themed, tmp_path, s):
    jobs = days_of(tmp_path / "a", s, pages=(10, 20), ticked=(A, K))
    w = open_window(qt, jobs, s)
    set_runs(w, 0, (1, 10, [A], {A: "Daily"}))
    set_runs(w, 1, (1, 20, [A], {}))
    text = html.unescape(w.summary.text())
    assert "Alex B. Counsel (Daily) only: 30 of your pages billed (30 total pages) - costs $270.00" in text, text
    assert "Expedite" not in text.split("Each firm's invoice")[0]
    w.close()


def test_a_firm_alone_with_nothing_set_still_chooses(qt, themed, tmp_path, s):
    """Nothing to settle: both prices, on its invoice and in Each pays, and what Generate offers."""
    jobs = days_of(tmp_path / "a", s, ticked=(A,))
    w = open_window(qt, jobs, s)
    assert cell(w, 0, A).text() == "" and w.firm_speed_boxes[A].short_text() == "Chooses"
    assert invoices_shown(w) == generate(jobs, s) == {
        "Alex B. Counsel": {"Regular": Decimal("189.00"), "Expedite": Decimal("228.00")}}
    w.close()


def test_the_days_themselves_are_not_given_a_speed_by_looking(qt, themed, tmp_path, s):
    """The window prices copies: a firm unset stays unset until Generate (Go back takes them off again, and the form's
    speed may change meanwhile)."""
    jobs = days_of(tmp_path / "a", s, pages=(10, 20))
    w = open_window(qt, jobs, s)
    assert all(j.speeds == {} for j in jobs)
    w.close()


# ------------------------------------------------------------------ how it is rounded, and Parties
def test_rounded_by_the_page(qt, themed, tmp_path, s):
    """$2.2666… of a Daily original three ways is rounded with every other charge, on each stretch: the window's
    cells add up to the invoice exactly, as Generate bills it."""
    s.invoice_rounding = "page"
    jobs = days_of(tmp_path / "a", s, pages=(11, 31), ticked=(D, A, K))
    w = open_window(qt, jobs, s)
    set_runs(w, 0, (1, 11, [A], {A: "Daily"}))
    set_runs(w, 1, (1, 7, [D, A, K], {}), (8, 31, [D, K], {}))
    billed = assert_as_generate(w, jobs, s)
    assert set(billed["Alex B. Counsel"]) == {"Daily"} and len(billed) == 3
    w.close()


def test_parties_above_the_firms_ticked_one_speed(qt, themed, tmp_path, s):
    jobs = days_of(tmp_path / "a", s)
    jobs[0].parties = 3
    w = open_window(qt, jobs, s)
    assert cell(w, 0, A).text() == "$120.00 (÷3)"
    assert assert_as_generate(w, jobs, s) == {"Alex B. Counsel": {"Expedite": Decimal("120.00")},
                                              "Dana Smith": {"Expedite": Decimal("120.00")}}
    w.close()


def test_parties_above_the_firms_ticked_and_a_speed_held_at_generate(qt, themed, tmp_path, s):
    """Alex Daily, Dana unset, Parties 3: Dana takes the form's speed at Generate, so the two named firms are at
    different speeds and what the third party pays can't be worked out. Generate holds the invoice: the window says
    so, though nothing on the days as they stand is held yet."""
    jobs = days_of(tmp_path / "a", s)
    jobs[0].parties = 3
    jobs[0].speeds = {A: "Daily"}
    assert not jobs[0].invoice_hold()
    w = open_window(qt, jobs, s)
    assert w.problem.text().startswith("⚠ No invoice yet") and "Parties says 3" in w.problem.text()
    assert generate(jobs, s) == {}
    w.close()


def test_a_third_speed_at_generate_is_held_and_said(qt, themed, tmp_path, s):
    """Dana Daily, Alex Immediate, Kim unset on the same pages: Kim takes the form's speed at Generate, the third on
    those pages, and the invoice is held. Nothing on the days as they stand says so."""
    jobs = days_of(tmp_path / "a", s, ticked=(D, A, K))
    jobs[0].speeds = {D: "Daily", A: "Immediate"}
    assert not jobs[0].invoice_hold()
    w = open_window(qt, jobs, s)
    assert "3 different speeds" in w.problem.text() and w.problem.text().startswith("⚠ No invoice yet")
    assert generate(jobs, s) == {}
    w.close()


# ------------------------------------------------------------------ random orders
def random_order(rng, folder, s):
    """Days of 1 to 3 transcripts, cut into runs at random, some with speeds, as the window keeps them."""
    jobs = days_of(folder, s, pages=tuple(rng.choice([7, 11, 13, 25, 33]) for _ in range(rng.choice([1, 2, 2, 3]))),
                   ticked=(D, A, K), forms=[rng.choice(SPEEDS[:3]) for _ in range(3)])
    days, firms = case_days(jobs), firms_of(jobs)
    for d in days:
        if rng.random() < .3:
            continue  # (the day whole, as ticked)
        cuts = sorted(rng.sample(range(1, d.pages), k=rng.choice([0, 1, 2])))
        rows = []
        for a, b in zip([1] + [c + 1 for c in cuts], cuts + [d.pages]):
            keys = rng.sample([D, A, K], k=rng.choice([1, 1, 2, 2, 3]))
            speeds = {k: rng.choice(SPEEDS) for k in keys if rng.random() < .2}
            rows.append(Run(d, a, b, keys, speeds if len(set(speeds.values())) < 3 else {}))
        store(d, rows, firms, s)
    if rng.random() < .3:  # (a firm's speed for the whole of a day)
        rng.choice(jobs).speeds[rng.choice([D, A, K])] = rng.choice(SPEEDS)
    return jobs


def as_shown(p, runs):
    """prices() as the window shows it: each firm's invoice, and what its cells or Each pays add up to."""
    invoices = {NAMES[k]: dict(a) for k, a in p.firms}
    cells: dict = {}
    for r in runs:
        for k, (_, pays) in p.ordered.get(id(r), {}).items():
            cells[NAMES[k]] = cells.get(NAMES[k], Decimal(0)) + pays
    return invoices, cells


@pytest.mark.parametrize("seed, rounding", [(1, "exact"), (2, "page")])
def test_random_orders_are_shown_as_generate_bills_them(tmp_path, s, seed, rounding):
    """Each firm of each random order, whatever is set on which pages. A held invoice (three speeds, say) is said and
    makes none."""
    s.invoice_rounding = rounding
    rng = random.Random(seed)
    compared = 0
    for n in range(10):
        s.invoice_include_index = rng.random() < .5
        s.invoice_index_threshold = rng.choice([10, 25])
        s.invoice_index_shared = rng.choice(["each", "split"])
        s.output_dir = str(tmp_path / f"o{n}")
        jobs = random_order(rng, tmp_path / f"d{n}", s)
        days = case_days(jobs)
        firms = firms_of(jobs)
        runs = [r for d in days for r in runs_of(d, firms)]
        p = prices(days, runs, s)
        invoices, cells = as_shown(p, runs)
        if p.hold:
            assert generate(jobs, s).keys() <= invoices.keys()  # (the days held have none)
            continue
        billed = generate(jobs, s)
        assert invoices == billed, (seed, n)
        for name, amounts in billed.items():
            compared += 1
            if len(amounts) == 1:
                assert abs(cells[name] - next(iter(amounts.values()))) < Decimal("0.01"), (seed, n, name)
    assert compared > 10


# ------------------------------------------------------------------ Generate asks
def test_asked_it_is_priced_as_it_stands_until_answered_and_says_so(qt, themed, tmp_path, s):
    """Settings.split_speeds "ask": Generate asks, starting from his Daily on day 1. Until then the price is at the
    form's (the invoice as it stands), amber, and the tooltip says all that; he shares nothing, so it doesn't say so."""
    from minute_filler.batch import speeds_to_ask
    from minute_filler.gui.excerpts import AMBER
    s.split_speeds = "ask"
    jobs = days_of(tmp_path / "a", s, pages=(10, 20), ticked=(A, K))
    w = open_window(qt, jobs, s)
    set_runs(w, 0, (1, 10, [A], {A: "Daily"}))
    set_runs(w, 1, (1, 20, [A], {}))
    it = cell(w, 1, A)
    assert it.text() == "Expedite? · $152.00" and it.foreground().color().name() == AMBER
    tip = it.toolTip()
    assert "Generate asks, starting from Daily" in tip and "Priced at Expedite, the agreement form's, until" in tip
    assert "with another firm" not in tip and "its other pages" in tip
    assert speeds_to_ask(jobs, s)  # (it does ask)
    assert invoices_shown(w) == {"Alex B. Counsel": {"Daily + Expedite": Decimal("242.00")}}  # (as it stands)
    for a in speeds_to_ask(jobs, s):  # the answers (the question's own starting speed), as the window keeps them
        a.job.speeds.setdefault(a.key, a.speed)
    w.load(jobs)
    assert cell(w, 1, A).foreground().color().name() != AMBER and "?" not in cell(w, 1, A).text()
    assert assert_as_generate(w, jobs, s) == {"Alex B. Counsel": {"Daily": Decimal("270.00")}}
    w.close()


def test_asked_and_shared_says_these_pages_are_ordered_with_another_firm(qt, themed, tmp_path, s):
    s.split_speeds = "ask"
    jobs = days_of(tmp_path / "a", s)
    w = open_window(qt, jobs, s)
    tip = cell(w, 0, A).toolTip()
    assert "these pages are ordered with another firm" in tip and "Generate asks" in tip
    w.close()


def test_asked_with_its_other_pages_shared_says_so(qt, themed, tmp_path, s):
    s.split_speeds = "ask"
    jobs = days_of(tmp_path / "a", s)
    w = open_window(qt, jobs, s)
    set_runs(w, 0, (1, 10, [A], {}), (11, 30, [A, D], {}))
    assert "some of its pages are ordered with another firm" in cell(w, 0, A).toolTip()
    w.close()


def test_asked_every_speed_answered_is_what_generate_bills(qt, themed, tmp_path, s):
    """Answered with another speed than the question starts from: that speed, in the window and on the invoice."""
    s.split_speeds = "ask"
    jobs = days_of(tmp_path / "a", s, pages=(10, 20))
    jobs[0].speeds = {A: "Daily", D: "Regular"}
    jobs[1].speeds = {A: "Immediate", D: "Regular"}
    w = open_window(qt, jobs, s)
    assert_as_generate(w, jobs, s)
    w.close()


@pytest.mark.usefixtures("split_orders_choose")
def test_it_doesnt_say_generate_asks_when_it_wont(qt, themed, tmp_path, s):
    """A courthouse whose firms needn't commit: a speed on one day, none on the other. Generate asks nothing and bills
    the form's on those pages, with no ? and no amber."""
    from minute_filler.batch import speeds_to_ask
    from minute_filler.gui.excerpts import AMBER
    s.split_speeds = "ask"
    jobs = days_of(tmp_path / "a", s, pages=(10, 20), ticked=(A, K))
    w = open_window(qt, jobs, s)
    set_runs(w, 0, (1, 10, [A], {A: "Daily"}))
    set_runs(w, 1, (1, 20, [A], {}))
    assert not speeds_to_ask(jobs, s)
    it = cell(w, 1, A)
    assert "?" not in it.text() and it.foreground().color().name() != AMBER and "Generate asks" not in it.toolTip()
    assert assert_as_generate(w, jobs, s) == {"Alex B. Counsel": {"Daily + Expedite": Decimal("242.00")}}
    w.close()


@pytest.mark.usefixtures("split_orders_choose")
def test_where_firms_neednt_commit_the_others_speed_is_the_firms_own(qt, themed, tmp_path, s):
    """Alex Daily, Dana with none, on the same pages, at a courthouse whose firms needn't commit: Alex's invoice divides
    the original as if Dana had ordered his speed (invoice.firm_invoices), not the form's. The cell said otherwise."""
    jobs = days_of(tmp_path / "a", s)
    jobs[0].speeds = {A: "Daily"}
    w = open_window(qt, jobs, s)
    assert amount(cell(w, 0, A).text()) == Decimal("172.50")
    assert assert_as_generate(w, jobs, s)["Alex B. Counsel"] == {"Daily": Decimal("172.50")}
    w.close()


# ------------------------------------------------------------------ Generate's days, in the main window
def trial_window(qt, tmp_path, make_window, s, pages=(10, 20)):
    """A main window on two days of a trial (Generate all bills them together), Alex alone on both."""
    from test_show_the_math import settled
    s.outputs = ["invoice"]
    win = settled(make_window(s))
    jobs = days_of(tmp_path / "a", s, pages=pages, ticked=(A,))
    for j in jobs:
        j.case.set("index_no", "712345/2024")
        j.case.set("case_name", "Jane Roe v. Sam Poe")
    win.jobs, win.cur = jobs, jobs[1]
    return win, jobs


def test_the_window_works_the_speeds_out_over_generates_days(qt, themed, tmp_path, make_window, s):
    """Day 2 shown and unticked, so the window has it alone; Generate works its speeds out over day 1 too, ticked
    (MainWindow._ask_split_speeds), and bills day 2 at Alex's Daily of day 1."""
    win, (one, two) = trial_window(qt, tmp_path, make_window, s)
    one.speeds, two.include = {A: "Daily"}, False
    w = open_window(qt, [two], s, pool=win._speed_days)
    assert cell(w, 0, A).text() == "$180.00" and w.firm_speed_boxes[A].short_text() == "Daily"
    assert invoices_shown(w) == {"Alex B. Counsel": {"Daily": Decimal("180.00")}}
    assert [j for j in win._as_billed([two])][0].speeds[A] == "Daily"
    assert two.speeds == {}
    assert win._ask_split_speeds([two]) and two.speeds == {A: "Daily"}  # (what Generate sets)
    win._unsettle()
    w.close()


@pytest.mark.parametrize("why", ["invoiced", "unticked"])
def test_a_day_generate_leaves_out_gives_no_speed(qt, themed, tmp_path, make_window, s, why):
    """Day 1 billed already, or unticked, isn't among the days Generate works day 2's speeds out over, though it is of
    its trial (the days ticks are pinned on, MainWindow._trial_of): day 2 still chooses from its invoice."""
    win, (one, two) = trial_window(qt, tmp_path, make_window, s)
    one.speeds = {A: "Daily"}
    if why == "invoiced":
        one.invoiced = True
    else:
        one.include = False
    assert any(j is one for j in win._trial_of([two]))
    w = open_window(qt, [two], s, pool=win._speed_days)
    assert cell(w, 0, A).text() == "" and w.firm_speed_boxes[A].short_text() == "Chooses"
    assert set(invoices_shown(w)["Alex B. Counsel"]) == {"Regular", "Expedite"}
    assert win._ask_split_speeds([two]) and two.speeds == {}
    w.close()


def generate_all(qt, win, s, monkeypatch) -> dict:
    """What Generate all bills, all of it as it runs: the days it makes (_to_generate), the speeds it sets
    (_ask_split_speeds), fill_jobs on its copies on its own thread; the invoices made, from the records: firm -> speed ->
    amount. The day shown is put in the editor first, as Generate all reads it back."""
    import time
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    win._show_job()
    before = {i.invoice_no for i in ledger_for(s).invoices()}
    win.fill_all_jobs()
    end = time.time() + 30
    while time.time() < end and (win.filling or win.runner._live):
        qt.QApplication.processEvents()
        time.sleep(0.01)
    assert not win.filling
    made = [i for i in ledger_for(s).invoices() if i.invoice_no not in before]
    return {i.bill_to: {sp: Decimal(v) for sp, v in i.amounts.items()} for i in made}


CHOOSES_ON_DAY_2 = {"Alex B. Counsel": {"Regular": Decimal("126.00"), "Expedite": Decimal("152.00")}}


@pytest.mark.parametrize("made", [True, False])
def test_a_day_invoiced_gives_no_speed_whether_or_not_it_was_made(qt, themed, tmp_path, make_window, s, monkeypatch, made):
    """Day 1 billed already, at Alex's Daily. Whether it counts as made (Job.made: not when a file of it failed on the run
    that made the invoice, so Generate all takes it up again) has nothing to do with the bill: not made, it was among the
    days day 2's speed was worked out over, which billed Daily $180.00, where the window said he chooses."""
    win, (one, two) = trial_window(qt, tmp_path, make_window, s)
    one.speeds, one.invoiced, one.made = {A: "Daily"}, True, made
    assert any(j is one for j in win._to_generate()) is not made
    w = open_window(qt, [two], s, pool=win._speed_days)
    assert cell(w, 0, A).text() == "" and w.firm_speed_boxes[A].short_text() == "Chooses"
    assert invoices_shown(w) == CHOOSES_ON_DAY_2 == generate_all(qt, win, s, monkeypatch)
    assert two.speeds == {}
    w.close()


def test_fill_jobs_works_no_speed_out_over_a_day_invoiced(tmp_path, s):
    """As the command line and the preview call it: the same days, without the window."""
    jobs = days_of(tmp_path / "a", s, pages=(10, 20), ticked=(A,))
    one, two = jobs
    one.speeds, one.invoiced = {A: "Daily"}, True
    assert generate(jobs, s) == CHOOSES_ON_DAY_2
    assert two.speeds == {}


def test_generate_all_asks_nothing_about_a_day_invoiced(qt, themed, tmp_path, make_window, s, monkeypatch):
    """Where Generate asks: a day billed already, shared and with no speed, isn't asked about (what would the answer
    change?), and a speed on it doesn't start the question of another day's."""
    s.split_speeds = "ask"
    win, (one, two) = trial_window(qt, tmp_path, make_window, s)
    for j in (one, two):
        for a in j.case.attorneys:
            a.checked = a.key() in (A, D)
    one.invoiced, one.speeds = True, {A: "Daily"}
    asked = []
    from minute_filler.gui import dialogs

    class Box(dialogs.SplitSpeedsDialog):
        def __init__(self, asks, *a, **k):
            asked.extend(asks)
            super().__init__(asks, *a, **k)

        def exec(self):
            return dialogs.SplitSpeedsDialog.Accepted
    monkeypatch.setattr(dialogs, "SplitSpeedsDialog", Box)
    generate_all(qt, win, s, monkeypatch)
    assert [(a.job, a.speed) for a in asked] == [(two, "Expedite"), (two, "Expedite")]
    assert one.speeds == {A: "Daily"}


@pytest.mark.parametrize("shown", ["day 2, ticked", "day 1, unticked"])
def test_what_generate_all_bills_doesnt_depend_on_the_day_shown(qt, themed, tmp_path, make_window, s, monkeypatch, shown):
    """Day 1 unticked, so not made, at Alex's Daily. It gave day 2 his Daily, $180.00, only while day 1 was the day on
    screen; the window on day 2 says what Generate all bills, from either."""
    win, (one, two) = trial_window(qt, tmp_path, make_window, s)
    one.speeds, one.include = {A: "Daily"}, False
    win.cur = two if shown.startswith("day 2") else one
    win._who_ordered(two)
    pump(qt)
    w = win.excerpts
    assert [d.job for d in w.days] == [two]
    assert invoices_shown(w) == CHOOSES_ON_DAY_2 == generate_all(qt, win, s, monkeypatch)
    assert two.speeds == {}
    w.close()


@pytest.mark.parametrize("shown", ["ticked", "unticked"])
def test_a_ticked_day_still_gives_its_speed_whichever_day_is_shown(qt, themed, tmp_path, make_window, s, monkeypatch, shown):
    """The other way about: days 1 and 2 ticked, day 3 unticked. Day 2 takes Alex's Daily from day 1 whichever is shown."""
    win, jobs = trial_window(qt, tmp_path, make_window, s, pages=(10, 20, 5))
    one, two, three = jobs
    one.speeds, three.include = {A: "Daily"}, False
    win.cur = two if shown == "ticked" else three
    win._who_ordered(two)
    pump(qt)
    w = win.excerpts
    assert [d.job for d in w.days] == [one, two]
    both = {"Alex B. Counsel": {"Daily": Decimal("270.00")}}
    assert invoices_shown(w) == both == generate_all(qt, win, s, monkeypatch)
    w.close()


def test_generate_of_the_day_shown_still_counts_the_days_ticked(qt, themed, tmp_path, make_window, s):
    """Generate of day 2, shown and unticked, works its speeds out over the days ticked, as it did: Generate all's days
    are the ticked ones, and this day is the one it makes."""
    win, (one, two) = trial_window(qt, tmp_path, make_window, s)
    one.speeds, two.include = {A: "Daily"}, False
    win.cur = two
    assert [id(j) for j in win._speed_days([two])] == [id(two), id(one)]
    assert win._ask_split_speeds([two]) and two.speeds == {A: "Daily"}
    win._unsettle()


def test_generate_of_a_day_invoiced_still_settles_its_own_speeds(qt, themed, tmp_path, make_window, s):
    """Generate of the day shown bills a day invoiced already again: its firms sharing pages still commit to a speed,
    though Generate all leaves it out."""
    win, (one, two) = trial_window(qt, tmp_path, make_window, s)
    for a in one.case.attorneys:
        a.checked = a.key() in (A, D)
    one.invoiced = True
    win.cur = one
    assert win._ask_split_speeds([one]) and one.speeds == {A: "Expedite", D: "Expedite"}
    win._unsettle()


def test_a_day_invoiced_already_is_shown_as_it_was_billed(qt, themed, tmp_path, make_window, s):
    """The days of an invoice made: a speed set since on a day still to bill isn't theirs. Before it was billed, Alex
    alone chose from his invoice; both prices stay."""
    win, (one, two) = trial_window(qt, tmp_path, make_window, s)
    one.invoiced, two.speeds = True, {A: "Daily"}
    win.cur = one
    w = open_window(qt, [one], s, pool=win._speed_days)
    assert set(invoices_shown(w)["Alex B. Counsel"]) == {"Regular", "Expedite"}
    assert win._as_billed([one])[0].speeds == {}
    w.close()


def test_the_main_windows_row_and_the_window_say_the_same(qt, themed, tmp_path, make_window, s):
    """Its row (batch.speed_shown) and its Invoice card (_as_billed) said Daily beside this window's Daily + Expedite."""
    from minute_filler.batch import speed_shown
    from minute_filler.invoice import firm_invoices
    from minute_filler.batch import joint_invoice
    win, (one, two) = trial_window(qt, tmp_path, make_window, s)
    one.speeds = {A: "Daily"}
    w = open_window(qt, [one, two], s, pool=win._speed_days)
    assert speed_shown([one, two], A, s).speed == "Daily" == w.firm_speed_boxes[A].short_text()
    case, opts = joint_invoice(win._as_billed([one, two]))
    card = {f.atty.label(): {q.speed: q.per_party for q in f.quotes} for f in firm_invoices(case, s, opts)}
    assert card == invoices_shown(w) == {"Alex B. Counsel": {"Daily": Decimal("270.00")}}
    w.close()


def test_the_excerpts_button_passes_generates_days_not_the_whole_trial(qt, themed, tmp_path, make_window, s):
    """The window the main window opens: a day billed already is of the trial, but gives no speed."""
    win, (one, two) = trial_window(qt, tmp_path, make_window, s)
    one.speeds, one.invoiced = {A: "Daily"}, True
    win._who_ordered(two)
    pump(qt)
    w = win.excerpts
    assert [d.job for d in w.days] == [two]
    assert cell(w, 0, A).text() == "" and w.firm_speed_boxes[A].short_text() == "Chooses"
    w.close()


def test_as_billed_is_where_the_main_window_has_it(qt, tmp_path, make_window, s):
    from test_show_the_math import settled
    from minute_filler.batch import as_billed
    win = settled(make_window(s))
    jobs = days_of(tmp_path / "a", s)
    win.jobs, win.cur = jobs, jobs[0]
    assert win._as_billed(jobs)[0].speeds == as_billed(jobs, s)[0].speeds == {A: "Expedite", D: "Expedite"}
    assert jobs[0].speeds == {}
    s.split_speeds = "ask"
    assert win._as_billed(jobs)[0] is jobs[0] and as_billed(jobs, s)[0] is jobs[0]  # (the days themselves)
