# 工單 B：`cds/` 與 `cdsint/` 的平行路徑收成一條

> 建立日期 2026-09-06。分支與 worktree 由監督者在派工時填：分支 `ticket/plumbing`，worktree `C:\Users\qazsskevin\Documents\repo\cdsint-plumbing`。
> 鐵律在 `docs/WORKER_RULES.md`，先讀它。使用者不在也不會回答，卡住寫進最後回報。
> 這是四張工單的第二張，在 `history/SETTINGS_PLAN.md` 合進 `main` 之後才開工。第 3 節的行號已在 `c67dcb7` 重核過（階段 0），底下每一段動工前仍請先確認自己那幾行沒被前一段挪走。

---

## 0. 本工單專屬的鐵律

- 臨時檔在 `%TEMP%\cdsint-work\plumbing\` 底下。
- 不碰 `engine/`，除了第 4 節明列的兩處（`compare` 把逐物件清單放進 `data`、對話框標題改用常數）。引擎的其他爛東西是 `ENGINE_PLAN.md` 的事。
- 不碰 `docs/SPEC.md` 的現況欄與第 10 節，那是 `HYGIENE_PLAN.md` 的事。SPEC 4.3 的 exit 2 那一格由監督者在派工前改好。

---

## 1. 目標與範圍

這兩層是本 repo 寫的，尺寸與註解紀律守得住，但「一件事一個地方」沒守住：跑一個命令組一筆結果寫了兩份、結果紀錄手工拼三次、命令表面散在七張表、退出碼決定散在六處、安裝探測寫兩遍還互相矛盾、印東西的檔案有五個。每一條都是「加一個命令、一個廠商、一個欄位要改 N 處」的維護稅。另有三個真 bug 和一條 SPEC 契約違反。

做完之後：每件事一個地方。加一個子命令只改一張表；拒絕只走一條路一個碼；結果紀錄只有一個建構子；印東西只在 `report.py`。

明確不做：任何使用者看得到的行為改變，除了下面明列的三件：`--install` 給錯名字從 traceback 變一句話加 exit 4；旗標不搭一律 exit 2；`compare --json` 的 `data` 多一個逐物件清單欄位。

---

## 2. 使用者定案的決定（2026-09-06）

| # | 決策 | 選擇 | 理由 |
|---|---|---|---|
| 1 | 四張工單切法與順序 | A 設定、B 管線、D 衛生、C 引擎，循序 | 按驗收方式切，不按檔案切；A 和 D 都大改 `tests/`，循序才沒有合併問題 |
| 2 | ScriptDir 在哪、要不要管理員，誰是主人 | Python（`cdsint/installs.py`）當主人，`irm/setup.ps1` 改成呼叫 `installs --json` | 有測試、有 `--json`；PowerShell 那段是最難維護的部分。安裝時就要有 Python 不是新條件 |
| 3 | 旗標不搭的退出碼 | 一律走 argparse 的 `parser.error` 回 2；SPEC 4.3 把 2 的定義改寫成「命令列本身不對：旗標不搭，或找不到唯一一個活著的 IDE」 | 退出碼的價值在呼叫端能不能據此決定下一步，2 的下一步是「別重試，改命令列」，兩種原因都是 |
| 4 | 替身 UI 的三條不變量 | 最小修法：`_install` 挪到 exec 之前、對話框標題收成 `cds/core` 常數、加 AST 測試擋引擎模組層級 import `codesys_ui`。換函式的機制不動 | B 的邊界是不碰引擎內部；C 把 `system` 改成顯式傳遞之後，替身 UI 自然變成「傳一個不同的 system」 |
| 5 | 第 4 節那十三條 | 全收 | 唯一改到對外形狀的是 `compare` 的 `--json` 多一個欄位，是加不是改 |

---

## 3. 接手前必須知道的現況事實

2026-09-06 在 `c67dcb7` 重核過一遍，行號已重填。工單建立時寫的是 `631259b` 的行號，A 之後全部漂了。標「A 已修」或劃掉的是 A 做掉的部分，不重做。

**跑命令與結果紀錄**

1. `cds/ide/headless.py` 的 `run_one`（134 到 155 行）與 `cds/ide/watcher.py` 的 `_run_script`（244 到 257 行）逐字相同：叫 `entries.run`，接 `outcome.error_text()`，`commands.new_result(...)` 帶七個具名欄位。`NeedsInput` 的處理在 `headless.py` 140 到 147 行與 `watcher._answer`（190 到 200 行）又各一份。~~`tests/test_watcher.py` 是第三份~~ ── 那份不在了，測試裡剩的是只呼叫一行 `new_result` 的假 handler。`cds/ide/entries.py` 檔頭說「running a command 的那部分住在這裡而不是兩邊」。
2. 結果紀錄的唯一建構子是 `cds/core/commands.py` 的 `new_result`（75 到 105 行，12 個鍵）。手拼的有：`cdsint/target.py` 74 到 84 行 `_gone`（3 個鍵）、`cdsint/verify.py` 82 到 98 行 `needs_yes`（7 個鍵）；`cdsint/report.py` 的 `show`（79 到 95 行）全靠 `.get()` 活著。訊息紀錄 `{"level", "text"}` 在 `silent.SilentUI._record`（158 到 159 行）與 `watcher._info`（307 到 308 行）各拼一次。命令紀錄 `commands.write_command`（35 到 45 行，有 `created_at`）與 `headless.run_one`（136 行，沒有）兩種。`silent.Outcome([], "", ...)` 在 `entries.py` 117 與 120 行用位置參數拼「沒跑腳本的 Outcome」。
3. **A 已修大半。** `cds/ide/project.py` 的 `prop`、`set_prop`、`save`、`_values` 都刪了，整個檔剩 51 行三個函式。`permit` 那條也修好了：`permit._written`（75 到 90 行）讓 `settings.Invalid` 往上冒，`entries._not_allowed`（113 到 121 行）接成 exit 1（`SETTINGS_PLAN.md` Ruling 19）。剩下的一處是 `project.sync_dir`（23 到 40 行）把 `settings.Invalid`、`IOError`、`OSError` 一起吞成 None，所以看門人的登記檔對「壞掉的設定檔」和「沒設定過的專案」寫同一個答案。

**替身 UI**

4. `cds/ide/silent.py` 的 `run`（192 到 209 行）先 `_exec_file`（206 行）再交給 `_call`（212 到 238 行），`_install` 在 216 行 ── 順序仍然是 exec 在前。`_ui_patches`（291 到 296 行）寫死要換的函式名。`YES_NO`（35 到 39 行）是對話框標題字串表，對應端剩三處：`engine/entry_export.py` 103 行、`engine/entry_import.py` 184 行、`engine/entry_plc.py` 116 行，兩邊沒有共用常數。標題改了會 raise「unexpected dialog」（318 行），這點是對的；繞過替身那條是無聲的。`tests/test_silent.py` 209 到 212 行只在 docstring 宣稱引擎沒有模組層級 import。
5. `silent.py` 365 行、`watcher.py` 308 行，超過 300 的軟上限。`statusform.StatusForm.__init__` 39 到 87 行共 49 行，過 40 的軟上限但已在 60 的硬上限內（A 刪掉 Settings 按鈕之後減重）。`headless.run_job` 74 到 108 行共 35 行、三個出口。

**特例與死參數**

6. `entries.py` 129 到 136 行 `tail` 對 `build` 有特例。~~`wrong_application` 對 `build` 的特例~~ ── A 刪了。`entry_build.py` 已有 `build_messages`。`messages.build_report` 的特例跟 `tail` 那條同源。
7. `messages._text`（`cds/ide/messages.py` 134 到 139 行）是 `cds/core/text.py` 的 `as_text` 逐字副本，而 `text.py` 的 docstring 說三份已經收成一份。
8. `EXIT_OK`、`EXIT_FAILED` 在 `cds/ide/headless.py` 55 到 56 行與 `cdsint/exits.py` 17 到 18 行各定義一次；SPEC 6.4 說 CLI 要拿 report 的 `intended_exit` 跟實際退出碼比對，兩邊必須相等但沒有東西釘住。
9. `forget_engine` 的迴圈在 `entries.py` 67 到 78 行、`stub/Project_export.py` 14 到 15 行、`stub/Project_import.py` 14 到 15 行各一份。`REPO_ROOT` 在 `entries.py` 28 行與 `cds/ide/headless.py` 33 行各算一次。
10. `silent._install(silent, ui, args)` 的 `ui` 未使用（263 行）；`SilentUI.info/warning/error(self, text, *rest)` 的 `*rest` 靜默丟掉（131 到 138 行）。`Watcher.__init__` 對 globals 缺 `system` 丟的是 `KeyError`（32 到 34 行）── A 把它從隱含的 KeyError 換成帶訊息的 KeyError，型別還沒換。
11. 註解裡寫死的行號，A 清掉了 `silent.py` 檔頭那兩條（`codesys_utils 517`、`codesys_ui 48-90`）。還在的：`silent.py` 64 行「Project_Build.py 73」；`messages.py` 4 與 17 行「Project_Build.py」；`cds/ide/__init__.py` 6 行說本體是 `Project_*.py`（實際是 `engine/entry_*.py`），4 到 9 行的模組索引列 6 個而套件有 10 個（缺 display、entries、headless、permit）；`watcher.py` 135 行「section 12」而 WATCHER.md 只有 10 節。
12. `statusform.py` 139 到 142、148 到 149 行兩個 `except Exception: pass`，棘輪只數 `except:` 所以看不到。`watcher.py` 293 行每 2 秒心跳讀一次 `project.sync_dir`，那是每 2 秒讀一次設定檔。~~`permit.refusal` 讀同一設定兩次~~ ── A 之後只讀一次；但 `project.path_of`（一趟 .NET）在一次拒絕裡仍被叫三次（`_written`、`refusal` 的 `_path`、`record` 的 `_path`）。

**CLI 的命令表面**

13. `cdsint/flags.py` 描述「哪個命令有哪種形式、收哪些旗標」的地方：`_HELP`（24 到 39 行）、`BOTH_FORMS`（42）、`WATCHER_ONLY`（44）、`PROJECT_ONLY_COMMAND`（48）、`FLAGS`（52 到 59）、`build_parser` 手寫 `installs`、`list` 再事後補 `plc`（83 到 96 行）、`_add_flag` 依旗標名 if/elif（140 到 149 行）、`command_args` 的分支（164 到 171 行）、`wire_name` 的 plc 分支（174 到 184 行）、`_only_the_project_form`（187 到 208 行）；`cli.py` 的 `main`（137 到 153 行）依名字分 `installs`、`list`、`verify`；`verify.py` 的 `steps`（33 到 45 行）手抄四個命令的 args。七個 `getattr(ns, ..., None)`（`cli.py` 43、85、115；`flags.py` 167、197、203、217 行）是各子命令 namespace 形狀不同的症狀。~~`flags._config_args`~~ ── A 刪了，KEY=VALUE 解析器只剩 `cli._answers`（54 到 61 行）。`--target` 的 `add_argument` 定義兩次（`flags.py` 112 與 119 行），兩段幫助文字。

**退出碼與拒絕**

14. `cdsint/installs.py` 的 `InstallError`（55 到 60 行）跟 `exits.Failure` 同形（message 加 matches）但沒帶 code，`cli.main`（137 到 153 行）只接 `Failure`。實測 `python -m cdsint.cli build --project x --install definitely-not-an-ide --sync-dir y` 噴整段 traceback，exit 1。SPEC 4.3 說「IDE 啟動失敗」是 4。
15. `flags.check`（223 到 230 行）走 `parser.error` 回 2；`refuse_project_flags`（211 到 220 行）丟 `Failure` 回 1，而且不在 `check` 裡，是 `cli.make_runner`（50 行）呼叫。實測 `build --target foo --profile bar` 回 1，`plc connect --target foo` 與 `export --target a --project b` 回 2。`flags.py` 6 到 7 行說「三種組合」、`check` 的 docstring 說「每個拒絕一次呼叫」，實際四種、跑兩種。
16. 退出碼的決定：`cli.exit_code`（129 到 135 行）管單命令；`cli.run_verify`（84 到 95 行）自己判 OK/FAILED 不經 `exit_code`；`Failure` 丟出點在 `cli.py` 57 行、`flags.py` 219 行、`cdsint/headless.py` 134、139、266、270 行、`target.py` 43、70、83 行；`InstallError` 丟出點在 `installs.py` 89、95、96、114、116 行；argparse 三處隱含 2。verify 某步回 `denied` 會是 1 不是 5。

**無頭啟動器 CLI 側**

17. `cdsint/headless.py` 的 `_collect`（233 到 283 行）51 行做六件事。264 行 `print("warning: " + ...)` 後 266 行 `raise Failure(...)`，`exits.py` 39 到 43 行再印一次。`_kill`（182 到 203 行）兩個分支都 `return None`，`_launch` 173 行卻拿它當回傳值。`Headless.__init__` 讀 `lock.held` 三次（67、135、220 行），建構子還掃 Program Files 與登錄檔（56 行）。
18. `sync_dir`：`cdsint/headless.py` 246 行頂層仍是「IDE 回報值 `or` 旗標」；~~272 行逐筆填旗標值~~ ── A 改成 282 行從已合併的 report 讀，逐筆那份沒了。`Target.sync_dir()`（`target.py` 51 到 53 行）與 `Headless.sync_dir()`（74 到 83 行）現在都只被 `cli.show_folder`（113 到 127 行）當後備用，而 `show_folder` 第一件事就是「不是 `--project` 形式就返回」，所以 `Target.sync_dir()` 沒有呼叫端。
19. `timed_out` 與 `exit_code_actual` 是一個事實兩個名字（`cdsint/headless.py` 248 行 `timed_out: code is None`）；`stdout_reached`（251、311 到 318 行）算了、寫了、沒人讀。`cdsint/headless.py` 33 到 46 行是帶日期的量測日誌，40 行「the phase-2 table」指的是 SPEC 第 7 節。

**印東西**

20. `report.py` 18 處、`cdsint/headless.py` 6 處（143、197、219、225、228、264 行）、`cli.py` 4 處（`run_list` 自己排表 72 到 78 行、verify 判決 89 到 93 行）、`installs.warn_if_elevated`（130 到 132 行）、`exits.Failure.report`（39 到 43 行）。`report.py` 4 行宣稱「One printer for both forms」。`--json` 下 stderr 會漏警告。
21. `report.py` 的 `show`（79 到 95 行）把 message 文字與 question 收進 `said`，再以 `result["error"] not in said` 決定印不印 error；`_show_needs`（157 到 168 行）為此改動呼叫端傳進來的 list。`_wants_tail`（171 到 177 行）用 `result.get("command") == "compare"` 決定印 tail，因為 compare 的真答案在 `stdout_tail` 不在 `data`。`report.py` 111 到 112 行硬寫廠商清單。

**安裝探測**

22. `irm/setup.ps1` 73 到 128 行 `Find-ScriptDirs` 與 `installs.py` 30 到 42 行 `VENDORS` 加 208 到 224 行 `_script_dir` 加 227 到 241 行 `_under_program_files` 各答一次。PS 第 102 行把 Lenze 3.x 的 ProgramData 標 `NeedsAdmin=$true`，`irm/setup.md` 照抄；`installs.py` 227 到 241 行的 docstring 卻說 ProgramData 不需要。PS 只掃 `$env:ProgramFiles`（81、107 行），Python 掃兩個 root。`installs.py` 每列的 `roots`（31、35、38 行）完全相同；`_script_dir` 用 `vendor["exe"]` if/elif 加目錄名 `startswith("4.")` 在表外重編每家知識。`run_as_admin_layers`（135 到 156 行）與 `find`（63 到 78 行）巢狀 4 層。`script_dir` 與 `script_dir_needs_admin` 兩個欄位的唯一讀者是 `report.show_installs`（119 到 121 行）。

**其他**

23. `target.send`（`target.py` 88 到 121 行）巢狀 4 層，交錯輪詢、`missing_since` 去抖、deadline 加清理、Ctrl-C 清理。去抖是在 CLI 端重判存活，`cds/core/instances.is_alive` 已是存活定義；`Target.__init__` 38 到 40 行又先 `live_instances` 過濾一次。
24. 120 秒：`target.py` 18 行 `DEFAULT_TIMEOUT_S`、`flags.py` 100 到 105 行幫助文字硬寫「(default 120)」、`cdsint/headless.py` 54 行 `timeout=120.0`；`target→flags→cli` 轉手三次，`cli.py` 34 行零使用者。`cli.py` 32 到 33 行帶 `noqa: F401` import 三個 `EXIT_*` 只為讓 `tests/test_cli.py` 寫 `cli.EXIT_TARGET`（18 處）。`cli.py` 28 行模組層 `sys.path.insert` 是 pyproject console script 之外的第二條可 import 路徑；SKILL.md 22 行說的 `python -m cdsint.cli` 其實不靠它（`-m` 自己會把工作目錄放上 sys.path），靠它的是「用路徑直接跑 `cli.py`」那種叫法。

**開工前重核清單**

- 上面每一條先用名字 grep 一次，行號重填，A 已經刪掉的劃掉。（2026-09-06 做完）
- 特別看 A 之後 `cds/ide/project.py`、`cdsint/headless.py`、`cdsint/flags.py`、`cds/ide/silent.py` 剩什麼。（做完，見第 3、5、10、13、17、18 條）
- 測試基線重跑，Windows 與 WSL 各記一個數字。（`c67dcb7`：Windows `python -m pytest tests -q` 960 passed；WSL Ubuntu-22.04 `python3 -m pytest tests -q` 960 passed）

---

## 4. 設計

每一條一句話說做完長什麼樣。

1. **跑命令組結果，一份。** `cds/ide/entries.py` 開一個 `answer(ide_globals, cmd, started)`，回結果紀錄，裡面接 `NeedsInput` 與其他例外。`headless.run_one` 與 `watcher._run_script` 各剩一行呼叫。`tests/test_watcher.py` 那份第三份刪。
2. **`project.py` 分清「沒有」和「壞了」。** 沒有回 None；壞了就 raise，或帶著例外文字回來讓拒絕訊息說真話。只接預期的那一種例外。
3. **`InstallError` 併進 `Failure`。** `installs.py` 直接 `raise Failure(msg, EXIT_HEADLESS, lines)`，`InstallError` 刪，`cli.main` 只接一種例外。
4. **退出碼一扇門。** `cli.exit_code` 是唯一決定「一筆結果值多少」的地方；`run_verify` 把失敗那筆交給它；`verify.needs_yes` 的拒絕紀錄用 `new_result` 建、走同一扇門。旗標不搭一律 `parser.error` 回 2，`refuse_project_flags` 併進 `flags.check`。`flags.py` 檔頭那句「三種組合」改成對的。
5. **命令表面一張表。** `flags.py` 一個 `COMMANDS` dict：名字、幫助、形式（`target`、`project`、`both`、`none`）、旗標清單（每個帶種類：布林、字串、`-y`）、位置參數、wire name。`build_parser` 迭代它，`set_defaults` 讓每個 namespace 同形；`command_args` 讀它；`cli.main` 查它決定 runner 種類；`verify.steps` 從它產生 args；`getattr(ns, ..., None)` 消失；`--target` 只定義一次。`plc` 的「只有 `--project` 形式，理由是 D8」寫在表的那一列，拒絕訊息從表裡拿。
6. **安裝探測一個主人。** `installs.VENDORS` 加 `script_dir` 欄（callable 或模板），Lenze 3.x 與 4.x 的分岔寫在它自己那列；`roots` 升成模組常數；`_script_dir` 刪；`find` 用一個 `_candidates()` generator 攤平。`irm/setup.ps1` 的 `Find-ScriptDirs` 刪，改成呼叫 `python <clone>\cdsint\cli.py installs --json` 拿清單；`irm/setup.md` 跟著改，ProgramData 要不要管理員以 Python 的答案為準（先在這台實測 `C:\ProgramData\PLCDesigner\ScriptDir` 建 junction 要不要提權，把結果寫進第 7 節）。
7. **結果紀錄只有一個建構子。** `target._gone`、`verify.needs_yes` 改用 `cds.core.commands.new_result`；`commands.py` 加 `new_command()` 與 `message(level, text)`；`entries.py` 拼 `Outcome` 的兩處隨第 1 條消失。`report.show` 不再 `.get()`。
8. **印東西只在 `report.py`。** runner 回傳或累積 notes，`report` 印；`run_list` 的排表搬進 `report`；`installs.warn_if_elevated` 回字串；逾時訊息只印一次，`_collect` 拆成純函數 `_annotate(report)` 與 `_verdict(report)`，warning 只在不致命那支印；`_kill` 回傳值有人用或就不回傳。
9. **`report.py` 不用文字比對去重複。** 生產者不在 `error` 裡重抄第一條壞訊息，`said` 消失，`_show_needs` 不改呼叫端的 list。`compare` 把逐物件清單放進 `data`（像 `discover` 放 `unknown`），`_wants_tail` 只剩「失敗才顯示 tail」。廠商清單那句從 `VENDORS` 導出或只說「no IDE found」。
10. **小工具各一份。** `messages._text` 改 `from cds.core.text import as_text`；`EXIT_*` 搬到 `cds/core/exits.py` 兩側 import；`forget_engine` 搬到 `cds/core`，stub 與 entries 都呼叫；`REPO_ROOT` 一處；120 秒一個常數，argparse 用 `%(default)s`，`Headless` 不給預設；`cli.py` 那三個 re-export 刪，`tests/test_cli.py` 改 import `cdsint.exits`；`cli.py` 的 `sys.path.insert` 與 SKILL.md 22 行二選一留一條。
11. **替身 UI 最小修法。** `silent.run` 先 `_install` 再 `_exec_file`；對話框標題收成 `cds/core/dialogs.py` 的常數，`YES_NO` 表與四個引擎呼叫點都 import 它；`tests/test_layering.py` 加一條：`engine/` 底下任何模組層級 `import engine.codesys_ui` 或 `from engine.codesys_ui import` 就紅（現在為零，測試把零釘住）。`_install` 的 `ui` 參數、`SilentUI` 的 `*rest` 刪；`Watcher.__init__` 缺 `system` 丟 `TypeError`。
12. **`target.send` 拆開。** `_poll_once` 一個，存活判定只在 `cds/core/instances`，`Target.__init__` 不再先過濾一次。`sync_dir` 只有 IDE 側一個來源，`Target.sync_dir()` 若沒人用就刪，兩個 docstring 宣稱的共同介面改成真的。
13. **註解與尺寸。** 行號改函式名；`cds/ide/__init__.py` 索引補齊或刪；`headless.py` 33 到 46 行的量測日誌換成一個指向 SPEC 第 7 節的指標；`statusform.py` 兩個 `except Exception: pass` 接預期的例外；`silent.py` 拆成資料（`NeedsInput`、`Outcome`）、runner、`_Tee` 三段以回到 300 行內；`headless.run_job` 五個出口收成一個。

---

## 5. 分階段與驗收

- [x] **階段 0：重核與基線**
  - [x] 第 3 節重核清單做完，行號重填，commit。
  - [x] 驗收：Windows 與 WSL 測試數記進第 6 節。（`c67dcb7` 基線：Windows 960 passed、WSL 960 passed）

- [x] **階段 1：IDE 側（第 4 節 1、2、7 的 IDE 側、10 的 IDE 側、11、13）**
  - [x] 驗收：`grep -rn "error_text()" cds/ide/` 剩兩處，一處是 `entries.answer` 這個唯一的讀者，一處是 `outcome.ok()` 呼叫自己。`new_result` 那條照 Ruling 20 改判：跑腳本那條路只剩 `entries.answer` 一個地方建結果紀錄，看門人自己的 ping／status／stop／refuse 留在 `watcher.py`。
  - [x] 驗收：三條測試都在。`tests/test_plc.py` 的 `test_a_settings_file_that_cannot_be_read_is_a_failure_not_a_refusal` 是第一條（A 就寫好了，本工單加一條斷言釘住「不是拒絕的措辭」）；`tests/test_silent.py` 兩條 `test_a_dialog_asked_at_module_level_*` 是第二條，把 `_install` 挪回 exec 之後就會紅（實測過）；`tests/test_layering.py` 的 `test_no_engine_file_imports_the_dialogs_as_it_loads` 加 `test_that_rule_would_catch_one` 是第三條，後者把合成的一行餵給檢查函式，不碰 `engine/`。
  - [x] 驗收：`cds/ide/*.py` 最大的是 `watcher.py` 299 行、`silent.py` 287 行，其餘都在 220 以內；`StatusForm.__init__` 23 行。

- [x] **階段 2：CLI 的表與退出碼（第 4 節 3、4、5、7 的 CLI 側、10 的 CLI 側）**
  - [x] 驗收：`python -m cdsint.cli build --project x --install definitely-not-an-ide` 印一句 `no IDE matches --install 'definitely-not-an-ide'` 加這台七套 IDE 的名字與路徑，exit 4，沒有 traceback。
  - [x] 驗收：三條都 exit 2。`build --target foo --profile bar` 說 `--profile only works with --project`；`plc connect --target foo` 說 plc 沒有 `--target` 形式並附上 D8 的理由；`export --target a --project b` 由 argparse 的互斥群組說 `argument --project: not allowed with argument --target`。
  - [x] 驗收：`grep -n "getattr(ns" cdsint/` 為零；`grep -n "BOTH_FORMS\|WATCHER_ONLY\|PROJECT_ONLY_COMMAND\|_add_flag" cdsint/` 為零；`--target` 的 `add_argument` 只出現一次。
  - [x] 驗收：三條測試在 `tests/test_verify.py`：`test_a_step_the_project_refuses_is_exit_5`、`test_the_refusal_without_yes_is_a_whole_result_record`、`test_every_row_in_the_table_is_a_command_you_can_type`（加反向的 `test_every_command_you_can_type_is_a_row_in_the_table` 與 `test_every_command_line_is_the_same_shape`）。

- [x] **階段 3：安裝探測一個主人（第 4 節 6）**
  - [x] 驗收：`python -m cdsint.cli installs --json` 每筆有 `script_dir` 與 `script_dir_needs_admin`（名字照舊，見 Ruling 40）；`irm/setup.ps1` 裡 `grep -c "Program Files\|ProgramData\|ScriptDir\\\\"` 為零，而且有一條測試釘住它（`test_the_installer_carries_no_scriptdir_knowledge_of_its_own`）。
  - [x] 驗收：`.\irm\setup.ps1 -List` 列出五個 ScriptDir，跟 `installs --json` 逐項相同（CODESYS 三套合成一列、Delta 兩套各一列、Lenze 兩套各一列）；`-ScriptDir %TEMP%\cdsint-work\plumbing\fake-scriptdir -Clone .` 裝得起來，junction 指向 worktree 的 `stub\`，三個 stub 加 `body.path` 都在。事後確認兩個真 junction 仍指向 `repo\cdsint\stub`，一個位元組沒動。
  - [x] 驗收：`irm/setup.md` 改寫成「問 cdsint」，管理員那段只剩 Delta 一項，實測結果見第 7 節 Ruling 41。

- [ ] **階段 4：印東西與 `report.py`（第 4 節 8、9、12）**
  - [ ] 驗收：`grep -rn "print(" cdsint/ | grep -v report.py | grep -v exits.py` 為零。
  - [ ] 驗收：逾時的一趟（用 `--timeout 1` 對一個會慢的命令，或測試裡模擬）stderr 那句只出現一次。
  - [ ] 驗收：`compare --json` 的 `data` 有逐物件清單，`report` 對成功的 compare 不印 `stdout_tail`；`grep -n '"compare"' cdsint/report.py` 為零。
  - [ ] 驗收：`--json` 模式下 stderr 沒有任何 runner 自己印的字。

- [ ] **階段 5：收尾**
  - [ ] `python -m pytest tests -q` 綠，WSL 綠；`tests/test_layering.py`、`test_bare_excepts.py`、`test_doc_links.py` 綠。
  - [ ] readMe、`docs/AI_WORKFLOW.md`、`skills/cdsint/SKILL.md` 裡 exit 2 的說法跟 SPEC 4.3 一致；`--install` 給錯的行為若文件有寫就對齊。
  - [ ] CHANGELOG Unreleased 加一段。
  - [ ] 真 IDE：softplc 副本 `verify -y --project ... --install 3.5.21.40 --sync-dir S` exit 0，hash 清單跟開工前的 diff 為空（B 不該碰輸出，這是保險）。
  - [ ] 沒有殘留的 IDE 行程；`%TEMP%\cdsint-work\plumbing\` 清掉。

---

## 6. 回報格式

同 `history/SETTINGS_PLAN.md` 第 6 節。

---

## 7. 未決事項與裁決

`Ruling: 決定 — 理由 — 錯了的代價`。

先列出來的：

1. `COMMANDS` 表用 dict 還是 namedtuple 清單。預設：dict，鍵是命令名，值是一個小 dataclass 或 dict；讀者要能用 `COMMANDS["plc"]` 一眼看到那一列。
2. `EXIT_*` 搬到 `cds/core/exits.py` 之後，`cdsint/exits.py` 的 `Failure` 留在 CLI 側還是也搬。預設：`Failure` 留 CLI 側，它是 CLI 的例外；常數才是兩側共用的。
3. `compare` 放進 `data` 的逐物件清單長什麼樣。預設：跟 `discover` 的 `unknown` 同一種形狀，一個 list of dict，每筆有 `name`、`path`、`state`（`changed`、`new_in_ide`、`new_on_disk`、`pending_import` 之一）。
4. ProgramData 要不要管理員：在這台實測。

### 階段 1 新增的 Ruling

20. `Ruling: 驗收那句「`grep -rn "new_result" cds/ide/` 只剩 entries.py 一處」改判成「跑腳本那條路只剩一處」 — `watcher.py` 的 `_ping`、`_status`、`_stop`、`_refuse` 與「不認得的命令」也各自建一筆結果紀錄，而那四件事跟引擎本體無關，是看門人自己的生命週期命令（WATCHER.md 4）；把它們搬進 `entries.py` 會讓那個檔同時管「引擎本體」和「看門人的命令」兩件事 — 錯了的代價是 `cds/ide/` 裡 `new_result` 出現九次而不是三次，讀的人要自己分辨哪三次是本體那條路。`
21. `Ruling: 第 4 節第 1 條說「`entries.py` 拼 `Outcome` 的兩處隨第 1 條消失」，實際改成 `Outcome.not_run(error, denied=None)` 一個具名建構子 — 那兩處是 PLC 權限閘門的答案，而閘門必須留在 `entries.run` 裡：`run` 是唯一按下本體的地方，把閘門移到 `answer` 會讓任何直接呼叫 `run` 的人（測試就有）繞過權限檢查 — 錯了的代價是 `cds/ide/outcome.py` 多一個四行的 classmethod。`
22. `Ruling: `project.sync_dir` 繼續把「沒設定過」和「設定檔壞了」答成同一個 None，但在 docstring 裡明講 — 第 4 節第 2 條要它分清楚，可是它的兩個呼叫端都需要「答不出來就 None」：看門人每兩秒寫一次登記檔，一個正在被編輯的檔案不能把看門人打下線；無頭那邊是命令跑完之後才讀，那時壞檔案早就讓某個命令失敗並把完整訊息報出去了。把 try 往外挪只是把同一個吞嚥抄成兩份，而且沒有任何使用者看得到的差別。真正要分清楚的地方是拒絕訊息，A 已經修好（Ruling 19），本工單加一條斷言釘住 — 錯了的代價是登記檔的 `sync_dir` 欄位對這兩種情況說同一句話，而那個欄位目前沒有讀者（見第 3 節第 18 條）。`
23. `Ruling: `statusform.py` 那兩個 `except Exception: pass` 改成「一樣寬，但會出聲」，不是改成接特定的例外 — 這兩個地方跑在 WinForms 的事件處理器裡，例外逃出去會變成 IDE 的執行緒例外對話框（WATCHER.md 5），而它們會撞到的是 .NET 的例外型別，在這台機器上沒有真 IDE 就只能用猜的，猜錯會把一個化妝品等級的問題變成關不掉的視窗。`watcher._show` 對同一個問題已經有答案：接得寬，但把 traceback 印出來。照抄那個 — 錯了的代價是關視窗時可能多印一段 traceback。`
24. `Ruling: `cds/ide/headless.py` 的 `_ROOT` 用完就 `del` — 它跟 `entries.REPO_ROOT` 是同一個地方的兩個名字（第 3 節第 9 條），但它沒得換：那一行正是「讓常數可以被 import」的那一行，在它跑完之前 `cds.core` 都不存在。刪掉之後行程裡就只剩一個名字叫得出安裝根目錄 — 錯了的代價是多一行 `del`，讀的人要看註解才知道為什麼。`
25. `Ruling: `EXIT_*` 搬進 `cds/core/exits.py`，`Failure` 留在 `cdsint/exits.py`（照第 7 節原本的預設 2），而且 CLI 側直接從 `cds.core.exits` import 常數，不透過 `cdsint.exits` 轉手 — 轉手就是第二個名字，PRINCIPLES 7 說那是平行路徑 — 錯了的代價是 `cdsint/target.py`、`cdsint/headless.py` 各多一行 import。`
26. `Ruling: `silent.py` 拆成 `cds/ide/outcome.py`（`NeedsInput` 與 `Outcome`）、`cds/ide/tee.py`（`Tee`）與 `silent.py` 本身 — 名字照它們各自的那一件事取，不叫 `silent_data.py` 這種跟著舊檔名走的名字；`_Tee` 順手去掉底線，它現在是一個模組的公開東西 — 錯了的代價是 `silent.NeedsInput` 這個寫法的呼叫端都要改（四處，加測試）。`
27. `Ruling: `Watcher.__init__` 缺 `system` 改丟 `TypeError`（第 4 節第 11 條照做） — 錯的是傳進來的引數，而從建構子丟出來的 `KeyError` 讀起來像是它內部查表查壞了 — 錯了的代價是 `tests/test_watcher.py` 那一條要改，而任何接 `KeyError` 的呼叫端會漏接；目前沒有這種呼叫端。`
28. `Ruling: `tests/test_silent.py` 原本用正規表示式掃引擎原始碼裡的對話框標題字面值，改成掃「還有沒有人用字面值」加「`cds/core/dialogs.py` 公布的每個標題都在答案表裡」 — 標題收成共用常數之後，引擎那邊就沒有字面值可以掃了，原本那兩條測試會空對空全綠；新的形狀直接擋住「又寫了一個字面值」，而不是等兩份清單漂開之後才發現 — 錯了的代價是有人用非常數的字串呼叫 `ask_yes_no` 時，測試指的是「別用字面值」而不是「這個標題沒有答案」。`

### 階段 2 新增的 Ruling

29. `Ruling: `COMMANDS` 用 dict，鍵是命令名，值是一個小 `Command` 類別，照第 7 節原本的預設 1；表的順序就是 `cdsint --help` 的順序，不排序 — dict 從 Python 3.7 起保序，而 `cdsint/` 是 CPython 3.11 以上；照字母排會把 `installs` 排到 `import` 後面，抓 `--help` 第一行的腳本會壞 — 錯了的代價是加一個命令的人要想一下放哪一列。`
30. `Ruling: `EVERY_ATTRIBUTE`（每個 namespace 都要有的屬性）從表推出來，不另外列一份 — 手寫那份跟 `PROJECT_FLAGS`、跟每一列的旗標是同一組事實的第三次抄寫，漏一個就是 `command_args` 在 `vars(ns)[dest]` 丟 KeyError — 錯了的代價是讀者要看兩行推導式才知道有哪些屬性。`
31. `Ruling: 只在 `--project` 形式有效的六個旗標升成一張 `PROJECT_FLAGS` 表，`PROJECT_ONLY` 從它推出來 — 原本 parser 加六個 `add_argument`、`PROJECT_ONLY` 又手寫六個名字，兩份漂開的結果是拒絕檢查漏掉一個旗標，或對一個不存在的屬性丟 KeyError — 錯了的代價是多一個只有 `--answer` 在用的旗標種類 `PAIRS`（它的 `metavar` 是 `KEY=VALUE`，寫在種類裡）。`
32. `Ruling: 120 秒的定義搬到 `cdsint/flags.py`，`target.py` 與 `cdsint/headless.py` 都從那裡 import；`Headless` 仍然有預設值，不是拿掉 — 第 4 節第 10 條說「`Headless` 不給預設」，理由是別讓它變成第二個答案；改成 import 同一個常數就已經沒有第二個答案了，而拿掉預設會讓建構子的參數順序得改（Python 不准有預設的參數後面跟沒預設的），連帶動到 `tests/test_headless.py` 十幾處，換來的是 `Target` 有預設、`Headless` 沒有的不對稱 — 錯了的代價是有人直接建 `Headless` 而忘了給 timeout 時，拿到的是文件上的預設而不是一個錯誤。`
33. `Ruling: 幫助文字用 `%(default)g` 而不是 `%(default)s` — 常數是 float，`%s` 會印成「(default 120.0)」，跟原本的「(default 120)」差一個字；`%g` 印出 120 — 錯了的代價是常數改成非整數時幫助文字會四捨五入。`
34. `Ruling: `installs.InstallError` 併成 `Failure(msg, EXIT_HEADLESS, lines)`，候選清單放進 `lines` 而不是新開一個欄位 — `Failure.report()` 本來就會把 `lines` 每行縮排印出來，那正是候選清單要的樣子；`raised.value.matches` 的三個測試改看 `raised.value.lines` — 錯了的代價是測試只能數行數，不能再直接拿到候選的 dict。`
35. `Ruling: `--project` 沒給 `--install` 仍然是 exit 4，不改成 2 — 它現在走 `installs.resolve` 的「say which IDE with --install」，而那是「這個專案沒有可用的 IDE」；改成 2 會是本工單第 1 節明列三件事以外的第四個對外行為改變 — 錯了的代價是有人以為所有「旗標不搭」都是 2，而這一個不是。記給 `HYGIENE_PLAN.md`。`
36. `Ruling: `cdsint/flags.py` 收成一張表之後是 311 行，過 300 的軟上限（PRINCIPLES 2） — 它現在是「一張宣告式的表加上照著表蓋 parser」，把表拆出去等於把「有哪些命令」和「命令怎麼解析」分成兩個檔，那正是本工單在收掉的那種分家；軟上限的意思是「下一次要加東西之前先拆」，所以留給加第十三個命令的人 — 錯了的代價是這個檔比規矩允許的長 11 行。`
37. `Ruling: `cdsint/cli.py` 的 `sys.path.insert` 留著，SKILL.md 不動 — 第 4 節第 10 條說兩者二選一，但它的前提（SKILL.md 的 `python -m cdsint.cli` 靠這一行）是錯的：`-m` 自己會把工作目錄放上 `sys.path`。真正需要這一行的是階段 3 的 `irm/setup.ps1`，它要對一份還沒 pip 裝過的 clone 用路徑直接跑 `cdsint\cli.py installs --json` — 錯了的代價是這個檔多一行，而註解得說清楚是誰在用它。`
38. `Ruling: `cdsint/report.py` 的 `show` 改成直接索引結果紀錄，測試裡手拼的假紀錄全部改用 `commands.new_result` 建 — 這是第 4 節第 7 條「`report.show` 不再 `.get()`」的另一半：印的人不再防禦，拼的人就必須拼完整。動到 `tests/test_verify.py`、`test_plc.py`、`test_cli.py` 各幾處 — 錯了的代價是測試要多寫一個 helper 才能造一筆結果。`
39. `Ruling: verify 的退出碼由新的 `cli.verify_code(results, problems)` 決定「哪一筆算數」，再交給 `cli.exit_code` 決定「那一筆值多少」 — 第 4 節第 4 條要 `exit_code` 當唯一一扇門，但「每一步都 ok 卻仍然有問題」（compare 在來回之後找到差異）沒有任何一筆失敗的紀錄可以交給它，那種情況直接是 1 — 錯了的代價是多一個函式，而「一扇門」變成「一扇門加一個指路的」。`

### 階段 3 新增的 Ruling

40. `Ruling: JSON 的欄位名維持 `script_dir_needs_admin`，不縮成驗收字面寫的 `needs_admin` — 同一筆紀錄裡已經有一個 `run_as_admin`（那個 exe 被登錄檔標成一定要提權），兩件不同的事；叫 `needs_admin` 讀者分不出是哪一個 — 錯了的代價是驗收那句要用寬鬆的讀法（grep `needs_admin` 仍然命中）。`
41. `Ruling: ProgramData 的 ScriptDir 不需要管理員，以 Python 的答案為準，PowerShell 那份是錯的 — 2026-09-06 在這台實測：非提權的 PowerShell 對 `C:\ProgramData\PLCDesigner\ScriptDir` 底下建一個 junction（`cdsint-probe-delete-me`，指向 `%TEMP%\cdsint-work\plumbing\probe-target`）成功，隨即刪掉；`icacls` 顯示該目錄是 `Everyone:(I)(OI)(CI)(F)`。原本的 `cdsint` junction 全程沒有被碰 — 錯了的代價是 Lenze 3.x 的使用者被叫去開系統管理員 PowerShell 做一件不需要提權的事。`
42. `Ruling: `setup.ps1` 改成先決定 body 再問它有哪些 ScriptDir，`-List` 例外 — 表搬進 Python 之後，「這台有哪些 IDE」的答案只有 body 給得出來，所以順序得反過來；但 `-List` 的承諾是「什麼都不改」，讓它去下載一份 release 就違背了那句話，所以 `-List` 在「這個腳本檔本身就在一份 checkout 裡」的時候用那份 checkout 回答 — 錯了的代價是有人只下載 `setup.ps1` 單一檔案再跑 `-List`，那一趟仍然會下載 body。`
43. `Ruling: 每一家的 ScriptDir 用一個 callable 放進 `VENDORS` 那一列，不是字串模板 — Lenze 要看目錄名是不是 `4.` 開頭才知道答案，模板表達不了；callable 讓那個分岔待在 Lenze 自己那一列，而不是在表外用 `vendor["exe"]` 的 if/elif 把三家的知識重編一次 — 錯了的代價是表裡有三個函式名，讀者要往上看十行才看得到內容。`
44. `Ruling: `roots` 從每一列的欄位升成模組常數 `ROOTS` — 三列填的是同一組值，而它本來就不是「這一家的性質」而是「Windows 把程式裝在哪」 — 錯了的代價是將來若真有一家只裝在其中一個 root，得把欄位加回去。`
45. `Ruling: `setup.ps1` 用 `python <body>\cdsint\cli.py installs --json` 而不是 `cdsint installs --json` — 安裝當下還沒有人跑過 `pip install -e`，PATH 上不會有 `cdsint`；這也是 `cdsint/cli.py` 那行 `sys.path.insert` 現在唯一的理由（Ruling 37） — 錯了的代價是 PATH 上沒有 `python` 的機器裝不起來，訊息會直說要 Python 3.11 以上。`

做的時候看到但不在範圍的，記在這裡給 C 和 D：

- （worker 填）

---

## 8. 接手 prompt

你在 `C:\Users\qazsskevin\Documents\repo\cdsint-plumbing`，分支 `ticket/plumbing`。先讀 `docs/WORKER_RULES.md`、本工單第 0 到 4 節、`docs/SPEC.md` 的 D2、D7、D8、D12、4.2、4.3、6.3、6.4、`docs/WATCHER.md`、`PRINCIPLES.md`、`CLAUDE.md`。然後從第 5 節第一個沒打勾的項目開始做，階段照順序。一段做完、測試綠、commit；做完的項目打勾並 commit。決定了第 7 節的事就寫回。看到不在範圍的爛東西記進第 7 節末尾，不修。全部做完照第 6 節回報，停下來，不要 merge、不要 push。
