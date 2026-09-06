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
        Form, Label, CheckBox, Button, FormBorderStyle,
        DialogResult, FormStartPosition, NotifyIcon, ToolTipIcon, TextBox,
        MessageBox, MessageBoxButtons, MessageBoxIcon, FlatStyle, Timer
    )
    from System.Drawing import Size, Point, Font, FontStyle, SystemIcons, Color, ContentAlignment
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

def ask_yes_no_cancel(title, message):
    """
    Shows a Windows Yes/No/Cancel dialog.
    Returns "yes", "no", or "cancel".
    """
    try:
        from System.Windows.Forms import MessageBox, MessageBoxButtons, MessageBoxIcon, DialogResult
        result = MessageBox.Show(message, title, MessageBoxButtons.YesNoCancel, MessageBoxIcon.Question)
        if result == DialogResult.Yes: return "yes"
        if result == DialogResult.No: return "no"
        return "cancel"
    except Exception as e:
        print("ask_yes_no_cancel error: " + str(e))
        # Fallback to pure CODESYS prompt
        try:
            import __main__
            if hasattr(__main__, "system"):
                res = __main__.system.ui.prompt(message, __main__.PromptChoice.YesNoCancel, __main__.PromptResult.Cancel)
                if res == __main__.PromptResult.Yes: return "yes"
                if res == __main__.PromptResult.No: return "no"
        except:
            pass
        return "cancel"

class SettingsForm(Form):
    def __init__(self, current_settings, version=None):
        self.Text = "CODESYS Sync Settings"
        self.Size = Size(420, 430) # Height fits retention + diagnostics group
        self.FormBorderStyle = FormBorderStyle.FixedDialog
        self.StartPosition = FormStartPosition.CenterScreen
        self.MaximizeBox = False
        self.MinimizeBox = False
        
        # Heading
        lbl = Label()
        lbl.Text = "Configure Sync Behavior"
        lbl.Location = Point(20, 20)
        lbl.AutoSize = True
        lbl.Font = Font("Segoe UI", 12, FontStyle.Bold)
        self.Controls.Add(lbl)
        
        # Version label (top-right corner)
        if version:
            lbl_version = Label()
            lbl_version.Text = "v" + str(version)
            lbl_version.Location = Point(320, 24)
            lbl_version.AutoSize = True
            lbl_version.Font = Font("Segoe UI", 8)
            lbl_version.ForeColor = Color.Gray
            self.Controls.Add(lbl_version)
        
        # Group 1: Export Settings
        y = 60
        self.chk_xml = CheckBox()
        self.chk_xml.Text = "Export Native XML (Visu/Alarms)"
        self.chk_xml.Location = Point(30, y)
        self.chk_xml.Size = Size(350, 24)
        self.chk_xml.Checked = current_settings.get("export_xml", False)
        self.Controls.Add(self.chk_xml)
        
        y += 30
        self.chk_bin = CheckBox()
        self.chk_bin.Text = "Backup .project Binary (Git LFS)"
        self.chk_bin.Location = Point(30, y)
        self.chk_bin.Size = Size(350, 24)
        self.chk_bin.Checked = current_settings.get("backup_binary", False)
        self.Controls.Add(self.chk_bin)

        # Subsection: Backup Name
        y += 30
        lbl_name = Label()
        lbl_name.Text = "Backup Name (Optional):"
        lbl_name.Location = Point(50, y+3)
        lbl_name.AutoSize = True
        self.Controls.Add(lbl_name)
        
        self.txt_backup_name = TextBox()
        self.txt_backup_name.Location = Point(200, y)
        self.txt_backup_name.Size = Size(150, 20)
        self.txt_backup_name.Text = current_settings.get("backup_name", "")
        self.Controls.Add(self.txt_backup_name)

        y += 30
        self.chk_save_exp = CheckBox()
        self.chk_save_exp.Text = "Save Project after Export"
        self.chk_save_exp.Location = Point(30, y)
        self.chk_save_exp.Size = Size(350, 24)
        self.chk_save_exp.Checked = current_settings.get("save_after_export", True)
        self.Controls.Add(self.chk_save_exp)

        # Group 2: Import Settings
        y += 40
        self.chk_save = CheckBox()
        self.chk_save.Text = "Save Project after Import"
        self.chk_save.Location = Point(30, y)
        self.chk_save.Size = Size(350, 24)
        self.chk_save.Checked = current_settings.get("save_after_import", True)
        self.Controls.Add(self.chk_save)

        y += 30
        self.chk_safety = CheckBox()
        self.chk_safety.Text = "Timestamped Backup before Import"
        self.chk_safety.Location = Point(30, y)
        self.chk_safety.Size = Size(350, 24)
        self.chk_safety.Checked = current_settings.get("safety_backup", True)
        self.Controls.Add(self.chk_safety)

        # Subsection: Backup Retention
        y += 30
        lbl_retention = Label()
        lbl_retention.Text = "Max Backups to Keep (Optional):"
        lbl_retention.Location = Point(50, y+3)
        lbl_retention.AutoSize = True
        self.Controls.Add(lbl_retention)
        
        self.txt_retention = TextBox()
        self.txt_retention.Location = Point(250, y)
        self.txt_retention.Size = Size(60, 20)
        self.txt_retention.Text = str(current_settings.get("retention_count", 10))
        self.Controls.Add(self.txt_retention)

        # Group 3: Diagnostics
        y += 40
        self.chk_debug = CheckBox()
        self.chk_debug.Text = "Debug mode (write metadata + logs)"
        self.chk_debug.Location = Point(30, y)
        self.chk_debug.Size = Size(350, 24)
        self.chk_debug.Checked = current_settings.get("debug", False)
        self.Controls.Add(self.chk_debug)

        # Buttons
        btn_cancel = Button()
        btn_cancel.Text = "Cancel"
        btn_cancel.DialogResult = DialogResult.Cancel
        btn_cancel.Location = Point(290, 350)
        self.Controls.Add(btn_cancel)

        btn_save = Button()
        btn_save.Text = "Save Settings"
        btn_save.DialogResult = DialogResult.OK
        btn_save.Location = Point(160, 350)
        btn_save.Size = Size(120, 23)
        self.Controls.Add(btn_save)
        self.AcceptButton = btn_save
        self.CancelButton = btn_cancel

    def get_results(self):
        try:
            retention = int(self.txt_retention.Text.strip())
            if retention < 1:
                retention = 10
        except:
            retention = 10
        
        return {
            "export_xml": self.chk_xml.Checked,
            "backup_binary": self.chk_bin.Checked,
            "backup_name": self.txt_backup_name.Text.strip(),
            "save_after_import": self.chk_save.Checked,
            "save_after_export": self.chk_save_exp.Checked,
            "safety_backup": self.chk_safety.Checked,
            "retention_count": retention,
            "debug": self.chk_debug.Checked
        }

def show_settings_dialog(current_settings, version=None):
    try:
        form = SettingsForm(current_settings, version)
        result = form.ShowDialog()
        if result == DialogResult.OK:
            return form.get_results()
    except Exception as e:
        print("Error showing settings dialog: " + str(e))
    return None


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

    def _on_cancel(self, sender, event):
        self.choice = "cancel"
        self.DialogResult = DialogResult.Cancel
        self.Close()

def show_directory_choice_dialog(title, message):
    try:
        form = DirectoryChoiceForm(title, message)
        form.ShowDialog()
        return form.choice
    except:
        # Fallback to standard if custom fails
        from engine.codesys_ui import ask_yes_no_cancel
        return ask_yes_no_cancel(title, message)


class SyncFolderPathForm(Form):
    """Type the sync folder instead of browsing for it.

    Browsing cannot express "./", and a relative path is the one that
    survives the project being opened on another machine, so the manual
    route is not a fallback -- it is the only way to ask for one.
    """
    def __init__(self, initial):
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
                                "Relative paths (starting with ./) are resolved against the project file."
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
        self.txt_path.Text = initial if initial else "./"
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


def show_sync_folder_dialog(system, initial=""):
    """Ask a person where the sync folder is. Returns a path, or None.

    The one door to the whole thing, browse and type alike, because
    cds/ide/silent.py patches this name to refuse when nobody is there
    (SPEC 6.1). A second door would open a modal window inside the IDE's
    message loop with no one to close it.
    """
    ans = show_directory_choice_dialog(
        "Project Sync Configuration",
        "Would you like to BROWSE for a folder or enter the path manually?")
    if ans == "cancel":
        return None
    if ans == "yes":
        return system.ui.browse_directory_dialog(
            "Select Sync Directory for this Project", initial)
    form = SyncFolderPathForm(initial)
    if form.ShowDialog() != DialogResult.OK:
        return None
    return form.txt_path.Text.strip()
