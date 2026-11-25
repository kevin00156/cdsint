# Ticket: `import` must not leave a slave's channel list stale when a `.device` file changes the PDO assignment (GitHub #16)

> Created 2026-11-25. Branch `fix/16-pdo-channel-rebuild` (from `dev`), worktree
> `C:/Users/qazsskevin/Documents/repo/cdsint/.claude/worktrees/cdsi-16`.
> The user is away and will not answer. If you are stuck, write why in the final report.

## 0. Hard rules

- The user is away. Do not ask "shall I continue"; go to the next stage. Blockers go in the final report.
- Touch only what you opened. **An IDE with the project `AX8_with_lenze_driver_experimental` is open on this
  machine, logged in to a real controller, and another session is recording a trace through it. Never pass
  `--target`. Never run any `cdsint plc ...` command. Never open, copy over, or write
  `C:/Users/qazsskevin/Documents/repo/ck_cutter/codesys_project/` or anything under
  `C:/Users/qazsskevin/Documents/repo/ck_cutter*`.**
- Real data only as copies: the two fixture projects below are already copies. Work on copies of *those*
  (copy to a scratch name before each run), so the fixtures stay pristine.
- Every IDE you start is `--project <your copy> --install "DIADesigner-AX 1.10"` with an explicit `--sync-dir`
  under the scratch root. Close only processes whose pid you recorded (`Stop-Process -Id`).
- A second IDE instance may ask about recovering unsaved project data: that is the user's data. Do not answer
  it; close your instance and note it.
- No credentials. No push, no merge, no GitHub comments: those are for the human. Commit locally only.
- One stage done, tests green, commit, then the next stage.
- Scratch root for everything temporary: `C:/Users/qazsskevin/AppData/Local/Temp/cdsint-16/`. Leave `fixtures/`
  there; remove the rest when done.
- Follow `CLAUDE.md`, `PRINCIPLES.md`, `docs/SPEC.md` of this repo. Code, comments, commits in English.

## 1. Goal and scope

Field failure (full text: `gh issue view 16 --repo kevin00156/cdsint`, read-only): a `.device` file that
removed two TxPDOs from an EtherCAT slave was imported. cdsint wrote the PDO assignment (`RxTxPdo/*/Sm`) and
the sync-manager lengths, but the IDE never rebuilt the slave's input channel list. Import, build and export
all reported success; every input of every slave behind it then read from the wrong address (E-stop read as
pressed), and a later start died with `AccessViolation` in the EtherCAT stack.

Do, in this order of preference:

1. **Make it work**: when a `.device` file changes which PDOs are assigned, `import` produces the same device
   state as doing it in the IDE's (Expert) Process Data page: channel list rebuilt, channel keys renumbered,
   downstream addresses recomputed.
2. **If the scripting API cannot do 1** (prove it with probes, not by assumption): `import` must refuse the
   change. It applies nothing of the PDO assignment for that device, names the device in `failed_objects`
   with a message saying the change must be made in the Process Data page, and exits non-zero.
3. **Either way, a guard**: after applying a device, verify the slave's channel list is consistent with its
   assigned PDOs; if not, fail the import loudly. A silently inconsistent IO image must be impossible.

Not in scope: the stale-read bug (first export after an unsaved IDE edit shows old values); adding or removing
devices; anything under `plc`.

## 2. Decisions already made

| Decision | Choice | Why |
|---|---|---|
| Silent partial apply | Never acceptable | It produced a wrong IO image on a machine |
| Fallback if API cannot rebuild | Refuse + `failed_objects` + non-zero exit | Same as how unsupported values are reported today |
| Test target | Copies of two real projects, `--project` mode, DIADesigner-AX 1.10 | The failure was seen in this IDE |
| On-disk `.device` format | Unchanged | Compatibility floor in CLAUDE.md |

## 3. Facts you must know first

- Live implementation: `engine/` (IronPython side, runs inside the IDE) and `cdsint/` (CLI). Device code:
  `engine/device_params.py` (`read`, `render`), `engine/device_pass.py` (`find_changes`, `_compare_one`).
  Find the apply path yourself. Verify these names against the tree; they came from the installed 0.7.0.
- `docs/ethercat-research.md` sections 4 and 10: "choosing which PDO is assigned" was never tried through the
  API. Lines ~234-237 and ~519. Update that document with what you find.
- Fixtures (pristine copies, do not modify in place), in `C:/Users/qazsskevin/AppData/Local/Temp/cdsint-16/fixtures/`:
  - `enc2it_36B_gui.project`: slave `Slave_2` (ICP DAS EC4-ENC2IT, under `EtherCAT_Master_SoftMotion/Slave_1/Port 1`)
    with TxPDOs 1A00,1A01,1A02,1A10,1A11,1A12 and RxPDOs 1600,1601,1602,1610,1611,1612, set up **in the GUI**.
    Input SM length 36, about 296 `map c1/335544xx` lines.
  - `enc2it_40B_gui.project`: same project after the GUI changed it to RxPDOs 1600,1601,1610,1611 and TxPDOs
    1A00,1A01,1A05,1A10,1A11,1A15. Input SM length 40, about 330 map lines, output SM length 16.
  Both may differ in `map` bindings of a few channels (two Ch.1 bindings were missing in one of them); compare
  structure (channel keys, names, `%I/%Q` addresses, lengths), not the bound variable names.
- Known reader quirk: the first `export` after a device change can show old values; export twice and use the
  second. This quirk is real in `--target` mode; check whether it exists in `--project` mode and say so.
- `--noUI` needs `--profile`. `print` in UI mode goes to the IDE message window; probes must write files.
- These projects are saved by DIADesigner-AX 1.10; do not let any other IDE upgrade them.
- The project references a real controller address. You never go online, so it does not matter. Do not build
  with download.

## 4. Design

Yours to decide. Constraints: no special-casing by vendor or device type; the guard in goal 3 must be computed
from data the IDE exposes (assigned PDOs and their entries vs. the channel list), not from a table.

## 5. Stages and acceptance

- [x] **Stage 1: reproduce and build the reference**
  - [x] Export each fixture (copy first) to its own sync dir, twice. Keep the second exports as `ref36/` and `ref40/`.
  - [x] Acceptance: a written table (in this file, section 7) of Slave_2's input SM length, map-line count, and
        the `%I` address of the first channel of `Slave_3`, for both references.
  - [x] Reproduce the bug: on a copy of the 40B project, import `ref36`'s `Slave_2.device`. Acceptance: export
        (twice) shows SM length 36 but a map-line count and Slave_3 address that differ from `ref36`. Record the numbers.
- [x] **Stage 2: find out what the API can do**
  - [x] Probe scripts under `tools/` or the scratch root that try to make the IDE rebuild the channel list after
        a PDO assignment change (whatever the object model offers: methods on the device/connector/parameter
        set, an update/"apply" call, re-reading the device description, `system.commands`, ...).
  - [x] Acceptance: either a probe that turns the reproduced-bug project into one whose export equals `ref36`
        structurally, or a list of what was tried with the observed result of each.
- [x] **Stage 3: implement**
  - [x] Goal 1 if stage 2 found a way, otherwise goal 2. Goal 3 in both cases.
  - [x] Acceptance (if goal 1): copy of 40B + import of `ref36/Slave_2.device` -> second export is structurally
        identical to `ref36` for `Slave_2..Slave_6` (keys, names, addresses, lengths). And the reverse: copy of
        36B + `ref40/Slave_2.device` -> identical to `ref40`. `build` gives 0 errors in both.
  - [ ] (goal 1 reached, not applicable) Acceptance (if goal 2): the same two imports exit non-zero, name `Slave_2` in `failed_objects`, and a
        following export is structurally identical to the project's state *before* the import.
  - [x] Acceptance (goal 3): a test or scripted check where the guard fires on the stage-1 reproduction.
  - [x] Acceptance: a `.device` import that only changes `map` lines or a plain value still works exactly as
        before (run it on a copy; show before/after).
  - [x] Existing test suite green (`pytest`); new unit tests for whatever logic lives outside the IDE.
- [ ] **Stage 4: documents**
  - [ ] `docs/SPEC.md`, `docs/REFERENCE.md`, `docs/ethercat-research.md`, the skill text under `skills/`, and
        `CHANGELOG.md` say what `import` now does with PDO assignment changes and how to check the result.
  - [ ] Acceptance (needs a human): pushing the branch, opening the PR, installing the build into the user's
        IDEs. Do not do these. List them.

## 6. Report format

Last message: status of each stage in one line; commit list; the numbers table; which goal (1 or 2) was
reached and the evidence; what needs a human; what was not done; how to install this build for a trial
(command only, not run).

## 7. Open questions and rulings

Write decisions here as `Ruling: decision - reason - cost if wrong`. Stage-1 numbers go here too.

### Stage 1 numbers (DIADesigner-AX 1.10, `--project`, copies of the fixtures)

| | input SM length | output SM length | Number of Inputs | Number of Outputs | `335544xx` map lines (all map lines) | `Ch.1 Counter value` | Slave_3 first channel |
|---|---|---|---|---|---|---|---|
| `ref36` | 36 | 36 | 40 | 60 | 296 (596) | `c1/33554470`, %ID53 | DI0, %IX228.0 |
| `ref40` | 40 | 16 | 58 | 38 | 330 (464) | `c1/33554479`, %ID53 | DI0, %IX230.0 |
| 40B + import of `ref36/Slave_2.device`, 0.7.0 engine | 36 | 36 | 40 | 60 | **330 (464)** | **`c1/33554479`** | **DI0, %IX230.0** |

The import exited 1, but only because the file maps `c1/16777258`, a key that does not exist in the stale
40B channel list; every PDO and SM value had been written and the project saved. In the field every mapped
key happened to exist and it exited 0. Both exports after the import are identical.

Stale-read quirk: not seen in `--project` mode. The two exports of each fixture, and the two after the import,
are identical (only `sync_cache.json` differs).

Every other "plain" value that differs between the references: PDO `Sm` of 1602/1612, 1A02/1A12, 1A05/1A15;
SM and FMMU lengths; `Number of Inputs/Outputs` on both `c1/16777216`+`c1/33554432` and their copies
`c1/268435456`+`c1/536870912`. The remaining 500 or so are spelling (`false`/`False`, `16#1a00`/`16#1A00`,
entry `Default`), left by the description the GUI read.

### Stage 2 result: the IDE can rebuild the list (DIADesigner-AX 1.10, `--noUI`)

What works: inside the script connector's private `PerformWithWriteableCopy`, the EtherCAT plug-in's public class
`LoadSavePDOData`: `LoadDataFromConfig(list, connector)`, set `iSm` on the PDOs that move, `SaveMappingToConfig(list,
pdo, connector)` for each moved one. On a 40B copy it produced 36B: channels, keys, SM and FMMU lengths, all four
counts, nothing else. Mapped variables stayed with their entries. Saved, reopened in another process, exported twice:
Slave_3..6 identical to `ref36`; Slave_2 differs only in seven padding channels' names (`---` for empty), which come
from the entry `Name` values the file would also write.

| Tried | Result |
|---|---|
| plain value writes (0.7.0), save, reopen, build | channel list stays 40B (stage 1) |
| `device.update()` to the same identification | raises, on every slave, untouched ones too: Delta replaces the command and opens a window (`CustomizedUpdateDeviceCommand.ShowPromptDialog`, `NullReferenceException`) |
| `LoadSavePDOData.AddAndUpdateEntries` instead | channels rebuilt, but the `Sm` of 1A05/1A15 stays assigned: inconsistent |
| `SaveMappingToConfig` for one moved PDO only | rebuilds its direction only; one call per moved PDO is needed |
| `SaveMappingToConfig` for every PDO, nothing moved | no difference: idempotent |
| an exception inside the writable copy | nothing is committed: one transaction |
| downstream addresses in the same process | old until the project is saved or built; either recomputes them |

Guard candidate, measured on every device of both fixtures (16 with PDOs, 8 models): per connector and direction, the
assigned PDOs' entry bits equal the channels' bits, and each sync manager's length equals its PDOs' bytes. No false
alarm; fires on the stage-1 project (288 against 320, 288 against 128). Two drives (`i950_BS_STO`) have PDOs and no
channel: their module `Axis_A` carries the channels.

### Rulings

- Ruling: goal 1, through the plug-in's own class - it reproduces the GUI's result exactly and commits atomically -
  if a later plug-in renames it, import falls back to refusing (goal 2), by name.
- Ruling: "structurally identical" = per slave, the set of (channel key, name, address) and every length, `Sm` and
  count; spelling of other values is reported, not judged - the two fixtures spell 500 values differently - a real
  difference in one of those would be missed here, but import reads every value back anyway.
- Ruling: refused before anything is written: a device whose list does not match its PDOs already, one with no
  channels or no sync managers of its own (a modular drive or its module), a file whose lengths disagree with its
  own assignment, an entry `Size` change - none of these was shown to rebuild right, and the Process Data page does
  them - cost: a person has to open the IDE for them.
- Ruling: lengths and counts the rebuild computed are not overwritten from the file; a line that disagrees is named -
  writing it back would recreate the bug - cost: editing only `Sm` lines exits 1 until the named lines are fixed too.
- Ruling: the guard fails any applied device that is inconsistent afterwards, also when it was before - "never silent"
  is decision 1 - cost: a slave whose channels legitimately differ from its PDOs (none found) exits 1 on every import.

### Stage 3 result (DIADesigner-AX 1.10, `--project`, fresh copy per row, second export)

| Import into a copy of | File | Exit | Result |
|---|---|---|---|
| 40B | `ref36/Slave_2.device` | 0 | identical to `ref36` for Slave_2..6, values too; build 0 errors |
| 36B | `ref40/Slave_2.device` | 0 | identical to `ref40` for Slave_2..6, values too; build 0 errors |
| 40B | a station alias, one mapping added, one removed | 0 | the three lines changed and nothing else; every exported file identical to the 0.7.0 engine's result |
| 40B | 1A05/1A15 `Sm` to -1, lengths left at 40 | 1 | refused, names the 28 bytes; project unchanged |
| 40B | an entry's `Size` of an assigned PDO | 1 | refused; project unchanged |
| 40B | `Sm` and SM length edited, counts, FMMU length and map lines left | 1 | assignment landed and consistent, variables kept on their channels, each stale line named |
| the stage-1 project (stale, 0.7.0) | a station alias | 1 | the guard names 288 against 320 and 288 against 128 bits |
| the stage-1 project | `ref36/Slave_2.device` | 1 | the same, plus the mapping that has no channel |

Guard run read-only over all 21 devices: 36B none, 40B none, stage-1 project only Slave_2, repaired copy none.

- Ruling: a file whose map lines are still numbered for the old channel list writes no mapping at all - the rebuild has
  already kept every variable on its channel, and an old number can be another channel's key (the field failure's second
  half) - cost: after a hand edit of `Sm` lines the agent deletes the file and exports once to get the new numbers.
- Ruling: the guard runs on the devices an import applies, not on every device of every import - reading every channel's
  size costs each import a pass over 12296 channels on the large sample - cost: a stale list left by 0.7.0 on a device
  nobody edits is not found by import.

## 8. Takeover prompt

You are in `C:/Users/qazsskevin/Documents/repo/cdsint/.claude/worktrees/cdsi-16`, branch
`fix/16-pdo-channel-rebuild`. Read this ticket up to "Stages and acceptance", plus `CLAUDE.md`, `PRINCIPLES.md`
and `docs/ethercat-research.md`, then start at the first unchecked item. One stage done, tests green, commit.
Stop at anything that needs a human and list it. Write rulings back into section 7. Report per section 6.
