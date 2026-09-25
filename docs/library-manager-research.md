# Research: letting an agent change the Library Manager

> A research record, not a spec. Nothing here is implemented, and nothing here
> changes SPEC.md or PRINCIPLES.md; section 8 lists where a design would have
> to change them. Measured on 2026-09-24 against CODESYS 3.5.21.40
> (ScriptEngine 4.2.0.0) and DIADesigner-AX 1.10 (ScriptEngine 4.0.0.0).
> Lenze was not tested.

The question: can `cdsint` (and so an agent) change which libraries a project
uses, safely, and how? Today `profiles/default.json` marks `library_manager`
`export_only`.

---

## 0. Answers in one table

| Question | Answer | Section |
|---|---|---|
| 1. What does ScriptEngine offer? | List, add, remove references; add placeholders; redirect a placeholder to a fixed version; set namespace, qualified-only, optional and two visibility flags; install, uninstall and look up libraries in a repository; add and remove repositories. All public | 2 |
| 2. Do they run under `--noUI`? | Yes, every one, with no prompt at all. The prompt logger was shown to work in the same run setup | 3 |
| 2. Missing library, missing version | 4.2.0.0 **accepts** a reference to a library or version that is not installed, silently, and a clean build then reports **0 errors**. 4.0.0.0 refuses it with an exception | 3.2, 7 |
| 3. What does the exported XML look like, and does an edited one import? | 480 to 700 lines, one element per reference. Importing it **merges**: it adds and restores, it never removes. Deleting the Library Manager object first and then importing restores its content | 4 |
| 3. Why `export_only`? | No reason was ever written down. The setting came with a bulk "sync direction" commit in the upstream repo; the only related remark is an older, deleted comment saying automatic library updates "are not reliable across all CODESYS versions" | 4.4 |
| 4. What does a build see after a change? | Pinned versions resolve to that version, `*` to the newest installed, and Delta also uses partial wildcards (`1.*`). **A plain `build()` after removing a library can say "up to date, 0 errors"; only clean plus build shows the errors** | 5 |
| 5. How to hold it on disk? | Not as native XML: it carries a timestamp and a hash-table section whose order changes after every edit. A small text file of the references the user owns, applied through the API and checked by reading back | 6, 9 |
| 5. Is the export stable? | Two exports in a row are byte-identical, also after edits, on both IDEs. Across an edit the timestamp changes, and after a restore the hash-table section comes back in another order with the same content | 6.1 |
| 6. Delta 1.10 | Same members except `download_missing_libraries`. Refuses uninstalled libraries. Otherwise the same behaviour | 7 |

---

## 1. How this was measured

Every experiment was an IronPython script started as
`<IDE>.exe --profile=... --noUI --runscript=...`, the way
`cds/ide/headless.py` starts, with the same prompt settings
(`LogMessageKeys | LogSimplePrompts | ProcessScriptPrompts`). Each script
opened a copy of a sample project in `%TEMP%\cdsint-work\`, did one list of
operations, and was closed without saving unless a step says it saved. The
scripts are throwaway and not in the repo.

- **Projects.** `softplc_refactor.project` in stock CODESYS 3.5.21.40 (19
  references in its Library Manager), `Shm_2026.07.29.project` in
  DIADesigner-AX 1.10 (27 references).
- **Reflection.** Inside the IDE, every public and private type of
  `ScriptEngine3`, `ScriptEngine.plugin` and the `ScriptDriver*` plug-ins
  (`LibManObject`, `DeviceObject`, `Projects`, `System`, `Online`) was listed
  with its members.
- **After every operation** the script wrote every reference's properties to
  JSON, exported the Library Manager with `export_native`, and built. "Build"
  below means `clear_messages`, `build()`, and a second `build()` if the first
  said nothing, which is what `engine/entry_build.py` does. "Clean build"
  means `clean()` first.
- **Prompts.** Unanswered prompts are printed with their key by
  `LogMessageKeys`. To show the instrument works, one run imported a POU over
  itself without a handler: stdout carried the prompt as JSON with
  `"message_key": "PromptImportConflict"`. So "no prompt" below is a
  measurement, not an absence of evidence.
- The machine had other sessions' processes running; CPU was 7 to 25% when
  checked. No conclusion here depends on timing.

---

## 2. What ScriptEngine offers (4.2.0.0, by reflection)

The project-side object is the Library Manager itself
(`IScriptLibManObject`, versions 1 to 3); the machine-side one is the global
`librarymanager` (`ILibManager`).

| Want | Member | Notes |
|---|---|---|
| List references | `libman.references` (each an `IScriptLibraryReference`), `get_libraries(recursive)` | `get_libraries` returns names only |
| Add a library | `add_library(name)`, `add_library(IManagedLib)` | `name` is the display string, `"Util, 3.5.19.0 (System)"`, or `"CAA Memory, * (CAA Technical Workgroup)"` for newest |
| Remove | `remove_library(name)` | name as `references` shows it, placeholders with `#` |
| Add a placeholder | `add_placeholder(name, default_resolution)` | |
| Pin a placeholder | `IScriptPlaceholderReference.set_redirection(fixed)`, `get_redirection()`, `default_resolution {get;set}`, `effective_resolution`, `resolution_info` | |
| Per-reference options | `namespace`, `qualified_only`, `optional`, `hide_when_referenced_as_depencency`, `publish_symbols_in_container`, `parameters[...]` | all settable; `system_library`, `is_placeholder`, `is_managed`, `id` read-only |
| What a reference resolves to | `IScriptManagedLibraryReference.managed_library` (`displayname`, `version`, `company`, `dependencies`) | throws for a library that is not installed, see 3.2 |
| Fetch missing libraries | `download_missing_libraries()` (`IScriptLibManObject3`) | not run: it goes to the network. Absent on 4.0.0.0 |
| Repositories | `repositories`, `insert_repository(folder, name, index)`, `remove_repository(repo, delete_on_disk)`, `move_repository`, `update_repository` | |
| Install into a repository | `install_library(path, repo, overwrite)`, `uninstall_library(repo, lib)` | `.library` and `.compiled-library` both work |
| Look up | `get_all_libraries(repo)`, `get_all_libraries(exclude_shadowed)`, `get_library(name, repo)`, `find_library(display_name)`, `get_file_path(lib)` | |

Two details a design needs:

- **`id` is not an identity.** The same reference had a different `id` in
  each of three sessions (355630764, 3455446963, 2016844075 for
  `#SM3_Basic`). The XML's `Id` is stable, but it is not the one the API
  shows. References have to be matched by name.
- **Most references are not the user's.** 17 of the 19 in the CODESYS
  project are placeholders whose `resolution_info` says who resolved them:
  "Resolved by device", "Resolved by SoftMotion profile 4.20.1.0", "Resolved
  by licensing mechanism", "Resolved by Essentials". 14 carry
  `system_library = True`. Only `ISysTypes2, 3.5.0.0 (System)` is a plain
  reference, and `#Standard` carries a redirection.

---

## 3. Under `--noUI`

### 3.1 Every operation runs, and none asks anything

Run on the CODESYS project, one process, each step followed by the JSON dump,
an export and a build:

| Operation | Result | Build after |
|---|---|---|
| `add_library("Util, 3.5.19.0 (System)")` | added, `qualified_only = True` | 0 errors |
| `add_library("CAA Memory, * (CAA Technical Workgroup)")` | added; resolves to 3.5.17.0, the newest of the three installed | 0 errors |
| `add_library("NoSuchLib, 1.0.0.0 (Nobody)")` | **added, no error** | 0 errors, "application is up to date" |
| `add_library("Util, 3.5.99.0 (System)")` (version not installed) | **added, no error** | 0 errors, "up to date" |
| `add_library("Util, 3.5.19.0 (System)")` again | no change, no error | — |
| `add_placeholder("MyUtil", "Util, 3.5.14.0 (System)")` | added; `effective_resolution` came back `Util, 3.5.1.0`, not the 3.5.14.0 asked for | 3 errors: "Ambiguous namespace 'UTIL'", three Util versions now in play |
| `set_redirection` of `#Standard` to 3.5.14.0 | accepted | unchanged |
| `set_redirection` of `#Standard` to 9.9.9.9 | **accepted**; `effective_resolution` reads the missing version | 504 errors ("Unknown type: 'TON'") |
| `qualified_only = True` on `ISysTypes2` | set | — |
| `remove_library("ISysTypes2, 3.5.0.0 (System)")` | removed | unchanged |
| `remove_library("NoSuchLib")` | `KeyError: library 'NoSuchLib' was not found.` | — |

Neither stdout nor stderr carried a prompt key in this run or any other
library run. Why `MyUtil` resolved to 3.5.1.0 was not investigated.

New references came in with `qualified_only = True` although the project's
existing ones are `False`; an agent that adds a library and then calls its
functions unqualified will get compile errors it did not expect.

### 3.2 A reference to nothing is invisible to the build

`NoSuchLib, 1.0.0.0 (Nobody)` stayed in the project through `clean()` and a
full build: 5.7 s, 0 errors, no message naming it. The only symptom is on the
reference itself: reading `managed_library` raises "Object reference not set
to an instance of an object". The same holds for an installed library at a
version that is not installed.

So the build is not a check for this. A tool that adds references has to
check each one resolves, by reading `managed_library` (or asking
`find_library`) afterwards, and report the ones that do not by name (SPEC
D13). On Delta the question does not arise (section 7).

### 3.3 Installing into a repository

With the user's permission, on a temporary repository created in `%TEMP%`
and removed afterwards (`remove_repository(repo, True)`; the repository list
afterwards held only `System` again and the folder was gone):

| Call | Result |
|---|---|
| `insert_repository(folder, name, index)` on a folder that does not exist | `ValueError`, "does not point to an existing directory" |
| `install_library(SysTypes.compiled-library, repo, False)` | installed, returned `SysTypes, 3.1.2.0 (System)` |
| the same again, `overwrite = False` | `IOException: Library already exists.` |
| the same again, `overwrite = True` | installed over it, no message |
| `install_library(SysRegistryAccess.library, ...)` | installed as `Registry Access, 1.0.0.0 (3S - Smart Software Solutions GmbH)` |
| a path that does not exist | "Failed to open managed library. (Reason: Object reference not set ...)" |
| a text file named `.library` | "Failed to open managed library. (Reason: The file is corrupted)" |
| `uninstall_library`, `remove_repository(repo, True)` | done |

No prompt appeared. Installing a library already present in `System` into a
second repository made the IDE log "The library 'SysTypes, 3.1.2.0 (System)'
has been changed and was reloaded automatically", so installing touches every
open project that uses that library, not only the one being worked on.

---

## 4. The native XML

### 4.1 What it looks like

`export_native` of the Library Manager wrote 26965 bytes, 479 lines, ASCII,
on CODESYS; 41507 bytes, 702 lines on Delta. It holds:

- a `MetaObject` with the object's GUID, its parent, a `Timestamp`, and a
  `PlaceholderResolution` dictionary;
- `Items`: one element per reference. A placeholder
  (`{4723ebe7-...}`) carries `DefaultResolution`, `PlaceholderName`,
  `ResolverGuid`, `Id`, `Namespace`, `SystemLibrary`, `Optional`,
  `QualifiedOnly`, `HideWhenReferencedAsDependency`,
  `PublishSymbolsInContainer`, `LinkAllContent`. A plain reference
  (`{51a11660-...}`) carries `Name` instead of the first three;
- `PlaceholderRedirectionTable`, a `System.Collections.Hashtable` of
  placeholder name to fixed version. It holds 20 entries in the CODESYS
  project (33 in the Delta one), most of them for placeholders the project's own references do not
  have (`System_VisuElems`, `Matrix`, `Collections` ...), which the API
  cannot see.

It is readable and an agent could edit it.

### 4.2 An edited XML merges; it does not replace

After five additions, a placeholder, two redirections and a removal, the
original export was imported back with `engine/native_import.py`'s
replace-on-conflict handler. The IDE said `ok` and no handler call was
needed. Afterwards:

| | Before edits | After edits | After importing the original |
|---|---|---|---|
| references | 19 | 23 | **24** |
| `ISysTypes2` (removed by the edits) | present | absent | present again, now last in the list |
| `#Standard` redirection | 3.5.18.0 | 9.9.9.9 | 3.5.18.0 |
| the five additions | absent | present | **still present** |

A separate run imported the unchanged export over the Library Manager with no
handler at all: `ok`, and no `PromptImportConflict`, where the same call on a
POU stopped on that prompt. So an XML on disk cannot express "remove this
library": a file with one reference fewer changes nothing.

### 4.3 Delete first, then import, restores exactly

Removing the Library Manager object (`remove()`, accepted) and importing the
original export brought back all 19 references, in their original order, and
the same 20 redirection entries. The next export differed from the original
in `Timestamp` and in the order of the redirection table's entries (8 of 20
moved); parsed, the table held the same pairs. The same on Delta: 27
references back in order, the same 33 redirection pairs in another order. Between the two steps the application has no
Library Manager at all; if the import fails there, the project is left
without one until it is closed unsaved.

### 4.4 Why `library_manager` is `export_only`

From the history of the old repository (read only):

- `e615902` (2026-02-07) exported the list to `_libraries.csv` and on import
  only *warned* about mismatches, telling the user to fix them by hand.
- `ea38988` (2026-02-22) deleted that, with a comment in the removed code:
  "Automatic library updates are not reliable across all CODESYS versions."
- `ddc182a` (2026-04-17) added `sync_direction_overrides` with
  `library_manager: export_only` alongside `device` and `device_module`. The
  commit message and the profile documentation it added give no reason.

Nothing measured the claim. What this round measured is in sections 3 to 7;
the merge behaviour in 4.2 is a concrete reason a plain XML import cannot be
the mechanism, but it is not the reason anyone gave.

---

## 5. What the compiler sees

### 5.1 Pinned, newest, partial

| Written | Resolves to | Measured on |
|---|---|---|
| `Util, 3.5.19.0 (System)` | exactly 3.5.19.0 | CODESYS |
| `CAA Memory, * (CAA Technical Workgroup)` | 3.5.17.0, the newest of 3.5.3.0, 3.5.7.0, 3.5.17.0 installed | CODESYS |
| `DL_EtherCAT_Diag, 1.* (Delta Electronics Inc)` | 1.3.2.2 | Delta, read from the project |
| `DL_SlaveParaBackupRestore, 1.0.* (...)` | 1.0.7.3 | Delta, read from the project |
| placeholder resolved by a device or profile | whatever the device description or SoftMotion profile names; `default_resolution` can differ from `effective_resolution` (`IecVarAccess` 3.3.1.20 default, 4.3.0.0 effective) | Delta |

What `*` means in practice follows from this and was not measured further:
the same project compiles against a different library on a machine with a
different set of installed versions. Only a pinned version or a redirection
gives the same build everywhere.

### 5.2 `build()` can miss a library change

| Change | `build()` right after | `clean()` then `build()` |
|---|---|---|
| remove `#IoStandard` (system library), CODESYS | 0.2 s, "application is up to date", 0 errors | errors ("Unknown type: 'IoConfigParameter'" ...) |
| remove `#SysTypes`, Delta | 0.7 s, 0 errors | errors ("Unknown type: 'RTS_IEC_HANDLE'" ...) |
| remove `#SM3_Basic`, CODESYS | 501 errors at once | 501 errors |
| add a pinned library | recompiled, 5 to 6 s | — |

So after changing libraries, only clean plus build is an answer. cdsint's
`build` today is `build()` (twice if silent), which would report the first
two rows as clean.

System libraries removed this way were not put back by the IDE, by build or
by clean build.

---

## 6. On disk

### 6.1 Native XML is stable only while nothing changes

| Check | Result |
|---|---|
| two exports in a row, unchanged project | byte-identical (CODESYS and Delta) |
| two exports in a row after edits | byte-identical (CODESYS and Delta) |
| two exports around `save_as` and after it | byte-identical |
| export after one added library vs the original | `Timestamp` differs; one `PlaceholderResolution` entry (`CBML`) appeared; the reference added |
| export after removing `#SysMem` vs the original | `Timestamp` differs; the reference gone; nothing else |
| export after "delete, import the original" vs the original | `Timestamp` differs; the same redirection pairs, 8 of 20 in other positions (Delta: the same) |

The last row is the problem: the content is back to what it was and the file
is not, because a hash table's order depends on how it was built, not only on
what is in it. A `git diff` then shows changes nobody made. Canonicalising it (sorting that table,
dropping `Timestamp`) is possible but makes cdsint the owner of a private
serialisation format it does not otherwise need, and 4.2 already rules the
XML out as the way back in.

### 6.2 A small text file built from the API

What the API gives is enough to write a file an agent can read and edit, in
an order cdsint chooses, with nothing in it that moves by itself: the
references by name, their version or `*`, company, the options of section 2,
and each placeholder's redirection. Section 9 sketches it. Its stability is
by construction; the thing to verify is that applying it and exporting again
gives the same file, which the measurements above suggest (every API change
read back as asked, except the placeholder in 3.1).

---

## 7. DIADesigner-AX 1.10 (ScriptEngine 4.0.0.0)

Reflection over the same assemblies, compared member by member for the 104
interfaces about libraries, devices, parameters, native import and projects:
identical, except that 4.0.0.0 has no `IScriptLibManObject3`
(`download_missing_libraries`), no `IScriptDriverInfo2`, no
`IScriptDeviceInstance`, no `IScriptDeviceRequiredLib` and no
`IScriptProject13`.

Behaviour, on the Delta project:

| | CODESYS 4.2.0.0 | Delta 4.0.0.0 |
|---|---|---|
| add an uninstalled library | accepted silently | `StandardError: The library 'NoSuchLib, 1.0.0.0 (Nobody)' has not been installed to the system.` |
| add pinned / newest | works | works |
| redirect to a missing version | accepted | accepted (and 0 errors here, because nothing in the project uses `Util`) |
| remove a library, then `build()` | "up to date", 0 errors; clean build fails | 0 errors in 0.7 s; clean build fails |
| import XML over the existing object | merges | merges (28 before, 29 after: the removed reference back, the two additions kept) |
| delete, then import | exact restore | exact restore |
| prompts | none | none |
| wildcards in the project | `*` | `*`, `1.*`, `1.0.*` |

---

## 8. Where this conflicts with SPEC.md and PRINCIPLES.md

1. **SPEC 4.5 and D15: the disk format.** A Library Manager file is a new
   kind of file in the sync folder, next to the `.st` files and the XML
   sidecars. D15 fixes the `.st` format and the pragma names; a new file
   type is not forbidden by it, but 4.5 lists what the sync folder holds and
   would have to name it.
2. **PRINCIPLES 5 and SPEC goal 1: disk is the truth, and a file with no
   object means create it.** Here the object always exists (one per
   application) and only its contents are synchronised. System references
   the devices add (13 of 19) are not the user's to write down; if the file
   holds only the user's references, "the disk is the whole truth" stops
   being literally true for this kind. The rule would need to say which part
   of the object the file owns.
3. **SPEC D13: nothing skipped silently.** On 4.2.0.0 the IDE accepts a
   reference to a missing library and the build does not mention it (3.2).
   Meeting D13 needs a check cdsint does itself, after applying.
4. **SPEC 6.1 and `cdsint build`: "0 errors" means compiled.** After a
   library change `build()` can report 0 errors for code it did not compile
   (5.2). The build step after a library change has to clean first; whether
   `cdsint build` should always clean is a separate decision (it costs a full
   compile every time).
5. **`profiles/default.json`, `sync_direction.library_manager = export_only`.**
   Would change to `bidirectional`, but the kind would stop being an XML kind
   (`XML_KINDS` in `engine/codesys_constants.py`), because the mechanism is
   the API, not `import_native`. That is a new code path next to the XML one
   for one kind; PRINCIPLES 7 asks that it replace the XML export for this
   kind rather than sit beside it.
6. **SPEC 2, non-goals.** Installing libraries into a repository changes the
   machine, not the project, and reloads the library in every open project
   (3.3). That is outside what any command does today and probably belongs
   outside `import` entirely.

---

## 9. Interface draft

Following the measurements: the API, not XML; names, not ids; clean build
after; verify by reading back.

### A file per application

`<sync>/<device>/Plc Logic/<Application>/Library Manager.libraries`, text,
one reference per line, sorted by kind and name, written by `export` and
applied by `import`:

```
# cdsint library list. Lines the devices add are listed as comments and are not applied.
library      Util, 3.5.19.0 (System)                        qualified_only
library      CAA Memory, * (CAA Technical Workgroup)        qualified_only namespace=MEM
placeholder  MyUtil = Util, 3.5.14.0 (System)
redirect     Standard = Standard, 3.5.18.0 (System)
# system     SM3_Basic = SM3_Basic, 4.20.0.0 (CODESYS)      resolved by SoftMotion profile 4.20.1.0
```

- `library`: a plain reference. Version or `*` as the IDE writes it.
- `placeholder`: a placeholder the user added, with its default resolution.
- `redirect`: a placeholder pinned with `set_redirection`.
- `# system`: references with `system_library = True` or resolved by a
  device, profile or licensing; written for the reader, never applied.
- Options are the settable flags of section 2, written only when they differ
  from what `add_library` produced.

### Import

1. Read the IDE's references, diff them against the file by name.
2. Refuse, before changing anything, any `library` line whose name or
   version `find_library` does not know (3.2), naming the line.
3. Apply with `add_library`, `remove_library`, `add_placeholder`,
   `set_redirection` and the option setters; never touch a system line.
4. Read everything back and compare with the file. Any line that did not
   land, including a placeholder that resolved elsewhere (3.1), goes into
   `failed_objects`.
5. The build that follows (`verify`) cleans first.

### Settings

None needed. Installing libraries into a repository stays out of `import`;
if wanted, it is its own command with its own permission, because it changes
the machine (section 8, point 6).

---

## 10. Not verified

- **Lenze** (ScriptEngine 4.0.0.0 like Delta, not run).
- **`download_missing_libraries()`**: not run, because it contacts the
  CODESYS store.
- **Why a placeholder resolved to a version other than the one given**
  (`MyUtil` to 3.5.1.0, section 3.1).
- **`PlaceholderRedirectionTable` entries the API cannot see**: whether they
  matter to the build, and whether they survive the API-based import in
  section 9, was not measured.
- **What `*` does when a newer version is installed later**: inferred from
  5.1, not measured, because it needs installing a newer version of a
  library than the machine has.
- **The text format of section 9**: a draft; the round trip "apply the file,
  export, compare" was not run because nothing implements it.
- **Library changes and the controller**: offline, adding a pinned library
  made `is_uptodate` false while `is_online_change_possible` stayed true on
  the bench copy (docs/ethercat-research.md 5.1). What a `Keep` login does
  with that difference was not measured for a library change.
