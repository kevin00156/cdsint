# 工單 B：`cds/` 與 `cdsint/` 的平行路徑收成一條

> 建立日期 2026-09-06。分支與 worktree 由監督者在派工時填：分支 `ticket/plumbing`，worktree `C:\Users\qazsskevin\Documents\repo\cdsint-plumbing`。
> 鐵律在 `docs/WORKER_RULES.md`，先讀它。使用者不在也不會回答，卡住寫進最後回報。
> 這是四張工單的第二張，在 `SETTINGS_PLAN.md` 合進 `main` 之後才開工。第 3 節的行號是 2026-09-06 晚上在 `631259b` 查的，A 做完之後會漂，開工第一件事是照第 3 節末尾的重核清單重查一遍再動手。

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

以 `631259b` 為準，A 做完之後要重核。

**跑命令與結果紀錄**

1. `cds/ide/headless.py` 的 `run_one`（136 到 158 行）與 `cds/ide/watcher.py` 的 `_run_script`（244 到 258 行）逐字相同：叫 `entries.run`，接 `outcome.error_text()`，`commands.new_result(...)` 帶八個欄位。`NeedsInput` 的處理在 `headless.py` 142 到 145 行與 `watcher.py` 的 `_answer`（190 到 200 行）又各一份。`tests/test_watcher.py` 515 到 522 行是第三份。`cds/ide/entries.py` 檔頭說「running a command 的那部分住在這裡而不是兩邊」。
2. 結果紀錄的唯一建構子是 `cds/core/commands.py` 的 `new_result`（12 個鍵）。手拼的有：`cdsint/target.py` 80 到 82 行 `_gone`（3 個鍵）、`cdsint/verify.py` 90 到 92 行 `needs_yes`（7 個鍵）；`cdsint/report.py` 的 `show`（74 到 89 行）全靠 `.get()` 活著。訊息紀錄 `{"level", "text"}` 在 `silent.SilentUI._record`（165 到 166 行）與 `watcher._info`（308 到 309 行）各拼一次。命令紀錄 `commands.write_command`（38 到 43 行，有 `created_at`）與 `headless.run_one`（138 行，沒有）兩種。`silent.Outcome([], "", ...)` 在 `entries.py` 90 與 138 行用位置參數拼「沒跑腳本的 Outcome」。
3. `cds/ide/project.py` 的 `prop`、`set_prop`、`save`、`_values` 全是 `except Exception: return None/False`。A 會刪掉前三個的屬性部分；留下來的 helper 若還是「never raises」，`permit` 在讀檔失敗時仍會說「not set」。A 之後重核這個檔剩什麼。

**替身 UI**

4. `cds/ide/silent.py` 的 `run`（199 到 216 行）先 `_exec_file`（213 行）再 `_install`（223 行）。`_ui_patches`（299 到 304 行）寫死要換的函式名。`YES_NO`（35 到 40 行）是對話框標題字串表，對應端在 `entry_import.py` 82 與 208 行、`entry_export.py` 109 行、`entry_plc.py` 116 行，兩邊沒有共用常數。標題改了會 raise「unexpected dialog」（322 到 323 行），這點是對的；繞過替身那條是無聲的。`tests/test_silent.py` 215 行只在 docstring 宣稱引擎沒有模組層級 import。
5. `silent.py` 379 行、`watcher.py` 309 行，超過 300 的軟上限。`statusform.StatusForm.__init__` 62 行超過 60 的硬上限（A 刪掉 Settings 按鈕之後重量）。`headless.run_job` 47 行。

**特例與死參數**

6. `entries.py` 148 到 153 行 `tail` 對 `build` 有特例，`wrong_application` 166 行對 `build` 有特例（A 刪後者）。`entry_build.py` 已有 `build_messages`（47 行）。`messages.build_report` 的特例跟 `tail` 那條同源。
7. `messages._text`（`cds/ide/messages.py` 134 到 139 行）是 `cds/core/text.py` 的 `as_text` 逐字副本，而 `text.py` 的 docstring 說三份已經收成一份。
8. `EXIT_OK`、`EXIT_FAILED` 在 `cds/ide/headless.py` 53 到 54 行與 `cdsint/exits.py` 17 到 18 行各定義一次；SPEC 6.4 說 CLI 要拿 report 的 `intended_exit` 跟實際退出碼比對，兩邊必須相等但沒有東西釘住。
9. `forget_engine` 的迴圈在 `entries.py` 78 到 80 行、`stub/Project_export.py` 14 到 15 行、`stub/Project_import.py` 14 到 15 行各一份。`REPO_ROOT` 在 `entries.py` 30 行與 `headless.py` 31 行各算一次。
10. `silent._install(silent, ui, args)` 的 `ui` 未使用；`SilentUI.info/warning/error(self, text, *rest)` 的 `*rest` 靜默丟掉。`Watcher.__init__` 對 globals 缺 `system` 丟 `KeyError`。
11. 註解裡寫死的行號全部已漂：`silent.py` 19 行「codesys_utils 517」（`resolve_system` 在 195 行）、21 行「codesys_ui 48-90」（`ask_yes_no` 在 76 到 96 行）、72 行「Project_Build.py 73」；`messages.py` 4 與 17 行「Project_Build.py」；`cds/ide/__init__.py` 6 行「Project_*.py」，4 到 9 行的模組索引列 6 個而套件有 11 個；`watcher.py` 134 行「section 12」而 WATCHER.md 只有 10 節。
12. `statusform.py` 152 到 155、158 到 162 行兩個 `except Exception: pass`，棘輪只數 `except:` 所以看不到。`watcher.py` 294 行每 2 秒心跳跨 .NET 讀一次專案屬性（A 之後變讀 JSON，仍是每 2 秒讀一次檔）；`permit.refusal` 讀同一設定兩次。

**CLI 的命令表面**

13. `cdsint/flags.py` 描述「哪個命令有哪種形式、收哪些旗標」的地方：`_HELP`（24 到 40 行）、`BOTH_FORMS`（43）、`WATCHER_ONLY`（46）、`PROJECT_ONLY_COMMAND`（50）、`FLAGS`（54 到 63）、`build_parser` 手寫 `installs`、`list` 再事後補 `config`、`plc`（76 到 85 行）、`_add_flag` 依旗標名 if/elif（127 到 136 行）、`command_args` 的分支（159 到 168 行）、`wire_name` 的 plc 分支（171 到 181 行）、`_only_the_project_form`（191 到 212 行）；`cli.py` 的 `main`（120 到 133 行）依名字分 `installs`、`list`、`verify`；`verify.py` 的 `steps`（40 到 45 行）手抄四個命令的 args。五個 `getattr(ns, ..., None)`（`cli.py` 45、128；`flags.py` 201、207、225、239 行）是各子命令 namespace 形狀不同的症狀。`cli._answers`（54 到 61 行）與 `flags._config_args`（184 到 188 行）是兩個 KEY=VALUE 解析器（A 刪後者）。`--target` 定義兩次、兩段幫助文字（101 到 103 與 109 到 110 行）。

**退出碼與拒絕**

14. `cdsint/installs.py` 的 `InstallError`（55 到 60 行）跟 `exits.Failure` 同形（message 加 candidates）但沒帶 code，`cli.main`（118 到 135 行）只接 `Failure`。實測 `cdsint build --project x --install definitely-not-an-ide --sync-dir y` 噴整段 traceback。SPEC 4.3 說「IDE 啟動失敗」是 4。
15. `flags.check`（245 到 253 行）走 `parser.error` 回 2；`refuse_project_flags`（233 到 242 行）丟 `Failure` 回 1，而且不在 `check` 裡，是 `cli.py` 50 行呼叫。實測 `--target foo --profile bar` 回 1。`flags.py` 6 到 7 行說「三種組合」、`check` 的 docstring 說「每個拒絕一次呼叫」，實際四種、跑兩種。
16. 退出碼的決定：`cli.exit_code`（104 到 115 行）管單命令；`cli.run_verify`（86 到 95 行）自己判 OK/FAILED 不經 `exit_code`；`Failure` 丟出點在 `target.py` 43、70、83 行、`headless.py` 127、133、259、263 行、`cli.py` 59 行、`flags.py` 241 行；argparse 三處隱含 2。verify 某步回 `denied` 會是 1 不是 5。

**無頭啟動器 CLI 側**

17. `cdsint/headless.py` 的 `_collect`（226 到 273 行）48 行做六件事。257 行 `print("warning: " + error)` 後 259 行 `raise Failure(error)`，`exits.py` 36 到 40 行再印一次。`_kill`（175 到 196 行）兩個分支都 `return None`，`_launch` 167 行卻拿它當回傳值。`Headless.__init__` 讀 `lock.held` 三次（67、128、213 行），建構子還掃 Program Files 與登錄檔（56 行）。
18. `sync_dir`：`headless.py` 239 行頂層用 IDE 回報值 `or` 旗標；272 行逐筆填旗標值。A 會改成只從 report 來；重核。`Target.sync_dir()`（`target.py` 52 到 54 行）在正式路徑沒人呼叫，`cli.py` 128 到 130 行只在 `--project` 時叫。
19. `timed_out` 與 `exit_code_actual` 是一個事實兩個名字（`headless.py` 241 行 `timed_out = code is None`）；`stdout_reached`（244、301 到 308 行）算了、寫了、沒人讀。`headless.py` 33 到 46 行是帶日期的量測日誌，40 行「the phase-2 table」指的是 SPEC 第 7 節。

**印東西**

20. `report.py` 18 處、`headless.py` 6 處（136 到 137、190 到 194、212 到 223、257 行直印 stderr）、`cli.py` 4 處（`run_list` 自己排表 81 到 83 行、verify 判決 90 到 94 行）、`installs.warn_if_elevated`（130 到 132 行）、`exits.Failure.report`。`report.py` 4 行宣稱「One printer for both forms」。`--json` 下 stderr 會漏警告。
21. `report.py` 的 `show`（78 到 86 行）把 message 文字與 question 收進 `said`，再以 `result["error"] not in said` 決定印不印 error；`_show_needs`（150 到 161 行）為此改動呼叫端傳進來的 list。`_wants_tail`（164 到 170 行）用 `result.get("command") == "compare"` 決定印 tail，因為 compare 的真答案在 `stdout_tail` 不在 `data`。`report.py` 107 到 108 行硬寫廠商清單。

**安裝探測**

22. `irm/setup.ps1` 73 到 128 行 `Find-ScriptDirs` 與 `installs.py` 30 到 42 行 `VENDORS` 加 208 到 224 行 `_script_dir` 加 227 到 241 行 `_under_program_files` 各答一次。PS 第 102 行把 Lenze 3.x 的 ProgramData 標 `NeedsAdmin=$true`，`irm/setup.md` 36 到 38 行照抄；`installs.py` 227 到 241 行的 docstring 卻說 ProgramData 不需要。PS 只掃 `$env:ProgramFiles`（81、107 行），Python 掃兩個 root。`installs.py` 每列的 `roots`（33、35、38 行）完全相同；`_script_dir` 用 `vendor["exe"]` if/elif 加目錄名 `startswith("4.")` 在表外重編每家知識。`run_as_admin_layers`（135 到 156 行）與 `find`（63 到 78 行）巢狀 4 層。`script_dir` 與 `needs_admin` 兩個欄位的唯一讀者是 `report.show_installs`（116 到 117 行）。

**其他**

23. `target.send`（`target.py` 87 到 119 行）巢狀 4 層，交錯輪詢、`missing_since` 去抖、deadline 加清理、Ctrl-C 清理。去抖是在 CLI 端重判存活，`cds/core/instances.is_alive` 已是存活定義；`Target.__init__` 40 到 41 行又先 `live_instances` 過濾一次。
24. 120 秒：`target.py` 18 行 `DEFAULT_TIMEOUT_S`、`flags.py` 91 到 92 行幫助文字硬寫「(default 120)」、`headless.py` 54 行 `timeout=120.0`；`target→flags→cli` 轉手三次，`cli.py` 36 行零使用者。`cli.py` 33 到 34 行帶 `noqa: F401` import 三個 `EXIT_*` 只為讓 `tests/test_cli.py` 寫 `cli.EXIT_TARGET`（20 處）。`cli.py` 28 行模組層 `sys.path.insert` 是 pyproject console script 之外的第二條可 import 路徑，SKILL.md 22 行靠它跑 `python -m cdsint.cli`。

**開工前重核清單**

- 上面每一條先用名字 grep 一次，行號重填，A 已經刪掉的劃掉。
- 特別看 A 之後 `cds/ide/project.py`、`cdsint/headless.py`、`cdsint/flags.py`、`cds/ide/silent.py` 剩什麼。
- 測試基線重跑，Windows 與 WSL 各記一個數字。

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

- [ ] **階段 0：重核與基線**
  - [ ] 第 3 節重核清單做完，行號重填，commit。
  - [ ] 驗收：Windows 與 WSL 測試數記進第 6 節。

- [ ] **階段 1：IDE 側（第 4 節 1、2、7 的 IDE 側、10 的 IDE 側、11、13）**
  - [ ] 驗收：`grep -rn "new_result" cds/ide/` 只剩 `entries.py` 一處；`grep -rn "error_text()" cds/ide/` 一處。
  - [ ] 驗收：測試涵蓋「`project_info` 丟例外時 `permit.refusal` 的訊息說讀不到而不是 not set」「`silent.run` 在本體模組層級就呼叫對話框時替身有接到」「引擎某檔加一行模組層級 `from engine.codesys_ui import ask_yes_no` 時 `test_layering` 紅」（用 tmp 檔或 monkeypatch 的方式驗，不真的改引擎）。
  - [ ] 驗收：`wc -l cds/ide/*.py` 每個檔在 300 以內；`statusform.StatusForm.__init__` 在 40 行內。

- [ ] **階段 2：CLI 的表與退出碼（第 4 節 3、4、5、7 的 CLI 側、10 的 CLI 側）**
  - [ ] 驗收：`cdsint build --project x --install definitely-not-an-ide` 回一句話加候選清單，exit 4，沒有 traceback。
  - [ ] 驗收：`cdsint build --target foo --profile bar`、`cdsint plc connect --target foo`、`cdsint export --target a --project b` 都 exit 2 且訊息各自說理由。
  - [ ] 驗收：`grep -n "getattr(ns" cdsint/` 為零；`grep -n "BOTH_FORMS\|WATCHER_ONLY\|PROJECT_ONLY_COMMAND\|_add_flag" cdsint/` 為零；`--target` 的 `add_argument` 只出現一次。
  - [ ] 驗收：測試涵蓋「verify 某步回 denied 時 exit 5」「`needs_yes` 的紀錄有 `new_result` 全部十二個鍵」「COMMANDS 表每一列都出現在 `cdsint --help`」。

- [ ] **階段 3：安裝探測一個主人（第 4 節 6）**
  - [ ] 驗收：`cdsint installs --json` 每筆有 `script_dir` 與 `needs_admin`；`irm/setup.ps1` 裡 `grep -c "Program Files\|ProgramData\|ScriptDir\\\\"` 為零（路徑知識只在 Python）。
  - [ ] 驗收：對 `%TEMP%\cdsint-work\plumbing\fake-scriptdir\` 跑 `.\irm\setup.ps1 -List`，列出的跟 `cdsint installs` 一致；`-Clone .` 對假 ScriptDir 裝得起來（不碰真的 junction，見 `WORKER_RULES.md`）。
  - [ ] 驗收：`irm/setup.md` 說的管理員規則跟 `installs.py` 一致，實測結果寫進第 7 節。

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

同 `SETTINGS_PLAN.md` 第 6 節。

---

## 7. 未決事項與裁決

`Ruling: 決定 — 理由 — 錯了的代價`。

先列出來的：

1. `COMMANDS` 表用 dict 還是 namedtuple 清單。預設：dict，鍵是命令名，值是一個小 dataclass 或 dict；讀者要能用 `COMMANDS["plc"]` 一眼看到那一列。
2. `EXIT_*` 搬到 `cds/core/exits.py` 之後，`cdsint/exits.py` 的 `Failure` 留在 CLI 側還是也搬。預設：`Failure` 留 CLI 側，它是 CLI 的例外；常數才是兩側共用的。
3. `compare` 放進 `data` 的逐物件清單長什麼樣。預設：跟 `discover` 的 `unknown` 同一種形狀，一個 list of dict，每筆有 `name`、`path`、`state`（`changed`、`new_in_ide`、`new_on_disk`、`pending_import` 之一）。
4. ProgramData 要不要管理員：在這台實測。

做的時候看到但不在範圍的，記在這裡給 C 和 D：

- （worker 填）

---

## 8. 接手 prompt

你在 `C:\Users\qazsskevin\Documents\repo\cdsint-plumbing`，分支 `ticket/plumbing`。先讀 `docs/WORKER_RULES.md`、本工單第 0 到 4 節、`docs/SPEC.md` 的 D2、D7、D8、D12、4.2、4.3、6.3、6.4、`docs/WATCHER.md`、`PRINCIPLES.md`、`CLAUDE.md`。然後從第 5 節第一個沒打勾的項目開始做，階段照順序。一段做完、測試綠、commit；做完的項目打勾並 commit。決定了第 7 節的事就寫回。看到不在範圍的爛東西記進第 7 節末尾，不修。全部做完照第 6 節回報，停下來，不要 merge、不要 push。
