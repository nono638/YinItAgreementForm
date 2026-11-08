"""Run sheets the released version (2.16) wrote, the day generated again: the takes it left off are put back, and none
twice.

It left a take off where two of a day's takes start on one printed number: a day whose numbers start again on a take's
own first number, or two volumes of a day each numbered from 1 (Pat 1-20 in AM.pdf, DS 1-15 in PM.pdf). Generated again,
the take matched the row of the other one, which starts on the same page, so the box said the sheet "already has these
takes" and the sheet stayed short, with no word said. Each sheet of that version's here is laid out with openpyxl as it
laid one out (runsheet._fill_sheet, _meta), with the rows it wrote for these very PDFs (each shape run through it). All
names and numbers are made up."""
from datetime import date

import pymupdf
import pytest
from openpyxl import Workbook, load_workbook

from minute_filler.batch import group, read_docs
from minute_filler.runsheet import Row, RunSheetOpts, _number, _read_ours, add_takes, run_sheet_summary, takes_to_add
from minute_filler.takes import TITLE_ONLY

from helpers import CAPTION_DPM, pat_settings

DAY = date(2026, 6, 3)  # (CAPTION_DPM's day)
PR, DS, KP = "pr", "ds", "kp"
LINES = "\n".join(f"{n:2}  {'Q.  And then?' if n % 2 else 'A.  Yes.'}" for n in range(1, 26))
HEADINGS = ["Date", "Weekday", "Reporter", "Day's Take", "Running Take", "Pages written", "Starting Page No.",
            "Ending Page No.", "Witness Start", "Witness End", "Note"]


@pytest.fixture
def s(tmp_path):
    s = pat_settings(initials="P.R.")
    s.output_dir, s.records_dir = str(tmp_path / "out"), str(tmp_path / "records")
    s.runsheet_dir = str(tmp_path / "sheets")
    s.save_math = "off"
    s.use_ai = s.open_after = False
    return s


def pdf(path, numbers, who):
    """A transcript whose pages print these numbers, each signed as `who` says ("" unsigned)."""
    doc = pymupdf.open()
    for i, n in enumerate(numbers):
        page = doc.new_page()
        page.insert_text((300, 40), str(n), fontsize=10)
        page.insert_text((60, 80), CAPTION_DPM if i == 0 else LINES, fontsize=9)
        if who[i]:
            page.insert_text((520, page.rect.height - 40), who[i], fontsize=10)
    doc.save(path)
    doc.close()
    return path


def job_of(s, *paths):
    docs, errors = read_docs([str(p) for p in paths], s)
    assert not errors
    job, = group(docs, s)
    return job


def released_sheet(path, rows, case_name="Jane Roe v. Sam Poe"):
    """A run sheet as the released version laid it out: the case at the top, the headings on row 4, a take a row from
    row 5 (Date, Reporter and Pages written typed; Starting Page No. a number, or the End of the row the last page came
    from + 1 where it goes on from it; the rest its formulas), and the hidden sheet that says it is this app's. rows:
    (reporter, pages, start) of DAY; pages may be a formula, as typed by the user."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Run Sheet"
    ws["A1"] = case_name
    for c, heading in enumerate(HEADINGS, 1):
        ws.cell(4, c, heading)
    prev_end = prev_row = None
    for i, (who, pages, start) in enumerate(rows):
        r = 5 + i
        count = _number(pages)  # (a sum typed in: "=38+1")
        ws.cell(r, 1, DAY).number_format = "m/d/yyyy"
        ws.cell(r, 2, f'=IF(A{r}="","",TEXT(A{r},"dddd"))')
        ws.cell(r, 3, who)
        ws.cell(r, 4, f'=IF(A{r}="","",IF(K{r}="{TITLE_ONLY}",0.5,COUNTIFS(A$5:A{r},A{r},K$5:K{r},"<>{TITLE_ONLY}")))')
        ws.cell(r, 5, f'=IF(A{r}="","",N(E{r - 1})+IF(A{r}=A{r - 1},D{r}-N(D{r - 1}),D{r}))')
        ws.cell(r, 6, pages)
        ws.cell(r, 7, f"=H{prev_row}+1" if prev_end is not None and start == prev_end + 1 else start)
        ws.cell(r, 8, f'=IF(OR(F{r}="",G{r}=""),"",G{r}+F{r}-1)')
        prev_end, prev_row = start + count - 1, r
    meta = wb.create_sheet("YinIt")
    for row in (["format", "YinIt run sheet 2"], ["case", case_name], ["index", ""], ["updated", "2026-10-30T09:00:00"]):
        meta.append(row)
    meta.sheet_state = "hidden"
    wb.save(path)
    return path


def again(job, s, path) -> RunSheetOpts:
    """The day generated again onto the run sheet at path."""
    opts = RunSheetOpts(job.runsheet_opts(s).rows, str(path))
    add_takes(job.case, opts, s, [])
    return opts


def sheet_of(path) -> list:
    return [(r.reporter, r.pages, r.start) for r in _read_ours(load_workbook(path)["Run Sheet"])]


def total(path) -> int:
    return sum(p for _, p, _ in sheet_of(path))


# ------------------------------------------------------------------ a day whose numbers start again
ONE_TRANSCRIPT = {
    # its numbers start again on Pat's first: the released sheet has Pat's take only
    "starts again": ((list(range(1, 40)) + list(range(1, 21)), [PR] * 39 + [DS] * 20),
                     [("Pat", 39, 1)], [("DS", 20, 1)]),
    # Pat's last take falls among Pat's first: the same reporter, the same row
    "falls into its own": ((list(range(1, 51)) + list(range(10, 30)), [PR] * 39 + [DS] * 11 + [PR] * 20),
                           [("Pat", 39, 1), ("DS", 11, 40)], [("Pat", 20, 10)]),
    # Pat's take written twice: the second is a take of its own
    "the same take twice": ((list(range(1, 21)) + list(range(1, 11)), [PR] * 10 + [DS] * 10 + [PR] * 10),
                            [("Pat", 10, 1), ("DS", 10, 11)], [("Pat", 10, 1)]),
    # Pat's last take starts on Dana's first number
    "on another's first": ((list(range(1, 41)) + list(range(21, 31)), [PR] * 20 + [DS] * 20 + [PR] * 10),
                           [("Pat", 20, 1), ("DS", 20, 21)], [("Pat", 10, 21)]),
}


@pytest.mark.parametrize("shape", ONE_TRANSCRIPT)
def test_a_day_whose_numbers_start_again_gets_the_take_left_off(tmp_path, s, shape):
    (numbers, who), old, lost = ONE_TRANSCRIPT[shape]
    job = job_of(s, pdf(tmp_path / "Roe.pdf", numbers, who))
    path = released_sheet(tmp_path / "sheet.xlsx", old)
    opts = again(job, s, path)
    assert (opts.added, opts.skipped) == (len(lost), len(old))
    assert run_sheet_summary(opts).startswith(f"Added {len(lost)} take to the run sheet")
    assert sorted(sheet_of(path)) == sorted(old + lost) and total(path) == len(numbers)
    assert again(job, s, path).added == 0  # (nothing twice)


# ------------------------------------------------------------------ two volumes each numbered from 1
VOLUMES = {
    "two reporters": ([("AM.pdf", range(1, 21), [PR] * 20), ("PM.pdf", range(1, 16), [DS] * 15)],
                      [("Pat", 20, 1)], [("DS", 15, 1)]),
    "as many pages": ([("AM.pdf", range(1, 21), [PR] * 20), ("PM.pdf", range(1, 21), [DS] * 20)],
                      [("Pat", 20, 1)], [("DS", 20, 1)]),
    "three": ([("AM.pdf", range(1, 21), [PR] * 20), ("EVE.pdf", range(1, 11), [KP] * 10),
               ("PM.pdf", range(1, 16), [DS] * 15)],
              [("Pat", 20, 1)], [("DS", 15, 1), ("KP", 10, 1)]),
    # the second starts again among the first's numbers, on a take's first number
    "falling": ([("AM.pdf", range(1, 41), [PR] * 20 + [DS] * 20), ("PM.pdf", range(10, 31), [DS] * 11 + [PR] * 10)],
                [("Pat", 20, 1), ("DS", 20, 21)], [("DS", 11, 10), ("Pat", 10, 21)]),
}


@pytest.mark.parametrize("shape", VOLUMES)
def test_two_volumes_each_numbered_from_1_get_the_take_left_off(tmp_path, s, shape):
    files, old, lost = VOLUMES[shape]
    job = job_of(s, *(pdf(tmp_path / name, list(numbers), who) for name, numbers, who in files))
    path = released_sheet(tmp_path / "sheet.xlsx", old)
    opts = again(job, s, path)
    assert (opts.added, opts.skipped) == (len(lost), len(old))
    assert sorted(sheet_of(path)) == sorted(old + lost)
    assert total(path) == sum(len(numbers) for _, numbers, _ in files)
    assert again(job, s, path).added == 0


def test_a_draft_or_a_part_sent_ahead_still_stands_for_its_take(tmp_path, s):
    """Pat's AM.pdf with an unsigned draft of it, and the first 12 pages of it sent ahead: the released sheet has Pat's
    take once. Dana's PM.pdf, signed by another reporter, is put back; the draft and the part, which may be copies of
    Pat's pages, aren't added as takes of their own."""
    job = job_of(s, pdf(tmp_path / "AM.pdf", list(range(1, 21)), [PR] * 20),
                 pdf(tmp_path / "Draft AM.pdf", list(range(1, 21)), [""] * 20),
                 pdf(tmp_path / "Part AM.pdf", list(range(1, 13)), [PR] * 12),
                 pdf(tmp_path / "PM.pdf", list(range(1, 16)), [DS] * 15))
    path = released_sheet(tmp_path / "sheet.xlsx", [("Pat", 20, 1)])
    opts = again(job, s, path)
    assert (opts.added, opts.skipped) == (1, 3)
    assert sorted(sheet_of(path)) == [("DS", 15, 1), ("Pat", 20, 1)]
    assert again(job, s, path).added == 0


def test_a_row_the_user_changed_still_counts_as_its_take(tmp_path, s):
    """A sum typed into Pages, "Dana" typed over "DS", and a Start the released version wrote as a formula: Pat's lost
    take is put back, and neither of the two there is added again."""
    job = job_of(s, pdf(tmp_path / "Roe.pdf", list(range(1, 51)) + list(range(10, 30)), [PR] * 39 + [DS] * 11 + [PR] * 20))
    path = released_sheet(tmp_path / "sheet.xlsx", [("Pat", "=38+1", 1), ("Dana", 11, 40)])
    assert load_workbook(path)["Run Sheet"]["G6"].value == "=H5+1"
    opts = again(job, s, path)
    assert (opts.added, opts.skipped) == (1, 2)
    assert sorted(sheet_of(path)) == [("Dana", 11, 40), ("Pat", 20, 10), ("Pat", 39, 1)]
    assert load_workbook(path)["Run Sheet"]["F5"].value == "=38+1"  # (as typed)
    assert again(job, s, path).added == 0


def test_their_own_run_sheet_gets_the_take_left_off_too(tmp_path, s):
    """A sheet this app didn't make, with the AM volume's take typed in."""
    wb = Workbook()
    ws = wb.active
    ws.append(HEADINGS[:8])
    ws.append([DAY, "Wednesday", "Pat", 1, 1, 20, 1, 20])
    path = tmp_path / "theirs.xlsx"
    wb.save(path)
    job = job_of(s, pdf(tmp_path / "AM.pdf", list(range(1, 21)), [PR] * 20),
                 pdf(tmp_path / "PM.pdf", list(range(1, 16)), [DS] * 15))
    opts = again(job, s, path)
    assert (opts.added, opts.skipped) == (1, 1)
    ws = load_workbook(path).active
    assert [ws.cell(r, 3).value for r in range(2, ws.max_row + 1)] == ["Pat", "DS"]
    assert sum(ws.cell(r, 6).value for r in range(2, ws.max_row + 1)) == 35


# ------------------------------------------------------------------ the rule
def take(who, pages, start, doc, initials, at=0, **kw):
    return Row(DAY, who, pages, start, initials=initials, doc=doc, at=at, numbers=list(range(start, start + pages)), **kw)


PUT_BACK = [
    # a row there exactly another take of this run's transcript: not this one's (it has no page to spare)
    ([take("Pat", 39, 1, "a", PR), take("Pat", 20, 10, "a", PR, at=50)], [Row(DAY, "Pat", 39, 1)], [("Pat", 20, 10)]),
    # of another transcript, signed by another reporter
    ([take("Pat", 20, 1, "a", PR), take("DS", 15, 1, "b", DS)], [Row(DAY, "Pat", 20, 1)], [("DS", 15, 1)]),
    # that take there under its initials ("PR", Pat's here)
    ([take("Pat", 20, 1, "a", PR), take("Dana", 15, 1, "b", DS)], [Row(DAY, "PR", 20, 1)], [("Dana", 15, 1)]),
    # the same take written twice in one transcript, once there: the other one
    ([take("Pat", 10, 1, "a", PR), take("Pat", 10, 1, "a", PR, at=20)], [Row(DAY, "Pat", 10, 1)], [("Pat", 10, 1)]),
]
AS_IT_WAS = [
    # a take of each there: nothing
    ([take("Pat", 20, 1, "a", PR), take("DS", 15, 1, "b", DS)], [Row(DAY, "Pat", 20, 1), Row(DAY, "DS", 15, 1)], []),
    # the same take written twice in one transcript, twice there: nothing
    ([take("Pat", 10, 1, "a", PR), take("Pat", 10, 1, "a", PR, at=20)],
     [Row(DAY, "Pat", 10, 1), Row(DAY, "Pat", 10, 1)], []),
    # one reporter's two transcripts, or one unsigned: maybe a copy, the row is either's
    ([take("Pat", 20, 1, "a", PR), take("Pat", 15, 1, "b", PR)], [Row(DAY, "Pat", 20, 1)], []),
    ([take("Pat", 20, 1, "a", PR), take("", 20, 1, "b", "")], [Row(DAY, "Pat", 20, 1)], []),
    ([take("", 20, 1, "a", ""), take("DS", 15, 1, "b", DS)], [Row(DAY, "", 20, 1)], []),
    # a take corrected since, or one row there that isn't exactly any (its label typed over): as it was
    ([take("Pat", 20, 1, "a", PR), take("DS", 15, 1, "b", DS, corrected=True)], [Row(DAY, "Pat", 20, 1)], []),
    ([take("Pat", 20, 1, "a", PR), take("DS", 15, 1, "b", DS)], [Row(DAY, "Patricia", 20, 1)], []),
    ([take("Pat", 20, 1, "a", PR), take("DS", 15, 1, "b", DS)], [Row(DAY, "Pat", 21, 1)], []),
    # another day's row
    ([take("Pat", 20, 1, "a", PR), take("DS", 15, 1, "b", DS)], [Row(date(2026, 6, 4), "Pat", 20, 1)],
     [("Pat", 20, 1), ("DS", 15, 1)]),
]


def test_which_takes_a_row_there_can_be():
    """Which takes are put back, and which a row there still stands for."""
    for rows, old, added in PUT_BACK + AS_IT_WAS:
        got = [(r.reporter, r.pages, r.start) for r in takes_to_add(rows, old)]
        assert got == added, ([(r.reporter, r.pages, r.start, r.doc) for r in rows], old)
