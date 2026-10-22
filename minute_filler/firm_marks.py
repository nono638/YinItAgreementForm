"""Each firm of a trial marked the same way wherever the window names it, so the reporter can tell them apart at a
glance (the user, 2026-10-21): as court exhibits are marked, the plaintiffs' firms are numbered 1, 2, 3, the
defense firms lettered A, B, C, and any other firm (a side not known, a sender of an e-mail) 001, 002. Each side
has its colours (gui.badges: oranges for the plaintiffs, blues for the defense, grey-greens for the others, a pair
told apart with the commoner colour blindness too), and each firm of a side its own shade (Mark.shade).

A firm is one however its attorneys are listed: "Dana Smith" of Smith Law on one day and "Smith Law, LLP" on
another get the same mark (firm_id). Which side it is on comes from the attorney's party ("Attorneys for
Plaintiff", "Defendants/Third-Party Plaintiffs": a defendant first, see side). Marks are given in the order the
firms first appear on the trial's days (marks), so they stay put as the days are clicked through."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Attorney

PLAINTIFF, DEFENSE, OTHER = "plaintiff", "defense", "other"

# words ending a firm's name that don't tell firms apart ("Smith Law, LLP" is Smith Law)
_FIRM_ENDINGS = re.compile(r"\b(?:llp|pllc|llc|pc|esq|esquire|inc|ltd|attorneys at law)$")  # (no dots: firm_id)


def side(party: str) -> str:
    """The side a party is on: 'Attorneys for Plaintiff' -> PLAINTIFF; 'Defendants', 'Respondent' -> DEFENSE (also
    'Defendant/Third-Party Plaintiff': a defendant first); anything else ('', 'sender') -> OTHER."""
    p = (party or "").lower()
    if re.search(r"defendant|respondent", p):
        return DEFENSE
    if re.search(r"plaintiff|petitioner|claimant", p):
        return PLAINTIFF
    return OTHER


def firm_id(a: Attorney) -> str:
    """What makes an entry the same firm as another: its firm's name without punctuation, case and endings like
    LLP ('Smith Law, LLP' and 'smith law' -> 'smith law'), else its attorney's name; "" for neither."""
    firm = re.sub(r"[^\w& ]+", " ", (a.firm or "").lower().replace(".", ""))  # ('P.C.' -> 'pc')
    firm = " ".join(firm.split())
    while True:
        cut = _FIRM_ENDINGS.sub("", firm).strip(" ,")
        if cut == firm:
            break
        firm = cut
    if firm:
        return "firm:" + firm
    name = " ".join((a.name or "").lower().split())
    return "name:" + name if name else ""


@dataclass(frozen=True)
class Mark:
    """A firm's mark: its badge ('1', 'A', '001'), side (PLAINTIFF, DEFENSE or OTHER) and shade (its place among
    its side's firms, from 0: gui.badges picks the colour)."""
    badge: str
    side: str
    shade: int


def _letters(n: int) -> str:
    """0 -> 'A', 25 -> 'Z', 26 -> 'AA', as exhibits run on."""
    out = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def badge(side_: str, n: int) -> str:
    """The n-th (from 0) badge of a side: plaintiffs '1', '2'; defense 'A', 'B'; others '001', '002'."""
    if side_ == PLAINTIFF:
        return str(n + 1)
    if side_ == DEFENSE:
        return _letters(n)
    return f"{n + 1:03}"


def marks(attorneys: list[Attorney]) -> dict[str, Mark]:
    """The marks of the firms of these attorneys, by firm_id, in the order they come (a trial's days in order:
    each firm keeps the mark it got first). Placeholder rows and entries naming nobody get none."""
    out: dict[str, Mark] = {}
    count = {PLAINTIFF: 0, DEFENSE: 0, OTHER: 0}
    for a in attorneys:
        key = firm_id(a)
        if not key or key in out or a.is_placeholder():
            continue
        s = side(a.party)
        out[key] = Mark(badge(s, count[s]), s, count[s])
        count[s] += 1
    return out


def mark_of(a: Attorney | None, given: dict[str, Mark]) -> Mark | None:
    """The mark of an attorney's firm among those given (marks), None when it has none."""
    return given.get(firm_id(a)) if a is not None else None
