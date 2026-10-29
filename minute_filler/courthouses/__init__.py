"""Which courthouse the program works for, and the tables that follow from its profile (MIGRATION.md).

Every module that needs to know which outputs exist asks here (or reads a table built here), instead of naming
them itself: settings.OUTPUTS and OUTPUT_FOLDERS, records.KINDS, the preview's names and colours (by_mark) and
batch's forms made once for a trial (keys("form")) and the folders inside a case's own (SUBFOLDERS) all come
from the courthouse's outputs. use() switches to another courthouse and refreshes these tables in place, so
`from .settings import OUTPUTS` keeps working in every module (tests use it to try a made-up courthouse); it is
not meant to run while work is going on. The
court holidays Settings -> Dates starts with are the courthouse's too (holiday_rows).

For now there is one courthouse, Queens Supreme Court, Civil Term (queens_supreme_civil); choosing one in
Settings comes in a later release.
"""
from __future__ import annotations

from .base import ASKS, GROUPS, Courthouse, OutputSpec, Part, Party, SplitRule  # noqa: F401 (for the profiles)
from .queens_supreme_civil import COURTHOUSE as QUEENS_SUPREME_CIVIL

BUILT_IN = (QUEENS_SUPREME_CIVIL,)  # the courthouses that come with the program (the build bundles their makers)
OUTPUTS: dict[str, str] = {}         # what Generate can make: key -> label, as listed (settings.OUTPUTS)
OUTPUT_FOLDERS: dict[str, str] = {}  # key -> its own folder under Documents (settings.OUTPUT_FOLDERS)
SUBFOLDERS: dict[str, str] = {}      # key (or "math", "inputs") -> its folder inside a case's own (settings.SUBFOLDERS)
# the folder the documents read are copied into, inside a case's own (Settings.save_inputs), whatever the courthouse
INPUTS_FOLDER = "Inputs"
_current: Courthouse | None = None


def current() -> Courthouse:
    """The courthouse the program works for."""
    return _current


def outputs() -> tuple[OutputSpec, ...]:
    """The outputs the courthouse makes, as listed."""
    return _current.outputs


def output(key: str) -> OutputSpec | None:
    """The output of this key, or None when the courthouse has none such."""
    return next((o for o in _current.outputs if o.key == key), None)


def keys(group: str | None = None) -> list[str]:
    """The outputs' keys as listed; with `group` ("form", "billing"...), only those of that group."""
    return [o.key for o in _current.outputs if group is None or o.group == group]


def make_order(wanted) -> list[str]:
    """The outputs among `wanted` (keys; unknown ones are left out) in the order a job's files are made: by
    group (GROUPS: the run sheet first, the invoices last), then as listed. ["invoice", "agreement",
    "runsheet"] -> ["runsheet", "agreement", "invoice"]."""
    wanted = set(wanted)
    listed = [o for o in _current.outputs if o.key in wanted]
    return [o.key for o in sorted(listed, key=lambda o: GROUPS.index(o.group))]  # (sorted keeps the listed order)


def panel_order() -> list[OutputSpec]:
    """The outputs in the order of the window's Outputs row and Options ▾ (OutputSpec.panel_pos; a tie: as
    listed)."""
    return sorted(_current.outputs, key=lambda o: o.panel_pos)


def asks(outputs, question: str) -> bool:
    """True when any of these outputs (keys) asks this question before it is made (OutputSpec.asks, of ASKS:
    "firms", "speed"...)."""
    return any(o.key in set(outputs) and question in o.asks for o in _current.outputs)


def split_rules() -> tuple[SplitRule, ...]:
    """The ways the courthouse may divide a charge billed once for pages firms ordered together at different
    speeds (Courthouse.split_rules), its default first; () when it bills no such pages."""
    return _current.split_rules_impl()


def split_rule(key: str = "") -> SplitRule | None:
    """The courthouse's split rule of this key (Settings.invoice_split_rule), else its default (the first: a key
    it doesn't have, from another courthouse or a later version, falls back to it); None when it bills no pages
    ordered together at different speeds."""
    rules = split_rules()
    return next((r for r in rules if r.key == key), rules[0] if rules else None)


def speeds_together() -> int:
    """How many different speeds may share pages (Courthouse.speeds_together; 1 = they must all be one)."""
    return _current.speeds_together


def speed_upfront() -> bool:
    """Whether the firms of a split order must each commit to a speed before they are billed
    (Courthouse.speed_upfront), instead of choosing one from the invoice."""
    return _current.speed_upfront


def holiday_rows() -> list[dict]:
    """The courthouse's holidays as Settings.holidays keeps them: [{"name": "Columbus Day", "when": "2nd Monday of
    October"}, ...] (Courthouse.holidays), the list Settings -> Dates starts with and restores."""
    return [{"name": n, "when": w} for n, w in _current.holidays]


def by_mark(mark: str) -> OutputSpec | None:
    """The output whose PDFs carry this mark (pdfout.mark: "MOFR"), or None ("math", a detailed copy, "")."""
    return next((o for o in _current.outputs if mark and o.mark == mark), None)


def use(courthouse: Courthouse) -> Courthouse | None:
    """Works for `courthouse` from now on and refreshes the tables built from it (in place: the modules that
    imported them see the new ones). Returns the courthouse before it."""
    global _current
    before, _current = _current, courthouse
    OUTPUTS.clear()
    OUTPUTS.update((o.key, o.label) for o in courthouse.outputs)
    OUTPUT_FOLDERS.clear()
    OUTPUT_FOLDERS.update((o.key, o.folder) for o in courthouse.outputs if o.folder)
    SUBFOLDERS.clear()
    SUBFOLDERS.update((o.key, o.subfolder) for o in courthouse.outputs if o.subfolder)
    if courthouse.math_subfolder:
        SUBFOLDERS["math"] = courthouse.math_subfolder
    SUBFOLDERS["inputs"] = INPUTS_FOLDER
    return before


use(QUEENS_SUPREME_CIVIL)
