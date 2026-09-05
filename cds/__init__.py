# -*- coding: utf-8 -*-
"""cds — the watcher and the file protocol the cdsint CLI speaks to it.

Two layers, and the boundary is the point (SPEC D12):

    cds.core  pure Python, no CODESYS imports, unit-tested in CI. The
              protocol the watcher and the CLI both speak.
    cds.ide   the only layer allowed near the CODESYS API. It runs under
              IronPython 2.7 inside the IDE, and does pipework only: the
              protocol endpoints, the timer, the stand-in UI, the status
              window. Walking the object tree is engine/'s job, and the
              dependency never points back this way.

docs/WATCHER.md is the whole story.
"""
