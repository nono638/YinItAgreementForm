"""Settings -> Invoice -> Rounding: "Exact" (the default: every fraction of a cent kept, the amount rounded up to
the cent once) or "The price a page, to the cent" (as reporters work it out by hand: each party's price a page,
every charge together, rounded to the nearest cent first, then times its pages; the user, 2026-10-10). Four firms
sharing Immediate pay $7.60 / 4 + $1.45 + $1.45 + $1.45 + $1.45 / 4 = $6.6125 a page: $6,612.50 for 1,000 pages
exactly, $6.61 x 1,000 = $6,610.00 by hand. It goes either way ($6.6175 -> $6.62), the same rule on every
invoice. The math says how the amount was reached; the invoice doesn't (the user, 2026-10-10: just use it, or
don't, as the setting says). Also Quote.prices (the exact price a page of each stretch: times their pages, they add
up to the exact share), the setting kept and checked, the Settings window and the Excerpts window's words. All
names and numbers are made up; prices are from the bundled "Sample Rates" sheet (Immediate: original $7.60, copy,
e-mailed copy and index $1.45; Expedite $5.40 and $1.10; Regular $4.30 and $1.00)."""
import json
import random
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

import pymupdf
import pytest

from helpers import ROE, make_case, pat_settings
from minute_filler.courthouses.queens_supreme_civil.billing import split
from minute_filler.invoice import DayOrder, InvoiceOpts, Portion, _detail, firm_invoices, make_invoices
from minute_filler.invoice_calc import Share, index_days, quote, quote_ordered, quote_shares, to_cent
from minute_filler.invoice_math import explain, together
from minute_filler.models import Attorney
from minute_filler.rates import Speed
from minute_filler.records import Ledger
from minute_filler.settings import Settings

FOUR = (("Dana Smith", "Smith Law"), ("Alex B. Counsel", "Counsel & Counsel"), ("Sam Roe", "Roe & Co."),
        ("Lee Doe", "Doe PC"))
SIX_61 = "$6.6125 a page, rounded to $6.61, × 1,000 pages"


@pytest.fixture
def s(tmp_path):
    s = pat_settings()
    s.output_dir = str(tmp_path / "out")
    s.records_dir = str(tmp_path / "records")
    s.invoice_speeds = ["Immediate"]
    s.save_math = "off"
    return s


def speed(s, name):
    return s.sheet().find(name)


def four_firms(s, orders=True):
    """Four firms sharing a day of 1,000 pages at Immediate (indexed: 50 pages or more), each with its own
    invoice (orders), or the invoice made the old way, split 4 ways (orders=False)."""
    firms = [Attorney(name=n, firm=f, checked=True) for n, f in FOUR]
    case = make_case({**ROE, "delivery": "Immediate"}, firms)
    opts = InvoiceOpts(1000, 4, days=[("6/3/2026", 1000)], my_pages=1000, total_pages=1000)
    if orders:
        opts.orders = [DayOrder("6/3/2026", 1000, [Portion(1000, [a.key() for a in firms], 4)], total=1000)]
    return case, opts


# ------------------------------------------------------------------ the arithmetic

def test_four_parties_at_immediate_exactly_and_by_the_page(s):
    """The user's example: $6.6125 a page. Exact: $6,612.50; the price a page to the cent: $6.61 x 1,000."""
    imm = speed(s, "Immediate")
    exact = quote(1000, imm, 4, True, "on", index_shared="each")
    by_hand = quote(1000, imm, 4, True, "on", index_shared="each", by_page=True)
    assert exact.prices == by_hand.prices == [(Fraction("6.6125"), 1000)]
    assert exact.per_party == Decimal("6612.50") and not exact.page_rounded
    assert by_hand.per_party == Decimal("6610.00") and by_hand.page_rounded
    assert by_hand.total == exact.total == Decimal("26450.00")  # (the work costs the same: only its share differs)
    assert by_hand.per_page == Decimal("6.61")


def test_the_price_a_page_rounds_to_the_nearest_cent_either_way(s):
    """$6.6175 a page (an original of $7.62) goes up to $6.62; half a cent goes up ($4.925 -> $4.93: four firms
    sharing 59 pages at Expedite)."""
    sp = Speed("Immediate", "7.62", "1.45", extras={"Email": "1.45", "Index": "1.45"})
    assert quote(1000, sp, 4, True, "on", by_page=True).per_party == Decimal("6620.00")
    assert quote(1000, sp, 4, True, "on").per_party == Decimal("6617.50")
    q = quote_shares([Share(59, 4, True)], speed(s, "Expedite"), by_page=True)
    assert q.prices == [(Fraction("4.925"), 59)] and q.per_party == Decimal("290.87")  # 59 x 4.93
    assert quote_shares([Share(59, 4, True)], speed(s, "Expedite")).per_party == Decimal("290.58")
    assert [to_cent(Fraction(x)) for x in ("6.6125", "6.6175", "4.925", "1.43333333", "6.30")] == \
        [Fraction(x) for x in ("6.61", "6.62", "4.93", "1.43", "6.30")]
    assert to_cent(Fraction(43, 30)) == Fraction("1.43")  # (a third of $4.30, exactly: 1.4333…)


def test_a_firm_with_pages_at_two_prices(s):
    """40 pages ordered alone ($6.30 a page) and 50 shared by 3 ($4.30 / 3 + $1 + $1 = $3.4333… a page), no index:
    by hand 40 x $6.30 + 50 x $3.43 = $423.50; exactly $423.666…, rounded up: $423.67."""
    reg = speed(s, "Regular")
    shares = [Share(40, 1), Share(50, 3)]
    q = quote_shares(shares, reg, by_page=True)
    assert q.prices == [(Fraction("6.30"), 40), (Fraction(103, 30), 50)]
    assert q.per_party == Decimal("423.50")
    assert quote_shares(shares, reg).per_party == Decimal("423.67")
    # (pages at one price, wherever they are, are counted together)
    assert quote_shares([Share(30, 1), Share(50, 3), Share(10, 1)], reg, by_page=True).prices == q.prices


def test_pages_ordered_together_at_different_speeds(s):
    """Queens's split rule: three firms on 60 pages, this one at Daily with another at Daily and one at Immediate
    (each Daily firm pays $6.50 / 3 of the original, and $1.25 / 3 of the judge's index), plus 25 pages it ordered
    alone. Its price a page: $2.1666… + 3 x $1.25 + $0.41666… = $6.3333… on the 60, $9.00 on the 25 (no index)."""
    shares = [Share(60, 3, True, "Daily", (("Smith Law", "Immediate"), ("Counsel & Counsel", "Daily"))),
              Share(25, 1, False, "Daily")]
    q = quote_ordered(shares, s.sheet(), split, by_page=True)
    assert q.prices == [(Fraction(19, 3), 60), (Fraction(9), 25)]
    assert q.per_party == Decimal("604.80")  # 60 x 6.33 + 25 x 9.00
    assert quote_ordered(shares, s.sheet(), split).per_party == Decimal("605.00")


def test_the_prices_a_page_add_up_to_the_exact_share(s):
    """However the pages were ordered (days with and without an index, shared by 1 to 5 firms, at one speed or
    several), the exact prices a page times their pages are the exact share, so the rounding rounds the real
    price; and the price a page to the cent is what each party pays."""
    rnd = random.Random(7)
    sheet = s.sheet()
    for _ in range(200):
        days = [rnd.choice((1, 7, 33, 49, 50, 60, 133)) for _ in range(rnd.randint(1, 3))]
        n, sp = rnd.randint(1, 5), rnd.choice(sheet.speeds)
        mode = rnd.choice(("each", "split"))
        whole = quote(days, sp, n, rnd.random() < 0.5, rnd.choice(("auto", "on", "off")), rnd.choice(("any", "each")),
                      index_shared=mode, by_page=True)
        assert sum(p * k for p, k in whole.prices) == Fraction(whole.total) / n
        assert whole.per_party == sum(to_cent(p) * k for p, k in whole.prices)
        flags = index_days(days, rule="each")
        shares = [Share(p, rnd.randint(1, 5), f) for p, f in zip(days, flags)]
        mine = quote_shares(shares, sp, rnd.random() < 0.5, mode == "split", by_page=True)
        assert sum(p * k for p, k in mine.prices) == mine.due
        assert mine.per_party == sum(to_cent(p) * k for p, k in mine.prices)
        names = [x.name for x in sheet.speeds]  # (with another firm on the pages at any speed, or none)
        ordered = [Share(x.pages, x.n, x.indexed, rnd.choice(names),
                         (("Smith Law", rnd.choice(names)),) if x.n > 1 else ()) for x in shares]
        q = quote_ordered(ordered, sheet, split, rnd.random() < 0.5, mode == "split", by_page=True)
        assert sum(p * k for p, k in q.prices) == q.due
        assert q.per_party == sum(to_cent(p) * k for p, k in q.prices)


# ------------------------------------------------------------------ the invoices, and how they say it

def test_each_firms_invoice_by_the_page_and_the_math_says_how(s):
    """Queens: the four firms committed to Immediate (the agreement form's speed). Rounded by the page, each
    invoice is $6,610.00; the math says how, under each firm's charges, and adds up what the firms pay together
    against what the work costs: $10.00 less."""
    case, opts = four_firms(s)
    assert {f.quotes[0].per_party for f in firm_invoices(case, s, opts)} == {Decimal("6612.50")}  # (exact)
    s.invoice_rounding = "page"
    firms = firm_invoices(case, s, opts)
    assert [f.quotes[0].per_party for f in firms] == [Decimal("6610.00")] * 4
    made = [(f, f"2026-00{i + 40}") for i, f in enumerate(firms)]
    html, plain = explain(made)
    assert f"    This firm pays: {SIX_61} = $6,610.00\n" in plain
    assert "    This firm's charges together: $6,612.50\n" in plain
    assert f"<b>This firm pays: {SIX_61}</b>" in html and "rounded up" not in plain
    assert together(made) == ["As ordered (Immediate): the 4 firms together pay $26,440.00 for work that costs "
                              "$26,450.00 (rounding each firm's price a page to the cent takes off $10.00)"]
    # the invoice's small print lists the charges, without a total they wouldn't add up to, nor how it was rounded
    assert _detail(firms[0].quotes[0]).endswith("Index: 1000 pp. × $1.45 + Judge's index: 1000 pp. × $1.45 ÷ 4 firms")
    # the firms side by side: what each pays, and how under it
    html, _ = explain(made, "firms")
    assert "Each firm pays (its price a page rounded to the cent)" in html
    assert "<b>$6,610.00</b><br><span class='muted'>1,000 × $6.61</span>" in html


def test_the_invoice_itself_doesnt_say_how_it_was_rounded(s, tmp_path):
    """The invoice PDF, with granular detail: $6.61 a page and $6,610.00 due, and not a word on rounding (no
    "$6.6125", no "rounded", no $6,612.50 its charges would add up to)."""
    s.invoice_rounding = "page"
    case, opts = four_firms(s)
    opts.detail = True
    path = make_invoices(case, s, tmp_path, opts, Ledger(tmp_path / "r.db"))[0]
    with pymupdf.open(path) as doc:
        text = doc[0].get_text()
        fields = {w.field_name: w.field_value for w in doc[0].widgets()}
    assert "Original: 1000 pp. × $7.60 ÷ 4 " in " ".join(text.split())  # ("firms" comes out as a ligature)
    assert fields["per page Immediate"] == "$6.61" and "$6,610.00" in fields.values()
    for word in ("rounded", "6.6125", "6,612.50"):
        assert word not in text and not any(word in v for v in fields.values()), word


@pytest.mark.usefixtures("split_orders_choose")
def test_firms_choosing_their_speed_by_the_page(s):
    """Where firms choose a speed from their invoices (a price for each speed offered): each is rounded by the
    page. Regular and Immediate: $4.30 / 4 + 3 x $1 + $1 / 4 = $4.325 a page -> $4.33, $4,330.00."""
    s.invoice_speeds = ["Regular", "Immediate"]
    s.invoice_rounding = "page"
    case, opts = four_firms(s)
    f = firm_invoices(case, s, opts)[0]
    assert [(q.speed, q.per_party) for q in f.quotes] == [("Regular", Decimal("4330.00")),
                                                          ("Immediate", Decimal("6610.00"))]
    assert together([(x, "") for x in firm_invoices(case, s, opts)])[0] == (
        "Regular: the 4 firms together pay $17,320.00 for work that costs $17,300.00 (rounding each firm's price a "
        "page to the cent adds $20.00)")


def test_the_invoice_made_the_old_way_split_by_the_page(s):
    """An invoice for the whole job, split 4 ways (no orders): each party pays $6.61 a page, and the math says so.
    The small print reads as it always has."""
    s.invoice_rounding = "page"
    case, opts = four_firms(s, orders=False)
    f = firm_invoices(case, s, opts)[0]
    (q,) = f.quotes
    assert not q.share and q.per_party == Decimal("6610.00")
    assert _detail(q).endswith(" = $26,450.00, split 4 ways")
    html, plain = explain([(f, "2026-0050")])
    assert "    Total: $26,450.00\n" in plain and f"    Each party pays: {SIX_61} = $6,610.00\n" in plain
    assert f"<b>Each party pays: {SIX_61}</b>" in html


def test_whole_cents_say_nothing_about_rounding(s):
    """Two firms at Regular: $4.30 / 2 + 3 x $1 + $1 / 2 = $5.65 a page, whole cents: the same either way, and
    the math reads as it always has."""
    s.invoice_speeds = ["Regular"]
    case = make_case(ROE, [Attorney(name="Alex B. Counsel", checked=True), Attorney(name="Dana Smith", checked=True)])
    opts = InvoiceOpts(60, 2, days=[("6/3/2026", 60)])
    before = explain([(firm_invoices(case, s, opts)[0], "x")])
    s.invoice_rounding = "page"
    f = firm_invoices(case, s, opts)[0]
    assert f.quotes[0].per_party == Decimal("339.00") and not f.quotes[0].page_rounded
    assert explain([(f, "x")]) == before


# ------------------------------------------------------------------ the setting

def test_the_rounding_setting_is_kept_and_checked():
    """"exact" by default; "page" is kept; a value it can't be loads as "exact"."""
    assert Settings().invoice_rounding == "exact"
    s = Settings()
    for saved, loaded in (("page", "page"), ("exact", "exact"), ("higher", "exact"), ("", "exact")):
        s.path.write_text(json.dumps({"settings_version": Settings.settings_version, "invoice_rounding": saved}),
                          encoding="utf-8")
        assert Settings.load().invoice_rounding == loaded, saved


def test_rounding_in_the_settings_window(qt):
    """Settings -> Invoice -> Rounding shows the setting and saves the choice."""
    from minute_filler.gui.dialogs import SettingsDialog
    s = Settings.load()
    dlg = SettingsDialog(s)
    assert dlg.i_rounding.currentData() == "exact"
    assert [dlg.i_rounding.itemData(i) for i in range(dlg.i_rounding.count())] == ["exact", "page"]
    assert "$6.6125" in dlg.i_rounding.toolTip()
    dlg.i_rounding.setCurrentIndex(dlg.i_rounding.findData("page"))
    dlg.accept()
    assert Settings.load().invoice_rounding == "page"
    assert SettingsDialog(Settings.load()).i_rounding.currentData() == "page"


def test_the_excerpts_window_says_how_each_invoice_is_rounded(qt):
    """Under the Excerpts window's table, "Each firm's invoice" says how its amounts were rounded."""
    from minute_filler.gui.excerpts import ExcerptsWindow
    s = pat_settings()
    p = SimpleNamespace(groups=[], ordered_groups=[], ordered={}, firms=[("smith law", {"Regular": Decimal("1.00")})],
                        committed=set(), speeds=["Regular"])
    windows = [ExcerptsWindow(s, lambda: None)]
    assert "<b>Each firm's invoice</b> (rounded up to the cent)" in windows[0]._summary(p, ["Regular"])
    s.invoice_rounding = "page"
    windows.append(ExcerptsWindow(s, lambda: None))
    text = windows[1]._summary(p, ["Regular"])
    for w in windows:
        w.deleteLater()
    assert "<b>Each firm's invoice</b> (its price a page rounded to the cent)" in text
