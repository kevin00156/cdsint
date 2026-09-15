---
name: Bug report
about: It did not do what it says it does
title: ''
labels: bug
assignees: ''

---

**What you ran**

The exact command, or the menu entry if this was the IDE half.

```
cdsint ...
```

**What it did**

Paste the output, and the exit code with it — `echo $LASTEXITCODE` in
PowerShell. If a log was written, the last twenty lines beat a summary of them.

**What you expected instead**

**Which IDE**

Run `cdsint installs` and paste the row for the IDE you used. If `installs` is
itself what is broken, name the product and version by hand: CODESYS 3.5 SP19,
DIADesigner-AX 1.10, PLC Designer 4.0.

- The IDE was: open in front of me / not open, headless / does not matter
- `pip show cdsint` version:
- Windows version:
- `python -V`:

**If an object failed to export or import**

Run `cdsint discover` and paste the lines for the objects involved. It names
every object and the kind it counted as, which is what tells us whether the kind
is unknown or the GUID is.

**Anything else**

A `.st` file that reproduces it, if you can share one.
