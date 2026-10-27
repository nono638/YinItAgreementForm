"""Each firm of a trial marked the same way wherever the window names it, so the reporter can tell them apart at a
glance (the user, 2026-10-21): by a colour, its side's (warm colours for the plaintiffs, cool ones for the defense,
greys and greens for any other firm: a side not known, a sender of an e-mail), each firm of a side its own colour of
them (Mark.shade). The window shows a mark as a small square of its colour before the firm's name and a thin stripe
of it (gui.badges); nothing is written on the square (the user, 2026-10-26: numbers and letters had nothing to do
with the firms' names).

A firm is one however its attorneys are listed: "Dana Smith" of Smith Law on one day and "Smith Law, LLP" on
another get the same mark (firm_id). Which side it is on comes from the attorney's party ("Attorneys for
Plaintiff", "Defendants/Third-Party Plaintiffs": the role named first, see side). Marks are given in the order the
firms first appear on the trial's days (marks), so they stay put as the days are clicked through."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Attorney, firm_key

PLAINTIFF, DEFENSE, OTHER = "plaintiff", "defense", "other"
# by side, the firms' colours in turn (Mark.shade), each far from the one before: with nothing written on the
# window's squares (gui.badges), two firms of a side are told apart by these alone (a seventh plaintiffs' firm
# takes the first again). None is the amber the window marks a field to check with.
SHADES = {
    PLAINTIFF: ["#ea580c", "#b91c1c", "#db2777", "#78350f", "#e11d48", "#9a3412"],  # orange, red, pink, brown...
    DEFENSE: ["#2563eb", "#0d9488", "#7c3aed", "#1e3a8a", "#0891b2", "#4338ca"],    # blue, teal, violet, navy...
    OTHER: ["#4b5563", "#15803d", "#78716c"],                                         # slate, green, stone
}

# words ending a firm's name that firm_key keeps but don't tell firms apart ("Smith Law, Attorneys at Law" is
# Smith Law; firm_key takes off "LLP", "P.C." and the like itself)
_FIRM_ENDINGS = re.compile(r"(?: (?:esquire|attorneys at law))+$")
_ROLES = [(DEFENSE, re.compile(r"defendant|respondent")), (PLAINTIFF, re.compile(r"plaintiff|petitioner|claimant"))]


def side(party: str) -> str:
    """The side a party is on, by the role named first: 'Attorneys for Plaintiff' -> PLAINTIFF; 'Defendants',
    'Respondent', 'Defendant/Third-Party Plaintiff' -> DEFENSE; 'Plaintiff/Counterclaim Defendant' -> PLAINTIFF;
    anything else ('', 'sender') -> OTHER."""
    p = (party or "").lower()
    found = [(m.start(), s) for s, rx in _ROLES if (m := rx.search(p))]
    return min(found)[1] if found else OTHER


def firm_id(a: Attorney) -> str:
    """What makes an entry the same firm as another: its Attorney.key() (models.firm_key reads a firm: 'Counsel &
    Counsel, LLP' and 'counsel and counsel' -> 'counsel and counsel', 'The Smith Law Firm' -> 'smith law firm';
    without a firm, its attorney's name: 'Dana Smith, Esq.' -> 'dana smith esq'), with endings like 'Attorneys at
    Law' taken off as well, and those before them ('Smith Law, LLP, Attorneys at Law' -> 'smith law'); "" for an
    entry naming nobody. Made from key(), so the entries of one key have one id: batch.trial_marks, which goes by
    key(), gives each entry one mark, and no colour is given to a firm twice over."""
    key = a.key()
    while (cut := firm_key(_FIRM_ENDINGS.sub("", key))) and cut != key:  # ("Attorneys at Law" alone stays)
        key = cut
    return key


@dataclass(frozen=True)
class Mark:
    """A firm's mark: its side (PLAINTIFF, DEFENSE or OTHER) and shade (its place among its side's firms, from 0:
    shade_of gives its colour)."""
    side: str
    shade: int


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
        out[key] = Mark(s, count[s])
        count[s] += 1
    return out


def shade_of(mark: Mark) -> str:
    """The colour of a firm's mark ("#ea580c"): its side's, in turn (SHADES)."""
    row = SHADES.get(mark.side, SHADES[OTHER])
    return row[mark.shade % len(row)]


def mark_of(a: Attorney | None, given: dict[str, Mark]) -> Mark | None:
    """The mark of an attorney's firm among those given (marks), None when it has none."""
    return given.get(firm_id(a)) if a is not None else None
