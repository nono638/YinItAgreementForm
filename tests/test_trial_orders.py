"""Who ordered a trial: a firm ticked orders the whole trial, every day of it, days read later too, as a standing
order (Settings.trial_orders "trial", the default: the user, 2026-10-24, "most common that one or more sides order
the entire trial"), unless the user said it orders some days only (Job.not_ordered: Who ordered's "Only 6/3/2026",
a firm unticked on a day in Excerpts...). batch.spread_orders keeps the days so; tick_firm, order_firm and
set_firm_speed are what Who ordered does; order_of and speed_shown what its rows say. The common case (a trial of 4
days, two firms ticked once) is billed exactly as ticking every day by hand was. With "day", each day is ticked on
its own, as before. Invoiced days stay as they were billed. All names and numbers are made up."""
import json

import pytest

from minute_filler.batch import (ShownSpeed, _date_key, expand_paths, fill_jobs, group, job_from_origin, job_origin,
                                 order_firm, order_of, pin_orders, read_docs, set_firm_speed, settle_split_speeds,
                                 speed_shown, spread_orders, tick_firm, trials)
from minute_filler.deliver import ledger_for
from minute_filler.excerpts import Run, case_days, firms_of, store
from minute_filler.invoice import default_speed
from minute_filler.models import Attorney

from helpers import pat_settings, transcript_pdf

DAYS = {"September 28, 2026": 30, "September 30, 2026": 20, "October 1, 2026": 40, "October 2, 2026": 50}


def dana():
    return Attorney(name="Dana Smith", firm="Smith Law", checked=True)


def settings(tmp_path, name: str):
    s = pat_settings()
    s.output_dir = str(tmp_path / name / "out")
    s.records_dir = str(tmp_path / name / "records")
    s.save_math = "off"
    return s


def read_days(tmp_path, s, days=DAYS, name="in"):
    """Jane Roe's trial, a transcript a day: each lists Advocate & Partners and Counsel & Counsel, neither ticked."""
    d = tmp_path / name
    d.mkdir()
    for day, n in days.items():
        transcript_pdf(d / f"Roe {day}.pdf", n, date=day)
    docs, errors = read_docs(expand_paths([str(d)]), s)
    assert not errors
    return docs


def days_of(jobs):
    return sorted(jobs, key=lambda j: _date_key(j.case.get("dates")))


def key_of(job, firm: str) -> str:
    return next(a.key() for a in job.case.attorneys if a.firm.startswith(firm))


def ticked(job) -> set[str]:
    return {a.firm for a in job.case.attorneys if a.checked}


@pytest.fixture
def s(tmp_path):
    return settings(tmp_path, "a")


@pytest.fixture
def trial(tmp_path, s):
    jobs = days_of(group(read_days(tmp_path, s), s))
    assert len(jobs) == 4 and not any(a.checked for j in jobs for a in j.case.attorneys)
    return jobs


def test_ticking_two_firms_once_bills_as_ticking_every_day_did(tmp_path, s, trial):
    """The typical trial: two firms tick once (tick_firm) and are billed, formed and asked about exactly as when
    each was ticked on every day by hand."""
    counsel, advocate = key_of(trial[0], "Counsel"), key_of(trial[0], "Advocate")
    tick_firm(trial, counsel, True, s, shown=trial[1])
    tick_firm(trial, advocate, True, s, shown=trial[1])
    assert all(ticked(j) == {"Counsel & Counsel", "Advocate & Partners, LLP"} for j in trial)
    s2 = settings(tmp_path, "b")
    by_hand = days_of(group(read_days(tmp_path, s2, name="in2"), s2))
    for j in by_hand:
        for a in j.case.attorneys:
            a.checked = True
    outputs = ["agreement", "invoice", "mofr"]

    def made(jobs, s) -> tuple:
        """What a run makes and records (one records database for both: the invoices it added)."""
        ledger = ledger_for(s)
        before = {i.invoice_no for i in ledger.invoices()}
        files = fill_jobs(jobs, s, outputs=outputs)
        invoices = sorted((i.bill_to, i.dates, i.pages, i.parties, sorted(i.amounts.items()), i.billed_speed)
                          for i in ledger.invoices()
                          if i.invoice_no not in before)
        names = sorted(p.name.split(" - ", 1)[1] if p.name.startswith("Invoice") else p.name for p in files)
        return names, invoices

    once, hand = made(trial, s), made(by_hand, s2)
    assert once == hand and len(once[0]) == 5 and len(once[1]) == 2
    assert [j.speeds for j in trial] == [j.speeds for j in by_hand]


def test_a_day_read_later_is_ordered_too(tmp_path, s, trial):
    """A standing order: a 5th transcript dropped later is ordered by every firm ordering the whole trial, at the
    speed it has; a firm that orders one day only isn't spread to it."""
    counsel, advocate = key_of(trial[0], "Counsel"), key_of(trial[0], "Advocate")
    tick_firm(trial, counsel, True, s, shown=trial[0])
    set_firm_speed(trial, counsel, "Daily")
    order_firm(trial, advocate, False, shown=trial[2])  # Advocate & Partners: only 10/1/2026
    assert [advocate in j.ticked_keys() for j in trial] == [False, False, True, False]
    later = read_days(tmp_path, s, {"October 5, 2026": 25}, name="later")
    jobs = days_of(group(later, s, trial))
    assert len(jobs) == 5
    new = jobs[-1]
    assert new.ticked_keys() == [counsel] and new.speeds == {counsel: "Daily"}
    assert order_of(jobs, counsel).words() == "The whole trial (5 days)"
    assert order_of(jobs, advocate).words() == "10/1/2026"


def test_a_firm_a_day_doesnt_name_is_added_to_it(s, trial):
    """A firm typed in on one day (Smith Law, on no transcript) orders every day: its row is added to the others."""
    trial[0].case.attorneys.append(dana())
    tick_firm(trial, dana().key(), True, s, shown=trial[0])
    assert all("Smith Law" in ticked(j) for j in trial)
    assert all(sum(a.firm == "Smith Law" for a in j.case.attorneys) == 1 for j in trial)


def test_an_invoiced_day_stays_as_it_was_billed(s, trial):
    trial[0].invoiced = True
    counsel = key_of(trial[0], "Counsel")
    tick_firm(trial, counsel, True, s, shown=trial[1])
    assert not trial[0].ticked_keys() and all(j.ticked_keys() == [counsel] for j in trial[1:])
    trial[0].case.attorneys[0].checked = True  # (billed to it: a tick there is spread to the days not billed)
    trial[0].invoiced = False
    tick_firm(trial, counsel, False, s, shown=trial[1])
    trial[0].invoiced = True
    for j in trial[0:1]:
        assert j.ticked_keys()  # (untouched)
    assert not any(j.ticked_keys() for j in trial[1:])


def test_an_untick_is_the_whole_trial(tmp_path, s, trial):
    """A firm unticked in Who ordered orders none of the trial, and no day says it doesn't: a day read later isn't
    ordered by it, and a tick later is the whole trial again."""
    counsel = key_of(trial[0], "Counsel")
    tick_firm(trial, counsel, True, s, shown=trial[0])
    tick_firm(trial, counsel, False, s, shown=trial[2])
    assert not any(j.ticked_keys() for j in trial) and not any(j.not_ordered for j in trial)
    jobs = days_of(group(read_days(tmp_path, s, {"October 5, 2026": 25}, name="later"), s, trial))
    assert not jobs[-1].ticked_keys()
    tick_firm(jobs, counsel, True, s, shown=jobs[1])
    assert all(j.ticked_keys() == [counsel] for j in jobs)


def test_a_tick_read_on_one_day_is_the_whole_trial(s, trial):
    """A firm a document ticks on one day (the sender of an e-mail about that day) orders the whole trial."""
    counsel = key_of(trial[2], "Counsel")
    next(a for a in trial[2].case.attorneys if a.key() == counsel).checked = True
    assert spread_orders(trial, s)
    assert all(j.ticked_keys() == [counsel] for j in trial)
    assert all(j.att_touched for j in trial if j is not trial[2])
    assert not spread_orders(trial, s)  # (nothing more to do)


def test_with_day_by_day_a_tick_is_the_day_shown(tmp_path, s, trial):
    s.trial_orders = "day"
    counsel = key_of(trial[0], "Counsel")
    tick_firm(trial, counsel, True, s, shown=trial[1])
    assert [bool(j.ticked_keys()) for j in trial] == [False, True, False, False]
    assert not spread_orders(trial, s)
    jobs = days_of(group(read_days(tmp_path, s, {"October 5, 2026": 25}, name="later"), s, trial))
    assert not jobs[-1].ticked_keys()


def test_a_firm_unticked_on_a_day_in_excerpts_stays_off_it(tmp_path, s, trial):
    """Excerpts... ticks day by day: a firm left out of a day there (pin_orders) orders the other days only, and a
    day read later isn't spread to either."""
    counsel = key_of(trial[0], "Counsel")
    tick_firm(trial, counsel, True, s, shown=trial[0])
    for a in trial[1].case.attorneys:
        a.checked = False
    pin_orders(trial, [a for a in trial[0].case.attorneys])
    assert counsel in trial[1].not_ordered
    assert not spread_orders(trial, s) and not trial[1].ticked_keys()
    order = order_of(trial, counsel)
    assert order.kind == "some" and order.words() == "9/28/2026, 10/1/2026 and 10/2/2026"
    jobs = days_of(group(read_days(tmp_path, s, {"October 5, 2026": 25}, name="later"), s, trial))
    assert not jobs[-1].ticked_keys()
    tick_firm(jobs, counsel, True, s, shown=jobs[0])  # ticked again in Who ordered: the whole trial again
    assert all(j.ticked_keys() == [counsel] for j in jobs) and not any(j.not_ordered & {counsel} for j in jobs)


def test_a_day_kept_in_excerpts_says_who_it_leaves_out(s, trial):
    """A day kept in Excerpts... (excerpts.store): a firm of the trial ordering none of its pages doesn't order
    the day, so it isn't spread back to it; ordering its pages again, it does."""
    counsel, advocate = key_of(trial[0], "Counsel"), key_of(trial[0], "Advocate")
    tick_firm(trial, counsel, True, s, shown=trial[0])
    tick_firm(trial, advocate, True, s, shown=trial[0])
    day, firms = next(d for d in case_days(trial) if d.job is trial[1]), firms_of(trial)
    store(day, [Run(day, 1, day.pages, [counsel])], firms, s)
    assert trial[1].not_ordered == {advocate}
    assert not spread_orders(trial, s) and trial[1].ticked_keys() == [counsel]
    store(day, [Run(day, 1, day.pages, [counsel, advocate])], firms, s)
    assert not trial[1].not_ordered and order_of(trial, advocate).kind == "whole"


def test_part_of_a_day(s, trial):
    counsel = key_of(trial[0], "Counsel")
    tick_firm(trial, counsel, True, s, shown=trial[0])
    advocate = key_of(trial[0], "Advocate")
    order_firm(trial, advocate, True)
    trial[2].portions = [(15, [counsel]), (40, [counsel, advocate])]
    order = order_of(trial, advocate)
    assert order.kind == "some" and order.words().endswith("and part of 10/1/2026")
    assert order_of(trial[2:3], advocate).words() == "Part of the day"
    assert order_of(trial[3:4], advocate).words() == "The whole day"
    assert order_of(trial, counsel).pages == 140 and order_of(trial, advocate).pages == 125


def test_the_speed_shown_is_the_speed_billed(s, trial):
    """speed_shown says what Generate bills without asking (settle_split_speeds): two firms together commit to
    the agreement form's speed; a firm alone chooses from its invoice; a speed chosen is that speed."""
    counsel, advocate = key_of(trial[0], "Counsel"), key_of(trial[0], "Advocate")
    tick_firm(trial, counsel, True, s, shown=trial[0])
    assert speed_shown(trial, counsel, s) == ShownSpeed("", "choose")
    assert speed_shown(trial, advocate, s) == ShownSpeed("", "none")
    tick_firm(trial, advocate, True, s, shown=trial[0])
    form = default_speed(trial[0].case, s)
    assert speed_shown(trial, counsel, s) == speed_shown(trial, advocate, s) == ShownSpeed(form, "billed")
    settle_split_speeds(trial, s, outputs=["invoice"])
    assert all(j.speeds == {counsel: form, advocate: form} for j in trial)
    assert speed_shown(trial, counsel, s) == ShownSpeed(form, "set")
    set_firm_speed(trial, advocate, "Daily")
    assert speed_shown(trial, advocate, s) == ShownSpeed("Daily", "set")
    trial[1].set_speed(advocate, "Regular")
    assert speed_shown(trial, advocate, s) == ShownSpeed("", "several")


def test_the_trials_of_a_batch(tmp_path, s, trial):
    other = [j for j in group(read_days(tmp_path, s, {"October 7, 2026": 10}, name="other"), s)]
    other[0].case.set("case_name", "Pat Doe v. Sam Poe")
    other[0].case.set("index_no", "799999/2022")
    got = trials(trial + other)
    assert [len(t) for t in got] == [4, 1]


def test_the_records_keep_who_orders_some_days_only(s, trial):
    advocate = key_of(trial[0], "Advocate")
    order_firm(trial, advocate, False, shown=trial[2])
    origin = json.loads(json.dumps(job_origin(trial[0])))
    assert origin["job"]["not_ordered"] == [advocate]
    assert job_from_origin(origin, s).not_ordered == {advocate}
    assert "not_ordered" not in job_origin(trial[2])["job"]  # (none: the record is as it always was)


def test_a_firm_renamed_keeps_the_days_it_doesnt_order(s, trial):
    advocate = key_of(trial[0], "Advocate")
    order_firm(trial, advocate, False, shown=trial[2])
    trial[0].rename_in_portions(advocate, "advocate partners")
    assert trial[0].not_ordered == {"advocate partners"}
