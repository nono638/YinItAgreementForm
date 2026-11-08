"""Generate of the day shown bills a day invoiced already as the window shows it. A day billed already shows what it
was billed (batch.speed_days: its speeds are worked out over its own days, as a speed set since on a day still to bill
isn't its), and so its Invoice card prices it; Generate of it worked them out over the other days of its trial ticked
in the list too (MainWindow._ask_split_speeds over _speed_days). Alex B. Counsel chose from his invoice on day 1, as
its card still said (Regular $63.00 or Expedite $76.00); Daily set for him on day 2 since, still to bill, became his
on day 1 at Generate: the agreement made again said Daily at $6.50, the invoice billed Daily $90.00, and the day kept
Daily. Day 2's pages shared with Dana Smith did the same with the form's Expedite (a firm sharing pages on one day
commits on all): the invoice billed Expedite $76.00 alone. Generate all leaves a day invoiced out already
(tests/test_excerpts_money.py).

Real files and invoices into a ledger of the test's own, the real window. Prices are the bundled "Sample Rates"
sheet's. All names are made up."""
import re
from decimal import Decimal

import pymupdf
import pytest

from helpers import pat_settings
from minute_filler.deliver import ledger_for

from test_excerpts_money import A, D, days_of

CHOOSES = {"Regular": Decimal("63.00"), "Expedite": Decimal("76.00")}  # (10 of your pages, alone)


@pytest.fixture
def s(tmp_path):
    s = pat_settings()
    s.output_dir, s.records_dir = str(tmp_path / "out"), str(tmp_path / "records")
    s.invoice_speeds = ["Regular", "Expedite"]
    s.invoice_include_index = False
    s.save_math = "off"
    s.use_ai = s.open_after = False
    return s


@pytest.fixture
def window(qt, make_window, s, monkeypatch):
    from test_show_the_math import settled
    from minute_filler.gui.dialogs import ClarifyDialog
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(ClarifyDialog, "exec", lambda self: qt.QDialog.Accepted)
    s.outputs = ["agreement", "invoice"]
    return settled(make_window(s))


def trial(win, tmp_path, s, day_2):
    """Jane Roe's trial in the window, both days ticked: June 3 (10 of your pages), invoiced already with Alex alone
    and no speed for him (he chose from his invoice), shown; June 4 (20 of your pages), still to bill, giving Alex a
    speed: Daily set for him ("daily"), or its pages shared with Dana ("shared")."""
    one, two = days_of(tmp_path / "in", s, pages=(10, 20), ticked=(A,) if day_2 == "daily" else (A, D))
    for a in one.case.attorneys:
        a.checked = a.key() == A
    for j in (one, two):
        j.case.set("index_no", "712345/2024")
        j.case.set("case_name", "Jane Roe v. Sam Poe")
    one.invoiced = one.made = True
    if day_2 == "daily":
        two.speeds = {A: "Daily"}
    win.jobs, win.cur = [one, two], one
    win._show_job()
    return one, two


def card(win) -> dict:
    """The Invoice card's prices of the day shown: speed -> amount ("10 of your pages · Regular $63.00 · Expedite
    (form) $76.00")."""
    return {sp: Decimal(n) for sp, n in re.findall(r"(\w+)(?: \(form\))? \$([\d.]+)", win.inv_info.text())}


def generate(win, s, job) -> tuple[dict, dict]:
    """Generate of the day shown (MainWindow.fill): the invoice made, as the records have it (speed -> amount), and
    what the agreement says (its delivery boxes ticked, its rate a page)."""
    before = {i.invoice_no for i in ledger_for(s).invoices()}
    win.fill()
    assert not job.error
    (made,) = [i for i in ledger_for(s).invoices() if i.invoice_no not in before]
    assert made.bill_to == "Alex B. Counsel"
    (path,) = [p for p in job.saved if p.name.startswith("Minute Agreement")]
    with pymupdf.open(path) as doc:
        fields = {w.field_name: w.field_value for w in doc[0].widgets()}
    form = {"speed": [n for n in ("Regular", "Expedited", "Daily", "Other") if fields.get(n)],
            "rate": fields["7 Rate to be Charged Per Page"]}
    return {sp: Decimal(v) for sp, v in made.amounts.items()}, form


@pytest.mark.parametrize("day_2", ["daily", "shared"])
def test_generate_of_a_day_invoiced_bills_what_its_card_says(window, tmp_path, s, day_2):
    one, two = trial(window, tmp_path, s, day_2)
    assert card(window) == CHOOSES
    invoice, agreement = generate(window, s, one)
    assert invoice == CHOOSES  # (was Daily $90.00; shared, Expedite $76.00 alone)
    assert agreement == {"speed": ["Expedited"], "rate": "$5.40"}  # (the form's Expedite; was Daily at $6.50)
    assert one.speeds == {}  # (the day keeps no speed it wasn't billed)
    window._show_job()
    assert card(window) == CHOOSES
    assert two.speeds == ({A: "Daily"} if day_2 == "daily" else {})  # (day 2 as it was)


def test_where_generate_asks_a_day_invoiced_isnt_asked_another_days_speed(window, tmp_path, s, monkeypatch):
    """Settings.split_speeds "ask": Generate of day 1 asked Alex's speed on it, starting from day 2's Daily (and
    billed Daily, the answer as it started). Now it asks nothing, and bills what the card says."""
    from minute_filler.gui import dialogs
    s.split_speeds = "ask"
    asked = []

    class Box(dialogs.SplitSpeedsDialog):
        def __init__(self, asks, *a, **k):
            asked.extend((x.job.case.get("dates"), x.name, x.speed) for x in asks)
            super().__init__(asks, *a, **k)

        def exec(self):
            return dialogs.SplitSpeedsDialog.Accepted

    monkeypatch.setattr(dialogs, "SplitSpeedsDialog", Box)
    one, _ = trial(window, tmp_path, s, "daily")
    assert card(window) == CHOOSES
    invoice, agreement = generate(window, s, one)
    assert asked == []  # (was [("6/3/2026", "Alex B. Counsel", "Daily")])
    assert invoice == CHOOSES and agreement == {"speed": ["Expedited"], "rate": "$5.40"}
    assert one.speeds == {}
