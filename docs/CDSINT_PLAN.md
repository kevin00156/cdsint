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
14. **使用者現在開著的 IDE。** pid 14012，DIADesigner-AX 1.10，專案 `P:\Shared\Acme\Site\SheetSplitter\PLC\Shm_2026.07.29.project`，看門人登記檔 `%LOCALAPPDATA%\cds-text-sync\instances\Shm_2026.07.29-14012.json`，記憶體裡的看門人版本 k1.1.0。不碰。（階段 4 的現況：這個行程已經不在了。它的登記檔最後一次心跳是 2026-09-05 20:48:24，而本 worker 第一次起無頭 IDE 是 21:29，所以是它自己先關的，不是被誰關的。登記檔沒有動過，還留在原處。）
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

- [x] **階段 1：三個入口**（SPEC 10.2 階段 1）——監督者 2026-09-05 17:10 驗收通過；只剩底下兩條「還需要人」，依使用者指示等基本開發全部做完再處理。
  - [x] 四支本體的 `main()` 回傳第 4 節的結果；`cds/ide/silent.py` 改讀回傳值，刪 `BAD_LEVELS`；`tests/test_silent.py` 的等級測試換成回傳值測試。
  - [x] 設定流程（SPEC 6.7）併進匯出匯入的本體；刪 `engine/` 裡 directory 與 parameters 的本體和它們的 stub，`stub/` 剩三支；狀態視窗加「設定」按鈕，開跟原本 `Project_parameters.py` 一樣的對話框。
  - [x] 安裝器 `irm/setup.ps1` 改寫：依 SPEC 5.3 的表判斷三家 ScriptDir、本體裝到 `%LOCALAPPDATA%\cdsint\` 或指向 clone、寫 stub 與找本體的檔、開發模式用 junction 指 `stub/`；下載來源改本 repo。接受 `-ScriptDir` 覆寫，讓驗收能對假目錄裝。
  - [x] 視窗標題改 `cdsint`：狀態視窗、比對結果視窗。階段 0 已做，見第 7 節 worker 的 Ruling。
  - [x] 驗收：`python -m pytest tests -q` 綠。`grep -rn "BAD_LEVELS" cds/ engine/ stub/ cdsint/` 為零。——416 passed，grep 零。
  - [x] 驗收：`stub/` 只有三個檔案。——三支 `.py`，各 15、15、14 行；另外有一個 `body.path`，那是安裝器寫的、gitignore 的機器專屬路徑檔，不是第四支腳本。
  - [x] 驗收：安裝器對 `%TEMP%\cdsint-work\scriptdir\` 裝完，裡面只有 `cdsint\Project_export.py`、`cdsint\Project_import.py`、`cdsint\Project_watch.py` 三個 `.py`。用原廠 3.5.21.40 無頭 `--runscript` 跑那份 `Project_watch.py`，輸出裡有看門人的啟動訊息、沒有 traceback。——過。第一次跑掛在 `body.path` 的 BOM 上（`ImportError: No module named cds.ide`），修掉後 exit 0，輸出是 `cdsint: listening as unsaved-21556`。
  - [x] 階段 1 收尾（監督者驗收後加的）：物件處理不了的時候，引擎要在**一個地方**把它變成有名字的正常結果，不是五個呼叫點各包一層 `try/except`。`classify_object` 現在有五個呼叫點（`entry_export` 兩處、`entry_compare` 一處、`codesys_compare_engine` 兩處），匯出那邊包了、比對那邊沒包，所以原廠開 Delta 專案時 export 活著而 compare 與 import 死掉。做法由 worker 定，約束是：任何命令碰到分類不出來、建不出來、匯不出去的物件，都把名字列進回傳結果的 `data`（例如 `data.failed_objects`），而且 `ok` 為 False；不准有 traceback 逃出來。加一個測試：假物件讀 `.type` 就丟例外，三個命令都回 `ok=False` 且名字在 `data` 裡。這條同時推翻 worker「`ok` 一比一複製舊判決」的做法，理由見第 7 節。——做法：`engine/unhandled.py` 是一次命令的登記簿；攔的地方是「一個迴圈處理一個物件」那一步，共兩處（`find_all_changes` 的 Pass 1、`entry_export` 的主迴圈），加上 `classify_object` 自己不再丟例外。只包 `classify_object` 不夠，因為 Pass 1 在它之前先讀 `obj.guid`，缺外掛的物件每個屬性都會丟例外。三個命令把名字寫進 `data.failed_objects` 並讓 `ok` 是 False，`summary` 也帶上名字。匯出額外一條：這一輪有物件處理不了就不刪孤兒檔。測試在 `tests/test_unhandled_objects.py`（11 條）。
  - [x] 驗收：對 Shm 副本，用 Delta 1.10 起無頭 IDE 掛看門人（事實 18 的路），`cdsint export --target`、`cdsint import -y --target`、`cdsint compare --target`、`cdsint build --target` 四個都 exit 0，`--json` 的 `ok` 是 true。做完把自己起的 IDE 收掉。——**Delta 1.10 四個全過**（export 16.6s、import 14.2s、compare 13.2s、build 31.3s，229 個物件，build 0 errors 101 warnings）。**原廠 3.5.21.40 只有 export 過**；compare 與 import 掛在 `classify_object` 對缺外掛的物件丟 `SystemError`，build 因為缺 Delta 的函式庫而有 502 個編譯錯誤所以 exit 1。兩者都不是階段 1 造成的，原因是這是 Delta 的專案、原廠 CODESYS 沒裝 Delta 的裝置描述與函式庫，見第 7 節的裁決請求。自己起的六個無頭行程都已收掉，`%TEMP%\cdsint-work\` 已刪。
  - [x] 驗收（監督者改寫）：原廠 3.5.21.40 用**它自己開得了的專案**驗四個命令：`D:\Acme\Site\SheetSplitter\PLC\.softplc\softplc_refactor.project`（Shm 的重構分支，一樣 229 個物件，上一輪在原廠 build 是 0 errors，見 `docs/history/WATCHER_CLI_PLAN.md` 第 16 節）。先複製到 `%TEMP%\cdsint-work\`，不碰 `.softplc\` 裡任何東西。四個命令都 exit 0，`ok` 是 true，build 0 errors。——**全過**：export 19.4s（229 個新檔）、import 13.4s（229 identical）、compare 13.4s（229 unchanged）、build 22.1s（0 errors、101 warnings）。四個的 `data.failed_objects` 都是空的。
  - [x] 驗收（監督者改寫）：跨家的情況變成收尾那條的驗收：原廠 3.5.21.40 開 Shm 副本，`export`、`compare`、`import -y` 三個都 exit 1，`--json` 的 `data` 裡列出那 7 個物件的名字，輸出裡沒有 traceback；`build` exit 1 帶錯誤數是預期（缺 Delta 函式庫），不算失敗。——**全過**：三個都 exit 1、`ok` false、`data.failed_objects` 是同樣的七個（`ArchiveObject`、`Hardware Configuration`、`Network Configuration`、`EtherCAT Topology`，另外三個連 `get_name()` 都丟例外，退而顯示物件本身的字串，是 GUID 形狀的識別碼），`error` 裡沒有 traceback。`build` exit 1，502 errors 101 warnings，也沒有 traceback。自己起的三個無頭行程都收掉了，`%TEMP%\cdsint-work\` 已刪，兩個來源專案一個位元組都沒動。
  - 監督者驗證（2026-09-05 17:10，收尾之後）：`python -m pytest tests -q` 與根目錄各 427 passed，監督者自己跑的。`engine/unhandled.py` 讀過，攔截點與登記簿的設計接受（見第 7 節）。`softplc_refactor.project` 最後寫入時間是 9 月 4 日，鎖檔的更新來自使用者自己開著的 CODESYS（pid 17340），worker 沒有寫過來源。沒有殘留的 IDE 行程，`%TEMP%\cdsint-work\` 不存在，使用者看門人心跳 17:02。真 IDE 的四個命令這一輪由 worker 跑，監督者沒有重跑；階段 2 的 `verify --project` 驗收會由監督者親自重現，那條一次涵蓋這四個命令。
  - 監督者驗證（2026-09-05 16:40）：`python -m pytest tests -q` 與根目錄各 416 passed，監督者自己跑的。`irm\setup.ps1 -List` 列出這台正好五個 ScriptDir。監督者自己對一個假 ScriptDir 跑 `-Clone`，裡面只有一個叫 `cdsint` 的 junction 指向 `stub/`；用原廠無頭跑那份 `Project_watch.py`，26 秒，exit 0，輸出 `cdsint: listening as unsaved-16500`，登記檔建在 `%LOCALAPPDATA%\cdsint\instances`（監督者跑完自己刪了）。來源 repo、五個 junction、使用者的看門人（心跳 16:35）都沒被碰；沒有殘留的 IDE 行程；`%TEMP%\cdsint-work\` 不存在。
  - [ ] 驗收（還需要人）：把五個 junction 改指本 repo 的 `stub/` 之後，三家 IDE 的 Scripts 選單各只有三項，toolbar 按鈕不用重設。原因：junction 是使用者的機器設定，選單也只有人看得到。
  - [ ] 驗收（還需要人）：看門人跑著時從 Scripts 選單啟動別的腳本沒問題（SPEC 11.3）。原因：要在有畫面的 IDE 裡點選單。

- [x] **階段 2：無頭前門**（SPEC 10.2 階段 2）——監督者 2026-09-05 19:50 驗收通過。施工項目、兩輪收尾（會清空專案的洞、逾時語意）都由監督者親自重現過，見各段的「監督者驗證」。
  - [x] `cdsint installs`：掃 `Program Files` 底下的 `CODESYS *`、`Delta Industrial Automation\DIAStudio\DIADesigner-AX*`、`Lenze\PlcDesigner\*`，還有 `Program Files (x86)\Lenze\PlcDesigner\*`；讀 `Profiles\*.profile.xml` 檔名當 profile 名；查登錄檔 `AppCompatFlags\Layers` 的 `RUNASADMIN`。——在 `cdsint/installs.py`。認一套安裝的條件是執行檔在，不是目錄名字像版本號，理由同安裝器那條 Ruling：這台的 `Lenze\PlcDesigner\` 底下有 `GatewayPLC`、`DIAStudio\` 底下有一個沒有版本號的 `DIADesigner-AX`，只看目錄名的話它們都會被當成一套。順帶也印 ScriptDir 與它要不要管理員。
  - [x] `--project P --install I` 形式：`cdsint/headless.py` 是 CLI 側，`cds/ide/headless.py` 是 IDE 側。SPEC 6.4 表的每一列都要保留，程式碼註解引 SPEC 6.4 的列。旗標 `--answer`、`--profile`、`--report`、`--force-lock`、`--sync-dir`；exit 3 逾時、exit 4 鎖檔或啟動失敗。
  - [x] `verify` 子命令，兩種形式都有。——`cdsint/verify.py`，import、export、compare、build 四步，compare 有任何差異就算沒過。
  - [x] `config get`、`config set KEY=VALUE`，兩種形式都有，`cds-sync-plc` 拒絕（SPEC 6.5）。——`cds/ide/config.py`，走看門人與無頭共用的那張命令表。
  - [x] argparse 擋住 `--target` 與 `--project` 同時給。——互斥群組；另外 `--project` 專用的五個旗標配 `--target` 用也會被擋。
  - [x] `tools/open_copy_and_watch.py`、`tools/watch_harness.py` 併進 `cds/ide/headless.py` 後刪除（D16）。——開專案那半進了 `cds/ide/headless.py`，「掛看門人再停住不退出」那半是新的 `tools/headless_watch.py`，理由見底下的 Ruling。`tools/probe_watcher_ui.py` 跟著改。
  - [x] 分紙機 Makefile 要改成呼叫 `cdsint ... --project` 的那幾行，寫進第 7 節第 4 項，人去改。
  - [x] readMe 依 SPEC 第 9 節全面改寫。`docs/AI_WORKFLOW.md` 與 `skills/cdsint/SKILL.md` 加 `--project` 形式那一段。`docs/history/WORKFLOW.md` 還成立的內容併進三個場景。
  - [x] 驗收：`python -m pytest tests -q` 綠；`cdsint/` 底下每個模組 `wc -l` 不超過 300。——508 passed（根目錄同）。`cdsint/` 最長的是 `headless.py` 253 行，其次 `cli.py` 249、`installs.py` 223。
  - [x] 驗收：`cdsint installs` 列出這台七套（3.5.19.10、3.5.20.40、3.5.21.40、Lenze 3.24、Lenze 4.0、Delta 1.8、Delta 1.10），每套有 profile 名，兩套 Delta 標需要管理員。——七套全到，每套一個 profile 名，只有兩套 Delta 標「needs an elevated shell」。「要不要管理員」指的是 ScriptDir，理由見 Ruling；這台沒有任何一支 exe 掛 `RUNASADMIN`，掛了會另外印一行。
  - [x] 驗收：`cdsint verify --project <softplc 副本> --install 3.5.21.40 --report r.json` 與 `cdsint verify --project <Shm 副本> --install "DIADesigner-AX 1.10"` 各一次 exit 0。report 裡 stdout 有回來、report 寫的退出碼跟實際收到的一致、匯出後同步資料夾無差異、build 0 errors。每一步的秒數記進第 7 節。——**兩家都 exit 0**。兩份 report 的 `stdout_reached` 都是 true、`exit_code_trusted` 都是 true、四步的 `failed_objects` 都是空的、compare 四個差異數全是 0、build 都是 0 errors 101 warnings。兩條命令都要加 `--force`，Delta 那條還要 `--answer UpgradeProjectConfirmation=Yes`，理由見第 7 節。秒數在底下的數據表，也寫進 SPEC 第 7 節。
  - [x] 驗收：對使用者開著的專案原檔跑 `cdsint compare --project "P:\Shared\Acme\Site\SheetSplitter\PLC\Shm_2026.07.29.project" --install "DIADesigner-AX 1.10"`，exit 4 且訊息含鎖檔路徑。這條只讀鎖檔就退出，不起 IDE，不寫原檔。——exit 4，0.23 秒，訊息帶 `...\Shm_2026.07.29.project.~u`，沒有起任何行程。
  - [x] 驗收：`--timeout 5` 對一個會跑超過五秒的命令 exit 3，report 記逾時並註明疑似有對話框卡住，用自己記的 pid 確認行程已經不在。——exit 3，5.3 秒。report 記了 `timed_out: true`、`pid: 19748`、`exit_code_actual: null`，`error` 那句說 `--noUI` 底下這通常是有個沒人能按的對話框。`tasklist` 查 19748 已經不在。
  - [x] 驗收：`cdsint export --target X --project P` 被 argparse 拒絕。——`error: argument --project: not allowed with argument --target`。
  - [x] 驗收：`cdsint verify --target <無頭掛看門人的實例>` 也跑得完，exit 0。——用 `tools/headless_watch.py` 在 Delta 1.10 起一個無頭 IDE 掛看門人（`Shm_2026.07.29-21576`），`verify --force --target` 50.4 秒 exit 0，四步都過。跑完 `cdsint stop`，行程自己收掉。
  - 階段 2 的秒數（229 個物件，兩個副本都是「磁碟與 IDE 已經一致」的情況，所以比 SPEC 第 7 節那組基準快；IDE 啟動加開專案另外算，兩家都三十幾秒）：

    | 步驟 | 原廠 3.5.21.40（softplc 副本） | Delta 1.10（Shm 副本） |
    |---|---|---|
    | import | 24.2 秒 | 18.4 秒 |
    | export | 14.8 秒 | 14.8 秒 |
    | compare | 13.2 秒 | 14.0 秒 |
    | build | 23.5 秒 | 31.3 秒 |
    | 一整趟（含啟動） | 124.6 秒 | 142.3 秒 |
    | `verify --target`（Delta，IDE 已經開著） | — | 50.4 秒 |

  - 監督者驗證（2026-09-05 18:40）：`python -m pytest tests -q` 與根目錄各 508 passed，監督者自己跑的。`cdsint installs` 七套全列、`cdsint/` 每個模組都在 300 行以下、`--target` 配 `--project` 是 exit 2、對使用者開著的 Shm 原檔 `compare --project` 是 exit 4 且訊息含 `.~u` 路徑，都是監督者自己跑的。兩個原始專案的修改時間都是 9 月 4 日，兩個來源 repo 的 `git status` 跟派工前一樣，沒有殘留的 IDE 行程。
  - **監督者重現 `verify --project` 時抓到的洞。** 監督者把 softplc 複製到暫存區，`--sync-dir` 指到一個**空的**資料夾，跑 `verify --project --install 3.5.21.40 --force`。第一步 import 把副本裡 178 個物件刪掉、51 個刪失敗（子物件在父物件刪掉之後才輪到，`Object reference not set`），然後存檔；exit 1 只是因為那 51 個失敗讓 `ok` 變 False。如果刪得乾淨，verify 會接著匯出一個空專案、compare 無差異、build 通過，回一個什麼都沒證明的綠燈。worker 的兩條驗收沒撞到，原因是它的副本旁邊已經有匯出過的同步資料夾。同一條命令用 `--target` 打在使用者開著的專案上，只要 `cds-sync-folder` 指錯，專案就會被清空。根因有兩個：`verify` 自己替匯入按了確認（worker 的 Ruling，監督者推翻），以及 import 把「同步資料夾是空的」當成正常輸入。
  - [x] 階段 2 收尾（監督者驗收後加的）：`verify` 不再自己替匯入按確認，跟 `import` 一樣需要 `-y`，兩種形式都是。沒給 `-y` 就把匯入那步的計畫印出來（modified、new on disk、delete 各幾個）、回 `needs_input`、exit 1，IDE 一個物件都不動。SPEC 4.2 的表改成 `verify -y`。——做法：沒給 `-y` 的時候 `verify` 只跑 `compare` 這一步（四步裡唯一只讀的），再把它的三個計數換成匯入的計畫，多回一筆 `command` 是 `import`、`ok` 是 False、`needs_input.arg` 是 `yes` 的紀錄。理由見第 7 節。SPEC 4.2 的表監督者已經改過。
  - [x] 階段 2 收尾：`import` 的三條路（選單、`--target`、`--project`）在同步資料夾裡一個 `.st` 都沒有時直接拒絕，訊息說「同步資料夾 X 沒有任何 .st，拒絕刪掉專案裡每一個物件；先跑 export，或修正 `--sync-dir`／`cds-sync-folder`」。這不是門檻式的啟發，是「事實來源不存在」的前置檢查，跟現有的「登入中拒絕匯入」同一類。——檢查放在 `engine/entry_import.py` 的 `import_project()`，位置在 `load_base_dir()` 之後、版本檢查之前，所以三條路都經過它，而且在讀 IDE 樹之前就結束。判斷式 `has_st_files()` 放在 `engine/codesys_compare_engine.py` 裡 `scan_new_disk_files()` 旁邊，走訪規則跟它一致。
  - [x] 階段 2 收尾：`--project` 形式一律要求 `--sync-dir`，沒給就 argparse 擋。解析後的同步資料夾印在輸出的第一行，並寫進 report 頂層（`sync_dir`）。——六個有 `--project` 形式的命令都要，`config` 也不例外；少給是 `parser.error()`、exit 2。路徑在 CLI 側 `os.path.abspath` 解析完才送進去。那一行是 `sync folder: <路徑>`，`--json` 的時候不印（會弄壞 JSON），改成每一筆結果紀錄多一個 `sync_dir` 欄位，SPEC 4.3 補了這個欄位。理由：副本的 `cds-sync-folder` 屬性可能是指向原專案真實資料夾的絕對路徑，export 會寫進使用者 git 管理的目錄；scenario C 的呼叫端本來就知道兩個路徑，讓它明講比讓它猜安全。
  - [x] 階段 2 收尾：readMe、`docs/AI_WORKFLOW.md`、`skills/cdsint/SKILL.md` 補上這三條：`verify` 要 `-y`；空同步資料夾會被拒絕；`--project` 必配 `--sync-dir`。第 7 節第 4 項分紙機 Makefile 的行跟著加 `-y` 與 `--sync-dir`。——readMe 多一節「Two lines you cannot cross by accident」，命令表改 `verify -y [--force]`，旗標那段標 `--sync-dir` 必填；三份文件裡每一個 `--project` 的例子都補上 `--sync-dir`。Makefile 那段多一個 `CDS_SYNC` 變數，順手修好上一輪被吃掉的續行反斜線。
  - [x] 驗收：測試涵蓋三條：verify 沒 `-y` 而匯入會刪東西時回 `needs_input` 且引擎的刪除沒被呼叫；空同步資料夾時 import 拒絕且引擎沒被呼叫；`--project` 少 `--sync-dir` 被 argparse 擋。——`tests/test_verify.py` 多 13 條（沒 `-y` 時只有 `compare` 被要求、拒絕紀錄的三個數字、六個命令各自少 `--sync-dir` 都是 exit 2、第一行印什麼、`--json` 還是合法 JSON）；`tests/test_empty_sync_folder.py` 是新檔 6 條，用一個間諜替掉 `find_all_changes`，證明拒絕發生在讀 IDE 之前；`tests/test_headless.py` 多 2 條（路徑解析成絕對、報告與紀錄都有 `sync_dir`）。全套 531 passed。
  - [x] 驗收（監督者會重現）：softplc 副本、空的 `--sync-dir`：`verify --project --install 3.5.21.40 --force -y` exit 1，訊息是空資料夾拒絕，副本裡的物件數仍是 229（跑一次 `compare --project` 看 `new_in_ide`）；同一副本先 `export --project --sync-dir S`，再 `verify --project -y --sync-dir S` exit 0，report 頂層有 `sync_dir`。——**全過**。空資料夾那趟 72.3 秒 exit 1，import 那一步 3.1 秒就結束在拒絕訊息上（訊息帶著空資料夾的路徑），後面三步沒跑；接著 `compare --project` 回 `new_in_ide=229`、`different=0`，副本一個物件都沒少。然後 `export --project --sync-dir S` 寫出 229 個物件（73.0 秒），`verify -y --project --sync-dir S` 125.8 秒 exit 0，四步 import 23.5／export 14.6／compare 14.0／build 25.9 秒，compare 四個差異數全 0，build 0 errors 101 warnings，report 頂層 `sync_dir` 就是 S。
  - [x] 驗收：`verify --target <無頭掛看門人的實例>` 沒 `-y` 回 `needs_input`、exit 1；加 `-y` exit 0。——用 `tools/headless_watch.py` 在原廠 3.5.21.40 起一個無頭 IDE 掛看門人（`softplc_copy-12972`，開的是同一份副本）。沒 `-y`：22.9 秒 exit 1，`--json` 回兩筆紀錄，`compare` ok 而 `import` 的 `needs_input.arg` 是 `yes`，計數全 0（那時磁碟與 IDE 已經一致）。加 `-y --force`：70.0 秒 exit 0，build 0 errors 101 warnings。跑完 `cdsint stop`，行程自己收掉；只有使用者原本開著的兩個 IDE（pid 17340、14012）還在，`%TEMP%\cdsint-work\` 已刪，來源專案最後寫入時間仍是 9 月 4 日 16:55。

  - 監督者驗證（2026-09-05 19:25，收尾之後）：`python -m pytest tests -q` 與根目錄各 531 passed，監督者自己跑的。少給 `--sync-dir` 是 exit 2 且訊息講清楚原因。監督者親自重現：新的 softplc 副本、空的 `--sync-dir`，`verify -y --project` 在 import 那步被拒絕，exit 1，訊息就是空資料夾那句；接著 `compare --project` 回 `new_in_ide=229`、`different=0`，副本一個物件都沒少。沒 `-y` 的 `verify` 回 exit 1 並印出「這一趟會刪 N 個」。report 頂層有 `sync_dir`。監督者重現時另外撞到三件事，寫成底下的「階段 2 收尾二」與階段 4 第一項。
  - [x] 階段 2 收尾二（監督者重現後加的）：`--timeout` 的意思改成「每一步的上限」，兩種形式一致；`--project` 形式的行程期限從它推導：啟動寬限 + 步數 × timeout + 關閉寬限，兩個寬限量出來寫成常數並在註解說明怎麼量的。預設 120 不變。——`--target` 那半本來就是每一步各等一次 timeout，沒改。`--project` 那半的 `Headless.deadline(步數)` 是那個公式，`STARTUP_GRACE_S = 180`、`SHUTDOWN_GRACE_S = 60`。量法寫在常數上面：跑真的命令，用 shell 的時鐘減掉 report 裡每一步的時間戳，啟動冷的 47 秒、熱的 43 秒，關閉兩次都是 2 秒；常數取好幾倍，因為寬限太小會殺掉健康的執行（那正是要修的 bug），太大只是晚一點才報告一個掛住的啟動。原因：監督者用預設 timeout 跑 `verify -y --project`（原廠、softplc 副本、短路徑），121 秒被 kill，exit 3，但 report 裡四步全部 ok。一趟含啟動本來就要 120 到 140 秒（worker 自己量的數字），預設值讓旗艦命令的預設呼叫必定逾時。
  - [x] 階段 2 收尾二：逾時的時候先看 report。report 完整（有 `intended_exit`）就以 report 為準，exit code 用 report 的，輸出說「腳本已做完，IDE 沒有在期限內退出，已 kill」；report 不完整才是「疑似對話框卡住」。SPEC 6.4 那列「逾時當成有對話框卡住」補這個界線。——IDE 側是跑完每一個命令、`run_job` 回來之後才寫 report，所以「檔案在而且有 `intended_exit`」就等於「腳本跑到最後」，這個判斷不用另外加欄位。完整就照常回結果（exit code 還是從結果算，跟 `intended_exit` 同一條規則），只多印一行警告；不完整才丟 exit 3。`timed_out` 兩種情況都還是 true，那是事實；差別在 `error` 那句話。
  - [x] 階段 2 收尾二：CLI 自己 kill 掉的 IDE 留下的鎖檔（`<project>.~u`）由 CLI 自己清掉並說明；只清自己起的那個行程開的那個專案的鎖。——kill 之後等行程真的不在了才清（`process.wait` 沒逾時才算），清完每個檔印一行；行程沒死就不清，並印一行說下一趟要 `--force-lock`。鎖檔的兩種檔名、查詢與清除收成新的 `cdsint/lock.py`，起動前的拒絕與 kill 後的清理是同一個概念的兩個方向。原因：監督者被 kill 那趟之後再跑同一個副本，立刻 exit 4，得手動加 `--force-lock`；那把鎖是 cdsint 自己造成的，它知道是誰的。
  - [x] 驗收：測試涵蓋三條：期限的推導、report 完整時逾時不算失敗、kill 之後鎖檔被清。——`tests/test_headless.py` 多 4 條：四步的等待時間等於公式算出來的值、report 完整的 kill 回得出結果而且 `error` 裡沒有「對話框」那句、kill 之後鎖檔不見了、kill 不死的行程鎖檔留著。假的行程現在會模擬「被 kill 之後 wait 才回來」，因為那正是能不能清鎖的判準。全套 535 passed。
  - [x] 驗收（監督者會重現）：`verify -y --project` 用**預設** timeout 在原廠 softplc 副本（`%TEMP%` 底下的短路徑）exit 0，report `timed_out` 是 false。——**過**：133.0 秒 exit 0，`timed_out` false、`exit_code_trusted` true、實際與打算用的退出碼都是 0，四步 import 24.6／export 15.1／compare 14.3／build 25.5 秒，全部 ok。跑完 `%TEMP%\cdsint-work\` 已刪，副本旁邊沒有留下鎖檔，只有使用者原本開著的兩個 IDE（pid 17340、14012）還在。

  - 監督者驗證（2026-09-05 19:50，收尾二之後）：`python -m pytest tests -q` 與根目錄各 535 passed，監督者自己跑的。監督者親自在 `%TEMP%\cdsint-sup\` 底下複製 softplc、`export --project` 229 個物件 0 失敗，再 `verify -y --project` **不帶 `--timeout`**：exit 0，122 秒，report `timed_out` false、`exit_code_trusted` true、四步全 ok、build 0 errors，副本旁沒有鎖檔。沒有殘留的 IDE 行程，`%TEMP%\cdsint-work\` 不存在。

- [x] **階段 3：權限與 PLC**（SPEC 10.2 階段 3）——監督者 2026-09-05 20:45 驗收通過；只剩台架那條「還需要人」，依使用者指示等基本開發全部做完再處理。
  - [x] 讀 `cds-sync-plc` 屬性與 exit 5。`plc connect`、`plc download -y` 引擎側從探路腳本搬，放 `engine/` 跟 `codesys_online` 並排（D12）。`--target` 形式拒絕並說明 D8 的理由。`config set cds-sync-plc` 拒絕。帳密只從 `CDS_DEV_USER`、`CDS_DEV_PASS` 讀，任何輸出、report、log 都不含它們（D14）。——權限在新的 `cds/ide/permit.py`，攔在 `cds/ide/entries.py` 按下引擎本體之前；exit 5 靠結果紀錄新的 `denied` 欄位決定。引擎本體是新的 `engine/entry_plc.py`。`--target` 由 argparse 收下再拒絕（exit 2），訊息說 D8 的理由；看門人那邊也有一份同樣的拒絕，給手寫命令檔用。`config set cds-sync-plc` 原本就拒絕，現在跟 `permit.PROPERTY` 共用同一個常數。
  - [x] 驗收：用假 IDE 物件的測試涵蓋四條：屬性空時 `plc download -y` exit 5 且引擎的 login 沒被呼叫；屬性有 `download` 但沒 `-y` 時回 `needs_input`、exit 1、login 沒被呼叫；`plc connect --target` 被拒絕；report 的 CRC 欄位 `MATCH` 與 `DIFFERENT` 兩種各有測試。——`tests/test_plc.py` 61 條，四條都有；「login 沒被呼叫」那兩條除了看假的 online 物件沒被登入，還多一條證明引擎根本沒被載入。全套 596 passed。
  - [x] 驗收：`grep -rn "CDS_DEV_PASS" .` 只出現在讀環境變數的那一行與文件裡。——程式碼裡只有 `engine/entry_plc.py:46` 的 `PASS_ENV = "CDS_DEV_PASS"` 一處，其餘三處在 `docs/SPEC.md` 與本工單。另外有一條測試：把密碼設成一個哨兵字串跑完一整趟下載，確認結果紀錄、stdout、messages 裡都沒有它。
  - [x] 驗收（工單沒寫，worker 加的）：新模組在真的 IronPython 裡 import 得起來。——`tools/probe_imports.py` 在原廠 3.5.21.40（IronPython 2.7.12）34.7 秒與 Lenze 3.24（2.7.7）173.7 秒各無頭跑一次，32 個模組全 ok、最後一行 OK。順手修好那份清單：它還列著階段 1 就刪掉的 `engine.entry_directory` 與 `engine.entry_parameters`，現在跑一定 FAILED。兩個行程都自己退出，`%TEMP%\cdsint-work\` 已刪。
  - [ ] 驗收（還需要人）：台架上 `plc connect` 列出裝置、`plc download -y` 下載成功且 CRC `MATCH`。原因：要接真 PLC 與憑證。
  - 監督者驗證（2026-09-05 20:45）：`python -m pytest tests -q` 與根目錄各 596 passed，監督者自己跑的。`plc connect --target X` 與 `plc download -y --target X` 都是 exit 2 並說明 D8 的理由。`CDS_DEV_PASS` 在程式碼裡只有 `engine/entry_plc.py:46` 一處。監督者在 `%TEMP%\cdsint-sup\` 的 softplc 副本上跑 `plc connect --project --install 3.5.21.40`：屬性沒開，57 秒後 exit 5，訊息指向 SPEC 6.5；`config set cds-sync-plc=connect --project` exit 1 被拒。沒有殘留的 IDE 行程，使用者看門人心跳 20:37。台架那條沒有驗，工具刻意不從檔案讀憑證，監督者也沒有。

- [ ] **階段 4：引擎品質**（SPEC 10.2 階段 4）
  - [x] **先做這條（D13 的洞）**：匯出寫檔失敗的物件沒進登記簿。監督者把同步資料夾放在一個 168 字元長的路徑底下匯出 softplc 副本：229 個物件裡 87 個寫出、12 個「路徑超過 260 字元」有進 `failed_objects`，另外 130 個「Failed to write ST file: Could not find a part of the path」只印在 log，`data.failed` 沒算它們，`failed_objects` 沒有它們的名字。也就是說如果只有這 130 個失敗，`ok` 會是 True。修法：`entry_export.py` 寫檔那一層的失敗跟其他失敗一樣 `unhandled.note`；有測試（假的寫檔函式丟 `IOError`）。順便決定要不要在匯出前檢查最長路徑會不會超過 260 並提前拒絕（跟空資料夾那條同類的前置檢查），或改用 `\\?\` 前綴開長路徑；第 7 節寫回。
  - [x] `engine/entry_plc.py` 607 行，是階段 3 新寫的程式碼，超過 PRINCIPLES 的 400 行硬上限（SPEC 第 8 節：新寫的程式碼適用硬上限，`engine/` 只對舊碼放寬）。照「這段話是關於誰的」拆開，例如連線與閘道、下載與開機應用程式、CRC 比對與封存各一個模組，每個不超過 300 行；行為與 `tests/test_plc.py` 的 61 條測試不變。
  - [x] 髒檔保護（SPEC 6.1 第一條）。匯出時磁碟上自上次同步後被改過而還沒匯入的 `.st` 不覆蓋，列成待匯入。
  - [x] `engine/codesys_ui.py` 的 `show_toast` 改 WinForms Timer（D5）。`engine/codesys_utils.py` 的 `threading.Lock` 去留寫進第 7 節第 4 項。
  - [x] `cds-sync-` 前綴收成一個常數，事實 12 的每一處改用它。`cds-text-sync-multipleApps` 是否併入見第 7 節第 3 項。
  - [x] PRINCIPLES.md 依 SPEC 第 8 節改成兩級。
  - [x] 碰到的函式順手把空白 `except:` 改成具體例外，不要求全清。回報清了幾處、剩幾處。
  - [x] `tools/cache_doctor.py` 改成直接 import 引擎的 `file_signature()` 來判讀快取，拿掉它自己重放的舊判斷式與檔頭的「已過時」警告（第 7 節第 6 項）。
  - [x] import 刪物件的順序：父物件（POU）刪掉之後它的成員再被輪到就丟 `Object reference not set`，監督者在階段 2 重現時一次看到 51 個。改成先刪成員再刪父物件，或父物件刪掉時把它的成員從待刪清單拿掉；有測試。
  - [x] perf 量測：對 Shm 副本用階段 2 的 `--project` 形式量 export、compare（只改一個 POU）、build，各三次取中位數，原廠與 Delta 各一組，更新 SPEC 第 7 節的表並註明日期與 commit。
  - [x] 驗收：磁碟改了沒匯入就跑 export，該檔沒被覆蓋且被列為待匯入，有測試涵蓋。
  - [x] 驗收：IDE 側沒有 sleep、沒有執行緒。由 `tests/test_single_threaded_ide_side.py` 守著，不是靠人跑 grep；見底下的 Ruling。
  - [x] 驗收：`grep -rn '"cds-sync-' engine/ cds/ cdsint/ tools/` 只剩常數定義那一處。
  - [x] 驗收：SPEC 第 7 節的 perf 表有新數字。

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

1. `cds-text-sync-multipleApps` 要不要併入 `cds-sync-` 常數。併入要對每個現有 `.project` 做遷移；不併就留一個有註解的例外。（階段 4 已裁：不併，見底下的 Ruling。）
2. `engine/codesys_utils.py` 的 `threading.Lock` 去留。單執行緒設計下它是空轉的。
3. 搬到 `tools/` 的 `Project_perf_probe.py` 等診斷腳本，無頭啟動器怎麼跑它們。是加一個 `--script` 旗標，還是各自帶啟動命令列。
4. 分紙機 Makefile 要改的行（階段 2 寫下，**人做**；本 worker 一個位元組都沒有寫進那個 repo）。

   現在的 `st-verify`（`Makefile:164` 起）只做兩件事：對 buildstamp，然後 `git diff --exit-code -- codesys_export`。
   它的前提寫在自己的註解裡——「Run it AFTER Project_import.py + Project_export.py」——而那兩支是人在
   IDE 裡點的。`cdsint verify --project` 可以把那一步變成 make 的一部分。要加的行：

   ```make
   # 這個專案的 .project 不在 repo 裡，它的 cds-sync-folder 已經指著 codesys_export/。
   # --sync-dir 還是要寫：--project 形式一律要求它，理由是副本身上帶的屬性可能指到別處。
   CDS_PROJECT ?= D:\Acme\Site\SheetSplitter\PLC\.softplc\softplc_refactor.project
   CDS_INSTALL ?= 3.5.21.40
   CDS_SYNC ?= $(CURDIR)/codesys_export

   # import、export、compare、build 一趟跑完。IDE 不能開著這個專案，
   # 開著的話 cdsint 讀鎖檔就 exit 4 並印出鎖檔路徑。
   # -y 是「確認這一趟會改 IDE」，跟 cdsint import 的 -y 同一個意思；
   # 不給的話 verify 只跑 compare，印出匯入會改幾個、建幾個、刪幾個就 exit 1。
   st-sync:
   	cdsint verify -y --project "$(CDS_PROJECT)" --install "$(CDS_INSTALL)" \
   	    --sync-dir "$(CDS_SYNC)" --report .cdsint-verify.json

   st-verify: st-sync          # 這一行是唯一要改的既有行，其餘是新增
   ```

   四個要提醒人的地方。零，`-y` 少了 make 會停在 exit 1，那是設計不是故障；`--sync-dir`
   少了會被 argparse 擋在 exit 2。
   一，`cds-sync-version` 屬性現在是 `k1.1.1` 而工具是 `0.0.1`，
   第一次跑會撞版本不符，要 `--force`；那個屬性只有在專案存檔之後才會更新，而這個專案的
   `cds-sync-save-after-export` 是 False，所以它不會自己好起來——要嘛每次都帶 `--force`，
   要嘛人跑一次 `cdsint config set cds-sync-version=0.0.1`（那個命令會存檔）。
   二，`.cdsint-verify.json` 要進 `.gitignore`。
   三，`st-verify` 的 `git diff` 仍然有價值：`verify` 問的是「IDE 跟磁碟一不一致」，
   `git diff` 問的是「磁碟跟上一次 commit 一不一致」，兩個問題不一樣。
5. `cdsint list` 找不到看門人時的 exit code。工單階段 0 的驗收寫 exit 2，程式碼與 `tests/test_cli.py` 都是 exit 0。見底下的 Ruling。
6. `tools/cache_doctor.py` 要重寫成呼叫 `file_signature()`。它現在重放的是 `95fdfbf` 修掉的舊判斷式，對現行的 cache 會報出沒有意義的數字。檔頭已加警告，程式沒動。（監督者已裁：階段 4 做。）（階段 4 已做。）
7. 階段 2 冒出來、沒有處理的：這台機器上的既有專案 `cds-sync-version` 是 `k1.1.1`，而工具是 `0.0.1`，所以每一趟 `import`／`export`／`verify` 都撞版本不符。`save_sync_metadata` 會把屬性寫成新值，但只有在專案存檔之後才留得住，而 softplc 與 Shm 兩個專案的 `cds-sync-save-after-export` 都是 False，所以它不會自己好起來。今天的解法是每次帶 `--force`，或人跑一次 `cdsint config set cds-sync-version=0.0.1`（那個命令會存檔）。這是引擎行為，不在階段 2 的範圍內；記在這裡是因為它讓每一條真 IDE 的驗收都要多一個旗標。

階段 4 新增的：

- Ruling: perf 表改成「冷／熱」兩欄，不是一組數字 — 第一輪三次的差距到 ±20%，跑完馬上再測同一件事只剩一半的時間，再跑一整輪三次之間差不到 2%。一組看起來精確的中位數會讓下一個人以為那是可重現的，而它不是。原因不是專案副本也不是同步資料夾的路徑：熱過之後複製一份全新的專案到全新的路徑再量，還是熱的那個數字，所以是整台機器的狀態 — 錯了的代價是這張表比原本大一倍，而且拿它跟舊基準比的人得先接受「舊那組沒記錄狀態，只能當參考」。
- Ruling: 舊的基準數字（59.7／50.6／23.3 那組）留在文字裡不留在表裡 — 它沒有記錄機器狀態也沒記錄同步資料夾是不是空的，放進表裡會被當成同一種量法的前後對照，然後有人算出一個不成立的改善倍數；留在文字裡並註明為什麼不可比，資訊沒有丟 — 錯了的代價是想追歷史的人要讀一段話而不是看一格。
- Ruling: 量到的數字沒有拿來動 SPEC 11.1（要不要改用 `export_native` 整包倒出）— 那條說「階段 4 量完再決定」，而量出來的結論是「這台機器熱起來之後 export 是 12 秒」，一個 12 秒的東西不值得為它換掉引擎裡最核心的那條路；但這是監督者的決定不是我的，所以只把數字放上去，11.1 原封不動 — 錯了的代價是無。
- Ruling: 刪孤兒的作法是「父物件在同一張清單上的話，成員就不自己刪」，不是「先刪成員再刪父物件」 — 工單給了兩個選項，後者在這個專案的檔案佈局下不成立：方法的磁碟路徑跟它的 POU 在同一層（`Function Blocks/MC/MC.Main.st` 對 `Function Blocks/MC/MC.st`），照路徑深度排序分不出誰是誰的成員，能分的只有 IDE 物件的 `parent` 鏈。而且先刪成員等於多打一次 API，刪掉父物件本來就會把它們帶走 — 錯了的代價是無。
- Ruling: 被父物件帶走的成員算進 `deleted`，不算 skip 也不算 failed — 那個數字是人拿去跟剛才看到的孤兒清單對的，「因為父物件被刪所以不在了」也是不在了 — 錯了的代價是報告上的刪除數比實際呼叫 `remove()` 的次數多，而那正是事實。
- Ruling: 判斷在任何 `remove()` 之前一次算完 — 一邊刪一邊問「你的父物件是誰」，問到一半那個物件已經死了，`.parent` 自己就會丟例外，那時候「丟例外」到底是「父物件不在了」還是「這個物件本來就壞的」分不出來 — 錯了的代價是多走一趟 `to_sync`，那是純記憶體的迴圈。
- Ruling: `cache_doctor.py` 第一節從「`disk_mtime` 存成什麼型別」改成「引擎還會不會讀這個 cache」 — 原本那一節是為了抓 int 對 float 那場格式戰，戰爭結束了，型別只剩一種；換上去的問題才是讀者第一個該知道的：`load_sync_cache` 在 cache 版本或 profile hash 對不上時整份丟掉，那樣的話底下每個數字講的都是一份沒有人會讀的檔案 — 錯了的代價是無，兩個判準都是從引擎 import 進來的，不是抄的。
- Ruling: 順手給它補了測試（`tests/test_cache_doctor.py`），雖然工單只說改判斷式 — 這支工具的整個毛病就是「手抄了一份引擎的判斷式然後跟著漂走」，只換一次判斷式不改變它會再漂一次；測試用引擎自己的 `save_sync_cache` 寫 cache 再問醫生看到什麼，所以下次引擎那邊一改，這裡就紅。改之前先跑，四條全紅，其中一條紅得剛好：現行引擎剛寫好的一份健康 cache，舊版醫生兩邊都報 0.0% DEGRADED — 錯了的代價是無。
- Ruling: PRINCIPLES 的兩級不是照「`engine/` 對其他」切，是照「搬過來的對這裡寫的」切 — `tools/` 底下的 `Project_discover.py`、`Project_resources.py`、`call_tree_*.py` 跟 `engine/` 同一批搬過來，性質一模一樣，照 SPEC 8 的字面切等於因為它們落在別的資料夾就要它們守新碼的規矩。判準寫成「`git log --follow` 看它是不是在本 repo 第一個 commit 就在了」，這樣不必在文件裡列一張會腐爛的檔案清單 — 錯了的代價是有人搬新東西進 `tools/` 卻以為自己在寬鬆那一級；第 1 條「一個模組一件事」沒有寬鬆級，那條先擋住他。
- Ruling: 「硬上限」改寫成「新檔不准一開始就超過，已經超過的不准再長」，不是「超過就是 bug」 — `cds/ide/silent.py` 現在 403 行，為了 3 行去拆它是湊數字不是設計；而原本那句話的問題正是它把三個一千多行的檔說成 bug 然後什麼也沒發生。改寫過的版本是守得住的，而且它施的壓力方向對：下一個東西進去之前先拆 — 錯了的代價是有人拿「反正不准再長」當藉口讓 401 行的檔停在那裡；那是第 1 條要管的事。
- Ruling: PRINCIPLES 整份改寫，不只改尺寸那一節 — 工單只寫「改成兩級」，但第 3 條（「整包 `export_native` 一次倒出」）與第 4 條（「`cds/ide` 是唯一准碰 CODESYS 全域的地方」）描述的是被刪掉的那個骨架，不是現在的程式碼；SPEC 8 要改寫這份文件的理由就是「文件跟程式碼講不同的話比沒有文件更糟」，只修其中一條而留著另外兩條假話，等於承認那個理由然後不照做 — 錯了的代價是這次改動比工單那一行大，而且都是文件；沒有一行程式碼跟著動。
- Ruling: 空白 `except:` 的約束變成一條逐檔棘輪測試（`tests/test_bare_excepts.py`），文件與 SPEC 不再寫死數字 — SPEC 原本寫「119 處」，這次數完是 103，也就是那個數字早就漂掉了，而沒有任何機制攔住它；棘輪把「還剩幾處」放在唯一會被執行的地方，清掉之後測試會叫你把數字調小，所以 commit 訊息裡的數字自動是真的 — 錯了的代價是清理的人多改一行表格。
- Ruling: 這次順手清掉的是這一階段真的動過的九處，剩 94 處（`engine/` 87、`tools/` 7）— 工單說「不要求全清」，而一次改一百個 `except:` 是一百次猜「這裡原本想接住什麼」，那些程式碼呼叫的 API 這台機器測不到 — 錯了的代價是這批東西還要好幾個階段才清得完。
- Ruling: 屬性名字收在 `cds/core/props.py`，不是收在引擎也不是收在 `cds/ide` — 兩邊都要用它，而 D12 不准它們互相 import，`cds/core` 是唯一兩邊都到得了又不碰 CODESYS 的地方；順帶它在 CI 上跑得到，所以那張表可以被測。收的是「前綴一次、每個屬性一個常數」而不是「到處寫 `PREFIX + "folder"`」，因為後者會讓 `grep folder` 什麼都找不到，而屬性名字正是人要在 IDE 裡打的東西。收的範圍是「把名字當識別字用」的地方；訊息與註解裡當人話出現的那幾處（例如「請跑 `cdsint config set cds-sync-folder=<path>`」）留著原樣，那跟 SPEC 4.4、readMe 裡寫的一樣是文件不是程式，而 `tests/test_props.py` 已經把程式碼與 4.4 那張表綁在一起，改名的人一定會經過它 — 錯了的代價是引擎多一條對 `cds.core` 的相依（原本一條都沒有），IDE 側 `sys.path` 上本來就有 `cds`，但這是一個新的方向，日後要拆開跑就得記得。
- Ruling: `cds-text-sync-multipleApps` 不併進 `cds-sync-` — 它比其他屬性早，而且已經寫進每一個同步過的 `.project`；併進去換到的是一致的拼法，代價是對所有現有專案跑一次遷移，跟 D10 當初拒絕改前綴是同一筆帳。它在 `props.py` 裡有自己的常數，那段解釋就放在旁邊，所以拼法怪的地方只有一處而且附理由 — 錯了的代價是有人以為所有屬性都是 `cds-sync-` 開頭，然後 grep 不到這一個；常數與註解就是為了擋這件事。
- Ruling: 順手把 `permit.PROPERTY`、`config.READ_ONLY`、兩處 `SYNC_FOLDER_PROP` 這幾個轉手的別名拆掉，直接用 `props.X` — 一個字串三個名字，D16 說的兩條路就是這個形狀；`config.py` 自己的註解早就寫著「兩種拼法就是其中一個會過時」 — 錯了的代價是 `tests/test_plc.py` 有四行跟著改，測試本體沒動。
- Ruling: D5 的驗收從「跑一次 grep」改成一條 parse 程式碼的測試 — 工單寫的那條字串 grep 現在只剩兩個命中，兩個都是散文：`engine/unhandled.py` 用「threading a register through」講的是「一路傳下去」，`cds/ide/watcher.py` 的檔頭在複述這條規則本身（「No threads, no time.sleep()」）。為了讓 grep 歸零去改後面那句，等於為了通過檢查把正確描述規則的那句話弄壞。測試看的是呼叫與 import 這兩種語法節點，講到 thread 的字不會被誤判，而且它每次 CI 都跑，不必有人記得 — 錯了的代價是這條規則現在多一個檔案要維護，而且如果有人用 `getattr(x, 'sleep')()` 這種寫法繞過去，AST 看不出來；沒有人有理由那樣寫。
- Ruling: `codesys_utils` 的 `threading.Lock` 直接刪掉，不是留著加註解 — 工單說它「單執行緒設計下是空轉的」，實際查過更乾脆：整個 repo 沒有任何一處 acquire 它，它是死碼，PRINCIPLES 第 7 條 — 錯了的代價是無。
- Ruling: `show_toast` 改成 Timer 這件事沒有測試，也沒有在真 IDE 上跑過 — 這個檔第一行就 `import clr`，CI 上根本 import 不了，而托盤氣泡要不要正確消失只有眼睛看得出來。守得住的部分（沒有執行緒、沒有 sleep）已經由上面那條測試守住；剩下的要人在 IDE 裡跑一次比對視窗的「存到 .diff」看氣泡有沒有出現又消失 — 錯了的代價是氣泡可能出不來或者留在托盤上不走，那是外觀問題，不影響任何命令的結果。
- Ruling: 髒檔擋下來的物件讓那一趟 `ok=False`，而且不進 `unhandled` 登記簿，自己一個 `data.pending_import` — 磁碟不再跟 IDE 一致而匯出選擇不去弄一致，那就不是一趟做完的匯出，場景 C 拿 `ok` 當閘門的話不能放行（跟階段 1 監督者那條同一個理由）。不進登記簿是因為那個登記簿的檔頭寫明「不是故意跳過的」，而這是故意跳過的，讀者要做的事也不一樣：登記簿要人去查為什麼失敗，這一份要人去跑一次匯入 — 錯了的代價是某個工作流程習慣「改磁碟、直接匯出」，那種人每次會多拿一個 exit 1 與一句話，要嘛先匯入要嘛把檔案刪掉再匯出。
- Ruling: 判斷用 mtime 加大小跟快取比，而且只在內容已經確定不同之後才問；快取沒有紀錄就不擋 — 內容先比，所以 git checkout 把同樣內容重寫一次（時間戳動了、內容沒動）不會被誤判成待匯入；快取沒紀錄就不擋，是因為那不是「沒被改過」而是「不知道」，快取是本機狀態又 gitignore，剛 clone 的資料夾一筆都沒有，擋下去等於新機器上第一次匯出全部被拒 — 錯了的代價是兩個真的漏掉的情況：一是匯出寫完檔案但還沒存快取就被中斷，下一趟會把那些檔誤報成待匯入（跑一次匯入就好）；二是資料夾裡有檔案而這台機器從來沒同步過，那一趟照樣覆蓋，git 還救得回來，而且 `compare` 本來就是拿來先看的。
- Ruling: 比對視窗按「匯出」不受髒檔保護 — 那條路上有人剛剛看過差異並且選了 IDE 那一邊，擋他等於推翻他剛給的答案；技術上是 `perform_export` 組的 context 裡沒有 `cache_data`，那個「沒有」現在有註解說明理由，也有一條測試釘著，免得有人日後好心加上去 — 錯了的代價是有人在比對視窗選錯邊時沒有第二道保險，但比對視窗本來就把兩邊內容都攤開給他看了。
- Ruling: `manager.export()` 出錯一律丟例外，回傳 `False` 只剩「沒有東西要寫」一個意思 — 原本 `False` 同時代表「這個物件沒有文字內容」和「檔案寫不出去」，而兩個呼叫端（`entry_export.export_project` 與 `entry_compare.perform_export`）都只看回傳值等不等於 `new`／`updated`／`identical`，所以寫失敗被當成沒事發生。兩個呼叫端本來就各有一個「處理這一個物件」的 try/except，例外一丟就落進去，一個命令仍然只有一個地方認定失敗，跟 `engine/unhandled.py` 檔頭講的理由同一條 — 錯了的代價是原本安靜回 `False` 的三種罕見情形（`export_native` 沒產出檔案、沒有 primary project、XML 換檔失敗）現在會讓整趟匯出 `ok=False`；如果某個物件種類本來就合法地不產出 XML，那種專案會開始每次匯出都 exit 1，那時要修的是分類而不是把判決放寬。
- Ruling: 路徑超過 Windows 260 字元不做匯出前的預檢，也不改用 `\\?\` 前綴，就照 D13 一個一個報出名字 — 預檢要精確就得先把整棵樹分類一次才知道最長的檔名會有多長，那是多走一趟專案，違反 PRINCIPLES 第 3 條；`\\?\` 那條路在這裡沒有驗證過而且很可能不成立，引擎跑在 IDE 內的 IronPython 2.7 上，檔案是 .NET Framework 開的，那一層自己就擋 `MAX_PATH`，就算開得成，寫出來的 `.st` 是 git 與編輯器打不開的路徑，等於把失敗推到一個完全沒有登記簿的地方 — 錯了的代價是同步資料夾放得太深的人拿到的是一串逐物件的失敗清單，而不是開頭一句「你的資料夾太深」，要自己從錯誤訊息看出路徑長度是原因。
- Ruling: `entry_plc.py` 拆成四個檔不是三個，而且 `Trip` 也搬出去 — 工單建議的三分法留下的門面加 `Trip` 是 329 行，超過工單自己訂的 300；要壓到 300 只能砍掉那些解釋 CODESYS 行為的註解，那是這個檔最值錢的部分。第四刀切在「命令的門面」與「一趟的步驟」之間，這兩件事本來就不同：門面是 `cds/ide/entries.py` 叫得出名字的那個東西，步驟是工作本身。順帶的好處是 `Trip` 需要的兩樣東西（`command_args` 與腳本執行時的 `globals()`）現在是參數，在 `entry_plc.py` 那一個地方讀，而那正是 `cds/ide/silent.py` exec 出來的命名空間；留在 `Trip` 裡讀的話，`Trip` 一旦是普通 import 的模組就會讀到空的 — 錯了的代價是 `plc` 這條路多一個檔案要跟著看，而且 `tools/probe_imports.py` 的清單多三行。
- Ruling: 搬出去的函式由測試改指新模組，不在 `entry_plc.py` 留 re-export — 留 re-export 就是同一個東西兩個名字，SPEC D16 禁的就是這個；`tests/test_plc.py` 改的只有那個 import 小工具與五處呼叫，測試本體一行沒動，61 條全綠 — 錯了的代價是無。
- Ruling: `entry_compare.perform_export` 與 `perform_import` 的 summary 在有失敗時也接上 `unhandled.summary()`，跟 `export_project`、`compare_project`、`import_project` 一致 — `entry.result` 的約定是「`ok` 為 false 時 summary 就是呼叫端拿到的錯誤文字」，一句只有 `Failed: 1` 的文字沒說是誰 — 錯了的代價是無。

階段 3 新增的：

- Ruling: `denied` 是結果紀錄的一個獨立欄位，不是 `error` 裡的一句話 — exit code 是一個決定，而從錯誤訊息的字串比對出「這是被拒絕」不是決定，是猜；`needs_input` 早就是這個形狀，兩者要呼叫端做的事也剛好相反（補旗標 vs. 請人去改屬性） — 錯了的代價是 SPEC 4.3 的欄位表多一格，而看門人那條路上它永遠是 null。
- Ruling: 兩個 PLC 命令在協定上叫 `plc connect` 與 `plc download`，不是一個 `plc` 配 args 裡的 action — `cds/ide/entries.py` 那張表就分得開「一個唯讀、一個會改機器」，不必再寫一個 dispatcher 把差別讀回來；報告與輸出上也直接看得出跑的是哪一個 — 錯了的代價是 `SCRIPTS` 的鍵帶一個空白。
- Ruling: 權限攔在 `cds/ide/entries.py` 按下引擎本體之前，不在引擎本體裡 — 引擎正是被守的那個東西，一個已經載入、已經拿到 IDE 全域的模組就是已經開始跑了，「它中途就停了」跟「它從來沒跑」不是同一個承諾 — 錯了的代價是 `cds/ide/` 多一個檔案（`permit.py`）。
- Ruling: `plc` 配 `--target` 走 `parser.error()`、exit 2，不是收下之後回 exit 5 — 這是「旗標組合不合法」，跟 `--target` 配 `--project` 同一類（階段 2 收尾那條 Ruling）；exit 5 的意思只有一個：專案屬性沒開放 — 錯了的代價是無，訊息裡照樣說 D8 的理由。
- Ruling: 比對有三種答案，`UNKNOWN` 跟 `DIFFERENT` 一樣是 exit 1 — 「比不出來」讀起來絕不能跟「一致」一樣，那正是 SPEC 目標 6 要消掉的沉默失敗；而它跟 `DIFFERENT` 分開，是因為兩者要人做的事不同：`DIFFERENT` 要下載，`UNKNOWN` 要先查為什麼沒東西可比 — 錯了的代價是控制器上什麼都沒載入的時候 `connect` 也是 exit 1；summary 會把缺的是哪一半講清楚。
- Ruling: 兩個命令都是「只有 `MATCH` 才 exit 0」 — `compare` 可以回報差異又算 `ok`，因為外面有 `verify` 把它的數字變成判決；PLC 這兩個外面沒有那種東西，退出碼本身就得是判決，而 SPEC 6.6 說的「pipeline 拿這個當閘門」講的正是只讀退出碼的呼叫端 — 錯了的代價是想「只看看」的人也會拿到非零退出碼；`--json` 的 `data.crc` 仍然分得出三種情況。
- Ruling: 沒給 `--gateway` 就完全不動專案的閘道設定 — 專案裡帶的是別人設過的答案，一個唯讀命令順手改掉它就是在改被問的那個東西；`--gateway` 是給「同一個專案換一套 IDE 開，閘道跟著 profile 走」那個已知情況用的逃生口 — 錯了的代價是那個情況下第一次跑會拿到 "Gateway not configured properly"，要自己補 `--gateway`。`--port` 不給用 11740。
- Ruling: 專案裡不只一個裝置節點就拒絕並列出名字 — 下載到哪一台控制器沒有安全的預設值，也沒有旗標可以回答（D7） — 錯了的代價是真的有多裝置專案的人要等一個 `--device` 旗標；今天先讓它停下來說清楚。
- Ruling: 下載的 `-y` 走 `cds/ide/silent.py` 那張對話框表（新標題 `Confirm PLC Download`），不是在引擎裡直接讀 `command_args["yes"]` — 走那張表它才跟 `import` 的 `-y` 是同一個東西：`needs_input.arg` 自己就會是 `yes`，兩種形式與 `--json` 都不用特別處理 — 錯了的代價是 `tests/test_silent.py` 的 `DRIVEN_FILES` 要加 `engine/entry_plc.py`（那條測試會抓）。
- Ruling: `--gateway`、`--port` 走一個注入的全域 `command_args`（`silent.ARGS_GLOBAL`），不是新增一種呼叫慣例 — 這個 codebase 現有的每一個旗標都是某個對話框的答案，而閘道位址不是任何人被問過的問題，走不了那條路；引擎本體本來就靠 CODESYS 注入的全域（`system`、`projects`）拿東西，多一個同類的比改掉四支本體的呼叫形狀便宜。注入在 exec 之後做，所以本體寫的模組層預設值不會反過來蓋掉它 — 錯了的代價是現在只有一個檔案用它，讀 `entry_plc.py` 的人得先知道這個名字是誰放進來的（檔頭有寫）。
- Ruling: `plc` 也要 `--sync-dir` — 階段 2 收尾定的是「每一個有 `--project` 形式的命令都要，`config` 也不例外」，一條沒有例外的規則比一條「除了 plc」好記 — 錯了的代價是 `plc` 根本不讀同步資料夾，呼叫端還是要多打一個旗標。
- Ruling: `cdsint/cli.py` 拆出 `cdsint/flags.py` — 加完 plc 之後 cli.py 是 354 行，超過階段 2 那條「`cdsint/` 每個模組不超過 300 行」的驗收；拆的判準跟階段 2 那次一樣是「這段話是關於誰的」：命令列長什麼樣、哪些旗標組合不合法是一件事，解析完之後要做什麼是另一件 — 錯了的代價是多一個檔案要開；cli.py 回到 133 行，flags.py 250 行。
- Ruling: PLC 的暫存檔（本機 boot application、從控制器拉回來的 `.crc` 與原始碼封存）寫在 `%TEMP%\cdsint\plc\<專案名>\`，同一個專案每次覆蓋，而且每個檔案寫之前先刪 — 用固定路徑是為了不在 TEMP 留一串編號目錄，而固定路徑的代價就是「某次呼叫回來了但沒寫檔」會讓上一趟的答案被讀成這一趟的，所以先刪；`tests/test_plc.py` 有一條就是拿一個「回來但不寫檔」的假 IDE 釘住這件事 — 錯了的代價是同一個專案兩個 cdsint 同時跑 PLC 命令會互相踩；那件事今天不會發生，因為控制器一次只接一個。

階段 2 收尾二新增的：

- Ruling: `--target` 那半一行都沒改 — 它本來就是一個命令送一次、各等一次 `--timeout`，也就是新的語意；要改的只有把整個行程當成一次等待的 `--project` 那半 — 錯了的代價是無。
- Ruling: 寬限用量出來的數字乘上幾倍，不是「量到多少就寫多少」 — 這兩個常數只在「某件事掛住了」的時候起作用，太小會殺掉健康的執行（就是被修掉的那個 bug），太大只是晚一點才報告；不對稱的代價就該給不對稱的餘裕。啟動 180 秒是量到最慢（冷啟 47 秒）的將近四倍，因為 Delta 與 Lenze 比原廠慢、機器也可能在忙；關閉 60 秒是量到 2 秒的三十倍，它只要蓋住寫報告與行程收尾 — 錯了的代價是第一步就掛住的執行要等三分鐘才被殺掉；那是公式本身的代價（`--timeout` 綁的是一步，不是啟動）。
- Ruling: 「report 完不完整」用 `intended_exit` 在不在判斷，不另外加一個「我跑完了」的欄位 — IDE 側是 `run_job` 回來之後才寫檔，所以檔案存在就代表腳本跑到最後；`intended_exit` 從報告被建出來的那一刻就有值，讀不到它只有一個原因：這份報告不是那個腳本寫完的 — 錯了的代價是萬一以後有人改成中途就先寫一份報告，這個判斷會變成謊話；那時該做的是讓中途的那份不要帶 `intended_exit`。
- Ruling: 逾時但 report 完整的時候，`timed_out` 仍然是 true，只有 `error` 那句話不一樣 — 行程確實被殺了，那是事實，把它改成 false 是為了讓話好聽而說謊；要區分的是「這趟有沒有答案」，那件事由 `error` 與結果本身回答 — 錯了的代價是看板上「逾時次數」這種指標會把慢關的執行也算進去。
- Ruling: `error` 用附加的，不是覆蓋 — 「專案沒開起來」跟「行程被殺掉」可以同時成立，後者蓋掉前者會讓報告少掉真正的原因 — 錯了的代價是那個欄位偶爾會有兩段話。
- Ruling: 鎖檔清理只在「kill 之後 `wait` 沒有再逾時」的時候做 — 行程還活著就可能還在寫專案檔，這時清掉鎖，下一趟會開到寫到一半的檔；等不到就印一行說下一趟要 `--force-lock`，把判斷交回給人 — 錯了的代價是那種情況下使用者還是要打一次 `--force-lock`，跟今天一樣。
- Ruling: 為了守住「`cdsint/` 每個模組不超過 300 行」這條階段 2 的驗收，這一輪從 `headless.py` 搬出四樣東西：鎖檔的規則進新的 `cdsint/lock.py`；報告檔的預設路徑與「退出碼不可信」那句話進 `cdsint/report.py`；RUNASADMIN 的警告進 `cdsint/installs.py`；兩支從來沒有人呼叫過的 `exit_code()`（`headless.py` 與 `target.py` 各一支）直接刪掉（PRINCIPLES 7）。搬的判準是「這段話是關於誰的」：鎖是專案檔的事、報告路徑與那句警告是報告的事、要不要管理員是安裝的事 — 錯了的代價是多一個檔案要開；`headless.py` 從 350 行回到 297。

階段 2 收尾新增的：

- Ruling: `verify` 沒給 `-y` 的時候跑一趟 `compare`，不是直接拒絕 — 工單要的是「把匯入那步的計畫印出來（modified、new on disk、delete 各幾個）」，而 compare 就是四步裡唯一只讀的那一步，它回的 `different`／`new_on_disk`／`new_in_ide` 換個名字就是那三個數字。少了它，拒絕只能說「你少給一個旗標」，說不出「你要同意的是刪掉 229 個物件」，而後者才是使用者該看的東西 — 錯了的代價是 `--project` 形式沒給 `-y` 也要付一次 IDE 啟動（這次量到 23 秒，`--target` 形式因為 IDE 已經開著）。
- Ruling: 拒絕的時候多回一筆 `command` 是 `import` 的結果紀錄，`ok` False、`needs_input.arg` 是 `yes`、`data` 放那三個數字 — 那正是那一步「如果跑了」會長的樣子，所以兩種形式、`--json` 與人看的輸出全都不用特別處理它；SPEC 4.3 說 agent 讀 `needs_input.arg` 就知道要補哪個旗標，這樣它讀得到 — 錯了的代價是紀錄裡有一筆 IDE 其實沒跑過的步驟，`elapsed_s` 是 0.0。
- Ruling: 「有沒有 `.st`」的判斷跟 `scan_new_disk_files` 用同一套走訪規則（跳過 `.` 開頭的資料夾與檔案、跳過 `__pycache__`），所以函式就放在它旁邊（`engine/codesys_compare_engine.py`） — 匯入看不到的 `.st` 不能算事實來源，否則一個只剩 `.project\backup.st` 的資料夾會通過檢查，然後把專案清空 — 錯了的代價是這兩段走訪規則以後要一起改；放在同一個檔案相鄰兩支函式是今天能做到最接近「一份事實」的形狀。附帶影響：`tests/test_unhandled_objects.py` 那個用空資料夾的 fixture 現在要明講「假設資料夾裡有東西」（monkeypatch `has_st_files`），因為放一個真的 `.st` 進去會讓匯入走到確認對話框，那個對話框在 CPython 底下 import 不起來。
- Ruling: `--sync-dir` 是每一個有 `--project` 形式的命令都要，`config` 也不例外 — 一條沒有例外的規則比一條「除了 config」的規則好記，而且 `config set cds-sync-folder=X` 正是最需要講清楚「這一趟的事實來源是誰」的命令 — 錯了的代價是 `config get --project` 這種純讀的呼叫也要多打一個旗標。
- Ruling: 少給 `--sync-dir` 走 `parser.error()`，exit 2，不是 `Failure` 的 exit 1 — 這是「旗標組合不合法」，跟 `--target` 配 `--project` 同一類，argparse 那類錯誤本來就是 exit 2（階段 2 的驗收已經記過那個 2）；exit 1 是「命令跑了但失敗」 — 錯了的代價是 SPEC 4.3 的 2 那一格意思變寬了一點：本來只寫「找不到看門人或不只一個」，現在也涵蓋用法錯誤。
- Ruling: 解析同步資料夾在 CLI 側（`os.path.abspath`），不是 IDE 側 — IDE 行程的工作目錄不是 shell 的，相對路徑送過去會落在別的地方；而且報告要寫「這一趟用了哪個資料夾」，那個值必須在啟動之前就定下來 — 錯了的代價是無。
- Ruling: 那一行印在 stdout，但 `--json` 的時候不印；`sync_dir` 同時進每一筆結果紀錄，SPEC 4.3 跟著補一個欄位 — 一行散文擋在 JSON 前面會讓 `json.loads(stdout)` 直接壞掉，那正是要通知的對象；`--json` 的呼叫端改從紀錄裡讀同一個事實 — 錯了的代價是 SPEC 4.3 的欄位表多一個欄位要維護。

階段 2 新增的：

- Ruling: 無頭那趟的工作內容走一個環境變數指向的 JSON 檔（`CDSINT_HEADLESS_JOB`），不是一堆環境變數 — SPEC 6.4 那一列說「專案路徑走環境變數，不走 `--project` 也不走 `--scriptargs`」，理由是 `--scriptargs` 是一個字串、空白切開、引號規則自成一格，而專案路徑帶中文帶空白。一個檔案滿足同一個理由，而且順帶解決了下一個問題：命令清單、`--answer` 的答案、同步資料夾、報告路徑，每加一樣就要多一個環境變數，兩側各記一次名字。IronPython 那邊的 json 已經在 `cds/core/ipc.py` 上跑過真專案 — 錯了的代價是多一個暫存檔（寫在 report 旁邊，叫 `<report>.job.json`），而它同時也是「這趟到底叫它做什麼」的紀錄。
- Ruling: `park()`（`system.delay()` 那個迴圈）留在 `tools/`，不進 `cds/ide/headless.py` — 工單寫「`open_copy_and_watch.py` 與 `watch_harness.py` 併進 `cds/ide/headless.py` 後刪除（D16）」，而 D16 要消滅的是「開專案、設同步資料夾、存檔」這件事有兩份程式碼；那一半確實搬進去了。但 `park()` 用 `system.delay()`，SPEC D5 對這件事的措辭是「這條是絕對的，沒有例外」，把它放進 D5 管轄的那個目錄等於讓規則自己打自己。它現在在 `tools/headless_watch.py`，跑之前檢查 `system.ui_present`，有 UI 就拒絕停住並印一句為什麼 — 錯了的代價是 `tools/` 底下有一個會 `system.delay()` 的檔案，D5 的 grep 要記得它是例外；換來的是 `cds/ide/` 底下一個都沒有。這一條值得監督者裁。
- Ruling: 一次 `--project` 呼叫起一個 IDE 跑完整串命令，不是一個命令一個 IDE — `verify` 是四個命令，而起 IDE 加開專案要三十幾秒；四趟就是兩分鐘的純等待，而且每一趟都要再問一次那些 IDE 自己的提示。工作檔裡放的是 commands 陣列，IDE 側依序跑、第一個失敗就停 — 錯了的代價是一個命令壞掉會連累後面的，但那正是想要的：匯入做了一半就匯出，等於把半成品寫回磁碟再說「這一輪很乾淨」。
- Ruling: `verify` 的第三步是 `compare`，不是「比對同步資料夾的前後快照」 — SPEC 4.2 寫「import、export、比對磁碟有沒有 diff、build」。前後快照要先知道同步資料夾在哪，而 `--project` 形式在 IDE 開起來之前不知道（那是專案屬性），只能多起一次 IDE 去問。`compare` 回的 `data` 裡有 `different`、`new_in_ide`、`new_on_disk`、`moved` 四個數字，任何一個不是 0 就代表跑完一輪之後 IDE 跟磁碟還是不一致，那正是這一步要抓的 — 錯了的代價是「export 寫出來的位元組跟之前一模一樣」這件事沒有被直接驗；`compare` 驗的是「兩邊對每一個物件的看法一致」，比位元組比對寬一點。
- ~~Ruling~~（監督者在階段 2 驗收後推翻，見底下「`verify` 需要 `-y`」；`--force` 那半仍然成立）: `verify` 自己回答匯入的確認，但不自己回答版本不符 — 匯入就是 `verify` 的定義，SPEC 4.2 的表上 `verify` 也沒有 `-y`；問一個只有一個有用答案的問題不是謹慎。版本不符不一樣，它說的是「這個同步資料夾是別的版本寫的」，那是呼叫端該知道並決定的事，所以 `verify` 多一個 `--force` 轉交給匯入與匯出 — 錯了的代價是每個既有專案第一次跑 `verify` 都要帶 `--force`（`cds-sync-version` 還是 `k1.1.1`），這件事寫進第 7 節第 4 項給人看。
- Ruling: `--answer` 只在 `--project` 形式有效，不是共用旗標 — SPEC 4.2 把它列在「共用旗標」那一排，但那一排講的是「每個命令都有」，不是「兩種形式都有」。`--answer` 回答的是 IDE 自己彈的提示，而 `--target` 那半的 IDE 前面坐著一個人，那些提示是他的。收下一個什麼都不做的旗標比拒絕它更糟 — 錯了的代價是 SPEC 4.2 那一句要改（已改），而想在看門人那半預先回答 IDE 提示的人得自己想辦法。
- Ruling: `--project` 形式一律不預先回答 `UpgradeProjectConfirmation` — 來源 repo 的 `open_copy_and_watch.py` 預設答 Yes，並在註解裡說「只有指向丟棄用的副本才安全」。cdsint 的 `--project` 收的是使用者給的任何一個 `.project`，而答 Yes 會改寫它的儲存格式，改完原本那套 IDE 就再也開不了它。這正是 D7 說的「永不猜」 — 錯了的代價是每個舊版存的專案第一次都要人自己加 `--answer UpgradeProjectConfirmation=Yes`；訊息會告訴他是哪個鍵、答 Yes 的後果是什麼。
- Ruling: 「需要管理員」在 `cdsint installs` 裡指的是 ScriptDir 在 `Program Files` 底下，不含 `ProgramData` — 安裝器現在把 `C:\ProgramData\PLCDesigner\ScriptDir` 也當成要提權，而這台的 `icacls` 顯示那個目錄是 `Everyone:(F)`，Lenze 的安裝程式就是這樣建的。SPEC 5.3 的表也只在 Delta 那一列註「需要管理員」。`Program Files` 是唯一一個一般帳號一定寫不進去的位置 — 錯了的代價是某台機器的 `ProgramData` 真的被鎖起來時，`installs` 不會事先警告；安裝器仍然會在寫失敗時報出那一行。安裝器那條規則沒有跟著改，因為它試完才知道，報「存取被拒」比事先跳過一套裝得起來的 IDE 好。
- Ruling: 安裝掃描在 `cdsint/installs.py` 與 `irm/setup.ps1` 各寫一份，接受這個重複 — D16 禁的是同一件事有兩條路，而這裡是同一份知識（SPEC 5.3 的表）有兩個實作。安裝器沒辦法呼叫 `cdsint installs`：它是 `irm ... | iex` 跑的，那時候 Python 套件還沒裝。SPEC 5.3 是唯一的事實來源，兩邊都照它寫，而 `installs` 那條驗收（這台正好七套、兩套 Delta 要管理員）是釘住 Python 那份的 — 錯了的代價是加一家 IDE 要改兩個檔；漏改哪一個都會被那條驗收或安裝器的 `-List` 抓到。
- Ruling: 命令列組成單一字串傳給 `subprocess.Popen`，即使 Python 不需要 — SPEC 6.4 那一列的理由是 PowerShell 5.1 的陣列參數會重新加引號弄壞 `--profile="有空白的名字"`。CPython 的 `Popen` 收陣列時用的是自己的 `list2cmdline`，理論上也對，但那一列是踩出來的，而「理論上也對」正是它當初被寫下來的原因。照著原本那個形狀組字串，跟已經跑過真專案的那份一模一樣 — 錯了的代價是路徑裡有引號的話要自己處理；`.project` 路徑不會有。
- Ruling: `cds/ide/config.py` 自己寫 `{"ok", "summary", "data"}` 這個 dict，不呼叫 `engine/entry.py` 的 `result()` — D12 禁止 `cds/ide` import 引擎。三行字面值配一句指向 `engine/entry.py` 的註解，比為了一個 dict 把契約搬到 `cds/core/`（引擎至今一次都沒有 import 過 `cds`）便宜 — 錯了的代價是契約改形狀的時候有兩個地方要改；`tests/test_config.py` 會抓到。
- Ruling: `config set` 一定存檔，兩種形式都一樣 — 一個只活在記憶體裡的設定在專案關掉的時候就沒了，而無頭模式沒有人會禮貌地關它，行程直接結束。使用者那半也存，因為他要的就是一個留得住的設定 — 錯了的代價是他手上還沒存的編輯會跟著落地，所以 summary 明講「project saved」；存不進去（Delta 1.10 升級過儲存格式之後的 `save()`）就說這個設定只到專案關掉為止。
- Ruling: `config` 只讀寫 SPEC 4.4 表上有的名字，打錯就拒絕 — 寫一個沒有人讀的屬性是安靜的失敗，正是 D13 要消掉的那種。`config get` 不給名字時列出有值的那些，沒設過的就不列，因為 `""` 跟「從來沒設過」是兩件事 — 錯了的代價是 SPEC 4.4 加屬性的時候 `cds/ide/config.py` 要跟著加一行。
- Ruling: `entry_build.py` 的 build 訊息改成「先問哪些分類正在裝訊息，再要」，而且一次不說話就再 build 一次 — 這是階段 2 在 Delta 1.10 上量出來的兩層問題，都不是階段 2 造成的。ScriptEngine 4.0.0.0 的 `get_message_objects` 沒有單參數形式（用 CLR 反射列出來看，兩個多載都要 severity），只給 category 會丟 `Value cannot be null. Parameter name: category`；而且那個 category 還得正在裝著訊息，什麼都沒重編的 build 讓它空著，同一句話又出現一次。底下那一層更要緊：**Delta 一個行程裡的第一次 `app.build()` 不會真的編譯**（同一個 IDE 連跑三次：7.4 秒沒有訊息、31.7 秒 101 個警告、5.8 秒同樣 101 個），而 `--project` 形式一個行程只跑得到第一次，所以它會回報一份沒有編過的乾淨結果。修法是「連自己的摘要行都沒寫的 build 就再 build 一次；兩次都沒有就報告『這台 IDE 沒有產出任何 build 輸出』而不是 0 個錯誤」 — 錯了的代價是某個 IDE 上真的存在「乾淨而且完全不出聲」的 build，那種情況會被多編一次然後報成失敗；沒有量到這種 IDE，而假的綠燈比假的紅燈危險得多。這一條值得監督者裁：它動的是引擎，而工單把引擎品質排在階段 4。
- Ruling: `entry_build.py` 失敗時把 traceback 印到 stdout — 這一輪一開始只看得到 `Build process failed: 值不能為 null。參數名稱: category`，那句話是真的，但對「是哪一個呼叫說的」一個字都沒說，查它花掉一次無頭啟動。traceback 走 `stdout_tail` 回到呼叫端，summary 維持原樣 — 錯了的代價是失敗時的輸出長了十行。
- Ruling: `cds/ide/entries.py` 抽出來，watcher 與無頭共用 — 兩個呼叫端做的是同一件事（清 `sys.modules` 的 engine、exec 本體、把 build 的 IDE 訊息接到 stdout_tail、檢查 `--app` 有沒有被忽略），差的只有「怎麼被告知」與「答案寫到哪」。不抽的話那四十行要寫兩份，而它們正是最容易漂的那種 — 錯了的代價是 `cds/ide/` 多一個檔案。
- Ruling: `cdsint/` 拆成七個模組而不是工單寫的四個 — 工單第 4 節寫 `cli.py`、`headless.py`、`installs.py`、`plc.py`。加上兩種形式、`verify`、`config` 之後 `cli.py` 一定破 300 行，而那是這一階段的驗收。多出來的三個各有一句話說得清的職責：`target.py` 是 `--target` 那條路、`report.py` 是把紀錄印成字、`exits.py` 是 SPEC 4.3 那張表加一個帶著 exit code 的例外 — 錯了的代價是 import 多幾行；`plc.py` 仍然留給階段 3。

階段 1 新增的：

- Ruling: 攔截的地方是「一個迴圈處理一個物件」那一步，共兩處，不是 `classify_object` 一處 — 監督者的約束是「一個地方，不是五個呼叫點各包一層」。做的時候發現只包 `classify_object` 不夠：`find_all_changes` 的 Pass 1 在呼叫 `classify_object` 之前先讀 `obj.guid`，而缺外掛的物件每一個屬性都會丟例外，不只 `.type`。所以 `classify_object` 自己改成不丟例外（它是最常丟的那個讀取，登記簿也該歸它），另外在兩個走物件樹的迴圈各包一層 per-object 的 try：`codesys_compare_engine.find_all_changes` 的 Pass 1（原本沒有，這就是 compare 與 import 死掉的地方）與 `entry_export` 的主迴圈（原本就有，只是改成寫進登記簿）。兩處都是「這一個物件處理不了」這件事的同一個抽象層級，不是五個散在 `classify_object` 周圍的補丁 — 錯了的代價是以後多一個走物件樹的迴圈，作者要記得包一層；`grep -n "for obj in" engine/` 找得到它們。
- Ruling: 登記簿是 `engine/unhandled.py` 的模組層級狀態，不是傳進去的收集器 — 傳的話 `classify_object` 五個呼叫點各要多兩行，而且「記得收集」變成五個呼叫端都要遵守的規則；沒遵守正是這個 bug 的成因。IDE 側不開執行緒（SPEC D5），看門人一次跑一個命令，所以模組狀態是安全的，`_logger` 與路徑快取本來就是這個形狀 — 錯了的代價是誰在同一個行程裡同時跑兩個命令會拿到混在一起的名單；那本來就已經被 `silent.running()` 擋掉了。
- Ruling: 這一輪有物件處理不了，匯出就一個孤兒檔都不刪 — 分類不出來的物件算不出路徑，它的 `.st` 於是長得像孤兒；`--delete-orphans` 會把專案還需要的檔案刪掉，而這一輪正好沒有辦法分辨哪個檔是它的。監督者沒有要求這條，但它就在這次改動的爆炸半徑裡：`ok=False` 只是回報，刪掉的檔案救不回來 — 錯了的代價是跨家開專案時孤兒檔會一直累積，要用對的 IDE 開一次才清得掉，訊息裡有寫。
- Ruling: `data` 裡出現了清單（`failed_objects`），所以 `cdsint/cli.py` 的 `_report` 改成清單一行一項 — 我在階段 1 前半寫過「`data` 的值都是純量」那條，這裡推翻它：讀者真正要的就是那幾個物件的名字，塞成一個字串或只給數量都等於叫人再去別的地方查 — 錯了的代價是 `--json` 以外的輸出會變長，一個有 50 個失敗物件的專案會印 50 行。

- **請監督者裁：原廠 CODESYS 開 Delta 的專案時，`classify_object` 對缺外掛的物件丟 `SystemError`，整個 compare 與 import 就死了。** 現況是引擎自己前後不一致：匯出的迴圈每個物件包在 `try/except Exception` 裡，所以那 7 個物件被算進 `failed` 並用名字寫進 log，匯出照樣完成；`codesys_compare_engine.find_all_changes` 沒有包，所以 7 個物件讓 229 個物件的比對整個中止。這不是階段 1 造成的，`codesys_managers.classify_object` 與 `find_all_changes` 這次一行都沒動。要修的話是「照匯出那樣，報出名字然後跳過」，屬於引擎品質（階段 4 那條「碰到的函式順手把空白 except 改成具體例外」的鄰居）。工單階段 1 的驗收句要求原廠也四個都 exit 0，所以這一條擋著那句驗收；請裁定是現在修還是留到階段 4，以及那句驗收要不要改成「用專案自己的 IDE」。
- Ruling: `cds/ide/messages.py` 讀 IDE 的編譯訊息時，一則讀不出來不影響其他則 — 它的 docstring 本來就寫「never an exception，因為它是在已經有結果的編譯之後才跑」，但 `_first` 用 `getattr(item, name, None)`，而預設值只吃 `AttributeError`；缺外掛的專案裡有一則訊息讀 `.object` 會丟 .NET 的「The object GUID ... is not valid」，於是整個 `build` 的結果被一個 traceback 換掉。改成每則各自 try、`_first` 吞掉任何例外之後，同一個情境下 build 回報 502 errors 101 warnings 與 200 行錯誤清單 — 錯了的代價是某則訊息如果只有部分讀得出來，報出來的位置會少一半，但那比整份不見好。新增 `tests/test_build_messages.py` 釘住這件事。
- Ruling: 四支本體改成 `from engine import entry` 再叫 `entry.result(...)`，不 `from engine.entry import result` — 這是真跑出來的 bug：`entry_export.export_project` 的匯出迴圈裡有一個區域變數也叫 `result`，於是 `return result(True, summary, ...)` 變成 `TypeError: str is not callable`，在 IDE 裡跑真專案才炸出來，單元測試與那三支「放棄路徑」的測試都走不到那一行。`result` 在這個引擎裡是很常見的區域變數名，把一個函式用這個名字 import 進四個上千行的舊檔案就是在等著被遮蔽 — 錯了的代價是每個呼叫點多六個字元。順手把那個區域變數改名 `wrote`（它是「這個物件寫出去的結果」），把同檔的字典推導變數 `entry` 改名 `record`。
- Ruling: `cdsint import` 加上 `-y` 這個短旗標，`--yes` 保留 — SPEC 4.2 通篇寫的是 `import -y`，工單階段 1 的驗收句也是；程式碼裡只有 `--yes`，所以驗收照著打會被 argparse 拒絕。加一個 alias 比改規格與驗收都便宜，而且 `-y` 是這類確認旗標的通用寫法 — 錯了的代價是無，`--yes` 照樣能用。
- Ruling: 安裝器不管下載還是 clone，一律用 junction 指向本體的 `stub/`，不複製 stub — 工單寫「本體裝到 `%LOCALAPPDATA%\cdsint\` 或指向 clone、開發模式用 junction」，讀起來像兩條路（下載就複製、開發就 junction）。兩條路就是兩份 stub，升級時一個 IDE 的 ScriptDir 留著舊的、另一個是新的，而且 SPEC D16 明講不准並存。改成一條之後，下載模式與開發模式的差別只剩「本體從哪來」 — 錯了的代價是 ScriptDir 所在的磁碟如果不是 NTFS 就裝不起來；三家的 ScriptDir 都在 C: 底下，這個情況實務上不存在。
- Ruling: 安裝器認一套 IDE 的條件是它的執行檔在，不是目錄名字像版本號 — 這台機器上 `Lenze\PlcDesigner\` 底下有 `Targets` 與 `GatewayPLC`，`DIAStudio\` 底下有一個沒有版本號的 `DIADesigner-AX`，只看目錄名的話它們每一個都會被當成一套有自己 ScriptDir 的 IDE。加上執行檔檢查之後，`-List` 列出的正好是這台真正的五個 ScriptDir — 錯了的代價是某天有一套 IDE 把執行檔搬到別的相對位置，安裝器就會說「找不到任何 IDE」，得改那三條路徑。
- Ruling: 拿掉互動式的版本選單，改成 `-Version`（預設 `main`） — 選單要先去 GitHub 抓 tag 再 `Read-Host`，而這個 repo 一個 release 都還沒發，選單永遠是空的；更要緊的是 `Read-Host` 讓安裝器沒辦法自動驗收 — 錯了的代價是之後真的發了版，想裝舊版的人要自己打 `-Version v1.2.3`，不能從清單挑。
- Ruling: `body.path` 一律寫成沒有 BOM 的 UTF-8，stub 讀的時候用 `utf-8-sig` — 第一次跑無頭驗收就是掛在這個上面：`Set-Content -Encoding utf8` 在 PowerShell 5.1 會加 BOM，stub 於是把 `﻿C:\...` 插進 `sys.path`，IDE 丟 `ImportError: No module named cds.ide`。安裝器寫對是根治，stub 讀得寬是因為這個檔也可能是人用編輯器建的 — 錯了的代價是 stub 各多一行 import，`Project_export.py` 與 `Project_import.py` 剛好用到 15 行的上限。
- Ruling: `cds/ide/silent.py` 自己按名字把 `engine.codesys_ui` 載進來，載不到就整個不跑本體 — 這是修一個階段 0 留下的洞：來源 repo 的入口在模組層級用 `_load_hidden_module` 把 `codesys_ui` 塞進 `sys.modules`，階段 0 改成函式裡的 `from engine.codesys_ui import ...` 之後就沒有人在模組層級載它了，而看門人每次執行命令前都會清掉 `sys.modules` 裡的 engine，所以 `_install` 那句 `sys.modules.get(...)` 永遠是 None，三個對話框一個都沒被換掉。後果是 `cdsint import -y --target` 會在 IDE 裡開一個沒人能按的 WinForms 對話框，把 IDE 的訊息迴圈卡死 — 正是階段 1 驗收要跑的那條命令。SPEC D12 的字面是「`cds/ide` 不准 import 引擎模組」，這一行違反了字面；但 `silent.py` 本來就寫死 `UI_MODULE = "engine.codesys_ui"` 並且往裡面 setattr，這個相依早就存在，缺的只是讓它真的成立。載進來之後 `cds/ide` 仍然不使用引擎的任何東西，只是把三個函式換掉再換回去 — 錯了的代價是 D12 的 grep 會多一筆命中（`__import__(UI_MODULE)`），要在規則裡寫成例外。這一條值得監督者裁。
- Ruling: `choose_sync_folder` 回 `(folder, error)` 兩元組，跟 `load_base_dir` 同形 — 只回 `folder` 或 `None` 的話，呼叫端只能回報一句「沒設同步資料夾」，把真正的原因（沒開專案／使用者按了取消／寫不進專案屬性）吃掉，那正是 SPEC D13 禁止的 — 錯了的代價是多一個要解包的回傳值。
- Ruling: `entry_directory.py` 裡檢查 `_metadata.json` 專案路徑不符的那一段整段刪掉，不搬進 `engine/settings.py` — 現在的中繼資料檔叫 `sync_metadata.json`，`_metadata.json` 全 repo 只剩 `RESERVED_FILES` 裡一個字串，沒有任何地方會寫出它，所以那段是對著一個不存在的檔案跑的死碼（PRINCIPLES 7）。順帶消掉的還有它那個 `ask_yes_no("Update Metadata?")`，否則替身 UI 的答案表要多登記一個永遠答不出來的題目 — 錯了的代價是如果真有人手上留著遠古版本寫的 `_metadata.json`，設定同步資料夾時不會再被問要不要更新裡面的專案路徑。
- Ruling: 「存成相對路徑」只在選到的資料夾位於專案檔那一層或底下時成立 — SPEC 6.7 寫「存成相對路徑」，但專案外面的資料夾只能寫成 `..\..\shared`，那種路徑只在專案不搬家時才對，比絕對路徑更會騙人；不同磁碟則根本沒有相對形式 — 錯了的代價是把同步資料夾放在專案外面的人，換一台電腦時仍然會撞到電腦名稱不符的警告。
- Ruling: 所有面向使用者的訊息只提今天真的存在的做法 — 原本想寫「跑 `cdsint config set cds-sync-folder=...`」，但 `config` 是階段 2 才有的子命令，現在講等於叫人跑一個不存在的命令。改成「在 Project Information > Properties 加屬性，或從選單跑一次匯出」 — 錯了的代價是階段 2 做完之後，這三處訊息（`codesys_utils` 兩處、`silent._no_folder_dialog` 一處）要回頭補上 `config set` 這條路。
- Ruling: 狀態視窗的「設定」按鈕在沒有 callback 時整個不出現，不是變灰 — `cds/ide` 不能 import 引擎（D12），所以設定對話框是 `stub/Project_watch.py` 傳進 `session.main` 的；沒傳就是沒有，按不下去的按鈕比沒有按鈕更難解釋 — 錯了的代價是有人自己寫程式起看門人而忘了傳 `settings`，狀態視窗上就少一個按鈕，而且沒有訊息說為什麼。
- ~~Ruling~~（監督者在階段 1 驗收後推翻，見底下「有物件處理不了就 `ok=False`」那條）: 新的 `ok` 一比一複製舊的等級規則的判決，不順手改嚴 — 匯出有 3 個物件失敗、匯入有幾筆沒落地，今天都算成功（結尾呼叫的是 `system.ui.info`），summary 與 `data` 裡有 `failed` 的數字。改成「failed > 0 就 ok=False」是新的失敗模式，D11 要解的是「無害的 warning 讓好的匯出變 exit 1」，跟這件事無關；而且沒有資料說真專案的匯出平常會失敗幾個 — 錯了的代價是包 cdsint 的 pipeline 要自己讀 `--json` 的 `data.failed` 才知道有物件沒落地，光看 exit code 看不出來。這一條值得監督者裁。
- Ruling: 回傳值的建構收在 `engine/entry.py` 的 `result(ok, summary, **data)`，不在四支本體各寫 dict 字面值 — 契約只寫一次，`**data` 讓呼叫端自然寫成扁平的鍵值；`engine/entry.py` 本來就是「呼叫端與本體之間的契約」那個模組，加這個沒有多一份職責 — 錯了的代價是本體多一行 `from engine.entry import result`。
- Ruling: `data` 由看門人寫進結果檔（`commands.new_result(data=...)`），CLI 的 `--json` 與非 JSON 輸出都看得到 — 不接出去的話 `data` 就是死碼（PRINCIPLES 7）；而且場景 B 的 agent 要的就是這些計數。因此每個 `data` 的值都是純量，`cdsint/cli.py` 的 `_report` 一個鍵印一行才不會印出巢狀 repr — 錯了的代價是以後想在 `data` 裡塞清單，得先改 `_report` 的印法。
- Ruling: build 的 `data` 只放 `application`、`errors`、`warnings` 三個計數，錯誤清單不放進去 — 工單第 4 節寫「build 放錯誤清單」，但那份清單已經有一條路了：`cds/ide/messages.py` 從 IDE 的訊息庫讀，帶物件名與行號，比引擎自己格式化的那張表詳細，走 `stdout_tail` 出去。放兩份等於同一個事實兩條路（SPEC D16），而且會漂移 — 錯了的代價是 `--json` 的 `data` 裡沒有錯誤清單，要讀 `stdout_tail`。
- Ruling: `cds/ide/watcher.py` 的 `_wrong_application` 維持掃 `outcome.messages` 找應用程式名字，這次不改 — 它現在可以改讀 `data["application"]`，那樣更準（今天的 `wanted in message["text"]` 是子字串比對，`--app App` 會被 `AppB` 的訊息滿足），但那是另一個事實的推斷，不在本項的範圍內 — 錯了的代價是 `--app` 的檢查對名字互為前綴的兩個應用程式仍然會誤判。留給監督者決定要不要現在改。

階段 0 新增的：

- Ruling: stub 找本體用 `body.path` — 旁邊一個純文字檔，一行安裝根目錄，stub 讀它、插進 `sys.path`、import 本體。安裝器寫它，開發模式也寫它；它是機器專屬的路徑，所以 gitignore。沒有選「把路徑寫死在 stub 裡」是因為那樣安裝器得改寫 stub 原始碼，而開發模式的 junction 直接指著 repo 裡的 `stub/`，改它就是弄髒 git。也沒有留「找不到就往上兩層」的後路，那會變成兩條路（SPEC D16）— 錯了的代價是 clone 完還沒寫 `body.path` 之前，從選單跑任何一支都會丟 `IOError`，訊息不會告訴你該建那個檔。
- Ruling: `engine/` 裡入口本體叫 `entry_export.py`、`entry_import.py`、`entry_compare.py`、`entry_build.py`、`entry_directory.py`、`entry_parameters.py` — `import` 是 Python 關鍵字，`entry_import` 不是；前綴一致所以一眼看得出哪些是入口本體、哪些是共用引擎模組 — 錯了的代價是文件與 commit 訊息裡「Project_import.py」這個講法要改口，選單上的名字沒變。
- Ruling: 看門人跑本體用 exec 檔案，選單跑本體用 import 加借全域 — 替身 `system` 必須在本體的模組層級程式碼跑起來之前就在它的命名空間裡，所以 `silent.run` 沒辦法改成 import；選單那條沒有這個需求，`engine/entry.py` 把 stub 的 `globals()` 借給本體，本體自己定義的名字優先，跟原本 `dict(ide_globals)` 再 exec 完全等價。這不算 SPEC D16 的兩條路：同一件事只有一份程式碼，差的是誰負責提供命名空間 — 錯了的代價是本體要維持「`system` 從自己的模組全域讀」這個假設，不能改成參數傳入，否則兩邊都要跟著改。
- Ruling: `cds/ide/session.py` 的 `script_version()` 整支刪掉，版本號由呼叫端（`stub/Project_watch.py` 與 `tools/watch_harness.py`）自己 import — 工單原本寫「改成普通 import」，但那樣 `imp.load_source` 的 hack 雖然沒了，`cds/ide` import 引擎模組這件事還在，而 SPEC D12 禁的就是這個方向。兩個呼叫端都不在 `cds/ide` 底下，所以移過去之後 D12 三條規則一個例外都不剩 — 錯了的代價是兩個呼叫端各多一行 import。
- Ruling: 比對結果視窗與狀態視窗的標題、IDE 訊息列的 `cds-ide:` 前綴，階段 0 就改成 `cdsint` — 標題本來排在階段 1，但階段 0 的驗收 grep 會抓到比對視窗那一行，而且這一階段叫「搬家與身分」，產品名字就是身分 — 錯了的代價是階段 1 的「視窗標題改名」那一項會發現已經做完了。
- Ruling: `cdsint list` 找不到看門人維持 exit 0，不改成工單寫的 exit 2 — `list` 的問題是「有誰在聽」，空的清單是答案不是失敗，而且現有的 `test_list_says_so_when_nothing_is_listening` 就是在釘這個行為；SPEC 4.3 的 exit 2 講的是「這個命令需要一個看門人而找不到」，`list` 不需要。改它是 CLI 契約的變更，超出「階段 0 不改邏輯」，留給監督者裁 — 錯了的代價是包 cdsint 的腳本如果拿 exit code 判斷「有沒有 IDE 在聽」會失準，要改讀 `--json` 的空陣列。
- Ruling: `irm/setup.ps1` 階段 0 只換名字與 URL，不改安裝佈局，檔頭加「還不能跑」的警告 — 它現在會把整棵樹倒進一個 ScriptDir 資料夾，而 IDE 是遞迴掃的，選單會列出 `engine/`、`tools/`、`tests/` 底下每一支 `.py`；要修就是階段 1 的重寫，硬塞進階段 0 等於把搬家跟改行為混在一起 — 錯了的代價是這段期間 `irm/setup.ps1` 是不能用的，安裝只能照 readMe 手動做，這件事寫在檔頭與 `irm/setup.md` 開頭。

監督者已裁的：

- Ruling（階段 3 驗收後）: worker 階段 3 的十二條 Ruling 全部接受 — `denied` 獨立欄位（exit 5 從紀錄決定不從字串猜）、只有 `MATCH` 才 exit 0 且 `UNKNOWN` 跟 `DIFFERENT` 同樣非零（比不出來不能讀成一致）、權限攔在按下本體之前、多裝置專案拒絕、`--gateway` 沒給就不動專案設定，每條都有理由與代價 — 錯了的代價是無。
- Ruling（階段 3 驗收後）: `engine/entry_plc.py` 607 行違反新碼的 400 行硬上限，排進階段 4 拆，不擋階段 3 — 拆檔不改行為，而 PLC 這兩個命令在台架驗過之前本來就不會發版；階段 4 就是品質階段 — 錯了的代價是拆完要再跑一次 IronPython 的 import 探針。
- Ruling（階段 2 收尾二驗收後）: worker 收尾二的七條 Ruling 全部接受，包括 `timed_out` 在 report 完整時仍為 true（事實就是被殺了，區分「有沒有答案」的是 `error` 與結果）、寬限常數取量到的數倍（它們只在掛住時起作用）、`cdsint/lock.py` 獨立出來 — 每條都有理由與代價 — 錯了的代價是無。
- Ruling（階段 2 收尾驗收後）: worker 收尾的七條 Ruling 全部接受，包括沒 `-y` 時仍跑一趟 `compare` 來印計畫（多付一次 IDE 啟動，換來「你要同意的是刪 229 個」這句話，值得）與 `--sync-dir` 連 `config` 都要（一條沒有例外的規則） — 錯了的代價是 `config get --project` 多打一個旗標。
- Ruling（階段 2 收尾驗收後）: `--timeout` 是每一步的上限，`--project` 形式的行程期限從它推導，不另設一個「無頭專用的預設」 — 一個旗標兩種意思是特殊情況；推導公式讓 `--timeout 120` 在兩種形式下說的都是「一個命令最多 120 秒」 — 錯了的代價是 `--project` 形式的實際等待上限比旗標的字面值大，文件要講清楚。
- Ruling（階段 2 收尾驗收後）: 逾時以 report 為準；kill 掉自己起的 IDE 之後清掉它留下的鎖檔 — 兩件都是「cdsint 知道的事不要假裝不知道」：report 完整就不是對話框卡住，鎖是自己造成的就不該要使用者 `--force-lock` — 錯了的代價是若 kill 的行程其實還在寫專案檔，清鎖會讓下一趟開到半寫的檔；用 kill 之後等行程真的不在了再清來擋。
- Ruling（階段 2 收尾驗收後）: 匯出寫檔失敗沒進登記簿這件事排階段 4 第一項，不當階段 2 的收尾 — 它在引擎的寫檔層，跟階段 2 的無頭前門無關，而且階段 3 完全不碰匯出；先把階段 2 的兩個前門問題收掉再進 3 — 錯了的代價是階段 3 期間這個洞多活一陣子，但它只在路徑超長時出現。
- Ruling（階段 2 驗收後）: `verify` 需要 `-y`，推翻 worker「匯入就是 verify 的定義，問一個只有一個答案的問題不是謹慎」那條 — 那個問題有第二個有用的答案：同步資料夾指錯的時候，「不要」就是唯一對的答案。監督者用一個空的 `--sync-dir` 重現，verify 第一步就把 229 個物件裡的 178 個刪掉並存檔。SPEC 4.2 對 `-y` 的定義是「確認這一步會改狀態」，verify 含匯入，就該跟匯入共用同一條規則，一條規則沒有例外 — 錯了的代價是 pipeline 的呼叫多打兩個字元。
- Ruling（階段 2 驗收後）: 同步資料夾裡一個 `.st` 都沒有時 `import` 拒絕，三條路一致 — 「磁碟是事實來源」的前提是磁碟上有一份事實；空資料夾不是「什麼都沒有」這個事實，是「還沒 export」或「路徑指錯」，兩種都該停下來。這跟「登入中拒絕匯入」一樣是前置檢查，不是門檻式的啟發 — 錯了的代價是真的想把專案清空的人要自己動手；那種需求不存在。
- Ruling（階段 2 驗收後）: `--project` 形式必給 `--sync-dir` — 副本帶著原專案的 `cds-sync-folder`，那可能是指向使用者 git 目錄的絕對路徑；scenario C 的呼叫端本來就知道兩個路徑，讓它明講比讓 cdsint 從副本的屬性猜安全 — 錯了的代價是每次呼叫多一個旗標，分紙機 Makefile 的行多一個參數。
- Ruling（階段 2 驗收後）: worker 階段 2 其餘的 Ruling 全部接受，包括 `park()` 留在 `tools/headless_watch.py`（D5 管的是產品的 IDE 側，測試用的支架撐住一個 `--noUI` 行程不算，SPEC D5 現況已註明）與 `entry_build.py` 在 Delta 上 build 兩次（跟階段 1 那條同形：擋著驗收、而且會把騙人的綠燈帶進下一階段） — 錯了的代價是 D5 的 grep 多一筆例外要記得。
- Ruling（階段 2 驗收後）: 真 IDE 驗收從此一定含一個「剛複製、同步資料夾是空的」情境 — worker 兩次驗收都用已經一致的副本，正好繞過最危險的路徑；監督者的重現才撞到 — 錯了的代價是每次驗收多兩分鐘。
- Ruling（階段 2 驗收後）: 第 7 節第 7 項（既有專案的 `cds-sync-version` 還是 `k1.1.1`）留給使用者，等基本開發做完一起處理；期間 `verify`／`import` 帶 `--force` — 這是使用者的專案設定 — 錯了的代價是無。
- Ruling（階段 1 收尾驗收後）: worker 收尾的四條 Ruling 全部接受 — 攔截點放在「一個迴圈處理一個物件」那一步（兩處）而不是 `classify_object` 一處，理由成立：缺外掛的物件每個屬性都丟例外，只包分類那一行擋不住 Pass 1 讀 `obj.guid`；登記簿用模組層級狀態，在 D5 單執行緒、一次一個命令的前提下是安全的，而且省掉五個呼叫點各自「記得收集」的規則；有物件處理不了就不刪孤兒檔，這是 worker 自己看出來的爆炸半徑，`ok=False` 只是回報、刪掉的檔案救不回來，這條比監督者要求的多想了一步；`_report` 改成清單一行一項是 `data` 出現清單的必然結果 — 錯了的代價：登記簿若有一天 IDE 側出現第二條執行路徑（D5 改了），它會混在一起；那時 D5 本身就是更大的事。
- Ruling（階段 1 驗收後）: `classify_object` 丟例外的問題**現在修，當階段 1 的收尾**，不留到階段 4 — 它擋住的是「跨家開專案」這個真實情境，而且階段 2 的 `verify` 會把 compare 與 import 串在一起跑，留著等於把一個已知會整個死掉的路徑帶進下一階段的驗收。修法的約束寫在階段 1 收尾那一項：一個地方處理、名字進 `data`、`ok` 為 False — 錯了的代價是階段 1 多一個 commit 的引擎改動，跟「階段 1 改行為」的定位一致。
- Ruling（階段 1 驗收後）: 有物件處理不了就 `ok=False`，推翻 worker「`ok` 一比一複製舊判決、7 個失敗仍算成功」的做法 — 磁碟是事實來源（SPEC 目標 1），少 7 個物件的匯出不是完成；場景 C 的 pipeline 拿 `ok` 當閘門，一個放行「有 7 個沒匯出」的閘門是壞的；D13 要的「以名字報出來」靠 `data` 滿足，`ok=False` 讓呼叫端不用先讀 `data` 才知道要讀 `data`。同一家 IDE 開自己的專案時 failed 是 0，所以日常路徑沒有任何變化 — 錯了的代價是某天出現「有一個物件永遠處理不了但大家都不在乎」的專案，每次同步都 exit 1；那時該修的是引擎或 profile，不是把閘門放寬。
- Ruling（階段 1 驗收後）: `cds/ide/silent.py` 以字串名字載入 `engine.codesys_ui` 這件事，接受為 SPEC D12 的唯一例外並寫進規格 — 替身 UI 的工作就是把引擎的三個對話框函式換掉，這個相依在來源 repo 就存在，只是以前靠入口腳本順手載好；知識方向沒有反過來，引擎仍然不認識 `cds/ide`。更乾淨的做法是本體改成接一個 `ui` 參數不再猴子補丁，但那要動 `codesys_utils` 裡每一個對話框呼叫點，現在沒有理由做 — 錯了的代價是 D12 的 grep 規則多一行例外，已寫進 SPEC D12 現況。
- Ruling（階段 1 驗收後）: 原廠的真 IDE 驗收改用 softplc 副本，Delta 用 Shm 副本，階段 2 的 `verify` 驗收同樣分開 — 工單原本一句「原廠與 Delta 各跑 Shm」是監督者寫錯，Shm 是 Delta 建的專案，原廠沒有它的裝置描述與函式庫，build 不可能是 0 errors — 錯了的代價是無，softplc 就是上一輪在原廠驗過的那個。
- Ruling（階段 1 驗收後）: worker 階段 1 其餘的 Ruling（`-y` 別名、`entry.result` 不裸 import、`messages.py` 一則壞訊息不毀整份、安裝器一律 junction、認 IDE 看執行檔、拿掉互動選單）全部接受 — 每一條有理由與代價，`-y` 那條是規格與程式碼不一致而規格是對的 — 錯了的代價是無。
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
