"""Queens Supreme Court, Civil Term: the courthouse the program was written for, and the only profile so far.

Its outputs are the four the program has always made, listed as Settings and the Records list them; in the
window the Invoice panel comes second (panel_pos). The bundled rate sheets and the prices used without one are
here too, not in rates.py: they are this courthouse's (and New York's), not every court's. So are New York's
court holidays (holidays), the list Settings -> Dates starts with.

So is how it bills firms that order the same pages at different speeds (billing.py), one of two ways the user
picks in Settings: Make-Whole Split, the default (the original is billed once, at the fastest speed ordered, each
slower firm pays its share as if every firm had ordered its speed, and the fastest pay the rest), or Same-Speed
Split (every firm, the fastest too, pays as if every firm had ordered its speed). Firms that order pages
together commit to their speed upfront (speed_upfront): only a firm billed alone chooses one from its invoice.
research/ (git-ignored, never published) holds the workbooks the rules came from and the questions still open
about them.
"""
from pathlib import Path

from ..base import Courthouse, OutputSpec

COURTHOUSE = Courthouse(
    key="queens_supreme_civil",
    name="Queens Supreme Court, Civil Term",
    # (minute_filler/rate_sheets: the build ships it there too, see YinItAgreementForm.spec)
    rate_sheets=Path(__file__).resolve().parents[2] / "rate_sheets",
    # the minimums on the New York minute agreement form
    fallback_rates=(("Regular", "3.30", "1.00"), ("Expedited", "4.40", "1.10"), ("Daily", "5.50", "1.25")),
    split_rules="minute_filler.courthouses.queens_supreme_civil.billing:RULES",
    # TEMPORARY, ARBITRARY CAP: at most two different speeds on the same pages. How three or more are billed
    # isn't settled yet (the workbook's rule and a "layered" one disagree from three speeds up; see
    # research/OPEN_QUESTIONS.md). billing's rules work for any number: raise this once the practice is settled.
    speeds_together=2,
    speed_upfront=True,
    # The New York State courts' legal holidays (nycourts.gov, Court Terms & Holidays): one that falls on a Saturday
    # is closed the Friday before (Independence Day 2026: Friday 7/3), one on a Sunday the Monday after (2027: Monday
    # 7/5). Lincoln's Birthday and Election Day are court holidays here, unlike in the federal courts.
    holidays=(("New Year's Day", "January 1"), ("Martin Luther King Jr. Day", "3rd Monday of January"),
              ("Lincoln's Birthday", "February 12"), ("Washington's Birthday", "3rd Monday of February"),
              ("Memorial Day", "last Monday of May"), ("Juneteenth", "June 19"), ("Independence Day", "July 4"),
              ("Labor Day", "1st Monday of September"), ("Columbus Day", "2nd Monday of October"),
              ("Election Day", "Tuesday after the 1st Monday of November"), ("Veterans Day", "November 11"),
              ("Thanksgiving Day", "4th Thursday of November"), ("Christmas Day", "December 25")),
    holiday_weekend="nearest",
    outputs=(
        OutputSpec(
            "agreement", "Minute agreement", "form", mark="agreement", color="#2563eb",
            maker="minute_filler.fill:Agreements", per="attorney", policy="minute_filler.batch:FormPolicy",
            tip="The UCS Court Reporter Minute Agreement Form, one for each ticked attorney,\n"
                "with the pages that attorney ordered (whoever wrote them)\n"
                "(Generate all: one per attorney for all the days of a case on one invoice,\n"
                "when Settings → Options says one for the whole case)",
            words=("minute agreement form", "minute agreement forms"),
            asks=("firms", "parties", "speed", "speeds", "fields", "attorney"),
            panel="minute_filler.gui.panels:agreement", panel_pos=0),
        OutputSpec(
            "mofr", "MOFR", "form", mark="MOFR", color="#9333ea", maker="minute_filler.mofr:Mofrs",
            policy="minute_filler.batch:FormPolicy",
            tip="The court's Minute Order Form/Receipt (your parts of it)\n"
                "(Generate all: one for all the days of a case on one invoice,\n"
                "when Settings → Options says one for the whole case)",
            words=("MOFR", "MOFRs"), asks=("firms", "parties", "speed", "speeds", "fields"),
            panel="minute_filler.gui.panels:mofr", panel_pos=2),
        OutputSpec(  # (its tooltip says whether the job has pages to bill: MainWindow._refresh_outputs)
            "invoice", "Invoice", "billing", mark="invoice", color="#16a34a",
            maker="minute_filler.invoice:Invoices", per="attorney", policy="minute_filler.batch:InvoicePolicy",
            words=("invoice", "invoices"), asks=("firms", "parties", "speeds", "attorney"),
            panel="minute_filler.gui.panels:invoice", panel_pos=1),
        OutputSpec(  # an Excel workbook, so never previewed; its tooltip too says whether the job can have one
            "runsheet", "Run sheet", "sheet", folder="YinIt Run Sheets",
            maker="minute_filler.runsheet:RunSheets", policy="minute_filler.batch:RunSheetPolicy",
            words=("run sheet", "run sheets"), panel="minute_filler.gui.panels:runsheet", panel_pos=3),
    ),
)
