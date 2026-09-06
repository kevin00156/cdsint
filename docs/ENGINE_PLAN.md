# 工單 C：引擎的平行路徑收成一條

> 建立日期 2026-09-06。分支 `ticket/engine`，worktree `C:\Users\qazsskevin\Documents\repo\cdsint-engine`。
> 鐵律在 `docs/WORKER_RULES.md`，先讀它。使用者不在也不會回答，卡住寫進最後回報。
> 這是四張工單的最後一張，在 `history/HYGIENE_PLAN.md` 合進 `main` 之後才開工。第 3 節的行號原本以 2026-09-06 晚上的 `631259b` 為準，2026-09-07 已經照 `0461006` 重核並重填。
> 這張最重，也是唯一一張每一層都要用真 IDE 驗的。驗收儀器在 `WORKER_RULES.md` 的「儀器」節，hash 清單 diff 為空是硬條件。

---

## 0. 本工單專屬的鐵律

- 臨時檔在 `%TEMP%\cdsint-work\engine\` 底下。
- **每一層做完都要跑一次儀器**，不是全部做完才跑。四層裡任何一層 hash 清單 diff 不為空就停在那一層，把 diff 寫進第 7 節，不往下做。
- `engine/` 是搬來的那一層（PRINCIPLES 說的 moved tier）。這張工單的規則：碰到的函式不能變長；新寫的函式與檔案守上限；搬來的知識（每個怪分支旁邊那段 WHY）留著，是刪重複不是刪知識。
- 不碰 `.st` 格式、pragma 名稱、`profiles/default.json` 的結構（D15）。
- 不碰 `cds/`、`cdsint/`，除了引擎介面改變時它們的呼叫端。

---

## 1. 目標與範圍

引擎的知識是真的，每個怪異分支旁邊都有一段被現場打出來的 WHY。但知識被塞進三個一千多行的檔案和四個兩三百行的函式裡，同一條規則平均寫兩到三份、靠註解提醒人肉同步，70 個 bare except 和 90 個吞噬體讓「大聲失敗」在這層不成立，還有一段從沒執行過的死碼被 bare except 蓋著。

做完之後：一條規則一份；沒有函式超過三層縮排；IDE 的全域物件由入口一次解析往下傳，引擎裡沒有 `import __main__`；替身 UI 變成「傳一個不同的 system」。

明確不做：拆 `codesys_utils.py` 成十個檔（只拆做完前四層之後邊界已經浮現的部分）；把剩下的 bare except 一次清完（維持棘輪，碰到的函式順手清）；換速度引擎（SPEC 11.1）；任何 `.st` 輸出的改變。

---

## 2. 使用者定案的決定（2026-09-06）

| # | 決策 | 選擇 | 理由 |
|---|---|---|---|
| 1 | 做到哪一層 | 刪死碼、消平行路徑、拆 `perform_import_items`、IDE 全域物件顯式傳遞，四層照順序。`codesys_utils.py` 只拆邊界已浮現的；bare except 維持棘輪 | 先猜邊界再拆檔是猜，做完前四層邊界會自己浮現；七十個 except 一次清完等於重寫，每個後面都可能藏著真專案撞出來的理由 |
| 2 | 驗收儀器 | 兩份副本匯出的 `.st` 逐檔 hash 相同是硬條件；`discover` 數字相同、`verify` exit 0、熱機速度不慢超過一成，紅了要寫 Ruling | 只跑 `verify` 證明 round trip 一致，證明不了跟重構前寫出的檔案一樣 |
| 3 | 替身 UI 的結構修法 | 歸這張：`system`、`projects`、`online` 顯式傳遞之後，`silent.py` 換函式的機制刪掉 | B 只做最小修法，這裡做完它就沒必要了 |

---

## 3. 接手前必須知道的現況事實

**2026-09-07 以 `0461006` 重核過。**A、B、D 三張工單都已經合進 `main`，所以行號跟 `631259b`
那一版差很多，事實也有幾條不成立了。底下每一條寫的是重核之後的樣子；重核改掉或推翻的地方
標「重核」。

**死碼（零呼叫者，全 repo 含 `cds/`、`cdsint/`、`tools/`、`tests/` 都 grep 過）**

1. 函式與常數：`codesys_managers.get_task_for_write`（34 到 78 行）、`codesys_utils.find_object_by_guid`（1192 到 1194 行）、`codesys_utils.find_application_recursive`（1002 到 1022 行，只剩自遞迴，加上 `codesys_online.py` 26 行一條引用它的註解）、`codesys_managers.collect_property_accessors`（524 到 586 行，`codesys_compare_engine.py` 44 行與 `entry_export.py` 25 行各 import 一次，兩邊都沒呼叫）、`codesys_utils.build_object_cache`（957 到 999 行，`compare` 30 行 import 了沒呼叫）、`codesys_constants.DEFAULT_TIMEOUT_MS`（307 行）、`codesys_constants.PROFILE_NAME`（101 行）、`DirectoryChoiceForm._on_cancel`（`ui` 164 到 167 行，沒有任何按鈕接這個事件）。

   重核：`DirectoryChoiceForm` 這個類別本身是活的，A 並沒有刪它。`show_directory_choice_dialog`（`ui` 169 行）建它，而 `show_sync_folder_dialog`（240 行）呼叫那一個。這一條只刪 `_on_cancel` 一個方法。

2. 死參數：`log_error(critical=)`（`utils` 106 行，全 repo 沒有一個呼叫端傳過它）、`perform_import_items(globals_ref=)`（`compare` 1236 行，1247 到 1249 行的 docstring 自己寫著 unused）、`ObjectManager.update(obj_info)`（`compare` 664 行永遠傳 `{}`，是唯一的呼叫端）。

   死分支：`FolderManager.export`（`managers` 840 到 844 行）兩邊都 `return "identical"`；`ConfigManager.create`（1487 到 1488 行）與 `ConfigManager.update`（1490 到 1491 行）純 `super()` 轉發。

   死 import 用 `python -m pyflakes engine/` 數，現在 38 個：`entry_export.py` 22 個（含五個 manager 類別、`is_nvl`、`is_graphical_pou`、`get_object_path`）、`codesys_compare_engine.py` 7 個、`entry_import.py` 4 個、`codesys_managers.py` 3 個（模組層的 `time` 與 `XML_TYPES_CONST`，加上 90 行一個函式內的 `re`）、`codesys_utils.py` 1 個（`csv`）、`entry_build.py` 1 個（`sys`）。

   重核：原本只列了四個檔，`compare_engine` 那七個與 `entry_build` 那一個是這次數出來的。

3. 從沒執行過的：`codesys_managers.py` 1005 到 1013 行是找 `PouType` 的第四招，掃 `sys.modules`，但這個檔沒有 import `sys`（imports 在 7 到 26 行），NameError 被 1012 行的 `except: pass` 吞掉。`python -m pyflakes engine/` 直接把它報出來：`codesys_managers.py:1008: undefined name 'sys'`。

   重核：`codesys_utils.Logger._initialize` 的同一個病 A 已經修掉了。它現在什麼都不查，log 路徑由 `init_logging(base_dir, debug)`（`utils` 94 行）一次給。這一條剩 `managers` 一處。

**平行路徑（同一條規則寫兩份以上）**

4. 分類加路徑快取的快速路徑：`entry_export.py` 242 到 271 行與 `codesys_compare_engine.py` 253 到 280 行是同一個演算法（diff 過，差別只有變數名、計數器、註解措辭）。同組的 XML gate（export 318 到 324 行、compare 284 到 295 行）、property accessor 掃描（export 281 到 297 行、compare 306 到 325 行、`managers.collect_property_accessors` 是第三份而且沒人呼叫）。compare 284 行的註解自己說「CRITICAL: honor the same export_xml gate that export uses」。

5. Manager 派發兩套而且規則不同：`entry_export.py` 326 到 332 行（is_xml 就 native 除非有專屬的；否則按 GUID；否則 default）與 `codesys_compare_engine.resolve_manager`（644 到 653 行：`.xml` 副檔名就 native；按 GUID；XML_TYPES 就 native；default）。圖形化 POU 兩邊答案碰巧一樣，靠的是副檔名。

6. `POUManager.export`（`managers` 885 到 950 行）與 `PropertyManager.export`（1098 到 1172 行）尾段逐行相同，各 25 行（926 到 950 對 1148 到 1172）：identical 檢查、`_disk_moved_since_sync`、寫檔、`exported_paths`、cache 更新。`if 'exported_paths' in context:` 在 `managers` 出現 9 次（758、797、834、933、947、1155、1169、1407、1423 行）。

   重核：原本說 8 次，現在數到 9 次。

7. 「export_native 到暫存檔、讀回、刪除」寫了四次：`get_task_for_write`（`managers` 42 到 54 行，死的）、`is_nvl`（`managers` 80 到 118 行）、`export_interface_declaration`（`managers` 424 到 450 行）、`get_ide_content`（`compare` 67 到 124 行），各有各的暫存檔命名和 bare except。`NativeManager.export`（`managers` 1357 到 1427 行）是第五處，但它是正經的匯出路徑，不是「讀回來看一眼」，性質不同。

8. 三個磁碟走訪、三套略過規則：`cleanup_orphaned_files`（`entry_export` 51 到 71 行：跳 dot-dir、dot-file、只看 `.st` 與 `.xml`，不跳 `__pycache__` 也不看 RESERVED_FILES）、`scan_new_disk_files`（`compare` 588 到 615 行：跳 dot-dir 加 `__pycache__`、RESERVED_FILES、dot-file）、`has_st_files`（`compare` 570 到 575 行）。今天沒出事是因為 RESERVED_FILES 裡剛好沒有 `.st`。`entry_export.py` 126 行還有第四個走訪，那個是刪空資料夾用的，問的不是同一個問題。

9. 微型平行路徑：讀名字有 `unhandled.name_of`（68 行）、`utils._obj_label`（746 行）、`codesys_online._name`（162 行）、`plc_link.device_name`（217 行）四份；讀 kind 有 `codesys_online._kind`（143 行）、`plc_link._kind_of`（232 行）、`compare._is_pou_or_itf`（667 行）；`managers._parent_of`（180 行）等於 `compare._parent_or_none`（1094 行）；`managers._cache_key`（172 行）等於 `compare._guid_or_none`（1101 行）；`codesys_online._children`（133 行）等於 `plc_link._children`（224 行），差別只在有沒有 `unhandled.note`。`compare_engine` 35 行跨模組 import 私有名 `_find_child_transparent`，`tools/perf_probe.py` 197 行也認得這個名字。

10. `context['effective_type']` 是透過共享 dict 偷傳的隱藏參數：`entry_export.py` 334 行每個物件寫一次，`managers` 在 888、916、1107、1359 行用 `context.get('effective_type', safe_str(obj.type))` 讀回，fallback 還會再打一次 .NET。

11. type cache 的 `(eff_type, is_xml, rel_path)` 是位置 tuple，三處用 `len(...) > 2` 防身：`compare` 254 與 351 行、`entry_export` 243 行。

12. 相對路徑解析與 Application GUID 字面值，A 已經收乾淨了。剩下唯一一個 GUID 字面值在 `utils` 1158 行，`TYPE_GUIDS.get("folder", "738bea1e-…")` 拿字面值當 profile 的備胎。

    重核：這一條原本寫「A 會收」，現在確認收完了，只剩上面那一處。

**深巢與長函式**

13. `codesys_compare_engine.perform_import_items`（1236 到 1494 行）259 行、巢狀深度 9，四趟 pass 內嵌 device remap、孤兒刪除、XML 批次、POU 子物件保存還原、ST 建立。move 處理 XML 版（1338 到 1352 行）和 ST 版（1456 到 1470 行）逐字相同，只有 log 訊息差一個字；「在 container 裡用小寫名字找 child」寫了四次（`compare` 971、987、1394、1420 行）。

14. `codesys_managers._hash_content`（1262 到 1355 行）94 行、深度 9，四個從子字串嗅出來的布林旗標接一串 if/elif；timestamp 與 guid 過濾上下兩半各寫一遍；fallback 拿檔名算 hash，註解自己說「preserved here, not endorsed」；1354 到 1355 行的 `except: return ""` 是第 18 條那個具體傷害的來源。1332 行的 `skip_next` 設成 False 之後再也沒有被設成 True，那個 if 分支永遠不會進去。

15. `entry_build.build_project`（144 到 486 行）343 行、深度 7：三段「Attempt」定位邏輯（263 到 405 行）內嵌、表格排版、寫 log 檔、UI 全在一個函式；415 行是註解掉的程式碼；182 行往 log 塞一句假的 phase 訊息（`"Typify code..."`，註解自己標了 Aesthetic phase marker）。

    重核：原本 394 行，A 改完剩 343 行。`main` 的 `if error: pass` B 已經修掉了，現在（488 到 498 行）錯誤會回一個 `entry.result(False, error)`。

16. `codesys_utils.ensure_folder_path`（1094 到 1189 行）96 行、深度 6，1113 到 1147 行是 debug trace，`src/` 前綴剝除在 1108 到 1109 行與 `find_object_by_path` 1238 行各一份，建資料夾四次嘗試做一件事（`create_folder`、`create_child`、回傳 falsy 之後重掃、丟例外之後再重掃）。

    重核：`load_base_dir` 已經被 A 刪掉了，全 repo 只剩 `tests/test_discover.py` 97 行一條註解提到它。這一條剩 `ensure_folder_path`。

**全域物件與例外**

17. 找 IDE 全域物件的解析器剩三套：`resolve_projects`（`utils` 130 到 172 行，第三招掃全部 `sys.modules`）、`resolve_system`（`utils` 187 到 216 行）、`codesys_online.resolve_online`（59 到 75 行）。`entry.lend()` 已經是「顯式借出」的正確答案，這三個是它的平行路徑。

    重核：`_resolve_primary_project` 與 `get_project_prop` 都被 A 刪了，所以第四層要收的從四個縮成三個。

18. bare `except:` 現在 70 個，棘輪表在 `tests/test_bare_excepts.py`：`managers` 29、`utils` 26、`compare` 6、`build` 5、`ui` 2、`entry_compare` 2。「整個 handler 只有 pass、continue、break 或回一個常數」的吞噬體，`engine/` 底下 AST 數到 90 個：`managers` 34、`utils` 25、`compare` 12、`build` 4、`entry_compare` 3、`plc_link` 3、`unhandled` 3、`codesys_online` 2、`codesys_ui` 2、`entry_export` 2。

    重核：開工時是 81 個 bare except，A、B、D 清掉 11 個（`utils` 33 到 26、`build` 6 到 5、`ui` 5 到 2）。吞噬體原本記 105 個，這次用同一支腳本重數是 90 個。

    具體傷害三例，全部還在。第一，`managers` 1012 行藏著第 3 條那個 NameError。第二，`utils` 267 行 `except: pass` 在 `get_quick_ide_hash`（234 到 288 行）裡，property 的子物件讀失敗就當 GET 與 SET 是空的去算 hash，快取於是說「identical」。第三，`managers` 1355 行 `_hash_content` 出錯回 `""`，而 `NativeManager.export` 1401 行寫的是 `old_hash and old_hash == new_hash`，空字串永遠讓這個條件為 False，那個檔每次 export 都被算成「updated」。

19. `codesys_ui.py` 7 到 21 行模組層 `try: clr.AddReference(...) except: pass` 是假容錯：import 失敗的話 100 行的 `class DirectoryChoiceForm(Form)` 照樣 NameError，另一個 Form 子類別同病。`ask_yes_no`（78 到 98 行）的 88 到 97 行帶一條摸 `__main__.PromptChoice` 的備用對話路徑。

    重核：`SettingsForm` 與 `ask_yes_no_cancel` 都被前面的工單刪了。剩 `DirectoryChoiceForm`（100 行）與 `SyncFolderPathForm`（181 行）兩個 Form 子類別，備用對話路徑只剩 `ask_yes_no` 一條。

20. `codesys_utils.py` 826 到 827 行把狀態存在函式物件上（`read_ide_attrs._bp_dumped`），是一次性的探針躺在每個物件都經過的熱路徑裡。

**過期註解（會主動騙人的）**

21. `constants` 47 行「installed next to codesys_constants.pyw」；`utils` 1107 行「handled by Project_export migration now」；`compare` 1026 行「Project_import and Project_compare」；`compare` 模組 docstring 14 行列了 `update_object_metadata()`，656 行說它被移除了；墓碑註解 `# Removed X` 在 `utils` 452、619 行與 `compare` 64、656 行；`utils` 32 到 33 行標題貼兩次；`entry_export` 238 行與 `utils` 1076 行寫「Second pass」但沒有 first pass；`compare` 56 到 62 行同一個橫幅標題貼兩次；`compare` 1024 到 1033 行十行悼念 `finalize_import`；`compare` 1061 行「phase 2 import」；`utils` 1572 行「e179ef9 policy」；`codesys_online` 25 到 26 行引一個死函式當深度守衛的依據。

    重核：`settings` 5 行「run Project_directory.py」與 `export` 189 行「only Project_Build reads」都已經不在了。`engine/` 底下現在只剩兩處提到 `Project_` 前綴的舊腳本名，就是上面列的那兩條。

**`codesys_utils.py` 的十五個職責（做完前四層再看要拆哪些）**

22. 檔案現在 1637 行。現況：logging（32 到 113）、IDE 全域物件解析（117 到 216）、IDE 屬性旗標與快速 hash（219 到 288）、hash 與字串轉換（291 到 313）、ST 型別嗅探與格式化（316 到 383、455 到 515、569 到 620）、git 設定檔（386 到 452）、XML 合併（517 到 566）、pragma（622 到 743）、build_properties 讀寫（746 到 902）、讀檔與解析 `.st`（905 到 954）、IDE 樹導航（957 到 1265）、備份（1268 到 1406）、互動計時器（1409 到 1448）、sync cache（1451 到 1565）、metadata 與 finalize（1568 到 1637）。

    重核：專案屬性、Application 計數、sync 資料夾解析這三塊已經被 A 刪光或搬走，所以從十七個職責變成十五個。

**開工前重核清單**

- [x] 每一條用名字 grep，行號重填，A、B、D 已經動過的標「重核」。
- [x] 重跑 `tests/test_bare_excepts.py` 的數字（81 降到 70），重數 AST 的吞噬體（105 降到 90）。
- [x] Windows 與 WSL 兩邊測試各 1072 個全綠。
- [x] 儀器基線：兩份副本各 export 一次存 hash 清單、`discover --json` 存起來、`verify` exit 0、熱機三次 export、compare、build 的中位數。全部存在 `%TEMP%\cdsint-work\engine\baseline\`，摘要在第 6 節。

---

## 4. 設計

四層，每層做完跑儀器、commit。

**第一層：刪死碼。** 第 3 節 1 到 3 條。`sys.modules` 那招連同它的三個前置策略要看清楚：第一招 `PouType.Program` 直接全域在真 IDE 裡成立就留第一招，其他三招刪；留一句註解說 `PouType` 是 IDE 注入的全域名。死 import 用 `python -m pyflakes` 或 AST 列出來一次刪乾淨。

**第二層：消平行路徑。** 第 3 節 4 到 11 條，一條一個 commit：

- `resolve_object(obj, cache)` 一個函式，回 `(eff_type, is_xml, rel_path, skip_reason)`，export 與 compare 都吃它；XML gate 規則進 `classify_object` 或 profile；accessor 掃描一份。
- `(is_xml, kind) → manager` 一張表，兩邊查同一張。
- `_write_text(obj, rel_path, file_path, content, content_hash, context)` 一個，POU 與 Property 的 export 只剩「怎麼組出 content」；`exported_paths` 的加入放進它。
- `native_xml_of(project, obj, recursive)` 一個。
- `sync_files(base_dir)` 一個 generator，三個走訪都用它，略過規則一份。
- `engine/ide_read.py` 新檔（守上限）：`name_of`、`kind_of`、`parent_of`、`children_of`、`guid_of`，全部帶 D13 記錄，四個模組的私有版本刪，`_find_child_transparent` 變公開。
- `effective_type` 明著傳：`export(obj, effective_type, rel_path, context)`。
- type cache 載入時正規化成固定 shape，`len(...) > 2` 三處刪。
- `_hash_content` 改成 `kind → [line predicates]` 一張表，函式剩十行。

**第三層：拆 `perform_import_items`。** 一個 `child_named(container, name)`，一個 `move_if_needed(item, obj)`，四趟 pass 各自成函式，主體剩順序表（像 `entry_plc.in_order` 那樣）。每個新函式守 40 行、3 層。`build_project` 同法：`locate_message(msg, decl, impl)` 純函式（能在 CI 測），主體剩 build、collect、verdict；註解掉的程式碼與假 phase 訊息刪。`ensure_folder_path` 的 debug trace 搬去 `tools/`，建資料夾一次、失敗就 raise 進 D13。`read_ide_attrs._bp_dumped` 那段搬去 `tools/`。

**第四層：IDE 全域物件顯式傳遞。** `projects`、`system`、`online` 由每個 entry body 的 `main` 從自己的 namespace 拿一次（stub 與 `silent.run` 注入的那個），往下傳給需要的函式；`resolve_projects`、`resolve_system`、`resolve_online` 刪（`_resolve_primary_project` A 已經刪了）；引擎裡 `grep "import __main__"` 為零，`grep "sys.modules"` 為零。`Logger` 的 log 路徑 A 已經改成由 `init_logging(base_dir, debug)` 一次給，這一項不用再做。做完之後 `cds/ide/silent.py` 換函式的機制刪掉：替身就是把一個 `system` 替身放進 body 的 namespace，`codesys_ui.ask_yes_no` 收 `system` 當參數而不是自己找。`_ui_patches`、`_install`、`UI_MODULE`、`tests/test_layering.py` 那個登記的 `__import__` 一起消失。

**第五層（只做邊界已浮現的）。** 做完前四層，`codesys_utils.py` 剩下的職責裡，凡是「已經有自己的一組函式、互相只呼叫彼此、外面只有兩三個進入點」的，各自成檔：候選是 `st_text.py`（格式、解析、pragma）、`sync_cache.py`、`backup.py`、`log.py`。不確定的留著。沒有 `utils`。

**過期註解。** 第 3 節 21 條在碰到那個檔的時候順手刪，不另開一層。

**bare except。** 碰到的函式順手把 `except:` 改成接預期的例外或讓它炸；棘輪數字往下改。不碰的函式不動。第 3 節 18 條的三個具體傷害要修：`get_quick_ide_hash` 讀失敗不能當空、`_hash_content` 出錯不能回空字串當 hash。

---

## 5. 分階段與驗收

- [x] **階段 0：重核與基線**
  - [x] 第 3 節重核清單做完，行號重填，commit（`69ba4d0`）。
  - [x] 儀器基線存好，摘要（檔案數、hash 清單的 SHA-256、discover 三個數字、三個中位數秒數）寫進第 6 節。
  - [x] 驗收：兩份副本 hash 清單各 231 行，也就是 229 個物件加兩個 git 設定檔（第 7 節第 9 條）；softplc 副本 `discover` total 407、22 種、unknown 空；Shm 副本 464、24 種、9 個 unknown（第 7 節第 8 條）。

- [x] **階段 1：刪死碼**
  - [x] 驗收：第 3 節 1 到 3 條列的名字 `grep -rn` 全 repo 為零（`docs/history/` 與本工單不算）。
  - [x] 驗收：`python -m pyflakes engine/` 沒有 unused import。
  - [x] 驗收：儀器四項全過（兩份副本 hash diff 各 0 行、discover 前後相同、verify exit 0、熱機中位數在一成內）。測試 Windows 與 WSL 各 1072 個全綠。

- [x] **階段 2：消平行路徑**
  - [x] 每一條一個 commit，commit 訊息說收了哪一條。十條共十個 commit。
  - [x] 驗收：`grep -rn "honor the same\|exactly like compare\|same as export" engine/` 為零（提醒人肉同步的註解沒有存在的理由了）。
  - [x] 驗收：`grep -rn "len(.*) > 2" engine/` 為零；`grep -rn "context\['effective_type'\]\|context.get('effective_type'" engine/` 為零；`grep -rn "def _name\|def _kind\|def _children\|def _parent_o\|def _obj_label" engine/` 為零。
  - [x] 驗收：測試涵蓋「export 與 compare 對同一個物件回同一個 `(eff_type, is_xml, rel_path)`」（`tests/test_classify.py`）「`sync_files` 跳 `__pycache__`、dot-dir、RESERVED_FILES」（`tests/test_sync_dir.py`）「`_hash_content` 對每種 kind 的過濾規則」（`tests/test_sync_cache.py` 的 `TestHashContentPerKind`）。
  - [x] 驗收：儀器四項全過。棘輪從 70 降到 51（`managers` 29→18、`utils` 26→19、`compare` 6→5、`build` 5、`ui` 2、`entry_compare` 2）。測試 Windows 與 WSL 各 1149 個全綠。

- [x] **階段 3：拆長函式**
  - [x] 驗收：`perform_import_items` 剩 30 行、`ensure_folder_path` 剩 11 行，兩個都不再出現在長函式清單裡；`build_project` 剩 60 行、2 層。新函式全部在 40 行、3 層內。
  - [x] 驗收：`grep -n "^\s*#.*\(def \|if \|for \|return \)" engine/entry_build.py` 沒有註解掉的程式碼；182 行那句假的 phase 訊息也刪了。
  - [x] 驗收：`locate_message` 有 CI 測試（`tests/test_build_log.py`，26 個）。
  - [x] 驗收：儀器四項全過。hash diff 兩份副本各 0 行、discover 前後相同、verify exit 0；速度用控制過的量法比，compare 慢 6.3%（第 7 節第 18、19 條）。測試 Windows 與 WSL 各 1191 個全綠。

- [~] **階段 4：顯式傳遞**（引擎那一半做完，`silent.py` 那一項沒做，見第 7 節第 26 條）
  - [x] 驗收：`grep -rn "import __main__\|sys.modules" engine/` 為零；`grep -rn "def resolve_projects\|def resolve_system\|def resolve_online\|_resolve_primary_project" engine/` 為零。
  - [ ] 驗收：`cds/ide/silent.py` 裡沒有 `_ui_patches`、`_install`、`UI_MODULE`；`tests/test_layering.py` 的例外登記為零。——**沒做**，理由與接手方法在第 7 節第 26 條。
  - [x] 驗收：`tests/test_silent.py` 全綠。替身這條路每一趟 `--project` 命令都會走到，兩份副本的 export、import、compare、build 各跑過好幾輪都 exit 0。`--target` 形式沒有另外起看門人實測，見第 7 節第 27 條。
  - [x] 驗收：儀器四項全過。兩份副本 hash diff 各 0 行、discover 前後相同、verify exit 0；控制過的 compare 中位數 17.05 秒，比基線的 16.59 秒慢 2.7%。

- [x] **階段 5：邊界已浮現的拆分與收尾**
  - [x] 拆了 `engine/backup.py` 與 `engine/sync_cache.py`，各一個 commit。第 4 節第五層列的候選裡，`st_text.py` 與 `log.py` 沒拆，理由在第 7 節第 28 條。
  - [x] 驗收：`engine/codesys_utils.py` 從 1637 行降到 1113 行。這張工單新增的七個檔都在 400 行以內：`import_items.py` 322、`classify.py` 205、`backup.py` 192、`build_log.py` 175、`sync_cache.py` 163、`ide_read.py` 115、`sync_dir.py` 76。
  - [x] 驗收：棘輪每個數字都比開工前低（`compare` 6→3、`managers` 29→18、`utils` 33→11、`build` 6→0、`ui` 5→0、`entry_compare` 2→2）。總數不寫在這裡：`tests/test_bare_excepts.py` 的 `ALLOWED` 表就是計數（PRINCIPLES 6），而這一行第一次寫的總數是錯的。第 3 節 18 條的三個具體傷害各有測試：PouType 那個 NameError 由 `tests/test_names_resolve.py` 這一整類守著，`get_quick_ide_hash` 由 `tests/test_ide_read.py` 的 `TestQuickHashRefusesToGuess`，`_hash_content` 由 `tests/test_sync_cache.py` 的 `test_content_that_cannot_be_hashed_raises`。
  - [x] 驗收：儀器四項全過。兩份副本 hash diff 各 0 行、discover 前後相同、verify exit 0；熱機中位數見第 6 節那張表，compare 的判定見第 7 節第 19 條。數字寫進 SPEC 第 7 節。
  - [x] CHANGELOG Unreleased 加一段。
  - [x] 沒有殘留的 IDE 行程；`%TEMP%\cdsint-work\engine\` 清掉。

---

- [x] **階段 6：審查後修正（監督者 2026-09-07 派回）**

  一個沒看過對話的 reviewer 逐 commit 讀完 31 個 commit，對每一組去重都對過舊碼，結論是沒有會改 `.st` 位元組或把整趟命令變成 traceback 的回歸；監督者另外在真 IDE 上跑過三種形式（`--project`、`--target` 用 `headless_watch.py` 起的看門人、選單 stub 用 `--runscript` 直跑），都通，兩份副本的 hash 也重量過零差異，所以 Ruling 27 那個洞補上了。剩下的是三個真問題加一批文件與註解。一到三必修，四到十同一輪做完，十一到十三順手。修完照第 6 節再回報一次，儀器四項再跑一次。

  - [x] **1. 登入預檢的失敗從「一行警告」變成「完全無聲」，docstring 說的正好相反。** `engine/entry_import.py` 的 `find_logged_in_applications` 在 `unhandled.start()` 之前執行；`codesys_online.py` 現在走 `ide_read.children_of`、`kind_of`，失敗只 `unhandled.note`，那筆紀錄在 `unhandled.start()` 被清掉，舊版的 `log_warning` 也沒了。`engine/ide_read.py` 檔頭說「the login pre-flight used to log a warning and carry on」是這模組的行為改變，實際結果是連警告都沒有。情境：device 節點外掛不在、`get_children()` 丟例外，預檢看不到 application，import 認定沒人登入，每個 create、move、delete 在 IDE 裡失敗，log 沒有一行指向原因。改法：`unhandled.start()` 移到預檢之前，讓它真的變成 D13 的一筆、`ok=False`；docstring 改成講真的。加一條測試：預檢讀不到 children 時結果的 `failed_objects` 有那個節點。
  - [x] **2. Ruling 22 的守衛只守了三個屬性。** `engine/entry_build.py` 的 `_message_id` 裸讀 `msg.prefix`、`getattr(msg, "number", 0)`，`collect_rows` 裡 `getattr(msg, "position", -1)`，都不在 try 內。Ruling 22 自己的教訓是 IronPython 的 `getattr` 帶預設值擋不住會丟例外的屬性。把同一則訊息的每個屬性讀取都放進同一個守衛，一則壞訊息只丟掉那一列，不丟整份判決。
  - [x] **3. `tests/test_names_resolve.py` 的白名單放行 `PouType`，等於放行這張工單修掉的那種 bug。** `IDE_GLOBALS` 套用到整個 `engine/`，但第四層之後只有 `entry_*.py` 有資格裸讀 IDE 全域名；`codesys_managers.py` 再寫一個裸 `PouType.Program` 測試照樣綠。另外有一條斷言 `ALLOWED == IDE_GLOBALS | PYTHON_2_BUILTINS`，那就是 `ALLOWED` 的定義，釘住的是零。改法：白名單只對 `engine/entry_*.py`、`stub/`、`cds/ide/headless.py` 生效，其他引擎模組一個 IDE 全域名都不准；那條空斷言刪。
  - [x] **4.** `cds/ide/silent.py` 檔頭「`__main__.system` — the shared engine modules look there」與 `_install` 換 `__main__.system` 那半：引擎已經沒有讀者了。Ruling 26 不刪 `ask_yes_no` 那半的理由成立，但 `__main__.system` 這半跟 SPEC 6.1 無關，刪掉，連 `tests/test_silent.py` 裡「codesys_utils:517 finds system through __main__」那兩條一起改。
  - [x] **5.** 工單第 3 節 21 條列的過期註解，被碰過的檔沒順手刪：`entry_export.py` 的「Second pass」、`codesys_compare_engine.py` 的墓碑與悼念 `finalize_import`、「Project_import and Project_compare」、「phase 2 import」，`codesys_utils.py` 的墓碑與「e179ef9 policy」，`codesys_constants.py` 的「codesys_constants.pyw」。全刪。
  - [x] **6.** 「81 降到 35」算錯，棘輪表加起來是 34。`CHANGELOG.md` 與本工單階段 5 那行改成 34，或照 PRINCIPLES 6 不寫數字只指棘輪表。
  - [x] **7.** `_hash_content` 的檔名 fallback 從四種 flavour 縮成兩種：舊碼四種特殊 flavour 過濾成空都走 `crc(fallback_name)`，新碼只有 alarm 兩種，textlist 與 device 改回 `crc("")`；另把 `'<Object Guid="' in line` 改成 `strip().startswith(...)`。Ruling 3 說「留、釘住」，這是悄悄改了規則。二選一：改回四種並釘住，或寫一條 Ruling 說為什麼縮成兩種，附 hash 清單為證。
  - [x] **8.** 同一個 property 的子物件讀不到會被記兩次：`classify.py` 與 `codesys_utils.py` 各 note 一次，export 的摘要變成「2 object(s): P, P」。記一次。
  - [x] **9.** 兩處 `except: pass` 改成 `unhandled.note` 讓 `ok` 從 True 變 False（`classify.py` 的 accessor、`compare_engine.py` 的 XML `export_native` 失敗）。D13 站得住，但第 0 節說行為改變要寫 Ruling，補上。
  - [x] **10.** Ruling 21 的理由只涵蓋 create：`import_items.py` 的 `move_if_needed` 現在 `ensure_folder_path` 會 raise，整個物件不更新、被點名；舊碼回 None、跳過搬移、物件在原地更新。把 move 這一半寫進 Ruling 21，或維持舊行為。
  - [x] **11.**（順手）`NativeManager.export` 在 `_hash_file(tmp_path)` 丟例外時留下 `.xml.tmp`，加 finally。
  - [x] **12.**（順手）`engine/entry_compare.py` 局部變數 `e` 未用。
  - [x] **13.**（順手）`_object_text` 兩次讀取包在同一 try，decl 丟就不讀 impl；拆成兩個。
  - [x] 記進第 7 節不動的（兩條都確認過，寫在第 7 節第 34 條後面）：`locate_message` 對「有 position、沒 object」的答案跟舊 Attempt 1 不同（只影響 debug log）；`_import_xml` 的 `fresh.get_name()` 在 try 外（實務不會丟）。
  - [x] 驗收：測試涵蓋「預檢讀不到 children 時 `failed_objects` 有它」「一則 `.prefix` 會丟的 build 訊息只丟那一列」「`codesys_managers.py` 加一行裸 `PouType` 時 `test_names_resolve` 紅」（用 tmp 檔或 monkeypatch 驗，不真的改引擎）。
  - [x] 驗收：`grep -rn "Second pass\|finalize_import\|phase 2 import\|e179ef9\|codesys_constants.pyw\|# Removed" engine/` 為零。`grep -n "__main__" cds/ide/silent.py` 剩兩行，那兩行在解釋 body 被 exec 成什麼名字，不是舊機制的殘留；理由在第 7 節第 32 條。
  - [ ] 驗收：儀器四項再跑一次（兩份副本 hash 零差異、discover 相同、verify exit 0、速度不慢超過一成）；Windows 與 WSL 測試綠。

---

## 6. 回報格式

同 `history/SETTINGS_PLAN.md` 第 6 節，加上每一層的儀器結果表：層、hash diff 行數、discover 三個數字、verify exit、三個中位數秒數。

### 儀器怎麼跑

每一層都照同一個順序，不然前後兩次量的不是同一件事（理由在第 7 節第 6 到 9 條）：

1. 從 `%TEMP%\cdsint-work\engine\master\` 複製一份乾淨的 `.project`，清空同步資料夾。
2. `discover --json`，跑在還沒有任何命令碰過的副本上。
3. `export --json`，然後把同步資料夾裡每個檔的相對路徑與 SHA-256 列成清單，排除 `sync_cache.json`。
4. `verify -y --json`，四步都要 ok。
5. 熱機中位數：export、compare、build 各連跑四次，丟掉第一次，取後三次的中位數。量的是命令自己回報的 `elapsed_s`，IDE 啟動不算在內。條件照 SPEC 第 7 節：export 每次跑之前清空同步資料夾，compare 之前在磁碟上改一個 `.st`，build 兩次之間什麼都不動。

驗收命令一律從 worktree 根目錄下 `python -m cdsint.cli ...`，因為 PATH 上的 `cdsint` 是使用者主 clone 的 editable install。

### 階段 0 基線（2026-09-07，commit `69ba4d0`）

| 量的東西 | 原廠 3.5.21.40（softplc 副本） | Delta 1.10（Shm 副本） |
|---|---|---|
| hash 清單行數 | 231（229 個物件加 `.gitignore`、`.gitattributes`） | 231 |
| hash 清單的 SHA-256 | `0B24716B0DEC547622E238FD826DBA430FBA4F2090BAFDA58BA2E5BA89726552` | `545EA020C87D42DE845338D4E1F0D244BD2C77648E42E491B12C8086A3041E1E` |
| discover total | 407 | 464 |
| discover kind 數 | 22 | 24 |
| discover unknown | 空，exit 0 | 9 個，exit 1（見第 7 節第 8 條） |
| export | ok，229 個物件，0 個失敗 | ok，229 個物件，0 個失敗 |
| verify | 四步全過（import 16.9、export 16.8、compare 12.1、build 22.3 秒） | 四步全過（import 15.4、export 16.4、compare 11.8、build 32.1 秒） |
| 熱機 export 中位數 | 22.941 秒 | 23.281 秒 |
| 熱機 compare 中位數 | 15.833 秒 | 15.328 秒 |
| 熱機 build 中位數 | 25.764 秒 | 30.538 秒 |

這一組數字跟 SPEC 第 7 節那張表不能直接相減：那張是 2026-09-05 量的，機器狀態不同（SPEC 自己說冷熱差兩到三倍），而且這裡的 compare 是「改一個 `.st` 之後」而不是「改一個 POU 之後」。這一組的用途只有一個，就是給這張工單的四層當比較基準。而且底下那張表裡各層的中位數只能當趨勢看：那些是在沒有控制起點的情況下量的，同一支腳本量階段 1 結束時的程式碼（那一層只刪東西）也會「慢 7.8%」。真正用來判斷有沒有超過一成的，是同一台機器、同一個起點、新舊碼背對背各量一次的那一組（第 7 節第 18 條）。

測試：Windows `python -m pytest tests -q` 1072 個全綠，WSL `python3 -m pytest tests -q` 1072 個全綠。

### 每一層的儀器結果

| 層 | hash diff 行數 | discover total／kind／unknown | verify exit | export／compare／build 中位數（秒） |
|---|---|---|---|---|
| 基線 | — | 407／22／空；464／24／9 | 0；0 | 22.9／15.8／25.8；23.3／15.3／30.5 |
| 1 刪死碼 | 0；0 | 407／22／空；464／24／9 | 0；0 | 24.1／16.4／25.0；（階段 5 才量） |
| 2 消平行路徑 | 0；0 | 407／22／空；464／24／9 | 0；0 | 19.5／16.9／25.3；（階段 5 才量） |
| 3 拆長函式 | 0；0 | 407／22／空；464／24／9 | 0；0 | 24.0／17.6／23.8；（階段 5 才量） |
| 4 顯式傳遞 | 0；0 | 407／22／空；464／24／9 | 0；0 | compare 17.0（控制過的量法，基線 16.6） |
| 5 拆檔與收尾 | 0；0 | 407／22／空；464／24／9 | 0；0 | 24.1／17.3／25.2；21.7／15.2／30.5 |

---

## 7. 未決事項與裁決

`Ruling: 決定 — 理由 — 錯了的代價`。

先列出來的：

1. `PouType` 四招留哪一招：實測結果是第二招，見第 10 條。
2. `sync_files` 的略過規則以哪一份為準：預設以 `scan_new_disk_files` 的為準（最完整），`cleanup_orphaned_files` 從此也跳 `__pycache__` 與 RESERVED_FILES；這是行為改變但方向是更安全。
3. `_hash_content` 的檔名 fallback 要不要留：預設留，加一條註解說明是哪種 kind 會走到，並加測試釘住。
4. 第五層拆哪些檔：`backup.py` 與 `sync_cache.py`，`st_text.py` 與 `log.py` 留著。理由在第 28 條。
5. `codesys_ui.py` 的 `clr.AddReference` 假容錯：照預設改成 raise，見第 25 條。

階段 0 定下來的（儀器怎麼跑，之後每一層都照這個跑）：

6. `Ruling: hash 清單排除 sync_cache.json — 那個檔存的是每個檔案上次同步時的 mtime 與大小，是本機狀態而且 gitignore（SPEC 4.5），每跑一次就會變，留在清單裡等於讓硬條件永遠紅 — 錯了的代價是每一層都看到一行跟重構無關的 diff，久了就沒有人再看那個 diff 了。`
7. `Ruling: discover 跑在 export 之前，而且跑在一份剛複製、沒有任何命令碰過的 .project 上 — export 結束會存檔，而 IDE 自己存一次檔就會讓 softplc 那份少掉五個 alarm_group 節點（`history/SETTINGS_PLAN.md` 第 15 條量過同一件事），所以存檔後再跑的 discover 回答的是另一個問題 — 錯了的代價是數到 402 節點 21 種 kind，跟 WORKER_RULES 寫的 407/22 對不上，然後花時間追一個不存在的 walker bug。`
8. `Ruling: Delta 那份副本的 discover 基線是 464 節點、24 種 kind、9 個 unknown、exit 1，硬條件是「跟基線一模一樣」而不是「unknown 空」 — 那 9 個是 Delta 專屬的物件種類（ArchiveObject、PersistentVariables、Hardware Configuration、Network Configuration、Recipe Manager、EtherCAT Topology，加三個十六進位名字的物件），`profiles/default.json` 裡沒有它們，discover 把名字報出來正是它該做的事（D13） — 錯了的代價是把一個開工前就存在的 exit 1 當成這張工單弄壞的。`
9. `Ruling: 第 5 節階段 0 的「兩份副本 hash 清單各 229 行」讀成「229 個可匯出物件」 — 229 個物件寫成 228 個 .st 加 1 個 .xml，再加 .gitignore 與 .gitattributes，兩份副本都是 231 行；`history/SETTINGS_PLAN.md` 第 13 條已經裁過同一件事 — 錯了的代價是照字面驗收的人會以為基線不對。`

階段 1 定下來的：

10. `Ruling: 第 1 條的 PouType 四招留第二招（`__main__.PouType.Program`），第一、三、四招刪 — 工單猜的是留第一招，但第一招讀的是這個模組自己的全域名 `PouType`，而 `entry.lend()` 把 IDE 的全域複製到入口本體上，不是複製到 `codesys_managers` 上，所以那個名字在這裡從來就不存在，不是「還沒量到」而是結構上不可能成立；真 IDE 兩台都實測過，原廠 3.5.21.40（ScriptEngine 4.2.0.0）與 Delta 1.10（4.0.0.0）建一個新的 FUNCTION_BLOCK，兩台都走第二招 — 錯了的代價是所有需要新建 POU 的匯入都會退到 `create_child`，那條路建出來的物件種類不對。`
11. `Ruling: `create_pou` 解不出 PouType 時的 `create_child` 退路留著 — 它會先 `log_error` 說自己在退，不是靜默跳過（D13），而這台機器上有五個 IDE 安裝、相容性矩陣還列了更多，我只在其中兩台量過 — 刪掉一條會出聲的退路換兩台的量測結果，賭得比留著大 — 錯了的代價是留了一段在這兩台上跑不到的程式碼。`
12. `Ruling: 階段 1 到 4 的熱機中位數只跑原廠那份副本，兩份都跑留到階段 5 — 一份副本的三組四次要十五分鐘，兩份就是半小時，五層下來兩個半小時，而 hash 清單 diff 才是硬條件，速度那條有一成的容差；原廠那份是 WORKER_RULES 與 SPEC 第 7 節都拿來當基準的那一份 — 錯了的代價是某一層只在 Delta 上變慢的話，要到階段 5 才會看到。`

階段 2 定下來的：

13. `Ruling: 真 IDE 抓到的回歸 — `ide_read.guid_of` 與 `parent_of` 失敗時不記進登記簿，只有 `kind_of` 與 `children_of` 記 — 工單說這個新模組「全部帶 D13 記錄」，照做之後原廠 3.5.21.40 上一趟乾淨的 229 個物件匯出變成 `ok: False`，登記簿裡有三筆專案根物件；原因是路徑組裝要往上走到專案根，而這個 API 用丟例外的方式表示「沒有上一層」，跟「外掛不見了」長得一模一樣，分不出來。往上走的兩個讀取安靜回 None，往下走的兩個照記 — 錯了的代價是一個外掛不見的物件，它的 GUID 讀不到時不會被點名，但它的 kind 或子物件讀不到時會。`
14. `Ruling: `Resolved` 帶第五個欄位 `cache`（"hit"／"invalidated"／"miss"），比工單寫的四個多一個 — compare 的 Pass 1 會回報「幾個路徑快取命中、幾個失效」，那是分辨「真的慢」跟「快取是冷的」的唯一依據，收成一個函式之後這個數字沒有別的地方拿得到 — 錯了的代價是一個 namedtuple 多一個欄位。`
15. `Ruling: `engine/classify.py` 在第二層就拆出來，不等到第五層 — 收完平行路徑之後，`codesys_managers.py` 從 1491 行漲到 1497 行，比開工時還長，而 PRINCIPLES 2 說已經超過上限的檔案不准再變長；分類這一組（`resolve_object`、兩道 gate、accessor 收集、manager 查表）互相只呼叫彼此，外面只有 export 與 compare 兩個進入點，正是第五層說的那種「邊界已浮現」 — 錯了的代價是第五層要重新看一次還剩什麼可拆。`
16. `Ruling: 統一之後的略過規則多了一條「沒有路徑就不寫」，export 這一側是新的 — compare 本來就有 `if should_skip or not rel_path: continue`，export 沒有；而 `effective_type` 改成必要參數之後，manager 不再有「rel_path 是 None 就自己重算」的退路，所以 export 拿到空路徑會把 None 傳進去 — 唯一會回空路徑的是頂層資料夾，而資料夾本來就不寫檔，所以磁碟上看不出差別（兩份副本的 hash 清單 diff 都是 0 行）— 錯了的代價是某個頂層資料夾不再進 `exported_paths`，而那個路徑是空字串，永遠對不上任何檔案。`
17. `Ruling: `_hash_content` 出錯改成往上丟，`_hash_file` 只接 IOError、OSError、UnicodeDecodeError — 第 18 條第三個具體傷害：回 `""` 之後 `NativeManager.export` 的 `old_hash and old_hash == new_hash` 永遠是 False，那個檔每次 export 都被算成 updated 而沒有人看得出為什麼；`_hash_file` 讀不到檔案仍然回 `""`，因為那時候 `is_new` 已經是 True，這個 hash 根本不會被拿來比 — 錯了的代價是一份真的無法 hash 的 XML 會讓那個物件的匯出丟例外，而例外會被每個迴圈的「處理這一個物件」那一層接住並點名（D13）。`

階段 3 定下來的：

18. `Ruling: 速度的量法改成「同一台機器、同一個起點、新舊碼背對背各量一次」，第 6 節那張表裡各層的中位數只當趨勢看 — 階段 3 量到 compare 比基線慢 12.1%，紅了；追下去才發現量法本身沒有控制起點：每一組 compare 都跑在上一組留下的副本與同步資料夾上。用同一支腳本量階段 1 結束時的程式碼（那一層只刪東西），也「慢了 7.8%」，那不可能是程式碼造成的 — 錯了的代價就是我已經付過的那一次：照著錯的數字去找原因，改了兩處 .NET 讀取，結果數字只動了 0.07 秒。`
19. `Ruling: compare 的速度判定是「落在量測誤差裡，沒有量到可以指認的變慢」，不是一個百分比 — 控制過的成對量測做了兩次，方向相反：階段 3 時舊碼 16.59 秒、新碼 17.63 秒（新碼慢 6.3%），階段 5 時新碼 17.74 秒、舊碼 17.96 秒（新碼快 1.2%）；兩次隔一個半小時，同一份舊碼從 16.59 漂到 17.96 秒，機器本身就有 8% 的變動，跟要量的東西同一個數量級 — 錯了的代價是把一個 6% 的雜訊當成真的變慢去追（我已經追過一次，改了兩處重複的 .NET 讀取，數字只動 0.07 秒），或者反過來，把一個真的變慢當成雜訊放過。要更確定需要同一小時內多對交錯量測，這張工單沒有做。`
20. `Ruling: `perform_import_items` 的四趟 pass 搬到新檔 `engine/import_items.py`，`build_project` 的訊息定位搬到新檔 `engine/build_log.py` — 兩個都是「拆長函式之後這個檔反而變長」的同一個問題：`codesys_compare_engine.py` 拆完會從 1373 漲到 1412 行，`entry_build.py` 已經 500 行；而拆出來的兩塊各自是一句話講得完的工作（「照順序把改動套用到 IDE」、「一則 build 訊息指到哪一行」），後者還因此變成純文字進出、CI 測得到 — 錯了的代價是 `engine/` 多兩個檔。`
21. `Ruling: `ensure_folder_path` 建不出資料夾改成 raise，不再回 None — 四次嘗試裡有兩次是同一個 CODESYS 怪癖的補救（`create_folder` 可能真的建好了卻回一個 falsy 的殼），收成「建一次、重掃一次、還是沒有就 raise」；三個呼叫端都在每個物件的 try/except 裡面，例外會被接住並點名（D13），而回 None 以前會再往上走一層，變成物件被建在錯的地方 — 錯了的代價是資料夾真的建不出來時，那個物件的匯入失敗而不是安靜地跑到別的地方去。`
22. `Ruling: 真 IDE 抓到的第二個回歸 — 讀 build 訊息的 `.object` 要自己包一層 try — 我把 `hasattr(msg, "object") and msg.object` 換成 `getattr(msg, "object", None)`，看起來等價，但 IronPython 2.7 的 `hasattr` 會吞掉例外回 False；Delta 1.10 對某些訊息的 `.object` 會丟「The object GUID '...' is not valid」，於是整份 build 變成一個 traceback，`verify` 停在第四步 — 錯了的代價就是它造成的那一次：一則讀不到的訊息把另外一百多則的判決一起丟掉。`

階段 4 定下來的：

23. `Ruling: 四個解析器換成 `engine/entry.py` 的一個 `borrowed(caller_globals, name)`，其他需要的地方改成參數 — `projects`、`system`、`online`、`PouType` 都是 IDE 注入到腳本 namespace 的名字，而每個 entry body 的 namespace 就是那一個；舊的解析器先看呼叫端的 globals，再看 `__main__`，再掃過每一個載入過的模組直到找到看起來像的東西，那是在找一個呼叫端本來就握著的物件，順便還可能撿到上一趟留下的死物件 — 錯了的代價是某個呼叫端忘了傳，那個名字就是 None，而每個呼叫端都得自己說 None 是什麼意思（匯出沒有 `projects` 不能跑，登入預檢沒有 `online` 只表示沒有人登入）。`
24. `Ruling: 六個 manager 方法要的專案改成建構時給一次（`create_import_managers(project, pou_type)`）— 一趟命令只開一個專案，而那六處要的就是它；`PouType` 走同一條路，只有會建 POU 的兩個 manager 用得到 — 錯了的代價是多兩個建構參數，換掉一個會掃遍所有模組的搜尋。`
25. `Ruling: `codesys_ui.py` 的 `clr.AddReference` 假容錯改成直接 raise，`ask_yes_no` 摸 `__main__` 的備用對話路徑刪掉 — 這是工單第 7 節第 5 條原本就預設的方向；模組裡每一個類別都繼承 `Form`，import 失敗之後往下一行就是 NameError，只是訊息完全不提真正的原因。備用路徑要從 `__main__` 拿 `system`、`PromptChoice`、`PromptResult` 三個名字，而它是為了「WinForms 不在」而存在的——在一個沒有 WinForms 就整個載不進來的模組裡 — 錯了的代價是沒有 WinForms 的 IDE 側現在會在 import 就停下來，訊息是一句人話而不是 NameError。這一改也讓 `codesys_ui.py` 的 bare except 歸零。`

沒做完的：

26. **`cds/ide/silent.py` 換函式的機制沒有刪。**第 4 節第四層還有一句「做完之後 `silent.py` 換函式的機制刪掉」，`_ui_patches`、`_install`、`UI_MODULE` 與 `tests/test_layering.py` 那筆登記都還在。

    理由：要刪它，引擎就得改成透過 `system.ui` 問是非題，而不是呼叫 `codesys_ui.ask_yes_no`。這條路可行也乾淨（替身本來就攔 `system.ui`，D12 的那個例外會跟著消失），但它會把 PLC 下載的確認對話框從 Windows 的 MessageBox 換成 CODESYS 的圓鈕提示框——使用者看得到的改變——而且 SPEC 6.1 明文寫著「對話框只透過 `codesys_ui.ask_yes_no`、`system.ui.choose`，因為替身 UI 只攔這兩個」，還有兩條測試守著這個設計。改它等於一個 worker 自己改掉 SPEC 的一條已定案決策，而且動的是無頭與看門人這條路。

    這一項不做不影響第四層的驗收條件：`engine/` 底下 `import __main__` 與 `sys.modules` 都是零，四個解析器都刪了。留下來的是 `cds/ide` 伸手進 `engine` 的那一個 D12 例外，不是引擎伸手去找全域物件。

    要接手的人：把 `SilentSystem` 的 `ui` 加一個 `ask_yes_no`，`engine/entry_plc.py` 改成問 `system.ui`，`engine/codesys_ui.ask_yes_no` 就沒有呼叫端了可以刪，`show_sync_folder_dialog` 已經收 `system` 了同法處理；然後 `_install`、`_ui_patches`、`_ui_module`、`UI_MODULE` 與 `STRING_IMPORTS_ALLOWED` 一起消失，SPEC 6.1 那句話要跟著改。

27. **`--target` 形式沒有實測。**用 `tools/headless_watch.py` 起自己的看門人試了兩次（原廠 3.5.21.40、`--noUI`、自己的副本、自己記 pid），行程兩次都在幾秒內就結束，`cdsint list` 一直看不到它，而且沒有留下任何 log 可以說為什麼。試錯的成本開始超過這一項的價值，就停在這裡。兩次的行程都確認結束了，使用者的兩個 IDE 沒有碰到，暫存資料夾清掉了。

    這一項留白的影響有限：`--target` 跟 `--project` 差的只有傳輸（看門人的檔案協定），而這張工單一個位元組都沒有改 `cds/` 或 `cdsint/`；協定那一端由 `tests/test_watcher.py` 與 `tests/test_ipc.py` 守著，兩個都綠。引擎本體則是兩台真 IDE 上跑過好幾輪 export、import、compare、build，而 `--project` 走的正是同一個替身 UI。


階段 5 定下來的（第 4 條「第五層拆哪些檔」的答案）：

28. `Ruling: 拆 `engine/backup.py` 與 `engine/sync_cache.py`，`st_text.py` 與 `log.py` 不拆 — 第 4 節第五層的判準是「已經有自己的一組函式、互相只呼叫彼此、外面只有兩三個進入點」。備份那一組完全符合：整組在 `codesys_utils.py` 外面只被提到一次（`tools/perf_probe.py` 的一個名字），連它的兩個進入點 `finalize_sync_operation` 與 `create_safety_backup` 都是為它存在的。sync cache 那一組也符合：`file_signature` 是匯出與比對唯一必須講好的東西，而它們曾經各算各的（一邊 `int(st.st_mtime)`、一邊 `os.path.getmtime()` 的浮點數），結果雙方寫的每一筆都被對方拒絕，真專案上快取命中率是零。

    `st_text.py` 不拆的理由是它沒有「外面只有兩三個進入點」：格式化、解析、pragma 這一組被 `managers`、`compare_engine`、`import_items` 從十幾個地方叫，拆出去只是把一長串 import 從一個檔搬到另一個檔。`log.py` 不拆的理由相反——它的進入點少，但幾乎每個模組都 import 它，拆一次要改十幾行 import，而換到的只是把 80 行搬走。兩個都留著，等下一個真的需要動它們的人來決定 — 錯了的代價是 `codesys_utils.py` 還有 1113 行，仍然超過上限，下一次要往裡面加東西的人得先拆。`

29. `Ruling: 新增 `tests/test_names_resolve.py`，用 pyflakes 問「哪些名字解不出來」，IDE 注入的全域名逐一列出來 — 這張工單有兩個 NameError 跑到真 IDE 上才被發現（`sync_cache.build_folder_hashes` 少 import `calculate_hash`、`save_pou_children` 少一個 `project` 參數），兩個都在假物件測試碰不到的分支裡，而 pyflakes 從頭到尾都在報它們；我看不到是因為 `engine/` 的 pyflakes 輸出被 `system`、`Severity`、`PouType` 這些真的沒定義也真的沒問題的名字淹沒，而寬到能蓋住它們的過濾器也寬到能蓋住一個打錯的字。過濾器搬進測試檔，白名單寫成兩個具名的集合 — 錯了的代價是 WSL 那邊沒裝 pyflakes 時這 72 條會 skip，所以 `requirements-dev.txt` 加了 `pyflakes>=3.0`。`

做的時候看到但不在範圍的：

- `history/SETTINGS_PLAN.md` 第 13 條記的是「Shm 是 233 行」，今天量到 231 行，跟 softplc 一樣。兩份副本的內容幾乎相同：231 行裡有 230 行的路徑與 SHA-256 完全一樣，唯一不同的是 `Task configuration.task_config.xml` 的 hash。export 回報 `total: 229`、`failed: 0`、`failed_objects` 空，`verify` 四步全過，所以沒有物件被靜默丟掉。少掉的那兩行是什麼，這張工單沒有查，記在這裡給下一個人。

---

階段 6 定下來的：

30. `Ruling: 兩處原本吞掉的例外改成進登記簿，是刻意的行為改變（審查第 9 條要我補的 Ruling）— `classify.collect_accessors` 讀不到某個 property 的子物件、`compare_engine.get_ide_content` 對某個 XML 物件的 `export_native` 失敗，兩處以前都是 `except: pass`，命令照樣回 `ok: True`。兩個失敗的後果都一樣：那個物件的內容被當成空的拿去比對或寫出，而「它就是沒有匯進去，我也不知道為什麼」正是這個工具存在的理由要消滅的東西（D13、目標 6）。所以 `ok` 從 True 變 False 是修正，不是回歸 — 錯了的代價是一個外掛不見的物件會讓整趟命令的 exit code 從 0 變 1，而那正是要的：其他物件照樣做完，名字列在 `data.failed_objects` 裡（D11）。`
31. `Ruling: Ruling 21 的「建不出資料夾就 raise」只涵蓋建立，搬移那一半改成「記下來但不擋更新」（審查第 10 條）— `move_if_needed` 走到 `ensure_folder_path` 時，磁碟已經告訴我們這個檔搬到哪個資料夾去了；那個資料夾建不出來的時候，物件的內容仍然是可讀的，只有新家不在。讓例外往上冒會使那個物件連內容都不更新，為了一個跟內容無關的理由把它留在上一版；而舊碼回 None、安靜跳過搬移，是另一個極端。現在是第三種：記進登記簿（`ok` 因此是 False），然後讓 `update_existing_object` 照常跑完 — 錯了的代價是一個物件的內容更新了但位置沒動，而使用者會在 `failed_objects` 裡看到它的名字。`
32. `Ruling: `grep -n "__main__" cds/ide/silent.py` 沒有歸零，剩兩行（審查第 4 條的驗收）— 那兩行在解釋 `namespace["__name__"] = "cds_watcher_script"`，也就是「body 被 exec 成一個不叫 `__main__` 的名字，所以它自己的 `if __name__ == "__main__"` 不會觸發、不會跑第二次」。那是現在這段程式碼的事實，不是舊機制的殘留；為了讓 grep 歸零而刪掉它，等於刪掉一段還成立的知識。伸手拿 IDE 全域名的那一半（`main.system = silent` 與它的 undo）已經刪乾淨了 — 錯了的代價是這條驗收要用眼睛確認一次，不能只看 grep 的數字。`
33. `Ruling: 棘輪的總數不再寫在 `CHANGELOG.md` 與本工單裡，改成指 `tests/test_bare_excepts.py` 的 `ALLOWED` 表（審查第 6 條）— 那一行第一次寫成「81 降到 35」，實際是 34；PRINCIPLES 6 本來就說那張表是計數、其他檔案不該再帶一個要跟它同步的數字，而這次就是被它抓到的 — 錯了的代價是讀者要多開一個檔才看得到總數。`
34. `Ruling: `_hash_content` 的四種特殊 flavour 全部保留「過濾完是空的就 hash 檔名」，`<Object Guid="` 也改回子字串比對（審查第 7 條）— 我把表格化的時候縮成兩種、並把子字串比對收緊成 `startswith`，兩個都沒有寫進任何 Ruling，而 Ruling 3 說的是「留、加註解、加測試釘住」。查下去才知道為什麼沒有測試抓到：textlist 與 device 這兩種的過濾規則會保留「認出它是哪一種」的那一行本身，所以它們的過濾結果永遠不是空的，那條 fallback 實務上到不了。「今天到不了」跟「規則寫的是兩種」不是同一件事 — 錯了的代價就是這一次的：規則被靜靜改掉，而沒有任何東西會紅。現在四種都釘住了，連「那兩種為什麼到不了」也一起釘住。`

審查記下來但不動的兩條，確認過：

- `locate_message` 對「有 position、沒有 object」的訊息答案跟舊的 Attempt 1 不同。舊碼 Attempt 1 需要 `obj_ref` 才算，沒有 object 就不算；新碼的 `_from_position` 只看 position 與兩段文字，而沒有 object 時兩段文字都是空字串，所以 position 一定落進 impl 的第 1 行第 1 欄。只影響 debug 模式才寫的 `build_*.log` 的位置欄，不影響錯誤數、判決或任何 `.st`。不改。
- `_import_xml` 裡 `fresh.get_name()` 在 try 之外。`fresh` 是 `child_named()` 剛剛才成功讀過名字的那個物件，同一趟裡再讀一次會丟的情況是「物件在這兩行之間消失」。不改。

監督者裁的（2026-09-07，審查後）：

- Ruling: Ruling 26（`silent.py` 換 `ask_yes_no` 的機制不刪）接受 — 改成問 `system.ui` 會把 PLC 下載的確認框從 MessageBox 換成 CODESYS 的提示框，是使用者看得到的改變，SPEC 6.1 也明文寫著對話框走哪幾個函式；但 `__main__.system` 那半沒有讀者了，刪（階段 6 第 4 條）— 錯了的代價是 D12 的那個字串 import 例外繼續存在，留給下一個碰替身 UI 的人。
- Ruling: Ruling 27（`--target` 沒實測）由監督者補上 — 用 `tools/headless_watch.py` 對 softplc 副本起看門人（worker 兩次沒起來的原因是量測方法：GUI 子系統的 exe 對 shell 立刻返回、prints 沒有去處；監督者用一支把 stdout 導到檔案再 exec 工具的包裝腳本，並把 `__file__` 設成工具的路徑），`cdsint list` 看到 `softplc_refactor-<pid>`，`export --target` 寫出 229 個檔、`compare --target` 零差異、`stop` 收掉、IDE 自己退出。選單那條路同法用 `--runscript` 直跑 `stub/Project_export.py`，229 個檔。三種形式都在真 IDE 上跑過這張的程式碼 — 錯了的代價是無。
- Ruling: 兩份副本的 hash 由監督者重量，`main` 對分支各匯出一次：softplc 231 個檔零差異、`discover` 402/21/0 兩邊相同；Shm 231 個檔零差異、`discover` 459/23/9 兩邊相同（那 9 個 unknown 是 Delta 專案本來就有的）— 硬條件成立。

---

## 8. 接手 prompt

你在 `C:\Users\qazsskevin\Documents\repo\cdsint-engine`，分支 `ticket/engine`。先讀 `docs/WORKER_RULES.md`（尤其儀器那節）、本工單第 0 到 4 節、`PRINCIPLES.md` 全文、`CLAUDE.md`、`docs/SPEC.md` 的 D5、D11、D12、D13、D15、4.5、6.1、第 7 節。然後從第 5 節第一個沒打勾的項目開始做，階段照順序，每一層做完先跑儀器再 commit。hash 清單 diff 不為空就停在那一層，把 diff 寫進第 7 節，回報。決定了第 7 節的事就寫回。全部做完照第 6 節回報，停下來，不要 merge、不要 push。
