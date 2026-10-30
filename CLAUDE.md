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
