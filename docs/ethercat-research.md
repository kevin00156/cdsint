# Research: letting an agent change EtherCAT device configuration

> A research record, not a spec. Nothing here is implemented, and nothing here
> changes SPEC.md or PRINCIPLES.md; section 9 lists where a design would have
> to change them. Measured on 2026-09-24 against CODESYS 3.5.21.40
> (ScriptEngine 4.2.0.0), DIADesigner-AX 1.10 (ScriptEngine 4.0.0.0), and a
> CODESYS Control for Linux SL soft PLC in WSL. **The soft PLC has no
> EtherCAT slaves attached, and in the CODESYS project the EtherCAT master is
> disabled; every statement about the bus itself was measured only there.**
> Lenze was not tested.

The question: can `cdsint` (and so an agent) change an EtherCAT master and
its slaves safely, and how? Today `profiles/default.json` marks `device` and
`device_module` `disabled`, and `engine/object_kind.py` says they are "too
unstable for XML sync". That claim had no measurement behind it.

---

## 0. Answers in one table

| Question | Answer | Section |
|---|---|---|
| 1. What is unstable about native XML? | Not the export: it is byte-stable. The **import**: over an existing tree it never replaces, it adds a full renamed copy with new GUIDs and duplicated IO mappings (78 build errors), and it never asks the conflict handler. A single slave does not import at all. Deleting the tree first and importing restores everything exactly on CODESYS; **on Delta the tree cannot be deleted**, it is rebuilt from the network topology with every slave renamed | 2 |
| 1. GUIDs, IO mappings, parameters, ESI | Delete-then-import kept all 81 GUIDs, all 46354 parameter values and all 12296 IO channels. "Missing" device descriptions here were a version-string mismatch; those devices exported, imported and edited like the others | 2 |
| 2. What does ScriptEngine offer for devices? | Identification, enable/disable, add, insert, plug, unplug, update, remove, every parameter's value and each IO channel's variable, IO mapping CSV export and import, the device repository. Nothing EtherCAT-specific | 3 |
| 3. Which EtherCAT settings can a script change? | Master cycle time, DC sync offset and window, network name, autoconfig; slave addresses, DC settings, each startup SDO's fields, PDO entries. **A slave's DC cycle time cannot be set independently: the value written is replaced by the master's cycle** | 4 |
| 4. What does a changed device do to CRC and full download? | Offline: master cycle, a startup SDO value and a slave address each make the IDE judge "online change not possible"; an IO mapping change or a library addition leave online change possible | 5.1 |
| 4. When does a `Keep` login download by itself? | **Whenever the working copy differs from what was downloaded**, device configuration or code. IO mapping change: 8 online changes, running code changed, `Application.crc` unchanged. Master cycle change: full download, boot project rewritten, application left stopped | 5.2 |
| 5. Are IO mappings lost or moved on import? | Not by delete-then-import. Updating a slave to another revision kept every mapped variable but moved 11766 channel addresses (68 of them mapped) and **deleted the slave's SoftMotion axis**. The CSV import adds mappings but cannot remove one and skips unknown devices silently | 6 |
| 6. Delta 1.10 | Same API, same parameter ids, same behaviour through the API. Native XML is worse: deleting a master is undone at once by the EtherCAT topology object, with every slave renamed `Slave_N` | 7 |

---

## 1. How this was measured

Same method as `docs/library-manager-research.md` section 1: IronPython
scripts run as `--noUI --runscript`, one list of operations per process, on
copies in `%TEMP%\cdsint-work\`, closed without saving, prompts logged by key
(the logger was shown to work). Scripts are throwaway.

- **Projects.** `softplc_refactor.project` in CODESYS 3.5.21.40: one PLC, one
  EtherCAT master (`EtherCAT_2`, CODESYS "EtherCAT Master SoftMotion"
  4.10.0.0, `is_enabled = False`), 42 slaves (an RTU coupler with an analog
  module, two digital I/O modules, 38 X5 servo drives each with a SoftMotion
  axis), 81 device objects under the master. `Shm_2026.07.29.project` in
  DIADesigner-AX 1.10: the same machine, a Delta EtherCAT master (16F7 0190,
  enabled), 125 device objects in the project.
- **Snapshot.** For every device under the master: GUID, parent, children,
  identification, enabled, every parameter value (connector host parameters
  and device parameters, sub-elements included) and every IO channel's
  variable and IEC address. 81 devices, 46354 values, 12296 channels; 4 to 8
  seconds. Every "changed" and "unchanged" below is a diff of two snapshots.
- **Offline download judgement.** `application.is_uptodate` and
  `is_online_change_possible` after a build, on a copy of the bench working
  copy (`%TEMP%\cdsint-work\trace-impl`) together with the three files the
  IDE wrote at its last download (`.compileinfo`, `.bootinfo`,
  `.bootinfo_guids`), each case on a fresh copy.
- **Bench.** WSL `slitter-b`, runtime at 127.0.0.1:11741, reached as
  `plc trace` reaches it (`engine/plc_link.py`), `OnlineChangeOption.Keep`.
  What happened on the controller was read from its audit log
  (`/var/opt/codesys/.Audit.log`) and the modification time and CRC of
  `PlcLogic/Application/Application.{app,crc}`. Both bench runs were
  approved by the user beforehand, including the risk that they download.
- CPU from other sessions was 7 to 25% when checked. Timings below are
  indicative only.

---

## 2. Native XML

### 2.1 The export is large and stable

| Export | Size |
|---|---|
| master and everything under it, CODESYS | 83,343,341 bytes, 1,027,209 lines |
| the same, Delta | 83,294,723 bytes |
| one X5 slave with its axis | 2,130,138 bytes |

Every parameter is stored with its localised name, description, type and
default copied from the device description, which is where the size comes
from. The value itself is one element per parameter
(`<Single Name="Value" Type="string">1000</Single>` next to
`<Single Name="Identifier" Type="string">805326848</Single>`), and an IO
mapping is `<Single Name="Variable" Type="string">...</Single>` under the
channel. An agent can find and edit them.

Two exports in a row were byte-identical, on both IDEs, before and after
edits made through the API. The export takes 1 to 2 seconds.

### 2.2 Importing over the existing tree duplicates it

The unchanged export, imported back into the PLC device through
`engine/native_import.py` (the handler that answers every conflict with
`replace`):

| | Before | After |
|---|---|---|
| IDE's answer | — | `ok`, no failures |
| handler calls | — | `conflict` 0, `progress` 81, `skipped` 0 |
| project tree | `EtherCAT_2` with 80 devices | `EtherCAT_2` unchanged, plus `EtherCAT_2_1` with `RTU_1_1`, `X5_7SEtherCAT_1_1`, `Axis_1_1` ... all with new GUIDs |
| build | 0 errors | **78 errors**: "Existing variable Application.GVL_IO.aPhysicalDIBytes[0] is mapped multiple inputs." and the like |

The IDE never offers a device to the conflict handler; it renames and adds.
This is what the old repository's changelog called "tree reconstruction"
(v1.6.1, 2026-02-26), measured. `cdsint import` would report such a run as
successful: the handler saw no failure.

### 2.3 A single slave does not import

Exporting `X5_7SEtherCAT_1` (with its axis) and importing it into the master
failed inside the EtherCAT plug-in: `InvalidOperationException: Collection was
modified` in `FixedPhysicalAddresses.CheckPhysicalAdresses`, reported through
the handler's `progress`, then `skipped(['Axis_1_1'])`, result `skipped`.
Nothing was added. `engine/native_import.py` would raise with that text, so
the failure is loud, but a per-slave file is not a way in.

### 2.4 Delete first, then import, restores exactly (CODESYS)

`remove()` on `EtherCAT_2`, then import of the export into the PLC device:

| Check | Result |
|---|---|
| GUIDs of the 81 devices | all identical |
| parents, children order | identical |
| 46354 parameter values | identical |
| 12296 IO channels (variable, auto flag, address) | identical |
| IO mapping CSV export | byte-identical |
| export afterwards | differs only in the 81 `Timestamp` lines |
| build | 0 errors |
| time | import 21 to 31 s |

Between the two calls the project has no master; the axes the code uses are
gone and a build gives "Identifier 'Axis_1' not defined". A failed import
there leaves it so; this happened once in this research, from a file the
probe itself held open.

### 2.5 An edited export imports, and the plug-in recomputes

The export was edited as text (master `MasterCycleTime` 1000 to 2000, the
first slave's DC sync0 cycle 1000 to 2000, one IO channel's variable to a new
name), then deleted and imported:

- The master cycle landed.
- **All 42 slaves' DC sync0 and sync1 cycle times became 2000**, not only the
  edited one. Section 4.2 shows why.
- The IO channel landed, and the build failed with one error:
  "Invalid application <xEcatProbeErr1> in mapping <xEcatProbeErr1>". The same
  mapping made through the API compiled (section 4.1); a new-variable mapping
  written in the XML needs something the text alone does not carry.

### 2.6 Device descriptions (ESI)

CODESYS warned on every open: "Device description for 'RTU_1' is missing",
likewise `AIO_2`, `DIO_1`, `DIO_2`. The device repository does hold those
modules, under the same ids, but with versions like `Revision=16#00100000`,
while the project names `1.0.0.0` and `1.0.0.1` (the versions Delta's own
repository uses). So "missing" here is a version mismatch, not an absent
file. Those four devices were read, written through the API, exported and
imported exactly like the others, and their parameters are all in the XML.
`update()` to the installed version worked (section 6.2). A device whose
description is absent altogether was not available to test.

---

## 3. What ScriptEngine offers for devices (4.2.0.0, by reflection)

There is no EtherCAT-specific script driver: `DeviceEditorEtherCAT` is a
plug-in with no scripting face. Everything goes through the generic device
object.

| Want | Member | Tried |
|---|---|---|
| identity | `get_device_identification()` (type, id, version), `get_module_identification()` | yes |
| enable, disable | `enable()`, `disable()`, `is_enabled()` | disable, yes |
| add a child | `add(name, type, id, version, module)`, `insert(name, index, ...)`, `plug(...)`; also on explicit connectors | add, yes |
| remove | the generic `remove()` | yes |
| change model or revision | `update(type, id, version, module)` | yes |
| detach | `unplug()` | no |
| parameters | `device_parameters`, `connectors[i].host_parameters`; each element: `identifier`, `visible_name`, `value {get;set}`, `default_value`, `offline_access_rights`, `type_string`, sub-elements by iteration | yes |
| IO mapping | element `.io_mapping`: `variable {get;set}`, `automatic_iec_address {get;set}`, `manual_iec_address {get;set}`, `default_variable`, `mapping_creates_variable` | yes |
| IO mapping as a file | `export_io_mappings_as_csv(path)`, `import_io_mappings_from_csv(path)`, on the device and on explicit connectors | yes |
| bus cycle, IO application | `driver_info`: `set_bus_cycle_task`, `io_application`, `update_ios_while_in_stop`, ... | read only |
| device repository | `device_repository.get_all_devices()`, `import_device`, `remove_device` | listing only |
| online parameter access | `read_online_value`, `write_online_value` | no |

---

## 4. EtherCAT settings through the API

### 4.1 What was written, and what it did

Each row is one `value = ...` in a process that had read every parameter once
before (see 8.1), followed by a snapshot of all 81 devices:

| Setting | Written | Read back | Changed elsewhere |
|---|---|---|---|
| master `MasterCycleTime` | 1000 to 2000 | 2000 | nothing |
| slave `DC sync0 cycletime` | 1000 to 4000 | **2000** | the same slave's sync1 cycle, also to 2000 |
| RTU (no matching ESI) `DC sync0 cycletime` | 1000 to 3000 | **2000** | its sync1, to 2000 |
| slave startup SDO "Op mode" `Value` (0x6060) | 6 to 8 | 8 | the compound's summary string |
| slave `Physical Address of the Slave` | 0 to 1001 | 1001 | nothing |
| slave "Error Code" channel variable | existing GVL variable to `xEcatProbeErr1` | new name | nothing; build 0 errors |

On Delta, the master cycle, the X5 slave's DC cycle, the startup SDO and the
IO channel were written the same way, with the same results; the RTU and the
slave address were not tried there.

### 4.2 A slave's DC cycle follows the master

Writing a slave's DC cycle is accepted without an error and replaced by the
master's cycle (times the sync factor, `'x 1'` here). The slaves are not
updated by the master write itself: after the master went to 2000, all 42
slaves still read 1000. They were recomputed when the tree was exported and
imported again (the 40 not written by hand changed on import; the two
written by hand were already at 2000). So between an API write of the master cycle and the next event that
makes the plug-in re-check the bus, the project holds slaves that disagree
with their master. What the compiled configuration contains in that state
was not examined.

For a tool this means: read back after every write, and treat a read-back
that differs as a failure, by name.

### 4.3 What the parameter list covers

Everything below is a parameter with `offline_access_rights = ReadWrite`
unless noted; section 4.1 is what was actually written.

| Master (connector 2) | Slave (connector 1) |
|---|---|
| `MasterCycleTime`, `SyncOffset`, `DCSyncInWindow`, `SyncWindowMonitoring`; `DCMode` has no access rights | `DC enable`, `DC sync0/1 enable`, `cycletime`, `factor` |
| `Autoconfig`, `SlaveAutorestart`, `MasterUseLRW`, `SlaveCheckMode` | `Physical Address`, `AutoIncr Address`, `StationAlias`, `CheckVendorID`, `CheckProductID` |
| `NetworkName`, `SelectNetworkByName`, `CompareNetworkName`, second adapter settings | the state-machine timeouts |
| | startup SDOs: `Number of SDO`, then one compound per entry with `Index`, `Subindex`, `Value`, `Size`, `Transition`, `AbortIfError`, `CompleteAccess`, `JumpToLine`, `Line` |
| | PDOs: `PDOAssign`, `PDOConfig`, one `RxTxPdo` compound per PDO (`Index`, `Name`, `Sm`, `Mandatory`, `Fixed`, `NumberofEntries`, ...), its `Exclude` list and entries; sync managers, FMMUs |
| | SoftMotion axis (the `Axis_N` child): scaling, software limits, drive id |

Adding or deleting a startup SDO entry, or choosing which PDO is assigned, is
not a single value in this list, and neither was tried (section 10).

---

## 5. Download: what the IDE judges, and what a `Keep` login does

### 5.1 Offline judgement

Each case on a fresh copy of the bench working copy with its three download
files, one change, then build:

| Change | `is_uptodate` | `is_online_change_possible` |
|---|---|---|
| none | true | true |
| POU: an empty statement appended | true | true |
| master `MasterCycleTime` 1000 to 2000 | false | **false** |
| slave startup SDO value 6 to 8 | false | **false** |
| slave physical address 0 to 1001 | false | **false** |
| IO channel mapped to a new variable | false | true |
| library `Util, 3.5.19.0` added | false | true |

The empty statement is not a code change the compiler sees; it is here only
to show that editing a POU object by itself moves nothing.

### 5.2 On the controller

Two runs, each on a fresh copy of the bench working copy with its download
files, the controller holding exactly that copy's program beforehand (CRC
2852105E, code identity 17d038a4, data identity 2b9658e1, running). One
change in memory, build, `Keep` login, logout, nothing saved.

| | IO channel remapped | Master cycle changed |
|---|---|---|
| offline judgement | online change possible | online change not possible |
| audit log after `Login successful` | `OnlineChange started`, then 8 × `OnlineChange successful, create bootproject: 0`, the last with code 7255d156, data 12c182cd | `ReinitApplication started`, `Reinitialize for Download successful`, then `Download successful, create bootproject: 1` (repeated), code bfc4df91 |
| application after | running | **stopped** |
| `Application.app`, `.crc` on the controller | unchanged, CRC 2852105E | rewritten, CRC F1FBBC62 |
| local `.compileinfo` | rewritten | rewritten |
| local `.bootinfo`, `.bootinfo_guids` | unchanged | rewritten |
| prompts | none | none |

Neither asked anything. **`OnlineChangeOption.Keep` is not "log in and change
nothing" when the project's device configuration differs from the
controller's**: it applies the difference, by online change when it can and
by full download when it cannot.

The same holds for code. Trace-research 12.1 recorded cases E and F (a
program edited in memory, download files present) as "not downloaded"; read
again, the controller's audit log shows each of those logins followed by an
online change, and 12.1 has been corrected. The trace object `plc trace`
creates is not a difference: 31 logins with it and nothing else changed made
no online change (trace-research 12.1).

After the IO run the controller ran code the boot project does not contain,
while `Application.crc` still matched cdsint's download record, and the
header of `Application.app` still matched `.bootinfo_guids`. Both checks
`plc trace` then made before logging in would have passed. A third,
`is_uptodate`, now stands before the login (SPEC 6.8 step 2): offline it was
false for every change of 5.1 that is a real change and true for an
unchanged copy with `cdsint_trace` in memory, without a build.

After the cycle run the working copy's `.project` (never saved, cycle 1000)
and its download files (cycle 2000) no longer describe the same program.

The bench was restarted between the two runs, with the user's approval, to
load the original boot project again. It was left as the second run left it:
cycle 2000 boot project, CRC F1FBBC62, application stopped.

### 5.3 The CRC

A device change moves the controller's `Application.crc` only when it is
downloaded in full (5.2). Computing an offline CRC to predict it is not an
option: `docs/trace-research.md` and `engine/plc_crc.py` already record that
the offline boot application's CRC is not comparable to the controller's,
and this round found a second reason. `create_boot_application(path, False,
False)`, whose second argument is `update_compile_info`, **rewrote the
`.compileinfo` and deleted and rewrote the `.bootinfo` files** beside the
project when the application needed a full download (master cycle case); with
no change it left them alone. Those are the files a `Keep` login trusts
(trace-research 12.1). cdsint does not call it offline today; nothing should.

---

## 6. IO mappings

### 6.1 Across a native round trip

Delete-then-import (2.4) kept all 12296 channels exactly. Import over the
existing tree (2.2) kept them too, and then mapped every variable twice.

### 6.2 Across structural changes (API)

| Change | Mapped variables (90 before) | Channel addresses moved | Other effects |
|---|---|---|---|
| `update()` X5_1, revision 1 to 2 | 90, none lost or changed | **11766**, of which 68 mapped | **`Axis_1` deleted** (81 to 80 devices); build: "Identifier 'Axis_1' not defined" |
| `update()` DIO_1 to the installed ESI version | 90 | 0 | 13 more parameters on the device |
| `add` an X5 at the end of the bus | 90 | 0 | no axis created |
| `remove` X5_38 (with its axis) | 90 | 150 (the device added after it) | — |
| `disable()` X5_37 | — | — | build unchanged |

Every mapping in this project uses an automatic address, and the exported
code (227 files) contains no `AT %I`/`%Q` and no direct `%I`, `%Q` address, so
the moved addresses change nothing here. In a project that addresses I/O
directly, a revision update or a removal in the middle of the bus silently
points that code at other data.

### 6.3 The mapping CSV

`export_io_mappings_as_csv` on the master wrote every channel of every device
under it: 12299 lines, 90 with a variable. Its header says to change only the
first, third or fourth column. Imported back after three edits:

| Edit in the CSV | After `import_io_mappings_from_csv` |
|---|---|
| a variable written into an empty first column | mapped |
| a mapped row's first column emptied | **still mapped** |
| a row naming a device that does not exist | **ignored, no error, no message** |

So the CSV adds; it cannot unmap, and bad rows vanish. As a disk format it
would need cdsint to export again and compare.

---

## 7. DIADesigner-AX 1.10

- **API**: the device interfaces are the same as 4.2.0.0 except
  `IScriptDriverInfo2` and `IScriptDeviceInstance` (library-manager-research
  section 7). Parameter identifiers are the same numbers
  (`805326848` is `MasterCycleTime` on both masters). Four of the writes of
  4.1 gave the same results (4.1 says which), the tree was unchanged
  afterwards, and two exports after them were byte-identical.
- **Native XML**: the export is stable. The import is not usable:
  - `remove()` on `EtherCAT_2` returned normally, and at the end of the call
    the master and all its devices existed again, with their GUIDs, but every
    slave was renamed `Slave_1`, `Slave_2`, ... and reordered. Delta keeps the
    bus in objects of its own (`Hardware Configuration`,
    `Network Configuration`, `EtherCAT Topology`) and rebuilds the tree from
    them. None of those types is in `profiles/default.json`.
  - Importing the export then added a renamed copy (`EtherCAT_1`, `RTU_2`,
    `DIO_3`, axes renumbered from `Axis_39`), and the build reported
    "The network name "ECAT" is duplicated." and duplicated mappings. A
    second import raised "Object reference not set to an instance of an
    object".
- **ESI**: no "description missing" warnings on Delta; the project's versions
  are Delta's own.

---

## 8. Other findings a design has to carry

### 8.1 The first write after opening can half-fail

In a process that had not read the device's parameters yet, the first write
raised "Attempt to write an object with read-only access. (Object: '')".
Reading the value back returned the new value. For the startup SDO and the
slave address, the build afterwards still said `is_uptodate = true`, which
the same change made after a full read of the parameters did not (5.1); for
the IO channel it made no difference. Seen on the original project and on the
bench copy, with and without download files, so it is not caused by either.
A second write in the same process never raised. Which read is enough was
not narrowed down; reading every parameter once (the snapshot) was enough
every time.

### 8.2 `update()` removes children the new description does not have

The SoftMotion axis under a drive is a child device. Updating the drive's
revision deleted it (6.2), and with it the axis the code refers to.

### 8.3 The device profile switch is loaded with a trap

`sync_direction` is a setting a user can edit without a code change, and
flipping `device` to `bidirectional` today would put the whole-tree import of
2.2 into `cdsint import`: `ok`, and a duplicated bus.

---

## 9. Where this conflicts with SPEC.md and PRINCIPLES.md

1. **SPEC 6.8 step 4: "`Keep` means log in and change nothing; the
   application is never downloaded."** Measured false when the working
   copy's device configuration differs from the controller's (5.2): online
   change or full download, no prompt. `plc trace` (unmerged, branch
   `trace-research`) inherits this: a working copy whose I/O or device
   parameters were edited and not downloaded passes both of its pre-login
   checks and is then applied to the controller by the login. Resolved on
   the same branch: `plc trace` now refuses when `is_uptodate` is false, and
   SPEC 6.8 says what `Keep` does.
2. **SPEC 2, non-goal "No online change".** A `Keep` login made one (5.2).
   cdsint does not ask for it, but a command of cdsint's would cause it.
3. **SPEC 6.6, what `MATCH` means.** After the online change of 5.2 the
   controller ran different code and `Application.crc` still matched. `MATCH`
   is about the boot application on the controller's disk, not about what is
   running; SPEC 6.6 should say so.
4. **`profiles/default.json` and `engine/object_kind.py`.** "Too unstable for
   XML sync" is now measured: import duplicates (CODESYS, Delta), a slave
   alone fails, delete-then-import is exact on CODESYS and impossible on
   Delta. The comment should say which; and 8.3 argues the direction should
   not be user-switchable for `device` while the XML path is what switching it
   would enable.
5. **SPEC D13 and PRINCIPLES 6.** The duplicate import reports `ok` with no
   failure (2.2); the CSV import drops unknown rows silently (6.3); a DC
   cycle write is silently replaced (4.2); a first write can half-fail (8.1).
   Every one needs a read-back by cdsint to be caught.
6. **PRINCIPLES 5, disk is the truth.** A device file that cdsint applies
   through the API can own values and mappings, not the structure: adding,
   removing, updating and reordering devices change addresses, drop axes
   and, on Delta, are owned by the topology object. The rule would need to
   say the file owns a device's settings and not its existence.
7. **SPEC D8, what needs permission.** Today only commands that touch the
   PLC need the `plc` list. A device change is offline, but 5.1 shows it
   decides whether the next download is a full one, which stops the machine.
   Whether that deserves a flag is a decision, not a measurement.
8. **SPEC 4.5, the disk format.** A device settings file is a new file type
   in the sync folder.

---

## 10. Interface draft

Following the measurements: no native XML for devices; the API with a
read-back; settings and mappings only, not structure; and say out loud when a
change will need a full download.

### Files

Per master, beside where its XML would have been:

```
<sync>/CODESYS_Control_for_Linux_SL/EtherCAT_2.ethercat.txt
```

```
# cdsint EtherCAT settings. Only ReadWrite values; one line per value.
[EtherCAT_2]  64|0000 1002|4.10.0.0
c2/805326848          = 1000        # MasterCycleTime
c2/805459456          = 20          # SyncOffset
[EtherCAT_2/X5_7SEtherCAT_1]  65|766_0001000000000001|Revision=16#00000001
c1/1074855936         = 0           # Physical Address of the Slave
c1/1627394048/Value   = 6           # startup SDO 0x6060:00 Op mode
map c1/33554435       = Application.GVL_Axis.aDriveErrorCodes[1]   # Error Code, %IW5
```

- Sections are device paths with the identification the device must have;
  a mismatch is refused, not "fixed" with `update()` (8.2, 6.2).
- Keys are connector and parameter identifiers, which are the same on both
  IDEs (7); the visible name is a comment for the reader.
- Which values are written is a decision to take (section 11): all
  ReadWrite leaves is about 46000 lines for this project; values that differ
  from the description's default are not a small set either (110 of 148 on
  one X5, mostly compounds whose default is empty).

### Import

1. Refuse if the tree's devices (paths, identities) differ from the file's
   sections: structural changes are the IDE's job, named in the refusal.
2. Read every parameter once (8.1), diff against the file.
3. Write the differences through `value` and `io_mapping.variable`.
4. Read everything back. Anything not as written, including a DC cycle the
   plug-in replaced (4.2), is in `failed_objects` by device and parameter.
5. Report `is_online_change_possible` after the build: "this change needs a
   full download" is information the caller must see before any `plc`
   command (5.1, 5.2).

### Export

Writes the same file from the IDE. Nothing structural is exported beyond the
section headers, so a device added in the IDE shows up as a new section and
one removed disappears; neither is applied back.

---

## 11. Not verified

- **Real EtherCAT slaves.** The bench has none, and the CODESYS project's
  master is disabled. Nothing here says what a changed setting does on a
  running bus.
- **What the compiled configuration holds** while slaves disagree with the
  master's cycle after an API write (4.2).
- **`Keep` with the other changes of 5.1** (startup SDO, slave address,
  library): only the IO channel and the master cycle were taken to the
  controller.
- **PDO assignment and adding or deleting startup SDO entries**: not single
  values in the API; where the selection is stored was not found, and neither
  was tried through the API or the XML.
- **A device whose description is absent altogether** (2.6 was a version
  mismatch).
- **Delta: `update`, `add`, `remove` of a slave, the CSV import, the
  offline download judgement and the bench**: not run on Delta; only the API
  writes of 4.1 and the native round trip were.
- **Delta's `Network Configuration` and `EtherCAT Topology` objects**: what
  they hold and whether they can be edited.
- **Lenze.**
- **The interface draft**: not implemented, so its round trip is not
  measured.
- **Why the first write half-fails** (8.1), and whether it also happens to a
  library or a POU.
