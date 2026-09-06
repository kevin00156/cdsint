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

- [ ] **階段 5：邊界已浮現的拆分與收尾**
  - [ ] 只拆第 4 節第五層說的那種；每拆一個檔一個 commit。
  - [ ] 驗收：`wc -l engine/codesys_utils.py` 比開工前少，且沒有新檔超過 400 行。
  - [ ] 驗收：棘輪表的每個數字不高於開工前，第 3 節 18 條的三個具體傷害各有一條測試。
  - [ ] 驗收：儀器四項全過；熱機三個中位數跟基線比，慢不超過一成，數字寫進第 6 節與 SPEC 第 7 節。
  - [ ] CHANGELOG Unreleased 加一段。
  - [ ] 沒有殘留的 IDE 行程；`%TEMP%\cdsint-work\engine\` 清掉（基線清單留一份在 `docs/history/` 若監督者要）。

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

---

## 7. 未決事項與裁決

`Ruling: 決定 — 理由 — 錯了的代價`。

先列出來的：

1. `PouType` 四招留哪一招：真 IDE 裡實測。
2. `sync_files` 的略過規則以哪一份為準：預設以 `scan_new_disk_files` 的為準（最完整），`cleanup_orphaned_files` 從此也跳 `__pycache__` 與 RESERVED_FILES；這是行為改變但方向是更安全。
3. `_hash_content` 的檔名 fallback 要不要留：預設留，加一條註解說明是哪種 kind 會走到，並加測試釘住。
4. 第五層拆哪些檔：做完前四層再決定，寫回這裡。
5. `codesys_ui.py` 的 `clr.AddReference` 假容錯：預設改成 import 失敗就 raise 一句人話，因為沒有 WinForms 的 IDE 側本來就跑不了。

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
19. `Ruling: 控制過的量法下，compare 比基線慢 6.3%（16.59 對 17.63 秒，同一台機器背對背，export 27.9 對 27.5 秒沒有差別），在一成以內，接受 — 慢的來源沒有指名的單一元凶：每個物件多經過 `resolve_object`、`_gated`、`collect_accessors` 與 `ide_read` 這幾層函式呼叫，而 IronPython 2.7 的函式呼叫本來就比行內的 if 貴。這是把同一條規則從兩份收成一份的價錢 — 錯了的代價是 407 個物件的專案每次 compare 多一秒。`
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

做的時候看到但不在範圍的：

- `history/SETTINGS_PLAN.md` 第 13 條記的是「Shm 是 233 行」，今天量到 231 行，跟 softplc 一樣。兩份副本的內容幾乎相同：231 行裡有 230 行的路徑與 SHA-256 完全一樣，唯一不同的是 `Task configuration.task_config.xml` 的 hash。export 回報 `total: 229`、`failed: 0`、`failed_objects` 空，`verify` 四步全過，所以沒有物件被靜默丟掉。少掉的那兩行是什麼，這張工單沒有查，記在這裡給下一個人。

---

## 8. 接手 prompt

你在 `C:\Users\qazsskevin\Documents\repo\cdsint-engine`，分支 `ticket/engine`。先讀 `docs/WORKER_RULES.md`（尤其儀器那節）、本工單第 0 到 4 節、`PRINCIPLES.md` 全文、`CLAUDE.md`、`docs/SPEC.md` 的 D5、D11、D12、D13、D15、4.5、6.1、第 7 節。然後從第 5 節第一個沒打勾的項目開始做，階段照順序，每一層做完先跑儀器再 commit。hash 清單 diff 不為空就停在那一層，把 diff 寫進第 7 節，回報。決定了第 7 節的事就寫回。全部做完照第 6 節回報，停下來，不要 merge、不要 push。
