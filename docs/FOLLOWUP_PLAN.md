# 工單：基本開發後的收斂——刪掉沒人到得了的功能、補上掉了的入口與文件

> 建立日期 2026-09-06。本 repo `C:\Users\qazsskevin\Documents\repo\cdsint`，分支 `main`。
> 前一張工單是 `CDSINT_PLAN.md`：鐵律第 0 節、現況事實第 3 節、台架事實（階段 3 末尾）全部沿用，這裡不重抄。
> 依據是 `docs/history/GAPS_2026-09-06.md` 那份只讀審查，加上使用者 2026-09-06 逐題定案的決定（第 2 節）。
> 使用者不在也不會回答，卡住寫進回報。

---

## 0. 鐵律

`CDSINT_PLAN.md` 第 0 節全部適用：來源 repo 只讀、使用者的 IDE 與 junction 不碰、真專案只用副本（`%TEMP%\cdsint-work\` 底下）、無頭行程自己起自己關、push 由監督者做、臨時檔集中並清掉。台架帳密在 `%LOCALAPPDATA%\cdsint\bench.env`，只准載進 shell 環境變數，這一張工單不需要碰控制器。

---

## 1. 目標與範圍

把審查列出的缺口收掉，方向是**簡潔**：使用者不常用的功能只留 CLI 或直接刪，不加任何新的設定、旗標、對話框，除了第 2 節明列的那一列。每一項做完測試綠、commit；整張做完由監督者 push，GitHub 兩條 job 都綠才算過。

明確不做：
- 「選到別的專案的資料夾時擋下匯入」——使用者的流程就是同一份文字餵給 AX8 專案與 WSL 專案，物件 GUID 不同，這個守門會誤擋。引擎的裝置名稱重對應（k1.0.2）本來就是為這個流程設計的。
- 任何新的守門、旗標、選項。

---

## 2. 使用者定案的決定（2026-09-06）

| 決定 | 選擇 | 理由 |
|---|---|---|
| compare 的互動視窗、並排 diff 視窗、`.diff/` | 刪。CLI `compare` 保留 | 幾乎沒人用，匯出之後有 `git diff`；那六百多行現在沒有任何使用者到得了 |
| `Project_discover` | 變成 CLI 子命令 `discover`，兩種形式 | 它是「物件靜默不匯出」唯一的診斷路徑 |
| `Project_resources` | 刪 | 幾乎沒人用，檔案大小任何工具都看得到 |
| `Project_perf_probe` | 改名 `tools/perf_probe.py`，留在 `tools/`，Execute Script File 跑 | 維護者的儀器不是使用者的功能；`Project_` 前綴只留給選單裡的三支 stub |
| 同步資料夾改路徑 | Settings 對話框加一列加 Browse | 原本 `Project_directory` 有的功能，搬家時掉了 |
| 版本號 | pyproject 用 dynamic version 讀 `SCRIPT_VERSION`，readMe 不寫版本，tag 人打 | 沒有東西要同步就不會漂 |
| skill 發佈 | `npx skills add kevin00156/cdsint`，不另發套件 | 那個工具已經直接認得 `skills/cdsint/SKILL.md`；repo 正式發版時會轉公開 |
| `img/` | 刪 | readMe 一張都沒用 |

---

## 3. 接手前必須知道的現況事實

1. `engine/codesys_ui.py` 749 行：`show_settings_dialog`（265 行起）、`show_directory_choice_dialog`（665）、`show_sync_folder_dialog`（730）。compare 視窗的 Ctrl+Diff 存 `.diff/` 在 497 到 547 行，`show_compare_dialog` 在 584 行起。`engine/codesys_ui_diff.py` 518 行整支是並排 diff 視窗。
2. `engine/entry_compare.py` 394 行：133 到 143 行是開互動視窗的那條路，`perform_export`（212 行起）與 `perform_import` 只有從視窗按鈕到得了。`cds/ide/silent.py` 對 `show_compare_dialog` 回 `(None, [])`。`tests/test_dirty_files.py` 第 205 行附近在測「比對視窗按匯出」那條路。SPEC 6.1 有一條規則講這條路（「比對視窗按『匯出』不受髒檔保護」那條 Ruling 也在 `CDSINT_PLAN.md` 第 7 節）。`engine/codesys_utils.py` 產生的 `.gitignore` 內容寫了 `/.diff/`。
3. `cds/ide/entries.py` 第 37 行 `SCRIPTS` 表：export、import、compare、build、plc connect、plc download。`cdsint/flags.py` 定義子命令與旗標，`cds/ide/permit.py` 只管 `plc`。加 `discover` 照 compare 的樣子（唯讀、兩種形式、不需權限）。
4. `tools/Project_discover.py` 140 行、`tools/Project_resources.py` 286 行都少 `sys.path` 的 bootstrap（跟 `tools/perf_probe` 的 `_INSTALL_ROOT` 那三行比）。discover 的本體是走物件樹、`classify_object`、列未知 GUID、寫 `sync_debug.log`。
5. `engine/settings.py`：`SETTINGS` 表八個開關；`choose_sync_folder` 只在缺資料夾時被叫；`_as_written` 是相對路徑規則；`_prepare`、`_remember_who_and_what` 是設完之後的收尾。`cds/ide/config.py` 的 `_set` 對 `cds-sync-folder` 只寫屬性不走那兩個收尾。
6. `pyproject.toml` 第 7 行 `version = "0.0.1"` 手抄；`tests/test_version.py` 比對它跟 `engine/codesys_constants.py` 的 `SCRIPT_VERSION`；readMe 第 17 行附近手寫「Version 0.0.1」。setuptools 支援 `[project] dynamic = ["version"]` 加 `[tool.setuptools.dynamic] version = {attr = "engine.codesys_constants.SCRIPT_VERSION"}`；`engine/codesys_constants.py` 在 CPython 下 import 得起來（測試已經在 import 它）。
7. 文件互相打架的三處：`docs/SPEC.md` 第 7 節矩陣「PLC connect、download 全部未驗」對上 6.6「2026-09-06 驗過」；矩陣「無頭 boot app 產出」那列量的東西已經不存在；`readMe.md` 開頭說 PLC 命令還沒做而下面整節在教。
8. `docs/AI_WORKFLOW.md` 第 365 到 367 行連到 readMe 兩個不存在的錨點（`#-sync-pragmas-in-st-files`、`#-type-profilesprofilesdefaultjson`）。來源 repo 的 readMe 332 到 357 行有 pragma、profile、call_tree 三節可以搬。
9. `npx skills add kevin00156/cdsint --list` 在這台已經列得出 `cdsint` 這個 skill（node 22、skills CLI 1.5.23）。
10. 這台的 Linux 迴圈：`wsl -d Ubuntu-22.04 -- bash -lc 'cd /mnt/c/Users/qazsskevin/Documents/repo/cdsint && python3 -m pytest tests -q'`（Python 3.10，pytest 6.2.5）。

---

## 4. 設計

- `discover` 的本體是 `engine/entry_discover.py`，`main()` 回 `entry.result(ok, summary, **data)`，`data` 至少有 `total`、`unknown`（未知 GUID 的物件清單，每筆有名字與 GUID）、`by_kind`（每種 kind 幾個）。`ok` 在有未知 GUID 時是 False（D13：認不得的物件要以名字報出來，而且呼叫端不用先讀 data 才知道要讀 data）。`sync_debug.log` 照舊只在 debug 開著時寫。
- Settings 對話框的資料夾列：文字框顯示現值，Browse 按鈕開 `show_sync_folder_dialog`，按 OK 時走 `_as_written`；值有變才 `set_project_prop` 並跑 `_prepare` 與 `_remember_who_and_what`。不加第二個對話框。
- 刪 compare 視窗之後，`entry_compare.py` 只剩「算差異、印報告、回 result」；`perform_export`、`perform_import` 若沒有別的呼叫端就刪。
- PRINCIPLES.md 加一條：`Project_` 前綴只給 Scripts 選單裡的入口（三支 stub）；`tools/` 裡的東西不用它。

---

## 5. 分階段與驗收

- [x] **A. 刪掉沒人到得了的**
  - [x] 刪 `engine/codesys_ui_diff.py`、`show_compare_dialog`、Ctrl+Diff 與 `.diff/` 那段、`entry_compare.py` 的視窗路徑與只從視窗到得了的函式、對應測試、`.gitignore` 產生器裡的 `/.diff/`。SPEC 6.1 那條規則刪，`CDSINT_PLAN.md` 第 7 節那條 Ruling 加一句「已刪」。
  - [x] 刪 `tools/Project_resources.py`、`img/`；SPEC 10.1 跟著改。
  - [x] 驗收：`grep -rn "show_compare_dialog\|codesys_ui_diff\|\.diff" engine/ cds/ cdsint/ tests/` 為零（`git diff` 這種字串不算）；測試綠。

- [x] **B. `discover` 進 CLI**
  - [x] `engine/entry_discover.py` 照第 4 節；`cds/ide/entries.py` 加一列；`cdsint/flags.py` 加子命令，兩種形式；`tools/Project_discover.py` 刪。
  - [x] 驗收：測試涵蓋「有未知 GUID 時 `ok` False 且名字與 GUID 在 `data.unknown`」「全部認得時 `ok` True」。
  - [x] 驗收（監督者會重現）：`cdsint discover --project <softplc 副本> --install 3.5.21.40 --sync-dir S --json` 回 `total` 229、`unknown` 空、exit 0。——**跑過，74.9 秒 exit 0**，`ok` true、`unknown` 空、`failed_objects` 空、22 種 kind。`total` 是 **407 不是 229**：229 是 export 寫出的檔案數（同一份副本、空同步資料夾跑 `compare --project` 回 `new_in_ide=229`），407 是樹上全部節點。理由與為什麼不改成 229，見第 7 節那條 Ruling。
  - [x] readMe 與 `docs/AI_WORKFLOW.md`、`skills/cdsint/SKILL.md`：`failed_objects` 出現時下一步是 `cdsint discover`，未知 GUID 加進 `profiles/default.json` 的 `guid_aliases` 再跑。

- [x] **C. perf_probe 改名**
  - [x] `tools/Project_perf_probe.py` → `tools/perf_probe.py`，檔頭寫 Execute Script File 的用法與參數；PRINCIPLES 加 `Project_` 前綴那一條。
  - [x] 驗收：`ls tools/ | grep Project_` 為空。

- [x] **D. Settings 加同步資料夾列**
  - [x] 照第 4 節。`cds/ide/config.py` 的 `_set` 對 `cds-sync-folder` 也跑 `_prepare` 與 `_remember_who_and_what`，兩條路寫出來的屬性一樣。
  - [x] 驗收：測試用假 IDE 物件涵蓋「改了資料夾就寫三個屬性並建目錄」「沒改就什麼都不寫」；`config set cds-sync-folder` 之後 `cds-sync-pc`、`cds-sync-version` 都有值。
  - [ ] 驗收（還需要人）：在有畫面的 IDE 跑 `Project_watch`，按狀態視窗的 Settings，看得到資料夾那列，Browse 選一個資料夾後 Properties 裡的值變了。

- [x] **E. 版本單一來源**
  - [x] pyproject 改 dynamic version 讀 `SCRIPT_VERSION`；刪 `tests/test_version.py`；readMe 拿掉手寫的版本號。
  - [x] 驗收：`pip install -e .` 之後 `pip show cdsint` 的 Version 等於 `SCRIPT_VERSION`；`grep -n "0\.0\.1" readMe.md pyproject.toml` 為零。——兩條都過。兩邊都是 0.0.1 證明不了什麼，所以另外把 `SCRIPT_VERSION` 暫時改成 `0.9.99` 重裝一次，`pip show` 跟著變成 0.9.99，再改回來重裝確認回到 0.0.1。

- [ ] **F. 文件**
  - [ ] readMe：Install 寫成兩步（`pip install -e .` 裝命令、`npx skills add kevin00156/cdsint` 裝 skill）；加 pragma 與 `profiles/default.json` 兩節（從來源 readMe 332 到 346 行搬，改名字）；加 `tools/` 一節（perf_probe、call_tree 各一行用法）；加「從 cds-text-sync 升級」一段（拆舊 junction、停舊看門人、實例目錄換了、toolbar 按鈕若失效重加）；Layout 列 `skills/`；開頭那句「PLC 命令還沒做」改成現況。
  - [ ] `docs/AI_WORKFLOW.md` 兩個死錨點改指新的節。
  - [ ] SPEC：第 7 節矩陣 PLC 那列改成 6.6 的現況、「無頭 boot app 產出」那列刪；10.1 對照表跟著 A、B、C 改。
  - [ ] 驗收：`grep -rn "#-sync-pragmas\|#-type-profiles" docs/ skills/` 為零；readMe 裡每個 `[...](#...)` 錨點都存在（寫一個小腳本檢查）。

- [ ] **G. 收尾**
  - [ ] `python -m pytest tests -q` 綠，WSL 那條也綠；commit；照第 6 節回報，停下來等監督者 push 並看 GitHub 兩條 job。

---

## 6. 回報格式

同 `CDSINT_PLAN.md` 第 6 節：狀態一句話、commit 清單、測試數、數據、需要人的事、沒做的事、裁決。

---

## 7. 未決事項與裁決

實作時決定，決定了寫回：`Ruling: 決定 — 理由 — 錯了的代價`。

本工單裁的：

- Ruling: `discover` 的 `data` 是 `total`（樹上全部節點）、`by_kind`（kind → 幾個，dict）、`unknown`（`[{"name", "guid"}]`）、`failed_objects`（跟其他命令同名同形） — `unknown` 用結構化的兩個欄位而不是一句字串，因為讀它的人下一步是把那個 GUID 貼進 `profiles/default.json`，agent 不該去剖析人話；`by_kind` 用 dict 因為 `--json` 那邊要的是可查表的東西 — 錯了的代價是 `cdsint/report.py` 的 `_show_data` 多了一段處理 dict 與 dict 清單的分支。
- Ruling: `total` 數的是樹上每一個節點，不是 export 會寫出去的那些 — 工單驗收寫「回 `total` 229」，實際量到 407；229 是 export 寫出的檔案數（空同步資料夾跑 `compare --project` 的 `new_in_ide` 就是 229），兩個數字量的是不同的東西。export 故意跳過的那些（property accessor 60、task 3、device 44、device_module 38，以及被單體容器擁有的子物件）正是「物件靜默消失」的藏身處，不數它們就等於把答案拿掉。要讓兩個數字對齊只有兩條路，都比數字不好看更糟：對每個物件呼叫 `classify_object` 會把 survey 已經讀過的 `.type` 與 `.parent` 再讀一次（PRINCIPLES 3），自己重寫一份跳過規則則是同一套規則的第二份拷貝（PRINCIPLES 7）— 錯了的代價是監督者重現驗收時會看到 407 而不是 229，所以這件事寫進了 `entry_discover.py` 的檔頭與 readMe。
- Ruling: `entry_compare.py` 留著當一支獨立模組，不並進 `codesys_compare_engine` — 它剩下的 181 行是 `entries.SCRIPTS` 裡 `compare` 那一列的本體，而 SPEC D12 要求每一個命令名字對到一支 `entry_*`；`codesys_compare_engine` 是算差異的引擎，把「載設定、印報告、回 result」塞進去就是兩個職責掉進同一支檔（PRINCIPLES 1）— 錯了的代價是多一支小檔案。
- Ruling: `config set cds-sync-folder=X` 的收尾走 `cds/ide/entries.py` 去按 `engine/settings.py` 的 `folder_was_set`，不在 `cds/ide/config.py` 裡自己寫一份 — `_prepare`（建目錄、寫 git 規則、數 application）與 `_remember_who_and_what`（寫 `cds-sync-pc`、`cds-sync-version`）都是引擎的事，而 `cds/ide` 不准 import 引擎（SPEC D12、PRINCIPLES 4）；entries.py 本來就有「照路徑與入口名字按一支引擎本體」這個門，走它就沒有第二份跳過規則，也不用把 `SCRIPT_VERSION` 搬家 — 錯了的代價是 `config set cds-sync-folder` 從此需要 `engine/codesys_ui` 載得起來（`silent.run` 會去接管它的對話框），而在真 IDE 裡那本來就是每個命令的前提。
- Ruling: `config set` 寫進去的值一字不改，不套 `_as_written` — 對話框會把瀏覽出來的絕對路徑改寫成 `./sync`，因為那個路徑不是人打的；`config set KEY=VALUE` 是人打的，而一個會偷改你給的值的 CLI 會讓 `config get` 回傳跟你設的不一樣的東西 — 錯了的代價是同一個資料夾從兩條路設進去，屬性值一個是絕對路徑一個是 `./sync`，兩者 `load_base_dir` 都解得開，差別只在專案搬家時相對的那個還能用。

監督者已裁的：

- Ruling: 不做「別的專案的資料夾」守門 — 使用者的 AX8 加 WSL 流程就是同一份文字餵兩個專案，引擎的裝置重對應為此而存在 — 錯了的代價是指錯資料夾時只有 `-y` 前的計畫預覽與空資料夾拒絕在擋，那兩個對這種錯已經夠。
- Ruling: `Project_` 前綴只給選單入口 — 使用者說 perf_probe 不該長得像使用者會按的東西，這句話推廣成規則就是這條 — 錯了的代價是無。

---

## 8. 接手 prompt

你在 `C:\Users\qazsskevin\Documents\repo\cdsint`，分支 `main`。先讀本工單全文、`CDSINT_PLAN.md` 第 0 節與第 3 節、`docs/history/GAPS_2026-09-06.md`、`CLAUDE.md`、`PRINCIPLES.md`。然後從第 5 節第一個沒打勾的項目開始做，A 到 G 照順序。一段做完、測試綠、commit（英文一句話說為什麼）。做完的項目打勾並 commit。「還需要人」的跳過。決定了第 7 節的事就寫回。全部做完照第 6 節回報，停下來，不要 push。
