# Changelog

All notable changes to this project will be documented in this file.

---

### Unreleased (0.1.0)

- **`cdsint update` installs the newest release, and every command says when
  there is one.** Only for an install `irm/setup.ps1` downloaded; a clone
  updates with `git pull` and never checks. The check asks GitHub at most once
  a day, prints one line on stderr, and says nothing under `--json` or when
  GitHub cannot be reached. The update refuses while any CODESYS-family IDE is
  running, unpacks the new tree beside the old one and swaps it in by two
  renames, so a failed download leaves the old one as it was (SPEC D17).
- **`irm/setup.ps1` installs the newest release, not `main`.** `-Version
  main` still gets the branch. The body moves to `%LOCALAPPDATA%\cdsint\body`:
  the old layout put it straight into `%LOCALAPPDATA%\cdsint`, and replacing
  it deleted the registrations of the IDEs that were listening along with it.
  Run from a 0.0.1 install, the script removes what the old layout left there;
  run `pip install -e` on the new path afterwards, as it says.
- **A pushed `v*` tag publishes a GitHub release**, after the tests pass, with
  that version's section of this file as its notes. The job refuses a tag that
  is not `SCRIPT_VERSION` and a section still headed "Unreleased".

- **`cdsint plc trace` records named variables from a controller, with
  nobody at the IDE.** A job file names the task, the variables and how
  long; the command logs in without downloading, records, saves `.trace`
  and `.csv`, and judges from the timestamps whether any cycle is missing.
  A `trigger` (numeric variable, edge, level, samples after) or a
  `record_condition` (one BOOL variable) are optional. The trace object
  lives only in memory as `cdsint_trace` and the project is never saved.
  It needs the word `trace` in the settings file's `plc` list, and
  `--gateway`, because a controller found by name can be the wrong one.
  What it refuses, and why, is in SPEC 6.8; the measurements behind it are
  in `docs/trace-research.md`.
- **A login that changes nothing can still download, and `plc trace`
  checks for that first.** Measured on the bench: a login with
  `OnlineChangeOption.Keep` downloads the whole application, without
  asking, when the IDE's `.compileinfo` and `.bootinfo_guids` are missing
  beside the project, even while cdsint's own record says `MATCH`. The
  command now compares the code and data identities in `.bootinfo_guids`
  with the ones in the controller's `Application.app` before it logs in.
- **The controller holds the whole recording.** The IDE stops fetching
  samples while its main thread is held up, measured at 13 s on a busy
  machine, so the ring on the controller is sized for the whole recording.
  The controller allocates it at once and does not refuse one it cannot
  hold (a soft PLC was killed by the operating system), so the estimate is
  held to a new setting, `trace_memory_mb` (default 256).
- **`system.delay()` has a second registered place on the IDE side**,
  `cds/ide/hold.py`, for the recording's wait, and only under `--noUI`
  (SPEC D5).

- **An edited native-XML object imports headless.** A trace, a
  visualisation, a text list, a task configuration: any object stored as
  native XML that already existed in the project failed to import in the
  `--project` form, because the IDE asked which objects to overwrite
  (`PromptImportConflict`), and that multiple-choice prompt cannot be
  answered by `--answer`. The failure was named, never silent, but it was
  every time. Every native import now passes a handler that answers
  "replace", which is what `import -y` asked for. Checked on CODESYS
  3.5.21.40 and DIADesigner-AX 1.10 by editing a trace object's XML,
  importing it and exporting it back; the sample project's export listing
  and `discover` counts are unchanged.

### 0.0.1 (2026-09-22) — moved into cdsint

**The tool became a product with its own repo.** The code came out of
`kevin-cds-text-sync` (branch `fix/member-creation-parent-resolution`, commit
`9aa9886`) and moved here unchanged in behaviour; that repo keeps the history
up to that commit. Version numbering restarts at `0.0.1` — the `k1.x` line was
a fork of upstream `cds-text-sync` and does not carry over. Nothing compares
that number against a project any more — the version stamp went with the move
to a settings file, below — so the renumbering costs nobody a prompt.

- **No engine file does more than one job any more.** The three modules that
  came across at over a thousand lines each — the managers, the "utils", the
  compare engine — are twenty one-job modules now (`object_kind`,
  `object_paths`, `managers_*`, `st_text`, `ide_attrs`, `change_detect`,
  `object_create`, `device_remap` and so on), and the two oversized tools
  are split the same way. Every statement moved verbatim: on two real IDEs
  (CODESYS 3.5.21.40, DIADesigner-AX 1.10) the export listing's SHA-256s,
  `discover`'s counts and a full `verify` came out identical before and
  after each step. PRINCIPLES 2's exemption for moved files is gone with
  them: `tests/test_size_limits.py` fails on any file over 400 lines, refuses
  a module named `utils`, `helpers`, `common` or `misc`, and keeps the
  functions still over 60 lines as a debt table that may only shrink.
- **Every text file is opened with `io.open`, newline untouched.**
  `codecs.open` is deprecated on CPython 3.12+ and the test run printed the
  warning 157 times. Each call passes `newline=""` both ways, because
  `codecs.open` never translated newlines and `io.open` would — on Windows
  that would turn every `\n` written into `\r\n` and change the bytes of every
  `.st`. Verified by the same two-IDE listing comparison.
- **A `--project` run refuses before it starts an IDE when the install is not
  a clone.** `pip install .` without `-e`, or from a git URL, ships the
  packages and nothing else; the IDE side then died inside the IDE on the
  missing type profile, which read as an IDE bug. Exit 4, with the fix
  spelled out.
- **The performance probe's compare mode works again.** With the compare
  engine split, `entry_export` no longer pulled in the import-side modules
  the probe table names, so a compare run refused on a table that was right.
  Both entry bodies are imported before the probes go in, whatever the mode.
- **The repo is in English, and carries nothing that belongs to one machine.**
  The spec, the watcher doc and the Claude instructions are translated with
  their section numbers unchanged; the construction tickets, the duplicate
  agent-workflow doc, the machine-specific worker rules, the code of conduct
  template and the old repo's version history are gone; the tests no longer
  use a customer's name as their non-ASCII fixture; the README has its
  conventional name and the maintainer's instruments are in `tools/README.md`.

- **The engine's parallel paths came down to one each.** Export and compare
  had carried the same thirty lines twice, with a comment in one copy asking
  whoever edited it to remember the other. Every `.st` and `.xml` file this
  writes is byte for byte what it wrote before: two real IDEs, two real
  projects, 229 objects each, and the SHA-256 of the whole listing unchanged
  at every step.

  - **Classifying an object.** One `resolve_object()` answers "what kind is
    this, where does its file go, and is it written at all" for both
    directions (`engine/classify.py`). When the two disagreed, compare saw
    "no disk file" for something export never writes, called it an orphan,
    and the next import deleted it.
  - **Picking a manager.** One rule, not two. Export asked for a dedicated
    manager first; import saw a `.xml` suffix and went straight to native, so
    a device was handled by one manager on the way out and another on the way
    back. That cost nothing only because of which methods ConfigManager
    happened not to override.
  - **Walking the sync folder.** One walk and one set of skip rules
    (`engine/sync_dir.py`). The orphan sweep did not skip `__pycache__` and
    never consulted RESERVED_FILES, so it could offer to delete a file the
    new-file scan refuses to see.
  - **Reading an IDE object.** One `name_of`, `kind_of`, `parent_of`,
    `children_of`, `guid_of`, `child_named` (`engine/ide_read.py`) instead of
    a private version in each of four modules, with three different sentences
    for "it will not say its name".
  - **Writing a text file.** POU and property export ended in twenty-five
    identical lines; they now say only how the content is built.
  - **The native-XML round trip.** Three callers each named their own temp
    file for the same "export it, read it back, delete it".

- **Long functions became lists of steps.** `perform_import_items` was 256
  lines and nine levels deep; it is four named passes and an order
  (`engine/import_items.py`). `build_project` was 343 lines and seven deep;
  working out which line a build message points at is now pure text in, text
  out, with 26 tests and no IDE (`engine/build_log.py`). `ensure_folder_path`
  makes a folder once and says so when it cannot, instead of four attempts at
  one thing and a `None` the caller carried on with.

- **The engine stopped going looking for the IDE.** `projects`, `system`,
  `online` and `PouType` are handed in from the entry body's own namespace
  (`engine/entry.py`'s `borrowed()`). Four resolvers used to search the
  caller's globals, then `__main__`, then every loaded module until something
  looked close enough — a hunt for an object the caller was already holding,
  and a way to pick up a dead one from a previous run. `import __main__` and
  `sys.modules` no longer appear in `engine/` at all.

- **Three silent failures that had been costing real work.**
  - A property whose accessors could not be read was hashed as if GET and SET
    were empty. The previous run had computed it the same way, so the two
    matched, the cache said "identical", and the export skipped it.
  - `_hash_content` answered an error with `""`, and `NativeManager.export`
    tests `old_hash and old_hash == new_hash` — which `""` makes false
    forever, so that file was reported "updated" on every single export and
    nothing said why.
  - A fourth strategy for finding `PouType` scanned `sys.modules` in a module
    that never imported `sys`; the NameError went into a bare `except: pass`.
    Measured on both IDEs, the strategy that actually fires is the one that
    reads the script's own namespace.

- **`codesys_ui.py` says out loud that it needs WinForms.** The module-level
  `clr.AddReference` was wrapped in a bare `except: pass`, and every class in
  the file subclasses `Form` — so a "tolerated" failure raised NameError one
  line further down, with a message about nothing. It raises a sentence now,
  and the second dialog path that reached into `__main__` is gone.

- **Bare `except:` came down in every engine file that had any**, and
  `engine/entry_build.py` and `engine/codesys_ui.py` are at zero. The count is
  the `ALLOWED` table in `tests/test_bare_excepts.py` and nowhere else -- a
  number repeated here would be one more thing to keep in step, and this
  paragraph got it wrong the first time. `tests/test_names_resolve.py` is new
  and asks pyflakes which names do not resolve, with the IDE's globals listed
  by name — two NameErrors reached a real IDE during this work because a
  filter wide enough to hide `system` was wide enough to hide a typo.

- **Every kind of thing now happens in one place.** The two layers this repo
  wrote had grown a habit of answering the same question twice, and each copy
  was a place for the next change to be forgotten:

  - **Running a command.** The watcher and the headless launcher each held
    their own "run it, and turn what came back into a result record". A field
    added to one was a field missing from the other. It is
    `cds/ide/entries.py` `answer()` now, and both callers are one line.
  - **Building a result record.** Three producers wrote one by hand, and the
    shortest carried three of the twelve fields — so `cdsint/report.py` read
    every field defensively and could not tell a value that is legitimately
    null from a producer that forgot it. One constructor, and the printer
    indexes.
  - **The command line.** Twelve subcommands were described across seven
    tables and an `if/elif`; adding one meant finding all seven, and the
    failure that came of missing one was not "unknown command" but a flag
    that parsed and then quietly did not reach the IDE. One `COMMANDS` table
    in `cdsint/flags.py` now, one row per command.
  - **Which directory each IDE scans for menu scripts.** The installer
    carried a copy of `cdsint/installs.py`'s vendor table, and the two
    disagreed for months about whether the machine-wide ScriptDir needs an
    elevated shell — it does not, measured. `irm/setup.ps1` runs
    `cdsint installs --json` and keeps no paths of its own.
  - **Printing.** Five files printed, so `--json` could not be honoured
    anywhere: a caller parsing stdout got prose on stderr with nothing to
    attach it to. Everything goes through `cdsint/report.py`, and the
    launcher's warnings ride back on the record as `notes`.
  - **The exit codes.** `cds/core/exits.py` holds the table both sides read,
    and a test checks it against SPEC 4.3. The IDE side used to define two of
    them again, which is the one thing the launcher's exit-code comparison
    cannot notice: both halves can be equally wrong and still agree.

  Three things a caller can see changed with it. **`--install` naming no IDE**
  printed a traceback and exited 1; it prints one sentence, lists what is
  installed, and exits 4. **Flags that do not go together** are all exit 2 now
  — one of them (`--profile` without `--project`) was exit 1, which tells the
  caller the command ran. **`compare --json`** gains `data.changes`, one row
  per differing object with `name`, `path` and `state`; the per-object answer
  used to be readable only by parsing `stdout_tail`.

  Two real bugs came out with it. A body that asked a question while it loaded
  reached the real message box rather than the stand-in, because the dialogs
  were swapped in after the file was exec'd — under `--noUI` that is an IDE
  frozen on a window nobody can close. And a `verify` step refused by the
  project's `plc` list came back as exit 1, which tells the reader to fix a
  flag when the fix is a word in a file.

- **The settings moved out of the `.project` and into a text file beside it.**
  They lived in the project's own properties, which only a running IDE can
  open. That one fact meant changing a boolean needed an IDE, reading the
  settings needed an IDE, and every new project started from nothing — and it
  had grown four ways in (the Properties grid, a Settings window, a `config`
  command, the first export's dialog) and three mechanisms that existed only to
  hold it up. All of that is gone. `Line.project` now sits beside
  `Line.cdsint.json` — one text file, any editor:

  ```json
  { "plc": ["connect"], "sync_folder": "./sync" }
  ```

  Only the keys somebody decided appear in the file; the defaults live once, in
  the code. Reading it is the only validation and every path goes through it, so
  an unknown key, a wrong type, a word `plc` does not recognise or broken JSON
  stops the command and prints the whole table — a hand-edited file gets typos,
  and a setting that quietly does nothing is worse than one that says so.

  What went with it: `cdsint config`, the Settings window and the status
  window's button that opened it, the computer-name stamp and its mismatch
  dialog, the tool-version stamp and its mismatch dialog, `--force` (which only
  ever answered those two), and `tools/grant_plc.py`. `--sync-dir` is optional
  now: it overrides `sync_folder` for one run and is never written back, so
  pointing it at a copy is safe — it was compulsory only because a copied
  `.project` carried the original's folder inside it, and it no longer does.
  The old `cds-sync-*` properties are not read, not migrated and not removed;
  a project already set up is asked for its folder once more.

  Two things the move uncovered and fixed. `build` counted the project's
  applications from a flag the last export had written, so the first build
  after a second application appeared skipped the chooser, compiled the active
  one and reported success with `--app` doing nothing; it walks the tree every
  build now, and a `--app` naming an application that is not there is a
  failure rather than a different build. And the engine's logger read the sync
  folder through a `projects` name that does not exist in that module, so the
  `NameError` went into a bare `except` and debug logs quietly stayed in
  `%TEMP%`; the folder is passed in now.

- **Six hundred lines nobody could reach are gone.** The compare window, the
  side-by-side diff viewer and the `.diff/` folder they wrote to were only ever
  opened from a Scripts-menu entry that the move removed, so no user could get
  to any of it — while a SPEC rule and a test went on guarding that path.
  `compare` on the command line stays; `git diff` on the exported text is the
  side-by-side view now. `tools/Project_resources.py` and `img/` went the same
  way: nothing reached the first and nothing referenced the second.
- **`discover` is a command.** It was a script in `tools/` missing the three
  lines that put the install root on `sys.path`, so **Execute Script File**
  failed on its first import and there was no other way in. It is the one
  diagnostic for an object that never reached the disk and said nothing about
  it, so it now has both command forms like any other: it walks the tree, says
  what each object was recognised as, and reports every type GUID no kind in
  `profiles/default.json` claimed in `data.unknown`, with the run not ok. The
  fix for an unknown GUID is a JSON edit, and the output says so.
- **`Project_perf_probe.py` is `tools/perf_probe.py`.** The prefix is what puts
  a name in the IDE's Scripts menu, so a maintainer's profiler wearing it looked
  like a feature to click. Only the three stubs carry it now (PRINCIPLES 12).
- **The sync folder can be changed again.** It was set on the first export and
  then unreachable: `Project_directory.py` had gone and there was no other way
  in. Editing the settings file is that way now (above); the first export still
  asks when there is nothing to read.
- **The version number lives in one place.** `pyproject.toml` carried a copy of
  `SCRIPT_VERSION` kept honest by a test; it reads the constant directly through
  `[tool.setuptools.dynamic]` instead, and the readMe no longer prints a number
  at all. A release is one line and a tag.
- **The readMe says the things the move dropped**: the `//% cds-text-sync.*`
  pragmas and what each one does, `profiles/default.json` and its two tables,
  the `tools/` scripts and how to run each, how to install the skill, and what
  to unpick when upgrading from `kevin-cds-text-sync`. Two links in
  `docs/AI_WORKFLOW.md` had pointed at readMe sections that never came across;
  `tests/test_doc_links.py` now walks every in-repo link and anchor in the docs.

- **The IDE's Scripts menu listed eleven entries, and there was no way to hide
  them.** The menu is a recursive scan of ScriptDir for `.py`, so every module
  had to live at the top level, be named `.pyw` to stay out of the list, and be
  loaded through `imp.load_source`. The bodies now live in `engine/`, outside
  ScriptDir, and only three small stubs sit where the IDE scans. Ordinary imports
  replace the loader, which also removed the last `imp` call — a module CPython
  3.12 no longer ships.
- **The command is `cdsint`**, installed from `pyproject.toml`, replacing
  `python cli/cds_ide.py`. The instance directory moved to
  `%LOCALAPPDATA%\cdsint\instances`; a watcher started before the move is
  invisible to the new CLI, and restarting it is the whole migration.
- **An agent that could build could also download to the machine.** There was
  nothing between `cdsint` and a PLC but the absence of a command; the probe
  script that knew how to log in, write a boot application and start it was one
  copy away from being one. `plc connect` and `plc download` are now that
  command, and they are the only two with a permission layer in front of them:
  the `plc` list in the project's settings file says whether this project
  allows the action at all (exit 5 if not), and `-y` says the caller means
  this call. There is no `--target` form, because the watcher lives in an
  IDE somebody is using and a login would take their online session. Both
  commands end in the same check, which is the reason to have them: the CRC the
  controller holds now, against the one the last download from this project
  left there. Only `MATCH` exits 0 — `DIFFERENT` means something else has been
  downloaded to the machine since, and `UNKNOWN` means there was nothing to
  compare, which is not agreement. Credentials come from `CDS_DEV_USER` and
  `CDS_DEV_PASS` and reach no command line, file or report.

- **The check those two commands exist for compared two files that are not the
  same file.** It built a boot application offline and held its `.crc` against
  the controller's. On the bench that answered `DIFFERENT` every time, for two
  independent reasons. The artefacts differ: the controller's `.app` is 2118764
  bytes, the offline one 2098340, with 1.68 million bytes unalike. And the
  offline value is not a property of the source — a four-byte identity is
  stamped into every 64 KB block, and the compiler mints a new one whenever the
  project has been written to, which the `--project` form does on every run when
  it sets `cds-sync-folder`; two identical `plc connect` runs a minute apart
  built `128DBA21` and `59B20109`. The comparison is now the controller's own
  CRC against what the last download from this project left on that controller,
  recorded in `<project>.cdsint-plc.json` beside the project, one entry per
  controller. `MATCH` therefore says "this controller still holds what cdsint
  put on it from here" and not "the controller is running this source": an
  edited POU nobody downloaded leaves it at `MATCH`, and `compare` and `verify`
  are the commands that read every object to answer the wider question. Neither
  command compiles anything now, which took `connect` from about 105 seconds to
  about 65. In exchange `download` gained the self-check it had been missing:
  it reads the controller's CRC before and after, and a value that did not move
  means nothing was written, however quietly the login returned.

- **A compare between an edit and an export threw away the edit.** The
  dirty-file guard reads one thing: the sync-cache entry saying what the
  disk held at the last sync. `find_all_changes` rewrote the cache with
  only the objects it found unchanged, so every object it reported as
  *different* lost its entry — and it runs before the Confirm Import
  dialog, so `compare`, `verify`, and an `import` nobody confirmed all
  left the next export free to overwrite an unimported edit, reporting
  `ok` with nothing pending. Entries for objects this run could not
  rewrite are now kept. (The compare dialog's own export had the mirror
  problem, fixed the same way and then deleted with the dialog above.)
- **A headless run could answer with the previous run's report.** The
  report path is stable across runs by design, so an IDE that hung on a
  dialog and wrote nothing left the last run's file to be read: it
  carried `intended_exit`, the run counted as finished, and `verify`
  passed on numbers from a run that had already happened. `run()` now
  removes the report before launching, as it already truncated stdout
  and stderr. Two more on the same path: `--sync-dir` that would not
  stick was swallowed into a `False` and the commands ran against the
  folder the project file carried, and Ctrl-C left the `--noUI` process
  running with no window, holding the project's lock.
- **A killed IDE's lock file is only cleared when it is ours to clear.**
  `--force-lock` means "go ahead anyway", not "that lock is mine", so a run
  started with it and then killed on timeout used to remove a lock file that
  another IDE really did have the project open behind — and the next run
  opened the same project alongside it. The launcher now records whether a
  lock was there before it started: if it was, the lock is left alone and the
  reason says so in `notes`, and the next `--project` run needs
  `--force-lock` once more. Same when the killed process does not actually
  die.
- **CI runs on Windows and Linux, not one of them.** Windows is where the IDE
  lives; Linux is the only place a Windows path handled with `os.path` can
  fail, which is why every run before this was red. Both jobs green is now
  what an acceptance means.
- **An object the IDE will not describe no longer gets a duplicate.**
  Its `.st` looks like a file nobody owns, so import created a second
  object for it or moved an unrelated orphan onto it; export has refused
  to delete orphans under the same conditions since D13. The withheld
  filenames are reported in `data.not_created`.
- **The version stamp is gone, and so is the warning it produced.** It was
  written into the project after the save rather than before, so it never
  survived a headless run at all and every run therefore warned about a
  version mismatch — a warning that is always wrong is a warning nobody
  reads. The mismatch dialog went with the settings move above, and D15 says
  the disk format does not change without a major version, so there is
  nothing left for a stamp to guard.
- **A safety backup that could not be made no longer lets the import run.**
  `engine/backup.py` answered every kind of trouble with the same `None`: no
  project open, project never saved to disk, save refused, copy refused — and
  the caller read that `None` as "no backup was asked for" and went on to
  change the project, which is the one thing a safety backup exists to
  prevent. `create_safety_backup()` now hands back `(filename, error)` with
  exactly one of the two set, both `None` only when the settings genuinely
  asked for no backup, and import refuses with `ok: false` on an error.
  End-of-sync saving is the other half: saving and copying were an `if/elif`,
  so with `cds-sync-backup-binary` on the only save was the one buried inside
  the copy, and a save that failed still left the previous copy in place
  looking like a fresh backup. They are two calls now, and
  `finalize_sync_operation()` returns the reason either one did not happen —
  which both import and export report, export separating the export itself
  from the save so the reader does not go hunting for a bad export.
- **The performance probe could not start, and its table had gone stale.**
  `tools/perf_probe.py` called `resolve_projects()`, a function the engine
  deleted when `engine/entry.py`'s `borrowed()` replaced the four resolvers,
  so the probe stopped at a `NameError` before it measured anything. Three
  more rows named things that are not there: `resolve_projects` itself, and
  `ConfigManager.update` and `ConfigManager.create`, methods that class has
  never defined. A row that matches nothing does not fail — it measures
  nothing and prints nothing, and a cost ranking that does not mention a
  function reads as a function that cost nothing. `install_probes()` now
  names every unresolved row and installs no probes at all rather than
  producing a report with holes in it, and the tables live in
  `tools/perf_tables.py` where `tests/test_perf_probe.py` reads them against
  the real engine, so the next rename fails in CI instead of in a report.
- **The last three flag reads that behaved differently on the two runtimes.**
  `hasattr(obj, name) and obj.name` swallows every exception on IronPython 2.7
  and only `AttributeError` on CPython 3, so a property that raises reads as
  False inside the IDE and crashes the import outside it — and it costs two
  crossings into .NET where one would do (PRINCIPLES 3). The two in
  `update_object_code` are `ide_flag()` now, which is the function written for
  exactly this. The third was inside a branch that could never run:
  `find_object_by_name` took a `parent_name` to break a tie between objects
  sharing a name, and its one caller passed its own local `parent_name` as the
  *first* argument, so the tie-break never ran once. The parameter and the
  branch are gone, and `ALLOWED["engine/codesys_utils.py"]` in
  `tests/test_bare_excepts.py` drops from 11 to 10 with the bare `except:`
  that lived in it.
- **The size limits have a test now, and the hash has one at all.**
  PRINCIPLES 2 said what hard means — no new file starts over 400 lines, no
  file already over it gets longer — and nothing enforced it, so the sentence
  sat there while three engine files went past 1000 lines.
  `tests/test_size_limits.py` is the ratchet, in the shape
  `test_bare_excepts.py` proved: one table of the files over the limit and
  one of the functions over it, each at the length it is today, and an entry
  that goes either way fails. The tables are the count; no other file carries
  a copy. `tests/test_hash.py` covers `calculate_hash`, which decides whether
  a `.st` changed and had no direct test — the case it pins is a comment with
  Chinese in it, which is where the two runtimes could have parted company.

Behaviour that was in `main` but never released:

- **Export and compare each rejected every cache entry the other wrote.** Both
  read and write `sync_cache.json` under the same keys, but derived
  `disk_mtime` independently: `int(st.st_mtime)` on the export side, a float
  from `os.path.getmtime()` on the compare side. NTFS stamps almost always
  carry a fraction, so on a real 148-object project the export side accepted
  100% of its own entries and the compare side accepted 0%. Because the two
  alternate in normal use, whichever ran last left the cache in a format the
  next one could not read, and every run re-processed every object. One
  `file_signature()` helper now feeds both, reporting milliseconds as an int:
  whole seconds would miss an edit made inside the same second, and a float
  would make cache equality depend on `repr()` surviving a JSON round trip.
- **One operation saved and copied the project two or three times.** Import
  ended with `finalize_import()`, which saved and — with
  `cds-sync-backup-binary` on — copied the whole `.project`; then its caller
  called `finalize_sync_operation()`, which did it again. Export copied the
  binary before and after, to the same filename, so the second copy just
  overwrote an identical first. On a 9.7 MB project each copy is a CODESYS save
  plus a full file copy, and they ran *after* the completion popup, which is why
  the tool looked like it kept working long after it said it was done.
  `finalize_sync_operation()` is now the single owner of end-of-operation
  saving. Import keeps two saves on purpose: the safety backup has to capture
  the state before the import.
- **"Time elapsed" measured the operator, not the sync.** The timed region
  spanned blocking dialogs and ended before the final save, so an 83-second
  export was overstated at one end and understated at the other. Prompts go
  through `timed_prompt()` and their duration is subtracted; the final save
  moved inside the measured region.
- **Almost all of an unchanged export was spent proving nothing had changed.**
  461 objects, 99.6% cache hits, 13.4 seconds, one object actually exported —
  and 5.0 of those seconds went to four helpers reading the same property off a
  live CODESYS object two to six times per call. The cause is that
  `hasattr(o, n) and o.n` is two crossings into .NET, not one. Each property is
  now read once. `update_application_count_flag` was another 1.63 seconds
  fetching its own copy of the project tree for a flag export never reads; the
  count now falls out of the classification the export already does.
  Ancestor paths are memoised per ancestor, turning ~300 root walks into ~44 on
  a 150-object project, and `test_read_budget_per_object` pins the ceiling so
  the next regression fails a test instead of showing up as seconds.
- **New diagnostics.** `tools/cache_doctor.py` replays both cache-hit
  predicates against a sync directory offline, so "is the cache working at
  all?" no longer needs CODESYS open — it is what found the `disk_mtime`
  split. `tools/perf_probe.py` wraps the real engine functions in place
  and runs a real export, compare or import, ranking them by exclusive time.
- **A byte-order mark at the head of a `.st` file was imported as code.** The
  sync folder is read as plain UTF-8, so a BOM — which Windows editors add
  without being asked, PowerShell's `Out-File` and Notepad among them — arrived
  as a U+FEFF in front of `PROGRAM`, and import wrote it into the POU. On the
  bench the untouched `PLC_PRG.st` with a BOM in front of it imported with
  `updated: 1` and `ok`, and took the build from 0 errors to 6. The comparison
  had the matching half of the problem: such a file never equalled what the IDE
  held, so every compare reported it and every import rewrote the POU with the
  mark still there. `read_sync_text` now reads the sync folder — one reader,
  `utf-8-sig` — and the six places that opened those files themselves go
  through it. Nothing here writes a BOM, so this only ever drops somebody
  else's.

- **The documentation and the tests were gone through for things that had
  stopped being true.** No behaviour changed here, but a good deal of what a
  reader was being told did. The spec carried a "status" line per decision — a
  snapshot with no expiry date, and thirty-two of them had drifted into saying
  the opposite of the code, down to a test count that was off by six hundred;
  where the code stands is what this file and `git log` are for, and the spec
  says what the thing is. The construction order it also carried went to
  `docs/history/`. Three documents gave three different line counts for the
  stubs, none of them right, and two said `list` takes `--target`, which it
  has never done. The `tools/` section named three of the nine instruments.

  On the test side: one stand-in per thing the IDE hands the engine, in
  `tests/fakes.py`, replacing six copies of some of them that had begun to
  disagree with each other; the three files that had grown past the size
  limit are split; and two rules that stopped at a directory boundary —
  `print_function`, and the one concurrency model — now reach the instruments
  in `tools/` that run inside an IDE. `profiles/default.json`
  keyed its notes by list position, so inserting a GUID moved a note onto a
  different one without a word.

  Two things a user can feel, both of them the price of the above. **The
  first sync after this runs slowly once.** `sync_cache.json` is trusted only
  when it was built against the same type profile, and the check is a CRC of
  the whole of `profiles/default.json` — so the two explanatory keys added to
  that file invalidate every cache exactly once, and the next export or
  compare re-classifies every object before the speed comes back. **And
  `tools/call_tree.py` now has to be run from a checkout.** Its parser reads
  the `// === IMPLEMENTATION ===` separator from `engine/codesys_constants.py`
  instead of holding a second copy of it; copying the three call-tree files
  somewhere on their own no longer works.

- **A running IDE can be driven from a terminal at all.** This is the feature
  the rest of the list is built on. **Project_watch** (Tools > Scripting) arms
  a timer and returns immediately, leaving a listener in the IDE, and `cdsint`
  then runs export, import, compare and build in it from any shell without the
  project being closed. Run **Project_watch** a second time, or `cdsint stop`,
  to shut the listener down.

  **The script must end, or the IDE is unusable.** `system.delay()` pumps
  repaints and posted messages but not mouse and keyboard, so a script that
  loops leaves the window looking alive and refusing every click — measured
  with real clicks on CODESYS 3.5.21.40 and confirmed by hand on
  DIADesigner-AX 1.10. The listener therefore lives on a WinForms timer hung
  on the IDE's own message loop, which still ticks on the UI thread, so
  nothing about the object-model calls changes. Between commands the IDE is
  genuinely free; while a command runs it is busy, exactly as it is when you
  run the script from the menu yourself.

  **The dialogs are answered by flags, never guessed.** A question with no
  flag behind it comes back as `needs_input` naming the flag, exit 1, and
  nothing changed in the IDE. `compare` reports counts and the per-object
  differences instead of opening a picker. One directory per IDE holds the
  file protocol, so several IDEs can be driven at once: `list` shows them and
  `--target` picks one by instance id or project name. `Project_import.py`
  reports its two give-up paths through `system.ui` rather than `print`, so a
  cancelled import cannot look like a successful one.

---
