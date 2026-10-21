# Watcher Login, Logout, Run and Stop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an agent log the IDE's active application in and out, and start and stop it, through the watcher (`cdsint plc login|logout|run|stop --target X`).

**Architecture:** Four new `plc` actions, watcher form only. The `plc` permission list grows from three words to seven and stops being the same tuple as the CLI's actions. The engine side is one new module, `engine/plc_session.py`, a `Trip` subclass whose steps run inside one nested script run (`ide_private.in_script_run`), pressed from four new functions in `engine/entry_plc.py`.

**Tech Stack:** Python 2.7 (IronPython, IDE side) and 3 (CLI); pytest; CODESYS ScriptEngine 4.2.0.0 on the WSL benches.

**Spec:** `docs/superpowers/specs/2026-10-21-watcher-online-design.md`. Read it first; this plan argues from it and does not repeat its reasons.

## Global Constraints

- Every file in `engine/`, `cds/`, `cdsint/`, `stub/`, `tools/` stays at or under 400 lines; functions at or under 60 (PRINCIPLES.md, enforced by `tests/test_size_limits.py`). `cdsint/flags.py` and `engine/plc_trip.py` are already past 300: add nothing to `plc_trip.py`, and keep what `flags.py` gains to the `plc` row and its sentences.
- IDE-side code must import under IronPython 2.7 (`tests/test_py27_compile.py`, `tests/test_py2_runtime.py`). No f-strings.
- `cds/ide` may not import `engine` (SPEC D12, `tests/test_layering.py`).
- Permission words, exactly: `connect`, `download`, `trace`, `login`, `online_change`, `run`, `stop`.
- `--method` values, exactly: `download`, `online_change`. One spelling for both the flag value and the list word.
- A plain `plc login` never downloads and never makes an online change. `--method online_change` never downloads in full.
- No dialog is ever left open in the IDE (SPEC D7): an unanswered prompt fails the command.
- Every application state reported is read back from the session after the action.
- New version: `SCRIPT_VERSION = "0.6.0"` (`engine/codesys_constants.py`).

## Review Focus

1. **The project has unsaved edits when `plc login` runs.** `is_uptodate` must reflect the in-memory project, not the file; a refusal must still name what differs. Pinned in Task 4 (`test_an_unsaved_edit_refuses_the_plain_login`).
2. **The caller runs `plc login --method download` twice in a row.** The second must refuse with "log out first", not download again over the live session. Pinned in Task 5.
3. **`plc run -y` while logged out**, e.g. after the person logged out by hand between two agent commands. Must be exit 1 pointing at `plc login`, never an implicit login. Pinned in Task 6.
4. **A settings file that lists only `download`.** The agent must be able to log out afterwards. Pinned in Task 2 (`test_any_login_word_allows_logout`).
5. **A watcher holding a recording receives `plc logout`.** Must be refused by the existing recording gate, the recording untouched. Pinned in Task 7.

---

### Task 0: Worktree

- [ ] **Step 1:** Create a worktree on branch `watcher-online` with superpowers:using-git-worktrees, `cd` into it, and run the whole suite once: `python -m pytest -q`. Expected: all pass. Every later task runs from that directory.

### Task 1: Bench research (R1 to R4, R6, R7 of the spec)

Everything later depends on these answers, so they come first. No product code in this task.

**Files:**
- Modify: `docs/trace-research.md` (new section 17, "Logging in from the watcher", dated, in the style of section 15)
- Probe scripts: the session scratchpad only, never the repo

The bench: a WSL soft PLC and an interactive CODESYS 3.5.21.40 with the watcher running, per the session memory's WSL bench and real-IDE acceptance notes. Use a copy of a bench project with its download files present. Read the controller's audit log after every login to see what really happened. Restore the bench to the program it held before, as section 5.2 of `docs/ethercat-research.md` did, and say so in the section.

- [ ] **Step 1: Answer, from a timer tick through `in_script_run`, each question below, one subsection each, with the audit log lines that prove it.**
  1. R3: with the master cycle changed (online change not possible), what do `login(OnlineChangeOption.Try, False)` and `login(OnlineChangeOption.Force, False)` each do? With the IO mapping changed (possible), do both make an online change? Which one never downloads in full? Name it; Task 5 uses that member.
  2. R2: delete the copy's `.compileinfo`, `.bootinfo`, `.bootinfo_guids`. What is `is_uptodate` then? Does a `Keep` login download?
  3. R1: download a different program onto the controller from a second copy, then, from the first (unchanged, `is_uptodate` true), log in with `Keep`. Does it change the controller? Does the `.bootinfo_guids` versus `Application.app` header comparison (`engine/plc_identity.py` `judged`) catch it, and does the device connection it needs (`create_online_device`, file pull, `disconnect`) disturb anything when nobody is logged in?
  4. R4: does a script login in the interactive IDE raise any dialog (credentials, "the address differs", "the application does not exist")? Does setting `online.auth_fallback_modes` (`engine/plc_link.py` `switch_fallback_off`) persist after the command, so that the person's next manual login gets no credential dialog? What does the bench controller's user management ask?
  5. Which device-node calls give the address the login reaches (`get_gateway`, `get_address`, or what reflection shows)?
  6. After `login(Never, False)`: application state (expected `stop`). After the online change: state unchanged? Does `create_boot_application()` after an online change rewrite `Application.crc`?
  7. R7: how long the full download login holds the IDE's message loop on the bench application, against the default `--timeout` of 120 s.
- [ ] **Step 2: Add a row per answer to the section's "answers in one table"**, and a "Not verified" list.
- [ ] **Step 3: Decide R1 by the spec's rule.** If question 3 found a change that `is_uptodate` misses and the identity check catches harmlessly, Task 4 includes the identity check (marked there). If nothing catches it, stop and bring it to the owner before Task 4: the spec says refuse that case rather than ship the hole, and how to detect it is then an open question.
- [ ] **Step 4: Commit** `docs/trace-research.md`: "Research: logging in from the watcher".

### Task 2: Seven permission words, and the gate that maps a command to them

**Files:**
- Modify: `cds/core/settings.py` (the `PLC_ACTIONS` tuple and `ACTIONS` string near line 35; `_actions`)
- Modify: `cds/ide/permit.py`
- Modify: `cds/ide/entries.py` (`_not_allowed`, `run`)
- Modify: every importer of `settings.PLC_ACTIONS` (`grep -rn PLC_ACTIONS`). `cdsint/flags.py` uses it as the `plc` row's `action`; give that row its own `PLC_COMMANDS = ("connect", "download", "trace")` here, and Task 3 extends it
- Test: `tests/test_plc_permit.py`, `tests/test_core_settings.py`

**Interfaces:**
- Produces: `settings.PLC_WORDS = ("connect", "download", "trace", "login", "online_change", "run", "stop")` (replaces `PLC_ACTIONS`, which is deleted); `settings.PLC_METHODS = ("download", "online_change")`.
- Produces: `permit.words_for(action: str, args: dict) -> tuple` — any one word in it allows the command. `login` → `(args["method"],)` when a method is given, else `("login",)`; `logout` → `("login", "download", "online_change")`; every other action → `(action,)`.
- Produces: `permit.refusal(projects_obj, action, args=None) -> str | None`; `permit.record(projects_obj, word) -> dict` (unchanged shape; `action` holds the first word of `words_for`).
- Produces: `entries._not_allowed(ide_globals, command, args)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_plc_permit.py`:
  - `test_the_seven_words_are_allowed_in_the_order_spec_lists_them`: list written as all seven reversed; `permit.granted(...) == list(settings.PLC_WORDS)`.
  - `test_login_with_a_method_needs_that_methods_word`: allowed `["login"]`; `permit.refusal(p, "login", {"method": "download"})` is not None and contains `'"download"'`; with allowed `["download"]` it is None.
  - `test_plain_login_needs_the_login_word`: allowed `["download", "online_change"]`; refusal for `("login", {})` is not None.
  - `test_any_login_word_allows_logout`: for each of `login`, `download`, `online_change` alone, `permit.refusal(p, "logout", {})` is None; with `["run", "stop"]` it is not None and says to add one of the three.
  - `test_run_and_stop_are_separate_words`: allowed `["run"]` allows `run` and refuses `stop`.
  - `test_a_refused_login_method_does_not_load_the_engine`: as the existing `test_the_refused_command_does_not_even_load_the_engine`, through `press(ide(allowed=["login"]), "login", {"method": "download", "yes": True})`; `denied["action"] == "download"`.
  - In `tests/test_core_settings.py`: `"online_change"` and `"Run"` read back as `["online_change", "run"]`; `"online-change"` is refused as not one of the words.
- [ ] **Step 2: Run** `python -m pytest tests/test_plc_permit.py tests/test_core_settings.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** the interfaces above. The refusal sentence for several words reads "Add one of "login", "download", "online_change" to that list"; for one word it keeps today's wording. `run()` passes `args` to `_not_allowed`. Update the comment above `PLC_WORDS`: one word per thing a project may allow, not one per command.
- [ ] **Step 4: Run** `python -m pytest -q`. Expected: all pass (the old permit tests still hold).
- [ ] **Step 5: Commit**: "Grow the plc list to seven words and gate a command by any of its words".

### Task 3: The command line, the watcher's table and the confirmations

**Files:**
- Modify: `cdsint/flags.py` (the `plc` row, its sentences)
- Modify: `cdsint/command_row.py` (one new flag kind)
- Modify: `cds/ide/entries.py` (`SCRIPTS`, `HEADLESS_REFUSES`, `WATCHER_REFUSES` text)
- Modify: `cds/core/dialogs.py`, `cds/ide/silent.py` (the title table near line 45)
- Test: `tests/test_plc_cli.py`, `tests/test_cli_surface.py`, `tests/test_silent.py`

**Interfaces:**
- Consumes: `settings.PLC_METHODS` (Task 2).
- Produces: `flags.PLC_COMMANDS = ("connect", "download", "trace", "login", "logout", "run", "stop")` as the `plc` row's `action`.
- Produces: command-file args `method` (`None`, `"download"` or `"online_change"`), `no_boot_app` (`None` or `True`), `yes`.
- Produces: `SCRIPTS["plc login"] = ("entry_plc.py", "log_in")`, `"plc logout"` → `"log_out"`, `"plc run"` → `"run_application"`, `"plc stop"` → `"stop_application"` (not `run`/`stop`: entry_plc.py is exec'd into the IDE's script namespace, and `record()`'s docstring records what a shadowed name cost).
- Produces: `dialogs.CONFIRM_PLC_ONLINE_CHANGE = "Confirm PLC Online Change"`, `CONFIRM_PLC_RUN = "Confirm PLC Run"`, `CONFIRM_PLC_STOP = "Confirm PLC Stop"`, each answered by `("yes", None)` in silent.py. `--method download` reuses `CONFIRM_PLC_DOWNLOAD`.

- [ ] **Step 1: Write the failing tests** (parser tests in the style of `tests/test_plc_cli.py`):
  - `--target X plc login` parses; `args == {"method": None, "no_boot_app": None, ...}`.
  - `--target X plc login --method online_change -y --no-boot-app` parses with those three values.
  - `--method online-change` and `--method full` exit 2 (argparse choices).
  - `--project P --install I plc login` (and `logout`, `run`, `stop`) exit 2 with a message saying it has only the `--target` form.
  - `--target X plc login --gateway 1.2.3.4` exits 2 (the device node chooses the controller).
  - `--target X plc logout --method download`, `plc run --method download`, `plc stop --no-boot-app` exit 2.
  - `--target X plc trace --name T --job J -y` still exits 2, and its sentence no longer claims only `plc download` confirms anything.
  - `tests/test_silent.py`: each new title is answered by `yes`, and without `yes` raises NeedsInput.
- [ ] **Step 2: Run** those test files. Expected: FAIL.
- [ ] **Step 3: Implement.** A `CHOICE`-style kind for `--method` with `choices=settings.PLC_METHODS`, default None. `action_forms` gains the four new actions as `(WATCHER, SESSION_IN_THE_IDE)`, a new sentence: "It logs this IDE's own application in or out, or starts or stops it, so it runs in the watcher of the IDE that holds the session." `takes`: `login` → `("method", "no_boot_app", "yes")`, `logout` → `()`, `run`/`stop` → `("yes",)`. Replace `ONLY_DOWNLOAD` with a sentence naming every action that takes `-y`. Rewrite `CONTROLLER_LOGIN` and `WATCHER_REFUSES`: `connect` stays `--project`-only because it reads the controller through a device connection of its own; `plc download` in the watcher points at `plc login --method download -y`. `HEADLESS_REFUSES` gains the four new commands.
- [ ] **Step 4: Run** `python -m pytest -q`. Expected: all pass, including `tests/test_flag_allow_lists.py` and `tests/test_size_limits.py`.
- [ ] **Step 5: Commit**: "Parse plc login, logout, run and stop in the watcher form".

### Task 4: Plain login and logout

**Files:**
- Create: `engine/plc_session.py`
- Modify: `engine/entry_plc.py` (add `log_in`, `log_out`; module docstring)
- Modify: `tests/plc_fakes.py` (`Session`, `Application`, `OnlineChangeOption`)
- Create: `tests/test_plc_session.py`

**Interfaces:**
- Consumes: `Trip.find_the_project`, `Trip.name_the_application`, `Trip.note`, `Trip.failed`, `Trip.result` (`engine/plc_trip.py`); `ide_private.in_script_run(online_api, call)`; `plc_download.state_of(session)`.
- Produces: `class SessionTrip(Trip)` in `engine/plc_session.py` with `__init__(action, args, ide_globals)`, `run(steps) -> dict` (runs `first_problem(steps)` inside `in_script_run`, then `failed` or `verdict`), and steps `open_session()`, `not_logged_in_yet()`, `nothing_to_change()`, `log_in_keep()`, `log_out()`, `read_state()`. `self.found` keys for these commands: `logged_in` (bool), `state` (str), `address` (str or None, per Task 1 question 5), `changed` (`"nothing"`, `"download"`, `"online_change"`), `boot_application` (bool), `uptodate` (bool or None), `online_change_possible` (bool or None), `methods` (list).
- Produces: `entry_plc.log_in()`, `entry_plc.log_out()`.
- Fakes: `Session.is_logged_in` (False until `login`, False again after `logout`), `Session.stop()`, `Session.login` sets `application_state` from a per-option table the test controls; `Application.is_uptodate = True`, `Application.is_online_change_possible = True`; `OnlineChangeOption.Try`, `.Force`.

- [ ] **Step 1: Write the failing tests** in `tests/test_plc_session.py`, each through `press(ide(allowed=["login"]), "login", {...})`:
  - `test_an_unchanged_copy_logs_in_with_keep`: session calls `== [("login", "keep", False)]`; `data["logged_in"] is True`, `data["changed"] == "nothing"`, `data["state"] == "run"`.
  - `test_already_logged_in_does_nothing_and_succeeds`: session logged in beforehand; no calls; ok; summary says already.
  - `test_an_unsaved_edit_refuses_the_plain_login`: `is_uptodate = False`, `is_online_change_possible = True`; not ok; no `login` call; `data["methods"] == ["download", "online_change"]`; `needs_input` is None.
  - `test_a_change_online_change_cannot_carry_offers_only_download`: `is_online_change_possible = False`; `data["methods"] == ["download"]`.
  - `test_an_ide_without_is_uptodate_is_refused`: attribute absent; not ok; no login call.
  - `test_another_client_logged_in_says_so`: `login` raises the `ALREADY_LOGGED_IN` text `engine/plc_trace.py` matches; summary says another client is logged in.
  - `test_logout_logs_out_and_reports_it`, `test_logout_when_logged_out_succeeds_saying_so`.
  - `test_every_online_call_runs_inside_one_script_run`: monkeypatch `ide_private.in_script_run` to count calls; exactly one per command.
  - If Task 1 step 3 kept the identity check: `test_a_controller_holding_another_program_refuses_the_plain_login`, built with `download_info` and a device whose `Application.app` header differs, as `tests/test_plc_identity.py` does.
- [ ] **Step 2: Run** `python -m pytest tests/test_plc_session.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `SessionTrip` and the two entries. Reuse `plc_trace.py`'s handling of "another client" by moving its matcher to a function both import, not by copying it. The refusal summary names what differs, the `--method` values, and that nothing was done.
- [ ] **Step 4: Run** `python -m pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit**: "plc login and logout in the watcher".

### Task 5: Login with a method

**Files:**
- Modify: `engine/plc_session.py`, `engine/entry_plc.py` (confirmation questions beside `DOWNLOAD_QUESTION`)
- Modify: `engine/plc_crc.py` only if R5 below needs a new function
- Test: `tests/test_plc_session.py`

**Interfaces:**
- Consumes: Task 1's answer to question 1 (the `OnlineChangeOption` member that never downloads in full), as module constant `ONLINE_CHANGE = "<Member>"` in `engine/plc_session.py`, with a comment pointing at the research subsection.
- Produces: steps `confirmed()`, `method_applies()` (online change possible, else refuse pointing at `--method download`), `log_in_with(option_name)`, `write_boot_application()`, `forget_the_record()`.

- [ ] **Step 1: Write the failing tests:**
  - `test_without_yes_a_method_asks_and_nothing_logs_in`: `needs_input` present, no session calls (as `test_without_yes_the_download_asks_and_nothing_logs_in`).
  - `test_download_logs_in_never_and_writes_the_boot_application`: calls `== [("login", "never", False), ("create_boot_application",)]`, no `start`; `data["changed"] == "download"`, `data["state"] == "stop"`, `data["boot_application"] is True`.
  - `test_download_downloads_even_when_nothing_differs`.
  - `test_no_boot_app_skips_it`: for both methods, no `create_boot_application` call, `data["boot_application"] is False`.
  - `test_online_change_that_is_not_possible_touches_nothing`: no calls; summary points at `--method download`.
  - `test_online_change_keeps_the_running_state`: state `run` before and after; calls use the `ONLINE_CHANGE` member.
  - `test_online_change_with_nothing_different_writes_no_boot_application`.
  - `test_a_method_while_logged_in_says_log_out_first`: no calls (Review Focus 2).
  - `test_a_download_that_raises_says_the_controller_may_be_stopped`, as `_download_on` words it.
  - `test_a_watcher_download_never_leaves_a_stale_match`: with `recorded()` holding an entry for the controller, after a download `plc_crc` no longer answers MATCH for it. Implement R5 the cheapest way that satisfies this; removing the entry is enough if reading the new CRC needs a device connection Task 1 found harmful.
- [ ] **Step 2: Run** the file. Expected: FAIL.
- [ ] **Step 3: Implement.** The download question says what this does differently from the `--project` download: it leaves the application stopped.
- [ ] **Step 4: Run** `python -m pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit**: "plc login --method download and online_change".

### Task 6: Run and stop

**Files:**
- Modify: `engine/plc_session.py`, `engine/entry_plc.py` (`run_application`, `stop_application`, their questions)
- Test: `tests/test_plc_session.py`

- [ ] **Step 1: Write the failing tests:**
  - `test_run_starts_and_reads_run_back`, `test_stop_stops_and_reads_stop_back`.
  - `test_run_when_running_succeeds_saying_so` (no `start` call); same for stop.
  - `test_run_while_logged_out_points_at_plc_login` (no calls; Review Focus 3).
  - `test_a_state_that_does_not_follow_fails`: `start` leaves `stop`; not ok, summary names both states.
  - `test_without_yes_run_asks`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `python -m pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit**: "plc run and plc stop in the watcher".

### Task 7: Where the new commands meet the watcher's trace

**Files:**
- Modify: `engine/plc_trace_watch.py` (`NOT_LOGGED_IN`, module docstring), `engine/plc_trace.py` (`application_runs` sentence, watcher form only)
- Test: `tests/test_plc_trace_watch.py`, `tests/test_watcher*.py` or wherever the recording gate is tested (`grep -rn WHILE_RECORDING tests`)

- [ ] **Step 1: Write the failing tests:** the watcher's not-logged-in refusal contains `plc login`; its not-running refusal contains `plc run -y`; while a recording is held, `plc logout`, `plc stop` and `plc login` are refused by the recording gate and the recording's `poll` is unaffected (Review Focus 5).
- [ ] **Step 2: Run.** Expected: the message tests FAIL; the gate test may already pass, which is fine: it pins the behaviour.
- [ ] **Step 3: Implement.** Delete the docstring claims that cdsint never logs in from the watcher.
- [ ] **Step 4: Run** `python -m pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit**: "Point the watcher's trace refusals at plc login and plc run".

### Task 8: Documents and version

**Files:** `docs/SPEC.md`, `docs/WATCHER.md`, `docs/REFERENCE.md`, `skills/` (the `cdsint` skill), `CHANGELOG.md`, `engine/codesys_constants.py`

- [ ] **Step 1: SPEC.** Rewrite D8 (the reason it reverses, from spec section 1). Section 2: replace the "No online change" non-goal with what is still not done. 4.3: the plain-login refusal is a failure with `data.methods`, not `needs_input`. 4.4 and 6.5: the seven words, `words_for`'s mapping, which commands need `-y`. 6.6: its first line. A new subsection under 6.8 or after 6.6 for the four commands, written from spec section 5 and Task 1's measurements. The command table in section 4. The verified-on table near the end: the new private-member use, if any.
- [ ] **Step 2: WATCHER.md** section 4 table; **REFERENCE.md** the four commands with one example each; **the skill**: when an agent should log in, and that a refused plain login is a decision to bring back, not a flag to add.
- [ ] **Step 3: Version.** `SCRIPT_VERSION = "0.6.0"`; a `CHANGELOG.md` entry in the existing style.
- [ ] **Step 4: Run** `python -m pytest -q` (includes `tests/test_doc_links.py`, `tests/test_release_notes.py`). Expected: all pass.
- [ ] **Step 5: Commit**: "Document plc login, logout, run and stop; 0.6.0".

### Task 9: Acceptance on the bench

- [ ] **Step 1:** Link the worktree's body into the bench IDE the way the session memory's e2e recipe says, start the watcher in an interactive IDE, and run every row of spec section 8 through the real `cdsint` command, reading the controller's audit log after each.
- [ ] **Step 2:** Record the runs (command, exit code, the audit log lines) as the last subsection of `docs/trace-research.md` section 17, and fill the SPEC verified-on table's CODESYS column.
- [ ] **Step 3:** Restore the bench program and say in the subsection what it was left holding.
- [ ] **Step 4: Commit**: "Acceptance: plc login, logout, run and stop on the bench".
- [ ] **Step 5:** superpowers:finishing-a-development-branch. Publishing the 0.6.0 release is the owner's call; ask.
