"""The math of the invoices just made, spelled out (Settings -> Options: "Show the math of each invoice"), or of
those about to be made (the main window's "Who pays what" and the Invoice card open it before there are numbers).

Most invoices show only each speed's amount; when someone later asks how an amount was reached, this is the
answer. explain() lays it out as tables (HTML, for the window that shows it, gui.preview.MathView, and for
to_pdf) in one of two layouts (settings.MATH_LAYOUTS): "invoice", a table for each invoice and speed with a row
for each charge (its pages, the rate, what it costs, how it is paid, what this firm pays), or "firms", a table
for each set of firms billed for the same work and each speed, with a column per firm. It also gives the same as
plain text, a line per charge, for the clipboard and an e-mail. The tables come from rows() and _foot() of each
quote, the plain text from _line() and _sum(): the same charges worded twice, so a change of wording goes in both.
Generate saves it as PDFs next to the invoices it made (save_math, as Settings.save_math says: each firm's own,
to send the firm that asks, which shows only what that firm owes (explain's one_firm), and one of everyone's, to
look back at the job), so the answer is still there when the question comes months later.

How a charge is paid is said in three plain phrases: "Each firm splits this cost" (the original and the judge's
index of pages ordered together, divided between the firms that ordered each page), "Each firm pays for its
own" (its copy, its e-mailed copy and, as Settings.invoice_index_shared says by default, its index) and "This
firm alone" (pages no other firm ordered). A firm's own share is worked out exactly (invoice_calc.quote_shares)
and spelled out stretch by stretch: the pages it ordered alone at the full price, and the pages ordered with
other firms divided between them ("50 pages × $4.30 = $215.00 ÷ 2 firms = $107.50"). A line can come to part of
a cent: it is shown as it is ("$8.175") and the lines add up to "This firm's charges together", which is then
rounded up to the cent ("This firm pays"). With Settings -> Invoice -> Rounding "the price a page" (Quote.by_page),
when a price a page came to part of a cent (Quote.page_rounded), what each party pays says how instead: "This
firm pays: $6.6125 a page, rounded to $6.61, × 1,000 pages", so a firm checking it by hand gets the same. The
invoice itself never says how it was rounded (the user): only the math does.

Under each invoice's heading (about): the pages the user wrote of the whole transcript ("You wrote 45 of 83
total pages.") and whether there is an index and why (FirmInvoice.index_note). When several firms are billed for
the same work, a last section, "All the firms together", adds up what they pay against their exact shares added
up, which shows what rounding each one up to the cent added (or what rounding each price a page added or took
off). Before it, when firms ordered the same pages at different speeds, "Who pays what a page" (split_pages)
has a table for each set of those pages: what each firm named on them pays a page of each charge, as its own
invoice bills it, and the firms together (in the math of one firm's invoice, sent to that firm, "What this firm
pays a page": its own row alone, explain's one_firm). who_pays() is the short version the main window keeps up
to date as things are ticked: a row per firm, its pages, how it ordered them and what it pays at each speed;
page_rates() goes under it.

A firm that committed to a speed (an ordered quote, invoice_calc.quote_ordered) has its speed headed "Daily
(ordered)" (speed_name), and the "firms" layout puts such firms in one table, "As ordered", each at its own
speed. On pages ordered together at different speeds the original (and the judge's index) is billed once and
divided by the split rule (chosen in Settings; a job keeps the one it was first invoiced by, and the later days
of a trial the one its first invoice was), and its row says
how this firm's part was reached, in that rule's own words and steps (_how_once, Make-Whole Split: "Billed once,
at Immediate ($7.60 a page). This firm ordered Daily, so it pays as if both firms had ordered Daily: $6.50 ÷ 2 =
$3.25 a page."); a charge whose pages were
ordered with different firms is shown "In parts", a row for each stretch. Such an invoice says so once under its
heading, in the rule's words (_mixed_note: SplitRule.note). The words come from the rule each stretch was priced
with (Stretch.rule), so the math of an invoice still says how it was billed after the setting is changed.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from .invoice import FirmInvoice
from .invoice_calc import (ANOTHER_PARTY, Quote, QuoteLine, Stretch, exact_number, fmt, money_exact,
                           page_prices_text)

# the PDF's look (to_pdf); the window's is gui.preview.MATH_CSS
CSS = """
body {font-family: sans-serif; font-size: 10pt; color: #222;}
h2 {font-size: 13pt; margin: 14px 0 2px 0;}
h3 {font-size: 11pt; margin: 10px 0 4px 0;}
p {margin: 2px 0;}
.muted {color: #666;}
.sum {font-weight: bold;}
table.math {border-collapse: collapse; font-size: 9pt; margin: 2px 0 6px 0;}
table.math th, table.math td {border: 1px solid #b9c0cc; padding: 3px 5px; vertical-align: top;}
table.math th {background-color: #eef0f4;}
"""

SPLITS = "Each firm splits this cost"
OWN = "Each firm pays for its own"
ALONE = "This firm alone"
AT_OWN = ", at its own speed"  # (after OWN, on an invoice of pages ordered at different speeds)
ONCE = "Billed once, divided by speed"  # a charge of pages ordered at different speeds, for the firms' layout
IN_PARTS = "In parts: each row below says how"  # (such a charge with pages ordered with different firms)

CENT = Decimal("0.01")
# (money_exact: '$8.175', '$1.4333…', in invoice_calc since the courthouses' split rules word their steps with it)


def _d(f: Fraction) -> Decimal:
    """An exact amount as a Decimal (to Decimal's 28 digits), for the tables: 65/2 -> 32.5."""
    return Decimal(f.numerator) / Decimal(f.denominator)


def _num(n) -> str:
    """A number of pages: '120', '1,200', '32.5', '3.33…' (a third of 10)."""
    return exact_number(Decimal(n), 2) if isinstance(n, Decimal) else f"{n:,}"


def _pages(n) -> str:
    """'1 page', '120 pages', '32.5 pages', '3.33… pages' (a third of 10)."""
    return f"{_num(n)} page" if n == 1 else f"{_num(n)} pages"


INDENT = "      "  # a line that spells out part of the line above it


def _firms(n: int) -> str:
    """'1 firm', '2 firms'."""
    return "1 firm" if n == 1 else f"{n} firms"


def _with(others) -> str:
    """The other firms on a stretch, with their speeds: 'Smith Law (Immediate)', 'Smith Law (Immediate) and
    Counsel & Counsel (Daily)'; parties a Parties number counts beyond them are left out (they order this firm's
    speed)."""
    named = [f"{name} ({speed})" for name, speed in others]
    return ", ".join(named[:-1]) + " and " + named[-1] if len(named) > 1 else (named[0] if named else "")


def _how_once(x: Stretch) -> str:
    """How this firm's part of a charge billed once was reached, on pages ordered at different speeds: 'Billed
    once, at Immediate ($7.60 a page). This firm ordered Daily, so it pays as if both firms had ordered Daily:
    $6.50 ÷ 2 = $3.25 a page.' (the split rule it was priced with gives the words and the steps)."""
    steps = " ".join(f"{words}." for words, _ in x.steps)
    return f"{x.rule.billed(x.billed_at, x.billed_rate)}. {steps}".strip()


def _mixed_note(quotes: list[Quote]) -> str:
    """Said once under an invoice (or the firms' table) some of whose pages were ordered with a firm at another
    speed: how such pages are billed, in the words of the split rule they were priced with (SplitRule.note); ""
    when there are none."""
    return " ".join(dict.fromkeys(q.rule.note for q in quotes if q.mixed))


# ------------------------------------------------------------------ the rows of the tables

@dataclass
class Row:
    """One row of the math's tables: a charge of a quote or, `sub`, a stretch of its pages under it (those a firm
    ordered alone, those it ordered with 2 firms...). pages: as shown ("60", "2 × 60" for the copies of a whole
    invoice); cost: the charge before anyone splits it; how: how it is paid (SPLITS, OWN, ALONE, with "(÷ 2)";
    IN_PARTS, or the split rule's words for pages ordered together at different speeds);
    pays: what this firm, or each party of a whole invoice, pays for it (exact: maybe part of a cent); short: that
    in a few words, for the firms' layout ("59 pp. ÷ 4", "70 alone + 50 ÷ 2"); split: its cost is divided; once: a
    charge billed once for pages ordered together at different speeds (ONCE in the firms' layout, whatever the
    rule's words)."""
    label: str
    pages: str
    rate: Decimal
    cost: Decimal
    how: str
    pays: Decimal
    short: str = ""
    split: bool = False
    sub: bool = False
    once: bool = False


def rows(q: Quote) -> list[Row]:
    """The rows of one speed's table. On a whole invoice (not a firm's share) each party pays an equal part of
    every charge: the copies (and, with Settings' index for each party, the index) one each (OWN), the rest split
    between the parties. On a firm's share, the lines as quote_shares made them: a line split between firms
    shows each stretch under it when the firm ordered some pages alone and some with others. On an ordered quote
    (quote_ordered), a charge billed once for pages ordered with a firm at another speed says how this firm's
    part was reached (_how_once), with a row for each stretch under it ("In parts") when they differ."""
    out = []
    n = max(1, q.parties)
    own = OWN + (AT_OWN if q.mixed else "")
    for l in q.lines:
        if l.mixed:  # a charge billed once for pages ordered with firms at other speeds: each stretch says how
            pages = sum(x.pages for x in l.stretches)
            subs = []
            for x in l.stretches:
                if x.mixed:
                    # what a page of it comes to, all the firms' parts together: one at the fastest speed under
                    # Make-Whole Split, each firm's at its own under Same-Speed (Stretch.parts)
                    whole = sum((a for _, _, a in x.parts), Fraction(0)) if x.parts else x.billed_rate
                    subs.append(Row(f"{_pages(x.pages)} ordered with {_with(x.others)}", _num(x.pages),
                                    _d(whole), _d(whole * x.pages), _how_once(x),
                                    _d(x.per_page * x.pages),
                                    f"{_num(x.pages)} pp. × {money_exact(x.per_page)}", True, True))
                elif x.n > 1:
                    subs.append(Row(f"{_pages(x.pages)} ordered by {_firms(x.n)} at {_line_speed(q, l)}", _num(x.pages),
                                    l.rate, l.rate * x.pages, f"{SPLITS} (÷ {x.n})", l.rate * x.pages / x.n,
                                    f"{_num(x.pages)} pp. × {money_exact(Fraction(l.rate) / x.n)}", True, True))
                else:
                    subs.append(Row(f"{_pages(x.pages)} ordered by this firm alone", _num(x.pages), l.rate,
                                    l.rate * x.pages, ALONE, l.rate * x.pages,
                                    f"{_num(x.pages)} pp. × {money_exact(l.rate)}", False, True))
            if len(subs) == 1:  # every page of it ordered with the same firms: the one row
                r = subs[0]
                out.append(Row(l.label, r.pages, r.rate, r.cost, f"{r.label}. {r.how}", r.pays, r.short, True,
                               once=True))
                continue
            # (in parts: "60 pp. × $3.25 + 60 pp. × $7.60", each part's row under it saying how; the rate what a
            # page of them comes to, so that rate × pages is the cost)
            short = " + ".join(r.short for r in subs)
            cost = sum((r.cost for r in subs), Decimal(0))
            out.append(Row(l.label, _num(pages), cost / pages if pages else l.rate, cost, IN_PARTS, l.amount, short,
                           True, once=True))
            out += subs
            continue
        if not q.share:
            pages = l.pages or q.pages
            shown = f"{l.qty} × {_num(pages)}" if l.qty > 1 else _num(pages)
            split = l.qty == 1 and n > 1
            how = OWN if l.qty > 1 else f"{SPLITS} (÷ {n})" if split else ALONE
            out.append(Row(l.label, shown, l.rate, l.amount, how, l.amount / n,
                           f"{_num(pages)} pp." + (f" ÷ {n}" if split else ""), split))
            continue
        parts = l.parts or [(l.pages, 1)]
        pages = sum(p for p, _ in parts)
        whole = l.rate * pages  # these pages' charge, before the firms that ordered them split it
        if not l.shared:
            how = own if any(k > 1 for _, k in parts) else ALONE
            out.append(Row(l.label, _num(pages), l.rate, l.amount, how, l.amount, f"{_num(pages)} pp."))
            continue
        if len(parts) == 1:  # every page it ordered, ordered by the same firms
            p, k = parts[0]
            out.append(Row(l.label, _num(p), l.rate, whole, f"{SPLITS} (÷ {k})", l.amount, f"{_num(p)} pp. ÷ {k}",
                           True))
            continue
        short = " + ".join(f"{_num(p)} alone" if k == 1 else f"{_num(p)} ÷ {k}" for p, k in parts)
        out.append(Row(l.label, _num(pages), l.rate, whole, f"{SPLITS} (the pages ordered together)", l.amount,
                       short, True))
        for p, k in parts:
            label = f"{_pages(p)} ordered by this firm alone" if k == 1 else f"{_pages(p)} ordered by {_firms(k)}"
            out.append(Row(label, _num(p), l.rate, l.rate * p, ALONE if k == 1 else f"{SPLITS} (÷ {k})",
                           l.rate * p / k, sub=True))
    return out


def _foot(q: Quote) -> list[tuple[str, str]]:
    """The last rows of a speed's table, (what, amount): a firm's share 'This firm pays' (after 'This firm's
    charges together' when the lines come to part of a cent, and then '(rounded up to the cent)'); a whole
    invoice its total and what each party pays. With each price a page rounded to the cent (Quote.page_rounded):
    the charges together (or the total), then what it pays and how: 'This firm pays: $6.6125 a page, rounded to
    $6.61, × 1,000 pages'."""
    if q.page_rounded:
        who = "This firm pays" if q.share else "Each party pays"
        total = ("This firm's charges together" if q.share else f"Total, the {q.parties} parties together",
                 money_exact(q.total))
        return [total, (f"{who}: {page_prices_text(q)}", fmt(q.per_party))]
    if q.share:
        out = []
        if q.total != q.per_party:
            out.append(("This firm's charges together", money_exact(q.total)))
        out.append(("This firm pays" + (" (rounded up to the cent)" if out else ""), fmt(q.per_party)))
        return out
    if q.parties <= 1:
        return [("Total", fmt(q.total))]
    up = " (rounded up to the cent)" if q.per_party * q.parties != q.total else ""
    return [(f"Total, the {q.parties} parties together", fmt(q.total)),
            (f"Each party pays ({fmt(q.total)} ÷ {q.parties}){up}", fmt(q.per_party))]


# ------------------------------------------------------------------ the plain text

def _line(l: QuoteLine, q: Quote) -> list[str]:
    """'Copy: 2 × 120 pages × $1.00 = $240.00'. On a firm's own share, the pages split between the firms
    are spelled out: 'Original: 60 pages × $4.30 = $258.00 ÷ 2 firms = $129.00 (each firm splits this cost)', or
    for pages ordered alone and with others, a line for each stretch ('40 pages ordered by this firm alone: ...',
    '50 pages ordered by 2 firms: 50 × $4.30 = $215.00 ÷ 2 = $107.50') under the line's own total. A charge each
    firm pays in full says so when some of its pages were ordered with other firms. A charge billed once for
    pages ordered with a firm at another speed says how this firm's part was reached: 'Original: 60 pages
    ordered with Smith Law (Immediate): 60 × $3.25 = $195.00. Billed once, at Immediate ($7.60 a page). This firm
    ordered Daily, so it pays as if both firms had ordered Daily: $6.50 ÷ 2 = $3.25 a page.'"""
    n = f"{l.qty} × " if l.qty > 1 else ""
    if l.mixed:
        out = [f"{l.label}: {money_exact(l.amount)}"] if len(l.stretches) > 1 else []
        for x in l.stretches:
            pays = _d(x.per_page * x.pages)
            if x.mixed:
                what = (f"{_pages(x.pages)} ordered with {_with(x.others)}: {x.pages:,} × {money_exact(x.per_page)} "
                        f"= {money_exact(pays)}. {_how_once(x)}")
            elif x.n > 1:
                what = (f"{_pages(x.pages)} ordered by {_firms(x.n)}: {x.pages:,} × {fmt(l.rate)} = "
                        f"{money_exact(l.rate * x.pages)} ÷ {x.n} = {money_exact(pays)}")
            else:
                what = f"{_pages(x.pages)} ordered by this firm alone: {x.pages:,} × {fmt(l.rate)} = {money_exact(pays)}"
            out.append(f"{INDENT}{what}" if len(l.stretches) > 1 else f"{l.label}: {what}")
        return out
    if not q.share or not l.parts:
        return [f"{l.label}: {n}{_pages(l.pages or q.pages)} × {fmt(l.rate)} = {money_exact(l.amount)}"]
    pages = sum(p for p, _ in l.parts)
    if not l.shared:
        own = f" ({OWN.lower()}{AT_OWN if q.mixed else ''})" if any(k > 1 for _, k in l.parts) else ""
        return [f"{l.label}: {_pages(pages)} × {fmt(l.rate)} = {money_exact(l.amount)}{own}"]
    if len(l.parts) == 1:  # every page it ordered, ordered by the same firms
        p, k = l.parts[0]
        whole = l.rate * p
        return [f"{l.label}: {_pages(p)} × {fmt(l.rate)} = {money_exact(whole)} ÷ {_firms(k)} = "
                f"{money_exact(l.amount)} ({SPLITS.lower()})"]
    out = [f"{l.label} ({fmt(l.rate)} a page, divided between the firms that ordered each page): "
           f"{money_exact(l.amount)}"]
    for p, k in l.parts:
        whole = l.rate * p
        if k == 1:
            out.append(f"{INDENT}{_pages(p)} ordered by this firm alone: {p:,} × {fmt(l.rate)} = "
                       f"{money_exact(whole)}")
        else:
            out.append(f"{INDENT}{_pages(p)} ordered by {_firms(k)}: {p:,} × {fmt(l.rate)} = {money_exact(whole)} "
                       f"÷ {k} = {money_exact(whole / k)}")
    return out


def _sum(q: Quote) -> list[str]:
    """The total and what each party owes: 'Total: $319.30', '÷ 3 parties = $106.44 each (rounded up to the
    cent)' (that last only when it does not split evenly); a firm's own share: 'This firm pays: $219.25', after
    'This firm's charges together: $219.245' when the lines come to part of a cent. With each price a page rounded
    to the cent (Quote.page_rounded), after the total: 'Each party pays: $6.6125 a page, rounded to $6.61, × 1,000
    pages = $6,610.00'."""
    if q.page_rounded:
        who = "This firm pays" if q.share else "Each party pays"
        total = f"This firm's charges together: {money_exact(q.total)}" if q.share else f"Total: {fmt(q.total)}"
        return [total, f"{who}: {page_prices_text(q)} = {fmt(q.per_party)}"]
    if q.share:
        out = []
        if q.total != q.per_party:  # (worked out exactly: $4.30 split three ways is $1.4333…, not whole cents)
            out.append(f"This firm's charges together: {money_exact(q.total)}")
        out.append(f"This firm pays: {fmt(q.per_party)}" + (" (rounded up to the cent)" if out else ""))
        return out
    out = [f"Total: {fmt(q.total)}"]
    if q.parties > 1:
        each = f"÷ {q.parties} parties = {fmt(q.per_party)} each"
        if q.per_party * q.parties != q.total:
            each += " (rounded up to the cent)"
        out.append(each)
    return out


def _who(f: FirmInvoice) -> str:
    """Who an invoice bills: 'Dana Smith (Smith Law)', 'Smith Law'; '' for a blank Bill To."""
    if f.atty is None:
        return ""
    name, firm = (f.atty.name or "").strip(), (f.atty.firm or "").strip()
    return name + (f" ({firm})" if firm and name else firm)


def heading(f: FirmInvoice, number: str) -> str:
    """'Invoice 2026-0001 · Bill to Dana Smith (Counsel & Counsel) · 120 pages' (just 'Invoice' while it has no
    number yet), with the excerpt it ordered and, on a whole invoice, the parties."""
    who = _who(f)
    head = (f"Invoice {number}" if number else "Invoice") + (f" · Bill to {who}" if who else "")
    head += f" · {_pages(f.opts.pages)}"
    if f.opts.excerpt:
        head += f" ({f.opts.excerpt})"
    if f.opts.parties > 1 and not (f.quotes and f.quotes[0].share):
        head += f", {f.opts.parties} parties"
    return head


def about(f: FirmInvoice) -> str:
    """What the heading doesn't say: the pages the user wrote of the whole transcript, when other reporters
    wrote some ("You wrote 45 of 83 total pages.", as the Invoice card's Billed line says it; "DS wrote ..." on
    an invoice in another reporter's name; "The Pages field: 40 of 83 total pages." when that number was typed,
    as it need not be the pages the user wrote), and whether there is an index and why ("Index: 83 total pages,
    50 or more."). "" when there is neither."""
    o = f.opts
    mine, whole = o.my_pages or o.pages, o.total_pages
    bits = []
    if whole > mine:
        who = "The Pages field:" if o.typed else f"{o.reporter.upper()} wrote" if o.reporter else "You wrote"
        bits.append(f"{who} {mine:,} of {whole:,} total pages.")
    if f.index_note:
        bits.append(f.index_note)
    return " ".join(bits)


def speed_name(q: Quote) -> str:
    """A speed's heading: 'Expedite' on an invoice that lets the firm choose; 'Daily (ordered)', 'Daily +
    Regular (ordered)' on one that bills the speeds the firm committed to (an ordered quote)."""
    return f"{q.speed} (ordered)" if q.ordered else q.speed


def _sections(made: list[tuple[FirmInvoice, str]]) -> list[tuple[str, str, list[tuple[str, list[str], list[str]]]]]:
    """For each invoice: its heading, the lines under it (about; _mixed_note when some of its pages were ordered
    at another speed by a firm sharing them) and, for each speed, (its name, the charge lines, the sum lines), as
    the plain text says them."""
    return [(heading(f, number),
             " ".join(x for x in (about(f), _mixed_note(f.quotes)) if x),
             [(speed_name(q), [x for l in q.lines for x in _line(l, q)], _sum(q)) for q in f.quotes])
            for f, number in made]


def _plain(made: list[tuple[FirmInvoice, str]]) -> list[str]:
    """The plain text of the invoices' math: the heading, the line under it, and each speed's lines."""
    plain = []
    for head, note, speeds in _sections(made):
        plain.append(head)
        if note:
            plain.append(note)
        for speed, lines, sums in speeds:
            plain.append(f"  {speed}")
            plain += [f"    {x}" for x in lines + sums]
        plain.append("")
    return plain


# ------------------------------------------------------------------ the tables

_TABLE = ("<table class='math' border='1' cellspacing='0' cellpadding='4' "
          "style='border-collapse: collapse; border-color: #8a8f99; border-style: solid;'>")


def _e(text: str) -> str:
    return html.escape(text)


def _cells(cells: list[tuple[str, str]], tag: str = "td") -> str:
    """A table row of (text, align) cells, the text already escaped."""
    return "<tr>" + "".join(f"<{tag} align='{a}'>{t}</{tag}>" for t, a in cells) + "</tr>"


def _speed_table(q: Quote) -> str:
    """One speed of one invoice: a row per charge (and its stretches, indented), then what this firm pays."""
    heads = ["Charge", "Pages", "Rate", "Cost", "How it's paid", "This firm pays" if q.share else "Each party pays"]
    out = [_TABLE, _cells([(h, "left" if i in (0, 4) else "right") for i, h in enumerate(heads)], "th")]
    for r in rows(q):
        label = ("&nbsp;" * 6 + _e(r.label)) if r.sub else _e(r.label)
        # (money_exact: the firms' parts of a page at different speeds add up to part of a cent, $6.8666…)
        out.append(_cells([(label, "left"), (_e(r.pages), "right"), (money_exact(r.rate), "right"),
                           (money_exact(r.cost), "right"), (_e(r.how), "left"), (money_exact(r.pays), "right")]))
    for what, amount in _foot(q):
        out.append(f"<tr><td colspan='5' align='right'><b>{_e(what)}</b></td>"
                   f"<td align='right'><b>{amount}</b></td></tr>")
    out.append("</table>")
    return "".join(out)


def _by_invoice(made: list[tuple[FirmInvoice, str]]) -> list[str]:
    """The "invoice" layout: for each invoice its heading, the line under it and a table for each speed."""
    parts = []
    for f, number in made:
        parts.append(f"<h2>{_e(heading(f, number))}</h2>")
        note = about(f)
        if note:
            parts.append(f"<p class='muted'>{_e(note)}</p>")
        if any(q.mixed for q in f.quotes):
            parts.append(f"<p class='muted'>{_e(_mixed_note(f.quotes))}</p>")
        for q in f.quotes:
            parts.append(f"<h3>{_e(speed_name(q))}</h3>")
            parts.append(_speed_table(q))
    return parts


def _ordered(f: FirmInvoice) -> bool:
    """The invoice bills the speeds the firm committed to (an ordered quote), not a choice of speeds."""
    return bool(f.quotes and f.quotes[0].ordered)


def _by_firms(made: list[tuple[FirmInvoice, str]]) -> list[str]:
    """The "firms" layout: for each set of invoices billed for the same work (FirmInvoice.group), a table for each
    speed with a column per firm: what it pays for each charge and how many pages that is, and what it pays in
    all. A charge a firm has none of shows "—". The firms billed the speeds they ordered share one table, "As
    ordered", each column at its own speed and rates."""
    groups: dict[int, list[tuple[FirmInvoice, str]]] = {}
    for f, number in made:
        groups.setdefault(f.group, []).append((f, number))
    parts = []
    for firms in groups.values():
        whose = firms[0][0].opts.reporter
        count = f"{len(firms)} invoices side by side" if len(firms) > 1 else "The invoice"
        if whose:
            count += f" in {whose.upper()}'s name"
        parts.append(f"<h2>{_e(count)}</h2>")
        notes = [(f, about(f)) for f, _ in firms if about(f)]
        if len({n for _, n in notes}) == 1:
            parts.append(f"<p class='muted'>{_e(notes[0][1])}</p>")
        else:
            parts += [f"<p class='muted'>{_e(_who(f) or '(no attorney)')}: {_e(n)}</p>" for f, n in notes]
        if any(q.mixed for f, _ in firms for q in f.quotes):
            parts.append(f"<p class='muted'>{_e(_mixed_note([q for f, _ in firms for q in f.quotes]))}</p>")
        ordered = [x for x in firms if _ordered(x[0])]
        chosen = [x for x in firms if not _ordered(x[0])]
        if ordered:
            parts.append("<h3>As ordered (each firm at its own speed)</h3>")
            parts.append(_firms_table(ordered, [f.quotes[0] for f, _ in ordered], True))
        for q0 in chosen[0][0].quotes if chosen else []:
            quotes = [next((q for q in f.quotes if q.speed == q0.speed), None) for f, _ in chosen]
            parts.append(f"<h3>{_e(q0.speed)}</h3>")
            parts.append(_firms_table(chosen, quotes))
    return parts


def _firms_table(firms: list[tuple[FirmInvoice, str]], quotes: list[Quote | None], own_speed: bool = False) -> str:
    """One speed of a set of invoices, a column per firm (see _by_firms). own_speed: each firm at the speed it
    ordered (the column names it, and each cell its own rate)."""
    tables = [{r.label: r for r in rows(q) if not r.sub} if q else {} for q in quotes]
    labels = list(dict.fromkeys(label for t in tables for label in t))
    heads = [("Charge", "left"), ("Rate", "right"), ("How it's paid", "left")]
    for (f, number), q in zip(firms, quotes):
        bits = ([number] if number else []) + ([q.speed] if own_speed and q else []) + [_pages(f.opts.pages)]
        heads.append((f"{_e(_who(f) or '(no attorney)')}<br><span class='muted'>{_e(' · '.join(bits))}</span>",
                      "right"))
    out = [_TABLE, _cells(heads, "th")]
    for label in labels:
        got = [t.get(label) for t in tables]
        first = next(r for r in got if r is not None)
        how = (ONCE if any(r and r.once for r in got)
               else SPLITS if any(r and r.split for r in got)
               else OWN + (AT_OWN if own_speed else "") if any(r and r.how.startswith(OWN) for r in got) else ALONE)
        rate = "" if own_speed else fmt(first.rate)  # (each firm's at its own speed: in its cell)

        def cell(r: Row) -> str:
            """What a firm pays for the charge, and how many pages (at what rate, at its own speed)."""
            short = r.short if not own_speed or "×" in r.short else f"{r.short} at {fmt(r.rate)}"
            return f"{money_exact(r.pays)}<br><span class='muted'>{_e(short)}</span>"

        cells = [(_e(label), "left"), (rate, "right"), (_e(how), "left")]
        cells += [(cell(r) if r else "—", "right") for r in got]
        out.append(_cells(cells))
    share = any(q is not None and q.share for q in quotes)
    parts = any(q is not None and q.share and q.total != q.per_party for q in quotes)  # (part of a cent)
    if parts:
        out.append(_cells([("<b>Charges together</b>", "left"), ("", "right"), ("", "left")]
                          + [(money_exact(q.total) if q else "—", "right") for q in quotes]))
    uneven = any(q is not None and not q.share and q.per_party * q.parties != q.total for q in quotes)
    pays = "Each firm pays" if share else "Each party pays"
    if any(q is not None and q.page_rounded for q in quotes):  # (each price a page rounded: each cell says how)
        pays += " (its price a page rounded to the cent)"
    elif parts or uneven:
        pays += " (rounded up to the cent)"

    def paid(q: Quote) -> str:
        """What a firm pays, and under it how when its price a page was rounded ('1,000 × $6.61')."""
        how = f"<br><span class='muted'>{_e(page_prices_text(q, short=True))}</span>" if q.page_rounded else ""
        return f"<b>{fmt(q.per_party)}</b>{how}"

    out.append(_cells([(f"<b>{_e(pays)}</b>", "left"), ("", "right"), ("", "left")]
                      + [(paid(q) if q else "—", "right") for q in quotes]))
    out.append("</table>")
    return "".join(out)


# ------------------------------------------------------------------ several firms together

def together(made: list[tuple[FirmInvoice, str]]) -> list[str]:
    """For the firms billed for the same work (the invoices of one set: one case, one reporter, see
    FirmInvoice.group), what they pay together at each speed against their exact shares added up: 'Regular:
    the 2 firms together pay $618.00 for work that costs $618.00' (+ what rounding each one up to the cent
    added, or rounding each price a page what it added or took off: _together; another reporter's set says whose:
    'Regular (DS invoices): ...'). The firms billed the speeds they
    ordered are added up together: 'As ordered (Daily, Immediate): the 2 firms together pay $780.00 for work that
    costs $780.00', and when some of their pages were ordered at different speeds, what their parts of each
    original add up to (the split rule's words, SplitRule.adds_up: one original at the fastest speed, under
    Make-Whole Split). [] when no set has two firms."""
    groups: dict[int, list[FirmInvoice]] = {}
    for f, _ in made:
        if f.quotes and f.quotes[0].share:
            groups.setdefault(f.group, []).append(f)
    out = []
    for firms in groups.values():
        ordered = [f for f in firms if _ordered(f)]
        if len(ordered) > 1:
            quotes = [f.quotes[0] for f in ordered]
            whose = ordered[0].opts.reporter
            speeds = ", ".join(dict.fromkeys(sp for q in quotes for sp in q.ordered))
            out.append(_together(f"As ordered ({speeds}){f' ({whose.upper()} invoices)' if whose else ''}", quotes))
            out += list(dict.fromkeys(q.rule.adds_up for q in quotes if q.mixed))
        firms = [f for f in firms if not _ordered(f)]
        if len(firms) < 2:
            continue
        for i, q0 in enumerate(firms[0].quotes):
            quotes = [f.quotes[i] for f in firms if i < len(f.quotes) and f.quotes[i].speed == q0.speed]
            if len(quotes) != len(firms):
                continue
            whose = firms[0].opts.reporter  # (another reporter's invoices are added up apart from the user's)
            out.append(_together(f"{q0.speed}{f' ({whose.upper()} invoices)' if whose else ''}", quotes))
    return out


def _together(what: str, quotes: list[Quote]) -> str:
    """'Regular: the 2 firms together pay $618.00 for work that costs $618.00' (+ what rounding each one up to the
    cent added, or, each price a page rounded to the cent, what that added or took off: '(rounding each firm's
    price a page to the cent takes off $10.00)'), for these firms' quotes."""
    paid = sum((q.per_party for q in quotes), Decimal("0.00"))
    # the exact shares added up first: a third of a cent three times is a whole cent, not 0.99…
    cost = _d(sum((q.due for q in quotes), Fraction(0)))
    line = f"{what}: the {len(quotes)} firms together pay {fmt(paid)} for work that costs {money_exact(cost)}"
    extra = paid - cost
    if any(q.page_rounded for q in quotes):
        if extra:
            line += (f" (rounding each firm's price a page to the cent {'adds' if extra > 0 else 'takes off'} "
                     f"{money_exact(abs(extra))})")
    elif extra > 0:
        line += f" (rounding each one up to the cent adds {money_exact(extra)})"
    return line


def how_shared(parts: list[tuple[int, int]]) -> str:
    """How a firm ordered its pages, in a few words, from a quote line's parts ((pages, firms) each):
    [(70, 1), (50, 2)] -> '70 alone + 50 shared by 2'; [(30, 1)] -> 'alone'; [(30, 3)] -> 'shared by 3'."""
    by: dict[int, int] = {}
    for p, k in parts:
        by[max(1, k)] = by.get(max(1, k), 0) + p
    if len(by) == 1:
        k = next(iter(by))
        return "alone" if k == 1 else f"shared by {k}"
    return " + ".join(f"{p:,} alone" if k == 1 else f"{p:,} shared by {k}" for k, p in sorted(by.items()))


@dataclass
class PayRow:
    """One firm's row of the window's "Who pays what": its name, the pages billed to it, how it ordered them
    ("70 alone + 50 shared by 2") and, for each speed the invoice offers, what it pays and what that comes to
    a page, everything on its invoice counted (the original, its copy, the e-mailed copy, the index)."""
    name: str
    pages: int
    how: str
    prices: list[tuple[str, Decimal, Decimal]]  # (speed, what it pays, a page)
    key: str = ""  # its Attorney.key() ("" for a blank Bill To): the window marks the firm by it (firm_marks)


def who_pays(firms: list[FirmInvoice]) -> list[PayRow]:
    """The rows of "Who pays what" for the invoices about to be made (invoice.firm_invoices): a row per
    invoice, in order, "(no attorney)" for a blank Bill To. Nothing is worked out again: what each pays is the
    invoice's own amount (per_party). Invoices made the old way (no shares) say "alone" or "split 3 ways"."""
    out = []
    for f in firms:
        parts = next((l.parts for q in f.quotes[:1] for l in q.lines if l.parts), [])
        n = f.opts.parties
        how = how_shared(parts) if parts else "alone" if n <= 1 else f"split {n} ways"
        if any(q.mixed for q in f.quotes):
            how += " (at different speeds)"
        name = f.atty.label() if f.atty is not None else "(no attorney)"
        out.append(PayRow(name, f.opts.pages, how, [(q.speed, q.per_party, q.per_page) for q in f.quotes],
                          f.atty.key() if f.atty is not None else ""))
    return out


# Under "Who pays what" when some pages were ordered together at different speeds, with how the split rule bills
# them (SplitRule.summary)
MIXED_RATES = "Pages ordered together at different speeds: {how}."


def _line_speed(q: Quote, l: QuoteLine) -> str:
    """The speed a line of a quote is at: the quote's, or on an ordered quote of two speeds the one its label
    names ('Original (Daily)' -> 'Daily')."""
    if l.label != l.charge:
        return l.label[len(l.charge) + 2:-1]
    return q.ordered[0] if q.ordered else q.speed


def page_rates(firms: list[FirmInvoice]) -> str:
    """What a page of the original costs a firm, at each speed, alone and shared, for the ways these firms
    ordered their pages: 'A page of the original: Regular $4.30 alone, $2.15 shared by 2 · Expedite $5.40
    alone, $2.70 shared by 2'. Firms billed the speeds they ordered: the speeds they ordered, and MIXED_RATES
    when some ordered the same pages at different speeds (in the words of the rule they were priced with). ""
    when there is nothing to price."""
    if any(_ordered(f) for f in firms):
        rates: dict[str, tuple[Decimal, set[int]]] = {}
        for f in firms:
            for q in f.quotes[:1]:
                for l in q.lines:
                    if l.charge == "Original":
                        rate, ns = rates.setdefault(_line_speed(q, l), (l.rate, set()))
                        ns |= {x.n for x in l.stretches if not x.mixed} or ({1} if not l.mixed else set())
        bits = [f"{sp} " + ", ".join(f"{money_exact(rate / k)} {'alone' if k == 1 else f'shared by {k}'}"
                                     for k in sorted(ns)) for sp, (rate, ns) in rates.items() if ns]
        text = "A page of the original: " + " · ".join(bits) if bits else ""
        hows = dict.fromkeys(q.rule.summary for f in firms for q in f.quotes if q.mixed)
        if hows:
            text = (text + ". " if text else "") + " ".join(MIXED_RATES.format(how=how) for how in hows)
        return text
    ns: set[int] = set()
    for f in firms:
        parts = next((l.parts for q in f.quotes[:1] for l in q.lines if l.charge == "Original"), [])
        ns |= {max(1, k) for _, k in parts} or {max(1, f.opts.parties)}
    if not firms or not firms[0].quotes or not ns:
        return ""
    bits = []
    for q in firms[0].quotes:
        rate = next((l.rate for l in q.lines if l.charge == "Original"), None)
        if rate is None:
            continue
        each = [f"{money_exact(rate / k)} {'alone' if k == 1 else f'shared by {k}'}" for k in sorted(ns)]
        bits.append(f"{q.speed} {', '.join(each)}")
    return "A page of the original: " + " · ".join(bits) if bits else ""


@dataclass
class SplitPart:
    """One firm on pages ordered together at different speeds (split_pages): who (Attorney.label()), the speed it
    ordered, what it pays a page of each charge ((charge, exact) each, in the invoice's order) and in all."""
    who: str
    speed: str
    charges: list[tuple[str, Fraction]]

    @property
    def total(self) -> Fraction:
        return sum((a for _, a in self.charges), Fraction(0))


@dataclass
class SplitSection:
    """Pages that the same firms ordered together at different speeds, priced alike (split_pages): how many, each
    firm named on them (SplitPart), the first invoice's firm first, and how many parties a Parties number counts
    beyond them (unnamed: on no invoice here, so neither a row nor in the total)."""
    pages: int
    firms: list[SplitPart]
    unnamed: int = 0

    @property
    def label(self) -> str:
        """'60 pages ordered by Alex B. Counsel (Daily) and Dana Smith (Immediate)'."""
        return f"{_pages(self.pages)} ordered by {_with([(p.who, p.speed) for p in self.firms])}"

    def own(self) -> SplitSection:
        """The section as the math sent to its first firm shows it (explain's one_firm): that firm's row alone,
        its label still naming who shared the pages (the invoice's own lines name them too)."""
        return _OwnSection(self.pages, self.firms[:1], self.unnamed, self.label)

    @property
    def total(self) -> Fraction:
        return sum((p.total for p in self.firms), Fraction(0))

    @property
    def note(self) -> str:
        """What the rows leave out: 'Also on these pages: 1 more party, counted by Parties but not named. Each
        firm's invoice takes it to order that firm's speed.'; "" when there is none."""
        if not self.unnamed:
            return ""
        more = "1 more party" if self.unnamed == 1 else f"{self.unnamed} more parties"
        return (f"Also on these pages: {more}, counted by Parties but not named. Each firm's invoice takes "
                f"{'it' if self.unnamed == 1 else 'them'} to order that firm's speed.")


@dataclass
class _OwnSection(SplitSection):
    """A SplitSection with one firm's row (SplitSection.own). Its label is the whole section's (whole: every firm
    on the pages named), and _split_plain and _split_tables leave out its firms together."""
    whole: str = ""

    @property
    def label(self) -> str:
        return self.whole


def _stretch_sections(f: FirmInvoice) -> list[SplitSection]:
    """The stretches of f's pages ordered together at different speeds, as f's invoice priced them: a section each,
    f's firm first, what each firm named on them pays a page of each charge (Stretch.parts)."""
    me = f.atty.label() if f.atty is not None else "(no attorney)"
    out = []
    for q in f.quotes:
        by_share: dict[int, SplitSection] = {}
        for l in q.lines:
            for x in l.stretches:
                if not x.parts:
                    continue
                named = [(who or me, speed, each) for who, speed, each in x.parts if who != ANOTHER_PARTY]
                sec = by_share.get(x.share)
                if sec is None:
                    sec = by_share[x.share] = SplitSection(x.pages, [SplitPart(who, speed, []) for who, speed, _ in
                                                                     named], len(x.parts) - len(named))
                for p, (_, _, each) in zip(sec.firms, named):
                    p.charges.append((l.charge, each))
        out += by_share.values()
    return out


def split_pages(made: list[tuple[FirmInvoice, str]]) -> list[SplitSection]:
    """Who pays what a page on the pages ordered together at different speeds (as the reporter's comparer workbook
    shows them, stretch by stretch: the user, 2026-10-21): a section for each stretch of pages the same firms
    ordered and priced alike, what each of them pays a page of each charge (its part of the original and the
    judge's index, as the split rule divided them; its own copies at its own speed: Stretch.parts) and in all.
    Each stretch once, from the first invoice that has it (every firm's on it has it), each firm's row as its own
    invoice bills it when that invoice is here too (an invoice prices a party a Parties number counts beyond the
    firms named at its own firm's speed, and leaves out a charge it has none of: the sweep of 2026-10-21);
    stretches of the same firms at the same prices (two days, say) added up. Invoices of another set
    (FirmInvoice.group, another reporter's) are counted apart. [] when no pages were ordered at different speeds."""
    views = [(f, (f.group, f.opts.reporter), _stretch_sections(f)) for f, _ in made]

    def firms_on(sec: SplitSection) -> tuple:
        return sec.pages, tuple(sorted((p.who, p.speed) for p in sec.firms))

    own: dict[tuple, list[SplitPart]] = {}  # each firm's own row of a stretch, by its set, the firm and the stretch
    for f, group, secs in views:
        for sec in secs:
            own.setdefault((group, sec.firms[0].who, firms_on(sec)), []).append(sec.firms[0])
    out: list[SplitSection] = []
    billed: dict[tuple, set[str]] = {}  # each set's firms whose invoice gave its stretches already
    alike: dict[tuple, SplitSection] = {}  # each set's sections by their firms and prices: pages added up
    for f, group, secs in views:
        before = billed.setdefault(group, set())
        for sec in secs:
            if any(p.who in before for p in sec.firms[1:]):
                continue  # (an invoice before this one has these pages)
            for i, p in enumerate(sec.firms[1:], 1):
                theirs = own.get((group, p.who, firms_on(sec)))
                if theirs:
                    sec.firms[i] = theirs.pop(0)
            key = (group, sec.unnamed, tuple((p.who, p.speed, tuple(p.charges)) for p in sec.firms))
            if key in alike:
                alike[key].pages += sec.pages
            else:
                alike[key] = sec
                out.append(sec)
        if secs:
            before.add(secs[0].firms[0].who)
    return out


def _split_plain(sections: list[SplitSection]) -> list[str]:
    """split_pages as the plain text says it: 'Alex B. Counsel, at Daily: Original $3.25 + Copy $1.25 + ... =
    $7.625 a page', and what the firms pay together (not for one firm's own: SplitSection.own)."""
    out = []
    for sec in sections:
        out.append(f"  {sec.label}:")
        for p in sec.firms:
            bits = " + ".join(f"{charge} {money_exact(a)}" for charge, a in p.charges)
            out.append(f"    {p.who}, at {p.speed}: {bits} = {money_exact(p.total)} a page")
        if not isinstance(sec, _OwnSection):
            out.append(f"    Together: {money_exact(sec.total)} a page; for the {_pages(sec.pages)}: "
                       f"{money_exact(_d(sec.total * sec.pages))}")
        if sec.note:
            out.append(f"    {sec.note}")
    return out


def _split_tables(sections: list[SplitSection]) -> list[str]:
    """split_pages as tables: for each stretch a row per firm, a column per charge and what it pays a page in
    all, then the firms together (not for one firm's own: SplitSection.own)."""
    parts = []
    for sec in sections:
        charges = list(dict.fromkeys(c for p in sec.firms for c, _ in p.charges))
        heads = [("Firm", "left"), ("Speed", "left")] + [(_e(c), "right") for c in charges] + [("A page", "right")]
        out = [f"<p><b>{_e(sec.label)}</b></p>", _TABLE, _cells(heads, "th")]
        for p in sec.firms:
            mine = dict(p.charges)
            out.append(_cells([(_e(p.who), "left"), (_e(p.speed), "left")]
                              + [(money_exact(mine[c]) if c in mine else "—", "right") for c in charges]
                              + [(f"<b>{money_exact(p.total)}</b>", "right")]))
        if not isinstance(sec, _OwnSection):
            out.append(f"<tr><td colspan='{len(charges) + 2}' align='right'><b>Together, a page (× "
                       f"{sec.pages:,} = {money_exact(_d(sec.total * sec.pages))})</b></td>"
                       f"<td align='right'><b>{money_exact(sec.total)}</b></td></tr>")
        out.append("</table>")
        if sec.note:
            out.append(f"<p class='muted'>{_e(sec.note)}</p>")
        parts.append("".join(out))
    return parts


# Under SPLIT_HEADING when an invoice rounded a price a page to the cent (Quote.page_rounded)
SPLIT_EXACT = ("The prices a page here are exact; each invoice rounds its own price a page to the cent (see what "
               "each firm pays above).")


# The heading of split_pages in the math (OWN_HEADING in the math of one firm's invoice, sent to that firm)
SPLIT_HEADING = "Who pays what a page, on pages ordered together at different speeds"
OWN_HEADING = "What this firm pays a page, on pages ordered together at different speeds"


def explain(made: list[tuple[FirmInvoice, str]], layout: str = "invoice",
            one_firm: bool = False) -> tuple[str, str]:
    """(html, plain text) of the math of each invoice: (FirmInvoice, its number) pairs, the number "" for one
    not made yet. layout: "invoice" (a table for each invoice and speed) or "firms" (a table for each set of
    firms and speed, a column per firm); the plain text is the same for both. Pages ordered together at different
    speeds get a section of their own after the invoices, what each firm on them pays a page (split_pages).
    one_firm: the math of one invoice (the first of `made`), to send that firm, shows only what that firm owes
    (the user, 2026-10-21): of those pages, its own row alone under OWN_HEADING (SplitSection.own), not the other
    firms' nor the firms together."""
    if one_firm:
        made = made[:1]
    parts = _by_firms(made) if layout == "firms" else _by_invoice(made)
    plain = _plain(made)
    split = split_pages(made)
    if one_firm:
        split = [sec.own() for sec in split]
    if split:
        rounded = any(q.page_rounded for f, _ in made for q in f.quotes)
        heading = OWN_HEADING if one_firm else SPLIT_HEADING
        parts.append(f"<h2>{_e(heading)}</h2>")
        if rounded:
            parts.append(f"<p class='muted'>{_e(SPLIT_EXACT)}</p>")
        parts += _split_tables(split)
        plain += [heading] + ([f"  {SPLIT_EXACT}"] if rounded else []) + _split_plain(split) + [""]
    check = together(made)
    if check:
        parts.append("<h2>All the firms together</h2>")
        parts += [f"<p>{_e(x)}</p>" for x in check]
        plain += ["All the firms together"] + [f"  {x}" for x in check]
    return "\n".join(parts), "\n".join(plain).rstrip() + "\n"


def to_pdf(html_text: str, out: Path) -> Path:
    """Saves the math as a PDF of letter pages (as many as it takes) at out, replacing a file there (the Save
    box asked); returns the path."""
    import io

    import pymupdf

    from .pdfout import mark
    page = pymupdf.paper_rect("letter")
    box = page + (54, 54, -54, -54)  # 3/4 inch margins
    story = pymupdf.Story(html=f"<h1 style='font-size:15pt'>The math</h1>{html_text}", user_css=CSS)
    data = io.BytesIO()
    writer = pymupdf.DocumentWriter(data)
    more = True
    while more:
        dev = writer.begin_page(page)
        more, _ = story.place(box)
        story.draw(dev)
        writer.end_page()
    writer.close()
    with pymupdf.open("pdf", data.getvalue()) as doc:
        mark(doc, "math")
        doc.set_metadata({**doc.metadata, "title": "The math"})
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        doc.save(out, garbage=3, deflate=True)
    return Path(out)


MATH_SUFFIX = " - the math.pdf"  # the end of every math PDF's name Generate saves (save_math)


def is_math_file(path: Path) -> bool:
    """A math PDF save_math saved: '... - the math.pdf', or '... - the math (2).pdf' beside one of that name."""
    return bool(re.search(r" - the math(?: \(\d+\))?\.pdf$", Path(path).name, re.I))


def save_math(made: list[tuple[FirmInvoice, str, Path]], save: str = "both", layout: str = "invoice") -> list[Path]:
    """Saves the math of the invoices one Generate just made ((FirmInvoice, number, its file) each), as
    Settings.save_math says (settings.MATH_SAVES), in Settings.math_layout: "each", a PDF next to each invoice,
    named after it ("Invoice 2026-0012 - Jane Roe v. X.Y. Holding Corporation - Alex B. Counsel - the math.pdf"),
    to send the firm that asks, showing only what that firm owes (explain's one_firm); "all", one for all of them
    (everyone's amounts) next to the first ("Invoices 2026-0012 to 2026-0013 - Jane Roe v. X.Y. Holding
    Corporation - the math.pdf"), to look back at the whole job; "both" (but one invoice alone gets only its own:
    everyone's would add only the other firms' rows, and the firms together, on pages ordered together at
    different speeds);
    "off", none. Invoices made in another reporter's name
    (Whose pages...) get "all of them" apart from the user's ("Invoices DS-2026-0001 to DS-2026-0002 - ..."):
    their math is theirs. Never over a file already there (pdfout.unique_path). Each is saved on its own: one
    that can't be (a full disk, a folder that went away) is logged, and the others are still saved. Returns the
    files saved."""
    from .log import error as log_error
    from .pdfout import safe_filename, short_caption, unique_path
    if save == "off" or not made:
        return []
    out = []

    def keep(of: list, path: Path, one_firm: bool = False) -> None:
        """Saves the math of these (FirmInvoice, number) as `path`, or a name beside it (one_firm: explain's)."""
        try:
            out.append(to_pdf(explain(of, layout, one_firm)[0], unique_path(path)))
        except Exception as e:
            log_error("could not save the math of an invoice", e)

    if save in ("each", "both"):
        for f, number, path in made:
            keep([(f, number)], path.with_name(path.stem + MATH_SUFFIX), one_firm=True)
    for reporter in dict.fromkeys(f.opts.reporter for f, _, _ in made):
        theirs = [x for x in made if x[0].opts.reporter == reporter]
        if save == "all" or (save == "both" and len(theirs) > 1):
            numbers = [n for _, n, _ in theirs if n]
            name = (f"Invoice {numbers[0]}" if len(numbers) == 1 else
                    f"Invoices {numbers[0]} to {numbers[-1]}" if numbers else "Invoices")
            stem = safe_filename(" - ".join(x for x in (name, short_caption(theirs[0][0].case.get("case_name")))
                                            if x))
            keep([(f, n) for f, n, _ in theirs], theirs[0][2].parent / (stem + MATH_SUFFIX))
    return out
