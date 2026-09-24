# Research: recording a CODESYS trace unattended (`cdsint plc trace`)

> A research record, not a spec. Nothing here is implemented, and nothing here
> changes SPEC.md or PRINCIPLES.md; section 9 lists where the design would have
> to change them. Measured on 2026-09-23 against CODESYS 3.5.21.40
> (ScriptEngine 4.2.0.0) and a CODESYS Control for Linux SL soft PLC running
> in WSL. Other IDEs in the compatibility matrix (SPEC 7) were not tested.

The goal: an agent names some variables, and cdsint logs in to a controller,
records them for a while and hands back a file, with nobody at the IDE and no
dialog left open.

---

## 0. Answers in one table

| Question | Answer | Section |
|---|---|---|
| A. Can a headless run record without losing samples? | Yes, but only by enlarging the controller-side buffer, which the script API does not expose. Reached through a private method; 100% of samples on a 1 ms task | 2 |
| Can a trace object be created for one run and thrown away? | **Yes.** Created in memory and never saved, it logs in with `OnlineChangeOption.Keep`, records, and leaves the controller's application files untouched. It fails if another IDE is logged in to the controller at the same time | 3 |
| B. Trigger and record condition from a script, headless | Settable from the script; whether they take effect headless was **not measured** (section 4) | 4 |
| C. What can `save()` write? | `.csv`, `.txt`, `.trace` (native, UTF-16 XML with data), `.xml` (same bytes as `.trace`) | 5 |
| C. Does ck_cutter's loader need changing? | No: it reads a saved `.trace` as it is. It drops the timestamps, so it cannot check for gaps | 5 |
| D. Do trace objects upset `discover`, `export`, `verify`? | No. They are recognised as kind `trace`, exported as `<name>.trace.xml` when `export_xml` is on, and survive `verify` | 6 |
| D. Does a GUID have to be added to `profiles/default.json`? | No, it is already there | 6 |
| D. Can an edited trace XML be imported? | **Not today.** Every edited native-XML object fails to import headless; a cdsint bug, not a trace one (section 6.3) | 6 |

---

## 1. How this was measured

The bench was one soft PLC in WSL, reached through its own gateway by IP and
port. The project was a copy of a real machine project of about 400 objects
with a 1 ms task and a 4 ms task. Every experiment was an IronPython script
started as `CODESYS.exe --noUI --runscript=...`, the same way
`cds/ide/headless.py` is started. Each run changed one thing, so a difference
in the result belongs to that one change. The scripts are throwaway and are
not in this repo; the code that matters is quoted below.

Two tools were used besides the IDE:

- **.NET reflection over the shipped assemblies**, to see what the script API
  really has. The scripting wrapper for traces is
  `PlugIns/<guid>/4.2.0.0/ScriptDriverTraceObject.plugin.dll`; the trace object
  itself is `TraceObject.plugin.dll`.
- **A sample checker** that reads a CSV and, for each variable, compares the
  number of samples with what the task period says there should be, and lists
  every gap between two timestamps longer than 1.5 periods.

No online ScriptEngine documentation was used. Where this document says the
API "has" or "lacks" something, the source is the reflection listing of the
4.2.0.0 assemblies.

---

## 2. A. Losing samples

### 2.1 Why samples are lost

A trace object has two buffers:

| Buffer | Where | Member | Default |
|---|---|---|---|
| Ring buffer the controller fills every task cycle | controller | `TraceRecord.uiBufferEntries` (the CSV's `BufferEntries`) | 100 |
| What the IDE keeps per variable | IDE | `TraceSettings.uiBufferPerVariable` | 10001 |

The IDE fetches from the controller only now and then. Measured on the
baseline run, the samples arrive in blocks of 100 followed by holes of 80 to
180 ms. The controller's ring holds 100 samples. On a 4 ms task that is
400 ms of history, which outlasts every hole, so nothing is lost. On a 1 ms
task it is 100 ms, which does not:

| Run (3 s, defaults) | Samples | Expected | Complete | Gaps | Longest gap |
|---|---|---|---|---|---|
| 4 ms task | 657 | 657 | 100.0% | 0 | 4 ms |
| 1 ms task | 761 | 2606 | 29.2% | 14 | 179 ms |

This is the same 28 to 30% ck_cutter's prototype saw. Polling
`get_packet_state()` every 20 ms, which the prototype tried, does not help:
the IDE-side buffer is also why its long recordings stopped at exactly 10000
samples.

### 2.2 What the script API offers

`ScriptTraceObject` has no member for either buffer. `ScriptTraceEditorObject`
has no `upload()` or any other way to ask for the data sooner; its members are
`download`, `start`, `stop`, `save`, `reset_trigger`, `get_packet_state`,
`get_trigger_state`, `get_trigger_timestamp`, `get_trace_start_timestamp`,
`get_trigger_startdate`, `get_online_traces`, `upload_to_device_trace` and
three `is_*` properties.

`ScriptTraceObject` does carry two private methods, `GetReadable()` and
`PerformWithWriteableCopy(Action<ITraceObject7>)`, and the object behind them
has both buffers. Through reflection:

```python
m = clr.GetClrType(type(api)).GetMethod("PerformWithWriteableCopy", NonPublic | Instance)
def change(o):
    o.TraceSettings.bOverrideRTSBufferSize = True    # without this the ring size is computed
    o.Record.uiBufferEntries = 5000
    o.TraceSettings.uiBufferPerVariable = 1000000
m.Invoke(api, Array[object]([clr.GetPythonType(m.GetParameters()[0].ParameterType)(change)]))
```

An object found by name (`app.find(...)`) is a plain script object, not a
`ScriptTraceObject`; the private
`CreateScriptTraceObject(projectHandle, guid)` turns one into the other.

### 2.3 Result

| Run (1 ms task) | Samples | Recorded span | Complete | Gaps over 1.5 periods | Longest interval |
|---|---|---|---|---|---|
| Ring 5000, IDE 1000000, ms resolution, 3 s | 2813 | 2.81 s | 99.9% | 4 (2 to 3 ms) | 3 ms |
| Ring 5000, IDE 1000000, µs resolution, 4 s, 3 variables | 3743 per variable | 3.74 s | 100.0% | 0 | 1.354 ms |
| Same, on a trace object created for the run (section 3), 2 variables | 3730 per variable | 3.74 s | 99.8% | 11 | 3.805 ms |

The small gaps (2 to 4 ms on a 1 ms task) are a different thing from the
100 to 180 ms holes of section 2.1. The bench is a non-realtime VM, and a
task that starts late or skips a cycle leaves no sample for that cycle; the
trace did not lose it, there was nothing to record. Timestamps alone cannot
tell the two apart. What they can tell apart is the size: a hole caused by
the ring buffer is at least as long as the IDE's fetch interval, and jitter
is a few periods.

The acceptance line in the brief was "3 s of recording, at least 2900 rows".
A 3 s wall-clock window records about 2.8 s of data, because starting and
stopping take a little of it, so the literal count is not reached even with
nothing lost. The measure that means "nothing lost" is completeness over the
recorded span plus the absence of gaps, and that is what section 8 proposes
as the exit criterion.

**Risk.** The buffer is reached through a private method. It can change or
disappear in any IDE release, and Lenze and Delta builds were not checked.
Section 9 lists this.

---

## 3. A trace object that lives for one run

### 3.1 It works, and the controller's application is not touched

A trace object is a child of the application, so creating one makes the
project differ from what the controller runs. That does not stop a login
that changes nothing. Measured with no other client connected to the
controller:

| Run | Login with `OnlineChangeOption.Keep` | Recording |
|---|---|---|
| Control: project as downloaded | succeeds | — |
| New trace object created in memory, never saved | succeeds | 4 s on the 1 ms task, 3730 samples per variable, 99.8% (section 2.3) |

After both runs the project file's SHA-256 was unchanged, and on the
controller `PlcLogic/Application/Application.app` and `Application.crc` still
had the modification time of the last `plc download`. The runtime's audit log
shows no download in between. The trace itself is sent by the trace editor's
own `download()`, which is not an application download.

ck_cutter's prototype saw a full download after creating trace objects
because it logged in with `OnlineChangeOption.Never`, which means "download
whatever differs". `Keep` means "log in, change nothing".

### 3.2 It fails when someone else is logged in

An earlier run of the same experiment was refused with:

```
A login is currently not possible. The user 'kevin' is already logged in from
host '...' via 'CODESYS'.
A login in read-only mode is also not possible because the project contains
changes that do not correspond to the state of the application on the device.
```

Another IDE was logged in to the same controller at the time (section 7.2).
The runtime allowed only one read-write client, so the IDE fell back to a
read-only login, and a read-only login refuses a project that differs from
the controller. A trace command therefore fails whenever an engineer's IDE,
or another tool, is logged in to the controller. The refusal has to say that,
not "project differs from controller", or the reader will go and download for
nothing.

### 3.3 Reconfiguring an existing trace object also works

With two trace objects already in the downloaded project, replacing the
variable list, switching the resolution and enlarging both buffers in memory
all kept `Keep` working, and the CSV held the new variables. This is not
needed by the design (a throwaway object does the same job), but it says the
same thing from the other side: trace settings are not part of what the
login compares.

### 3.4 A device trace cannot take variables

A trace created under the device node instead of the application is not part
of the application, and a `Keep` login with one in memory succeeds. But the
script API refuses to add variables to it ("This operation can not be
performed on a DeviceTrace"); it can only fetch the controller's own traces
(`CpuCoreLoad`, `PlcLoad`, `Redundancy` on this runtime). Dead end.

---

## 4. B. Trigger and record condition

What was established, offline, on an existing trace object:

- `trigger_variable`, `trigger_edge` (`Positive`, `Negative`, `Both`),
  `trigger_level`, `post_trigger_samples`, `trigger_enabled`,
  `record_condition` and `every_n_cycles` are all settable.
- `trigger_level` takes a number or a numeric string and converts it to the
  trigger variable's type (`"5000"`, `5000` and `5000.0` all became `5000L`
  for a `UDINT`). An IEC literal (`UDINT#5000`) is refused. On a `BOOL` trigger
  variable, `True` is refused; how a boolean trigger is meant to be expressed
  is open.
- **Nothing is validated when it is set.** A variable that does not exist, a
  task that does not exist and a condition naming a missing variable were all
  accepted without complaint. See 7.3.
- A trigger left half set (variable and edge set, level refused) makes the
  next `start()` fail with "Cannot start the trace in the current state".

What was **not** measured: whether a trigger or record condition actually
fires under `--noUI`. The bench application was idle, every variable in it
was constant, and the run that would have added a counter to test with
needed another application download, which the session's permission check
refused. Until that run exists, section
8 leaves both fields out of the job.

An external stop signal (the prototype's `.stop` file) is not an API question:
the recording loop decides when to call `stop()`. Its cost is a file protocol
between the command and whoever writes the file.

---

## 5. C. What `save()` writes

`editor.save(path)` picks the format from the extension:

| Extension | Content |
|---|---|
| `.csv` | `;`-separated, a header block of `key; value`, then one block per variable (`N.Variable; name` plus display settings), then rows `; <timestamp>; <value>` |
| `.txt` | a title line, the project path, then columns `Timestamp(ms) <var> ...` |
| `.trace` | UTF-16 XML with BOM: the full trace configuration plus `<TraceVariable VarName=...><Values>...</Values><Timestamps>...</Timestamps>` |
| `.xml` | byte-for-byte the same as `.trace` |

Things a reader of these files has to know:

- **The timestamp unit is not fixed.** It follows the trace object's
  `resolution`: milliseconds by default, microseconds if set. The CSV says
  which only through its `Flags` line (16 for ms, 32 for µs); the `.txt`
  header names the unit; the `.trace` file has `MicroSeconds` in its settings.
  ck_cutter's prototype set microseconds, which is why its timestamps looked
  1000 times larger than these.
- **Timestamps are relative** to the start of the trace, not wall-clock time.
- The CSV header lines were the same set, in the same order, in every run.
  One run is not proof of stability across IDE versions.
- ck_cutter's `tools/trace/trace_lib.py` read a `.trace` from `save()`
  correctly (761 values from the 761-sample run). It keeps only the values.
  A gap check needs the timestamps, so if ck_cutter wants one, the loader
  should also return `<Timestamps>`.

The `.trace` file is the one to keep if only one is kept: it carries the
configuration that produced the data, so a result can be read back without
the job file that asked for it.

---

## 6. D. Trace objects and the existing commands

### 6.1 Recognised, and exported only on request

The trace type GUID is already in `profiles/default.json` (`"trace"`) and
`trace` is already in `XML_KINDS` in `engine/codesys_constants.py`. Measured
on two copies of the same project:

| | Without trace objects | With two trace objects |
|---|---|---|
| `discover` total | 402 | 404 |
| kinds | 22 | 23 (`trace`: 2) |
| `unknown` | empty | empty |

`export` with `export_xml` off wrote 227 files and no trace; `failed_objects`
was empty. With `export_xml` on it wrote 232 files, among them
`Application/T_slot1.trace.xml` and `Application/T_slot4.trace.xml`
(about 10 KB, 154 lines of ASCII XML each). `verify -y` on that folder
(import, export, compare, build) exited 0.

The exported XML is readable enough for an agent to edit: the variable name,
task, `BufferEntries`, `OverrideRTSBufferSize`, `BufferPerVariable`, trigger
variable, `Condition`, `EveryNCycles` and `MicroSeconds` are each a named
element.

### 6.2 Opening without saving leaves the project file alone

After every run that opened the project, changed trace objects in memory and
closed it without saving, the `.project` SHA-256 was unchanged. The IDE does
write two `.opt` files (per-user view options) beside the project on the first
open; every `--project` command already does that.

### 6.3 An edited native XML object cannot be imported headless (a cdsint bug)

Editing `T_slot1.trace.xml` (ring buffer 100 to 5000, one variable renamed)
and running `import -y` failed:

```
Failed: 1 (Identical: 228) -- 1 object(s) could not be handled: T_slot1
... does not contain a prompt handling for the message key 'PromptImportConflict'
```

`PromptImportConflict` asks which existing objects to overwrite; it is a
multiple-choice prompt, and `--answer PromptImportConflict=OK` did not get past
it. The failure is reported by name, so D13 held; but it means that **no
edited native-XML object of any kind** (trace, visualisation, text list, task
configuration...) can be imported by the `--project` form today. The cause is
the call in `engine/object_create.py:268` and in `engine/managers_native.py`,
`import_native(path)` with no handler.

ScriptEngine 4.2.0.0 has an overload
`import_native(path, filter, handler)`, where `handler` implements
`INativeImportHandler` and its `conflict()` returns `NativeImportResolve.replace`,
`skip` or `cancel`. A probe that passed a handler answering `replace` imported
the edited XML, and the trace object then had the new buffer and the new
variable. This is independent of the trace work and should be its own change.

---

## 7. Other findings the design has to carry

### 7.1 Leftover traces on the controller

A trace stays on the controller after `stop()`, logout and closing the IDE.
The next `download()` of a trace with the same name raises
`Strings.OverwriteExistingOnlineTrace` ("The trace already exists on the
device. Delete?", default OK). A command that owns the trace has to answer it
itself; see section 9 on D7.

### 7.2 Controllers found by name can be the wrong controller

Every WSL distribution reports the Windows host name, so two soft PLCs
running at once answer to the same device name. A project that finds its
controller by name, and answers the IDE's "the address differs from the one
stored in the project" prompt with its default Yes, can reach either one.
During this research exactly that happened: another tool's trace script
logged in to the bench used here, downloaded its own application onto it,
and recorded from it. The `plc` commands already aim at an explicit
`--gateway` address when one is given (SPEC 6.6). A trace command has more
reason than the others to insist on it.

### 7.3 Names are checked by nobody, except the controller

Section 4 showed that the API accepts any variable, task or condition string.
A build does not check them either: a trace holding two variables and a
record condition that do not exist compiled with the usual 103 messages and
none of them named the trace. At recording time a variable the controller
does not have makes `start()` fail with "Cannot start the trace in the
current state", which names nothing.

What does name the bad input is the online session's `read_value()`, called
after login and before the trace is downloaded:

| Name | `read_value` |
|---|---|
| `PRG_AxisControl._iOvrZone` | `'INT#3'` |
| `GVL.udiCmdStageGen` | `'UDINT#0'` |
| `NoSuch.var`, `PRG_AxisControl.noSuchMember` | fails, "Invalid expression" |
| `PRG_AxisControl.udiProbeCnt` (declared in the project, not on the controller) | fails, "Invalid expression" |
| `Application.PRG_AxisControl._iOvrZone` | fails: no application prefix |

It checks against the program the controller runs, so it catches a typo and
a variable that only exists in an undownloaded edit alike, one name at a
time. It also returns the type, which a trigger level needs (section 4).
It is a read of a live value, which is the one thing section 9, point 1 is
about.

### 7.4 `Keep` does not notice a changed program

With the program itself changed (a variable added to a POU, not downloaded),
`Keep` still logged in. A trace of variables that exist on both sides then
recorded, and the values were the controller's (`_iOvrZone` read 3, as it
does on the controller), so in that one run nothing was misread. A trace of
the new variable failed at `start()` as in 7.3. One data point on value
correctness is not a guarantee, and the decision "a program that differs
from the controller is refused" cannot be delegated to the login. The
command has to establish it before it records: cdsint already keeps the
controller's `Application.crc` from the last `plc download` of this working
copy (SPEC 6.6), and `MATCH` there is the closest thing it has to "the
controller runs this program".

### 7.5 The application may not be running

After a soft-PLC restart the application on this bench was in `stop`. A trace
on a stopped application records nothing. The probes started it with
`session.start()`. The command will not: it refuses, because starting the
application is a change to the controller's state that the caller did not
ask for (section 10).

---

## 8. Interface draft: `cdsint plc trace --job <json>`

This follows the decisions already taken: select variables only; the
`--project` form only; its own `trace` word in the `plc` list and no `-y`;
the login never downloads, and a program that differs from the controller
is refused with a pointer to `plc download`; the trace object exists for one
run and is never saved; one trace per run; incomplete samples fail the run.
Section 3 showed the throwaway object works. Section 10 lists what is still
open.

```
cdsint plc trace --project P --install I --gateway IP [--port N] --job JOB.json [--json] [--report FILE] [--timeout S]
```

### What one run does

1. Refuse unless the `plc` list holds `trace` (exit 5) and `--gateway` is
   given (exit 2).
2. Pull `Application.crc` and compare it with this working copy's record, as
   `plc connect` does. Anything but `MATCH` is exit 1, pointing at
   `plc download -y` (section 7.4).
3. Open the project, create the trace object `cdsint_trace` under the
   application in memory (refuse if the project already has an object of that
   name), and set variables, task, resolution and both buffers.
4. Log in with `OnlineChangeOption.Keep`. A refusal because another client is
   logged in is reported as that (section 3.2).
5. `read_value()` every variable; each one that fails is listed by name in
   `failed_objects`, and nothing is downloaded (section 7.3).
6. Refuse if the application is not running (section 7.5).
7. Download the trace, answering `Strings.OverwriteExistingOnlineTrace` with
   OK (section 7.1), start, wait `duration_s`, stop, save each format.
8. Log out and close the project without saving.
9. Check completeness from the saved data and write the report.

### Job file

| Field | Type | Required | Meaning |
|---|---|---|---|
| `task` | string | yes | the IEC task to sample in |
| `variables` | list of strings | yes | paths as `read_value()` takes them (`PRG_X.var`, `GVL.var`), no application prefix |
| `duration_s` | number | yes | how long to record |
| `out` | string | yes | output path without extension |
| `formats` | list | no, `["trace", "csv"]` | any of `trace`, `csv`, `txt` |
| `resolution` | `"us"` or `"ms"` | no, `"us"` | timestamp unit |
| `every_n_cycles` | integer | no, 1 | sample every Nth cycle |
| `min_complete` | number | no, 0.99 | completeness below which the run fails |
| `max_gap_periods` | integer | no, 20 | a gap longer than this many periods fails the run |

`trigger` and `record_condition` stay out until section 4's open run shows
they work headless. The ring size is not a field: the command sizes it from
the task period to hold at least two seconds of samples, about ten times the
longest fetch hole measured (180 ms).

`max_gap_periods` is what separates a lost block from jitter (section 2.3):
the jitter measured was up to 4 periods, a buffer loss 80 or more.

### Exit codes (SPEC 4.3, meanings unchanged)

| Code | When |
|---|---|
| 0 | recorded, saved, completeness and gaps within the job's limits |
| 1 | anything else that ran: no `MATCH`, another client logged in, a name that does not resolve, application not running, samples incomplete (the files are still written), `needs_input` |
| 2 | bad command line, including a missing `--gateway` |
| 3 | timed out |
| 4 | no usable IDE for the project |
| 5 | `trace` is not in the settings file's `plc` list |

### Report `data`

```json
{
  "action": "trace",
  "controller": "127.0.0.1:11741",
  "crc": "MATCH",
  "task": "MainTask",
  "period_us": 4000,
  "resolution": "us",
  "duration_s": 3.0,
  "buffer": {"controller_entries": 500, "ide_per_variable": 1000000},
  "files": {"trace": "out.trace", "csv": "out.csv"},
  "variables": [
    {"name": "PRG_X.var", "type": "INT", "samples": 745, "expected": 745,
     "complete": 1.0, "gaps": [], "longest_interval_us": 4210}
  ],
  "complete": true,
  "failed_objects": [],
  "why": null
}
```

`gaps` lists each gap longer than 1.5 periods as `[from, to]` in the file's
timestamp unit, so a reader can see where data is missing, not only that
some is. `type` is what `read_value()` reported.

### Settings file

`plc` gains one word, `trace`, next to `connect` and `download`.

---

## 9. Where this conflicts with SPEC.md and PRINCIPLES.md

1. **SPEC 2, non-goals: "no live read/write of PLC variables".** A trace is a
   live read of PLC variables, and the name check in 7.3 reads each value once.
   The non-goal has to be narrowed, for example to "no watching or writing
   single values", or recording has to be named as the exception.
2. **SPEC D5 and PRINCIPLES 9: no `system.delay()`, no `time.sleep()` in
   `engine/` or `cds/ide/`, enforced by `tests/test_single_threaded_ide_side.py`.**
   A recording of N seconds waits N seconds. The rule exists so the IDE stays
   usable between commands; this command only runs in the `--project` form,
   where nobody is using the IDE. Either the wait is done by a WinForms
   timer, as the watcher does, which needs a message loop that outlives the
   `--runscript` script's return, or D5 gets a named exception for the
   headless trace step.
3. **SPEC 6.5: the `plc` list recognises exactly `connect` and `download`.**
   It needs `trace`.
4. **SPEC D7 and `cds/ide/headless.py` `answer_prompts`: no default answers to
   the IDE's prompts.** `Strings.OverwriteExistingOnlineTrace` has to be
   answered on every run after the first. The trace being overwritten is the
   command's own, so answering is not guessing for the caller; but it is the
   first IDE prompt cdsint would answer without a flag, and the exception
   belongs in D7.
5. **Goal 4 (every listed IDE), and no rule about private API.** The buffers
   are set through a private method of the trace plugin. Nothing in SPEC
   forbids that, but nothing else in cdsint depends on a non-public member.
   Accepted (section 10); what it still needs is a check that the member
   exists before use (refuse rather than record with 100 entries) and a row
   in the compatibility matrix.
6. **SPEC 6.6: without `--gateway`, the project's own gateway is used.**
   Section 7.2 argues `plc trace` should refuse without it, which makes it the
   one `plc` command where the flag is required.
7. **SPEC 6.6, what `MATCH` means.** `MATCH` says the controller still holds
   what this working copy last downloaded; it does not say the working copy
   has not been edited since. `plc trace` leans on it harder than
   `plc connect` does (section 7.4), so that gap now matters more. The
   `read_value()` check narrows it for the variables being traced, and only
   for those.
8. **SPEC goal 1 and D13, native XML import (section 6.3).** Not a conflict
   with the trace design; an existing gap the trace work exposed.

A trace object that is never saved never has to reach disk, so the
disk-is-the-truth rule (PRINCIPLES 5) is not in play.

---

## 10. Decisions

Taken after this research, on 2026-09-24:

1. **A stopped application is refused.** The command never changes the
   controller's run state.
2. **The private buffer member is used.** Without it, tasks faster than
   about 4 ms lose samples. If a later IDE changes it, the likely change is a
   public member, and the command follows then.
3. **Native XML import (section 6.3) is fixed first**, as its own change,
   before the trace command.

Still open:

4. **Trigger and record condition.** Pending the run in section 4, which
   needs an application with a changing variable on the bench.
5. **The trace object's name.** `cdsint_trace` is fixed so the overwrite
   prompt is always about cdsint's own trace. A project with its own object of
   that name is refused rather than renamed around.

## 11. Not verified

- A trigger or record condition firing under `--noUI` (section 4).
- Recording longer than 4 s. The IDE-side buffer was set to 1,000,000
  samples per variable; memory use at that size and behaviour over minutes
  were not measured.
- That values recorded while the program differs from the controller are
  always the controller's (one run, section 7.4).
- Whether a trace download changes `Application.crc`. The file's modification
  time did not change across the trace runs here; its content was not
  compared.
- Any IDE other than CODESYS 3.5.21.40.
