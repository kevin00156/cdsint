# -*- coding: utf-8 -*-
"""cds.core — pure Python. NO CODESYS imports, ever (PRINCIPLES.md §4).

The file protocol the in-IDE watcher and the external CLI talk over:

    ipc        where the instance directories are, and how to write a file
               in one that a second process may be reading
    instances  the registration files: heartbeat, liveness, picking a target
    commands   the command and result files, and their queue

And one thing that is not the protocol but belongs to the same tier, because
both sides need it and SPEC D12 forbids engine/ and cds/ide/ from importing
each other:

    props      what the project properties are called (SPEC 4.4)

Everything takes paths and data in and returns data out, so it runs in CI
under CPython 3 and inside the IDE under IronPython 2.7 from one source:
no type annotations, no f-strings, standard library only.

Editing anything here needs the IDE restarted. The menu stubs drop the
`engine` modules from sys.modules so a changed engine is picked up on the
next run; `cds` was never in that set, and adding it would hand a running
watcher and a fresh export two different copies of the same module.
"""

from __future__ import print_function
