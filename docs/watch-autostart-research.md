# Research: arming the watcher without a click

> A research record, not a spec. Nothing here is implemented, and nothing here
> changes SPEC.md, PRINCIPLES.md or WATCHER.md. Measured on 2026-09-26 against
> CODESYS 3.5.20.40 and 3.5.21.40, DIADesigner-AX 1.8 and 1.10, and Lenze PLC
> Designer 3.24 and 4.0.1, all with the UI on. CODESYS 3.5.19.10 could not be
> tested: that install has no ScriptEngine plug-in at all (section 1).

Today somebody has to click **Tools > Scripting > Scripts > Project_watch**
once per IDE session before `--target` can reach that IDE. The question: can
the watcher be armed with no click at all?

Every claim below is marked as one of three kinds:

- **Measured**: an experiment on this machine showed it; the output is quoted.
- **Read**: an official document, a forum post or a reflection listing says it.
- **Inferred**: a conclusion from the two above that nothing here tested.

---

## 0. Answers in one table

| Question | Answer | Section |
|---|---|---|
| 1. Does `<exe> --profile=... --runscript=<script>` without `--noUI` show the UI? | **Yes, on all six IDEs tested.** The main window is up before the script runs, and the IDE stays open after the script returns. Measured | 2 |
| 1. Can that script arm the watcher and leave the IDE usable? | **Yes, on all six.** `list`, `ping` and `status` reach it, and real clicks on File open the menu every time. Measured | 2.2 |
| 1. Does the shipped `Project_watch.py` work as the `--runscript` target, unchanged? | **Yes** (SP21, with `--project`). Measured | 2.3 |
| 1. Before or after the main window? | After. `ScriptEngine` runs `--runscript` from the engine's `UIReady` event. Read (IL) and measured | 2.1 |
| 1. Dialogs? | None from the script route itself. The IDE's own dialogs still appear: "Project Environment" when a project is opened, and Lenze 4.0's "Installing Lenze packages..." at start-up | 2.4 |
| 2. A "project opened" or "IDE started" event in the **script API**? | **No.** None in any ScriptEngine or ScriptDriver assembly, none in the docs, and CODESYS staff call the feature (CDS-20898) unimplemented with "no release plan" | 3.1 |
| 2. In the Automation Platform underneath? | **Yes.** `IObjectManager.ProjectLoaded`, `IObjectManager6.ProjectLoadFinished`, `IProjects.PrimaryProjectSwitched`, `IEngine.UIReady`, on all seven installs. Read (reflection) | 3.2 |
| 2. Can a script subscribe to them? | **Only through a compiled shim.** A plain IronPython delegate **breaks project open, create and close**: a person's File > Open fails with "The specified project could not be loaded". A delegate bound to a static method in a tiny compiled DLL works. Measured | 3.3, 3.4 |
| 2. Does the handler survive the script returning, and fire on a person's open? | **Yes, on all six.** Ctrl+O, type the path, Enter, and the handler armed the watcher for the new project. Measured | 3.4 |
| 3. An official autostart option, startup folder or plug-in folder for Python? | **None found.** `--runscript` is the only documented way to run a script without a click. Read | 4 |

**Recommendation in one line:** a shortcut that starts the IDE with
`--runscript=<ScriptDir>\cdsint\Project_watch.py` removes the click today, with
no code change, for an IDE started from that shortcut. To also follow projects
opened later, poll `projects.primary` from the watcher's existing timer, not
events (section 6).

---

## 1. How this was measured

**Reflection** (read-only). A PowerShell script loaded each install's
assemblies with `[Reflection.Assembly]::LoadFrom`, resolved dependencies from
the same `Common` directory, and listed `GetTypes()` / `GetEvents()` /
`GetMembers()`, keeping the types that loaded when some did not. To see what a
method does, it decoded the method's IL and resolved every `call` and `ldstr`
token. Assemblies read:

| Install | ScriptEngine plug-in |
|---|---|
| CODESYS 3.5.19.10 | **none**: `PlugIns\dc937c18-e9f0-434d-85b7-1b8f499e378a` does not exist and the profile does not name it |
| CODESYS 3.5.20.40 | 4.1.0.0 |
| CODESYS 3.5.21.40 | 4.2.0.0 |
| DIADesigner-AX 1.8 / 1.10 | 4.0.0.0 |
| Lenze PLC Designer 3.24 | 4.0.0.0 |
| Lenze PLC Designer 4.0.1 | 4.1.0.0 |

On 3.5.19.10, then, nothing can run a script at all, whether from the Scripts
menu or from `--runscript`. That also means `Project_watch.py` cannot run there
today (inferred from the missing plug-in; not started).

**Experiments** (measured). Each IDE was started with its UI on:

```
<exe> --profile="<name>" --runscript="%TEMP%\cdsint-work\autostart\exp_a.py"
```

The launcher script (throwaway, not in the repo) did the following:

1. Logged `system.ui_present`, the engine's `Frame`, the process's main window
   handle and title, and `projects.primary`, at script start, at script end
   and on the first timer tick after the script returned.
2. Optionally subscribed to Automation Platform events (section 3).
3. Ran this worktree's `tools/probe_watcher_ui.py`: build a throwaway project
   with three POUs, write its settings file, and arm the watcher the way
   `Project_watch.py` does.
4. Scheduled a one-shot WinForms timer that, 40 to 90 s later, stopped the
   watcher, closed the project, created a second project and opened it with
   `projects.open`.

While the IDE was up, the following were run from outside:

- `python -m cdsint.cli list`, then `ping` and `status` against the instance.
  On SP21 also `export`.
- `tools/probe_click_menu.py --pid <pid>` for real mouse clicks on File
  (WATCHER.md 8).
- A throwaway `ui_open.py`: bring the IDE to the front, then press Ctrl+O,
  type the path and press Enter through `SendInput`. It is the same input a
  person gives. It refuses to send any key unless the foreground window
  belongs to the IDE it started.

Every IDE was started by this work and killed by pid with `Stop-Process -Id`
(pids 23836, 16452, 12048, 11572, 2288, 5900, 25244, 23472, 2124, 3796,
23420, 25436, 23348, 23932). The user's own DIADesigner-AX 1.10 (pid 20256)
was never touched.

---

## 2. Question 1: `--runscript` with the UI on

### 2.1 What the ScriptEngine does with `--runscript` (read, IL)

In `ScriptEngine.plugin.dll`, `_3S.CoDeSys.ScriptEngine.ScriptEngine`:

- `OnAllSystemInstancesAvailable()` reads the `runscript` option from
  `ICommandLineManager.GetOption`. When it is set, it subscribes
  `IEngine.UIReady` and `IEngine7.ConsoleReady`.
- `OnApplicationReady()` (the handler) unsubscribes both. It reads
  `runscript` and `scriptargs`, creates an executor, and calls
  `IScriptExecutor.ExecuteFile`. On an exception it reports
  `ScriptRunCausedException` through the message service. It calls
  `IEngine.Shutdown()` and `Environment.Exit` **only on the branch where
  `IEngine.Frame` is null**, that is, under `--noUI`.

This IL shape is identical in plug-ins 4.0.0.0 (Delta 1.8, Delta 1.10,
Lenze 3.24), 4.1.0.0 (SP20, Lenze 4.0.1) and 4.2.0.0 (SP21).

So with the UI on, the script runs once the main window is up, and the IDE is
not closed when the script ends. The official docs describe `--runscript`
only together with `--noUI`, where "CODESYS starts and executes the script
without opening the CODESYS main window. Then CODESYS is exited"
([_cds_starting_script_via_command_line](https://content.helpme-codesys.com/en/CODESYS%20Scripting/_cds_starting_script_via_command_line.html)).
A CODESYS developer on the forum confirms the UI case: to close the IDE after
the script, "insert a `system.exit()` statement at the end of the python
script ... or add `--noUI`"
([forge thread a582b0f360](https://forge.codesys.com/forge/talk/Engineering/thread/a582b0f360/), 2012).

### 2.2 Measured on six IDEs

At script start, every run logged `ui_present=True frame=MainForm`, a non-zero
main window handle, and `thread=1`, which is the UI thread. For example, on
SP21:

```
01:14:01 +1.00s script start: ui_present=True frame=MainForm mainwnd=0x1308AC title='CODESYS ' primary=None thread=1
```

| IDE | Start to script | Watcher armed | `list` / `ping` / `status` | File-menu clicks after the script returned |
|---|---|---|---|---|
| CODESYS 3.5.21.40 | 21 to 29 s | yes | all exit 0; `export` wrote 3 new | 5 of 5 opened (twice) |
| CODESYS 3.5.20.40 | 75 s | yes | exit 0 | 3 of 3 opened |
| DIADesigner-AX 1.10 | 39 s | yes | exit 0 | 4 of 4 opened |
| DIADesigner-AX 1.8 | 124 s | yes | exit 0 | 4 of 4 opened |
| PLC Designer 4.0.1 | 220 s, after the package installer | yes | exit 0 | 3 of 3 opened |
| PLC Designer 3.24 | 146 s | yes | exit 0 | 3 of 3 opened |

The Delta 1.10 row fills the cell WATCHER.md 8 left open: this time
`SetForegroundWindow` succeeded, and the clicks show the watcher leaves Delta
1.10 clickable.

**The IDE can stay busy for a while after the script returns** (measured).
The first timer tick after the script ended came 0.2 to 17 s later. It was
17 s on SP21's first run and on SP20's only run, and 0.2 to 3.2 s in the
other nine runs. The watcher only answers once ticks run, and it writes the
registration file before the first tick. A caller that sees the file and
sends a command at once may therefore wait up to that long for the answer.

**With no project open, the watcher still arms** (measured, SP21). It
registers as `unsaved-<pid>`, `status` says `no project open`, and it answers
`ping`. That instance does **not** follow a project opened afterwards: the
instance id and `project_path` are fixed when it is armed (WATCHER.md 2).

### 2.3 `--project` together with `--runscript`, and the shipped stub

With the UI on, `--project` opens the project **before** the script runs
(measured, SP21):

```
01:46:19 +0.72s script start: ... title='sp21p2.project - CODESYS ' primary=C:\...\sp21p2\sp21p2.project thread=1
```

This differs from `--noUI`, where SPEC 6.4 records that `--project` does not
open the project.

The unchanged, installed stub `%LOCALAPPDATA%\CODESYS\ScriptDir\cdsint\Project_watch.py`
was then used as the `--runscript` target, with `--project` pointing at a
throwaway project (measured, SP21). Thirty seconds after start, `cdsint list`
showed `sp21p1-23348 idle <path>`, and `ping` answered
`pong from sp21p1-23348`. So the product's existing entry point is already a
valid no-click entry point.

### 2.4 Dialogs

- The script route adds no dialog of its own on any of the six (measured).
- **"Project Environment"** (the SoftMotion version check) came up whenever a
  project with no SoftMotion version set was opened by a person or by
  `--project`, on SP20, SP21 and Delta 1.10. It is modal. One File click
  landed while it was up and did not open the menu. The watcher still
  answered `ping` while it was up (measured, SP21), because the modal loop
  still pumps timers. This is the IDE's normal behaviour for such a project,
  not something the script route adds.
- **Lenze 4.0.1** showed "Installing Lenze packages..." at start-up for about
  3.5 minutes before the script ran. This is Lenze's own first-start step and
  would happen for a person too. Where it installs was not traced.
- A script that raises on its first line (SP21) left the IDE up, responding,
  and clickable (2 of 2 opened), with no dialog. This matches the IL: an
  exception is reported, and shutdown happens only with no frame. It is
  measured only as "the IDE survived". The error text itself was not captured,
  because it goes to the IDE's message view.

---

## 3. Question 2: an event hook

### 3.1 The script API has no lifecycle event

- **Read (reflection, SP21).** The only events in `ScriptEngine3.dll` 4.2.0.0
  and `ScriptEngine.plugin.dll` are the executor's own: `IScriptExecutor.Executing`
  and `Executed`, `IScriptExecutor2.Compiling` and `Compiled`, and
  `Notifications` on the event-args types. None of the 18
  `Script*.plugin.dll` in SP21's `PlugIns` declares any other event. That
  includes `ScriptDriverProjects.plugin` (the `projects` object) and
  `ScriptDriverSystem.plugin` (`system`).
- **Read (docs).** The `ScriptSystem` and `ScriptProjects` references on
  [content.helpme-codesys.com/en/ScriptingEngine](https://content.helpme-codesys.com/en/ScriptingEngine/ScriptSystem.html)
  list no event, callback or handler member.
- **Read (forum, CODESYS staff).** Asked for a script that runs automatically
  on an IDE event, mkeller (CODESYS) wrote "CDS-20898 in our bug tracking but
  it is not implemented yet", and then "For CDS-20898 there is no release
  plan" ([forge thread 8c192018e5](https://forge.codesys.com/forge/talk/Engineering/thread/8c192018e5/),
  2017). Nothing newer was found saying it shipped.

### 3.2 The Automation Platform does have them (read, reflection)

These interfaces are present on all seven installs, SP19 included:

| Interface (assembly) | Events of interest |
|---|---|
| `_3S.CoDeSys.Core.IEngine` (EngineWin) | `Initialized`, `UIReady`, `Exiting`; `IEngine7.ConsoleReady` |
| `_3S.CoDeSys.Core.Objects.IObjectManager` (ObjectsWin) | `ProjectLoading`, `ProjectLoaded`, `ProjectCreated`, `ProjectClosing`, `ProjectClosed`, `ProjectSaved`, plus per-object events |
| `_3S.CoDeSys.Core.Objects.IObjectManager6` | `ProjectLoadFinished` |
| `_3S.CoDeSys.Core.IProjects` (Objects) | `PrimaryProjectSwitched`, `Before...`, `After...` |

The `ObjectManager` events are `(object sender, <X>EventArgs e)`. The
`IProjects` events are `(IProject oldProject, IProject newProject)`.

`IEngine.UIReady` is not usable as an autostart: it is the event the
`--runscript` handler itself hangs on, so it has already fired by the time any
script runs.

A script reaches these objects (measured) through the component manager, the
same call a CODESYS developer quotes for plug-ins
([forge thread 60039f2d35](https://forge.codesys.com/forge/talk/Engineering/thread/60039f2d35/)):
`ComponentManager.Singleton.InstanceFactory.GetSystemInstance("_3S.CoDeSys.Core.Objects.IObjectManager")`.
It returned `_3S.CoDeSys.ObjectManager.ObjectManager` on every IDE. None of
this is script API: it is the internal plug-in API, reached by type name
through reflection.

### 3.3 A plain IronPython handler breaks the IDE (measured)

A handler subscribed the obvious way,
`EventInfo.AddEventHandler(obj, clr.GetPythonType(ev.EventHandlerType)(py_function))`,
**never ran**. Instead, every operation that raises the event threw:

- SP21, subscribed to `IObjectManager.ProjectLoaded`/`ProjectCreated`/
  `ProjectClosed`/`ProjectLoadFinished`: `projects.create(...)` raised
  `ValueError: MethodInfo must be a runtime MethodInfo object. Parameter name: this`.
  A control run with no subscription created the same project without error.
- SP21, subscribed only to `IEngine.Exiting` and `IProjects.PrimaryProjectSwitched`:
  `projects.create` raised the same error after the project had already
  become primary. Ninety seconds later, from a timer after the script had
  returned, `projects.primary.close()` raised it too.
- Delta 1.10, subscribed to `ProjectLoaded` and `ProjectLoadFinished`: a
  **person's** open (Ctrl+O, path, Enter) put up a message box: "The
  specified project could not be loaded. Possible reasons might be: - The
  project file is corrupted or invalid ...". The same project had opened
  cleanly in the previous run.

Inferred cause: the IDE raises these events through reflection over each
handler's `Delegate.Method`. IronPython's delegates are backed by a
`DynamicMethod`, which is not a runtime `MethodInfo`. Either way the measured
consequence stands. **A subscription like this, left in someone's IDE, makes
every later File > Open fail until the IDE is restarted.**

### 3.4 A compiled shim works, survives, and fires on a person's open (measured)

The same subscription made through a delegate bound to a static method of a
compiled class works. The class was a three-line C# file compiled with
PowerShell `Add-Type -OutputAssembly AsShim.dll`:
`public static void Handle(object a, object b)` forwards to a static
`Action<string, object, object>` holding the Python callback. The script
loaded it with `clr.AddReferenceToFileAndPath`, and subscribed with
`Delegate.CreateDelegate(ev.EventHandlerType, typeof(Hook).GetMethod("Handle"))`
(parameter contravariance binds it to every `(object, XEventArgs)` and
`(IProject, IProject)` handler type).

With the shim, on SP20, SP21, Delta 1.8, Delta 1.10, Lenze 3.24 and 4.0.1:

1. `projects.create`, `close` and `open` all worked, and the handlers fired
   (`ProjectLoaded`, `ProjectLoadFinished`, `ProjectClosed`,
   `PrimaryProjectSwitched`).
2. **The handlers kept firing after the script returned**, first for the
   scripted `projects.open` in the delayed timer, then for a **person's
   open**. On that open the handler scheduled a 500 ms one-shot timer, and
   the timer armed the watcher for the new project. From Delta 1.10:

```
01:31:14 +110.69s EVENT ... ProjectLoadedEventArgs ProjectHandle=3
01:31:14 +110.94s EVENT ... (NoneType, ProjectImpl) Path=C:\...\dia110p1\dia110p1.project
01:31:16 +112.11s armed from event as dia110p1-25244
01:31:16 +112.23s EVENT ... ProjectLoadFinishedEventArgs ProjectHandle=3
```

   followed from outside by `cdsint list` → `dia110p1-25244 idle ...` and
   `ping` → `pong from dia110p1-25244`. Every one of the six IDEs showed the
   same sequence. On Lenze 4.0.1 the arming came 6 s after `ProjectLoadFinished`,
   because the IDE was still busy.

3. On SP21 and Delta 1.10, `projects.open` pumps messages. The timer that the
   `ProjectLoaded` handler set **fired before `projects.open` returned** and
   before `ProjectLoadFinished`. The watcher was therefore armed on a project
   still loading. A real design would have to arm on `ProjectLoadFinished`,
   or check again on the next tick.

---

## 4. Question 3: other ways to avoid the click

All of these are read, not measured, unless marked.

- **Command line.** The official option list
  ([_cds_commandline](https://content.helpme-codesys.com/en/CODESYS%20Development%20System/_cds_commandline.html))
  has `--runscript`, `--scriptargs`, `--noUI`, `--enablescripttracing`,
  `--profile`, `--project` and `--scriptdebugger`, and nothing like a
  start-up script directory. In `ScriptEngine.plugin`, the only command-line
  descriptors are `ScriptEngineRunScript` ("Executes the given script. The
  absolute path of the script file must be entered."),
  `ScriptEngineScriptArgs` and `ScriptEngineEnableScriptTracing` (reflection,
  resource strings).
- **ScriptDir and Script Commands.** The Scripts menu lists `ScriptDir`
  ([_cds_cmd_scripts](https://content.helpme-codesys.com/en/CODESYS%20Scripting/_cds_cmd_scripts.html)).
  `Script Commands` folders add toolbar icons
  ([_cds_executing_scripts_toolbar](https://content.helpme-codesys.com/en/CODESYS%20Scripting/_cds_executing_scripts_toolbar.html)).
  Both still run a script only on a click; they save navigation, not the
  click.
- **Tools > Options.** No start-up script or autorun option is documented.
- **C# plug-in.** The documented way to run scripts from IDE events is an
  Automation Platform plug-in that calls `IScriptEngine.Execute`
  ([forge thread 60039f2d35](https://forge.codesys.com/forge/talk/Engineering/thread/60039f2d35/)).
  That means building against the non-public SDK and installing a DLL into
  each IDE's `PlugIns` and profile. `ScriptEngine.plugin` also has an
  `IScriptEngineOEMCustomization` extension point, which is the same kind of
  thing: OEM plug-in territory.
- **Delta, Lenze.** No public scripting or command-line documentation was
  found. The Delta manual mirror returned 403. Reflection shows both use the
  same ScriptEngine code (section 2.1), so the CODESYS findings carry over.
  The measurements in sections 2 and 3 confirm it.

---

## 5. Not tried, and why

- **CODESYS 3.5.19.10.** No ScriptEngine plug-in is installed, so there is
  nothing to test.
- **Starting through a file association or a double-click in Explorer.** The
  machine rules forbid changing file associations. A shortcut with explicit
  arguments stands in for it.
- **`--runscript` on an IDE a person already has open.** Every IDE here was
  a fresh process. Whether a second launch hands its arguments to a running
  instance was not tested directly. The two DIADesigner-AX 1.10 processes that
  ran side by side here (the user's and this work's) were independent, and
  the experiment script refused to act in any process it had not launched.
- **Compiling the shim at run time** (CodeDom, from inside IronPython)
  instead of shipping a DLL. Not tried.
- **Polling `projects.primary` from the watcher's tick** (section 6, route C).
  Not built, because that would be designing the feature. The measured part
  is that `projects.primary` and its path read correctly from a timer tick
  after the script returned, on all six IDEs (the "first tick" log lines).
- **Graceful exit.** Every IDE was killed with `Stop-Process`. What the IDE
  writes to the per-user settings on a normal close was not examined.
- **The real sample projects.** Only throwaway projects were used, and
  `export` was run only on SP21.

---

## 6. Recommendation

| Route | Click-free for | Cost | Risk |
|---|---|---|---|
| **A. Launcher/shortcut:** `<exe> --profile="<name>" [--project="<p>"] --runscript="<ScriptDir>\cdsint\Project_watch.py"` | an IDE started that way, with the project it was started on | None in the IDE code; the stub works unchanged (2.3). Only a way to create the shortcut, e.g. a `cdsint` command that writes one per install | The IDE opened by double-clicking a `.project` still needs the click. A project opened later is not followed (2.2) |
| **B. A + events through a compiled shim** | also projects opened later | Ship and load a .NET DLL; reach internal types by name through `ComponentManager`; arm on `ProjectLoadFinished` | **High.** Internal API, not script API. One mistake (a plain IronPython delegate) makes the user's File > Open fail (3.3) |
| **C. A + follow `projects.primary` from the existing tick** | also projects opened later | Watcher change only: when the primary path differs from the registered one, re-register under the new instance id. No new mechanism, no DLL | Changes the watcher's contract (instance id, registration lifecycle in WATCHER.md 2) and needs its own design. Inferred, not built |
| D. C# Automation Platform plug-in | everything, including double-click | Build against the non-public SDK, install per IDE and profile, sign and ship | Out of proportion for this problem |

**Viable today: route A.** It is measured on six IDE versions and needs no
product change. What it does not cover is an IDE someone opens some other way.
If following later projects matters, **route C is the one to design**. It uses
nothing the watcher does not already use: the timer is there, and
`projects.primary` is readable from a tick. Route B should not be taken. The
event hook exists and works, but only by reaching past the script API, and
the way it fails puts a broken File > Open in the user's IDE, the worst place
for it.

---

## 7. Settings safety record

Before the first UI run, `%APPDATA%\CODESYS`, `%APPDATA%\Delta Industrial
Automation`, `%APPDATA%\DIADesigner-AX`, `%APPDATA%\PLCDesigner` and
`%APPDATA%\Lenze` were copied to `%TEMP%\cdsint-work\autostart\backup\`, and
SHA-256 was recorded for all 54 files. After each of the 14 runs, a recheck
showed `diffs: 0`: no file was changed, added or deleted, so nothing was
restored. The ScriptDir junctions, the registry and the file associations were
not touched. The one registration file left behind by a killed watcher
(`sp21p1-23348`, started by this work) was deleted. `cdsint list` was empty
at the end.
