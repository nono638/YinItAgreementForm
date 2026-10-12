"""The tick boxes of the Records window's invoices, the status they spell out, and the colour of each row
(Settings -> Records). For the reporter's own bookkeeping, as much or as little of it as they like: nothing pops
up or reminds.

A box (TrackBox) is Paid (kept as the invoice's status, with what was paid) or a tick kept with the invoice
(Invoice.checks: its key and the day it was ticked, {"transcribed": "2026-10-10"}). Built in, in this order:
Paid (in use from the start), Invoice sent, Transcribed and Transcript sent (switched on in Settings); the user
can add boxes of their own ("c" and a few letters for a key, which never changes, whatever the box is called).

The Status column says each box in use, ticked or not, in the words the box has for each ("Paid, Transcribed,
Not sent"); a blank word says nothing. A void invoice says "Void".

A row is coloured by the first colour rule (ColourRule) that matches it: each rule names, for some of the boxes,
ticked or not ticked (the others: either way), and can ask that every firm of the transcript has paid
(EVERY_PAID: the invoice is "ready to send" only then, as the invoice says the transcript is delivered once
every party has paid). A rule that names a box not in use is skipped, so the rules given (default_rules) colour
the rows whichever boxes are in use. For example, with Paid, Transcribed and Transcript sent in use: four firms
ordered the 6/3/2026 transcript; until it is transcribed, an unpaid invoice is teal and a paid one yellow; once
it is (one tick of Transcribed ticks the four: TrackBox.whole), an unpaid one is blue, and every one is orange,
ready to send, once all four have paid; a sent one is green.

The invoices of one transcript (Transcripts): the same index number (712345/2021 and 712345-21 are one; without
one, the same case name), the same reporter and the same days. Every firm paid looks wider: every invoice of the
index number and reporter that shares a day with this one (a firm that ordered one day of a trial counts for the
invoices of that day)."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, replace

PAID, TICK = "paid", "tick"  # TrackBox.kind: kept as the invoice's status, or a tick kept with the invoice
EVERY_PAID = "every_paid"    # a rule's condition: every firm of the transcript has paid (worked out, not ticked)
EVERY_PAID_NAME = "Every firm paid"
CUSTOM_KEY = re.compile(r"c[0-9a-z]{1,32}")  # the key of a box of the user's own ("c3f9a0b12")
COLOUR = re.compile(r"#[0-9a-fA-F]{6}")
# The Records columns a box's name may not take (they would be two columns of one name in the CSV copies and
# the window): the CSV copies' (records.INVOICE_COLUMNS) and these, which only the window has
WINDOW_HEADINGS = ("Paid", "No.", "Pages billed", "Offered (each party)", "Speed ordered", "Deleted on",
                   "Gone for good on")


@dataclass
class TrackBox:
    """A tick box of the Records window's invoices. key: what it is kept as, never changed by renaming it
    ("transcribed"; the user's own: "c" and some letters); name: its column's heading; yes / no: what the
    Status column says when it is ticked and when it isn't ("" says nothing); on: in use (a column, and in the
    status and the colours); kind: PAID or TICK; whole: ticking or unticking it does the same to the other
    invoices of the same transcript (Transcribed)."""
    key: str
    name: str
    yes: str = ""
    no: str = ""
    on: bool = False
    kind: str = TICK
    whole: bool = False

    @property
    def built_in(self) -> bool:
        """One of the boxes the app has (renamed or switched off, but never removed)."""
        return any(b.key == self.key for b in BUILT_IN)

    def word(self, ticked: bool) -> str:
        """What the Status column says of this box."""
        return self.yes if ticked else self.no


@dataclass
class ColourRule:
    """A colour for the rows it matches. when: box key (or EVERY_PAID) -> True (ticked) or False (not); a box
    not named matches either way. name: what the Status filter and the row's tooltip call it."""
    name: str
    colour: str  # "#16a34a"
    when: dict[str, bool] = field(default_factory=dict)


BUILT_IN = (
    TrackBox("paid", "Paid", "Paid", "Not paid", True, PAID),
    TrackBox("invoice_sent", "Invoice sent", "Invoice sent", "Invoice not sent"),
    TrackBox("transcribed", "Transcribed", "Transcribed", "Not transcribed", whole=True),
    TrackBox("sent", "Transcript sent", "Sent", "Not sent"),
)
GREEN, ORANGE, BLUE, YELLOW, TEAL = "#16a34a", "#ea580c", "#2563eb", "#ca8a04", "#0d9488"
# The first that matches colours the row; one naming a box not in use is skipped. With Paid alone: the last two.
# With Paid and Transcript sent: Done, the second Ready to send, Paid, waiting on other firms, and Not paid.
# With Paid and Transcribed: the second to the fifth. With the three: the first five.
DEFAULT_RULES = (
    ColourRule("Done", GREEN, {"sent": True}),
    ColourRule("Ready to send", ORANGE, {EVERY_PAID: True, "transcribed": True}),
    ColourRule("Transcribed, waiting for payment", BLUE, {"transcribed": True}),
    ColourRule("Paid, not transcribed", YELLOW, {"paid": True, "transcribed": False}),
    ColourRule("Not paid, not transcribed", TEAL, {"paid": False, "transcribed": False}),
    ColourRule("Ready to send", ORANGE, {EVERY_PAID: True, "sent": False}),
    ColourRule("Paid, waiting on other firms", BLUE, {"paid": True, EVERY_PAID: False, "sent": False}),
    ColourRule("Paid", GREEN, {"paid": True}),
    ColourRule("Not paid", TEAL, {"paid": False}),
)


def default_boxes() -> list[TrackBox]:
    """The boxes a new user has (copies: changing one doesn't change BUILT_IN)."""
    return [replace(b) for b in BUILT_IN]


def default_rules() -> list[ColourRule]:
    """The colour rules a new user has (copies)."""
    return [replace(r, when=dict(r.when)) for r in DEFAULT_RULES]


def box_rows(boxes: list[TrackBox]) -> list[dict]:
    """The boxes as Settings keeps them (Settings.tracking_boxes)."""
    return [asdict(b) for b in boxes]


def rule_rows(rules: list[ColourRule]) -> list[dict]:
    """The colour rules as Settings keeps them (Settings.tracking_rules)."""
    return [asdict(r) for r in rules]


def _taken_headings() -> set[str]:
    """The headings of the Records columns a box may not be named (lower case)."""
    from .records import INVOICE_COLUMNS  # (here: records imports the settings, through log, and they import this)
    return {h.lower() for h in (*INVOICE_COLUMNS, *WINDOW_HEADINGS)}


def clean_boxes(rows) -> list[TrackBox]:
    """The boxes of a settings file, checked: a row that isn't one is dropped (and one with a key seen before,
    or a box of the user's own without a name), a built-in box missing is put back in its place, and a box
    whose name is another column's ("Notes", "Billed") or another box's gets " (2)". A built-in box keeps its
    kind; one named blank gets its usual name back."""
    built = {b.key: b for b in BUILT_IN}
    out: list[TrackBox] = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or not isinstance(r.get("key"), str) or r["key"] in {b.key for b in out}:
            continue
        key = r["key"]
        if key not in built and not CUSTOM_KEY.fullmatch(key):
            continue
        text = {k: (r.get(k) if isinstance(r.get(k), str) else "").strip() for k in ("name", "yes", "no")}
        if key not in built and not text["name"]:
            continue
        base = built.get(key)
        out.append(TrackBox(key, text["name"] or base.name, text["yes"], text["no"],
                            r.get("on") is True, base.kind if base else TICK,
                            r.get("whole") is True if (base is None or base.kind == TICK) else False))
    for i, b in enumerate(BUILT_IN):  # (after the built-in box before it, as they are listed)
        if all(x.key != b.key for x in out):
            before = [n for n, x in enumerate(out) if x.key in {y.key for y in BUILT_IN[:i]}]
            out.insert(before[-1] + 1 if before else 0, replace(b))
    taken = _taken_headings() - {"paid"}  # (the Paid box is the Paid column)
    for b in out:
        name, n = b.name, 2
        while name.lower() in taken or (name.lower() == "paid" and b.kind != PAID):
            name, n = f"{b.name} ({n})", n + 1
        b.name = name
        taken.add(name.lower())
    return out


def clean_rules(rows, boxes: list[TrackBox]) -> list[ColourRule]:
    """The colour rules of a settings file, checked against the boxes: a rule that isn't one, with a colour that
    isn't "#rrggbb", or naming a box there isn't (a box removed, a rule imported from another computer) is
    dropped. A rule with no condition is kept: it colours every row (the Settings window says so)."""
    keys = {b.key for b in boxes} | {EVERY_PAID}
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or not isinstance(r.get("colour"), str) or not COLOUR.fullmatch(r["colour"]):
            continue
        when = r.get("when", {})
        if not isinstance(when, dict) or not all(k in keys and isinstance(v, bool) for k, v in when.items()):
            continue
        name = r.get("name") if isinstance(r.get("name"), str) else ""
        out.append(ColourRule(name.strip(), r["colour"].lower(), dict(when)))
    return out


def is_ticked(inv, box: TrackBox) -> bool:
    """Whether the invoice (a records.Invoice) has this box ticked: Paid by its status."""
    return inv.status == "paid" if box.kind == PAID else box.key in inv.checks


def status_words(inv, boxes: list[TrackBox]) -> str:
    """The Status column: the word of each box in use, ticked or not ("Paid, Transcribed, Not sent"); "Void"
    for a void invoice."""
    if inv.status == "void":
        return "Void"
    return ", ".join(w for b in boxes if b.on for w in [b.word(is_ticked(inv, b))] if w)


def _case(inv) -> str:
    """The index number as cases compare it ("712345/2021"; batch.index_key), else the case name; "" when there
    is neither."""
    from .batch import index_key  # (here: batch imports the settings, which import this module)
    key = index_key(inv.index_no)
    if key:
        return key
    name = " ".join(inv.case_name.lower().split())
    return f"case: {name}" if name else ""


def _days(inv) -> frozenset[str]:
    """The days an invoice bills ("6/3/2026, 6/4/2026" -> both), or its dates as written when no day can be read
    from them; empty without any."""
    from .extract_regex import find_dates
    days = frozenset(d for _, _, d in find_dates(inv.dates or ""))
    return days or (frozenset([" ".join(inv.dates.split())]) if (inv.dates or "").strip() else frozenset())


class Transcripts:
    """The invoices (not void, not deleted) of each transcript, for Transcribed ticked on all of them (mates)
    and for Every firm paid (every_paid). An invoice without an index number or case name, or without days, is
    a transcript of its own."""

    def __init__(self, invoices: list):
        self.live = [i for i in invoices if i.status != "void" and not i.deleted]
        self._case = {i.invoice_no: (_case(i), i.reporter or "") for i in self.live}
        self._days = {i.invoice_no: _days(i) for i in self.live}
        self._by_case: dict[tuple, list] = {}
        for i in self.live:
            if self._case[i.invoice_no][0] and self._days[i.invoice_no]:
                self._by_case.setdefault(self._case[i.invoice_no], []).append(i)

    def _key(self, invoice_no: str):
        """The invoice's case (with its reporter) and days, or None when it is a transcript of its own (or not
        among the live invoices)."""
        case, days = self._case.get(invoice_no), self._days.get(invoice_no)
        return (case, days) if case and case[0] and days else None

    def mates(self, invoice_no: str) -> list[str]:
        """The numbers of the live invoices of the same transcript as this one, itself among them (the same case,
        reporter and days); just itself when it is a transcript of its own; none when it is void or deleted."""
        key = self._key(invoice_no)
        if key is None:
            return [invoice_no] if invoice_no in self._case else []
        return [i.invoice_no for i in self._by_case[key[0]] if self._days[i.invoice_no] == key[1]]

    def every_paid(self, inv) -> bool:
        """Whether this invoice and every other live one of its case and reporter that shares a day with it are
        paid."""
        key = self._key(inv.invoice_no)
        if key is None:
            return inv.status == "paid"
        return inv.status == "paid" and all(o.status == "paid" for o in self._by_case[key[0]]
                                            if self._days[o.invoice_no] & key[1])


def state_of(inv, boxes: list[TrackBox], transcripts: Transcripts | None = None) -> dict[str, bool]:
    """Box key -> ticked, for the boxes in use, and EVERY_PAID while Paid is in use (with no transcripts: this
    invoice alone)."""
    state = {b.key: is_ticked(inv, b) for b in boxes if b.on}
    if any(b.on and b.kind == PAID for b in boxes):
        state[EVERY_PAID] = transcripts.every_paid(inv) if transcripts is not None else inv.status == "paid"
    return state


def rule_for(inv, boxes: list[TrackBox], rules: list[ColourRule],
             transcripts: Transcripts | None = None) -> ColourRule | None:
    """The first rule that matches the invoice, or None (a void invoice has none). A rule naming a box not in
    use is skipped."""
    if inv.status == "void":
        return None
    state = state_of(inv, boxes, transcripts)
    return next((r for r in rules if all(k in state and state[k] == v for k, v in r.when.items())), None)


def usable(rule: ColourRule, boxes: list[TrackBox]) -> bool:
    """Whether every box the rule names is in use (else it is skipped)."""
    keys = {b.key for b in boxes if b.on} | ({EVERY_PAID} if any(b.on and b.kind == PAID for b in boxes) else set())
    return all(k in keys for k in rule.when)


def reachable(boxes: list[TrackBox], rules: list[ColourRule]) -> set[int]:
    """The places in `rules` of those that can colour a row: tried on every way the boxes in use can be ticked
    (a rule below others that always match first can't: with Paid, Transcribed and Transcript sent, "Paid,
    waiting on other firms" never comes up). With very many boxes, those whose boxes are all in use."""
    import itertools
    keys = [b.key for b in boxes if b.on]
    paid = next((b.key for b in boxes if b.on and b.kind == PAID), None)
    if paid:
        keys.append(EVERY_PAID)
    if len(keys) > 12:
        return {n for n, r in enumerate(rules) if usable(r, boxes)}
    out = set()
    for ticks in itertools.product((False, True), repeat=len(keys)):
        state = dict(zip(keys, ticks))
        if paid and state[EVERY_PAID] and not state[paid]:
            continue  # (every firm paid: this one too)
        n = next((n for n, r in enumerate(rules) if all(k in state and state[k] == v for k, v in r.when.items())),
                 None)
        if n is not None:
            out.add(n)
    return out


def rule_names(boxes: list[TrackBox], rules: list[ColourRule]) -> list[str]:
    """The names of the rules that can colour a row (reachable), each once, in order."""
    can = reachable(boxes, rules)
    return list(dict.fromkeys(r.name for n, r in enumerate(rules) if n in can and r.name))


NOT_PAID = "Not paid"  # the Records button's count of the invoices not paid (Settings.records_count)


def count_names(boxes: list[TrackBox], rules: list[ColourRule]) -> list[str]:
    """What the main window's Records button can count (Settings -> Records): Not paid, then the names of the
    colours that can colour a row, as the Records window's Status filter lists them ("Paid" and "Not paid" once)."""
    return [NOT_PAID] + [n for n in rule_names(boxes, rules) if n.lower() not in ("paid", NOT_PAID.lower())]


def count_of(name: str, invoices: list, boxes: list[TrackBox], rules: list[ColourRule]) -> int:
    """How many of the invoices (every one not in the trash) the Records button counts: those not paid (and not
    void) for "Not paid", else those coloured by the colour of that name (both "Ready to send" colours count), 0
    for a name no colour can take with these boxes, or none (""). Every firm paid looks at all of them."""
    if not name:
        return 0
    if name == NOT_PAID:
        return sum(1 for i in invoices if i.status == "open")
    if name not in rule_names(boxes, rules):
        return 0
    transcripts = Transcripts(invoices)
    return sum(1 for i in invoices if (r := rule_for(i, boxes, rules, transcripts)) is not None and r.name == name)


def new_key(boxes: list[TrackBox]) -> str:
    """A key for a box of the user's own, not one any box has: "c" and 8 hex digits ("c3f9a0b12"), made up at
    random so that a box removed and another added later don't share the ticks kept under it."""
    import uuid
    while True:
        key = "c" + uuid.uuid4().hex[:8]
        if all(b.key != key for b in boxes):
            return key
