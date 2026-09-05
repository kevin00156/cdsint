# 工單：把 kevin-cds-text-sync 的程式碼搬進 cdsint 並照 SPEC 整理（階段 0 到 4）

> 建立日期 2026-09-05。本 repo `C:\Users\qazsskevin\Documents\repo\cdsint`，分支 `main`，剛 init。
> 程式碼來源是 `C:\Users\qazsskevin\Documents\repo\kevin-cds-text-sync`（分支 `fix/member-creation-parent-resolution`，commit 9aa9886），只讀。
> 使用者不在也不會回答，卡住寫進回報。
> 規格本文是 `docs/SPEC.md`。本工單不重抄規格，只寫施工順序、現況事實、驗收與裁決。
> 規則引用一律用 SPEC 的 D 編號與節號。

---

## 0. 鐵律

通用的：

- 使用者不在、不會回答。卡住就把原因寫進回報，跳過那一項，繼續同一階段的其他項目。一個階段做完就停下來回報，由監督者派下一階段。不問「要不要往下做」。
- 只碰自己開的資源：使用者開著的程式、專案、視窗一律不動；要關的程序只關自己記下 pid 的；關程序用 `Stop-Process -Id`。
- 真實資料只用副本；使用者 git 管理的資料夾一個位元組都不寫。
- 憑證由使用者自己填在本機檔案；遇到要憑證的步驟中止並記錄，繼續其他工作。
- 一段做完、測試綠、commit，再進下一段。
- 對外動作（建遠端、push、打 tag 推上去、發訊息）由人做。worker 只在本 repo 的 `main` 分支 commit。
- 儀器拿不到前景就改用非 UI 驗證並註明；桌面上無關的視窗留在原處。
- 臨時檔集中在 `%TEMP%\cdsint-work\` 底下，做完清掉。

這個任務專屬的：

- **來源 repo 只讀。** `C:\Users\qazsskevin\Documents\repo\kevin-cds-text-sync` 是使用者 git 管理的資料夾，從它複製檔案可以，往裡面寫一個位元組都不行，也不准在裡面 `git` 任何會改狀態的命令。
- **不能碰的程序：pid 14012。** 那是使用者開著的 DIADesigner-AX 1.10，專案 `Shm_2026.07.29.project`，裡面跑著舊版看門人。不准對它下 `stop` 或任何命令，不准刪它在 `%LOCALAPPDATA%\cds-text-sync\instances\` 底下的登記檔。不准用 `cds-ide` 這個 skill 或來源 repo 的 `cli/cds_ide.py` 對它下命令。
- **不能改的機器設定：五個 ScriptDir 的 junction 一律不動。** `%LOCALAPPDATA%\CODESYS\ScriptDir\cds-text-sync`、`%LOCALAPPDATA%\PLCDesigner\ScriptDir`（整個 ScriptDir 本身就是 junction）、`C:\ProgramData\PLCDesigner\ScriptDir\cds-text-sync`、兩個 Delta 安裝目錄底下的 `CODESYS\ScriptDir\cds-text-sync`，全部指向來源 repo。安裝器要驗證就對 `%TEMP%\cdsint-work\` 底下的假 ScriptDir 裝。
- **不能寫的其他資料夾：** `C:\Users\qazsskevin\Documents\repo\sample_slitter_dev`（只准讀 `scripts\codesys-probe.ps1` 與 `tools\codesys_probe.py`）；`P:\Shared\` 底下任何東西。
- **真專案只用副本：** `P:\Shared\Acme\Site\SheetSplitter\PLC\Shm_2026.07.29.project` 複製到 `%TEMP%\cdsint-work\` 底下再開。原檔正被 pid 14012 開著，直接開會撞鎖。
- **無頭 IDE 行程自己起、自己記 pid、自己關。** 逾時要 kill 只 kill 自己記的 pid，不准 `Stop-Process -Name`。

---

## 1. 目標與範圍

做 SPEC 第 10.2 節的階段 0 到 4，順序不變。每一階段結束時 `python -m pytest tests -q` 綠、commit、在本工單打勾、回報。

明確不做：

- SPEC 第 2 節列的非目標。
- 分紙機 repo 的 Makefile 改寫。階段 2 做完把要改的行寫進第 7 節，人去改。
- 建 GitHub 遠端、push、tag。
- 台架上的 PLC 下載。階段 3 只做到單元測試能證明的部分。
- 回頭改來源 repo 任何東西。

---

## 2. 已定案的決策

SPEC 第 3 節的 D1 到 D16 全部適用。本工單另外定的：

| 決策 | 選擇 | 理由 |
|---|---|---|
| 搬法 | 直接搬進 SPEC 5.1 的佈局，不先平搬再移 | 搬兩次等於每個 import 改兩次 |
| 階段 0 不改邏輯 | 只搬、只改 import 與路徑、只刪規格點名要刪的 | 搬家與改行為混在一起，測試紅了分不清是哪個 |
| git 歷史 | 從本 repo 的第一個 commit 開始，不 `git filter-repo` 也不 subtree | 來源 repo 留著就是歷史 |
| 版本號 | 階段 0 就把 `SCRIPT_VERSION` 與 `pyproject.toml` 的 `version` 都改成 `0.0.1` | 監督者裁的，見第 7 節 |
| CHANGELOG | 來源的整份搬過來，頂上加「Unreleased：搬進 cdsint」一段 | 引擎行為的歷史使用者還在依賴 |
| Python 版本 | 本機 3.14，CI 3.12，`pyproject.toml` 要求 3.11 以上 | SPEC 4.2 |
| 測試怎麼跑 | `python -m pytest tests -q` 是基準；根目錄 `python -m pytest` 也要能跑 | 來源 repo 根目錄跑會在收集階段就死 |
| 分紙機探路腳本 | 從 `sample_slitter_dev` 讀進來改寫，那邊不改 | 那是使用者的 repo |
| 現在跑著的看門人 | 不理它。實例目錄不同，新 CLI 看不到它是預期行為 | SPEC 階段 0 明寫不做遷移 |
| commit 訊息 | 英文、一句話、說為什麼不說做了什麼，跟來源 repo 慣例 | 看來源 `git log --oneline -20` |

---

## 3. 接手前必須知道的現況事實

全部是 2026-09-05 實際查過的。沒特別說的路徑與行號都是**來源 repo** 裡的。

1. **活著的實作在哪。** 來源根目錄的十一支 `Project_*.py` 是選單入口，七支 `codesys_*.pyw` 是引擎（`codesys_utils` 1906 行、`codesys_managers` 1428、`codesys_compare_engine` 1364、`codesys_ui` 643、`codesys_ui_diff` 516、`codesys_constants` 311、`codesys_online` 167）。`cds/core/` 是檔案協定（`ipc.py`、`instances.py`、`commands.py`），`cds/ide/` 是看門人（`watcher.py`、`session.py`、`silent.py`、`statusform.py`、`project.py`、`messages.py`、`display.py`）。`cli/cds_ide.py` 是 CLI，248 行。沒有骨架。
2. **測試基準。** 來源 `python -m pytest tests -q` 是 389 passed。根目錄 `python -m pytest` 收集失敗，原因是 `Project_perf_test.py` 的檔名符合 `*_test.py`，而它第 17 行 `import imp`，這個模組 Python 3.12 之後沒有。
3. **引擎模組彼此怎麼 import。** `codesys_*.pyw` 之間用裸名字（例如 `from codesys_utils import safe_str`）。入口腳本用 `_load_hidden_module` 配 `imp.load_source` 把 `.pyw` 塞進 `sys.modules`。搬進 `engine/` 套件後這些都要改成 `from engine.codesys_utils import ...` 這種形式，IronPython 2.7 與 CPython 3 都吃。
4. **profile 檔的相對路徑。** `codesys_constants.pyw` 從 `__file__` 找 `profiles/default.json`（來自 memory，搬之前 grep `_profile_path` 確認）。搬進 `engine/` 之後要往上多一層。
5. **測試怎麼載入 `.pyw`。** `tests/conftest.py` 的 `load_legacy` 用 `SourceFileLoader` 依名字找 `REPO_ROOT/<name>.pyw`，各測試檔透過 `legacy_loader` fixture 拿模組。改成 `.py` 之後這個 loader 換成普通 import 或刪掉，測試檔跟著改。
6. **四支入口的本體怎麼被叫。** `cds/ide/watcher.py` 第 35 到 38 行的 `SCRIPTS` 表把命令名對到 `Project_*.py` 檔名與 `main`。`cds/ide/silent.py` 第 164 行的 `run()` 把檔案 exec 進一個命名空間再呼叫 `main`。四支 `main()` 現在都回 `None`：`Project_export.py:416`、`Project_import.py:231`、`Project_compare.py:300`、`Project_Build.py:401`。
7. **成功失敗現在怎麼推。** `cds/ide/silent.py` 第 43 行 `BAD_LEVELS = ("warning", "error")`，`Outcome.ok()` 看訊息裡有沒有這兩級。這就是 D11 要換掉的等級推斷，階段 1 的事。
8. **對話框登記表。** `tests/test_silent.py` 第 306 行 `titles_asked_for` 掃一張寫死的檔名清單 `DRIVEN_FILES`，抓 `ask_yes_no("標題"` 與 `timed_prompt(ask_yes_no, "標題"` 兩種寫法，跟 `silent.YES_NO`、`silent.YES_NO_CANCEL` 比。搬檔案要改這張清單。
9. **版本在哪。** `codesys_constants.pyw` 第 22 行 `SCRIPT_VERSION = "k1.1.1"`。`cds/__init__.py` 第 15 行 `VERSION = "k1.0.1"` 沒人讀。`cds/ide/session.py` 第 123 行 `script_version()` 用 `imp.load_source` 讀 `codesys_constants.pyw`，這是 D12 的唯一例外。引擎改成套件之後這裡可以變成普通 import，例外就消失了。
10. **實例目錄的字面值。** `cds/core/ipc.py` 第 46 行、`tests/test_ipc.py` 第 19 行、`Project_watch.py` 第 7 行的 docstring、readMe。`cds/ide/statusform.py` 第 33 行從 `ipc.default_root()` 往上一層推 `statusform.json` 的位置，會跟著走。
11. **`WATCHER_CLI_PLAN.md` 的節號指標。** SPEC 說六處，實際九處：`cds/core/instances.py:26`（11.3）、`cds/ide/session.py:9`（14）、`cds/ide/silent.py:156`（15）、`cds/ide/statusform.py:10`（14）、`cds/ide/watcher.py:7`（14）、`cds/__init__.py:13`、`tests/test_watcher.py:8`（14.5）、`tools/probe_click_menu.py:4`（14.2）、`tools/probe_watcher_ui.py:4`（14.5）。
12. **`cds-sync-` 字面值分佈。** `codesys_utils.pyw` 19 處、`Project_parameters.py` 16、`tests/test_project.py` 7、`Project_directory.py` 4、`Project_export.py` 3，其餘各 1 到 2 處：`tools/watch_harness.py`、`tools/probe_watcher_ui.py`、`tests/test_watcher.py`、`tests/test_path_cache.py`、`codesys_compare_engine.pyw`、`cds/ide/project.py`、`Project_perf_test.py`、`Project_perf_probe.py`、`Project_import.py`、`Project_compare.py`、`tools/open_copy_and_watch.py`。階段 4 收成常數。
13. **另一個前綴不同的專案屬性。** `cds-text-sync-multipleApps` 出現在 `codesys_utils.pyw:483`、`Project_Build.py:47`、`cds/ide/watcher.py:334`。它不是 `cds-sync-` 開頭。要不要併進常數，第 7 節決定。
14. **使用者現在開著的 IDE。** pid 14012，DIADesigner-AX 1.10，專案 `P:\Shared\Acme\Site\SheetSplitter\PLC\Shm_2026.07.29.project`，看門人登記檔 `%LOCALAPPDATA%\cds-text-sync\instances\Shm_2026.07.29-14012.json`，記憶體裡的看門人版本 k1.1.0。不碰。
15. **這台的 IDE 與無頭啟動三元組。** 「無頭」指用 `--noUI` 起 IDE 不開視窗、跑完腳本就退出。
    - 原廠 3.5.21.40：`C:\Program Files\CODESYS 3.5.21.40\CODESYS\Common\CODESYS.exe`，profile `CODESYS V3.5 SP21 Patch 4`，ScriptDir `%LOCALAPPDATA%\CODESYS\ScriptDir`，ScriptEngine.plugin 4.2.0.0，IronPython 2.7.12。另有 3.5.19.10、3.5.20.40 裝在同層，共用同一個 ScriptDir。
    - Lenze 3.24：`C:\Program Files (x86)\Lenze\PlcDesigner\3.24.0.24457\PlcDesigner\Common\PlcDesigner.exe`，profile `PLC Designer V3.24.0`，ScriptDir `C:\ProgramData\PLCDesigner\ScriptDir`，plugin 4.0.0.0，IronPython 2.7.7。
    - Lenze 4.0：`C:\Program Files\Lenze\PlcDesigner\4.0.1.33999\` 底下同形，profile `PLC Designer V4.0.1`，ScriptDir `%LOCALAPPDATA%\PLCDesigner\ScriptDir`，plugin 4.1.0.0。
    - Delta 1.10：`C:\Program Files\Delta Industrial Automation\DIAStudio\DIADesigner-AX 1.10\CODESYS\Common\DIADesigner-AX.exe`，profile `DIADesigner-AX 1.10`，ScriptDir `<安裝目錄>\CODESYS\ScriptDir`（要管理員），plugin 4.0.0.0，IronPython 2.7.7。Delta 1.8 同形。
    - 無頭啟動的規矩：`--noUI` 必配 `--profile`，少了直接退出。這些 exe 是 GUI 子系統，從 shell 直接跑拿不到輸出，要用 `cmd /c "\"<exe>\" --profile=\"<name>\" --noUI --runscript=\"<絕對路徑 .py>\" > out.txt 2>&1"`，或讓腳本自己寫檔。從 Git Bash 傳 profile 引號會壞，用 PowerShell 工具或 `cmd /c`。
16. **junction 現況。** 五個 junction 都指向整個來源 repo，所以 IDE 選單今天看到十一項。本 repo 的東西在人重新指 junction 之前不會出現在任何 IDE 的選單裡。
17. **分紙機探路腳本。** `sample_slitter_dev\tools\codesys_probe.py` 是 IronPython 側，report 是每行 `KEY=value`，有 BEGIN、END 標記與 `INTENDED_EXIT`。`sample_slitter_dev\scripts\codesys-probe.ps1` 是 CLI 側，參數有 `-List`、`-Install`、`-Exe`、`-ProfileName`、`-Project`、`-Report`、`-DumpDir`、`-Build`。SPEC 6.4 的表就是這兩支踩過的坑。
18. **上一輪真專案怎麼跑的。** 來源 `docs/WATCHER_CLI_PLAN.md` 第 16 節。用 `tools/open_copy_and_watch.py` 配環境變數 `CDS_OPEN_PROJECT`（副本路徑）與 `CDS_OPEN_KEEPALIVE=1` 起一個無頭 IDE、開副本、掛看門人、停在 `system.delay()` 不退出，再從外面用 CLI 打命令。階段 1 的 `--target` 驗收照這條路。
19. **CI。** 來源 `.github/workflows/ci.yml` 只在 push 到 `main` 與 `claude/**` 時跑，Python 3.12，`pytest tests -q`。
20. **安裝器。** 來源 `irm/setup.ps1` 只認 `%LOCALAPPDATA%\CODESYS\ScriptDir`，下載來源是上游 ArthurkaX。
21. **授權。** 來源是 MIT，版權人 Arthur（上游作者）。本 repo 的 `LICENSE` 已照搬，不能拿掉。

---

## 4. 設計

架構、資料流、安裝佈局全在 SPEC 第 5 節，這裡只寫 SPEC 沒定的實作細節。

**目錄。**

```
engine/     原 codesys_*.pyw 改 .py，加四支本體（分別對應 export、import、compare、build），各回傳結果
stub/       Project_*.py，每支不超過 15 行；階段 0 五支（export、import、watch、directory、parameters），階段 1 減到三支
cdsint/     原 cli/cds_ide.py 拆成 cli.py（目標解析、印結果）、headless.py（無頭啟動器 CLI 側）、
            installs.py（IDE 安裝探測）、plc.py（PLC 子命令）
cds/core/   照搬
cds/ide/    照搬，階段 2 加 headless.py（從 tools/open_copy_and_watch.py 與 watch_harness.py 收進來）
tools/      離線工具與診斷腳本
profiles/   照搬
tests/      照搬再改 import
docs/       SPEC.md、本工單、WATCHER.md、AI_WORKFLOW.md、history/
irm/        安裝器
img/        readMe 用的圖
```

**回傳結果的形狀（D11，階段 1）。** 一個 dict，至少有 `ok`（bool）、`summary`（一句話）、`data`（各命令自己的欄位，build 放錯誤清單）。`NeedsInput` 仍然走例外。替身 UI 用 `ok` 判斷成功，不再看訊息等級。

**stub 怎麼找本體。** 只准一個機制服務開發與安裝兩種模式（D16）。建議：stub 旁邊放一個 `body.path` 文字檔，一行本體路徑。安裝器寫它；開發模式安裝器也寫它，指向 repo。stub 讀它、插進 `sys.path`、import 本體、呼叫、回傳。這是第 7 節第 1 項，實作前決定並寫回。

**引擎模組載入。** `engine/` 是普通套件，四支本體用普通 import，不再 `imp.load_source`。要保留「改了引擎不用重啟 IDE」的行為，stub 在 import 前把 `sys.modules` 裡 `engine` 開頭的項目清掉。

**pyproject。** `[project] name = "cdsint"`，`requires-python = ">=3.11"`，無相依，`[project.scripts] cdsint = "cdsint.cli:main"`。`version` 第一版手寫成跟 `SCRIPT_VERSION` 一樣的字串，加一個測試比對兩者相等，release 腳本之後再補。

**report 格式（`--project` 形式，階段 2）。** 沿用 `--json` 結構再加 `ide`、`report_path`，寫 JSON。探路腳本用 `KEY=value` 是因為當時不信任 IronPython 的 json 模組；`cds/core/ipc.py` 已經在 IronPython 上用 json 寫結果檔跑過真專案，這個顧慮已經消失。

---

## 5. 分階段與驗收

「驗收」是能勾選的句子。標「還需要人」的，worker 做到那裡就跳過並在回報裡列出來。

- [x] **階段 0：搬家與身分**（SPEC 10.2 階段 0）
  - [x] 從來源 repo 搬進第 4 節的佈局。照搬的：`cds/`、`tools/`、`profiles/`、`tests/`、`irm/`、`img/`、`.github/`、`conftest.py`、`requirements-dev.txt`、`CHANGELOG.md`、`PRINCIPLES.md`、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`SECURITY.md`、`docs/AI_WORKFLOW.md`、`skills/cds-ide/` 改名 `skills/cdsint/`。改位置的：七支 `codesys_*.pyw` 進 `engine/` 改 `.py`；`Project_export.py`、`Project_import.py`、`Project_compare.py`、`Project_Build.py`、`Project_directory.py`、`Project_parameters.py` 的本體進 `engine/`（檔名第 7 節第 2 項決定），`_load_hidden_module` 那段換成普通 import，邏輯一行不改；`Project_discover.py`、`Project_resources.py`、`Project_perf_probe.py` 進 `tools/`；`cli/cds_ide.py` 進 `cdsint/cli.py`。不搬的：`Project_perf_test.py`、`Performance_tests/`、`cds/__init__.py` 的 `VERSION`、`readMe.md`（重寫）、`WORKFLOW.md`（進 history）。
  - [x] `stub/` 五支與找本體的機制（第 7 節第 1 項）。`Project_watch.py` 的本體已經是 `cds/ide/session.py`。
  - [x] `pyproject.toml`：套件 `cdsint`、命令 `cdsint`。`tests/test_cds_ide_cli.py` 跟著改。
  - [x] 實例目錄改 `%LOCALAPPDATA%\cdsint\instances`（事實 10 的每一處），不寫遷移。
  - [x] `cds/ide/watcher.py` 的 `SCRIPTS` 表與 `cds/ide/silent.py` 的 `run()` 改成叫 `engine/` 裡的本體。`cds/ide/session.py` 的 `script_version()` 改成普通 import，D12 例外消失。
  - [x] `tests/conftest.py` 的 `load_legacy` 換成普通 import 或刪除；`DRIVEN_FILES` 清單改指 `engine/` 的本體。
  - [x] 抽 `docs/WATCHER.md`：從來源 `docs/WATCHER_CLI_PLAN.md` 第 5、6、14 節抽，改成現況陳述不是計畫。事實 11 的九處指標改指它的節號。來源的 `WATCHER_CLI_PLAN.md`、`RESEARCH_HTTP_IDE_CONTROL.md`、`REWORK_PLAN.md`、`WORKFLOW.md` 與 `docs/history/` 底下兩份，全部進本 repo 的 `docs/history/`。
  - [x] CI 改成 push 到任何分支都跑。
  - [x] CHANGELOG：頂上加 Unreleased 一段，說明搬進 cdsint、來源 repo 是哪個、來源 k1.1.1 之後沒發版的內容（來源 `git log --oneline 81d994e..9aa9886`，perf 與存檔一次那幾個 commit）寫症狀、根因、改法。
  - [x] readMe：先寫最小版。定位一段（SPEC 第 0 節）、來源 repo 一句、開發模式安裝（junction 指 `stub/`，三家 ScriptDir 的表）、CLI 命令表（現有的八個）、exit code。全面改寫留到階段 2。
  - [x] 驗收：根目錄 `python -m pytest -q` 與 `python -m pytest tests -q` 都綠，通過數不少於 389。
  - [x] 驗收：在 `%TEMP%\cdsint-work\clone\` 對本 repo `git clone`、`pip install -e .`、`cdsint --help` 列出八個命令——過。`cdsint list` 訊息說沒有看門人——過。exit 是 0 不是本句原本寫的 2，監督者裁定 0 才對，見第 7 節第 5 項；SPEC 4.3 已補一句。
  - [x] 驗收：`grep -rn "cds-text-sync" --include=*.py --include=*.md --include=*.toml --include=*.ps1 --include=*.yml .` 剩下的只有 pragma 前綴 `cds-text-sync.<key>`、屬性 `cds-text-sync-multipleApps`、來源與上游的出處註記、`docs/history/` 底下的。
  - [x] 驗收：`grep -rn "WATCHER_CLI_PLAN\|imp.load_source\|_load_hidden_module" --include=*.py .` 為零。
  - [x] 驗收：一支放在 `tools/` 的探針腳本，把本 repo 根目錄插進 `sys.path`，import `engine` 底下七個模組、四支本體、`cds.core`、`cds.ide.session`，成功印 `OK` 並寫檔。用原廠 3.5.21.40、Lenze 3.24、Delta 1.10 各無頭跑一次，三份輸出都有 `OK`、沒有 traceback。
  - [x] 驗收：用原廠 3.5.21.40 無頭跑 `stub/Project_watch.py`，輸出裡有看門人的啟動訊息、沒有 traceback；跑 `stub/Project_export.py`，輸出說沒有開啟的專案、沒有 traceback。
  - [x] 驗收：`stub/` 每個檔案 `wc -l` 不超過 15。
  - 監督者驗證（2026-09-05 15:40）：`python -m pytest tests -q` 與根目錄 `python -m pytest -q` 各 390 passed，監督者自己跑的。`tools/probe_imports.py` 在原廠 3.5.21.40 無頭重跑一次，27 秒，最後一行 `OK`。來源 repo 的 `git status` 跟派工前一字不差。兩條 grep 驗收監督者重跑，結果同 worker 回報；`imp.load_source` 唯一一筆命中是 `tools/probe_imports.py` 的 docstring 在講歷史，不是呼叫。worker 起過的六個無頭行程都已不在，`%TEMP%\cdsint-work\` 已空。

- [ ] **階段 1：三個入口**（SPEC 10.2 階段 1）
  - [ ] 四支本體的 `main()` 回傳第 4 節的結果；`cds/ide/silent.py` 改讀回傳值，刪 `BAD_LEVELS`；`tests/test_silent.py` 的等級測試換成回傳值測試。
  - [ ] 設定流程（SPEC 6.7）併進匯出匯入的本體；刪 `engine/` 裡 directory 與 parameters 的本體和它們的 stub，`stub/` 剩三支；狀態視窗加「設定」按鈕，開跟原本 `Project_parameters.py` 一樣的對話框。
  - [ ] 安裝器 `irm/setup.ps1` 改寫：依 SPEC 5.3 的表判斷三家 ScriptDir、本體裝到 `%LOCALAPPDATA%\cdsint\` 或指向 clone、寫 stub 與找本體的檔、開發模式用 junction 指 `stub/`；下載來源改本 repo。接受 `-ScriptDir` 覆寫，讓驗收能對假目錄裝。
  - [x] 視窗標題改 `cdsint`：狀態視窗、比對結果視窗。階段 0 已做，見第 7 節 worker 的 Ruling。
  - [ ] 驗收：`python -m pytest tests -q` 綠。`grep -rn "BAD_LEVELS" cds/ engine/ stub/ cdsint/` 為零。
  - [ ] 驗收：`stub/` 只有三個檔案。
  - [ ] 驗收：安裝器對 `%TEMP%\cdsint-work\scriptdir\` 裝完，裡面只有 `cdsint\Project_export.py`、`cdsint\Project_import.py`、`cdsint\Project_watch.py` 三個 `.py`。用原廠 3.5.21.40 無頭 `--runscript` 跑那份 `Project_watch.py`，輸出裡有看門人的啟動訊息、沒有 traceback。
  - [ ] 驗收：對 Shm 副本，用原廠與 Delta 1.10 各起一次無頭 IDE 掛看門人（事實 18 的路），`cdsint export --target`、`cdsint import -y --target`、`cdsint compare --target`、`cdsint build --target` 四個都 exit 0，`--json` 的 `ok` 是 true。做完把自己起的 IDE 收掉。
  - [ ] 驗收（還需要人）：把五個 junction 改指本 repo 的 `stub/` 之後，三家 IDE 的 Scripts 選單各只有三項，toolbar 按鈕不用重設。原因：junction 是使用者的機器設定，選單也只有人看得到。
  - [ ] 驗收（還需要人）：看門人跑著時從 Scripts 選單啟動別的腳本沒問題（SPEC 11.3）。原因：要在有畫面的 IDE 裡點選單。

- [ ] **階段 2：無頭前門**（SPEC 10.2 階段 2）
  - [ ] `cdsint installs`：掃 `Program Files` 底下的 `CODESYS *`、`Delta Industrial Automation\DIAStudio\DIADesigner-AX*`、`Lenze\PlcDesigner\*`，還有 `Program Files (x86)\Lenze\PlcDesigner\*`；讀 `Profiles\*.profile.xml` 檔名當 profile 名；查登錄檔 `AppCompatFlags\Layers` 的 `RUNASADMIN`。
  - [ ] `--project P --install I` 形式：`cdsint/headless.py` 是 CLI 側，`cds/ide/headless.py` 是 IDE 側。SPEC 6.4 表的每一列都要保留，程式碼註解引 SPEC 6.4 的列。旗標 `--answer`、`--profile`、`--report`、`--force-lock`、`--sync-dir`；exit 3 逾時、exit 4 鎖檔或啟動失敗。
  - [ ] `verify` 子命令，兩種形式都有。
  - [ ] `config get`、`config set KEY=VALUE`，兩種形式都有，`cds-sync-plc` 拒絕（SPEC 6.5）。
  - [ ] argparse 擋住 `--target` 與 `--project` 同時給。
  - [ ] `tools/open_copy_and_watch.py`、`tools/watch_harness.py` 併進 `cds/ide/headless.py` 後刪除（D16）。
  - [ ] 分紙機 Makefile 要改成呼叫 `cdsint ... --project` 的那幾行，寫進第 7 節第 6 項，人去改。
  - [ ] readMe 依 SPEC 第 9 節全面改寫。`docs/AI_WORKFLOW.md` 與 `skills/cdsint/SKILL.md` 加 `--project` 形式那一段。`docs/history/WORKFLOW.md` 還成立的內容併進三個場景。
  - [ ] 驗收：`python -m pytest tests -q` 綠；`cdsint/` 底下每個模組 `wc -l` 不超過 300。
  - [ ] 驗收：`cdsint installs` 列出這台七套（3.5.19.10、3.5.20.40、3.5.21.40、Lenze 3.24、Lenze 4.0、Delta 1.8、Delta 1.10），每套有 profile 名，兩套 Delta 標需要管理員。
  - [ ] 驗收：`cdsint verify --project <Shm 副本> --install 3.5.21.40 --report r.json` 與 `--install "DIADesigner-AX 1.10"` 各一次 exit 0。report 裡 stdout 有回來、report 寫的退出碼跟實際收到的一致、匯出後同步資料夾無差異、build 0 errors。每一步的秒數記進第 7 節。
  - [ ] 驗收：對使用者開著的專案原檔跑 `cdsint compare --project "P:\Shared\Acme\Site\SheetSplitter\PLC\Shm_2026.07.29.project" --install "DIADesigner-AX 1.10"`，exit 4 且訊息含鎖檔路徑。這條只讀鎖檔就退出，不起 IDE，不寫原檔。
  - [ ] 驗收：`--timeout 5` 對一個會跑超過五秒的命令 exit 3，report 記逾時並註明疑似有對話框卡住，用自己記的 pid 確認行程已經不在。
  - [ ] 驗收：`cdsint export --target X --project P` 被 argparse 拒絕。
  - [ ] 驗收：`cdsint verify --target <無頭掛看門人的實例>` 也跑得完，exit 0。

- [ ] **階段 3：權限與 PLC**（SPEC 10.2 階段 3）
  - [ ] 讀 `cds-sync-plc` 屬性與 exit 5。`plc connect`、`plc download -y` 引擎側從探路腳本搬，放 `engine/` 跟 `codesys_online` 並排（D12）。`--target` 形式拒絕並說明 D8 的理由。`config set cds-sync-plc` 拒絕。帳密只從 `CDS_DEV_USER`、`CDS_DEV_PASS` 讀，任何輸出、report、log 都不含它們（D14）。
  - [ ] 驗收：用假 IDE 物件的測試涵蓋四條：屬性空時 `plc download -y` exit 5 且引擎的 login 沒被呼叫；屬性有 `download` 但沒 `-y` 時回 `needs_input`、exit 1、login 沒被呼叫；`plc connect --target` 被拒絕；report 的 CRC 欄位 `MATCH` 與 `DIFFERENT` 兩種各有測試。
  - [ ] 驗收：`grep -rn "CDS_DEV_PASS" .` 只出現在讀環境變數的那一行與文件裡。
  - [ ] 驗收（還需要人）：台架上 `plc connect` 列出裝置、`plc download -y` 下載成功且 CRC `MATCH`。原因：要接真 PLC 與憑證。

- [ ] **階段 4：引擎品質**（SPEC 10.2 階段 4）
  - [ ] 髒檔保護（SPEC 6.1 第一條）。匯出時磁碟上自上次同步後被改過而還沒匯入的 `.st` 不覆蓋，列成待匯入。
  - [ ] `engine/codesys_ui.py` 的 `show_toast` 改 WinForms Timer（D5）。`engine/codesys_utils.py` 的 `threading.Lock` 去留寫進第 7 節第 4 項。
  - [ ] `cds-sync-` 前綴收成一個常數，事實 12 的每一處改用它。`cds-text-sync-multipleApps` 是否併入見第 7 節第 3 項。
  - [ ] PRINCIPLES.md 依 SPEC 第 8 節改成兩級。
  - [ ] 碰到的函式順手把空白 `except:` 改成具體例外，不要求全清。回報清了幾處、剩幾處。
  - [ ] `tools/cache_doctor.py` 改成直接 import 引擎的 `file_signature()` 來判讀快取，拿掉它自己重放的舊判斷式與檔頭的「已過時」警告（第 7 節第 6 項）。
  - [ ] perf 量測：對 Shm 副本用階段 2 的 `--project` 形式量 export、compare（只改一個 POU）、build，各三次取中位數，原廠與 Delta 各一組，更新 SPEC 第 7 節的表並註明日期與 commit。
  - [ ] 驗收：磁碟改了沒匯入就跑 export，該檔沒被覆蓋且被列為待匯入，有測試涵蓋。
  - [ ] 驗收：`grep -rn "time.sleep\|threading\|Thread(" engine/ cds/ide/ stub/` 為零。
  - [ ] 驗收：`grep -rn '"cds-sync-' engine/ cds/ cdsint/ tools/` 只剩常數定義那一處。
  - [ ] 驗收：SPEC 第 7 節的 perf 表有新數字。

---

## 6. 回報格式

每個階段做完，最後一則訊息要有：

1. 這個階段的狀態一句話。
2. commit 清單，每個 hash 配一句話。
3. 測試通過數。
4. 數據表（有量東西的階段）。
5. 需要人的事，每件附一句為什麼只有人能做。
6. 沒做的事與原因。
7. 這個階段新增的裁決（第 7 節）。

---

## 7. 未決事項與裁決

實作時決定，決定了寫回：`Ruling: 決定 — 理由 — 錯了的代價`。

1. `cds-text-sync-multipleApps` 要不要併入 `cds-sync-` 常數。併入要對每個現有 `.project` 做遷移；不併就留一個有註解的例外。
2. `engine/codesys_utils.py` 的 `threading.Lock` 去留。單執行緒設計下它是空轉的。
3. 搬到 `tools/` 的 `Project_perf_probe.py` 等診斷腳本，無頭啟動器怎麼跑它們。是加一個 `--script` 旗標，還是各自帶啟動命令列。
4. 分紙機 Makefile 要改的行（階段 2 寫下，人做）。
5. `cdsint list` 找不到看門人時的 exit code。工單階段 0 的驗收寫 exit 2，程式碼與 `tests/test_cli.py` 都是 exit 0。見底下的 Ruling。
6. `tools/cache_doctor.py` 要重寫成呼叫 `file_signature()`。它現在重放的是 `95fdfbf` 修掉的舊判斷式，對現行的 cache 會報出沒有意義的數字。檔頭已加警告，程式沒動。

本階段（階段 0）新增的：

- Ruling: stub 找本體用 `body.path` — 旁邊一個純文字檔，一行安裝根目錄，stub 讀它、插進 `sys.path`、import 本體。安裝器寫它，開發模式也寫它；它是機器專屬的路徑，所以 gitignore。沒有選「把路徑寫死在 stub 裡」是因為那樣安裝器得改寫 stub 原始碼，而開發模式的 junction 直接指著 repo 裡的 `stub/`，改它就是弄髒 git。也沒有留「找不到就往上兩層」的後路，那會變成兩條路（SPEC D16）— 錯了的代價是 clone 完還沒寫 `body.path` 之前，從選單跑任何一支都會丟 `IOError`，訊息不會告訴你該建那個檔。
- Ruling: `engine/` 裡入口本體叫 `entry_export.py`、`entry_import.py`、`entry_compare.py`、`entry_build.py`、`entry_directory.py`、`entry_parameters.py` — `import` 是 Python 關鍵字，`entry_import` 不是；前綴一致所以一眼看得出哪些是入口本體、哪些是共用引擎模組 — 錯了的代價是文件與 commit 訊息裡「Project_import.py」這個講法要改口，選單上的名字沒變。
- Ruling: 看門人跑本體用 exec 檔案，選單跑本體用 import 加借全域 — 替身 `system` 必須在本體的模組層級程式碼跑起來之前就在它的命名空間裡，所以 `silent.run` 沒辦法改成 import；選單那條沒有這個需求，`engine/entry.py` 把 stub 的 `globals()` 借給本體，本體自己定義的名字優先，跟原本 `dict(ide_globals)` 再 exec 完全等價。這不算 SPEC D16 的兩條路：同一件事只有一份程式碼，差的是誰負責提供命名空間 — 錯了的代價是本體要維持「`system` 從自己的模組全域讀」這個假設，不能改成參數傳入，否則兩邊都要跟著改。
- Ruling: `cds/ide/session.py` 的 `script_version()` 整支刪掉，版本號由呼叫端（`stub/Project_watch.py` 與 `tools/watch_harness.py`）自己 import — 工單原本寫「改成普通 import」，但那樣 `imp.load_source` 的 hack 雖然沒了，`cds/ide` import 引擎模組這件事還在，而 SPEC D12 禁的就是這個方向。兩個呼叫端都不在 `cds/ide` 底下，所以移過去之後 D12 三條規則一個例外都不剩 — 錯了的代價是兩個呼叫端各多一行 import。
- Ruling: 比對結果視窗與狀態視窗的標題、IDE 訊息列的 `cds-ide:` 前綴，階段 0 就改成 `cdsint` — 標題本來排在階段 1，但階段 0 的驗收 grep 會抓到比對視窗那一行，而且這一階段叫「搬家與身分」，產品名字就是身分 — 錯了的代價是階段 1 的「視窗標題改名」那一項會發現已經做完了。
- Ruling: `cdsint list` 找不到看門人維持 exit 0，不改成工單寫的 exit 2 — `list` 的問題是「有誰在聽」，空的清單是答案不是失敗，而且現有的 `test_list_says_so_when_nothing_is_listening` 就是在釘這個行為；SPEC 4.3 的 exit 2 講的是「這個命令需要一個看門人而找不到」，`list` 不需要。改它是 CLI 契約的變更，超出「階段 0 不改邏輯」，留給監督者裁 — 錯了的代價是包 cdsint 的腳本如果拿 exit code 判斷「有沒有 IDE 在聽」會失準，要改讀 `--json` 的空陣列。
- Ruling: `irm/setup.ps1` 階段 0 只換名字與 URL，不改安裝佈局，檔頭加「還不能跑」的警告 — 它現在會把整棵樹倒進一個 ScriptDir 資料夾，而 IDE 是遞迴掃的，選單會列出 `engine/`、`tools/`、`tests/` 底下每一支 `.py`；要修就是階段 1 的重寫，硬塞進階段 0 等於把搬家跟改行為混在一起 — 錯了的代價是這段期間 `irm/setup.ps1` 是不能用的，安裝只能照 readMe 手動做，這件事寫在檔頭與 `irm/setup.md` 開頭。

監督者已裁的：

- Ruling（階段 0 驗收後）: `cdsint list` 找不到看門人回 exit 0，工單原本的驗收句寫錯了 — worker 的理由成立：`list` 問的是「有誰在聽」，空清單是答案；SPEC 4.3 的 exit 2 是給需要一個目標的命令用的。SPEC 4.3 補一句把這條講明 — 錯了的代價是包 cdsint 的腳本要讀 `--json` 的空陣列來判斷有沒有 IDE，不能看 exit code；這本來就是比較穩的做法。
- Ruling（階段 0 驗收後）: `tools/cache_doctor.py` 在階段 4 修，不在階段 1 — 它是離線診斷工具，不擋任何入口；階段 4 是引擎品質，改成 import `file_signature()` 正好歸那裡 — 錯了的代價是它帶著「已過時」的檔頭多活三個階段，有人拿它看 cache 會被警告擋住而不是被錯數字騙。
- Ruling（階段 0 驗收後）: worker 在階段 0 做的七條 Ruling 全部接受，不翻案 — 每一條都有理由與代價，而且 `script_version()` 那條讓 D12 一個例外都不剩，比工單原本寫的更好 — 錯了的代價是無。
- Ruling: cdsint 第一個版號是 `0.0.1`，階段 0 就把 `SCRIPT_VERSION` 與 `pyproject.toml` 的 `version` 一起改掉 — 監督者 2026-09-05 裁的；產品換了名字，繼續掛 `k1.1.1` 這個上游分叉的編號會讓「這是哪一版」變成要先問是哪個 repo — 錯了的代價是既有專案的 `cds-sync-version` 屬性跟新版號不符，下次匯出匯入會跳一次版本不符警告，按 `--force` 或在對話框按繼續就過，之後屬性自動寫成新值。
- Ruling: GitHub 遠端叫 `cdsint`，建立與 push 由人做，worker 不碰 — 監督者 2026-09-05 裁的，對外動作歸人 — 錯了的代價是沒有，worker 本來就只在本機 `main` commit。
- Ruling: 開新 repo，程式碼搬過來 — 使用者 2026-09-05 明確選的；SPEC D1 已改寫 — 錯了的代價是來源 repo 的歷史查起來要跨 repo，可接受。
- Ruling: 階段 0 只搬不改邏輯 — 搬家與改行為混在一起，測試紅了分不清 — 錯了的代價是階段 0 結束時 `engine/` 裡暫時有 directory 與 parameters 兩支等著階段 1 併掉，多活一個階段。
- Ruling: 階段 0 的 stub 有五支，階段 1 減到三支 — 階段 0 結束時工具要跟來源一樣可用 — 錯了的代價是多寫兩支各十行的檔案再刪。
- Ruling: 一條 `main` 分支跑五個階段 — 檔案搬移有相依 — 錯了的代價是某階段壞了要 revert 一段 commit，用 commit 邊界解決。
- Ruling: readMe 全面改寫放階段 2 不放階段 0 — CLI 的形狀階段 2 才定案 — 錯了的代價是階段 0、1 期間 readMe 只有最小版，可接受。
- Ruling: 分紙機 repo 與來源 repo 只讀不寫 — 都是使用者 git 管理的資料夾，鐵律 — 錯了的代價是使用者要自己改幾行 Makefile。

---

## 8. 接手 prompt

你在 `C:\Users\qazsskevin\Documents\repo\cdsint`，分支 `main`。先讀本工單第 0 到 4 節、`docs/SPEC.md` 全文、`CLAUDE.md`，再讀來源 repo 的 `PRINCIPLES.md`。然後從第 5 節第一個沒打勾的項目開始做。一段做完、`python -m pytest tests -q` 綠、commit（訊息照來源 repo 慣例）。做完的項目在本工單打勾並 commit。需要人在場的驗收做不到就標成「還需要人」跳過，繼續下一項。決定了第 7 節的未決事項就寫回 `Ruling: 決定 — 理由 — 錯了的代價`。一個階段全部做完就停下來照第 6 節回報，不要自己進下一階段。
