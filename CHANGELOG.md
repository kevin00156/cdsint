# Changelog

All notable changes to this project will be documented in this file.

---

### Unreleased — moved into cdsint

**The tool became a product with its own repo.** The code came out of
`kevin-cds-text-sync` (branch `fix/member-creation-parent-resolution`, commit
`9aa9886`) and moved here unchanged in behaviour; that repo keeps the history
up to that commit. Version numbering restarts at `0.0.1` — the `k1.x` line was
a fork of upstream `cds-text-sync` and does not carry over. `cds-sync-version`
is compared as a plain string, so the first sync of an existing project warns
about a version mismatch once and then records the new number.

- **The IDE's Scripts menu listed eleven entries, and there was no way to hide
  them.** The menu is a recursive scan of ScriptDir for `.py`, so every module
  had to live at the top level, be named `.pyw` to stay out of the list, and be
  loaded through `imp.load_source`. The bodies now live in `engine/`, outside
  ScriptDir, and only ten-line stubs sit where the IDE scans. Ordinary imports
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
  the project property `cds-sync-plc` says whether this project allows the
  action at all (exit 5 if not, and only a person in the IDE can change it —
  `config set` refuses to write that one property), and `-y` says the caller
  means this call. There is no `--target` form, because the watcher lives in an
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
  rewrite are now kept. The compare dialog's own export had the mirror
  problem: it wrote the file and recorded nothing, so the next ordinary
  export blamed the disk for a change the IDE had made and refused.
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
- **An object the IDE will not describe no longer gets a duplicate.**
  Its `.st` looks like a file nobody owns, so import created a second
  object for it or moved an unrelated orphan onto it; export has refused
  to delete orphans under the same conditions since D13. The withheld
  filenames are reported in `data.not_created`.
- **`cds-sync-version` is written before the project is saved**, not
  after, so it can actually outlive the run that wrote it. Written
  afterwards it never survived a headless process at all, and every run
  therefore warned about a version mismatch — a warning that is always
  wrong is a warning nobody reads.

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
  split. `tools/Project_perf_probe.py` wraps the real engine functions in place
  and runs a real export, compare or import, ranking them by exclusive time.

---

### Unreleased

**Drive a running IDE from a terminal.** `Project_watch.py` (Tools > Scripting) arms a timer and returns immediately, leaving a listener in the IDE; `cli/cds_ide.py` then runs export, import, compare and build in it from any shell, without the project being closed. Run `Project_watch.py` a second time, or `cds_ide.py stop`, to shut the listener down.

- **The script must end, or the IDE is unusable.** `system.delay()` pumps repaints and posted messages but not mouse and keyboard, so a script that loops leaves the window looking alive and refusing every click — measured with real clicks on CODESYS 3.5.21.40 and confirmed by hand on DIADesigner-AX 1.10. The listener therefore lives on a WinForms timer hung on the IDE's own message loop, which still ticks on the UI thread, so nothing about the object-model calls changes. Between commands the IDE is genuinely free; while a command runs it is busy, as it is when you run the script from the menu yourself.
- **The dialogs are answered by flags, never guessed.** `--yes` confirms an import, `--force` overrides a version or computer mismatch, `--delete-orphans` answers the orphan prompt, `--app` picks the application to build. A question with no flag behind it comes back as `needs_input` with the flag named, exit code 1, and nothing changed in the IDE. `compare` reports counts and the per-object differences instead of opening its picker.
- **One directory per IDE** under `%LOCALAPPDATA%\cds-text-sync\instances`, so several IDEs can be driven at once; `list` shows them and `--target` picks one by instance id or project name. Exit codes: 0 done, 1 failed or needs a flag, 2 no single live IDE matched, 3 timed out.
- New: `cds/core/{ipc,instances,commands}.py` (the file protocol, pure Python, unit-tested), `cds/ide/{watcher,session,silent,project}.py` (the IDE half), `cli/cds_ide.py`, `docs/WATCHER_CLI_PLAN.md`, `docs/RESEARCH_HTTP_IDE_CONTROL.md`. `Project_import.py` now reports its two give-up paths through `system.ui` instead of `print`, so a cancelled import cannot look like a successful one. Tests: 301.

---

### Version k1.1.1 (2026-08-07)

**Fixes for POU/interface members being created in the wrong place on import** — both silent: the object *was* created, just not where it belonged, and the next compare then deleted it as an orphan, so every import created and destroyed the same objects in a loop ("匯入每次結果都不一樣").

- **Interface methods were never created**: `POUManager.create` dispatched on the exact `method` GUID, so `itf_method` (a method on an INTERFACE — a distinct GUID, `f89f7675-…`) matched no branch and fell through to the `create_pou` fallback, which an interface cannot serve; `create` returned `None` with no exception, so the log showed only a bare `Failed to create …`. Every `//% cds-text-sync.kind=itf_method` file failed on every import (observed: `IAxisControl` missing 7 methods, `IStateMachine` empty — a project that could not compile). Dispatch is now keyed by **kind** (`kind_of`), not by primary GUID, with `itf_method` routed to `create_method`.
- **Members landed in a same-named folder instead of on their POU**: `create_new_object` accepted the resolved container as the parent POU on a **name match alone**. The export lays a POU's members out under a folder named after the POU (`Function Blocks/MC_BasicControl/MC_BasicControl.Main.st`), so the folder always won and each method/action/property was created as a standalone `PROGRAM` beside the real FB. Collisions surfaced as `An object with the name 'Init' already exists within the corresponding namespace` (folders do not scope the POU namespace), and the strays had no disk file, so the next import deleted them and the one after recreated them. All four parent-resolution strategies now require the candidate to be a POU or interface (`_is_pou_or_itf`), and `find_parent_pou` looks one level through a same-named folder.
- **Members never silently become POUs again**: `POUManager._create_member` fails loud when the container exposes no creator for the kind, instead of falling back to `create_pou` — the same "fail rather than create the wrong kind" rule k1.1.0 applied to special GVLs.
- **Profile**: added `28747452-a93d-4b34-8d05-d2c6018edd7d` to `property_accessor` — the GUID emitted for accessors on an *interface* (accessors on a POU keep `792f2eb6-…`), the same method/itf_method split one level down. Observed on DIADesigner-AX 1.8 via `Project_discover.py`, which flagged 28 unclassified `Get`/`Set` objects.

Regression tests in `tests/test_member_creation.py` (11); 6 of them fail against the previous code. Tests: 149.

### Version k1.1.0 (2026-07-15)

**Four upstream features ported as concepts onto the fork's text-first engine** (upstream's 2.x implementations are built on the external-engine/CLI architecture this fork rejected, so these are re-implementations, not merges):

- **JSON type profile** (`profiles/default.json`, from upstream v1.7.5's profile idea):
  - Object-type GUIDs moved out of `codesys_constants.pyw` into `guid_aliases` — one kind can own several GUIDs (first = primary, rest = version variants). The SP21 P4 GUID differences fixed in k1.0.1 (`method` alt-GUID, enumeration DUT) are now aliases of `method`/`dut` instead of separate kinds, and the old upstream persistent-GVL GUID is tolerated as an alias. Future GUID drift is a JSON edit; `Project_discover.py` points there.
  - `sync_direction` per kind: `bidirectional` / `export_only` / `import_only` / `disabled`. `library_manager` is `export_only` (generalizes the f7de090 fix — compare never marks non-exported kinds as IDE orphans, import refuses to touch or delete them, loudly); `device`/`device_module` `disabled` replaces the hardcoded exclusion.
  - `classify_object` normalizes alias GUIDs to the primary; `sync_cache.json` stores a `profile_hash` so any profile edit forces full re-classification (no more stale-skip poisoning). A missing/broken profile fails loud — no silent fallback table.
- **Build-attribute pragma sync** (manual port of upstream d85381d, v1.7.4): `exclude_from_build`, `link_always`, `external_implementation`, `enable_system_call` sync as `//% cds-text-sync.<attr>=true` header lines in `.st` files, compared both ways and applied via `obj.build_properties` on import (removing the line clears the IDE flag). State hashes include attributes (`CACHE_VERSION` bumped — one-time full rebuild). Also deduplicated the three export cache-skip blocks into `ObjectManager._try_cache_skip`, deleted the dead `batch_import_native_xmls`, unified export/compare manager dicts via `create_import_managers()` (compare's dict was missing `visu_manager`/`device`/`softmotion_pool`), and unified metadata writes in `save_sync_metadata` (version property always recorded; metadata file debug-only).
- **Kind pragma** (concept from upstream v2.0.1's TypeGuid pragma, reshaped): `//% cds-text-sync.kind=<kind>` is stamped only on files whose kind ST keywords cannot express (persistent GVLs, parameter lists, actions, interface methods) — all other files stay byte-identical. Import lets the pragma win over keyword sniffing and maps the kind name to the *current profile's* primary GUID, so **persistent GVLs deleted from the IDE are recreated as persistent GVLs** (previously they were silently recreated as PROGRAM POUs via the `create_pou` fallback; when no scriptable creation API exists the import now fails with an explicit message instead). Same parser as the attribute pragmas — one mechanism. Kind mismatches between disk and IDE are warned, never auto-fixed.
- **Offline call-tree tool** (`tools/call_tree.py`, extracted from upstream f09c438): standalone CPython, builds a cross-file call graph from the exported `.st` projections — `python tools/call_tree.py <sync-dir> [root-pou] [-o out.json]`. Resolves FB-method calls through local/global/GVL instance types, tags IEC built-ins via `tools/sys_funcs.json`, renders a text subtree with recursion guards.

Migration: first compare/export after upgrading runs the slow path once (cache version + profile hash changed), rewrites only ambiguous-kind and attribute-bearing files, then Merkle-speed returns. Existing pragma-less exports compare clean. Tests: 118 (golden-equivalence tests pin the generated GUID tables to the k1.0.2 literals).

### Version k1.0.2 (2026-06-13)

**Fix for objects silently imported into a phantom folder when the device name differs:**

- **Device-name remap on import**: Every device-contained object's path begins with the device name (from `get_container_prefix`). When an export made under one device name (e.g. `CODESYS_Control_for_Linux_SL`) was imported into a project whose device had a different name (e.g. `Device`), `find_object_by_path`/`ensure_folder_path` failed to resolve the leading segment and **silently created a bogus top-level folder** named after the export's device, nesting every imported object *outside* the real device. The objects existed in the project (so `Project_compare` saw them via the recursive scan) but never appeared under the device in the IDE — the "imported fine but nothing shows up" symptom. The workaround was to manually rename the IDE device to match the export.
  - `perform_import_items` now reconciles the device name: `build_device_remap` detects a renamed device by structurally confirming the second path level (e.g. `Application`) against the IDE's actual device(s), then rewrites the leading segment of every import path onto the real device (`apply_device_remap`). The absolute on-disk file path is never rewritten.
  - The remap is **fail-safe**: a segment is only remapped when it can be positively tied to exactly one device, so genuine project-global top-level folders are left alone and ambiguous multi-device cases are skipped (with a warning) rather than guessed.
  - `Project_import.py` now surfaces the detected mismatch in the final confirmation dialog (`[!] Device remap (export -> IDE): …`) instead of remapping silently.
  - Regression tests added in `tests/test_device_remap.py`.

### Version k1.0.1 (2026-06-09)

**Fixes for silently-dropped objects on export/import:**

- **Corrected/added object type GUIDs for CODESYS SP21 P4**: `classify_object` silently skips any object whose `obj.type` GUID is unknown, so several objects vanished from export with no warning (and were then deleted as false "orphans"). Discovered via `Project_discover.py` and fixed:
  - `persistent_gvl` corrected to `261bd6e6-…` — the hardcoded `3183921b-…` never matched a real object, so **Persistent Variable lists (PersistentVars) were never exported**.
  - Added `method_alt` (`62ebfd1c-…`), a second Method GUID SP21 emits (e.g. `Main`/`Init`), treated exactly like a method.
  - Added `enum` (`40989022-…`), an Enumeration DUT variant, exported as a textual `.st`.
- **Sync cache no longer permanently buries skipped objects**: both the export loop (`Project_export.py`) and the compare/import loop (`codesys_compare_engine.pyw`) trusted a cached "skip" decision (`rel_path=None`) and never re-classified, so the GUID fixes above had no effect until the cache was manually deleted — and on import the stale skip could delete the disk file as a false orphan. The cache fast path is now used only for objects that previously had a real path; skipped objects are always re-classified, so newly-supported types self-heal without clearing the cache.
- **Encoding fix**: removed a non-ASCII character from `Project_export.py` (a headerless entry script parsed as ASCII by IronPython).

### Version 1.7.3 (2026-04-02)

**Move/Rename Detection & Stale File Cleanup:**

- **Moved File Detection**: Implemented smart detection of renamed/moved project files by cross-referencing IDE orphan objects with disk orphan files using base filename matching.
- **Automatic Path Invalidation**: Enhanced cache invalidation logic to detect when objects are moved/renamed in the IDE, ensuring stale cached paths are refreshed during comparison.
- **Stale File Cleanup**: Added automatic removal of old files from disk during export when objects have been moved/renamed in the IDE, preventing orphaned files from cluttering the sync directory.
- **UI Enhancements**: Updated comparison dialog to display moved files with their old (IDE) and new (Disk) paths, using `~moved` visual indicator.
- **Import/Export Move Handling**: Added logic to physically move objects within the IDE during import when path mismatches are detected, ensuring project structure stays synchronized.
- **Statistics Update**: Moved object count now reported in comparison summary (`~:` prefix) and import/export completion messages.

### Version 1.7.2 (2026-03-28)

**Critical Fixes & UX Optimization:**

- **Module Import Fix**: Resolved a critical `ImportError` where `codesys_ui` was not being loaded in `Project_directory.py`, causing a crash on startup for new projects.
- **Reference Bug Fixes**:
  - Fixed an undefined variable crash (`choice[0]`) in `Project_directory.py`.
  - Fixed an undefined variable crash (`result[0]`) in `Project_export.py` during orphaned file cleanup.

### Version 1.7.1 (2026-03-27)

**UI Robustness & Post-Sync Enhancements:**

- **Standard Windows Prompts**: Replaced the unreliable native CODESYS `system.ui.choose` radio-button dialogs with standard Windows MessageBox dialogs (`ask_yes_no`, `ask_yes_no_cancel`) across all scripts.
- **Cancel Button Fix**: Completely resolved an issue where clicking "Cancel" or closing dialogue windows would fail to halt script execution due to inconsistent CODESYS API return types.
- **Import Final Confirmation**: Added an explicit final summary dialog (`Ready to import X changes into the IDE... Proceed?`) right before applying structural changes or deletions in `Project_import.py`.
- **Auto-Save & Workflow**:
  - Introduced optional automatic project saving and binary backup after an export is completed.
  - Added a new 'Save Project after Export' toggle in the Configuration UI (`Project_parameters.py`).
  - Centralized version compatibility checks, safety backups, and post-sync operations into `codesys_utils.pyw` for cleaner architecture and standardized execution.

### Version 1.7.0 (2026-03-27)

**Merkle Tree & High-Performance Sync Overhaul:**

- **Lightning-Fast Comparison**: Total sync/compare time reduced by ~90% (sub-10s for large projects) using a new Merkle Tree-based hierarchical hashing strategy.
- **Intelligent Path/Type Caching**:
  - Implemented GUID-based caching for object classification and filesystem paths in `sync_cache.json`.
  - Eliminates thousands of slow CODESYS COM API calls (`classify_object`, `get_children`, `build_expected_path`) on repeat runs.
- **Hierarchical Merkle Skips**: The comparison engine now uses folder hashes to skip entire unchanged branches of the project tree instantly.
- **Import Optimization**:
  - Eliminated redundant double-save operations during import/backup, reducing the post-import pause by 50%.
  - Optimized POU child restoration and metadata handling.
- **Hybrid XML Hashing**: Integrated last-known XML hashes into Pass 1 so folders containing mixed ST and XML objects can still benefit from Merkle Tree skips.
- **Integrated Accessor Collection**: Merged property accessor scanning into the main object pass to avoid redundant project-wide traversals.
- **Profiling Tool Upgrade**: Updated `Project_perf_test.py` with the new architecture to provide accurate real-world metrics, including cache hit ratios and Merkle skip statistics.

---

### Version 1.6.7 (2026-03-25)

**Silent Mode Removal & Backup Enhancement:**

- **Removed Silent Mode**: All `silent` parameters have been removed from `Project_import.py`, `Project_export.py`, `Project_compare.py`, and `Project_Build.py`. Scripts now consistently use modal dialogs for all user feedback.
- **Unified UI Behavior**: All operations now use modal dialogs (`system.ui.info` / `system.ui.error`) in interactive mode, eliminating the previous inconsistent behavior.
- **Version Compatibility Checks**: All version compatibility checks now always prompt the user when version mismatches occur, rather than silently logging warnings or ignoring the issue.
- **Timestamped Backup with Retention**: Enhanced import backup functionality with automatic retention policy:
  - **codesys_utils.pyw**: Added `cleanup_old_backups()` function to automatically delete old timestamped backups while preserving non-timestamped Git LFS backups
  - **Enhanced Backup Function**: `backup_project_binary()` now accepts `retention_count` parameter and returns the backup filename on success
  - **UI Enhancement**: Added "Max Backups to Keep (Optional)" field in settings dialog (default: 10, minimum: 1)
  - **Persistent Settings**: Added `cds-sync-backup-retention-count` property to Project_parameters.py for cross-run persistence
  - **Import Scripts**: Both `Project_import.py` and `Project_compare.py` now create timestamped backups before import operations when changes exist
  - **Backup Reports**: Import completion reports now show backup confirmation message when safety backups are created
  - **Cleanup Pattern**: Only timestamped `.bak` files matching pattern `^\d{8}_\d{6}_.*\.bak$` are subject to cleanup; non-timestamped backup files are preserved

---

### Version 1.6.6 (2026-03-18)

**Resource Analysis UI Enhancement:**

- **Interactive Results Dialog**: `Project_resources.py` now displays results in a modern Windows Forms dialog instead of console output.
- **Sortable Data Grid**: Click column headers to sort by Object Name, Type, Size, or Category.
- **Full Object List**: Shows all analyzed objects with scrolling support (previously limited to top 30).
- **Summary Panel**: Displays Total Code, Total XML, and Object count at the bottom.
- **Fallback Support**: Console output still works if UI components are unavailable.

---

### Version 1.6.5 (2026-03-17)

**Interface Export Support:**

- **Interface Objects**: Added full support for exporting and importing `INTERFACE` objects with their `EXTENDS` clauses preserved.
- **Interface Methods**: Interface methods/properties now export as flat files (`InterfaceName.Method.st`) matching the existing FB pattern.
- **Native XML Fallback**: Added `export_interface_declaration()` function that extracts interface declarations via native XML export when `textual_declaration` is unavailable.
- **Updated Type GUIDs**: Corrected interface type GUID to `6654496c-404d-479a-aad2-8551054e5f1e` and added `itf_method` GUID for interface members.

---

### Version 1.6.4 (2026-03-12)

**UI Cleanup & Module Security:**

- **Hidden Internal Modules**: Renamed all `codesys_*.py` files to `.pyw` extension. This hides them from the CODESYS Script Engine menu, providing a cleaner user interface that only shows primary `Project_*.py` commands.
- **Custom Module Loader**: Implemented a robust `_load_hidden_module` mechanism in all entry scripts to handle `.pyw` imports with proper dependency ordering.
- **Deprecated Scripts Cleanup**: Removed several unused and debug scripts (`debug_metadata.py`, `Project_Daemon.py`) to streamline the repository.

---

### Version 1.6.3 (2026-03-07)

**Version Tracking & Compatibility Detection:**

- **Single Source of Truth**: Added `SCRIPT_VERSION = "1.6.3"` in `codesys_constants.py` as the central version reference for all scripts.
- **Dual Storage Strategy**:
  - **sync_metadata.json**: Metadata file stored in export directory containing script version, last action (export/import), timestamp, duration, and statistics.
  - **Project Property**: Version also saved to CODESYS project property (`cds-sync-version`) for runtime compatibility checks.
- **Import/Compare Warnings**: Both `Project_import.py` and `Project_compare.py` now detect version mismatches and display warnings without blocking operations (User can continue at their own risk).
- **Improved Audit Trail**: Each export and import operation updates `sync_metadata.json` with current script version, making it easy to identify which scripts were used for operations.
- **Git Integration**: The `sync_metadata.json` file is now tracked in version control, enabling teams to see export/import history.

---

### Version 1.6.2 (2026-03-04)

**XML Import & Object Structure Enhancements:**

- **POU Child Management**: Implemented saving and restoring of POU children during the XML import process to maintain project hierarchy.
- **Parent Lookup**: Enhanced parent POU lookup logic during object creation for improved structural accuracy.
- **Empty Implementation Handling**: Ensured that implementation markers are always present for specific object types, even if their implementation is empty (addressing issues where empty methods or properties might be skipped).

### Version 1.6.1 (2026-02-26)

**Orphan Deletion & Stability Enhancements:**

- **Bi-directional Orphan Management**:
  - **IDE-to-Disk (Sync/Export)**: Existing logic in `Project_export.py` continues to clean up files on disk that are missing in the IDE.
  - **Disk-to-IDE (Import)**: `Project_import.py` now supports deleting objects from the IDE if they were removed on disk (e.g., from a Git pull). The "Disk wins" principle is now fully enforced.
- **Improved Comparison UI**:
  - The Interactive Results dialog now clearly identifies objects missing on disk as **"Missing on Disk (DELETE from IDE?)"**.
  - Importing these items will now safely remove them from the CODESYS project tree.
- **Hardware Stability (Device Exclusion)**:
  - Hard-excluded `device` and `device_module` objects from the synchronization engine.
  - Syncing these components via XML was found to be unstable (can lead to tree reconstruction and project "emptying").
  - Users should configure hardware manually and sync the application logic.
- **Bug Fixes**:
  - Fixed an issue where the import process could fail to report the correct number of updated/created items when deletions were involved.
  - Updated default `.gitignore` template to include `*.device` and `*.device_xml` patterns as a safety measure.

### Version 1.6 (2026-02-24)

**Core Engine Refactoring & Interactive Sync:**

- **Multi-PLC & Multi-Application Support**: The engine now automatically handles complex project hierarchies, organizing exports into a clear `Device/Application/Folder` structure (essential for modern CODESYS projects).
- **Metadata-Free Sync Engine**: Significant refactoring to transition from metadata files (`_metadata.csv`, `_config.json`) to a direct, hash-based two-way comparison between the CODESYS IDE and disk. This improves reliability when moving projects between machines or using Git.
- **Interactive Comparison Dialog**: `Project_compare.py` now includes an interactive results window where you can selectively apply changes (Import or Export) directly from the diff list.
- **Project Discovery Tool**: New `Project_discover.py` script for mapping the project tree structure and diagnosing supported block types (logs findings to `sync_debug.log`).
- **Maintenance**: `Project_daemon.py` has been temporarily disabled.
- **Improved Comparison Logic**: Better handling of graphical POUs and XML-based objects (Visualizations, Task Configurations) in the comparison engine.

### Version 1.5.6.1 (2026-02-21)

### Version 1.5.6 (2026-02-18)

**Safety Net: Timestamped Import Backups:**

- **Automatic Rollback Point**: `Project_import.py` now creates a timestamped backup (e.g., `20260218_220000_MyProject.project.bak`) at the very beginning of the import process.
- **Configurable Safety**: Added "Timestamped Backup before Import" toggle in `Project_parameters.py` (enabled by default).
- **Non-destructive**: These backups are placed in the `/project` folder and use a `.bak` extension to avoid conflict with your primary Git LFS tracking.

### Version 1.5.5 (2026-02-18)

**Relative Path Support for Team Collaboration:**

- **Portable Project Configuration**: `Project_directory.py` now supports relative paths (e.g., `./`, `./folderName/`) in addition to absolute paths.
- **Manual Path Input**: Added a new "Manual Input" option in the directory setup dialog, allowing users to type paths directly.
- **Automatic Directory Creation**: If a specified directory doesn't exist, it will be created automatically.
- **Team-Friendly**: Relative paths are resolved relative to the project file location, making projects portable across different machines and users without reconfiguration.
- **Examples**:
  - `./` - Sync to project directory
  - `./sync/` - Sync to a subfolder
  - `C:\MySync\` - Traditional absolute path still supported

### Version 1.5.4 (2026-02-16)

**Comparison Logging & Rerouting:**

- **Dedicated Comparison Log**: `Project_compare.py` now reroutes its output to `compare.log` in the sync directory.
- **Recreative Logging**: The log file is truncated and recreated on every run, providing a fresh report for each comparison.
- **Tee Output**: Comparison results are still mirrored to the CODESYS Script Output window for immediate feedback.

### Version 1.5.3 (2026-02-16)

**Line Ending & Git Consistency Fix:**

- **Cross-Platform Consistency**: Fixed an issue where different line endings (CRLF vs LF) on different machines caused Git to show identical files as modified.
- **Deterministic Export**: The export script now explicitly uses LF (`\n`) for all `.st` files regardless of the host OS by using `newline=''` in file operations.
- **Automated Git Configuration**: Updated the `.gitattributes` template to automatically disable text conversion for `.st` files (`*.st -text`), ensuring they remain as LF in the repository and are treated consistently by Git on all platforms.

### Version 1.5.2 (2026-02-15)

**Improved Property Sync & Bug Fixes:**

- **Enhanced Property Support**: Properties with combined GET/SET accessors are now correctly handled. The export script now accurately combines both the `VAR` declaration and implementation code for each accessor into a single `.st` file.
- **Bi-directional Accessor Sync**: The import script now correctly parses combined accessor content and updates both the declaration and implementation in CODESYS.
- **Object Restoration**: Fixed an issue where objects deleted from CODESYS but remaining on disk would not be recreated. They are now automatically detected and restored during import.
- **Bug Fix (#4)**: Resolved an issue where properties created manually in external editors (or by AI) were incorrectly identified or failed to import.

### Version 1.5.1 (2026-02-15)

**Performance & Optimization Update:**

- **CRC32 Hashing**: Switched from SHA256 to CRC32 for file tracking, achieving **10-20x faster** hashing performance and significantly reducing metadata size.

### Version 1.5.0 (2026-02-13)

**The "Power User" Update:**

- **Project_Daemon.py**: New background service with Global Hotkey (`Alt + Q`).
- **Quick Action Dashboard**: Instant access to Export, Import, Build, and Backup commands.
- **Enhanced Build Log**: `Project_Build.py` now generates a clean, readable table format in `build.log` with accurate line numbers for external editors.
- **Focus Management**: Daemon correctly handles focus switching between Virtual Desktops and restores context after execution.

### Version 1.4.0 (2026-02-12)

**UI & Experience Overhaul:**

- **Configuration Dialog**: Replaced the text-based menu with a modern Windows Forms dialog for easier configuration.
- **Silent Mode**: Added a "Silent Mode" option that uses non-blocking system tray notifications (toasts) instead of blocking popups.
- **Safety**: Added checks to prevent sync on wrong machine (PC Name check).

### Version 1.3.0 (2026-02-09)

**Binary Backup & Configuration Overhaul:**

- **Project_parameters.py**: New interactive menu to toggle features.
- **Binary Backup**: Added optional `.project` file backup loop. The binary is now updated on both Export and Import events.
- **Logging**: Moved `sync_debug.log` to the project sync folder (or Temp) to keep `ScriptDir` clean.
- **Import Logic**: Removed interactive menu from Import script; now uses project settings.

### Version 1.2.0 (2026-02-09)

**Safety & Validation:**

- **PC Check**: Validates `cds-sync-pc` to prevent syncing on the wrong machine.
- **Properties**: All settings are now stored in Project Properties (`cds-sync-*`).

### Version 1.0.0 - 1.1.0

- Full support for nested folders.
- Detection of deletions (Orphan cleanup).
- Library version tracking (`_libraries.csv`).
