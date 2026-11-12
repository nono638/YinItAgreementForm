# YinItAgreementForm: notes for work on the code

## Every page count says whose pages it counts

A transcript is often written by several court reporters, each page signed with its reporter's initials. Telling
apart **the total pages** (every reporter's pages of the transcript) and **your pages** (the user's own: what
their invoice bills) is what this program is for. So wherever the interface shows a page count (a column
heading, a label, a tooltip, a message, a summary line, the help), it says which count it is (the user,
2026-10-30):

- **Total pages**: every reporter's pages (`Job.transcript_pages`).
- **Your pages**: the user's own (`Job.your_pages`), and **your pages billed**: what the user's invoice bills
  (`Job.invoice_pages`, as Whose pages… says).
- **Pages typed**: a number typed into the Pages field (`Job.pages_typed`), the user's own count.

A bare "Pages", "pp." or "120 pages" for a count is a bug, even on a transcript one reporter wrote, where the two
counts are equal. Put both counts side by side when either could be misread: "43 of your pages billed (93 total
pages)". Page **numbers** (the numbers printed on the pages, "236–328") are not counts: label them as page
numbers, and show them as read from the PDFs, never worked out from a count.

What the court's own forms print (the agreement form's "Est. number of pages") keeps the form's wording.

An unnumbered Min-U-Script cover isn't a page: no count counts it, and nothing bills it (the user, 2026-11-06).

## Every setting makes one decision and has one home

Before adding, moving or renaming a setting, follow SETTINGS.md: write the one decision it makes, look for a setting
that already makes it (and extend that one instead), try a better default first, and place it by the page rules.
`minute_filler/settings_catalog.py` lists every setting's page, heading and decision; `tests/test_settings_catalog.py`
fails when a field has no entry, a control or a label is missing, or a "Settings → …" path names a page that no longer
exists. A message that points at one setting builds its path with `settings_catalog.path(key)`; a page named alone
("Settings → My info") may be written, and the test checks it is a page of today's.
