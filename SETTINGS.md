# Settings: one decision, one home

Every setting makes **one decision**, has **one home**, and is named the same wherever it shows. This file says
where a setting belongs and what to check before one is added or moved. The list itself is code:
`minute_filler/settings_catalog.py` has the Settings window's pages and an entry for every field of `Settings`.
`tests/test_settings_catalog.py` holds the code to it.

## Where a choice belongs

| The choice is… | It goes… | Why |
|---|---|---|
| A standing practice or preference, set once and rarely changed, true of every job ("bill the judge's index", "dark theme") | **Settings** | Settings is for configuration that "doesn't require frequent readjustment" (Microsoft); "general, infrequently changed settings" (Apple). |
| About the job on screen ("this firm ordered pages 1–40") | **The main window** (a card, or a dialog of the job's: Peripherals…, Whose pages…) | "Commands that are part of the typical app workflow shouldn't be in a settings page" (Microsoft). |
| A way of looking at a view: show, hide, filter, sort, fold, columns | **Where it acts** (the card, the window), never Settings | "Prefer letting people modify task-specific options without going to your settings area… showing or hiding parts of the current view… filtering a list" (Apple). |
| A standing default that a job sometimes needs otherwise | **The default in Settings, the override on the job**, with "Same as Settings" to go back | Invoicing programs keep workspace defaults that each invoice can override (Ruddr, Harpoon, Productive, Dubsado). |
| A setting used often enough to want at hand | **Settings, plus a shortcut in the main window** that writes the same value, worded so it is plainly the same setting (it may be shorter) | Property inspector and property sheet "aren't exclusive": the most-used properties in the window, the full set in the sheet (Microsoft, Windows 7 guidelines). |

**Before any of these: does it need to be a setting at all?** Each preference has a cost. Ask what the user is
trying to fix, and whether a better default, or fixing the behaviour, makes the choice unnecessary for everyone.
"Demand that each preference have some real value" (Havoc Pennington, *Free software and good user interfaces*).

## The pages

The window lists its pages on the left, each with a line saying what is on it, and a **Find a setting** box above
them. A page has a card per heading. A page's settings serve one purpose (Microsoft: "Make pages coherent by
relating all properties on each page to a single, specific, task-based purpose"), and the window goes no deeper
than page → heading (NN/g: more than two levels of disclosure loses people).

| Page | A setting belongs here if it… | Headings |
|---|---|---|
| My info | is about you, as forms and invoices give your details | Contact · Initials · Signature |
| Other reporters | is about another reporter: their name on run sheets, the invoices for their pages | Reporters |
| Reading documents | changes how documents are read, or what fills in when they don't say | When a document doesn't say · Names · Index numbers · Firms you answered |
| AI helper | is about the local AI model (Ollama) that helps read documents | AI helper · The model |
| Trials | decides how the days of one case are ticked, billed or made together | Who ordered · Invoices and forms · Batches |
| Dates | decides a date on a form or an invoice, or how turnaround days are counted | Filling in · Turnaround · Business days · Court holidays |
| Rates and speeds | decides a price, a rate sheet or a speed | Rate sheets · Speeds · Same pages, different speeds |
| Outputs | decides which outputs are made, or how a minute agreement or a MOFR is filled in | Make by default · Minute agreement · MOFR |
| Invoices | decides what an invoice charges or shows, its number, or its math | Charges · Index · What the invoice shows · Invoice text · Numbers · The math |
| Run sheets | decides how a run sheet is filled in | Run sheets |
| Records | decides how the Records window tracks, finds or sums up your invoices | Tick boxes and colours · Search · Recaps · CSV copies |
| Files and folders | decides where a file is saved, what it is called, or what happens as it is saved | Folders · File names · Saving |
| Program | is about the program itself: how it looks, how it starts, its updates | Look · Start card · New versions |

Pages are grouped (you; the job; what Generate makes; the program), with a line between groups, in the order
they're used. Windows 7's guidelines say: groups ordered by how likely they are to be used, the pages within a
group by how they relate.

**Room to grow.** A setting goes on the page whose rule fits it. If none fits, add a page (in the group it
belongs to); never put a setting on the nearest page. For example:
- a new place files are saved or read from: Files and folders → Folders;
- a new kind of form: a heading under Outputs;
- an output with many settings of its own: a page after Outputs, as Invoices and Run sheets are;
- something that changes how documents are read: a heading on Reading documents.

## Before adding or moving a setting

1. **Write its decision in one sentence** (the entry's `decides`): "Whether the judge's index is billed to the
   firms." If you can't, it is two settings, or none.
2. **Look for that decision already made.** Search the catalog (`settings_catalog.search`, or Find a setting in
   the window) for its words. If an existing setting decides it, or nearly, extend that one: another choice in
   its dropdown (a dropdown leaves room for a third way where a tick box doesn't). Two settings must never decide
   the same thing.
3. **Try a better default first.** If the request is "let me turn off X", ask whether X is wrong for everyone.
4. **Say what it depends on** (`needs`). A setting that only matters when another is on goes on the same page, and
   the window greys it out while that one is off; it isn't hidden. One that still counts when the other is off
   (a job's own choice can bring it back into play: the index's rows) needs nothing. Settings on different pages
   never depend on each other (Microsoft: "Don't make the settings on a page dependent upon settings on other
   pages").
5. **Say which value wins** when there are several: the job's own choice (`job_field`), then Settings, then the
   courthouse's default.
6. **Choose its home** with the table at the top, then its page with the rules above.
7. **Add it everywhere it must be:**
   - the field in `Settings` (a new field with a default needs no migration; a renamed one does: `from_dict`);
   - its catalog entry, with its label exactly as the window shows it;
   - its control on the page (`_row` / `_check` in `gui/settings_dialog.py`);
   - `also_in`, for every other place that sets it (the test reads the windows' code for `self.s.<setting> =` and
     `_set_opt("<setting>")`; a write through another name, `p = self.s.profile`, it can't see: declare it all
     the same);
   - a line in the page's help topic (the help test checks every label is named in the help);
   - a test of what it does.
8. **Point at a setting with `settings_catalog.path(key)`** in a message or tooltip: it gives "Settings → Invoices
   → Rounding" and follows the setting when it moves. A page named alone ("Settings → My info") may be written.
   The catalog test checks every "Settings → …" written in the code, the help and the README names a page of
   today's, and that what follows it is a heading or a setting of that page.

## What the tests check (tests/test_settings_catalog.py)

- Every field of `Settings` and `Profile` has exactly one entry.
- Each entry is whole: a page, a heading, a label, a decision; what it needs is on its page; its job field is a
  `Job` attribute.
- The window has a control for every setting it shows, on its page, with its label shown there word for word, and
  keeps none it doesn't.
- Every `needs` greys its setting out while the other is off, and back.
- Saving the window untouched gives back every setting exactly, with the settings changed from their defaults
  (but for a few the test can't set offscreen, which it lists).
- The window opens at the page last shown.
- Find a setting finds what it should.
- No window outside Settings writes `self.s.<setting>` (or through `_set_opt`) for a setting it doesn't declare.
- Every "Settings → …" path in the code, the help and the README is a page and a heading or setting of today's.
