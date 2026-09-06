# -*- coding: utf-8 -*-
"""
codesys_ui.py - Modern UI components for CODESYS scripts
"""
from __future__ import print_function

import clr
try:
    clr.AddReference("System.Windows.Forms")
    clr.AddReference("System.Drawing")
    from System.Windows.Forms import (
        Form, Label, Button, FormBorderStyle,
        DialogResult, FormStartPosition, NotifyIcon, ToolTipIcon, TextBox,
        FlatStyle, Timer
    )
    from System.Drawing import (
        Size, Point, Font, FontStyle, SystemIcons, Color, ContentAlignment
    )
except:
    # Fallback if forms not available (e.g. Linux/Headless)
    pass


# Each live toast, until its timer fires. Nothing else refers to a tray icon
# or its timer once show_toast returns, and .NET objects nobody holds get
# collected: a collected NotifyIcon disappears from the tray mid-balloon and
# a collected Timer never ticks, so the icon would stay there forever.
_TOASTS = []


def show_toast(title, message, timeout=3000):
    """Put a tray balloon up and return at once, without blocking the IDE.

    The wait before the icon is taken down is a WinForms timer on the IDE's
    own message loop, not a thread that sleeps (SPEC D5). The old version
    started a .NET thread purely so the script could return while the balloon
    was up; a timer buys the same thing and puts no second thread anywhere
    near an API that is not thread-safe.
    """
    try:
        notification = NotifyIcon()
        notification.Icon = SystemIcons.Information
        notification.Visible = True
        notification.ShowBalloonTip(timeout, title, message, ToolTipIcon.Info)
    except Exception as e:
        # A notification nobody can show is not worth failing the command it
        # was announcing, but it should not vanish without a word either.
        print("show_toast error: " + str(e))
        return

    timer = Timer()
    # A second past the balloon's own lifetime: disposing the icon while
    # Windows is still showing the balloon takes the balloon down early.
    timer.Interval = timeout + 1000
    live = [notification, timer]
    _TOASTS.append(live)

    def put_it_away(sender=None, event_args=None):
        # Runs on the IDE's message loop, where there is no script left
        # to catch anything: an exception out of here is an unhandled
        # exception in the IDE's own process, which puts a
        # thread-exception dialog on top of whatever the person was
        # doing. A tray icon that will not go away is the smaller bug.
        try:
            timer.Stop()
            try:
                notification.Visible = False
                notification.Dispose()
            finally:
                timer.Dispose()
                _TOASTS.remove(live)
        except Exception as e:
            print("show_toast cleanup error: " + str(e))

    timer.Tick += put_it_away
    timer.Start()

def ask_yes_no(title, message):
    """
    Shows a standard Windows Yes/No dialog. 
    Returns True for Yes, False for No or Cancel.
    Avoids the CODESYS radio-button based choose dialog.
    """
    try:
        from System.Windows.Forms import MessageBox, MessageBoxButtons, MessageBoxIcon, DialogResult
        result = MessageBox.Show(message, title, MessageBoxButtons.YesNo, MessageBoxIcon.Question)
        return result == DialogResult.Yes
    except Exception as e:
        print("ask_yes_no error: " + str(e))
        # Fallback to pure CODESYS prompt if WinForms fails
        try:
            import __main__
            if hasattr(__main__, "system"):
                res = __main__.system.ui.prompt(message, __main__.PromptChoice.YesNo, __main__.PromptResult.No)
                return res == __main__.PromptResult.Yes
        except:
            pass
        return False

class DirectoryChoiceForm(Form):
    """Modern choice dialog for setting the sync directory"""
    def __init__(self, title, message):
        self.Text = title
        self.Size = Size(450, 270) # Increased height for better padding
        self.FormBorderStyle = FormBorderStyle.FixedDialog
        self.StartPosition = FormStartPosition.CenterScreen
        self.MaximizeBox = False
        self.MinimizeBox = False
        self.BackColor = Color.FromArgb(250, 250, 250)
        self.choice = "cancel"

        # Main Text
        lbl_msg = Label()
        lbl_msg.Text = "Sync Directory Setup"
        lbl_msg.Font = Font("Segoe UI", 14, FontStyle.Bold)
        lbl_msg.Location = Point(20, 20)
        lbl_msg.AutoSize = True
        lbl_msg.ForeColor = Color.FromArgb(50, 50, 50)
        self.Controls.Add(lbl_msg)

        lbl_sub = Label()
        lbl_sub.Text = "Choose how you would like to configure the primary sync folder."
        lbl_sub.Font = Font("Segoe UI", 9)
        lbl_sub.Location = Point(22, 50)
        lbl_sub.AutoSize = True
        lbl_sub.ForeColor = Color.Gray
        self.Controls.Add(lbl_sub)

        # Buttons - Big and Modern (Removed emojis for better compatibility)
        btn_browse = Button()
        btn_browse.Text = "  Browse Folder...\n  (Select via file explorer)"
        btn_browse.Font = Font("Segoe UI", 10)
        btn_browse.TextAlign = ContentAlignment.MiddleLeft
        btn_browse.Location = Point(25, 90)
        btn_browse.Size = Size(385, 55)
        btn_browse.BackColor = Color.White
        btn_browse.FlatStyle = FlatStyle.Flat
        btn_browse.FlatAppearance.BorderColor = Color.LightGray
        btn_browse.Click += self._on_browse
        self.Controls.Add(btn_browse)

        btn_manual = Button()
        btn_manual.Text = "  Enter Manually...\n  (Use relative ./ paths or text input)"
        btn_manual.Font = Font("Segoe UI", 10)
        btn_manual.TextAlign = ContentAlignment.MiddleLeft
        btn_manual.Location = Point(25, 155)
        btn_manual.Size = Size(385, 55)
        btn_manual.BackColor = Color.White
        btn_manual.FlatStyle = FlatStyle.Flat
        btn_manual.FlatAppearance.BorderColor = Color.LightGray
        btn_manual.Click += self._on_manual
        self.Controls.Add(btn_manual)

    def _on_browse(self, sender, event):
        self.choice = "yes"
        self.DialogResult = DialogResult.OK
        self.Close()

    def _on_manual(self, sender, event):
        self.choice = "no"
        self.DialogResult = DialogResult.OK
        self.Close()

def show_directory_choice_dialog(title, message):
    """Browse or type? Returns "yes" to browse, "no" to type, "cancel" to stop.

    Only ever reached with a person at the keyboard: cds/ide/silent.py
    replaces show_sync_folder_dialog above this, so a headless run never gets
    here to open a window nobody could close.
    """
    form = DirectoryChoiceForm(title, message)
    form.ShowDialog()
    return form.choice


class SyncFolderPathForm(Form):
    """Type the sync folder instead of browsing for it.

    Browsing cannot express "./", and a relative path is the one that
    survives the project being opened on another machine, so the manual
    route is not a fallback -- it is the only way to ask for one.

    The answer is written to `settings_path` and the window says so, because
    that file is where every later change to it is made: there is no dialog
    to come back to (SPEC 6.7).
    """
    def __init__(self, settings_path):
        self.Text = "Enter Sync Directory Path"
        self.Size = Size(500, 220)
        self.FormBorderStyle = FormBorderStyle.FixedDialog
        self.StartPosition = FormStartPosition.CenterScreen
        self.MaximizeBox = False
        self.MinimizeBox = False

        lbl_instructions = Label()
        lbl_instructions.Text = "Examples:\n" + \
                                "  ./                    - Project directory\n" + \
                                "  ./folderName/         - 'folderName' beside the project file\n" + \
                                "  C:\\MySync\\            - Absolute path\n\n" + \
                                "Relative paths (starting with ./) are resolved against the project file.\n" + \
                                "Saved to: " + str(settings_path)
        lbl_instructions.Location = Point(20, 15)
        lbl_instructions.Size = Size(460, 100)
        self.Controls.Add(lbl_instructions)

        lbl_path = Label()
        lbl_path.Text = "Path:"
        lbl_path.Location = Point(20, 125)
        lbl_path.AutoSize = True
        self.Controls.Add(lbl_path)

        self.txt_path = TextBox()
        self.txt_path.Location = Point(70, 122)
        self.txt_path.Size = Size(400, 20)
        self.txt_path.Text = "./"
        self.Controls.Add(self.txt_path)

        btn_ok = Button()
        btn_ok.Text = "OK"
        btn_ok.DialogResult = DialogResult.OK
        btn_ok.Location = Point(300, 155)
        btn_ok.Size = Size(80, 25)
        self.Controls.Add(btn_ok)
        self.AcceptButton = btn_ok

        btn_cancel = Button()
        btn_cancel.Text = "Cancel"
        btn_cancel.DialogResult = DialogResult.Cancel
        btn_cancel.Location = Point(390, 155)
        btn_cancel.Size = Size(80, 25)
        self.Controls.Add(btn_cancel)
        self.CancelButton = btn_cancel


def show_sync_folder_dialog(system, settings_path):
    """Ask a person where the sync folder is. Returns a path, or None.

    The one door to the whole thing, browse and type alike, because
    cds/ide/silent.py patches this name to refuse when nobody is there
    (SPEC 6.1). A second door would open a modal window inside the IDE's
    message loop with no one to close it.

    `settings_path` is the file the answer goes into. The window shows it,
    and the stand-in names it in its refusal, which is how a headless caller
    finds out which file to write by hand.
    """
    ans = show_directory_choice_dialog(
        "Project Sync Configuration",
        "Would you like to BROWSE for a folder or enter the path manually?")
    if ans == "cancel":
        return None
    if ans == "yes":
        return system.ui.browse_directory_dialog(
            "Select Sync Directory for this Project", "")
    form = SyncFolderPathForm(settings_path)
    if form.ShowDialog() != DialogResult.OK:
        return None
    return form.txt_path.Text.strip()
