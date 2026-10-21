# -*- coding: utf-8 -*-
"""What came back from running one engine body: verdict, words, output, needs.

Data only. cds/ide/silent.py is what produces these and cds/ide/entries.py is
what turns one into the result record both callers write; keeping the shape
here is what lets either of those be read without the other.

Whether a run worked is the body's return value (SPEC D11). The messages are
what a person would have read on their way past, and they are never the
verdict — that was the old rule, and it made a harmless warning in the middle
of a good export into a failed command.
"""
from __future__ import print_function

from cds.core import commands, trace_run


class NeedsInput(BaseException):
    """A dialog wanted an answer that the command did not carry.

    Deliberately not an Exception. This codebase wraps IDE calls in broad
    `except Exception` blocks — engine/entry_build.py's build step is one —
    that would swallow it and let the script carry on as though someone had
    clicked. Same reasoning as KeyboardInterrupt.
    """

    def __init__(self, question, arg=None):
        BaseException.__init__(self, question)
        self.question = question
        self.arg = arg

    def as_record(self):
        return {"question": self.question, "arg": self.arg}


class Outcome(object):
    """One run of one body, as the layer above it needs to read it.

    `result` is what the body returned — engine/entry.py `result()` builds it.
    """

    def __init__(self, messages, stdout_tail, needs=None, error=None,
                 result=None, denied=None):
        self.messages = messages
        self.stdout_tail = stdout_tail
        self.needs = needs
        self.error = error
        self.result = result
        # Set when the project's own policy refused the command before it ran
        # (cds/ide/permit.py). Carried separately from error because it is
        # what earns exit 5 (SPEC 4.3).
        self.denied = denied

    @classmethod
    def not_run(cls, error, denied=None):
        """A command stopped at the gate: no words, no output, just the reason.

        Still an Outcome rather than a bare string, because the caller cannot
        tell a refusal from a failure by reading prose — `denied` is the field
        that earns exit 5, and matching on wording is a guess, not a decision.
        """
        return cls([], "", error=error, denied=denied)

    @property
    def recording(self):
        """The run still going after the body returned, or None: a watcher
        plc trace (cds/ide/entries.py Pending)."""
        if isinstance(self.result, dict):
            return self.result.get(trace_run.RECORDING)
        return None

    def ok(self):
        return not self.error_text()

    def data(self):
        """The command's own counts, or None if it did not hand any back."""
        if isinstance(self.result, dict):
            return self.result.get("data")
        return None

    def said(self):
        """The messages, ending with the summary of a run that worked.

        A failure's summary is already its error (error_text). A success's
        is the only place a body says what came of it when that was nothing
        -- "already logged in; nothing was done" -- and kept out of the
        record, such a call could not be told from one that acted. A body
        that already said the same words on screen is not repeated.
        """
        summary = self.result.get("summary") if self.ok() else None
        if not summary or summary in [m["text"] for m in self.messages]:
            return list(self.messages)
        return list(self.messages) + [commands.message("info", summary)]

    def error_text(self):
        """The reason this run failed, or None. Never a silent failure."""
        if self.error:
            return self.error
        if self.needs is not None:
            return self.needs.question
        if not isinstance(self.result, dict) or "ok" not in self.result:
            # Every body ends by returning a result (SPEC D11). Coming back
            # without one means it took a give-up path that only print()s,
            # and a caller told "ok" would go on to build code that was
            # never imported.
            return ("the script returned no result; see stdout_tail for what "
                    "it printed")
        if not self.result["ok"]:
            return (self.result.get("summary")
                    or "the script reported failure without saying why")
        return None
