"""The two ways Queens may bill pages firms ordered together at different speeds (courthouses.base.SplitRule,
courthouses/queens_supreme_civil/billing.py), chosen in Settings -> Invoice -> "Split invoices"
(Settings.invoice_split_rule): Make-Whole Split, the default (the slower firms pay as if every firm had ordered
their speed, the fastest the rest), and Same-Speed Split (every firm, the fastest too, pays as if every firm had
ordered its speed).

The numbers are the reporter's comparer workbook's ("Transcript_Billing_Calculator - comparer.xlsx"): its sample
job, 100 pages with an index, Attorney A at Regular and Attorney B at Daily, is $565.00 and $885.00 under
Make-Whole, $565.00 and $762.50 under Same-Speed, with the bundled Sample Rates (the workbook's own). Then the
rules as a choice: the setting, its note on the invoice, the invoices and their math (with "Who pays what a page",
invoice_math.split_pages), the Settings window, and a made-up third rule to show a new one plugs in without other
changes. Then a job billed one way billed that way again (batch.Job.split_rule): made again, its days joined or
billed together, opened again from its records (batch.billed_split_rule). All names are made up."""
import json
from decimal import Decimal
from fractions import Fraction

import pytest

from minute_filler import courthouses
from minute_filler.courthouses.base import Part, Party, SplitRule
from minute_filler.courthouses.queens_supreme_civil.billing import MAKE_WHOLE, RULES, SAME_SPEED
from minute_filler.invoice_calc import Share, quote_ordered
from minute_filler.settings import Settings

from helpers import pat_settings
from test_mixed_speeds import A, B, bills, excerpt_example, typed_day


@pytest.fixture
def sheet():
    return pat_settings().sheet()


def priced(sheet, rule, speed, others, pages=10, indexed=False):
    """One firm's ordered quote for `pages` pages it ordered at `speed` with the other firms ((name, speed) each)."""
    return quote_ordered([Share(pages, 1 + len(others), indexed, speed, tuple(others))], sheet, rule)


# ------------------------------------------------------------------ the rules


def test_queens_offers_both_ways_make_whole_first():
    assert courthouses.split_rules() == RULES == (MAKE_WHOLE, SAME_SPEED)
    assert courthouses.split_rule() is MAKE_WHOLE and courthouses.split_rule("") is MAKE_WHOLE
    assert courthouses.split_rule("same_speed") is SAME_SPEED
    assert courthouses.split_rule("layered") is MAKE_WHOLE  # (one it doesn't have: the default)
    assert all(isinstance(r, SplitRule) and r.label and r.tip and r.summary and r.note and r.adds_up
               and r.invoice_note for r in RULES)


def test_same_speed_every_firm_pays_as_if_all_had_ordered_its_speed():
    daily = Party("Counsel & Counsel", "Daily", Fraction("6.50"), 2)
    immediate = Party("Smith Law", "Immediate", Fraction("7.60"), 3)
    slow, fast = SAME_SPEED.split([daily, immediate], 0), SAME_SPEED.split([daily, immediate], 1)
    assert slow.per_page == Fraction("3.25") and fast.per_page == Fraction("3.80")
    assert slow.per_page + fast.per_page < Fraction("7.60")  # (each part at its own speed)
    assert fast.steps == (("This firm ordered Immediate, so it pays as if both firms had ordered Immediate: "
                           "$7.60 ÷ 2 = $3.80 a page", Fraction("3.80")),)


def test_one_speed_is_the_usual_split_either_way():
    parties = [Party(f"Firm {i}", "Daily", Fraction("6.50"), 2) for i in range(3)]
    for i in range(3):
        assert MAKE_WHOLE.split(parties, i) == SAME_SPEED.split(parties, i)
        assert SAME_SPEED.split(parties, i).per_page == Fraction("6.50") / 3


def test_a_slower_firm_pays_the_same_either_way():
    """Only the fastest firms' part differs; a slower firm's is capped at the fastest speed's price under both (an
    index priced lower at a faster speed)."""
    speeds = [("Regular", "4.30", 0), ("Daily", "6.50", 2), ("Immediate", "7.60", 3), ("Cheap fast", "1.00", 4)]
    for mine in range(3):
        for top in range(mine + 1, 4):
            parties = [Party("This firm", speeds[mine][0], Fraction(speeds[mine][1]), speeds[mine][2]),
                       Party("Other", speeds[top][0], Fraction(speeds[top][1]), speeds[top][2])]
            assert MAKE_WHOLE.split(parties, 0) == SAME_SPEED.split(parties, 0)


def test_the_words_count_the_firms():
    """Two firms are "both firms", more are "all 3 firms", under either rule."""
    parties = [Party("A", "Daily", Fraction("6.50"), 2), Party("B", "Daily", Fraction("6.50"), 2),
               Party("C", "Immediate", Fraction("7.60"), 3)]
    for rule in RULES:
        assert "as if all 3 firms had ordered Daily" in rule.split(parties, 0).steps[0][0]
        assert "as if both firms had ordered Daily" in rule.split(parties[1:], 0).steps[0][0]
    assert "as if all 3 firms had ordered Immediate" in SAME_SPEED.split(parties, 2).steps[0][0]


def test_a_slower_speed_priced_the_same_as_the_fastest_is_not_billed_for_less():
    """A slower speed at the fastest's price (an index of $1.25 at both): its share is its own, as usual; only one
    priced higher than the fastest's is worked out from the fastest's, which "costs less"."""
    same = [Party("A", "Daily", Fraction("1.25"), 2), Party("B", "Immediate", Fraction("1.25"), 3)]
    higher = [Party("A", "Daily", Fraction("1.25"), 2), Party("B", "Immediate", Fraction("1.00"), 3)]
    for rule in RULES:
        assert rule.split(same, 0).steps[0][0] == ("This firm ordered Daily, so it pays as if both firms had "
                                                   "ordered Daily: $1.25 ÷ 2 = $0.625 a page")
        assert rule.split(higher, 0).steps[0][0] == ("This firm ordered Daily, but Immediate, the fastest ordered, "
                                                     "costs less: $1.00 ÷ 2 = $0.50 a page")


# ------------------------------------------------------------------ the comparer workbook


@pytest.mark.parametrize("rule, regular, daily", [(MAKE_WHOLE, "565.00", "885.00"), (SAME_SPEED, "565.00", "762.50")],
                         ids=["make_whole", "same_speed"])
def test_the_comparer_workbooks_sample_job(sheet, rule, regular, daily):
    """100 pages, an index: A at Regular pays (4.30 + 1.00) ÷ 2 + 3.00 = $5.65 a page either way; B at Daily the
    rest of one original and judge's index at Daily (Make-Whole: $8.85 a page) or (6.50 + 1.25) ÷ 2 + 3.75 = $7.625
    (Same-Speed). The workbook's Compare Methods tab: together $1,450.00 or $1,327.50."""
    a = priced(sheet, rule, "Regular", [("Attorney B", "Daily")], 100, indexed=True)
    b = priced(sheet, rule, "Daily", [("Attorney A", "Regular")], 100, indexed=True)
    assert (a.per_party, b.per_party) == (Decimal(regular), Decimal(daily))
    assert a.rule is rule and b.rule is rule and a.mixed


@pytest.mark.parametrize("rule, immediate", [(MAKE_WHOLE, "72.50"), (SAME_SPEED, "67.00")], ids=["make_whole",
                                                                                                    "same_speed"])
def test_the_worked_example_either_way(sheet, rule, immediate):
    """10 pages, no index: Daily $57.50 either way; Immediate $72.50 (Make-Whole) or $67.00 (Same-Speed)."""
    assert priced(sheet, rule, "Daily", [("Smith Law", "Immediate")]).per_party == Decimal("57.50")
    assert priced(sheet, rule, "Immediate", [("Counsel & Counsel", "Daily")]).per_party == Decimal(immediate)


# ------------------------------------------------------------------ the setting


def test_the_setting_is_kept_and_checked():
    """"" (the courthouse's default, Make-Whole) at first; a rule's key is kept; one the courthouse doesn't have
    loads as the default."""
    assert Settings().invoice_split_rule == ""
    s = Settings()
    for saved, loaded in (("same_speed", "same_speed"), ("make_whole", "make_whole"), ("layered", ""), (3, "")):
        s.path.write_text(json.dumps({"settings_version": Settings.settings_version, "invoice_split_rule": saved}),
                          encoding="utf-8")
        assert Settings.load().invoice_split_rule == loaded, saved


def notes(s) -> list[str]:
    return [r["text"] for r in s.invoice_texts if r["when"] == "mixed_speeds"]


def test_the_invoice_note_follows_the_rule_unless_reworded():
    s = Settings()
    assert notes(s) == [MAKE_WHOLE.invoice_note]
    s.use_split_rule("same_speed")
    assert s.invoice_split_rule == "same_speed" and notes(s) == [SAME_SPEED.invoice_note]
    s.use_split_rule("make_whole")
    assert notes(s) == [MAKE_WHOLE.invoice_note]
    next(r for r in s.invoice_texts if r["when"] == "mixed_speeds")["text"] = "Faster costs more."
    s.use_split_rule("same_speed")
    assert notes(s) == ["Faster costs more."]  # (the user's own words are kept)
    s.use_split_rule("layered")
    assert s.invoice_split_rule == ""


# ------------------------------------------------------------------ the invoices and their math


@pytest.fixture
def s(tmp_path):
    s = pat_settings()
    s.output_dir = str(tmp_path / "out")
    s.records_dir = str(tmp_path / "records")
    s.invoice_include_index = False
    s.save_math = "off"
    return s


def test_the_invoices_bill_the_rule_chosen(s):
    """Pages 1-60 Counsel & Counsel at Daily with Smith Law at Immediate, 61-120 Smith Law alone: Counsel & Counsel
    $345.00 either way; Smith Law 60 x (4.35 + 2.90) + 60 x 10.50 = $1,065.00, or 60 x (3.80 + 2.90) + 630 =
    $1,032.00."""
    assert bills(s, excerpt_example()) == {A: [("Daily", Decimal("345.00"))], B: [("Immediate", Decimal("1065.00"))]}
    s.invoice_split_rule = "same_speed"
    assert bills(s, excerpt_example()) == {A: [("Daily", Decimal("345.00"))], B: [("Immediate", Decimal("1032.00"))]}


def test_the_math_says_how_in_the_rules_words(s):
    from minute_filler.batch import joint_invoice
    from minute_filler.invoice import _detail, firm_invoices
    from minute_filler.invoice_math import explain, page_rates, together
    s.invoice_split_rule = "same_speed"
    case, opts = joint_invoice([excerpt_example()])
    firms = firm_invoices(case, s, opts)
    made = [(f, "") for f in firms]
    html, plain = explain(made)
    assert SAME_SPEED.note in plain and MAKE_WHOLE.note not in plain and "Billed once, at" not in plain
    assert ("60 pages ordered with Alex B. Counsel (Daily): 60 × $3.80 = $228.00. At Immediate, the fastest speed "
            "ordered, it is $7.60 a page. This firm ordered Immediate, so it pays as if both firms had ordered "
            "Immediate: $7.60 ÷ 2 = $3.80 a page.") in plain
    assert SAME_SPEED.adds_up in together(made)
    assert f"Pages ordered together at different speeds: {SAME_SPEED.summary}." in page_rates(firms)
    smith = next(f for f in firms if f.atty.key() == B)
    assert "60 pp. × $3.80 (your part, at the speed you ordered)" in _detail(smith.quotes[0])


@pytest.mark.parametrize("rule", ["make_whole", "same_speed"])
def test_the_firms_side_by_side_say_the_original_is_billed_once_whatever_the_rule(s, rule):
    """Both firms on all 120 pages (one row each): the firms' layout says the original is "Billed once, divided by
    speed" under either rule. It went by Make-Whole's words, "Billed once, at", and said "Each firm splits this
    cost" under Same-Speed (the sweep of 2026-10-21)."""
    from minute_filler.batch import joint_invoice
    from minute_filler.invoice import firm_invoices
    from minute_filler.invoice_math import ONCE, SPLITS, explain
    s.invoice_split_rule = rule
    job = excerpt_example()
    job.portions = [(120, [A, B])]
    case, opts = joint_invoice([job])
    html, _ = explain([(f, "") for f in firm_invoices(case, s, opts)], "firms")
    original = html[html.index(">Original<"):]
    assert original.index(ONCE) < original.index("</tr>") and SPLITS not in original[:original.index("</tr>")]


def test_an_invoice_s_math_keeps_the_rule_it_was_billed_by(s):
    """The words come from the rule each stretch was priced with: changing the setting afterwards doesn't reword
    the math of invoices already made."""
    from minute_filler.batch import joint_invoice
    from minute_filler.invoice import firm_invoices
    from minute_filler.invoice_math import explain
    case, opts = joint_invoice([excerpt_example()])
    made = [(f, "") for f in firm_invoices(case, s, opts)]
    s.invoice_split_rule = "same_speed"
    assert MAKE_WHOLE.note in explain(made)[1]


# ------------------------------------------------------------------ a third way plugs in


class EvenSplit(SplitRule):
    """Made up: every firm pays an equal part of the original at the fastest speed."""
    key, label, tip, summary = "even", "Even Split", "Equal parts.", "equal parts"
    note, adds_up, invoice_note = "Split evenly.", "They add up to one.", "You pay an equal part."

    def split(self, parties, me):
        top = max(parties, key=lambda p: p.rank)
        return Part(top.rate / len(parties), ((f"{top.rate} ÷ {len(parties)}", top.rate / len(parties)),))

    def billed(self, speed, rate):
        return f"Even, at {speed}"

    def your_part(self, speed):
        return "an equal part"

    def run_note(self, speed):
        return "equal parts"


def test_a_new_rule_is_a_subclass_and_nothing_else_changes(sheet):
    q = priced(sheet, EvenSplit(), "Daily", [("Smith Law", "Immediate")])
    assert q.per_party == Decimal("63.00")  # 10 x (7.60 ÷ 2 + 2.50)
    assert q.rule.key == "even"
    with pytest.raises(TypeError):
        type("Half", (SplitRule,), {"key": "half"})()  # (a rule must say how it splits, and in what words)


def test_a_profile_must_name_a_tuple_of_rules():
    """One rule (or anything else) named where the tuple goes is the ValueError the profile's check says, not a
    TypeError from deep inside (the sweep of 2026-10-21)."""
    from dataclasses import replace
    billing = "minute_filler.courthouses.queens_supreme_civil.billing"
    for name in ("MAKE_WHOLE", "_all"):
        with pytest.raises(ValueError, match="a tuple of SplitRules"):
            replace(courthouses.current(), split_rules=f"{billing}:{name}").split_rules_impl()
    assert replace(courthouses.current(), split_rules="", speeds_together=1).split_rules_impl() == ()


# ------------------------------------------------------------------ the Settings window


def test_split_invoices_in_the_settings_window(qt):
    """Settings -> Invoice -> Split invoices lists the courthouse's rules, each with its tooltip, saves the choice
    and rewords the invoice's note."""
    from PySide6.QtCore import Qt
    from minute_filler.gui.dialogs import SettingsDialog
    s = Settings.load()
    dlg = SettingsDialog(s)
    box = dlg.i_split
    assert box.currentData() == "make_whole"
    assert [box.itemData(i) for i in range(box.count())] == ["make_whole", "same_speed"]
    assert box.itemData(1, Qt.ToolTipRole) == SAME_SPEED.tip
    box.setCurrentIndex(box.findData("same_speed"))
    dlg.accept()
    again = Settings.load()
    assert again.invoice_split_rule == "same_speed" and notes(again) == [SAME_SPEED.invoice_note]
    assert SettingsDialog(again).i_split.currentData() == "same_speed"


def test_saving_settings_keeps_the_default_as_the_default(qt):
    """Settings saved without touching Split invoices keeps "" (the courthouse's default, whatever it is then),
    not the default's key; chosen by name, it is kept by name (the sweep of 2026-10-21)."""
    from minute_filler.gui.dialogs import SettingsDialog
    SettingsDialog(Settings.load()).accept()
    assert Settings.load().invoice_split_rule == ""
    s = Settings.load()
    s.invoice_split_rule = "make_whole"
    s.save()
    SettingsDialog(Settings.load()).accept()
    assert Settings.load().invoice_split_rule == "make_whole"


# ------------------------------------------------------------------ the math: who pays what a page
# (the user, 2026-10-21: "show it clearly like the compare sheet does": how much each side pays a page, section by
# section; the comparer workbook's 7B, "Who pays what per page in each stretch")


def made_of(s, *jobs):
    from minute_filler.batch import joint_invoice
    from minute_filler.invoice import firm_invoices
    case, opts = joint_invoice(list(jobs))
    return [(f, "") for f in firm_invoices(case, s, opts)]


@pytest.mark.parametrize("rule, smith, together", [("make_whole", "7.25", "13.00"), ("same_speed", "6.70", "12.45")])
def test_the_math_says_what_each_firm_pays_a_page_on_pages_ordered_at_different_speeds(s, rule, smith, together):
    """Pages 1-60 (Counsel & Counsel at Daily, Smith Law at Immediate; no index): each firm's part of each charge
    a page and in all, the firms together, once though both invoices have those pages. Smith Law's pages 61-120,
    ordered alone, aren't in it."""
    from minute_filler.invoice_math import SPLIT_HEADING, explain, split_pages
    s.invoice_split_rule = rule
    made = made_of(s, excerpt_example())
    (section,) = split_pages(made)
    assert section.label == "60 pages ordered by Alex B. Counsel (Daily) and Dana Smith (Immediate)"
    html, plain = explain(made)
    original = {"make_whole": "$4.35", "same_speed": "$3.80"}[rule]
    assert (f"{SPLIT_HEADING}\n  60 pages ordered by Alex B. Counsel (Daily) and Dana Smith (Immediate):\n"
            "    Alex B. Counsel, at Daily: Original $3.25 + Copy $1.25 + E-mailed copy $1.25 = $5.75 a page\n"
            f"    Dana Smith, at Immediate: Original {original} + Copy $1.45 + E-mailed copy $1.45 = ${smith} a page\n"
            f"    Together: ${together} a page; for the 60 pages: ${Decimal(together) * 60:,.2f}\n") in plain
    assert f"<h2>{SPLIT_HEADING}</h2>" in html and f"<b>${smith}</b>" in html
    assert explain(made, "firms")[0].count(f"<h2>{SPLIT_HEADING}</h2>") == 1
    # one firm's invoice alone says what the other firm pays too
    alone = [m for m in made if m[0].atty.key() == A]
    assert split_pages(alone)[0].total == section.total


def test_each_stretch_of_other_firms_is_a_section_of_its_own(s):
    """Counsel & Counsel with Smith Law on pages 1-60, Sam Poe (Regular) with Smith Law on 61-120: two sections,
    each with its own firms and prices."""
    from test_mixed_speeds import C, poe, counsel, smith
    from minute_filler.invoice_math import split_pages
    job = typed_day(attorneys=[counsel(), smith(), poe()])
    job.portions = [(60, [A, B]), (120, [B, C])]
    job.speeds = {A: "Daily", B: "Immediate", C: "Regular"}
    got = [(x.label, [(p.who, p.total) for p in x.firms]) for x in split_pages(made_of(s, job))]
    assert got == [("60 pages ordered by Alex B. Counsel (Daily) and Dana Smith (Immediate)",
                    [("Alex B. Counsel", Fraction("5.75")), ("Dana Smith", Fraction("7.25"))]),
                   # Sam Poe: $4.30 ÷ 2 + $2.00; Smith Law the rest of $7.60, $5.45, + $2.90
                   ("60 pages ordered by Dana Smith (Immediate) and Sam Poe (Regular)",
                    [("Dana Smith", Fraction("8.35")), ("Sam Poe", Fraction("4.15"))])]


def billed_a_page(f) -> Fraction:
    """What a firm's own invoice bills a page of its pages ordered together at different speeds, every charge."""
    return sum((x.per_page for q in f.quotes for l in q.lines for x in l.stretches if x.parts), Fraction(0))


@pytest.mark.parametrize("rule", ["make_whole", "same_speed"])
def test_each_firm_on_pages_ordered_at_different_speeds_pays_what_its_invoice_bills(s, rule):
    """Parties 3, two firms named (Counsel & Counsel at Daily, Smith Law at Immediate, 120 pages): each invoice
    takes the party not named to order its own firm's speed, so the first invoice's view of Smith Law's part isn't
    what Smith Law's invoice bills. Each firm's row is its own invoice's; the party not named is said under the
    table, neither a row nor in the total (the sweep of 2026-10-21: "another party" was a row, and Smith Law's
    amounts were Counsel & Counsel's view)."""
    from minute_filler.invoice_math import explain, split_pages
    s.invoice_split_rule = rule
    job = typed_day()
    job.speeds = {A: "Daily", B: "Immediate"}
    job.parties = 3
    made = made_of(s, job)
    (sec,) = split_pages(made)
    assert [p.who for p in sec.firms] == ["Alex B. Counsel", "Dana Smith"] and sec.unnamed == 1
    by_who = {f.atty.label(): f for f, _ in made}
    assert [p.total for p in sec.firms] == [billed_a_page(by_who[p.who]) for p in sec.firms]
    assert sec.total == sum(billed_a_page(f) for f, _ in made)
    assert "another party" not in sec.label
    plain = explain(made)[1]
    assert "Also on these pages: 1 more party, counted by Parties but not named." in plain


def test_a_charge_one_speed_has_no_price_for_is_still_in_the_other_firms_row(s):
    """A sheet with no Index price at Daily (Immediate has one), the index on: Counsel & Counsel's invoice has no
    index line, Smith Law's has; Smith Law's row of the section still has its index (the sweep of 2026-10-21: the
    section, from Counsel & Counsel's invoice, left it out)."""
    import copy
    from minute_filler.invoice_math import split_pages
    s.invoice_include_index = True
    sheet = copy.deepcopy(s.sheet())
    for sp in sheet.speeds:
        if sp.name == "Daily":
            sp.extras = {k: ("" if k.lower() == "index" else v) for k, v in sp.extras.items()}
    s.sheet = lambda: sheet
    job = typed_day(60)
    job.speeds = {A: "Daily", B: "Immediate"}
    made = made_of(s, job)
    (sec,) = split_pages(made)
    by_who = {f.atty.label(): f for f, _ in made}
    smith = sec.firms[1]
    assert smith.who == "Dana Smith" and any("ndex" in c for c, _ in smith.charges)
    assert smith.total == billed_a_page(by_who["Dana Smith"])


def test_the_section_says_its_prices_are_exact_when_the_invoices_round_each_price(s):
    """Rounding "the price a page", three firms on 90 pages under Same-Speed ($4.6667 a page each at Daily): the
    section says its prices are exact and the invoices round theirs."""
    from test_mixed_speeds import C, poe, counsel, smith
    from minute_filler.invoice_math import SPLIT_EXACT, explain
    s.invoice_split_rule, s.invoice_rounding = "same_speed", "page"
    job = typed_day(90, attorneys=[counsel(), smith(), poe()])
    job.speeds = {A: "Daily", B: "Immediate", C: "Daily"}
    html_text, plain = explain(made_of(s, job))
    assert SPLIT_EXACT in plain
    s.invoice_rounding = "total"
    assert SPLIT_EXACT not in explain(made_of(s, job))[1]


def test_the_rate_of_a_charge_in_parts_is_what_a_page_of_it_comes_to(s):
    """Smith Law with Counsel & Counsel (Daily) on pages 1-60 and with Sam Poe (Regular) on 61-120, Same-Speed:
    the Original's row "In parts" has a rate that, times its pages, is its cost; a part of a cent shows as it is
    (the sweep of 2026-10-21: $7.60 for a cost of $780, and $6.87 for $6.8666…)."""
    from test_mixed_speeds import C, poe, counsel, smith
    from minute_filler.invoice_math import IN_PARTS, _speed_table, rows
    s.invoice_split_rule = "same_speed"
    job = typed_day(attorneys=[counsel(), smith(), poe()])
    job.portions = [(60, [A, B]), (120, [B, C])]
    job.speeds = {A: "Daily", B: "Immediate", C: "Regular"}
    f = next(f for f, _ in made_of(s, job) if f.atty.key() == B)
    (row,) = [r for r in rows(f.quotes[0]) if r.label == "Original" and r.how == IN_PARTS]
    assert row.rate * 120 == row.cost
    job = typed_day(60, attorneys=[counsel(), smith(), poe()])
    job.speeds = {A: "Daily", B: "Immediate", C: "Daily"}
    f = next(f for f, _ in made_of(s, job) if f.atty.key() == A)
    assert "$6.8667…" in _speed_table(f.quotes[0])


@pytest.mark.parametrize("rule, rate", [("make_whole", "7.60"), ("same_speed", "7.05")])
def test_the_rate_of_a_charge_billed_once_is_what_the_firms_parts_come_to(s, rule, rate):
    """The table's Rate and Cost of the original on pages ordered at different speeds: what the firms' parts add
    up to, one original at Immediate under Make-Whole, $3.25 + $3.80 under Same-Speed (it showed $7.60 either
    way)."""
    from minute_filler.invoice_math import rows
    s.invoice_split_rule = rule
    f = next(f for f, _ in made_of(s, excerpt_example()) if f.atty.key() == A)
    (row,) = [r for r in rows(f.quotes[0]) if r.label == "Original"]
    assert (row.rate, row.cost) == (Decimal(rate), Decimal(rate) * 60)


# ------------------------------------------------------------------ billed one way, billed that way again
# (the user, 2026-10-21: "If a job was calculated one way, it should be left alone that way")


def test_a_job_keeps_the_rule_it_was_billed_by(s, tmp_path):
    """Generate all bills the job by the rule in Settings and keeps it (Job.split_rule, and its records' origin):
    Settings changed afterwards, the job made again or opened again from its record is billed the same way."""
    from minute_filler.batch import billed_split_rule, fill_jobs, job_from_origin, job_origin
    from minute_filler.deliver import ledger_for
    job = excerpt_example()
    assert job.split_rule == ""
    fill_jobs([job], s, outputs=["invoice"])
    assert job.split_rule == "make_whole" and job_origin(job)["job"]["split_rule"] == "make_whole"
    s.invoice_split_rule = "same_speed"
    assert bills(s, job)[B] == [("Immediate", Decimal("1065.00"))]  # (Make-Whole still)
    lg = ledger_for(s)
    origin = next(a.origin for a in lg.activity() if a.kind == "invoice")
    again = job_from_origin(json.loads(origin), s, billed_split_rule(origin, lg))
    assert again.split_rule == "make_whole" and again.invoice_opts().split_rule == "make_whole"
    new = excerpt_example()  # (a job not billed yet: as Settings say now)
    assert bills(s, new)[B] == [("Immediate", Decimal("1032.00"))]


def test_a_record_says_which_rule_it_was_billed_by(s):
    """An older invoice's record has none: before 2.9.0 (published 2026-10-21, 11:11) it was billed by the
    courthouse's first rule (the only one), and opened again it is billed so again; one of 2.9.0's (either rule,
    none kept) as Settings say; a record of something else (an agreement) as Settings say; an unknown rule (or "")
    as Settings say. Ledger.invoiced_from tells an invoice's record, and when it was made (the reviews of
    2026-10-21: an agreement's record had come back billed by the first rule, and so had 2.9.0's own invoices)."""
    from minute_filler.batch import billed_split_rule, fill_jobs, recorded_split_rule
    from minute_filler.deliver import ledger_for
    old, that_morning, new = "2026-10-01T14:05:00", "2026-10-21T09:00:00", "2026-10-21T16:00:00"
    assert [recorded_split_rule(None, when) for when in ("", old, that_morning, new)] == \
        ["", "make_whole", "make_whole", ""]
    assert [recorded_split_rule(v, new) for v in ("same_speed", "layered", "")] == ["same_speed", "", ""]
    lg = ledger_for(s)
    # an invoice of several days whose documents are gone: opened as one job, billed as the invoice was
    assert billed_split_rule(json.dumps({"joint": True, "split_rule": "same_speed"}), lg) == "same_speed"
    assert billed_split_rule(json.dumps({"job": {"parties": 2}}), lg) == ""  # (an older record, no invoice of it)
    assert billed_split_rule("not JSON", lg) == billed_split_rule("[]", lg) == ""
    job = excerpt_example()
    fill_jobs([job], s, outputs=["agreement", "invoice"])
    kinds = {a.kind: a for a in lg.activity()}
    assert lg.invoiced_from(kinds["invoice"].origin) == kinds["invoice"].ts
    assert lg.invoiced_from(json.dumps({"job": {"parties": 2}})) == "" and lg.invoiced_from("") == ""
    # the agreement of the run keeps the job's rule from before it (none): its invoice's record says the rule
    assert json.loads(kinds["agreement"].origin)["job"]["split_rule"] == ""
    s.invoice_split_rule = "same_speed"
    assert [billed_split_rule(kinds[k].origin, lg) for k in ("invoice", "agreement")] == ["make_whole"] * 2


def test_a_job_billed_keeps_its_rule_in_the_records_of_later_files(s):
    """Billed by Make-Whole, then an agreement made again another day (its record not the invoice's), Settings
    now Same-Speed: opened again from that agreement, the job is billed by Make-Whole still (the review of the
    sweep's fixes, 2026-10-21: only a record the same as an invoice's kept it)."""
    from minute_filler.batch import billed_split_rule, fill_jobs, job_from_origin
    from minute_filler.deliver import ledger_for
    job = excerpt_example()
    fill_jobs([job], s, outputs=["invoice"])
    job.case.set("judge", "Hon. Pat Doe", "user")  # (something changed since: a record of its own)
    fill_jobs([job], s, outputs=["agreement"])
    s.invoice_split_rule = "same_speed"
    lg = ledger_for(s)
    later = next(a.origin for a in lg.activity() if a.kind == "agreement")
    assert not lg.invoiced_from(later)
    assert job_from_origin(json.loads(later), s, billed_split_rule(later, lg)).split_rule == "make_whole"


def test_an_agreement_made_when_the_invoice_failed_keeps_no_rule(s, monkeypatch):
    """Agreement and invoice made in one run, the invoice failing (open in another program): nothing was billed,
    so the agreement's record keeps no rule, and opened again from it the job is billed as Settings say by then (the
    sweep of 2026-10-21: it kept the rule the invoice was about to be billed by)."""
    from minute_filler import invoice
    from minute_filler.batch import billed_split_rule, fill_jobs
    from minute_filler.deliver import ledger_for

    def locked(*a, **k):
        raise PermissionError("the invoice is open in another program")

    s.invoice_split_rule = "same_speed"
    monkeypatch.setattr(invoice.Invoices, "make", staticmethod(locked))
    job = excerpt_example()
    fill_jobs([job], s, outputs=["agreement", "invoice"])
    assert "PermissionError" in job.error and job.split_rule == ""
    lg = ledger_for(s)
    agreement = next(a for a in lg.activity() if a.kind == "agreement")
    assert json.loads(agreement.origin)["job"]["split_rule"] == ""
    s.invoice_split_rule = "make_whole"
    assert billed_split_rule(agreement.origin, lg) == ""


def test_no_invoice_made_no_rule_kept(s, monkeypatch):
    """A run that makes no invoice (it failed before any: a file open in another program, say) keeps no rule: the
    job is billed as Settings say when it is (the review of 2026-10-21: the rule was kept before anything was
    billed)."""
    from minute_filler import batch

    def locked(*a, **k):
        raise PermissionError("the invoice is open in another program")

    monkeypatch.setattr(batch, "generate", locked)
    job = excerpt_example()
    batch.fill_jobs([job], s, outputs=["invoice"])
    assert "PermissionError" in job.error and job.split_rule == ""
    monkeypatch.undo()
    batch.fill_jobs([job], s, outputs=["invoice"])  # (made this time: kept)
    assert job.split_rule == "make_whole"


def two_days_billed_together(s):
    """Two days of the excerpt example (6/3 and 6/4), billed on one invoice (or the test is skipped)."""
    from minute_filler.batch import invoice_groups
    days = [excerpt_example(), excerpt_example()]
    days[1].case.set("dates", "6/4/2026", "user")
    if len(invoice_groups(days, s)[0]) < 2:
        pytest.skip("the two days aren't billed together here")
    return days


def test_days_billed_together_keep_no_rule_when_no_invoice_was_made(s, monkeypatch):
    from minute_filler import batch
    days = two_days_billed_together(s)

    def locked(*a, **k):
        raise PermissionError("the invoice is open in another program")

    monkeypatch.setattr(batch, "generate", locked)
    batch.fill_jobs(days, s, outputs=["invoice"])
    assert [d.split_rule for d in days] == ["", ""]


def test_a_day_billed_already_keeps_its_rule_billed_with_a_new_day(s):
    """Day 1 billed by Same-Speed, Day 2 not billed yet, Settings now Make-Whole: billed together, both are billed
    by Day 1's rule, and Day 2 keeps it too."""
    from minute_filler.batch import fill_jobs
    days = two_days_billed_together(s)
    days[0].split_rule = "same_speed"
    fill_jobs(days, s, outputs=["invoice"])
    assert [d.split_rule for d in days] == ["same_speed", "same_speed"]


def test_days_joined_into_one_job_keep_the_rule_one_was_billed_by(s):
    """A document naming both days joins them (batch.group): the job keeps the billed day's rule, whichever
    of the two it is."""
    from minute_filler.batch import Doc, Ident, group, ident
    from minute_filler.ingest import ingest_text
    from minute_filler.models import Extraction
    for billed in (0, 1):
        days = [excerpt_example(), excerpt_example()]
        days[1].case.set("dates", "6/4/2026", "user")
        days[billed].split_rule = "same_speed"
        one, two = ident(days[0].case), ident(days[1].case)
        doc = Doc(ingest_text("Jane Roe v. X.Y. Holding Corporation, 6/3 and 6/4", "letter.txt"), Extraction(),
                  ident=Ident(one.index, one.dates | two.dates, one.sides))
        s.batch_combine_dates = False
        (job,) = group([doc], s, days)
        assert job.split_rule == "same_speed"


def test_the_note_on_the_invoice_is_in_the_words_of_the_rule_it_was_billed_by(s):
    """Billed by Make-Whole, then Split invoices set to Same-Speed (which rewords the note as it came): the
    invoice made again for the job still says Make-Whole's note; a note the user wrote is printed as written."""
    from minute_filler.batch import fill_jobs, joint_invoice
    from minute_filler.invoice import firm_invoices, invoice_texts
    job = excerpt_example()
    fill_jobs([job], s, outputs=["invoice"])
    s.use_split_rule("same_speed")
    case, opts = joint_invoice([job])
    f = next(f for f in firm_invoices(case, s, opts) if f.atty.key() == B)
    assert MAKE_WHOLE.invoice_note in invoice_texts(s, f.case, f.atty, f.quotes, "", f.opts)["amounts"]
    for r in s.invoice_texts:
        if r["when"] == "mixed_speeds":
            r["text"] = "Pages ordered with another firm: see the math."
    assert "Pages ordered with another firm: see the math." in \
        invoice_texts(s, f.case, f.atty, f.quotes, "", f.opts)["amounts"]


def test_two_days_of_the_same_firms_are_one_section_of_their_pages(s):
    """Two days of 60 pages, Counsel & Counsel at Daily and Smith Law at Immediate both days: one section of 120
    pages, as the invoices bill them (the review of 2026-10-21: the second day was left out, and the section said
    60 pages)."""
    from minute_filler.invoice_math import split_pages
    days = []
    for date in ("6/3/2026", "6/4/2026"):
        d = typed_day(60, date)
        d.speeds = {A: "Daily", B: "Immediate"}
        days.append(d)
    made = made_of(s, *days)
    (sec,) = split_pages(made)
    assert sec.pages == 120 and [(p.who, p.total * 120) for p in sec.firms] == [
        ("Alex B. Counsel", Fraction(690)), ("Dana Smith", Fraction(870))]
    assert {f.atty.key(): f.quotes[0].per_party for f, _ in made} == {A: Decimal("690.00"), B: Decimal("870.00")}


def test_an_invoice_of_several_days_keeps_its_rule(s):
    """Days billed together keep the rule too, and the record of their invoice says it (opened again, each day is
    read from its documents and billed by it: MainWindow.open_past_job)."""
    from minute_filler.batch import fill_jobs, invoice_groups, joint_invoice
    from minute_filler.deliver import ledger_for
    days = [excerpt_example(), excerpt_example()]
    days[1].case.set("dates", "6/4/2026", "user")
    s.invoice_split_rule = "same_speed"
    if len(invoice_groups(days, s)[0]) < 2:
        pytest.skip("the two days aren't billed together here")
    fill_jobs(days, s, outputs=["invoice"])
    assert [d.split_rule for d in days] == ["same_speed", "same_speed"]
    origins = [json.loads(a.origin) for a in ledger_for(s).activity() if a.origin]
    assert any(o.get("joint") and o.get("split_rule") == "same_speed" for o in origins)
    s.invoice_split_rule = "make_whole"
    assert joint_invoice(days)[1].split_rule == "same_speed"
    days[0].split_rule = ""  # (a day added since, not billed yet: the invoice is the billed day's)
    assert joint_invoice(days)[1].split_rule == "same_speed"

