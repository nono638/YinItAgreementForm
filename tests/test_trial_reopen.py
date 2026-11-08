"""A trial billed on one invoice and opened again from its record (Records -> Open this job again) bills as it did:
each day comes back with its own choices of the invoice (Parties, the Peripherals, Whose pages...) and the fields
typed in on it (the Pages number among them), as a day's own record gives them back (batch.trial_orders,
batch.put_back_orders). They were lost once, and the days billed by what their documents and Settings said instead,
with no word: $200 each became $245 (Parties 3), $147 became $245 for the whole transcript, another reporter's
invoices went. Real invoices into a ledger of the test's own, the real window. All names and numbers are made up."""
import json

import pytest

from minute_filler.batch import fill_jobs, group, joint_origin, put_back_orders, read_docs
from minute_filler.deliver import ledger_for
from minute_filler.models import SRC_USER, Attorney

from helpers import CAPTION_DPM, page_numbered_transcript, pat_settings

DANA = dict(name="Dana Smith", firm="Smith Law", party="Plaintiff")
ALEX = dict(name="Alex B. Counsel", firm="Counsel & Counsel", party="Defendant")
A, D = Attorney(**ALEX).key(), Attorney(**DANA).key()


@pytest.fixture
def s(tmp_path):
    s = pat_settings()
    s.output_dir, s.records_dir = str(tmp_path / "out"), str(tmp_path / "records")
    s.invoice_speeds = ["Regular", "Expedite"]
    s.save_math = "off"
    s.use_ai = s.open_after = False
    return s


def wait(win, until, seconds=30):
    import time

    from PySide6.QtWidgets import QApplication
    end = time.time() + seconds
    while time.time() < end:
        QApplication.processEvents()
        if not win.runner._live and win.work == 0 and until():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


@pytest.fixture
def window(monkeypatch, make_window, qt, s):
    monkeypatch.setattr(qt.QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(qt.QMessageBox, "question", lambda *a, **k: qt.QMessageBox.Yes)
    s.outputs = ["invoice"]
    return make_window(s)


def trial(tmp_path, s, initials=None):
    """Jane Roe's trial: June 3 (30 total pages, printed 100-129) and June 4 (20, printed 200-219), both ordered by
    Smith Law and Counsel & Counsel at Expedite."""
    tmp_path.joinpath("in").mkdir()
    a = page_numbered_transcript(tmp_path / "in" / "Day1.pdf", 30, first=100, initials=initials)
    b = page_numbered_transcript(tmp_path / "in" / "Day2.pdf", 20, first=200,
                                 caption=CAPTION_DPM.replace("June 3, 2026", "June 4, 2026"))
    docs, errors = read_docs([str(a), str(b)], s)
    assert not errors
    jobs = sorted(group(docs, s), key=lambda j: j.case.get("dates"))
    assert [j.case.get("dates") for j in jobs] == ["6/3/2026", "6/4/2026"]
    for j in jobs:
        j.case.attorneys = [Attorney(**ALEX, checked=True), Attorney(**DANA, checked=True)]
        j.case.set("delivery", "Expedite")
        j.att_touched = True
    return jobs


def bill(jobs, s, led):
    """The invoices fill_jobs makes of these days: (who, pages, amounts) each, and their numbers."""
    before = {i.invoice_no for i in led.invoices()}
    fill_jobs(jobs, s, outputs=["invoice"], ledger=led)
    assert not [j.error for j in jobs if j.error]
    made = [i for i in led.invoices() if i.invoice_no not in before]
    return sorted((i.bill_to, i.pages, {k: str(v) for k, v in i.amounts.items()}) for i in made), made


def whole_transcript(jobs):
    jobs[0].page_basis = {jobs[0].docs[0].key(): "*"}


def both_reporters(jobs):
    jobs[0].page_basis = {jobs[0].docs[0].key(): ["me", "ds"]}


def parties_3(jobs):
    for j in jobs:
        j.parties = 3


def no_emailed_copy(jobs):
    for j in jobs:
        j.invoice_email = False


def pages_typed_40(jobs):
    jobs[0].case.set("est_pages", "40")


def index_on(jobs):
    jobs[0].invoice_index = "on"


@pytest.mark.parametrize("choose", [whole_transcript, both_reporters, parties_3, no_emailed_copy, pages_typed_40,
                                    index_on])
def test_a_trial_opened_again_bills_as_it_did(window, tmp_path, s, choose):
    s.profile.initials = "P.R."  # (June 3: Pat's first 10 pages, then Dee Sanders's 20)
    jobs = trial(tmp_path, s, ["pr"] * 10 + ["ds"] * 20)
    choose(jobs)
    led = ledger_for(s)
    first, made = bill(jobs, s, led)
    assert window.open_past_job(led.origin_of(made[0].invoice_no)) is True
    wait(window, lambda: len([j for j in window.jobs if j.docs]) == 2)
    again, _ = bill(list(window.jobs), s, led)
    assert again == first


def test_the_days_come_back_with_what_was_chosen_and_typed_on_each(tmp_path, s):
    jobs = trial(tmp_path, s)
    day1, day2 = jobs
    day1.parties, day1.invoice_email, day1.invoice_detail = 3, False, True
    day1.invoice_show = ["per_page"]
    day1.page_basis = {day1.docs[0].key(): "*"}
    day1.case.set("est_pages", "40")
    day1.case.set("judge", "")  # (emptied: the documents' judge must not come back)
    day2.invoice_index, day2.index_on_typed = "on", True
    day2.case.set("rate", "6.00")
    origin = json.loads(json.dumps(joint_origin(jobs, split_rule="")))
    again = sorted(group([d for j in jobs for d in j.docs], s), key=lambda j: j.case.get("dates"))
    assert again[0].parties == 0 and again[0].case.fields["est_pages"].source != SRC_USER  # (the documents')
    put_back_orders(again, origin, s)
    one, two = again
    assert (one.parties, one.invoice_email, one.invoice_detail, one.invoice_show) == (3, False, True, ["per_page"])
    assert one.page_basis == {one.docs[0].key(): "*"} and one.invoice_index is None
    assert one.case.get("est_pages") == "40" and one.pages_typed() and one.invoice_pages() == 40
    assert one.case.get("judge") == "" and one.case.fields["judge"].source == SRC_USER
    assert (two.invoice_index, two.index_on_typed, two.parties) == ("on", True, 0)
    assert two.case.get("rate") == "6.00" and two.case.fields["rate"].source == SRC_USER
    assert one.case.get("copies") == "3"  # (No. of copies follows Parties)


def test_what_follows_from_a_field_typed_is_worked_out_again(tmp_path, s):
    """Regular chosen on June 4 (the documents', and Settings', speed is Expedite): its rate is Regular's again."""
    jobs = trial(tmp_path, s)
    jobs[1].case.set("delivery", "Regular")
    origin = json.loads(json.dumps(joint_origin(jobs, split_rule="")))
    again = sorted(group([d for j in jobs for d in j.docs], s), key=lambda j: j.case.get("dates"))
    assert again[1].case.get("rate") == s.rate_for("Expedite") != s.rate_for("Regular")
    put_back_orders(again, origin, s)
    assert again[1].case.get("delivery") == "Regular" and again[1].case.get("rate") == s.rate_for("Regular")


def test_rows_counted_in_a_pages_number_typed_stay_with_it(tmp_path, s):
    """40 typed on a day of 30 total pages, Smith Law ordering its last 20: the rows end on the number typed, which is
    no count of the pages read. Taken for the record's count, it was cleared as settled, and the rows then passed
    the day's 30 pages: the invoice held."""
    jobs = trial(tmp_path, s)
    jobs[0].case.set("est_pages", "40")
    jobs[0].portions = [(20, [A]), (40, [A, D])]
    origin = json.loads(json.dumps(joint_origin(jobs, split_rule="")))
    again = sorted(group([d for j in jobs for d in j.docs], s), key=lambda j: j.case.get("dates"))
    put_back_orders(again, origin, s)
    day = again[0]
    assert day.case.get("est_pages") == "40" and day.pages_typed()
    assert day.portions == [(20, [A]), (40, [A, D])] and not day.portions_problem() and not day.invoice_hold()


def test_a_day_s_whose_pages_follow_its_folder_renamed(tmp_path, s):
    """Kept by the document's path, as a job's own record keeps them: a case's folder renamed for another day of the
    trial (Ledger.move_folder) moves them with the document, or opened again, the day would bill otherwise."""
    from minute_filler.records import moved_origin
    jobs = trial(tmp_path, s)
    key = jobs[0].docs[0].key()
    jobs[0].page_basis, jobs[0].front_owner = {key: "*"}, {key: "ds"}
    origin = json.loads(json.dumps(joint_origin(jobs, split_rule="")))
    new = tmp_path / "Roe 6-3-2026 6-4-2026"
    assert moved_origin(origin, tmp_path / "in", new) is True
    day = origin["orders"][0]
    assert day["page_basis"] == {str(new / "Day1.pdf"): "*"} and day["front_owner"] == {str(new / "Day1.pdf"): "ds"}
    assert origin["sources"] == [str(new / "Day1.pdf"), str(new / "Day2.pdf")]


def test_an_older_record_s_days_come_back_as_their_documents_say(tmp_path, s):
    """A record made before the days kept their choices has none of them: nothing is put back, nothing fails."""
    jobs = trial(tmp_path, s)
    jobs[0].parties = 3
    jobs[0].case.set("est_pages", "40")
    origin = json.loads(json.dumps(joint_origin(jobs, split_rule="")))
    for row in origin["orders"]:
        for k in ("parties", "invoice_email", "invoice_index", "index_on_typed", "invoice_show", "invoice_detail",
                  "page_basis", "front_owner", "typed"):
            row.pop(k, None)
    again = sorted(group([d for j in jobs for d in j.docs], s), key=lambda j: j.case.get("dates"))
    assert put_back_orders(again, origin, s) == again
    assert again[0].parties == 0 and again[0].invoice_pages() == 30 and not again[0].pages_typed()
