# 工單 C：引擎的平行路徑收成一條

> 建立日期 2026-09-06。分支 `ticket/engine`，worktree `C:\Users\qazsskevin\Documents\repo\cdsint-engine`。
> 鐵律在 `docs/WORKER_RULES.md`，先讀它。使用者不在也不會回答，卡住寫進最後回報。
> 這是四張工單的最後一張，在 `HYGIENE_PLAN.md` 合進 `main` 之後才開工。第 3 節的行號以 2026-09-06 晚上的 `631259b` 為準，前三張做完會漂很多，開工先重核。
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

引擎的知識是真的，每個怪異分支旁邊都有一段被現場打出來的 WHY。但知識被塞進三個一千多行的檔案和四個兩三百行的函式裡，同一條規則平均寫兩到三份、靠註解提醒人肉同步，81 個 bare except 和一百多個吞噬體讓「大聲失敗」在這層不成立，還有一段從沒執行過的死碼被 bare except 蓋著。

做完之後：一條規則一份；沒有函式超過三層縮排；IDE 的全域物件由入口一次解析往下傳，引擎裡沒有 `import __main__`；替身 UI 變成「傳一個不同的 system」。

明確不做：拆 `codesys_utils.py` 成十個檔（只拆做完前四層之後邊界已經浮現的部分）；把 81 個 bare except 一次清完（維持棘輪，碰到的函式順手清）；換速度引擎（SPEC 11.1）；任何 `.st` 輸出的改變。

---

## 2. 使用者定案的決定（2026-09-06）

| # | 決策 | 選擇 | 理由 |
|---|---|---|---|
| 1 | 做到哪一層 | 刪死碼、消平行路徑、拆 `perform_import_items`、IDE 全域物件顯式傳遞，四層照順序。`codesys_utils.py` 只拆邊界已浮現的；bare except 維持棘輪 | 先猜邊界再拆檔是猜，做完前四層邊界會自己浮現；81 個 except 一次清完等於重寫，每個後面都可能藏著真專案撞出來的理由 |
| 2 | 驗收儀器 | 兩份副本匯出的 `.st` 逐檔 hash 相同是硬條件；`discover` 數字相同、`verify` exit 0、熱機速度不慢超過一成，紅了要寫 Ruling | 只跑 `verify` 證明 round trip 一致，證明不了跟重構前寫出的檔案一樣 |
| 3 | 替身 UI 的結構修法 | 歸這張：`system`、`projects`、`online` 顯式傳遞之後，`silent.py` 換函式的機制刪掉 | B 只做最小修法，這裡做完它就沒必要了 |

---

## 3. 接手前必須知道的現況事實

以 `631259b` 為準。A 會刪掉設定相關的一大塊，B 會改對話框標題常數，重核。

**死碼（零呼叫者，全 repo 含 `cds/`、`cdsint/`、`tools/`、`tests/` 都 grep 過）**

1. 函式：`codesys_managers.get_task_for_write`（34 到 78 行）、`codesys_utils.find_object_by_guid`（1450 行）、`find_application_recursive`（1260 到 1280 行，只剩自遞迴和 `codesys_online.py` 26 行一條註解引用）、`collect_property_accessors`（`managers` 524 到 586 行，import 了兩次沒人呼叫）、`build_object_cache`（`utils` 1215 行）、`DEFAULT_TIMEOUT_MS`、`PROFILE_NAME`、`DirectoryChoiceForm._on_cancel`（`ui` 378 行）。A 會刪 `DirectoryChoiceForm` 整個。
2. 死參數：`log_error(critical=)`、`perform_import_items(globals_ref=)`（1246 到 1249 行自己承認 unused）、`ObjectManager.update(obj_info)`（`compare` 664 行永遠傳 `{}`）。死分支：`FolderManager.export` 840 到 844 行兩邊都 return "identical"；`ConfigManager.create/update` 1487 到 1491 行純 `super()` 轉發。死 import：`entry_export.py` 22 個（含五個 manager class、`is_nvl`、`is_graphical_pou`、`get_object_path`），`entry_import.py` 4 個，`managers` 的 `time`、`XML_TYPES_CONST`，`utils` 的 `csv`。
3. 從沒執行過的：`codesys_managers.py` 984 到 1014 行找 `PouType` 的第四招掃 `sys.modules`，但這個檔沒有 import `sys`（imports 在 7 到 26 行：`os`、`codecs`、`tempfile`、`zlib`、`time`），NameError 被 1012 行的 `except: pass` 吞掉。`codesys_utils.py` 的 `Logger._initialize` 52 到 66 行用 `projects` 這個在模組裡未定義的名字，同病（A 會改這段）。

**平行路徑（同一條規則寫兩份以上）**

4. 分類加路徑快取的快速路徑：`entry_export.py` 251 到 281 行與 `codesys_compare_engine.py` 249 到 280 行是同一個演算法（diff 過，差別只有變數名、計數器、註解措辭）。同組的 XML gate（export 334 到 339 行、compare 291 到 295 行）、property accessor 掃描（export 297 到 312 行、compare 307 到 325 行、`managers.collect_property_accessors` 第三份沒人呼叫）。compare 284 到 290 行的註解自己說「CRITICAL: honor the same export_xml gate that export uses」。
5. Manager 派發兩套且規則不同：`entry_export.py` 342 到 347 行（is_xml 就 native 除非有專屬；否則按 GUID；否則 default）與 `codesys_compare_engine.resolve_manager` 644 到 653 行（`.xml` 副檔名就 native；按 GUID；XML_TYPES 就 native；default）。圖形化 POU 兩邊答案碰巧一樣，靠的是副檔名。
6. `POUManager.export`（`managers` 885 到 950 行）與 `PropertyManager.export`（1098 到 1172 行）尾段約 30 行逐行相同：identical 檢查、`_disk_moved_since_sync`、寫檔、exported_paths、cache 更新。`if 'exported_paths' in context: context['exported_paths'].add(rel_path)` 在 managers 出現 8 次。
7. 「export_native 到暫存檔、讀回、刪除」寫了四次：`get_task_for_write` 42 到 54 行（死的）、`is_nvl` 96 到 108 行、`export_interface_declaration` 432 到 443 行、`get_ide_content` 81 到 98 行，各有各的暫存檔命名和 bare except。
8. 三個磁碟走訪、三套略過規則：`cleanup_orphaned_files`（export 46 到 68 行：跳 dot-dir、dot-file、只看 `.st`、`.xml`，不跳 `__pycache__` 也不看 RESERVED_FILES）、`scan_new_disk_files`（compare 589 到 614 行：跳 dot-dir 加 `__pycache__`、RESERVED_FILES、dot-file）、`has_st_files`（562 到 575 行）。今天沒出事是因為 RESERVED_FILES 裡剛好沒有 `.st`。
9. 微型平行路徑：讀名字有 `unhandled.name_of`、`utils._obj_label`、`codesys_online._name`、`plc_link.device_name` 四份；讀 kind 有 `codesys_online._kind`、`plc_link._kind_of`、`compare._is_pou_or_itf`；`managers._parent_of` 等於 `compare._parent_or_none`；`managers._cache_key` 等於 `compare._guid_or_none`；`codesys_online._children` 等於 `plc_link._children`（差別只在有沒有 `unhandled.note`）。`compare_engine` 跨模組 import 私有名 `_find_child_transparent`。
10. `context['effective_type']` 是透過共享 dict 偷傳的隱藏參數：`entry_export.py` 349 行每個物件寫一次，managers 在 888、916、1107、1359 行用 `context.get('effective_type', safe_str(obj.type))` 讀回，fallback 還會再打一次 .NET。
11. type cache 的 `(eff_type, is_xml, rel_path)` 是位置 tuple，三處用 `cached_info[2] if (cached_info and len(cached_info) > 2) else None` 防身（compare 254、351 行；export 253 行）。
12. 相對路徑解析（A 會收成一份）；Application GUID 字面值三處兩個值（A 會收）。

**深巢與長函式**

13. `codesys_compare_engine.perform_import_items`（1236 到 1494 行）259 行、巢狀深度 10，四趟 pass 內嵌 device remap、孤兒刪除、XML 批次、POU 子物件保存還原、ST 建立。move 處理 XML 版（1337 到 1352 行）和 ST 版（1456 到 1470 行）逐字相同；「在 container 裡用小寫名字找 child」寫了四次（970 到 973、986 到 989、1393 到 1394、1419 到 1420 行）。
14. `codesys_managers._hash_content`（1262 到 1355 行）深度 9，四個從子字串嗅出來的布林旗標接一串 if/elif；timestamp 與 guid 過濾上下兩半各寫一遍（1291 到 1292、1340 到 1344 行）；fallback 拿檔名算 hash，註解自己說「preserved here, not endorsed」。
15. `entry_build.build_project`（95 到 488 行）394 行、深度 7：三段「Attempt」定位邏輯（263 到 406 行）內嵌、表格排版、寫 log 檔、UI 全在一個函式；10 個 bare 或 broad except；411 到 420 行是註解掉的程式碼；182 行往 log 塞假的 phase 訊息；`main` 491 到 493 行 `if error: pass`。A 會改 112 到 160 行。
16. `codesys_utils.load_base_dir`（543 到 641 行）深度 8（A 會大砍）；`ensure_folder_path`（1352 到 1447 行）深度 7，1380 到 1406 行是 debug trace，`src/` 前綴剝除在 1366 到 1367 行與 `find_object_by_path` 1496 行各一份，`TYPE_GUIDS.get("folder", "738bea1e-…")` 用字面值當 profile 的備胎，建資料夾四次嘗試做一件事。

**全域物件與例外**

17. 找 IDE 全域物件的解析器四套：`resolve_projects`（`utils` 138 到 180 行，第三招掃全部 `sys.modules`）、`resolve_system`（195 到 224 行）、`_resolve_primary_project`（500 到 510 行）、`codesys_online.resolve_online`（59 到 75 行）。`entry.lend()` 已經是「顯式借出」的正確答案，這些是它的平行路徑。每個呼叫 `get_project_prop()` 的函式都隱性依賴「誰 exec 了我」（A 會刪 `get_project_prop`）。
18. bare `except:` 81 個（棘輪表 `tests/test_bare_excepts.py`：utils 33、managers 29、compare 6、build 6、ui 5、entry_compare 2）。「整個 body 只有 pass、continue、回預設值」的 handler 105 個（AST 數的：utils 34、managers 33、compare 11、plc_link 5、build 4）。具體傷害三例：`managers` 1012 行藏了第 3 條的 NameError；`utils` 277 行 `except: pass` 在 `get_quick_ide_hash` 裡，property 的子物件讀失敗就當 GET/SET 是空的算 hash，cache 說「identical」；`managers` 1354 行 `_hash_content` 出錯回 `""`，`NativeManager.export` 1401 行 `old_hash and old_hash == new_hash` 遇到空字串永遠 False，那個檔每次 export 都被「updated」。
19. `codesys_ui.py` 8 到 19 行模組層 `try: clr.AddReference... except: pass` 是假容錯，122 行 `class SettingsForm(Form)` 在 import 失敗時照樣 NameError（A 刪 SettingsForm，其他 Form 子類別同病）。`ask_yes_no` 89 到 95 行、`ask_yes_no_cancel` 112 到 119 行各帶一條摸 `__main__.PromptChoice` 的備用對話路徑。
20. `codesys_utils.py` 1084 到 1097 行把狀態存在函式物件上（`read_ide_attrs._bp_dumped`），是一次性的探針躺在每個物件都經過的熱路徑裡。

**過期註解（會主動騙人的）**

21. `constants` 46 行「installed next to codesys_constants.pyw」；`settings` 5 行「run Project_directory.py」；`utils` 1365 行「handled by Project_export migration now」；`compare` 1026 行「Project_import and Project_compare」；`export` 189 行「only Project_Build reads」；`compare` 模組 docstring 8 到 14 行列了 `update_object_metadata()`，656 行說它被移除了；墓碑註解 `# Removed X` 在 `utils` 710、877、`compare` 64、656 行；`utils` 33 到 34 行標題貼兩次；`export` 32、182、224、248 行「Second pass」但沒有 first pass；`compare` 1024 到 1033 行十行悼念 `finalize_import`；`compare` 1061 行「phase 2 import」；`utils` 1855 行「e179ef9 policy」；`codesys_online` 25 到 26 行引一個死函式當深度守衛的依據。

**`codesys_utils.py` 的十七個職責（做完前四層再看要拆哪些）**

22. logging（35 到 121 行）、IDE 全域物件解析（125 到 224）、hash（299 到 307、981 到 992）、ST 型別嗅探與格式化（324 到 371、713 到 874）、pragma（880 到 992）、build_properties 讀寫（995 到 1160）、專案屬性（382 到 464，A 刪）、Application 計數（465 到 541，A 刪）、sync 資料夾解析（543 到 641，A 大砍）、git 設定檔（644 到 707）、XML 合併（775 到 824）、IDE 樹導航（1215 到 1523）、備份（1526 到 1661）、互動計時器（1664 到 1703）、sync cache（1706 到 1821）、版本檢查與 metadata 與 finalize（1823 到 1928，A 砍一半）。

**開工前重核清單**

- 每一條用名字 grep，行號重填，A、B、D 已經動過的劃掉或更新。
- 重跑 `tests/test_bare_excepts.py` 的數字，重數 AST 的吞噬體。
- 儀器基線：兩份副本各 export 一次存 hash 清單、`discover --json` 存起來、`verify` exit 0、熱機三次 export、compare、build 的中位數。全部存在 `%TEMP%\cdsint-work\engine\baseline\`，而且 commit 一份摘要（不含路徑）進本工單第 6 節。

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

**第四層：IDE 全域物件顯式傳遞。** `projects`、`system`、`online` 由每個 entry body 的 `main` 從自己的 namespace 拿一次（stub 與 `silent.run` 注入的那個），往下傳給需要的函式；`resolve_projects`、`resolve_system`、`_resolve_primary_project`、`resolve_online` 刪；引擎裡 `grep "import __main__"` 為零，`grep "sys.modules"` 為零。`Logger` 的 log 路徑由 `init_logging(base_dir)` 一次給。做完之後 `cds/ide/silent.py` 換函式的機制刪掉：替身就是把一個 `system` 替身放進 body 的 namespace，`codesys_ui.ask_yes_no` 收 `system` 當參數而不是自己找。`_ui_patches`、`_install`、`UI_MODULE`、`tests/test_layering.py` 那個登記的 `__import__` 一起消失。

**第五層（只做邊界已浮現的）。** 做完前四層，`codesys_utils.py` 剩下的職責裡，凡是「已經有自己的一組函式、互相只呼叫彼此、外面只有兩三個進入點」的，各自成檔：候選是 `st_text.py`（格式、解析、pragma）、`sync_cache.py`、`backup.py`、`log.py`。不確定的留著。沒有 `utils`。

**過期註解。** 第 3 節 21 條在碰到那個檔的時候順手刪，不另開一層。

**bare except。** 碰到的函式順手把 `except:` 改成接預期的例外或讓它炸；棘輪數字往下改。不碰的函式不動。第 3 節 18 條的三個具體傷害要修：`get_quick_ide_hash` 讀失敗不能當空、`_hash_content` 出錯不能回空字串當 hash。

---

## 5. 分階段與驗收

- [ ] **階段 0：重核與基線**
  - [ ] 第 3 節重核清單做完，行號重填，commit。
  - [ ] 儀器基線存好，摘要（檔案數、hash 清單的 SHA-256、discover 三個數字、三個中位數秒數）寫進第 6 節。
  - [ ] 驗收：兩份副本 hash 清單各 229 行；`discover` total 407、22 種、unknown 空。

- [ ] **階段 1：刪死碼**
  - [ ] 驗收：第 3 節 1 到 3 條列的名字 `grep -rn` 全 repo 為零（`docs/history/` 不算）。
  - [ ] 驗收：`python -m pyflakes engine/` 沒有 unused import。
  - [ ] 驗收：儀器四項全過。測試綠。

- [ ] **階段 2：消平行路徑**
  - [ ] 每一條一個 commit，commit 訊息說收了哪一條。
  - [ ] 驗收：`grep -rn "honor the same\|exactly like compare\|same as export" engine/` 為零（提醒人肉同步的註解沒有存在的理由了）。
  - [ ] 驗收：`grep -rn "len(.*) > 2" engine/` 為零；`grep -rn "context\['effective_type'\]\|context.get('effective_type'" engine/` 為零；`grep -rn "def _name\|def _kind\|def _children\|def _parent_o\|def _obj_label" engine/` 為零。
  - [ ] 驗收：測試涵蓋「export 與 compare 對同一個物件回同一個 `(eff_type, is_xml, rel_path)`」「`sync_files` 跳 `__pycache__`、dot-dir、RESERVED_FILES」「`_hash_content` 對每種 kind 的過濾規則」。
  - [ ] 驗收：儀器四項全過。棘輪數字不升。

- [ ] **階段 3：拆長函式**
  - [ ] 驗收：`perform_import_items`、`build_project`、`ensure_folder_path` 各在 60 行內；新函式全部在 40 行、3 層內（寫一個 AST 小腳本量，放 `tools/`）。
  - [ ] 驗收：`grep -n "^\s*#.*\(def \|if \|for \|return \)" engine/entry_build.py` 沒有註解掉的程式碼。
  - [ ] 驗收：`locate_message` 有 CI 測試。
  - [ ] 驗收：儀器四項全過。

- [ ] **階段 4：顯式傳遞**
  - [ ] 驗收：`grep -rn "import __main__\|sys.modules" engine/` 為零；`grep -rn "def resolve_projects\|def resolve_system\|def resolve_online\|_resolve_primary_project" engine/` 為零。
  - [ ] 驗收：`cds/ide/silent.py` 裡沒有 `_ui_patches`、`_install`、`UI_MODULE`；`tests/test_layering.py` 的例外登記為零。
  - [ ] 驗收：`--target` 形式對看門人跑 export（用 `tools/headless_watch.py` 起一個自己的看門人，不碰使用者的），`needs_input` 與 `-y` 的行為跟開工前一樣（`tests/test_silent.py` 全綠）。
  - [ ] 驗收：儀器四項全過。

- [ ] **階段 5：邊界已浮現的拆分與收尾**
  - [ ] 只拆第 4 節第五層說的那種；每拆一個檔一個 commit。
  - [ ] 驗收：`wc -l engine/codesys_utils.py` 比開工前少，且沒有新檔超過 400 行。
  - [ ] 驗收：棘輪表的每個數字不高於開工前，第 3 節 18 條的三個具體傷害各有一條測試。
  - [ ] 驗收：儀器四項全過；熱機三個中位數跟基線比，慢不超過一成，數字寫進第 6 節與 SPEC 第 7 節。
  - [ ] CHANGELOG Unreleased 加一段。
  - [ ] 沒有殘留的 IDE 行程；`%TEMP%\cdsint-work\engine\` 清掉（基線清單留一份在 `docs/history/` 若監督者要）。

---

## 6. 回報格式

同 `SETTINGS_PLAN.md` 第 6 節，加上每一層的儀器結果表：層、hash diff 行數、discover 三個數字、verify exit、三個中位數秒數。

---

## 7. 未決事項與裁決

`Ruling: 決定 — 理由 — 錯了的代價`。

先列出來的：

1. `PouType` 四招留哪一招：真 IDE 裡實測。
2. `sync_files` 的略過規則以哪一份為準：預設以 `scan_new_disk_files` 的為準（最完整），`cleanup_orphaned_files` 從此也跳 `__pycache__` 與 RESERVED_FILES；這是行為改變但方向是更安全。
3. `_hash_content` 的檔名 fallback 要不要留：預設留，加一條註解說明是哪種 kind 會走到，並加測試釘住。
4. 第五層拆哪些檔：做完前四層再決定，寫回這裡。
5. `codesys_ui.py` 的 `clr.AddReference` 假容錯：預設改成 import 失敗就 raise 一句人話，因為沒有 WinForms 的 IDE 側本來就跑不了。

做的時候看到但不在範圍的：

- （worker 填）

---

## 8. 接手 prompt

你在 `C:\Users\qazsskevin\Documents\repo\cdsint-engine`，分支 `ticket/engine`。先讀 `docs/WORKER_RULES.md`（尤其儀器那節）、本工單第 0 到 4 節、`PRINCIPLES.md` 全文、`CLAUDE.md`、`docs/SPEC.md` 的 D5、D11、D12、D13、D15、4.5、6.1、第 7 節。然後從第 5 節第一個沒打勾的項目開始做，階段照順序，每一層做完先跑儀器再 commit。hash 清單 diff 不為空就停在那一層，把 diff 寫進第 7 節，回報。決定了第 7 節的事就寫回。全部做完照第 6 節回報，停下來，不要 merge、不要 push。
