"""Date helpers shared by the forms, invoices, records and window: M/D/YYYY text and month arithmetic. Business
days and the court holidays (the day a form is dated, the delivery date) are workdays.py's."""
from __future__ import annotations

import calendar
from datetime import date


def us_date(d: date | str | None = None) -> str:
    """date(2026, 9, 30) or '2026-09-30...' -> '9/30/2026'; None = the clock's today (the day a form is dated may
    be later: workdays.document_day). Unreadable text comes back unchanged."""
    if d is None:
        d = date.today()
    elif isinstance(d, str):
        try:
            d = date.fromisoformat(d[:10])
        except ValueError:
            return d
    return f"{d.month}/{d.day}/{d.year}"


def add_months(d: date, months: int) -> date:
    """Same day of the month `months` later; the 31st becomes the month's last day when it has fewer."""
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))
