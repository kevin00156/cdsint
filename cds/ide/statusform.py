# -*- coding: utf-8 -*-
"""The little window that says the watcher is alive.

WinForms and nothing else. It is handed a picture — headline, level, project,
detail — by cds/ide/display.py and paints it; every decision about what that
picture should be is made there, where CPython can test it.

Shown with Show(), never ShowDialog(): a modal would hold the main thread and
put the IDE straight back in the state the whole timer design exists to avoid
(docs/WATCHER.md 6). Owned by the IDE's main window rather than TopMost,
so it floats over the IDE and minimises with it instead of sitting on top of
whatever else the user is doing.
"""
from __future__ import print_function

import os

from cds.core import ipc

WIDTH = 320
HEIGHT = 110
MARGIN = 24  # from the inside of the owner's bottom-right corner

COLOURS = {
    "idle": (223, 240, 216),    # calm green
    "busy": (252, 235, 208),    # working orange
    "failed": (245, 205, 205),  # something went wrong, and still is
}


def placement_path():
    """Beside the instances directory, not inside it: this is a preference."""
    return os.path.join(os.path.dirname(ipc.default_root()), "statusform.json")


class StatusForm(object):
    """A borderless-ish tool window pinned to the IDE's bottom-right corner."""

    def __init__(self, on_stop):
        import clr
        clr.AddReference("System.Windows.Forms")
        clr.AddReference("System.Drawing")
        from System.Windows.Forms import (
            Application, FormBorderStyle, Form, FormStartPosition)
        from System.Drawing import Color, Size

        self._forms = Application
        self._colour = Color
        self.on_stop = on_stop
        self._stopping = False

        self.form = Form()
        self.form.Text = "cdsint watcher"
        self.form.FormBorderStyle = FormBorderStyle.FixedToolWindow
        self.form.StartPosition = FormStartPosition.Manual
        self.form.ShowInTaskbar = False
        self.form.Size = Size(WIDTH, HEIGHT)
        self._build_controls()
        # Closing the window means the same as pressing Stop; anything else
        # would leave a watcher running that the user believes they shut down.
        self.form.FormClosing += self._closing

    def _build_controls(self):
        """The three lines of text and the button, top to bottom."""
        from System.Windows.Forms import Button, Label
        from System.Drawing import (
            ContentAlignment, Font, FontStyle, Point, Size)

        self.headline = Label()
        self.headline.Font = Font("Segoe UI", 14, FontStyle.Bold)
        self.headline.Location = Point(10, 8)
        self.headline.Size = Size(WIDTH - 26, 28)
        # IronPython will not coerce a bare int into a .NET enum, so name it.
        self.headline.TextAlign = ContentAlignment.MiddleLeft

        self.who = Label()
        self.who.Location = Point(12, 40)
        self.who.Size = Size(WIDTH - 28, 16)

        self.detail = Label()
        self.detail.Location = Point(12, 58)
        self.detail.Size = Size(WIDTH - 28, 16)

        self.stop = Button()
        self.stop.Text = "Stop"
        self.stop.Size = Size(70, 24)
        self.stop.Location = Point(WIDTH - 96, 78)
        self.stop.Click += self._stop_clicked

        for control in (self.headline, self.who, self.detail, self.stop):
            self.form.Controls.Add(control)

    # -- showing -----------------------------------------------------------

    def show(self):
        owner = self._owner()
        if owner is not None:
            self.form.Owner = owner
        self.form.Location = self._corner(owner)
        self.form.Show()
        return self

    def _owner(self):
        """The IDE's main window, or None if it cannot be identified."""
        try:
            forms = list(self._forms.OpenForms)
        except Exception:
            return None
        for form in forms:
            if form is not self.form and form.Visible:
                return form
        return None

    def _corner(self, owner):
        """Where the user last dragged it, else inside the owner's corner."""
        from System.Drawing import Point
        saved = ipc.read_json(placement_path())
        if saved and "x" in saved and "y" in saved:
            return Point(int(saved["x"]), int(saved["y"]))
        if owner is None:
            return Point(80, 80)
        return Point(owner.Left + owner.Width - WIDTH - MARGIN,
                     owner.Top + owner.Height - HEIGHT - MARGIN * 2)

    # -- painting ----------------------------------------------------------

    def update(self, picture):
        """Paint one picture from cds.ide.display.describe()."""
        red, green, blue = COLOURS.get(picture["level"], COLOURS["idle"])
        self.headline.Text = picture["headline"]
        self.form.BackColor = self._colour.FromArgb(red, green, blue)
        self.who.Text = "%s  ·  %s" % (picture["project"],
                                       picture["instance_id"])
        self.detail.Text = picture["detail"]
        self.form.Refresh()

    # -- going away --------------------------------------------------------

    def close(self):
        """Called when the watcher stops, from anywhere.

        Broad, and loud rather than silent. This runs while the watcher is
        shutting down, sometimes because the user closed the window and this
        is the watcher catching up, so the form may already be disposed --
        and a window that will not tidy itself away must not stop a shutdown.
        Naming the .NET exception would be a guess about a path only a person
        at the machine reaches; saying what happened is not.
        """
        self._stopping = True
        try:
            self._remember_where()
            self.form.Close()
        except Exception:
            import traceback
            print("statusform: closing the window failed\n"
                  + traceback.format_exc())

    def _remember_where(self):
        """Save where the user dragged the window to.

        Same shape as close(): broad and loud. The write can fail, and so can
        reading a coordinate off a form that is going away underneath us; a
        window position is not worth an error path either way, but it is
        worth a line saying it was not saved.
        """
        try:
            ipc.write_json(placement_path(), {"x": self.form.Left,
                                              "y": self.form.Top})
        except Exception:
            import traceback
            print("statusform: could not remember where the window was\n"
                  + traceback.format_exc())

    def _stop_clicked(self, sender, args):
        self._ask_to_stop()

    def _closing(self, sender, args):
        if not self._stopping:
            self._ask_to_stop()

    def _ask_to_stop(self):
        """Hand the decision back to whoever owns the watcher."""
        self._remember_where()
        self._stopping = True
        try:
            self.on_stop()
        except Exception:
            import traceback
            print("statusform: stopping failed\n" + traceback.format_exc())
