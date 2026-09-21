# Importing an authority's data files

When MahaRERA (or another RERA) replies to the data request with files, this is how they get into Sahi Ghar. Nothing here fetches from a website: it reads files you put in a folder.

## Steps

1. Put every file from the reply in one folder (CSV or Excel `.xlsx`). Keep the originals unchanged.
2. Make sure the database is up and migrated (see the README), then run, from `backend/`:

       DATABASE_URL=<your database url> uv run python -m sahighar.cli import <folder> --obtained-on 2026-11-05

   `--obtained-on` is the date you **received** the files. Pages show it as "Data as of", so set it honestly. Without it, each file's own modified date is used.
3. Read the output. It says how many files loaded, names any file that failed with the reason and the line numbers, and says how many promoter groups were scored. Fix or re-request a failed file and run the same command again: importing is safe to repeat (unchanged files are skipped, changed files update their rows).

Exit code 0 means every file loaded; 1 means at least one failed (the rest still loaded); 2 means the folder path was wrong.

## What it recognises

Files are recognised by their **columns**, not their names, and column headings are matched by meaning (capitals, punctuation and common wordings do not matter). A file with none of the key columns is reported as "not recognised" and listed with the columns it has.

| Table | Recognised by | Required columns | Optional columns |
|---|---|---|---|
| **Projects** | a project registration number | registration number, project name, promoter id | promoter name, district, locality, registration valid up to, extended up to |
| **Promoters** | a promoter id (and no registration or complaint number) | promoter id, promoter name | registered office address, PAN, directors or partners |
| **Complaints** | a complaint number | complaint number, status, and either a promoter id or a project number | filing date, or year and month of filing, "applied for non-execution (Y/N)", order link |

Notes on the rules, so a surprising result is easy to explain:

- **Dates** must be day first: `31/12/2018`, `31-12-2018`, `31.12.2018` or `2018-12-31`. Excel date cells work. An ambiguous or unreadable date (`12/31/2018`, `31/12/18`, `soon`) **fails the file** with its line number instead of being guessed.
- **Extensions.** If a project has several rows (one per extension), the latest "extended up to" date is used. One row per project also works.
- **Directors or partners** in a single cell are split on `;`, `|` or a new line, never on a comma.
- **A complaints table without a promoter id** is fine (the public complaint table has none): each complaint takes the promoter of the project it names. A complaint with neither a known promoter nor a known project fails its file.
- **A projects-only reply** still imports: promoters are created from the project rows (id and name). A promoters table, when it arrives later, fills in address, PAN and directors without erasing anything.
- **Order of loading** is projects, then promoters, then complaints, whatever the file names.
- **A complaints table means "complaints were collected for everyone".** Once one is imported, a builder who is not in it is shown as having no complaints. Without one, complaints show as "not collected" and score nothing. So only import a complaints table that covers all builders in the data; do not import a partial extract.
- Later imports **add or change** values; they never blank one. A project whose extension was withdrawn would keep the old extension date until corrected by hand.
- **Complaint status** is stored exactly as written. It is only interpreted into a stage: "Order Approved" is *order issued*; "Hearing Scheduled" and "Roznama Approved" are *pending*; anything else is *other* and is not counted as pending or issued. The site's day of filing is never invented: only year and month are kept unless the file has a full date.
- **Excel** files: only the first sheet is read.

## If the reply uses different column headings

Add the new wording to `_ALIASES` in `backend/sahighar/adapters/tabular.py` (one line, next to its meaning) and run the import again. If the reply has a different **structure** (for example, extensions in a separate file, or a complaint's outcome in its own column), tell me what it looks like and I will extend the adapter and its tests. Keep a copy of the original reply files: they are stored in the raw store (`raw_store/` by default) and every number on a page links to the file it came from.

## What is not covered yet

- PDFs and scanned documents (a reply as PDFs would need a different extractor).
- More than one sheet per Excel file.
- Karnataka and Telangana: the same command works (`--state KA` or `--state TG`) if their replies use the same kinds of tables.
