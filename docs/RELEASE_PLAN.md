# 工單：發佈前把審查找到的壞味道修掉

> 建立日期 2026-09-15。分支 `release-audit`，worktree 路徑
> `C:\Users\qazsskevin\Documents\repo\cdsint-release-audit`。
> 使用者不在也不會回答，卡住寫進最後回報。

## 0. 鐵律

- 使用者不在、不會回答。卡住就把原因寫進最後回報，階段之間直接進下一段，不問「要不要往下做」。
- 只碰自己開的資源：使用者開著的程式、專案、視窗一律不動；要關的程序只關自己記下 pid 的；程序用 `Stop-Process -Id`。
- 真實資料只用副本；使用者 git 管理的資料夾一個位元組都不寫。
- 憑證由使用者自己填在本機檔案；遇到要憑證的步驟中止並記錄，繼續其他工作。
- 一段做完、測試綠、commit，再進下一段。
- 對外動作（push、merge、發訊息）事先在 settings 加允許規則，或明寫「由人做」。被分類器擋就升級給人。
- 儀器拿不到前景就改用非 UI 驗證並註明；桌面上無關的視窗留在原處。
- 臨時檔集中在一個前綴底下，做完清掉。

這張工單專屬的：

- 只在 `C:\Users\qazsskevin\Documents\repo\cdsint-release-audit` 這個 worktree 裡工作。主工作樹 `C:\Users\qazsskevin\Documents\repo\cdsint` 有使用者未 commit 的改動，一個位元組都不碰。
- 不 push。分支留在本機，合併由人做。
- 這張工單不需要開 IDE。所有驗收都在 `python -m pytest -q` 裡。不要啟動或關閉任何 CODESYS、DIADesigner、PLC Designer 程序，不要對真實專案跑 `cdsint verify --project`。
- 磁碟上的 `.st` 格式與 pragma 名稱是使用者的資料，不准改（CLAUDE.md）。這張工單沒有任何一項會碰到它們；碰到了就是做錯了。
- `engine/`、`cds/ide/`、`cds/core/`、`stub/` 裡的程式碼要同時在 IronPython 2.7 和 CPython 3 上跑（PRINCIPLES 8）：沒有型別註解、沒有 f-string、沒有 `pathlib`。`tests/test_print_function.py` 只守 `__future__` 那一行，其餘靠你自己。
- commit 訊息跟 `git log` 既有風格一致：一句英文說清楚為什麼，沒有 `feat:` 之類的前綴。

## 1. 目標與範圍

發佈前審查找到的問題分三層。這張工單三層都做，順序固定：先做會吃掉使用者資料的，再做會主動騙人的，最後做讓這些問題不再長回來的。

**做：**

1. `engine/backup.py` 重寫：安全備份失敗要能擋下匯入；存檔失敗要能讓匯入和匯出回報失敗。
2. `tools/perf_probe.py` 改用 `entry.borrowed()`，探針表裡解析不到的名字要大聲報出來。
3. 三處 `hasattr(o, p) and o.p` 換成 `ide_flag()`，其中一處在死碼裡，連死碼一起刪。
4. 四處會主動騙人的 docstring 和 SPEC 條文改正。
5. 規則 2（尺寸上限）做成棘輪測試；`PRINCIPLES.md` 的分層判斷補上「拆檔」的情況；`calculate_hash` 補一個帶中文的測試。

**明確不做：**

- 不重寫 `engine/codesys_managers.py`、`codesys_utils.py`、`codesys_compare_engine.py` 這三個移入層的大檔。它們的問題已經有 `tests/test_bare_excepts.py` 的棘輪在記。
- 不處理審查報告裡「次要但真實」那一列的其他項目（`entry_export.py:92` 孤兒檔刪除失敗、`plc_trip.py:271` 下載沒記錄、`show_toast` 沒有呼叫端、`settings.load` 沒有呼叫端、`RESERVED_FILES` 的幽靈項目）。那些寫成 backlog 是下一張工單的事。
- 不動 `.st` 格式、pragma 名稱、`profiles/default.json`。
- 不改 CI 的 Python 版本矩陣、不改 `pyproject.toml` 的 packages 清單。那是發佈流程的決定，由人做。

## 2. 已定案的決策

| 決策 | 選擇 | 理由 |
|---|---|---|
| `create_safety_backup` 失敗時怎麼告訴呼叫端 | 回傳 `(filename, error)`，恰好一個是 `None` | 跟 `entry_build.choose_application` 的 `(app, refusal)` 和 `settings.prepare` 的 `(values, base_dir, error)` 同一個形狀；repo 裡沒有用例外傳結果的先例 |
| 備份失敗之後匯入要不要繼續 | 不繼續。`entry_import` 回 `entry.result(False, error)` | 備份的用途就是在破壞性匯入前留一手；留不了就不能動手（PRINCIPLES 6） |
| `finalize_sync_operation` 存檔失敗時匯出要不要也算失敗 | 要。匯入和匯出都回 `ok=False`，summary 寫存檔為什麼失敗 | 使用者開了 `save_after_export` 就是要它存；沒存卻回 ok 是 PRINCIPLES 6 說的「換頂帽子的靜默跳過」。匯出的檔案本身沒壞，summary 要講清楚這一點 |
| 存檔和複製的關係 | 拆成兩個函式：`save_project` 一律先跑（只要 `save_after_op` 或 `backup_binary` 任一開著），`copy_project` 在 `backup_binary` 開著時跟著跑 | 原本用 `elif` 是為了不存兩次；拆開之後存一次、複製一次，兩件事各自能失敗、各自能報 |
| `cleanup_old_backups` 刪不掉舊備份要不要報失敗 | 不報。narrow 成 `except OSError`，log 之後繼續 | 舊備份刪不掉不危及任何東西；但 `except Exception` 會把程式錯誤跟磁碟錯誤混在一起，所以縮小 |
| `find_object_by_name` 的 `parent_name` 分支 | 整段刪掉，連參數一起刪。`tests/test_bare_excepts.py` 的 `ALLOWED["engine/codesys_utils.py"]` 從 11 降到 10 | 唯一呼叫端 `codesys_compare_engine.py:669` 只傳兩個參數，那個分支永遠進不去；在死碼裡把 `hasattr` 換成 `ide_flag` 是自欺 |
| 探針表裡解析不到的名字怎麼處理 | `install_probes` 把解析不到的名字逐一印出來然後 `return` 不裝任何探針 | 一個少了三列的效能報告比沒有報告更會誤導人；靜默縮水正是 PRINCIPLES 6 禁止的 |
| 從移入層的檔案切出來的新檔案算哪一層 | 切出來的函式維持移入層，直到有人重寫；新加的函式算嚴格層。切檔的 commit 訊息要說「這是搬運」 | 規則 2 要求超過上限的檔案先拆再改；如果拆等於重寫，沒人會拆。`git log --follow` 追不到內容搬家，所以規則要用文字補上 |
| 尺寸棘輪測試的形狀 | 跟 `tests/test_bare_excepts.py` 同一個形狀：一張 `ALLOWED` 表記下現況，只准降不准升；不在表上的檔案和函式必須在上限內 | 那個形狀已經在 repo 裡證明過自己：數字是紀錄，不是目標；降了就要改表，改表就進 commit |
| 尺寸棘輪的上限用哪個數字 | 硬上限：檔案 400 行、函式 60 行。軟上限不進測試 | 軟上限是給人看的提醒；測試只擋規則 2 說「hard means」的那兩句 |

## 3. 接手前必須知道的現況事實

以下全部在 `4b4ad14`（`release-audit` 分支的起點）上查過。行號會隨你的改動漂移，改完以名字為準。

**活著的實作在哪。**

- 備份：`engine/backup.py`，192 行，四個函式：`cleanup_old_backups`（:25）、`backup_project_binary`（:78，79 行，超過 60 行硬上限）、`finalize_sync_operation`（:159）、`create_safety_backup`（:186）。從 `engine/codesys_utils.py` 在 `f99a91d` 整段切出來，內容沒重寫。沒有 `tests/test_backup.py`。
- 備份的呼叫端：`engine/entry_import.py:197`（`create_safety_backup`）與 `:209`（`finalize_sync_operation`）；`engine/entry_export.py` 也呼叫 `finalize_sync_operation`（`git grep finalize_sync_operation` 找）。
- 探針：`tools/perf_probe.py`，`_FUNCTIONS` 表在 :177-239，`methods` 表在 :262-283，`install_probes` 在 :251，壞掉的呼叫在 :436。
- `ide_flag`：`engine/codesys_utils.py:111`，簽名 `ide_flag(obj, name)`，回 `bool`。`tests/test_ide_round_trips.py` 已經釘住它的語意（`ExplodingFlag`、`test_raising_property_is_false_not_an_error`）。
- `entry.borrowed`：`engine/entry.py:49`，簽名 `borrowed(caller_globals, name)`，找不到回 `None`。

**現在的 bug，逐條。**

1. `engine/backup.py:97-156`：`backup_project_binary` 整個身體包在 `try/except Exception: return None` 裡。`:101` 和 `:115` 另外有兩個 `return None`（沒有專案、專案沒存過檔）。三種意思塌成一個 `None`。`create_safety_backup:186` 在 `safety_backup` 關著或沒東西匯入時也回 `None`。
2. `engine/entry_import.py:197-201`：拿到 `backup_filename` 後匯入直接跑；`backup_filename` 只在 `:223` 和 `:246` 用來決定印不印「Backup created」。
3. `engine/backup.py:169-183`：`finalize_sync_operation` 用 `if backup_binary ... elif save_after_op ...`，真正的 `projects_obj.primary.save()` 在 `elif` 分支。`backup_binary` 開著時存檔只發生在 `backup_project_binary:105`，那行的例外被 `:107` 接走後繼續複製舊的 `.project`。函式沒有回傳值。
4. `engine/backup.py:174`：這個 `except Exception` 接不到 `backup_project_binary` 丟出的任何東西，因為那個函式自己全包了。死的。
5. `tools/perf_probe.py:436`：`utils.resolve_projects(None, globals())`。`resolve_projects` 全 repo 沒有定義，在 `docs/history/ENGINE_PLAN.md:197` 被刻意刪掉，驗收只 grep 了 `engine/`。`:236` 的探針表也還有 `("resolve_projects", "setup:resolve_projects")` 這一列。
6. `tools/perf_probe.py:278-279`：`ConfigManager` 的 `update` 和 `create` 兩列 patch 不到東西。`ConfigManager`（`engine/codesys_managers.py:1372`）只覆寫 `export`；`_patch_method` 用 `cls.__dict__.get`，看不到繼承來的方法，回 0，沒人注意。
7. `tools/perf_probe.py:139-140` 與 `:161-168`：`_patch_function` 和 `_patch_method` 找不到目標時回 0，`install_probes` 只加總，所以少幾列沒人知道。
8. `engine/codesys_managers.py:430` 與 `:442`：`hasattr(obj, "has_textual_declaration") and obj.has_textual_declaration`、`hasattr(obj, "has_textual_implementation") and obj.has_textual_implementation`。Python 2 的 `hasattr` 吞所有例外，Python 3 只吞 `AttributeError`，所以同一個會丟例外的屬性在兩個 runtime 上行為不同。`ide_flag` 就是為這件事寫的。先確認 `codesys_managers.py:16` 那行 `from engine.codesys_utils import (...)` 有沒有 `ide_flag`，沒有就加。
9. `engine/codesys_utils.py:981-993`：`find_object_by_name(name, name_map, parent_name=None)` 的 `if parent_name:` 分支。唯一呼叫端 `engine/codesys_compare_engine.py:669` 是 `find_object_by_name(parent_name, name_map)`，把區域變數 `parent_name` 傳給第一個參數 `name`，第三個參數沒人傳。分支裡有一個裸 `except:`（:988），算在 `tests/test_bare_excepts.py` 的 `ALLOWED["engine/codesys_utils.py"] = 11` 裡。
10. `engine/entry.py:7`：docstring 說 bodies「pass `globals()` to resolve_projects()」。那個函式已經不存在。
11. `engine/entry_build.py:5`：模組 docstring 說「Compiles the active application」；`:288` `build_project` 的 docstring 說「Build the active application」。程式碼走 `choose_application()`（:115），認 `--app`、單一 application 直接用、多個就用 `system.ui.choose` 問。`applications()` 的 docstring（:102-107）自己寫著建置 active application 正是被修掉的 bug。
12. `cds/ide/silent.py:203-205`：說「its three dialog functions can be swapped」；`_ui_patches`（:235-241）回兩個：`ask_yes_no`、`show_sync_folder_dialog`。`:16-21` 的模組 docstring 說「Two things have to be swapped」但表格只列 `system` 和 `codesys_ui.ask_yes_no`，漏了 `show_sync_folder_dialog`。`tests/test_layering.py:20` 也說「three dialog functions」。`docs/SPEC.md` D12 那段說「三個對話框函式」。第三個是 `ask_yes_no_cancel`，`tests/test_silent.py:437` 有測試斷言它已經不在。
13. `docs/SPEC.md:309`：6.1 說「`test_every_yes_no_dialog_has_an_answer` 會擋沒登記的」。那條測試不存在。實際在跑的是 `tests/test_silent.py:433` 的 `test_every_shared_title_has_an_answer_and_no_answer_is_stale`。
14. `engine/codesys_utils.py:196` `calculate_hash`：`git grep calculate_hash -- tests/` 是空的，沒有任何直接測試。它是 `codesys_compare_engine.py:135-136` 判斷檔案有沒有變的依據。
15. 尺寸現況（規則 2 沒有測試在守）：超過 400 行硬上限的檔案有 `engine/codesys_managers.py`（1383）、`engine/codesys_utils.py`（1115）、`engine/codesys_compare_engine.py`（1083）、`tools/perf_probe.py`（511）、`tools/call_tree_resolve.py`（438）。超過 60 行硬上限的函式有 19 個，其中嚴格層只有 `backup_project_binary` 一個；其餘在移入層。完整清單用 `ast` 掃一次就有，不要抄這裡的數字進測試，要從程式碼算。

**會擋你的檢查。**

- `tests/test_bare_excepts.py`：`ALLOWED` 表兩個方向都會 fail。刪了裸 `except:` 就要在同一個 commit 降數字。
- `tests/test_print_function.py`：`engine/`、`cds/ide/`、`cds/core/`、`stub/`、`tools/` 每個 `.py` 都要有 `from __future__ import print_function`，包括新檔。
- `tests/test_layering.py`：`engine/` 不准 import `cds/ide`；`cds/core` 不准 import `system`、`projects`、`online`、`clr`。
- `tests/test_single_threaded_ide_side.py`：`engine/`、`cds/ide/`、`stub/` 不准 `sleep`、執行緒。
- `tests/test_names_resolve.py`：pyflakes。抓沒定義的名字，不抓模組上不存在的屬性——這正是 `resolve_projects` 沒被抓到的原因。
- `tests/test_doc_links.py`：`docs/SPEC.md`、`PRINCIPLES.md` 等文件裡的相對連結和錨點都要存在。改標題就要查有沒有人連過來。
- CHANGELOG 的 `### Unreleased` 段落是這一版的紀錄。每個階段結束加一條，風格跟現有條目一致：粗體一句話講改了什麼，接著講為什麼。

**環境。**

- 主機 Python 是 3.14，CI 是 3.12。`python -m pytest -q` 在 `4b4ad14` 上是 1306 passed。
- 沒有 IronPython 可跑。PRINCIPLES 8 的相容性靠讀碼守。

## 4. 設計

### `engine/backup.py`

五個函式，每個一句話：

| 函式 | 職責 | 回傳 |
|---|---|---|
| `target_name(project_path, backup_name, timestamped, now)` | 算出這次備份的檔名。純函式，`now` 是 `time.struct_time` 或同等物，由呼叫端傳進來 | 檔名字串 |
| `save_project(projects_obj)` | 把開著的專案存檔 | `None` 或錯誤字串 |
| `copy_project(project_path, export_dir, file_name)` | 把 `.project` 二進位檔複製到 `<export_dir>/.project/<file_name>`，資料夾不在就建 | `None` 或錯誤字串 |
| `cleanup_old_backups(project_folder, retention_count)` | 刪掉超過保留數的時間戳備份 | 無 |
| `create_safety_backup(base_dir, projects_obj, items_to_import, values)` | 匯入前的安全備份：設定關著或沒東西要匯入就不做 | `(filename, error)`，恰好一個是 `None`；兩個都是 `None` 表示這次不需要備份 |
| `finalize_sync_operation(base_dir, projects_obj, values, is_import)` | 同步結束：照設定存檔、複製 | `None` 或錯誤字串 |

`backup_project_binary` 這個名字消失。它現在做的事拆進 `save_project`、`copy_project`、`target_name`；「沒有專案」「專案沒存過檔」這兩個提早離開的情況變成 `create_safety_backup` 和 `finalize_sync_operation` 各自檢查一次並回錯誤字串，因為對它們來說那是失敗，不是「跳過」。

`import time` 和 `import re` 移到檔案頂端。

每個函式在 60 行以內；整個檔案在 400 行以內。裡面不留任何 `except Exception`——存檔和複製各自接自己預期的例外（`.NET` 呼叫用 `except Exception` 是可以的，但要在最小的範圍內，而且結果一定要變成回傳的錯誤字串）。

### `engine/entry_import.py` 與 `engine/entry_export.py`

```python
backup_filename, error = create_safety_backup(...)
if error:
    return entry.result(False, "Safety backup failed, nothing was imported: " + error)
```

```python
error = finalize_sync_operation(...)
if error:
    return entry.result(False, summary + " -- but the project was not saved: " + error)
```

匯出那邊 summary 要講清楚檔案已經寫到磁碟、只有 IDE 專案沒存。這兩個檔案是移入層，改動只限這幾行；函式不能變長超過原本。

### `tools/perf_probe.py`

- `:436` 改成 `projects_obj = entry.borrowed(globals(), "projects")`；確認檔案頂端有辦法拿到 `engine.entry`（看 `_root.py` 和現有的 `__import__` 寫法，跟著做）。
- `_FUNCTIONS` 刪 `resolve_projects` 那列；`methods` 刪 `ConfigManager` 的 `update` 和 `create` 兩列。
- `install_probes`：`_patch_function` 和 `_patch_method` 回 0 的那些名字收集起來；有任何一個就印出「probe table names nothing in the engine: ...」然後 `return` 不裝探針。這是唯一新增的行為。

### `engine/codesys_managers.py`、`engine/codesys_utils.py`

- `:430`、`:442` 的兩個 `hasattr(obj, X) and obj.X` 換成 `ide_flag(obj, X)`。
- `find_object_by_name` 刪 `parent_name` 參數和 `:981-991` 那段；保留 `return found[0]`，並把它上面那句「Return first match ONLY if no parent filter was requested」的註解改成講真話。函式 docstring 裡關於 strict matching 的句子一起刪。

### 文件與 docstring

- `engine/entry.py:7`：那句改成講 `borrowed()`。
- `engine/entry_build.py:5` 與 `:288`：改成「Build the application named by --app, the only one, or the one the user picks」這個意思。
- `cds/ide/silent.py:16-21` 表格補 `show_sync_folder_dialog`；`:203-205` 的「three」改「two」。
- `tests/test_layering.py:20`：「three」改「two」。
- `docs/SPEC.md` D12：「三個對話框函式」改「兩個」。
- `docs/SPEC.md:309`：測試名字改成 `test_every_shared_title_has_an_answer_and_no_answer_is_stale`。

### `tests/test_size_limits.py`（新檔）

跟 `tests/test_bare_excepts.py` 同一個骨架：`SCANNED` 五個目錄，`ast` 解析，兩張 `ALLOWED` 表。

- `ALLOWED_FILE_LINES = {"engine/codesys_managers.py": <現在的行數>, ...}`：只列超過 400 行的檔案。測試：不在表上的檔案必須 ≤ 400；在表上的檔案不准超過表上的數字，低於就要求降表。
- `ALLOWED_FUNCTION_LINES = {"engine/codesys_managers.py": {"classify_object": <行數>, ...}, ...}`：只列超過 60 行的函式。同樣的雙向規則。
- 函式行數的算法：`node.end_lineno - node.lineno + 1`，decorator 不算。寫在測試的 docstring 裡。
- docstring 要講清楚：這是規則 2 的棘輪，表上的數字是現況紀錄不是目標，改短了就要降表；跟 `test_bare_excepts.py` 一樣，這張表是唯一的計數，其他地方不抄數字。
- 表裡的數字從程式碼算出來填，不從本工單抄。填完跑測試必須綠。

### `PRINCIPLES.md`

「Two tiers」那段補一句：從移入層檔案切出來的新檔，切出來的函式維持移入層直到重寫，切檔的 commit 訊息要說明；新加進去的函式算嚴格層。規則 2 那段補一句：`tests/test_size_limits.py` 是硬上限的棘輪，`ALLOWED` 表是唯一的計數。

### `tests/test_hash.py`（新檔）或併進既有測試

`calculate_hash(u"中文註解")` 回 8 位大寫十六進位，值等於 `"%08X" % (zlib.crc32(u"中文註解".encode("utf-8")) & 0xFFFFFFFF)`；`calculate_hash(b"...")` 同值；`calculate_hash(None)` 回 `""`。docstring 說明這條測試只證明 CPython 那半邊；IronPython 上 `str` 與 `unicode` 是同一個型別，所以 `isinstance(content, str)` 也會為真，走同一條路。

## 5. 分階段與驗收

- [x] **階段 1：`engine/backup.py` 重寫，備份失敗擋下匯入、存檔失敗回報失敗**
  - [x] `tests/test_backup.py` 新增，用 `tests/fakes.py` 的假物件，先寫測試再改實作：
    - 複製失敗（`shutil.copy2` 丟 `OSError`）時 `create_safety_backup` 回 `(None, error)` 且 `error` 含原因
    - `safety_backup` 關著時回 `(None, None)`
    - 專案沒有 `path` 時回 `(None, error)`
    - `save()` 丟例外時 `finalize_sync_operation` 回錯誤字串，且不複製
    - `backup_binary` 開著時 `save()` 恰好被呼叫一次，然後 `copy_project` 被呼叫
    - `save_after_import` 開著、`backup_binary` 關著時 `save()` 被呼叫一次，不複製
    - `target_name` 三種情況：時間戳、自訂名（有無 `.project` 副檔名）、專案原名
  - [x] `engine/backup.py` 照第 4 節重寫
  - [x] `engine/entry_import.py` 在備份失敗時回 `entry.result(False, ...)`，不進 `perform_import_items`；`finalize_sync_operation` 有錯誤時回 `entry.result(False, ...)`
  - [x] `engine/entry_export.py` 在 `finalize_sync_operation` 有錯誤時回 `entry.result(False, ...)`
  - [x] `tools/perf_probe.py` 的 `_FUNCTIONS` 表跟著改名（`backup_project_binary` 那列換成新名字）
  - [x] 驗收：`python -m pytest -q` 全綠，數量 ≥ 1306 加新測試數
  - [x] 驗收：`engine/backup.py` 每個函式 ≤ 60 行（用 `ast` 算），檔案 ≤ 400 行
  - [x] 驗收：`git grep -n 'except Exception' -- engine/backup.py` 每一個命中的 handler 都把例外變成回傳的錯誤字串，沒有 `pass` 或 `return None`
  - [x] 驗收：`git grep backup_project_binary` 除了 `CHANGELOG.md` 和 `docs/history/` 之外沒有命中
  - [x] CHANGELOG `### Unreleased` 加一條
  - [x] commit

- [x] **階段 2：`perf_probe` 能啟動，探針表解析不到就大聲說**
  - [x] `:436` 改用 `entry.borrowed`
  - [x] 刪三列過期的表項
  - [x] `install_probes` 收集解析不到的名字並印出
  - [x] `tests/test_perf_probe.py` 新增：一條測試對 `_FUNCTIONS` 每一列 `name` 斷言 `engine/` 底下某個模組有這個頂層名字（用 `ast` 或 `importlib`，不要真的 import IDE 側模組後呼叫 `.NET`），一條對 `methods` 每一列斷言該 class 的 `__dict__` 有該方法。這兩條就是讓表不再過期的機制
  - [x] `engine/entry.py:7` 那句 docstring 改掉
  - [x] 驗收：`git grep -n resolve_projects -- '*.py'` 為零
  - [x] 驗收：新測試在現況上綠，把 `_FUNCTIONS` 塞一個假名字進去時紅（自己試一次，不留在 commit 裡）
  - [x] 驗收：`python -m pytest -q` 全綠
  - [x] CHANGELOG 加一條
  - [x] commit

- [x] **階段 3：`hasattr` 換 `ide_flag`，死分支刪掉**
  - [x] `engine/codesys_managers.py:430`、`:442` 換成 `ide_flag`
  - [x] `engine/codesys_utils.py` 的 `find_object_by_name` 刪 `parent_name` 參數與分支，改註解與 docstring
  - [x] `tests/test_bare_excepts.py` 的 `ALLOWED["engine/codesys_utils.py"]` 從 11 降到 10
  - [x] 驗收：`git grep -nE 'hasattr\([a-z_]+, "[a-z_]+"\) and [a-z_]+\.' -- engine/ cds/` 為零
  - [x] 驗收：`python -m pytest -q` 全綠
  - [x] CHANGELOG 加一條
  - [x] commit

- [x] **階段 4：四處騙人的文字改正**
  - [x] `engine/entry_build.py:5` 與 `:288`
  - [x] `cds/ide/silent.py:16-21` 與 `:203-205`、`tests/test_layering.py:20`、`docs/SPEC.md` D12
  - [x] `docs/SPEC.md:309` 的測試名字
  - [x] 驗收：`git grep -n 'active application' -- engine/entry_build.py` 只剩 `applications()` docstring 裡講 bug 歷史的那一處
  - [x] 驗收：`git grep -n 'three dialog\|三個對話框' -- . ':!docs/history' ':!CHANGELOG.md'` 為零
  - [x] 驗收：`git grep -n test_every_yes_no_dialog_has_an_answer -- . ':!docs/history'` 為零
  - [x] 驗收：`python -m pytest -q tests/test_doc_links.py` 綠
  - [x] commit（文件修正可以不進 CHANGELOG）

- [ ] **階段 5：讓問題不再長回來**
  - [ ] `tests/test_size_limits.py` 新增，`ALLOWED` 兩張表從程式碼算出來填
  - [ ] `PRINCIPLES.md` 兩處補句
  - [ ] `tests/test_hash.py` 新增（或併進既有測試檔，說明放哪、為什麼）
  - [ ] 驗收：`tests/test_size_limits.py` 在現況上綠；把任何一個表上的數字調高一格時紅、調低一格時紅（自己試，不留在 commit 裡）
  - [ ] 驗收：`ALLOWED_FUNCTION_LINES` 裡沒有 `engine/backup.py`（階段 1 已經把它修到上限內）
  - [ ] 驗收：`python -m pytest -q` 全綠
  - [ ] 驗收：`python -m pytest -q tests/test_doc_links.py` 綠（`PRINCIPLES.md` 改了）
  - [ ] CHANGELOG 加一條
  - [ ] commit

- [ ] **收尾**
  - [ ] 在 worktree 裡從乾淨狀態跑一次 `python -m pytest -q`，把最後一行貼進回報
  - [ ] `git log --oneline 4b4ad14..HEAD` 貼進回報
  - [ ] 第 7 節的裁決全部寫回本工單並 commit
  - [ ] 驗收（還需要人）：在一個註解裡有中文的真實專案上跑 `cdsint verify --project`，確認 compare 不炸。這張工單不開 IDE，所以留給人。
  - [ ] 驗收（還需要人）：把 `.project` 資料夾設成唯讀之後跑一次匯入，看到 `ok: false` 且 summary 講備份失敗、沒有物件被改。同上，留給人。

## 6. 回報格式

最後一則訊息要有：

1. 每個階段一行：做完 / 部分做完（哪些沒做、為什麼）/ 沒動
2. `git log --oneline 4b4ad14..HEAD`
3. 一張表：測試數（起點 1306 → 終點）、`engine/backup.py` 行數與最長函式行數、`ALLOWED["engine/codesys_utils.py"]` 的值
4. 需要人做的事，每件附一句為什麼機器做不了
5. 沒做的事，每件附一句為什麼
6. 偏離本工單的地方，以及是否已寫回第 7 節

## 7. 未決事項與裁決

工單沒講到、實作時必須決定的事，決定之後寫在這裡：

`Ruling: 決定 — 理由 — 錯了的代價`

**Ruling（階段 1）：安全備份在複製之前先存檔，存檔失敗就是備份失敗。** 第 4 節的
表只說 `save_project` 是 `finalize_sync_operation` 的一步，沒說安全備份要不要存。
理由是安全備份的用途是留住匯入前的狀態；不先存檔，複製到的是上次存檔的 `.project`，
少掉的正是這次匯入要覆蓋的那些改動。一份不是當下狀態的備份，看起來有、實際上沒有，
就是 PRINCIPLES 6 說的換頂帽子的靜默跳過。錯了的代價：專案存不了檔（例如檔案被鎖）
的時候匯入會被擋下來，就算舊的 `.project` 其實還可以當備份用。要改的話改
`create_safety_backup` 裡 `save_project` 那三行，讓它只記錄不中止。

**Ruling（階段 1）：`import_project` 和 `export_project` 多出來的錯誤處理，用同一個
函式裡的註解噪音抵掉，兩個函式的行數都沒有變長。** 這兩個函式各 229 行和 214 行，
都在移入層而且遠超過 60 行硬上限，PRINCIPLES 2 說「碰到的函式不准比原來長」。刪掉的
是只把下一行程式碼翻譯一遍的橫幅註解（`# ── Phase 1: Find all changes ──` 這類）、
描述已經不存在的程式碼的註解（`# Create project binary backup (moved down)`、
`# Metadata migration - no longer used`），以及夾在中間的多餘空行。這些都是
CLAUDE.md 註解紀律要求直接刪的東西，所以不是為了湊數字而砍。錯了的代價：如果有人覺得
那些橫幅註解幫助閱讀，他失去的是分段的視覺提示；程式碼一行都沒改。

**Ruling（階段 2）：把 `tools/perf_probe.py` 的兩張探針表搬到新檔
`tools/perf_tables.py`。** 那個檔案 511 行，超過 400 行硬上限，PRINCIPLES 2 對這種
檔案的規定是「下一樣東西進去之前先拆」，而階段 2 正是要放東西進去。拆出來的是純資料，
沒有行為，而且正好是新測試要讀的那一塊，所以縫接在這裡。搬過去的內容一個字沒改，只有
三列過期的列被刪掉、兩個 bucket 函式跟著搬並去掉底線前綴。依第 2 節的決策，搬過去的
東西維持移入層，commit 訊息寫明這是搬運。`perf_probe.py` 從 511 降到 444，仍然超過
400，但比原來短，所以規則的兩句都沒有被違反。`readMe.md` 跟著加一條，因為
`tests/test_tools_are_documented.py` 要求 `tools/` 底下每個檔案都要有說明。
錯了的代價：多一個檔案要看；想知道探針量什麼的人要多開一個檔案。要合回去的話，
把 `perf_tables.py` 的兩張表貼回 `perf_probe.py` 並改回 `_FUNCTIONS`／`_METHODS` 即可，
但那樣 `perf_probe.py` 會回到 500 行以上。

**Ruling（階段 3）：`codesys_compare_engine.py:675` 那個 `hasattr` 只刪掉，不換成
`ide_flag`。** 第 3 節只列了三處，但階段 3 的驗收 grep 會多抓到這一行：
`hasattr(container, "get_name") and container.get_name() == parent_name`。它跟另外三處
不是同一件事——它檢查的是有沒有那個方法，然後把方法叫起來，不是讀一個布林屬性。
`ide_flag` 會把任何一個 bound method 當成 True，用在這裡是錯的。真正多餘的是 `hasattr`
本身：外面那圈 `try/except:` 本來就會接住方法不存在時的 `AttributeError`，所以刪掉它
行為完全不變，還少一次進 .NET 的往返（PRINCIPLES 3）。裸 `except:` 沒有動，
`ALLOWED["engine/codesys_compare_engine.py"]` 維持 3。錯了的代價：如果將來有人把那圈
`try/except:` 縮小成只接特定例外，方法不存在的情況就會炸出來；縮小的人要記得自己補
判斷。

## 8. 接手 prompt

你在 `C:\Users\qazsskevin\Documents\repo\cdsint-release-audit`，分支 `release-audit`。先讀本工單第 0 到 4 節，再讀 `PRINCIPLES.md` 和 `CLAUDE.md`，然後從第 5 節第一個沒打勾的項目開始做。一段做完、測試綠、commit，再進下一段。需要人在場的驗收做不到就停下來，把要人做的事列成清單。決定了第 7 節的未決事項就寫回。做完照第 6 節回報。
