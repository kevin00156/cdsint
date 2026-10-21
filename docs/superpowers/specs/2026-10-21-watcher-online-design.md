# Design: logging in and out, running and stopping from the watcher

Date: 2026-10-21. Status: approved by the owner, 2026-10-21.

## 1. Why

The watcher runs inside an IDE that, when an agent drives it through
cdsint, almost nobody is sitting at. An agent asked to work on a trace
object or on EtherCAT settings regularly needs the application logged in
(to download and record a trace, to see the device online) or logged out
(to change what only an offline project can change). Today it cannot do
either: D8 says the watcher never logs in or out, so the agent stops and
waits for a person to press Login or Logout. That small wait is what stalls
the work, and removing it is the whole point.

This reverses two decisions on purpose, as a product decision by the
project owner:

- **D8**, "the watcher never logs in or out". Its reason was that a login
  from the watcher would take away the online session of the person at the
  IDE. In the scenario this design serves, there is no such person; and
  every new action is still behind the `plc` list and, where it changes the
  controller, `-y`.
- **SPEC 2, non-goal "No online change"** (and the first line of 6.6). An
  online change becomes a method the caller may ask for explicitly.

## 2. Goals

1. An agent can log the IDE's active application in and out from the
   watcher.
2. A plain login never changes the controller. When the working copy
   differs from what the controller runs, the login does nothing and says
   so, and the caller has to choose how to bring the controller up to date:
   a full download or an online change.
3. An agent can start and stop the application from the watcher.
4. Each action that touches the controller has its own word in the `plc`
   list, so a project can allow logging in without allowing downloads, and
   so on.

## 3. Non-goals

- These commands in the `--project` form. That form logs out at the end of
  every run, so a login, a `run` or a `stop` there outlives nothing. The
  `--project` form keeps `plc connect`, `plc download` and `plc trace`
  exactly as they are.
- Choosing a controller. The watcher logs in to whatever the device node in
  the open project already points at, as the IDE's Login button does. No
  `--gateway`, `--port` or `--gateway-name`.
- Writing variables, forcing, reset (warm, cold, origin), source download.
- Falling back from one method to the other. An online change that is not
  possible is a failure, never a quiet full download.

## 4. Anti-goals: it fails even if it "works" when

- A plain `plc login` downloads anything or makes an online change. This is
  the one property the whole design rests on: today a `Keep` login applies
  any difference itself, without asking (`docs/ethercat-research.md` 5.2,
  `docs/trace-research.md` 12.1).
- A dialog opens in the IDE and the watcher waits on it. Nobody is there to
  click it; a stuck IDE means someone has to walk to the machine.
- The report says the application is in a state it is not in. Every state
  claimed is read back from the controller after the action.

## 5. The commands (decided with the owner)

All four exist only in the watcher form (`--target X`); the `--project`
form refuses them at the parser (exit 2).

| Command | `plc` list word | `-y` | What it does |
|---|---|---|---|
| `plc login` | `login` | no | log in only if nothing has to change on the controller; otherwise change nothing and return exit 1 saying what differs and which `--method` values would apply it |
| `plc login --method download` | `download` | yes | log in with a full download, then write the boot application; the application is left stopped |
| `plc login --method online_change` | `online_change` | yes | log in with an online change, then write the boot application; the application keeps the state it had |
| `plc logout` | `login` | no | log out |
| `plc run` | `run` | yes | start the application |
| `plc stop` | `stop` | yes | stop the application |

`--no-boot-app` on either `--method` skips writing the boot application.
Writing it is the default because a controller that is restarted should come
back running what the agent last put on it, not what was there before.

Without `-y`, the commands that need it print what this run would do and
return `needs_input`, exit 1, exactly as `plc download` and `import` do
(SPEC 6.5). Exit 5 keeps its single meaning: the list does not allow it.

### 5.1 `plc login`, no method

1. Refuse with exit 5 unless the list holds `login`.
2. Already logged in: success, and the report says so. Nothing is done.
3. Decide, without touching the controller, whether a login would change
   it. `is_uptodate` is false means the working copy's code, IO mapping,
   device settings or libraries differ from the IDE's record of the last
   download (`docs/ethercat-research.md` 5.1). If it differs, return exit 1
   with: that it differs, `is_online_change_possible`, and the
   `--method` values that would apply it (`online_change` only when
   possible), in `data.methods`. This is an ordinary failure, **not**
   `needs_input` (builder's call, 2026-10-21): `needs_input` means "add this
   flag and run again" (SPEC 4.3), and a caller that does that by reflex
   would stop the machine with `--method download`. Choosing a method is a
   decision, not a missing flag. See 7, R1 and R2, for what this check does not yet cover.
4. Log in with `OnlineChangeOption.Keep`. After step 3, `Keep` has nothing to
   apply.
5. Report the login and the application's state as read back.

A login refused because another client is already logged in to the
controller says exactly that.

### 5.2 `plc login --method download`

1. Exit 5 unless the list holds `download`; `needs_input` unless `-y`.
2. Already logged in: exit 1, "log out first". Downloading over a live
   session is a second path for the same thing.
3. Log in with a full download (`OnlineChangeOption.Never`,
   `delete_foreign_apps` false, as the `--project` download does). This
   downloads even when nothing differs: the caller asked for a download.
4. Unless `--no-boot-app`, write the boot application.
5. Leave the application stopped. Read its state back and report it. A
   caller that wants it running issues `plc run -y`.

### 5.3 `plc login --method online_change`

1. Exit 5 unless the list holds `online_change`; `needs_input` unless `-y`.
2. Already logged in: exit 1, "log out first".
3. `is_online_change_possible` false: exit 1, saying so and pointing at
   `--method download`. Nothing is touched.
4. Log in so that the difference is applied by online change and by nothing
   else (R3). Nothing different: it is a plain login, and the report says
   no change was made.
5. Unless `--no-boot-app` or nothing changed, write the boot application.
6. Report the application's state, read back.

### 5.4 `plc logout`

Exit 5 unless the list holds a word that can log in: `login`, `download` or
`online_change` (builder's call, 2026-10-21: a list that lets the agent log
in must let it log out, or the next `--method` stalls on "log out first"
until a person comes). Logging out changes nothing on the controller. Not logged in: success, saying so.
Otherwise log out and report.

### 5.5 `plc run`, `plc stop`

Exit 5 unless the list holds `run` (or `stop`); `needs_input` unless `-y`.
Not logged in: exit 1, pointing at `plc login`. Already in the asked state:
success, saying so. Otherwise start (or stop), then read the state back;
anything but `run` (or `stop`) is exit 1.

### 5.6 Where these meet existing behaviour

- While a recording is held, the watcher already answers only `plc trace
  --stop`, `ping` and `status` (SPEC 6.8), so none of these can end a
  recording. No new rule.
- The watcher's `plc trace` refusal "the application is not logged in" and
  "the application is not running" now point at `plc login` and `plc run -y`.
- The watcher's refusal of `plc connect` and `plc download` stays; its
  message for `plc download` points at `plc login --method download -y`.
- The `plc` list gains `login`, `online_change`, `run` and `stop`. Existing
  settings files keep working unchanged. **`download` widens** (owner's
  decision, 2026-10-21): it used to allow only the `--project` download,
  which always names `--gateway`; it now also allows the watcher's full
  download to whatever controller the device node points at. Both are the
  same act, and a second word would only be one more name to remember.
- Which controller. The same-host-name problem of the WSL benches
  (`docs/trace-research.md` 7.2) is fixed on the bench (owner, 2026-10-21),
  so the watcher logs in where the device node points, with no extra rule.
  Every login's report names the address actually reached. If the IDE asks
  "the address differs from the one stored in the project", the command has
  no answer for it, so the login fails saying so, as every unanswered prompt
  does (D7; builder's call).
- The CRC record (`<project>.cdsint-plc.json`, SPEC 6.6). A download from
  the watcher changes the controller's `Application.crc`, so the entry for
  that controller no longer describes it. The rule: the record must never
  say `MATCH` for a controller that holds something else. Whether the
  watcher writes the new value or removes the stale entry is the builder's
  call (R5).

## 6. Documents to change

SPEC (D8 rewritten, section 2 non-goal, 4.4 and 6.5 list words, 6.6 first
line, 6.8 watcher refusals, the command table in 4, the verified-on table),
`docs/WATCHER.md` section 4, `docs/REFERENCE.md`, the `cdsint` skill under
`skills/`, `CHANGELOG.md`, and `SCRIPT_VERSION` (a new minor version: new
commands and new list words, nothing removed).

## 6a. Where it lands in the code (as found on 2026-10-21)

- The permission words: `PLC_ACTIONS` in `cds/core/settings.py`, read by
  `cds/ide/permit.py`; the watcher's `_not_allowed()` in
  `cds/ide/entries.py` already gates every command starting `plc `.
- The parser: the `plc` row of `COMMANDS` in `cdsint/flags.py`
  (`needs`/`takes`/`refuses`, `form_refuses`, `action_forms`), checked by
  `cdsint/refusals.py`. The IDE side keeps its own copy of the watcher
  refusals in `WATCHER_REFUSES` and the script map in `SCRIPTS`, both in
  `cds/ide/entries.py`.
- The online calls to reuse: `ide_private.in_script_run` (R6), the login
  and "another client" handling in `engine/plc_trace.py` `_log_in`, the
  `Never` login and boot application in `engine/plc_download.py`
  `_download_on`, the state reader `state_of`, and the credential switch
  `switch_fallback_off` in `engine/plc_link.py` (R4).
- `cdsint/flags.py` and `engine/plc_trip.py` are already over the 300-line
  soft limit and `engine/entry_trace.py` is two lines under the hard one
  (PRINCIPLES.md), so the new steps go in a new engine module rather than
  into those.

## 7. Open technical questions (the builder settles these, on the bench)

None of these changes what gets built from the owner's side; each has a
rule it has to satisfy.

- **R1. Does `is_uptodate` alone make a `Keep` login safe from the
  watcher?** The `--project` trace also compares the controller's
  `Application.app` header with `.bootinfo_guids` before logging in (SPEC
  6.8 step 2), which catches a controller someone else downloaded to. From
  the watcher that needs a device connection of cdsint's own, which SPEC
  6.8 avoided while the person's login was open. Before `plc login` nobody
  is logged in, so it may be harmless now. Measure it. Rule: if a case is
  found where `Keep` changes the controller and no pre-check catches it,
  plain `plc login` refuses that case rather than ships with the hole.
- **R2. A working copy without the IDE's download files** (`.compileinfo`,
  `.bootinfo`, `.bootinfo_guids`): `Keep` downloads in full
  (`docs/trace-research.md` 12.1). Check what `is_uptodate` says then. Rule
  as in R1.
- **R3. Which `OnlineChangeOption` applies an online change and refuses
  rather than falls back to a download** (`Force` or `Try`, as measured, not
  as named). Rule: the method never downloads in full.
- **R4. Dialogs.** Credentials (device user management), and any prompt a
  login raises in an interactive IDE. `plc connect` switches the credential
  dialog off through `online.auth_fallback_modes`; find out whether doing
  that in the person's IDE outlives the command, and restore it if it does.
  The credentials in `CDS_DEV_USER`/`CDS_DEV_PASS` belong to the CLI's
  environment, not the IDE's; a controller that asks for credentials the
  IDE does not already have makes the login fail, saying a person has to
  log in once by hand. Rule: no dialog is ever left open.
- **R5. The CRC record after a watcher download** (5.6).
- **R6. The nested script run** (`docs/trace-research.md` 15.2). Every
  online call here must go through it, as the watcher's `plc trace` does.
- **R7. How long a login with download blocks the IDE's message loop**, and
  whether the default `--timeout` holds for it on the bench's application.

## 8. Acceptance

On a WSL bench, in an interactive IDE with the watcher running, each row of
5 at least once, with the controller's audit log read after each to confirm
what happened on it: plain login on an unchanged copy (no download, no
online change in the log); plain login refused after a code edit, after an
IO mapping edit and after a master cycle edit, each with the right
`--method` hint; `--method online_change` after the IO mapping edit (online
change in the log, application still running, boot application written);
`--method online_change` refused after the master cycle edit;
`--method download` after the master cycle edit (download in the log,
application stopped); `run` and `stop` with the state read back; `logout`;
a watcher `plc trace` straight after `plc login` and `plc run -y`.
