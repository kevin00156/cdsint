# 工單 D：文件與測試衛生

> 建立日期 2026-09-06。分支 `ticket/hygiene`，worktree `C:\Users\qazsskevin\Documents\repo\cdsint-hygiene`。
> 鐵律在 `docs/WORKER_RULES.md`，先讀它。使用者不在也不會回答，卡住寫進最後回報。
> 這是四張工單的第三張，在 `history/PLUMBING_PLAN.md` 合進 `main` 之後才開工。第 3 節的行號以 2026-09-06 晚上的 `631259b` 為準，A 和 B 做完會漂，開工先重核。

---

## 0. 本工單專屬的鐵律

- 臨時檔在 `%TEMP%\cdsint-work\hygiene\` 底下。
- 這張工單沒有行為改動。任何 `engine/`、`cds/`、`cdsint/` 的非註解改動都不在範圍，看到記第 7 節。
- `docs/history/` 裡的東西是當天的紀錄，不改內容，只搬。

---

## 1. 目標與範圍

同一個事實在三到五個地方用三到五種說法存在，而且已經互相打架：stub 幾行三份文件三個數字、`list` 收不收 `--target` 兩份文件同一個錯、鎖檔誰清、SPEC 的「現況」有七條是 9 月 5 日早上的快照。測試那邊，假 IDE 物件抄了幾十份，兩支本 repo 寫的測試檔超過硬上限一點五到二點七倍，規則守到了引擎沒守到自己。

做完之後：grep 得到的每個數字和檔名都對；文件裡只有不會過期的東西；一份假物件；每個測試檔在上限內。

明確不做：改任何程式行為；改 SPEC 的規則本文（只刪現況、搬第 10 節）；重寫 CHANGELOG 舊段落（只併 Unreleased）。

---

## 2. 使用者定案的決定（2026-09-06）

| # | 決策 | 選擇 | 理由 |
|---|---|---|---|
| 1 | SPEC 的「現況」欄 | 整欄刪掉；第 10 節搬去 `docs/history/` | 設計上必然過期的欄位遲早講不同的話；「做到哪」由 git log 和 CHANGELOG 回答 |
| 2 | 鐵律與已完成的工單 | 鐵律只有 `docs/WORKER_RULES.md` 一份（監督者已建）；做完的工單搬去 `docs/history/`（`CDSINT_PLAN.md`、`FOLLOWUP_PLAN.md` 監督者已搬） | Ruling 是決策紀錄，做完就是歷史 |
| 3 | 第 4 節那八條 | 全收 | 每一條都是 grep 得到就能驗的，沒有一條改行為 |

---

## 3. 接手前必須知道的現況事實

**文件互相打架的地方**

1. `docs/SPEC.md` 第 7 行表頭說「各條『現況』指的是來源 repo 的狀態」，底下 32 條現況多數已改成「已做（階段 N）」指本 repo。已確認為假的：D1（69 行「本 repo 剛 init」）、D3（79 行「選單有十一項」）、D9（110 行「CLI 叫 cds-ide」）、5.1（243 行「現在的 codesys_*.pyw」）、6.1（317 行同句）、6.3（337 行「現有 cli/cds_ide.py」）、第 8 節（481 行說 PRINCIPLES 要改寫，早已改；488 行「389 個」，實際 948）。A 的 commit 已經把 D8、D10、4.2、4.4、6.5、6.7 改寫成沒有現況的樣子，其他條照那個樣子做。
2. `readMe.md` 188 行與 `docs/SPEC.md` 167 行都說 `list` 收 `--target`，`cdsint/flags.py` 73 行沒給，實跑 `cdsint list --target foo` 回 unrecognized arguments。
3. stub 行數：`readMe.md` 485 行「fifteen-line」、SPEC 251 與 300 行「各十行」、SPEC 514 行「各十行」、`CHANGELOG.md` 140 行「ten-line」；實際 17、17、15。
4. `CHANGELOG.md` 有兩段 `### Unreleased`（7 行與 276 行）。第二段用搬家前的名字：`cli/cds_ide.py`、`%LOCALAPPDATA%\cds-text-sync\instances`、`docs/WATCHER_CLI_PLAN.md`、「Tests: 301」。第一段內部 118 行說 `tools/perf_probe.py`，259 行說 `tools/Project_perf_probe.py`。未收錄但使用者看得到的：`f05a233`（`--force-lock` 之後被 kill 的鎖檔不再由 cdsint 清，只清「啟動前不存在」的；readMe、`AI_WORKFLOW.md` 275 行、SKILL.md 166 行只說「會自己清掉」）與 `06394cf`、`71be709`（CI 雙 OS）。
5. `PRINCIPLES.md` 14 到 16 行說搬來的檔案「都在第一個 commit 進來」；第一個 commit `69106ff` 只有 spec、工單、授權，程式碼是第二個 commit `5c96d4e` 進的。111 行說 bare except「約一百」，棘輪表是 70。
6. `profiles/default.json` 3 行的 description 說「run Project_discover.py」，那支已經是 `cdsint discover`。`alias_notes` 用 `"dut[1]"` 這種清單索引當鍵，插一個 GUID 註解就無聲指錯，沒有測試看它。kind 名稱除了 `guid_aliases` 之外還手抄在 `engine/codesys_constants.py` 182 行（`EXPORTABLE_KINDS`）與 229 行（`XML_KINDS`），新增一個 kind 到 JSON 不會自動匯出；SPEC 4.5 把「47 種」寫死。
7. `docs/history/WATCHER_CLI_PLAN.md` 240 行「PRINCIPLES §9」應為 §10；`REWORK_PLAN.md` 50 行「兩層」對上現在的「三層」。history 不改，但說明「用編號引用規則跟用行號引用代碼一樣會漂」。
8. 「別用 `os.kill(pid,0)`」出現在 `docs/WATCHER.md` 52 行、`cds/core/instances.py` 7 行、`WATCHER_CLI_PLAN.md` 166 行、`PHASE2_PLAN.md` 26 行，四處（`CDSINT_PLAN.md` grep 不到，工單原本寫五處是錯的）。

**測試**

9. 假 IDE 物件（2026-09-06 開工當天重數）：`Projects` 六份、`Project` 六份、`Node` 六份、`Info` 五份、`DeafUI` 五份、`DeafSystem` 四份、`FakeSystem` 三份、`fake_codesys_ui` fixture 兩份、`FakeRunner`×2、`FakeTimer`×2（兩個對同一個 .NET Timer 的假物件介面不同：toast 版用 `.Interval` 與 `Tick +=`，watcher 版用建構子收 `(interval, handler)`）、`_StubManager`×2（都是巢狀在測試類別裡的）。四支測試檔 `from tests.test_watcher import`（`test_cli`、`test_display`、`test_headless` 各一，`test_headless` 連 `FakeSystem` 一起拿），`tests/` 沒有 `__init__.py`，靠根目錄 `conftest.py` 塞 sys.path。
10. 本 repo 寫的、超硬上限的測試檔：`tests/test_plc.py` 1131 行（首次進 repo `6fdb619`）、`tests/test_headless.py` 657 行（`7b2e70b`）、`tests/test_verify.py` 409 行（`7b2e70b`，工單寫的時候還在 400 以內，開工當天已經超過）。搬來的（`test_call_tree` 692、`test_watcher` 563、`test_silent` 509）豁免。
11. `tests/test_silent.py` 389 到 400 行 `DRIVEN_FILES` 寫死十個引擎檔名；SPEC 6.1 自己說「10.1 搬檔案時要跟著改」。加一支新的 `entry_*.py` 忘了登記，它開的對話框在 silent 模式下是「unexpected dialog」而測試全綠。`engine/` 現在有 19 支非 `__init__` 的 `.py`，清單只認十支。
12. `tests/test_call_tree.py` 16 行在 import 時把 `tools/` 塞進 `sys.path[0]`。`tests/test_headless.py` 210、211、215 行非 raw 字串裡的 `"D:\what-ran"`、`"D:\what-was-asked"`（工單原本寫 170 行的 `"D:\sync"`，已改名），Python 3.12 起是 SyntaxWarning，WSL 的 3.10 已經在報。`tests/conftest.py` 的 `load()`、`load_engine` 只是 `importlib.import_module("engine." + name)` 的包裝，docstring 自己承認是過渡。
13. `tests/test_ide_round_trips.py` 的讀取計數是有意識的實作釘（PRINCIPLES 3），不動。`tests/test_bare_excepts.py` 27 到 32 行的棘輪設計是好的，不動；表頭「What is left, 2026-09-05」是一個會漂的日期。

**工具**

14. `tools/` 五份 sys.path bootstrap、三種寫法（`grant_plc.py` A 已刪）：`cache_doctor.py` 37 行、`headless_watch.py` 38 行、`perf_probe.py` 51 行、`probe_imports.py` 25 行各三行，變數名 `_INSTALL_ROOT` 與 `REPO_ROOT` 兩種；`probe_watcher_ui.py` 30 行把 `tools/` 塞進 sys.path 再 `import headless_watch`。`probe_imports.report_path/main` 與 `headless_watch` 的對應段落除檔名外相同。`call_tree_parse.py` 20 行把 `IMPL_MARKER` 抄成字面值配一行「Must match IMPL_MARKER in engine/codesys_constants.py」。
15. `readMe.md` 445 到 474 行與 SPEC 5.1 258 行只認 `call_tree`、`cache_doctor`、`perf_probe`；`tools/` 有九支 `.py`。`probe_imports.py` 沒有活文件、測試、skill 引用。`probe_click_menu`、`probe_watcher_ui` 由 WATCHER.md 第 8 節引用，`headless_watch` 由 SPEC D5 與 `cds/ide/headless.py` 引用。
16. 沒有 `from __future__ import print_function` 的是六支：`cache_doctor.py`、`call_tree.py`、`call_tree_parse.py`、`call_tree_resolve.py`、`perf_probe.py`、`probe_watcher_ui.py`（工單原本寫兩支，只算了在 IronPython 2.7 內跑的那兩支；把 `tools/` 整個掃進去就是六支都要補）。`tests/test_print_function.py` 24 行只掃 `engine`、`cds/ide`、`cds/core`、`stub`，`test_single_threaded_ide_side.py` 15 行也明寫排除 tools。
17. 搬來的長函式：`cache_doctor.main` 176 行、`call_tree_resolve._resolve_calls` 104 行、`perf_probe.build_report` 105 行與 `main` 87 行、`call_tree_parse._blank_comments` 61 行。豁免，但 PRINCIPLES 2 說碰到的函式不能變長；`cache_doctor` 搬來後改過四次。

**開工前重核清單（2026-09-06 做完，`25cafe7`）**

- [x] 第 1 到 8 條逐條 grep 確認還在。八條全部還在，行號漂了一批，上面已改成開工當天的值。第 8 條原本寫五處，實際四處。
- [x] 第 9 條重數一次。份數變了，上面已改。
- [x] 第 14 條 `grant_plc.py` 已不在，bootstrap 從六份變五份。
- [x] 測試基線重跑：Windows `python -m pytest tests -q` 1043 passed；WSL Ubuntu-22.04 `python3 -m pytest tests -q` 1043 passed。這是階段 3「測試總數不少於開工前」要比的數字。

第 7 節的 Ruling 2 在重核的時候就有答案了（真的有第三種 kind），寫在那裡。

---

## 4. 設計

1. **SPEC。** 每一條「現況：」開頭的段落刪掉，連同「已做（階段 N）」這類句子；D 編號的決策只留決定與理由。第 7 節的相容性矩陣與 perf 基準是量測紀錄，留著但表頭標日期。第 10 節整節搬到 `docs/history/SPEC_10_CONSTRUCTION.md`，SPEC 只留一句指過去。第 8 節的「389 個」那類數字刪，「PRINCIPLES 要改寫」那段刪。第 7 行表頭改寫。第 0 節 15 行「`cds-sync-` 是它底下同步功能的屬性前綴」A 已改。
2. **CHANGELOG。** 兩段 Unreleased 併成一段，舊名字全改成今天的；`perf_probe` 兩個名字改成一個；補 `f05a233` 那條鎖檔規則與 CI 雙 OS。readMe、`AI_WORKFLOW.md` 479 行、SKILL.md 758 行的鎖檔說法對齊 `f05a233`。
3. **PRINCIPLES。** 14 到 16 行的分級判準改成寫 commit hash `5c96d4e`；111 行「約一百」改成指向 `tests/test_bare_excepts.py` 的表，不寫數字。
4. **數字與檔名。** stub 行數三處刪數字，只說「三支 stub」；`list --target` 兩處改成不收；`profiles/default.json` 的 description 改成 `cdsint discover`；`alias_notes` 改成用 GUID 當鍵，並加一條測試：每個 `alias_notes` 的鍵都在 `guid_aliases` 的某個清單裡。SPEC 4.5 的「47 種」改成不寫數字。`EXPORTABLE_KINDS`、`XML_KINDS` 跟 `guid_aliases` 的關係加一條測試：`guid_aliases` 裡的每個 kind 要嘛在 `EXPORTABLE_KINDS`、要嘛在 profile 的 `sync_direction` 標 `disabled`，不准第三種（這條若發現真的有第三種，記進第 7 節不改程式）。
5. **一份假物件。** `tests/fakes.py`：`Project`、`Projects`、`Info`、`Node`、`DeafSystem`、`DeafUI`、`FakeTimer`、`make_globals`。每個測試模組只 import 它，`from tests.test_watcher import` 消失。`FakeTimer` 一個介面，兩邊測試都用它。`test_call_tree.py` 的 `sys.path.insert` 改成 fixture 內 monkeypatch。`tests/conftest.py` 的 `load`、`load_engine` 刪，呼叫端改直接 import。`"D:\sync"` 改 raw。
6. **測試檔尺寸。** `test_plc.py` 切成 `test_plc_link.py`、`test_plc_trip.py`、`test_plc_crc.py`、`test_plc_cli.py`，對應引擎那四支加 CLI；`test_headless.py` 切成 `test_headless_ide.py` 與 `test_headless_cli.py`。每支在 400 以內，目標 300。
7. **`DRIVEN_FILES`。** 改成掃 `engine/` 目錄底下每支 `.py`，只列排除清單（現在只有 `settings.py`，註解已說理由）。
8. **工具。** bootstrap 收成 `tools/_root.py` 一份（三行，其他檔 `import _root` 或同等做法，IronPython 2.7 跑得動）；`answers`、`report_path` 各一份放 `tools/_probe.py`；`call_tree_parse` 改 import `IMPL_MARKER`；`probe_imports.py` 刪；`test_print_function` 與單執行緒那條測試把 `tools/` 掃進去，兩支缺 `print_function` 的補上；readMe 的 `tools/` 一節列出每一支和一行用法，SPEC 5.1 那句跟著改。
9. **鐵律五處。** `WATCHER.md` 52 行與 `instances.py` 7 行留（一處規格、一處程式碼註解說為什麼），其他三處在 history 不動。

---

## 5. 分階段與驗收

- [x] **階段 0：重核與基線**
  - [x] 第 3 節重核清單做完，commit。
  - [x] 驗收：Windows 1043 passed、WSL 1043 passed，記在第 3 節重核清單末尾。

- [x] **階段 1：文件（第 4 節 1 到 4、9）**
  - [x] 驗收：`grep -n "現況" docs/SPEC.md` 為零；`grep -n "階段 [0-9]" docs/SPEC.md` 為零；`docs/history/SPEC_10_CONSTRUCTION.md` 存在。
  - [x] 驗收：`grep -c "^### Unreleased" CHANGELOG.md` 是 1。`grep -n "cds_ide\|cds-text-sync\\\\instances\|Project_perf_probe\|Tests: [0-9]" CHANGELOG.md` 在 Unreleased 段落裡還有兩筆，都是「舊名字改成新名字」的句子，見第 7 節 Ruling 4。
  - [x] 驗收：`grep -rn "fifteen-line\|ten-line\|各十行" readMe.md docs/SPEC.md CHANGELOG.md` 為零；`list` 在 readMe 與 SPEC 的命令表都改成兩種形式都不收，對上 `flags.py` 的 `NO_IDE`。
  - [x] 驗收：`grep -n "first commit\|about a hundred" PRINCIPLES.md` 為零。
  - [x] 驗收：`tests/test_doc_links.py` 綠（14 passed）；整份測試 1043 passed。

- [x] **階段 2：profile 與工具（第 4 節 4 的 profile 部分、8）**
  - [x] 驗收：`grep -n "Project_discover" profiles/default.json` 為零；新測試「`alias_notes` 的鍵都是 `guid_aliases` 裡的 GUID」綠（`tests/test_profile.py::TestAliasNotes`，兩條）。`alias_notes` 改成 GUID 當鍵，原本那則講 `legacy_kind_names` 的註解搬到平行的 `legacy_kind_names_note`，這樣 `alias_notes` 每一個鍵都是 GUID，測試不需要例外。
  - [x] 驗收：`grep -rn "IMPL_MARKER = " tools/` 為零，`call_tree_parse.py` 改成 import；`probe_imports.py` 已刪（它自己那份 MODULES 清單也早就漏了 `entry_discover`、`statusform`、`core.settings` 這幾支）。`grep -rn "sys.path.insert" tools/` 是五處不是一處，理由見第 7 節 Ruling 5。
  - [x] 驗收：`test_print_function.py` 掃到 `tools/` 且綠（53 passed）。單執行緒那條的範圍見 Ruling 7。
  - [x] 驗收：readMe 的 `tools/` 一節列出每一支，而且由 `tests/test_tools_are_documented.py` 兩條測試守著，不再是一次性的 grep。

- [x] **階段 3：測試（第 4 節 5 到 7）**
  - [x] 驗收：`grep -rn "^class \(Projects\|Info\|Node\|DeafSystem\|DeafUI\|FakeTimer\)\b" tests/` 只在 `tests/fakes.py`；`grep -rn "from tests.test_" tests/` 為零。要多做一點的測試改成子類別化並以行為命名（`RemovableNode`、`WalkCountingNode`、`ReadCountingNode`、`DeviceNode`），所以一個叫 `Node` 的東西永遠是共用那一個。
  - [x] 驗收：本 repo 寫的每支測試檔都在 400 以內，最大的是 `tests/plc_fakes.py` 315。切的份數見第 7 節 Ruling 9。
  - [x] 驗收：`DRIVEN_FILES` 改成 `driven_files()`，掃 `engine/` 目錄、只維護排除清單（現在只有 `settings.py`）。掃到 17 支，原本寫死十支。
  - [x] 驗收：`python -W error::SyntaxWarning -m pytest tests -q` 綠。
  - [x] 驗收：Windows 1072 passed、WSL 1072 passed，開工前是 1043。

- [x] **階段 4：收尾**
  - [x] CHANGELOG Unreleased 加了一段，說文件與測試整理過、改了哪些會過期的東西。
  - [x] `%TEMP%\cdsint-work\hygiene\` 從頭到尾沒有建過，所以沒有東西要清。那個目錄底下現有的 `import-bug`、`importbug2` 不是這張工單的，沒碰。
  - [x] 順手：`tests/test_bare_excepts.py` 表頭的「What is left, 2026-09-05」把日期拿掉了。第 3 節第 13 條說棘輪的設計不動，那沒動；拿掉的是註解裡那個會漂的日期，而 `PRINCIPLES.md` 現在指著這張表當唯一的數字來源。

---

- [ ] **階段 5：審查後修正（監督者 2026-09-07 派回）**

  一個沒看過對話的 reviewer 把 SPEC、readMe、AI_WORKFLOW、WATCHER、SKILL、CHANGELOG 從頭讀到尾，對照程式碼，找到十九處還在說假話或互相打架的地方，加上假物件沒收乾淨。監督者抽驗過。這張工單的目標就是「文件全對、一份假物件」，所以全部修。修完照第 6 節再回報一次。

  **文件還在說假話的**
  - [ ] **1.** `docs/SPEC.md` 5.1 與 6.1 兩句「現在的 `codesys_*.pyw`」：repo 沒有任何 `.pyw`。工單第 3 節第 1 條自己點名了這兩句，第 4 節說要改，沒改。改成講今天的 `engine/*.py`。
  - [ ] **2.** `CHANGELOG.md` Unreleased 段 PLC 那條還說「the project property `cds-sync-plc` … `config set` refuses to write that one property」；同一段前面已經說 `config` 刪了、設定在文字檔。改成講設定檔的 `plc` 清單加 `-y`。
  - [ ] **3.** `CHANGELOG.md` 另一條「`cds-sync-version` is written before the project is saved」：版本戳記已刪。這條描述的是已經不存在的機制，整條刪，或改成一句「版本戳記連同它的存檔順序問題一起刪了」。Ruling 4 的豁免是「以前叫什麼、現在叫什麼」，這兩條不是，是用舊機制描述現在。
  - [ ] **4.** `docs/SPEC.md` 6.4 那張表的鎖檔規則還是 `f05a233` 之前的：「自己起的 IDE 留下的鎖檔由 CLI 清掉」無條件；程式是開跑前有鎖就不清。工單只對了三份使用手冊，沒對規則本文。照 `cdsint/headless.py` 和 `lock.py` 的實際行為改寫。
  - [ ] **5.** `readMe.md` 274 到 276 行「`--project` therefore requires `--sync-dir`」：同檔前面、SKILL、AI_WORKFLOW、SPEC 都說選用。改。
  - [ ] **6.** `docs/AI_WORKFLOW.md` exit 5 那格說「要人去 IDE 裡改屬性，見第 6 節」，第 6 節說的是設定檔的鍵。改成一致。
  - [ ] **7.** `docs/WATCHER.md` 命令表說 compare 的逐物件清單進 `stdout_tail`，AI_WORKFLOW 和 SKILL 說在 `data.changes`，程式是後者。WATCHER 改。
  - [ ] **8.** `docs/WATCHER.md` 命令檔例子還帶 `"force": false`，`--force` 已刪；同節「專案屬性擋下 `plc`」是屬性時代的話。兩處改。
  - [ ] **9.** `docs/SPEC.md` 6.4 指向 `tools/codesys_probe.py`，不存在。改成講它從哪搬來、現在在哪。
  - [ ] **10.** `docs/SPEC.md` D5 說單執行緒那條測試只 parse 三個目錄；Ruling 7 之後也掃 `tools/` 裡會載進 IDE 的。補一句。
  - [ ] **11.** `docs/SPEC.md` 4.3 exit 4 那格補「`--install` 對不到任何 IDE」，程式、readMe、SKILL 都有。
  - [ ] **12.** 「兩支」還是「三支」：`readMe.md` 說 tools 裡三支在 IDE 內跑，`tests/test_print_function.py` docstring 和 `CHANGELOG.md` 說兩支。以程式碼為準，三處改成一致，或不寫數字。
  - [ ] **13.** `readMe.md` tools 那節「the underscore is what keeps it out of this list」寫在把 `_root.py` 列進去的那條裡。二選一。
  - [ ] **14.** `tools/call_tree_parse.py` 改成 import `IMPL_MARKER` 之後，`engine/codesys_constants.py` 在 import 時就讀並驗證 `profiles/default.json`，這支原本只靠標準函式庫的離線工具現在綁死 repo 佈局。監督者裁決（第 7 節末尾）：留 import，但 readMe 那句「Import them if you want the pieces」改成講它要從 repo 的 checkout 跑，CHANGELOG 補一句。
  - [ ] **15.** `profiles/default.json` 多了 `alias_notes_note`、`legacy_kind_names_note` 兩個頂層鍵，`PROFILE_HASH` 因此變了，每個人的 `sync_cache.json` 下一趟重建一次、第一趟 export 慢兩三倍。留著可以，但 CHANGELOG 要寫一句，不然使用者不知道為什麼慢。

  **假物件與測試**
  - [ ] **16.** 沒收乾淨的替身：`Project` 在 `tests/test_build_application.py` 頂層一份同形、`tests/test_delete_order.py` 一個叫 `Project` 的 Node 子類、`test_ide_round_trips.py` 三份巢狀；`FakeSystem` 在 `plc_fakes.py` 與 `test_silent.py`；`_StubManager` 在 `test_kind_pragma.py` 與 `test_member_creation.py` 完全相同；`Session`、`Online` 在 `plc_fakes.py` 與 `test_online_preflight.py` 各兩份。全部收進 `tests/fakes.py`（或 `plc_fakes.py`），子類別化的留子類別但不重抄本體。第 5 節階段 3 的 grep 驗收把 `Project`、`FakeSystem`、`_StubManager`、`Session`、`Online` 加進去重跑。
  - [ ] **17.** `tests/test_call_tree.py` docstring 說 fixture 的 monkeypatch 讓 `tools/` 不會永久留在 `sys.path`，但 `call_tree_parse.py` import 時無條件 insert，第一條測試之後就永久在。改 docstring 講真的，或讓 fixture 真的做到。
  - [ ] **18.** 五支 tools 的 bootstrap 註解「Neither is on sys.path already」在 `python tools/x.py` 下是假的，只在 IDE 裡才真；`probe_watcher_ui` 經 `headless_watch` 會 insert 兩次。註解改成講清楚兩種情況，insert 改成先查再加。
  - [ ] **19.** 「十一個鍵」手抄五份（SPEC 兩處、AI_WORKFLOW 兩處、CHANGELOG 一處）。今天對，但跟被刪的「47 種」同一個形狀。改成不寫數字，或只留 SPEC 4.4 那張表一處。

  - [ ] 驗收：`grep -n "pyw\|codesys_probe" docs/SPEC.md` 為零（第 0 節那格 `pywebview` 是別人的東西，不算）。
  - [ ] 驗收：`grep -n "config set\|cds-sync-version\|cds-sync-plc" CHANGELOG.md` 只剩「以前叫什麼」那種句子，reviewer 點名的兩條不在。
  - [ ] 驗收：`grep -rn "requires \`--sync-dir\`\|\"force\"" readMe.md docs/ skills/ | grep -v history` 為零。
  - [ ] 驗收：`grep -rn "^class \(Project\|Projects\|Info\|Node\|DeafSystem\|DeafUI\|FakeTimer\|FakeSystem\|_StubManager\|Session\|Online\)\b" tests/` 只在 `tests/fakes.py` 與 `tests/plc_fakes.py`。
  - [ ] 驗收：`python -m pytest tests -q` 與 WSL 綠，數目不少於 1072；`tests/test_doc_links.py` 綠。

---

## 6. 回報格式

同 `history/SETTINGS_PLAN.md` 第 6 節。這張沒有真 IDE 驗收。

---

## 7. 未決事項與裁決

`Ruling: 決定 — 理由 — 錯了的代價`。

先列出來的：

1. `docs/history/SPEC_10_CONSTRUCTION.md` 要不要連 SPEC 第 7 節的 perf 表一起搬。預設：不搬，基準表是「現在的數字」，SPEC 11.1 的速度引擎決定要對著它比。
2. **Ruling：真的有第三種 kind，所以第 4 節 4 那條「不准第三種」的測試不寫 — 那條規則本身是錯的，不是程式碼錯了。**
   理由：`guid_aliases` 的 47 種裡，有十種既不在 `EXPORTABLE_KINDS` 也沒有在 `sync_direction` 標 `disabled`：`application`、`folder`、`image`、`plc_logic`、`project_info`、`recipe`、`recipe_manager`、`target_visu`、`task_call`、`web_visu`。它們認得出來是為了讓 `discover` 不要把它們報成 unknown GUID，但它們本來就沒有可匯出的內容 — `folder`、`application`、`plc_logic`、`project_info` 是容器，`web_visu` 與 `target_visu` 是 `visu_manager` 遞迴匯出的子節點（`EXPORTABLE_KINDS` 的註解自己寫了）。而且那條規則連互斥都不成立：`device` 與 `device_module` 同時在 `EXPORTABLE_KINDS` 裡也標了 `disabled`。
   錯了的代價：照原規則寫測試，開工第一天就紅十筆，而唯一的修法是把十個不該匯出的 kind 塞進 `EXPORTABLE_KINDS`，那會改行為，而這張工單明文不改行為。留給 C：真要有一條測試守這三者的關係，得先定義出第三類（「認得但沒有內容」）是什麼，那是設計工作不是衛生工作。
3. `tests/fakes.py` 收進去之後若某個測試靠替身的某個怪行為，寧可在那個測試裡子類別化，不要把怪行為加進共用替身。

4. **Ruling：CHANGELOG 的 Unreleased 段落裡留下兩處舊檔名，所以階段 1 那條 grep 驗收有兩筆命中，不是零。**
   決定：留著不改。兩處分別是「`Project_perf_probe.py` is `tools/perf_probe.py`」與「replacing `python cli/cds_ide.py`」。
   理由：那條驗收要擋的是「用搬家前的名字描述今天的東西」，而這兩句的整個作用就是講「以前叫什麼、現在叫什麼」。把舊名字拿掉，改名這件事就無從查起，升級的人會找不到自己手上那支檔案去哪了。刪掉的是資訊，不是過期的東西。
   錯了的代價：以後有人照那條 grep 驗收，會看到兩筆命中而以為沒做完。所以寫在這裡。

5. **Ruling：`tools/` 的 sys.path bootstrap 收不到一處，是五處：`_root.py` 一處，另外四支各一行。**
   決定：`tools/_root.py` 擁有「install root 在哪」這個知識；每一支要用的工具開頭兩行完全相同 — 先把自己的目錄放上 sys.path，再 `import _root`。
   理由：`import _root` 要能成功，`tools/` 本身得先在 sys.path 上，而在 IDE 裡不會。ScriptEngine 是把檔案交給 IronPython 執行，sys.path 是 IDE 自己的搜尋路徑，不含腳本所在目錄 — `stub/` 底下三支自己插路徑就是同一個理由。所以那一行是 `import _root` 的前提，不是重複的 bootstrap。真正會漂的知識（root 是往上一層）現在只有 `_root.py` 一份，變數名也從 `_INSTALL_ROOT` 與 `REPO_ROOT` 兩種收成一種。
   順手修掉一個：`probe_watcher_ui.py` 以前只把自己的目錄放上 sys.path，然後靠 `import headless_watch` 的副作用把 install root 插進去，才輪得到下一行 `from cds.core import settings`。import 順序變成承重的，而且沒有一個字說明。現在它自己 `import _root`。
   錯了的代價：`grep -rn "sys.path.insert" tools/` 是五筆不是一筆。

6. **Ruling：`tools/_probe.py` 不建。**
   理由：工單寫這條的時候 `answers` 與 `report_path` 各有兩三份。A 刪掉 `grant_plc.py`、這次刪掉 `probe_imports.py` 之後，`answers` 只剩 `headless_watch` 一份，`report_path` 一份都不剩。為了一個唯一的呼叫端開一個共用模組，就是 PRINCIPLES 10 說的「一個子類別的基底類別不是抽象，是兩個檔做一個檔的事」。
   錯了的代價：以後真的第三次抄到 `answers`，得有人記得這裡曾經想收。所以寫下來。

7. **Ruling：`test_print_function` 把整個 `tools/` 掃進去（六支補上 `__future__`），但 `test_single_threaded_ide_side` 只掃「會 import 進 IDE 的」那幾支。**
   理由：兩條規則的代價不對稱。多一行 `from __future__ import print_function` 對純 CPython 的工具沒有任何成本，所以那條可以沒有例外。併發那條不行：`probe_click_menu.py` 是唯一一支從 IDE *外面* 用 Win32 真實點擊來驅動 IDE 的工具，`time.sleep` 在兩次點擊之間是它的方法本身，不是違規。用目錄一刀切會把它判成紅的。
   判準不寫死檔名，用問的：一支檔 import 得到 `engine`、`cds` 或 `_root`，就是會載進 IDE 的。`_root` 也算，因為 `perf_probe.py` 用字串名字 `__import__("engine." + name)` 進引擎，AST 看不到。這個判準寧可多掃（`cache_doctor.py`、`call_tree_parse.py` 被掃進去，它們本來就沒有 sleep），也不要漏掉一支真的跑在訊息迴圈上的。
   D5 的那一個例外（`headless_watch.park()` 的 `system.delay()`）在測試裡登記成一筆，同一個檔第二筆 `delay()` 還是紅的 — 跟 `test_layering.py` 登記 `silent.py` 那個 `__import__` 同一個做法。

8. 給 C：`PROFILE_HASH` 是 `profiles/default.json` **整份原始文字**的 CRC，所以改一句 `description` 或一則 `alias_notes` 註解，全世界的 `sync_cache.json` 都會被丟掉重建一次。這次改 profile 的註解就觸發了。改註解會讓使用者的下一趟慢一輪，這不對；但改成只 hash 會影響分類的那幾個鍵是行為改動，不在這張工單裡。

9. **Ruling：測試檔切成的份數比工單寫的多，因為工單的 400 行上限比它寫的檔名重要。**
   `test_plc.py` 1131 行切成五支加一份共用替身，不是四支：`test_plc_permit.py`（兩道門）、`test_plc_cli.py`（命令列與退出碼）、`test_plc_trip.py`（一整趟與判決）、`test_plc_link.py`（連到哪台、用誰的帳密）、`test_plc_crc.py`（`plc_crc` 自己），共用的 IDE 替身與 fixture 在 `tests/plc_fakes.py`。權限那一支是工單沒列的第五支，理由是 `cds/ide/permit.py` 是一個真的模組，照它命名比硬塞進別支清楚。
   `test_headless.py` 657 行切成三支加一份 fixture：切成兩支的話 CLI 那半是 456 行，硬上限就破了。`test_headless_cli.py` 是「決定要起什麼」，`test_headless_result.py` 是「起完之後怎麼讀回來的東西」，共用的 fixture 在 `tests/headless_fakes.py`。
   工單沒提但開工當天已經超過 400 的 `test_verify.py`（409）也切了：`test_verify.py` 留驗證那四步，`test_cli_surface.py` 收命令列表面與 `COMMANDS` 表，共用的 `FakeRunner` 在 `tests/cli_fakes.py`。
   兩個 `FakeRunner` 沒有合成一個：`test_verify` 那個照命令查表回答並在失敗時停下，`test_plc_cli` 那個不管問什麼都回同一筆。合成一個就要有兩種模式，那正是第 3 條說不要做的事。
   錯了的代價：檔名跟工單第 4 節 6 寫的對不上，所以寫在這裡。

10. **Ruling：`tests/conftest.py` 的 `load_engine` 刪掉了，但各測試檔自己的模組 fixture（`utils`、`env`、`managers`）留著。**
    理由：要拔掉的是「用字串名字繞過 import」那一層，那一層現在沒有了 — 每個檔案頂上是真的 `from engine import ...`。剩下的 fixture 只是那個模組在這個檔案裡的稱呼，是 pytest 正常用法。把它們也拆掉要動大約九十個測試函式的簽名，換不到任何東西。
    順帶：那些 `for dep in (...): load_engine(dep)` 的預熱迴圈全刪了。引擎模組自己 import 自己的相依（`codesys_managers` 頂上就 import 了 `codesys_utils` 與 `codesys_constants`），那些迴圈是 `imp.load_source` 時代留下的殘骸。

做的時候看到但不在範圍的，記在這裡給 C：

- （worker 填）

---

監督者裁的（2026-09-07，審查後）：

- Ruling: `tools/call_tree_parse.py` 留 `from engine.codesys_constants import IMPL_MARKER`，不改回字面值 — 分隔符只能有一個定義（D15），一個離線工具為了能被抄到別處而多養一份磁碟格式的定義是本末倒置；代價是它從此要從 repo 的 checkout 跑，readMe 講清楚就好 — 錯了的代價是有人把兩支檔抄走時得到一個講 profile 的 traceback。
- Ruling: `profiles/default.json` 的兩個 `_note` 鍵留著，`PROFILE_HASH` 變一次接受 — 那是給讀 JSON 的人看的說明，沒有別的地方放；快取重建一次是一趟慢兩三倍，不是資料風險 — 錯了的代價是 CHANGELOG 要多一句，這一輪補。

---

## 8. 接手 prompt

你在 `C:\Users\qazsskevin\Documents\repo\cdsint-hygiene`，分支 `ticket/hygiene`。先讀 `docs/WORKER_RULES.md`、本工單第 0 到 4 節、`PRINCIPLES.md`、`CLAUDE.md`、`docs/SPEC.md` 第 3 節與第 8 節、`tests/test_doc_links.py`。然後從第 5 節第一個沒打勾的項目開始做，階段照順序。一段做完、測試綠、commit；做完的項目打勾並 commit。決定了第 7 節的事就寫回。看到不在範圍的爛東西記進第 7 節末尾，不修。全部做完照第 6 節回報，停下來，不要 merge、不要 push。
