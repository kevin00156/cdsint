# 工單 A：設定從 `.project` 的專案屬性搬到專案旁的 JSON 檔

> 建立日期 2026-09-06。分支 `ticket/settings`，worktree `C:\Users\qazsskevin\Documents\repo\cdsint-settings`。
> 鐵律在 `docs/WORKER_RULES.md`，先讀它。使用者不在也不會回答，卡住寫進最後回報。
> 這是四張工單的第一張，後面依序是 `PLUMBING_PLAN.md`、`HYGIENE_PLAN.md`、`ENGINE_PLAN.md`。
> 那三張會再碰這張改過的檔案，所以這張只做這張的事，看到別的爛東西記進第 7 節，不順手修。

---

## 0. 本工單專屬的鐵律

- 臨時檔在 `%TEMP%\cdsint-work\settings\` 底下。
- 這張工單不碰 PLC 台架。`plc connect` 的驗收只驗「拒絕」那一半，能連上算加分，連不上不算失敗。
- 不做遷移。既有專案的舊屬性留在 `.project` 裡不讀、不刪、不提。

---

## 1. 目標與範圍

設定今天存在 `.project` 二進位檔的專案屬性裡，只有 IDE 行程開得了。要改一個布林值得先弄到一個活著的 IDE；agent 想看設定得起一個 IDE；每個新專案從零開始。這一個事實養出了一整圈補丁：四條入口（Properties 表格、Settings 視窗、`config` 命令、第一次匯出的對話框）、`--project` 形式強制 `--sync-dir`、電腦名稱不符的對話框、`config set` 之後再按引擎收尾。

做完之後：設定是專案檔旁邊的一個 JSON 文字檔，任何編輯器都能改，不需要 IDE。專案屬性那條路整段刪掉，連同只為它存在的機制。

明確不做：
- 遷移舊屬性（決定表第 7 條）。
- 任何新的旗標、命令、對話框。
- 引擎其他地方的去重（那是 `ENGINE_PLAN.md`）、`cds/` 與 `cdsint/` 的平行路徑（`PLUMBING_PLAN.md`）、文件現況欄與測試假物件（`HYGIENE_PLAN.md`）。看到就記第 7 節，不做。

---

## 2. 使用者定案的決定（2026-09-06，逐題）

| # | 決策 | 選擇 | 理由 |
|---|---|---|---|
| 1 | JSON 放哪 | 專案檔旁邊，照專案名：`Line.project` 旁的 `Line.cdsint.json` | 十二個設定大多是這台機器的事，不是團隊政策；只有放這裡才能連同步資料夾一起搬出來，讓專案屬性那條路整個關掉。先例：下載紀錄 `Line.cdsint-plc.json` 已經這樣做 |
| 2 | 跟下載紀錄合併？ | 獨立一個檔 | 人決定的偏好和機器跑完留下的紀錄生命週期不同；合併等於 `plc download` 每次重寫一個人手編輯的檔 |
| 3 | 鍵名 | 拿掉 `cds-sync-` 前綴，蛇形：`sync_folder`、`plc`、`debug`、`export_xml`、`backup_binary`、`safety_backup`、`backup_name`、`backup_retention_count`、`save_after_import`、`save_after_export`、`auto_delete_orphans` | 前綴是為了在 Properties 表格裡跟別人區分，進自己的檔就是噪音。這正是 `engine/settings.py` 的 `SETTINGS` 表對話框已經在用的鍵名 |
| 4 | `cds-sync-plc` 留在專案屬性？ | 也搬進 JSON。專案屬性是 legacy，整段刪 | 使用者明說。代價是 D8 和 SPEC 6.5 那句「人在 IDE 裡決定過」不再成立，門變成「檔案裡有寫」加 `-y` |
| 5 | `config set` 可以寫 `plc` 嗎 | 開放（後來 `config` 整個刪掉，此題失效） | 一個自己承認擋不住的門不是門，是特殊情況 |
| 6 | `cds-text-sync-multipleApps` | 刪掉旗標，build 時現數 application | 它是會過期的快取，`cds/ide/entries.py` 已記錄它造成的 bug。build 本來就會走樹，多幾百次 .NET 讀取跟一次編譯比不算什麼 |
| 7 | 遷移 | 不遷移 | 還沒發布過版本，唯一沒預設值的是同步資料夾，而它本來就有對話框會問 |
| 8 | `--sync-dir` | 改成選用，只在這一趟記憶體裡生效，永不寫檔 | 只複製 `.project` 的副本什麼都不帶；連 JSON 一起複製才會帶路徑，而相對路徑規則讓常見情況是 `./sync`。空同步資料夾拒絕匯入那道護欄留著 |
| 9 | `config` 命令 | 整個刪掉，檔案就是介面 | 三個選項裡唯一沒有特殊情況的。驗證放在讀檔那一支，唯一一份，所有路都經過 |
| 10 | `pc` 戳記 | 刪掉，連同電腦名稱不符的對話框 | 刪掉 `config` 之後只有對話框那條路會寫它，人手寫的 JSON 沒有，一個只對一半情況生效的護欄是特殊情況。電腦名稱是「資料夾在不在」的代理人 |
| 11 | `version` 戳記 | 刪掉，連同版本不符的檢查和 `--force` 旗標 | D15 說 `.st` 格式不准改，同一個大版本裡這個檢查永遠抓不到真問題，只會每次升級要你多打一次 `--force`。`--force` 只回答這兩個對話框，所以一起消失 |
| 12 | IDE 裡的對話框 | 留第一次跑時問資料夾的那個，刪 Settings 視窗和狀態視窗的 Settings 按鈕 | 前者是一個問題換一個能用的專案；後者是同一個檔案的第二個編輯器，每加一個鍵就要多一列 |
| 13 | 未知鍵、型別錯 | 整個命令拒絕，訊息列出十一個鍵和各自的預設值 | 檔案是人手改的，打錯字必然發生；安靜地沒效果比錯誤更糟 |
| 14 | 對話框寫出的檔 | 只寫 `sync_folder` 一個鍵 | 預設值只在程式碼裡一份；檔案裡出現的每一行都是有人決定過的，「我選的」和「它填的」分得出來 |
| 15 | `plc` 的型別 | 清單 `["connect", "download"]` | JSON 有清單，切逗號那段是遷就 Properties 才存在的 |
| 16 | 「搬遷不會自動修好」的九條 | 全部進本工單當驗收條件 | 它們在搬遷經過的檔案裡，不順手做就會留渣 |

---

## 3. 接手前必須知道的現況事實

全部是 2026-09-06 晚上在 `main` 的 `631259b` 上查的。行號會漂，名字不會；先用名字 grep 再信行號。

**設定今天怎麼讀寫**

1. 屬性名字在 `cds/core/props.py`（47 行）：`PREFIX = "cds-sync-"`，十三個常數，加上不帶前綴的 `MULTIPLE_APPS = "cds-text-sync-multipleApps"`。SPEC 4.4 那張表是它的第二個證人，`tests/test_props.py` 綁著兩邊。
2. 引擎讀寫在 `engine/codesys_utils.py`：`get_project_prop`（382 行起）讀出來是字串再猜型別，`"true"`/`"false"` 變布林、全數字變整數；`set_project_prop`（409 行起）寫入時 `str(value)`，而且對 `props.DEBUG` 有一條特例去清 `_debug_flag` 快取。`is_debug`（431 行起）用模組層級 list `_debug_flag` 當快取，`reset_debug_cache` 清它。同一條 `proj.get_project_info() if hasattr(...) else getattr(proj, "project_info", None)` 加 `info.values if hasattr(info, "values") else info` 的 hasattr 鏈在這個檔貼了四份：`Logger._initialize`（52 到 66 行，用 `projects` 這個名字，在這個模組裡是未定義的，NameError 被 bare except 吞掉）、391 與 394、424 與 427、487 與 488。
3. IDE 側另有一份讀寫：`cds/ide/project.py` 的 `prop`（27 行起）、`set_prop`（41）、`save`（59）、`_values`（77）、`sync_dir`（94 到 111）。`cds/ide/config.py`（124 行）是 `config get/set` 的本體，`PROPERTIES` 表列十二個可寫的，`READ_ONLY = props.PLC`。
4. 呼叫 `get_project_prop`、`set_project_prop`、`project.prop`、`project.set_prop` 的地方共 43 處，分佈在 `engine/codesys_utils.py`、`entry_build.py`、`entry_compare.py`、`entry_export.py`、`entry_import.py`、`settings.py`、`cds/ide/config.py`、`headless.py`、`permit.py`。每一處讀出來之後常常再自己 `bool()` 或 `int()` 一次。

**同步資料夾**

5. `load_base_dir`（`codesys_utils.py` 543 到 641 行）做五件事：讀屬性、解相對路徑（557 到 577 行）、電腦名稱不符對話框（585 到 630 行，`ask_yes_no_cancel("Computer Mismatch Detected", ...)`）、對話框之後再解一次相對路徑（611 到 618 行，是上面那段的貼上版）、`os.makedirs`。相對路徑判定另外在 `engine/settings.py` 的 `_as_written`（158 到 178 行）又寫一次。
6. 第一次跑的對話框：`engine/settings.py` 的 `choose_sync_folder`（49 到 84 行），被 `entry_export.py` 的 `main`（440 到 460 行）和 `entry_import.py` 的 `main`（281 到 286 行）在屬性沒設時呼叫。選完走 `_as_written`、`set_project_prop`、`_remember_who_and_what`（200 到 213 行，寫 `pc` 與 `version`）、`_prepare`（216 到 227 行，建目錄、`ensure_git_configs`、`update_application_count_flag`）。對話框本身是 `engine/codesys_ui.py` 的 `show_sync_folder_dialog`（448 行起）與 `SyncFolderPathForm`（394 行起）。
7. `--sync-dir` 今天的路：CLI 側 `cdsint/headless.py` 62 行 `os.path.abspath`，87 行放進 job；IDE 側 `cds/ide/headless.py` 的 `run_job`（72 到 118 行）呼叫 `point_sync_folder`（201 到 214 行）把它寫進屬性，之後 `finalize_sync_operation` 的存檔會讓它落地到 `.project`。`cdsint/flags.py` 的 `_needs_sync_dir`（215 到 230 行）讓 `--project` 少了它就 `parser.error`，`check`（245 到 253 行）呼叫它。`cdsint/headless.py` 239 行頂層 `sync_dir` 取 IDE 回報值，272 行逐筆卻填旗標值。
8. 看門人登記檔的 `sync_dir` 欄位由 `cds/ide/watcher.py` 274 行每次心跳讀 `project.sync_dir` 填入；`cdsint status --json` 的 `data.sync_dir` 就是它。

**`config` 命令**

9. `cdsint/flags.py`：`_HELP` 37 行、`BOTH_FORMS` 43 到 44 行含 `"config"`、`_config_arguments`（139 到 144 行）、`command_args`（147 到 155 行）對 config 分支、`_config_args`（184 到 188 行）。`cdsint/cli.py` 12 到 16 行的 docstring 範例含 `config set`。
10. `cds/ide/entries.py`：61 行把 `"config"` 加進允許清單，89 到 91 行 `if command == "config"` 特例，`_folder_follow_up`（101 到 121 行）在 `config set cds-sync-folder` 之後用 `silent.run` 按 `engine/settings.py` 的 `folder_was_set`（139 到 156 行）。`silent.Outcome.ok`（103 到 104 行）在正式碼裡只有它在用。

**版本與電腦戳記、`--force`**

11. `check_version_compatibility`（`codesys_utils.py` 1823 到 1846 行）被 `entry_compare.py` 47 行和 `entry_import.py` 73 行呼叫；import 那邊不符就 `ask_yes_no("Version Mismatch Warning", ...)`（82 行）。`finalize_sync_operation`（1883 行起）開頭寫 `props.VERSION`。`tests/test_sync_version_stamp.py` 整支在測這個順序。
12. `--force` 在 `cdsint/flags.py` 的 `FLAGS`（56 到 57 行 import、61 到 62 行 verify）、`cdsint/cli.py` 87 行、`cdsint/verify.py` 42 行。IDE 側的答案表在 `cds/ide/silent.py`：`YES_NO`（35 到 40 行）的 `"Version Mismatch Warning": ("force", False)`，`YES_NO_CANCEL`（44 到 46 行）的 `"Computer Mismatch Detected": "force"`，`_yes_no_cancel`（334 到 340 行），`_ui_patches`（299 到 304 行）換掉的三個函式之一是 `ask_yes_no_cancel`。`engine/codesys_ui.py` 的 `ask_yes_no_cancel`（98 行起）除了 `load_base_dir` 只有 `show_directory_choice_dialog`（383 行起）在用，而後者沒有呼叫端。`tests/test_silent.py` 182 行起有一條測電腦名稱不符。

**multipleApps**

13. 寫：`entry_export.py` 283 到 290 行在主迴圈數 application，372 行 `set_application_count_flag(app_count)`；`codesys_utils.py` 的 `set_application_count_flag`（470 到 495 行，裡面還順手刪一個叫 `"boolean"` 的舊屬性）、`count_applications`（512 到 521 行，只比 `APPLICATION_GUID = "639b491f-…"` 一個值）、`update_application_count_flag`（527 到 540 行）；`entry_build.py` 170 行、`engine/settings.py` 227 行也呼叫。`tools/perf_probe.py` 234 行列它當量測項。
14. 讀：`entry_build.py` 112 到 160 行。旗標為真才走樹找 application，用 `APP_GUID = "639b491f-…"`；旗標為假就取 `active_application`，再沒有就用另一個 GUID `"6394ad93-…"` 遞迴找第一個。兩個 GUID 在 `profiles/default.json` 都是 `application` 的 alias，`engine/codesys_constants.py` 142 行的 `kind_of` 能把任一個對回 `"application"`。
15. `cds/ide/entries.py` 的 `wrong_application`（156 到 174 行）在 build 之後掃訊息文字找 `--app` 的名字，來偵測「旗標還沒設所以跳過選擇」的 bug。`cds/ide/headless.py` 151 行和 `cds/ide/watcher.py` 250 行都呼叫它。

**Settings 視窗**

16. `engine/codesys_ui.py` 的 `SettingsForm`（122 到 297 行）與 `show_settings_dialog`（302 到 310 行）。`engine/settings.py` 的 `SETTINGS` 表（26 到 36 行）、`edit`（87 到 110 行）、`_apply_folder`（113 到 136 行）。進入點是 `stub/Project_watch.py` 14 行 `from engine import settings`、16 行 `settings=settings.edit`，經 `cds/ide/session.py` 31、37 到 39、50、55、66 到 69 行的 `settings` 參數與 `on_settings` lambda，到 `cds/ide/statusform.py` 39、51、83 到 93、167 到 173 行的按鈕。`tests/test_settings.py`（180 行）測這條。

**PLC 授權**

17. `cds/ide/permit.py`（75 行）直接用 `project.prop` 讀 `props.PLC`，切逗號、去空白、轉小寫再對 `ACTIONS = ("connect", "download")`。拒絕訊息說「Only a person in the IDE can change that: Project Information > Properties」。`tools/grant_plc.py`（126 行）是台架用來寫這個屬性的 `--runscript` 腳本。`tests/test_plc.py`、`test_cli.py`、`test_config.py`、`test_props.py` 提到它。

**替身 UI 的文案**

18. `cds/ide/silent.py` 的 `_no_folder_dialog`（307 到 317 行）在無人時把資料夾對話框換成 `NeedsInput`，訊息說三條路：`cdsint config set`、Project Information > Properties、選單跑一次匯出。

**文件裡提到的地方**

19. `readMe.md`：62、70 到 72（`--sync-dir` 必填的理由）、172（升級段說屬性不動）、190 與 194（`--force`）、195（config 列）、204、248、267 到 273（plc 授權）、312（exit 5）、334（版本不符 FAQ）、338 到 340（設定在哪 FAQ）。
20. `docs/AI_WORKFLOW.md`：50、99 到 100、161、178 到 183（force）、222 到 256（`--sync-dir` 必填）、282 到 295（第 5 節 config 整節）、301 到 304、313 到 314、387。
21. `skills/cdsint/SKILL.md`：43、68 到 76、95 到 104、129、163、186。
22. `docs/WATCHER.md`：96（命令表的 config 列）、157。
23. `docs/SPEC.md` 的 D8、D10、4.2、4.3、4.4、5.2、6.5、6.7 已經由監督者改寫成做完的樣子（跟本工單同一個 commit）。SPEC 是規格，工單是施工；兩邊講的不一樣以 SPEC 為準並記進第 7 節。

**測試**

24. 直接測這些機制的：`tests/test_config.py`（191 行）、`test_settings.py`（180）、`test_props.py`（61）、`test_project_props.py`（讀寫屬性的引擎 helper）、`test_sync_version_stamp.py`。間接碰到 `force`、`sync_dir`、`props.PLC` 的：`test_cli.py`、`test_commands.py`、`test_headless.py`、`test_silent.py`、`test_verify.py`、`test_empty_sync_folder.py`、`test_plc.py`、`test_profile.py`、`test_project.py`、`test_watcher.py`。
25. 基線：Windows 與 WSL 都是 948 passed（2026-09-06 晚上，`631259b`）。

---

## 4. 設計

**檔案。** `<專案主檔名>.cdsint.json`，跟 `.project` 同一個目錄。UTF-8，縮排 2，鍵照字母排序。只出現人決定過的鍵。長這樣：

```json
{
  "plc": ["connect"],
  "sync_folder": "./sync"
}
```

**Schema，一份。** `cds/core/props.py` 改名成 `cds/core/settings.py`，職責從「屬性名字表」變成「設定的 schema 與讀寫」。純 Python，兩側共用，CI 測得到。內容：

- 一張表，每個鍵一列：名字、型別、預設值、一句意思。十一個鍵：`sync_folder`（str，無預設）、`plc`（list of str，預設空清單，元素只認 `connect`、`download`）、`debug`（bool，False）、`export_xml`（bool，False）、`backup_binary`（bool，False）、`safety_backup`（bool，True）、`backup_name`（str，空）、`backup_retention_count`（int，10）、`save_after_import`（bool，True）、`save_after_export`（bool，True）、`auto_delete_orphans`（bool，False）。
- `path_for(project_path)`：`.project` 路徑對到 JSON 路徑。
- `read(path)`：檔案不存在回 `None`；存在就 parse 並驗證，不認識的鍵、型別不對、`plc` 裡有不認識的字、JSON 壞掉，一律 raise 一個帶人話的例外，訊息列出十一個鍵和預設值。回傳的是檔案裡有的鍵，不補預設值，這樣呼叫端分得出「沒設」和「設成預設值」。
- `resolve(written)`：把 `read` 的結果補上預設值，回完整的十一個鍵，型別就是表上的型別，呼叫端不再自己轉。
- `write(path, values)`：只寫傳進來的鍵，覆蓋整個檔。
- `folder(written, project_dir)`：相對路徑解析，唯一的一份。`./` 開頭或 `.` 就對 `project_dir` 解，其他照用。取代 `load_base_dir` 裡的兩份和 `settings._as_written` 的判定那半（`_as_written` 產生相對路徑那半留在引擎，因為它只有對話框用）。
- 前綴常數 `PREFIX` 刪掉；`MULTIPLE_APPS` 刪掉。

**引擎怎麼讀。** `engine/codesys_utils.py` 的 `get_project_prop`、`set_project_prop`、`is_debug` 的快取、`reset_debug_cache`、四份 hasattr 鏈全部刪。取而代之的是 `engine/settings.py` 的一個函式：以 `projects.primary.path` 找到 JSON，`read` 加 `resolve`，加上這一趟的 `sync_folder` 覆蓋值，回一個 dict。一次命令讀一次，結果傳給需要的人；不用模組層級快取，因為讀一個小 JSON 不是跨 .NET 的成本。`Logger._initialize` 找 log 路徑改用同一條。所有原本 `get_project_prop(props.X, default)` 的呼叫端改成從那個 dict 取值，型別直接用，不再 `bool()`、`int()`。

**`--sync-dir` 怎麼進來。** 變成命令的一個引數，跟 `--yes` 同一條路：CLI 側把它放進每一步的 `args["sync_dir"]`，IDE 側 `silent.run` 本來就會把 args 注入本體的 `command_args`，本體讀到就交給引擎的設定函式當覆蓋值。引擎不寫它、不存它。`point_sync_folder` 刪，`run_job` 不再碰專案屬性，report 的 `sync_dir` 填引擎實際解析出來的值，CLI 逐筆那一行不再自己填。`--sync-dir` 在 argparse 變成選用；`--project` 形式沒有 JSON 也沒有 `--sync-dir` 時，export 和 import 走到「沒有資料夾」的地方回 `needs_input`，跟 `--target` 一樣。

**第一次跑。** `entry_export.main` 與 `entry_import.main` 在 `resolve` 之後發現 `sync_folder` 沒設就呼叫 `settings.choose_sync_folder`：對話框選完走 `_as_written` 產生相對路徑，`write` 一個只有 `sync_folder` 的 JSON，`_prepare` 建目錄、寫 git 規則（`update_application_count_flag` 那行刪）。`_remember_who_and_what` 刪。確認訊息多一行：其他設定和預設值見 readMe 的設定表。無人時 `silent._no_folder_dialog` 的訊息改成：這個專案還沒有同步資料夾，在專案旁寫 `<檔名>`，內容 `{"sync_folder": "<路徑>"}`，或從選單跑一次匯出。

**PLC 授權。** `cds/ide/permit.py` 用 `cds/core/settings` 讀 `plc` 清單，`granted` 是清單和 `ACTIONS` 的交集，切逗號那段刪。拒絕訊息說三件事：檔案在哪、現在的值是什麼、要加什麼。`tools/grant_plc.py` 刪，台架直接在副本旁寫 JSON。

**build 找 application。** `entry_build.py` 的 112 到 160 行整段換成：走一次 `get_children(recursive=True)`，`kind_of(safe_str(obj.type)) == "application"` 的收成清單；`--app` 給了就按名字挑，挑不到 `result(False, ...)`；沒給而清單超過一個才問 `system.ui.choose`；一個就用它。兩個 GUID 字面值、`APPLICATION_GUID` 常數、`count_applications`、`set_application_count_flag`、`update_application_count_flag`、export 主迴圈的 `app_count`、`entries.wrong_application` 及它的兩個呼叫端，全部刪。

**刪掉的清單，一條一條打勾用。**

- `cds/ide/config.py`；`cdsint/flags.py` 裡 `config` 的四處；`cli.py` docstring 範例；`entries.py` 的 61、89 到 91 行特例、`_folder_follow_up`；`engine/settings.py` 的 `folder_was_set`、`edit`、`_apply_folder`、`SETTINGS` 表；`silent.Outcome.ok`。
- `--force`：`flags.FLAGS` 兩列、`cli.py` 87 行、`verify.py` 42 行。
- `check_version_compatibility`、`finalize_sync_operation` 開頭寫 version 那段、import 的版本對話框、`silent.YES_NO` 那一列、`tests/test_sync_version_stamp.py`。
- `load_base_dir` 的電腦名稱段、`silent.YES_NO_CANCEL`、`_yes_no_cancel`、`_ui_patches` 裡那一項、`codesys_ui.ask_yes_no_cancel`、`show_directory_choice_dialog` 與 `DirectoryChoiceForm`（沒有呼叫端）、`tests/test_silent.py` 182 行那條。
- multipleApps 那一整組（現況 13 到 15）。`tools/perf_probe.py` 234 行那一列跟著刪。
- `SettingsForm`、`show_settings_dialog`、`statusform.py` 的 Settings 按鈕與 `on_settings` 參數、`session.py` 的 `settings` 參數與 lambda、`stub/Project_watch.py` 的 import 與引數、`tests/test_settings.py` 裡測視窗的部分。
- `cds/ide/project.py` 的 `prop`、`set_prop`、`save`、`_values`（`sync_dir` 改讀 JSON 後留著，`path_of`、`ide_name` 等不相關的留著）。
- `tools/grant_plc.py`。
- `codesys_utils.py` 裡刪 `"boolean"` 舊屬性那段。

**文件。** readMe 加一節設定表：鍵、意思、預設值、型別，取代 338 到 340 行的 FAQ；命令表拿掉 config 列和 `[--force]`；`--sync-dir` 改成選用並說明覆蓋語意；plc 那段改成 JSON 的 `plc` 清單加 `-y`；exit 5 的說法跟著改；升級段那句「屬性不動」改成「舊屬性不再被讀，第一次匯出會再問一次資料夾」。`docs/AI_WORKFLOW.md` 第 5 節改寫成「設定檔在哪、長什麼樣、agent 怎麼寫」；第 2 節的 force 列刪；第 4 節 `--sync-dir` 改選用；第 6 節 plc 授權改寫；第 9 節那條 `--force` 刪。`skills/cdsint/SKILL.md` 對應的六處。`docs/WATCHER.md` 96 與 157 行。`CHANGELOG.md` Unreleased 加一段：症狀、根因、改法。

---

## 5. 分階段與驗收

- [x] **階段 0：基線**
  - [x] 複製 softplc 到 `%TEMP%\cdsint-work\settings\softplc\`，用現在的程式碼跑 `export --project ... --install 3.5.21.40 --sync-dir <空資料夾>`，照 `WORKER_RULES.md` 儀器那節存 hash 清單到 `%TEMP%\cdsint-work\settings\baseline-softplc.txt`。
  - [x] Shm 副本同樣做一份，`--install "DIADesigner-AX 1.10" --answer UpgradeProjectConfirmation=Yes`。
  - [x] 驗收：兩份物件數各 229（檔案數 231 與 233，見第 7 節 Ruling 13）。

- [x] **階段 1：schema 與讀寫，純 Python**
  - [x] `cds/core/props.py` 改名 `cds/core/settings.py`，照第 4 節。`tests/test_props.py` 改寫成 `tests/test_core_settings.py`。
  - [x] 驗收：測試涵蓋「檔案不存在回 None」「未知鍵拒絕且訊息列出十一個鍵」「型別錯拒絕」「`plc` 裡有 `downlaod` 拒絕且原字出現在訊息」「`resolve` 補齊十一個鍵且型別正確」「`write` 只寫給的鍵」「`folder` 對 `./sync`、`.`、絕對路徑、另一個磁碟四種情況」「`path_for` 對含中文的路徑」。
  - [x] 驗收：`grep -rn "cds-sync-" cds/core/` 為零。

- [x] **階段 2：引擎改讀 JSON**
  - [x] 照第 4 節「引擎怎麼讀」「第一次跑」「build 找 application」，刪第 4 節清單裡屬於引擎的項目。
  - [x] 驗收：用假 IDE 物件的測試涵蓋「JSON 有 `debug: true` 就寫 log」「第一次跑對話框寫出的 JSON 只有 `sync_folder`」「覆蓋值給了就用覆蓋值且 JSON 不被寫」「build 有兩個 application 且 `--app` 給錯名字回 ok False」「build 有兩個 application 沒給 `--app` 才問」「build 一個 application 不問」。
  - [x] 驗收：`grep -rn "get_project_prop\|set_project_prop\|project_info\|_debug_flag\|MULTIPLE_APPS\|APPLICATION_GUID\|check_version_compatibility\|Computer Mismatch\|Version Mismatch\|ask_yes_no_cancel\|SettingsForm" engine/` 為零。
  - [x] 驗收：引擎裡讀設定的地方沒有 `bool(`、`int(` 包著設定值：`grep -rn "bool(settings\|int(settings\|bool(cfg\|int(cfg" engine/` 為零，或用你實際取的變數名。

- [x] **階段 3：IDE 側管線**
  - [x] `permit.py` 改讀清單；`project.sync_dir` 改讀 JSON；`cds/ide/headless.py` 的 `run_job` 不再寫屬性，`sync_dir` 進每一步的 args；`silent._no_folder_dialog` 文案；刪 `config.py`、`_folder_follow_up`、`wrong_application`、`YES_NO_CANCEL`、`_yes_no_cancel`、Settings 按鈕那一整條、`Outcome.ok`。
  - [x] 驗收：測試涵蓋「`plc` 清單沒有 `download` 時 `plc download` 回 denied 且訊息含檔名與鍵名」「`plc: ["DOWNLOAD"]` 大寫也算」「沒有 JSON 時 `--target` 形式 export 回 `needs_input` 且訊息含檔名」「`run_job` 帶 `sync_dir` 跑完副本旁沒有 JSON」「登記檔的 `sync_dir` 來自 JSON」。
  - [x] 驗收：`grep -rn "cds-sync\|config\b\|Properties\|wrong_application\|on_settings\|YES_NO_CANCEL" cds/ stub/` 為零（註解裡的英文單字 config 若指別的東西，改掉那個字）。

- [x] **階段 4：CLI**
  - [x] 刪 `config` 子命令、`--force`、`_needs_sync_dir`；`--sync-dir` 選用；每一步的 args 帶 `sync_dir`；`cdsint/headless.py` 272 行那行刪，`sync_dir` 只從 report 來；`cli.py` docstring。
  - [x] 驗收：`cdsint config` 回 argparse 的「invalid choice」；`cdsint import -y --force --target x` 回「unrecognized arguments」；`cdsint build --project P --install I` 不給 `--sync-dir` 過得了 argparse；`tests/test_cli.py`、`test_verify.py`、`test_headless.py` 對應改。
  - [x] 驗收：`grep -rn "force\b\|sync_dir\|config" cdsint/` 只剩 `force_lock` 與 `sync_dir` 覆蓋值的傳遞。

- [x] **階段 5：工具與文件**
  - [x] 刪 `tools/grant_plc.py`；`perf_probe.py` 那一列。
  - [x] 文件照第 4 節「文件」段。
  - [x] 驗收：`grep -rn "cds-sync-\|config set\|config get\|--force\b\|Project Information\|multipleApps\|grant_plc" readMe.md docs/AI_WORKFLOW.md docs/WATCHER.md skills/ tools/ cdsint/ cds/ engine/ stub/` 為零。`docs/SPEC.md`、`CHANGELOG.md`、`docs/history/` 不在範圍。
  - [x] 驗收：`python -m pytest tests -q` 綠，WSL 那條綠。`tests/test_doc_links.py` 綠。

- [x] **階段 6：真 IDE 驗收（無頭，worker 自己跑）**
  - [x] softplc 副本旁沒有 JSON：`export --project ... --install 3.5.21.40 --json` 不給 `--sync-dir`，exit 1，`needs_input` 不是 null，訊息含 `softplc_refactor.cdsint.json`。副本旁仍然沒有 JSON。
  - [x] 同一副本給 `--sync-dir <階段 0 的資料夾>`：exit 0，hash 清單跟 `baseline-softplc.txt` diff 為空，副本旁仍然沒有 JSON。
  - [x] 在副本旁手寫 `softplc_refactor.cdsint.json` 內容 `{"sync_folder": "./sync"}`：`verify -y --project ... --install 3.5.21.40` 不給 `--sync-dir`，exit 0，輸出第一行的 sync folder 是副本旁的 `sync`，report 的 `sync_dir` 同一個值。
  - [x] 同一副本 `plc connect --project ... --install 3.5.21.40`：exit 5，訊息含檔名、`plc`、`connect`。改 JSON 加 `"plc": ["connect"]` 再跑：不是 exit 5。台架不在就記「台架不在」。
  - [x] JSON 寫成 `{"sync_folder": "./sync", "debgu": true}`：任何命令 exit 1，訊息含 `debgu` 和十一個鍵的清單。
  - [x] Shm 副本：`verify -y --project ... --install "DIADesigner-AX 1.10" --answer UpgradeProjectConfirmation=Yes --sync-dir <階段 0 的資料夾>` exit 0，hash 清單跟 `baseline-shm.txt` diff 為空。
  - [ ] 驗收（還需要人，沒做）：在有畫面的 IDE 開一個沒有 JSON 的副本，從 Scripts 選單跑 Project_export，對話框問資料夾，選完副本旁出現只有 `sync_folder` 的 JSON，資料夾裡有 `.gitignore` 與 `.gitattributes`。看門人狀態視窗沒有 Settings 按鈕。
  - [x] 沒有殘留的 IDE 行程；`%TEMP%\cdsint-work\settings\` 清掉。

---

- [ ] **階段 7：審查後修正（監督者 2026-09-06 晚上派回）**

  一個沒看過對話的 reviewer 對 `main..ticket/settings` 的 diff 審過，四個真 bug 監督者逐條重現過。前四條必修，五到十一條是工單自己的勾與文件說謊，同一輪修掉；十二到十六條順手。全部修完照第 6 節再回報一次。

  - [ ] **1. 設定檔壞掉時 `build` 與 `discover` 靜默用預設值跑完並回 ok。** `engine/settings.py` 的 `prepare` 對「檔案不合法」和「還沒設 `sync_folder`」都回 `(None, None, error)`，`entry_build.py` 的 `main` 與 `entry_discover.py` 為了容忍後者把 `_error` 丟掉，連前者一起吞。實測專案旁放 `{"sync_folder": "./sync", "debgu": true}`，`build` 回 `ok: True`，一句話都沒有。這正是 SPEC 4.4「整個命令拒絕」要殺的東西，階段 6「打錯字時任何命令 exit 1」對這兩個命令不成立。改法：`prepare` 把兩種情況分開，檔案壞回 error，沒資料夾回 `(values, None, None)`；`values["debug"] if values else False` 和 `values or {}` 兩處特例跟著消失；`build_project` 的 `values` 參數沒人讀，刪。
  - [ ] **2. 設定檔壞掉時 `plc` 回 exit 5 並謊報「清單是空的」。** `cds/ide/permit.py` 的 `_written` 把 `settings.Invalid` 吞成 `[]`。它的註解說「本體等一下會再讀同一個檔完整報錯」是假的：`entries.run` 在 `_not_allowed` 拒絕後直接 return，本體從不載入。後果是 agent 照訊息加 `"plc": ["connect"]` 再跑還是 exit 5，永遠找不到那個錯字。改法：`Invalid` 往上冒，`_not_allowed` 對它回 `error` 是 `Invalid` 的訊息、`denied` 是 None，exit 1 不是 5。`tests/test_plc.py` 對應那段註解一起改。
  - [ ] **3. `--target` 形式每個命令第一行多印 `sync folder: …`。** `cdsint/cli.py` 的 `run_command` 與 `run_verify` 現在無條件呼叫 `show_sync_dir`，`folder_used` 退而取登記檔的值，所以 `ping`、`status`、`export --target` 第一行都變了。SPEC 4.2 那句在 `--project` 段落，`main` 上的 `--target` 沒有這一行，抓第一行的腳本會壞。改回只在 `--project` 形式印。Ruling 10 補一句說明這個邊界。
  - [ ] **4. `tools/headless_watch.py` 呼叫已刪除的 `headless.point_sync_folder`。** 那是 WATCHER.md 第 8 節無頭看門人驗收的儀器，開完專案就炸。`tools/probe_watcher_ui.py` 已經改成 `settings.write(...)`，照抄。
  - [ ] **5.** `readMe.md` 升級段那句 `cds-sync-save-after-export`：內容正當，但階段 5 的 grep 驗收打了假勾。改寫成不含前綴（例如「the old save-after-export property」），讓驗收句成立。
  - [ ] **6.** `docs/WATCHER.md` 替身 UI 那張表仍列 `ask_yes_no_cancel`，`docs/SPEC.md` 6.1 那句「對話框只透過 `codesys_ui.ask_yes_no`、`ask_yes_no_cancel`、`system.ui.choose`」也是，兩處都改成只剩兩個。
  - [ ] **7.** `tools/perf_probe.py` 的量測表還列 `check_version_compatibility`，另一列的說明文字「IDE:is_debug — get_project_info() round trips」描述的是已經不存在的機制。刪那一列、改那句。
  - [ ] **8.** `tools/probe_imports.py` 的清單還有 `"cds.ide.config"`，模組已刪，儀器會報成 import 失敗。拿掉。
  - [ ] **9.** 說謊的測試註解：`tests/test_plc.py` 檔頭「project property cds-sync-plc」、`tests/test_headless.py` 的「The IDE side sets cds-sync-folder」、`tests/test_unhandled_objects.py` 的版本對話框註解。三處改成講現在的機制。假物件裡殘留的 `cds-sync-version`、`ask_yes_no_cancel` 留給 `HYGIENE_PLAN.md`，不用動。
  - [ ] **10.** `cdsint/headless.py` 的 `Headless.sync_dir()` docstring 說「printed as the run's first line, before the IDE has started」，跟 Ruling 10 和 `cdsint/report.py` 的說法相反。改成一致。
  - [ ] **11.** `engine/codesys_utils.py` `Logger._initialize` 那段「the NameError went into the bare except below」指的 except 已經被這個 diff 刪了，整段是 git log 的事。刪。
  - [ ] **12.**（順手）`engine/settings.py` 的 `_as_written` 自己判定「是不是相對路徑」，`cds/core/settings.py` 的 `folder` 又一份。工單第 4 節說判定那半要收進 `folder`，補上。
  - [ ] **13.**（順手）`engine/settings.py` 的 `choose_sync_folder`：「No project open!」分支從 `prepare_asking` 到不了；`_folder` 跑兩次讓 `ensure_git_configs` 做兩遍。收成一次。
  - [ ] **14.**（順手）`cds/ide/permit.py` 拒絕訊息前半用 Python repr 印清單、後半用 JSON。統一用 `json.dumps`。
  - [ ] **15.**（順手）`cdsint/flags.py` 的 `check()` docstring 整段是歷史，改成現在的 WHY 一句。
  - [ ] 驗收：`{"sync_folder": "./sync", "debgu": true}` 對 `build --project`、`discover --project`、`plc connect --project` 都 exit 1，訊息含 `debgu`，`denied` 是 null。
  - [ ] 驗收：`cdsint ping --target <你自己用 headless_watch 起的看門人>` 第一行是 `info: pong`，不是 `sync folder:`。
  - [ ] 驗收：`tools/headless_watch.py` 對副本起得來、`cdsint list` 看得到它、`stop` 得掉。
  - [ ] 驗收：階段 5 那條 grep 重跑為零；`grep -n "ask_yes_no_cancel" docs/WATCHER.md docs/SPEC.md tools/` 為零。
  - [ ] 驗收：Windows 與 WSL 測試綠；softplc 副本 export 的 hash 清單跟 `main` 的 diff 仍為零（監督者會重量）。

---

## 6. 回報格式

最後一則訊息要有：每段狀態一句話；commit 清單，每個 hash 配一句話；Windows 與 WSL 的測試數；階段 6 每一條的 exit code 與關鍵輸出；需要人的事，每件附一句為什麼只有人能做；沒做的事與原因；第 7 節新增的 Ruling。

---

## 7. 未決事項與裁決

實作時決定，決定了寫回：`Ruling: 決定 — 理由 — 錯了的代價`。

先列出來的三題，都照預設走：

1. `read` 對舊的 `cds-sync-` 鍵不特別說一句。`Ruling: 照預設，不特別說 — 它就是未知鍵，訊息裡有十一個鍵和各自的預設值，讀者對得上 — 錯了的代價是升級的人多花一分鐘查 readMe 的設定表。`
2. `resolve` 之後 `sync_folder` 沒設就是 dict 裡沒有這個鍵。`Ruling: 照預設，沒有這個鍵 — 跟「檔案裡有的才是決定過的」一致，呼叫端用 `"sync_folder" not in values` 判斷第一次執行 — 錯了的代價是呼叫端要多分辨 None 與空字串。`
3. 覆蓋值走 `command_args`。`Ruling: 照預設，走 `command_args` — 它已經是「旗標進本體」的那條路 — 錯了的代價是引擎多讀一個 caller_globals 的鍵。`

實作時新增的：

4. `Ruling: 階段 1 到 5 合成兩個 commit（程式一個、文件一個），不是每階段一個 — 把 `props.py` 改名會同時打斷十四個 import，中間任何一個切點測試都是紅的，而「一段做完、測試綠、commit」要求綠 — 錯了的代價是這兩個 commit 比較大，review 要一次看完整個搬遷。`
5. `Ruling: `silent.Outcome.ok()` 留著 — 工單第 4 節說它在正式碼裡只有 `_folder_follow_up` 在用，但 `tests/test_plc.py` 有十五處在用它，測試也是呼叫端 — 錯了的代價是多一個一行的方法。`
6. `Ruling: `codesys_ui.DirectoryChoiceForm` 與 `show_directory_choice_dialog` 留著 — 工單第 3 節現況 12 說它沒有呼叫端，這是錯的：`show_sync_folder_dialog` 就在呼叫它，那是第一次跑時「用瀏覽的還是自己打」那一問。跟著刪的是它的 `ask_yes_no_cancel` fallback，那個才真的沒有理由存在 — 錯了的代價是 codesys_ui 多七十行只有真人會看到的視窗程式碼。`
7. `Ruling: `--sync-dir` 由 IDE 側的 `run_commands` 分發到每一步的 args，不是 CLI 側 — 工單第 5 節階段 4 寫的是 CLI 側；兩邊都只有一個分發點，選 IDE 側是因為它就在跑命令的那個迴圈旁邊，`verify` 的四步不可能各自拿到不同的值 — 錯了的代價是 job 檔的 `sync_dir` 欄位既是引擎的輸入也是 report 的輸入，讀的人要看兩次才知道。`
8. `Ruling: argparse 關掉縮寫（`allow_abbrev=False`）— 不關的話 `--force` 會被當成 `--force-lock` 的縮寫收下，一個還在傳 `--force` 的舊腳本不會報錯，而是安靜地拿到「硬開別人開著的專案」；階段 4 的驗收要的「unrecognized arguments」也只有關掉才拿得到 — 錯了的代價是不能再用 `--proj` 這種簡寫。`
9. `Ruling: `show_sync_folder_dialog(system, initial)` 的第二個參數換成 `settings_path` — `initial` 在新流程裡永遠是空字串（沒有舊值可以帶），已經是死參數；換成設定檔路徑之後，視窗會告訴人「等一下寫進哪個檔」，替身 UI 的拒絕訊息也才點得出檔名，而那是階段 3 與階段 6 的驗收條件 — 錯了的代價是真人看到的視窗多一行字。`
10. `Ruling: 「這一趟用了哪個資料夾」那一行改成跑完之後從 report 印，不是跑之前從旗標印 — 不給 `--sync-dir` 的時候，IDE 讀完設定檔之前外面沒人知道答案；SPEC 4.2 要求印在第一行，而我們自己在那之前不印任何東西，所以仍然是第一行 — 錯了的代價是 `--sync-dir` 給了的時候，那一行從「開 IDE 之前」延到「跑完之後」才出現。`
11. `Ruling: hash 清單排除 `sync_cache.json` — 它記的是每個檔的 `disk_mtime`，兩趟之間必然不同，而 SPEC 4.5 已經把它列為本機狀態、gitignore 的東西 — 錯了的代價是快取格式如果壞掉，這個儀器抓不到。`
12. `Ruling: `is_debug()` 留著，改成回傳 `_logger.debug` — 工單說刪掉模組層級快取，但 `read_ide_attrs` 每個物件都問一次，每趟命令幾千次；`init_logging(base_dir, debug)` 本來就把這個值交給 logger 了，讓 `is_debug()` 讀它就是「一次命令讀一次、結果傳給需要的人」，沒有第二份快取 — 錯了的代價是忘記呼叫 `init_logging` 的路徑會拿到 False 而不是設定檔的值。`

### 階段 0 與階段 6 的兩個數字，跟工單寫的不一樣

13. `Ruling: 階段 0 的驗收「兩份清單各 229 行」改成「229 個物件」 — 229 是可匯出物件數，不是檔案數；softplc 匯出 229 個物件成 228 個 .st 加 1 個 .xml，再加 .gitignore、.gitattributes 就是 231 行，Shm 是 233 行 — 錯了的代價是照字面驗收的人會以為基線不對。`
14. `Ruling: 階段 6「discover 的 total、by_kind、unknown 前後相同」的比較對象改成「同一份全新副本、舊碼與新碼各跑一次」 — 我一開始拿一份已經跑過多趟命令的副本去比，數到 402/21，跟 WORKER_RULES 寫的 407/22 對不上；換成乾淨副本，新舊碼都是 407/22 — 錯了的代價是把下面第 15 條那個真實現象誤判成 walker 壞掉。`

### 一個量到的行為改變（不是 bug，是不遷移的代價）

15. **舊屬性關掉的設定會變回預設值，`softplc_refactor.project` 剛好踩到。**
    那個專案的 `cds-sync-save-after-export` 是 `False`，舊碼讀得到所以匯出完不存檔；
    新碼不讀舊屬性（決定表第 7 條），所以用預設值 `true`，匯出完存檔。
    在乾淨副本上量到的：舊碼匯出後 `.project` 一個位元組沒動，`discover` 是 407 節點 22 種 kind；
    新碼匯出後 `.project` 從 3808832 變成 3843088 位元組，`discover` 變成 402 節點 21 種 kind，
    少掉的正好是五個 `alarm_group`。在新碼的設定檔裡寫 `"save_after_export": false` 再跑一次，
    `.project` 沒動、`discover` 回到 407/22——所以少掉那五個節點是 IDE 自己存檔的行為，
    不是 cdsint 刪的，而且新舊碼在同一個設定值下完全一致。
    匯出的 `.st` 兩邊逐位元組相同（231 個檔的 SHA-256 清單 diff 為空）。
    這一條已經寫進 readMe 的升級段。

### 做的時候看到但不在範圍的，記給後面三張工單

- **`PLUMBING_PLAN.md`**：`cdsint/cli.py` 31 行 `from cdsint.exits import ...` 帶著
  `# noqa: E402,F401`，`EXIT_TARGET`、`EXIT_TIMEOUT`、`EXIT_HEADLESS` 三個名字沒有人用，
  只是為了 re-export。
- **`HYGIENE_PLAN.md`**：`engine/entry_export.py` 有二十一個沒用到的 import
  （`sys`、`codecs`、`json`、`IMPL_MARKER`、`FolderManager` 這一整批），`entry_import.py` 四個，
  `entry_build.py` 一個，`codesys_utils.py` 一個（`csv`）。這些在本工單之前就在了，
  pyflakes 對 `f3ffd97` 也是同一份清單。
- **`HYGIENE_PLAN.md`**：`engine/entry_compare.py` 有一個 `except Exception as e: pass`，
  `e` 綁了不用。
- **`ENGINE_PLAN.md`**：`engine/codesys_utils.py` 還有 26 個空白 `except:`，
  `codesys_ui.py` 2 個，`entry_build.py` 5 個（棘輪已經在本工單降到這三個數字）。
- **`PLUMBING_PLAN.md`**：`cdsint/report.py` 的 report 檔名只照專案名，所以同一個專案的兩趟
  `--project` 會互相覆蓋 stdout/stderr 檔。我要比對兩趟輸出的時候被這個絆了一次，
  只能重跑並自己給 `--report`。

---

## 8. 接手 prompt

你在 `C:\Users\qazsskevin\Documents\repo\cdsint-settings`，分支 `ticket/settings`。先讀 `docs/WORKER_RULES.md`、本工單第 0 到 4 節、`docs/SPEC.md` 的 D8、4.2、4.4、6.5、6.7、`PRINCIPLES.md`、`CLAUDE.md`。然後從第 5 節第一個沒打勾的項目開始做，階段照順序。一段做完、測試綠、commit；做完的項目打勾並 commit。「還需要人」的跳過並列進回報。決定了第 7 節的事就寫回。看到不在範圍的爛東西記進第 7 節末尾，不修。全部做完照第 6 節回報，停下來，不要 merge、不要 push。
