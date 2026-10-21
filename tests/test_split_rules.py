"""The two ways Queens may bill pages firms ordered together at different speeds (courthouses.base.SplitRule,
courthouses/queens_supreme_civil/billing.py), chosen in Settings -> Invoice -> "Split invoices"
(Settings.invoice_split_rule): Make-Whole Split, the default (the slower firms pay as if every firm had ordered
their speed, the fastest the rest), and Same-Speed Split (every firm, the fastest too, pays as if every firm had
ordered its speed).

The numbers are the reporter's comparer workbook's ("Transcript_Billing_Calculator - comparer.xlsx"): its sample
job, 100 pages with an index, Attorney A at Regular and Attorney B at Daily, is $565.00 and $885.00 under
Make-Whole, $565.00 and $762.50 under Same-Speed, with the bundled Sample Rates (the workbook's own). Then the
rules as a choice: the setting, its note on the invoice, the invoices and their math, the Settings window, and a
made-up third rule to show a new one plugs in without other changes. All names are made up."""
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
from test_mixed_speeds import A, B, bills, excerpt_example


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
