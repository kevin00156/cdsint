# `tools/`

Offline instruments for whoever maintains this. None of them is a cdsint
command and none appears in the Scripts menu (PRINCIPLES 12). Every instrument
in this directory has an entry here; `tests/test_tools_are_documented.py`
fails if one is added and this list is not. A file whose name starts with an
underscore is not an instrument but something the instruments stand on, and
gets a closing note rather than an entry — there is one, `_root.py`.

Some of them run **inside** an IDE, through **Tools > Scripting > Execute
Script File** or `--runscript`; the rest are ordinary CPython you run from a
shell. Each entry below says which, because that is the thing that decides
what you can do with it — no count here, since the count is what goes stale
the next time somebody adds one.

**`tools/call_tree.py`** builds a cross-file call graph from an exported sync
folder. Plain CPython, no IDE:

```
python tools/call_tree.py <sync-dir> MAIN -o call_tree.json
```

It follows calls between project functions and function-block methods across
files, including instances declared in GVLs, tags IEC system calls from
`tools/sys_funcs.json`, and marks whatever it could not resolve.
**`tools/call_tree_parse.py`**, **`tools/call_tree_symbols.py`** and
**`tools/call_tree_resolve.py`** are its three parts — reading `.st` text,
collecting what that text defines, and resolving calls against it. Run
`call_tree.py`; import the parts only if you want the pieces.

Run it from a checkout, not from a copy of the files somewhere else. The
parser reads the `// === IMPLEMENTATION ===` separator from
`engine/codesys_constants.py` rather than carrying its own copy, because two
definitions of the disk format is one too many (SPEC D15) — so it needs
`engine/` and `profiles/` beside it. Three files copied into a scratch
directory stop at `No module named '_root'`.

**`tools/cache_doctor.py`** answers "would the cache actually skip anything on
the next run?" without opening the IDE, and names the reasons it would not:

```
python tools/cache_doctor.py <sync-dir>
```

**`tools/perf_probe.py`** wraps the real engine functions and ranks where a
sync spends its time. Runs inside an IDE that has the project open: **Execute
Script File**, then pick the file. With no argument it profiles an export;
`compare` and `import` are the other two modes, given in the script-arguments
box. The report goes to `perf_probe_<mode>.txt` in the sync folder. Run the
same mode twice — the second run is the one that says whether the cache is
earning its keep.

**`tools/perf_tables.py`** is that probe's two tables: the engine functions it
measures, and the manager methods it measures. Not something you run. It is a
file of its own because a row that names something the engine has renamed
measures nothing and prints nothing, so the report comes out a row short
without saying so — `tests/test_perf_probe.py` reads these tables against the
real engine, and `install_probes()` refuses to run on a stale one.
**`tools/perf_patch.py`** is the wrapping itself — every row of those tables
rebound to a timing wrapper in every namespace that imported it — and
**`tools/perf_report.py`** turns what the wrappers recorded into the ranked
report. Neither is run on its own; `perf_probe.py` is the entry.

**`tools/headless_watch.py`** opens a project in a headless IDE and arms the
watcher in it, so that `--target` has something to talk to without a person
opening the IDE. Runs inside the IDE it starts:

```
<exe> --profile="<name>" --noUI --runscript="<abs path>\tools\headless_watch.py"
```

with `CDSINT_WATCH_PROJECT` naming the `.project`, and optionally
`CDSINT_WATCH_SYNC` and `CDSINT_WATCH_ANSWERS` (`KEY=VALUE,KEY=VALUE`). Under
`--noUI` it parks the process with `system.delay()` — SPEC D5's one stated
exception, and it refuses to park when the IDE has a window.

**`tools/probe_watcher_ui.py`** is the acceptance launcher behind
`docs/WATCHER.md` 8: it builds a throwaway project, arms the watcher the way
**Project_watch** does, and returns, so that somebody can check the IDE is
still clickable. Runs inside the IDE, same `--runscript` shape.

**`tools/probe_click_menu.py`** is the other half of that acceptance, and the
only tool that drives an IDE from outside it: real mouse clicks on the File
menu, counting whether a drop-down appeared.

```
python tools/probe_click_menu.py --pid 1234 --seconds 60 --every 5
```

**`tools/attr_probe.py`** prints what `build_properties` exposes on the first
few objects of the open project, and what each attribute answers. Use it when
a compile attribute (`exclude_from_build` and friends) does not round-trip on
an IDE version: the names differ between versions, and this says what this one
calls them. Runs inside the IDE, same `--runscript` shape. It used to be a
one-shot dump inside `read_ide_attrs()`, costing a `getattr` per object on
every export to answer a question somebody asks once a year.

And the one that is not an instrument: **`tools/_root.py`** puts the install
root on `sys.path` so the others can import `engine/` and `cds/`. Nothing to
run; it is imported.
