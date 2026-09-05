# 產品規格：cdsint

> 狀態：草稿，2026-09-05，同日審查後改寫一次。
> 這份文件描述「做完之後的樣子」，不是施工順序。施工順序在第 10 節。
> 每一條規格後面若標了「現況」，表示這件事現在的程式碼已經做到或還沒做到。
> 所有規則只寫在第 3 節的決策表裡，其他章節和程式碼註解用 D 編號引用，不重抄內容。
> 程式碼來源是 `kevin-cds-text-sync`（`C:\Users\qazsskevin\Documents\repo\kevin-cds-text-sync`，分支 `fix/member-creation-parent-resolution`，commit 9aa9886）。本 repo 只從它讀，不寫回去。各條「現況」指的是來源 repo 的狀態。

---

## 0. 一句話定位

**磁碟上的 `.st` 文字檔是 PLC 專案的事實來源，cdsint 負責把它和 CODESYS 系列 IDE 之間的搬運、驅動與驗證做成可以從外面呼叫的東西。**

名字的拆法：`cdsint` 是產品，`cds-sync-` 是它底下同步功能的屬性前綴，兩者不衝突（D9、D10）。

跟上游 cds-text-sync 3.x 與 CODESYS 官方 MCP Server 的差別，就是 cdsint 存在的理由：

| | cdsint | 上游 3.x | 官方 MCP Server |
|---|---|---|---|
| 事實來源 | 磁碟 `.st` | XML 快照，文字模式是選配 | IDE 裡開著的專案 |
| 命令執行期間之外，IDE 能不能用 | 能 | 不能，daemon 用 `time.sleep` 佔住主執行緒 | 能 |
| IDE 側相依 | 只要 IDE 本身 | 另裝 Python 3.11 加 pywebview | 付費訂閱 |
| 支援的 IDE | 原廠 SP17 到 SP21、Lenze PLC Designer、Delta DIADesigner-AX | 宣稱 SP10 以上 | SP22 以上原廠 |
| IDE 關著也能跑 | 能，無頭模式 | 不能 | 不能 |

---

## 1. 誰用、怎麼用

三個場景，cdsint 都要支援，而且用的是同一套引擎。

**場景 A，工程師的日常。** IDE 開著專案，旁邊開 VS Code 改 `.st`。改完在 IDE 的 Scripts 選單按「匯入」，或在終端機打一行命令。IDE 在兩次命令之間完全可以操作。

**場景 B，AI agent 的迴圈。** agent 沒有辦法看 IDE 的視窗，只能讀檔案和命令輸出。它改 `.st`、跑 compare 看差異、跑 import 送進 IDE、跑 build 拿錯誤清單、修、再來一次。所有對話框都由命令列旗標回答，沒有旗標就回報「需要哪個旗標」而不是掛住（D7）。

**場景 C，pipeline。** IDE 沒開。`make` 或 CI 起一個無頭的 IDE 行程，開專案副本，匯入、匯出驗證、編譯、產出開機應用程式、比對 CRC、視需要下載到台架。整趟沒有人在鍵盤前。

---

## 2. 目標與非目標

### 目標

1. 磁碟文字是事實來源。磁碟上有、IDE 沒有的 `.st` 就建出來；建不出來就報錯，說明是哪個檔、為什麼。
2. IDE 開著的時候可以被外部驅動，而且在命令與命令之間 IDE 完全可以操作。
3. IDE 側只需要 IDE 自帶的 IronPython 2.7 與標準函式庫，不需要另裝任何東西。
4. 原廠 CODESYS 3.5 SP17 到 SP21、Lenze PLC Designer 3.24 與 4.0、Delta DIADesigner-AX 1.8 與 1.10 都能裝、都能跑。
5. IDE 關著的時候可以無頭跑同一套引擎。
6. 每一次靜默失敗都是 bug。物件沒匯入、檔案沒匯出、對話框沒人答，都要以物件名稱或檔名報出來（D13）。
7. 會改變 PLC 的動作要有明確的授權，預設拒絕（D8）。

### 非目標

- 不重寫同步引擎。引擎裡的 GUID 表、成員建立、裝置改名、pragma 這些知識全是真專案撞出來的，重寫的人不會在第一週發現自己少了什麼。
- 不做靜態分析、FSM 圖、格式化、SVG 轉視覺化、PLC 變數即時讀寫。上游有，cdsint 不追。
- 第一版不做 HTTP 或 MCP 伺服器。CLI 的 `--json` 已經是機器可讀的，要包 MCP 是 IDE 外的事，隨時可以加，而且不動命令交接的協定（D6）。
- 不做線上變更（online change）。下載一律是完整下載。
- 不做多使用者或跨網路。命令目錄在本機使用者的 `%LOCALAPPDATA%` 底下，誰登入這台機器誰能下命令。

---

## 3. 已定案的決策

每一條有編號、決定、理由、現況。其他章節只引編號。

**D1 開新 repo `cdsint`，程式碼從 `kevin-cds-text-sync` 搬過來，不重寫。**
理由：產品換名字、目錄佈局整個換，在舊 repo 原地改等於每個檔案都搬一次還要顧舊路徑；新 repo 的 git 歷史從搬家那一刻開始，舊歷史留在來源 repo。引擎、看門人、CLI 的程式碼原封搬過來再整理，理由跟非目標第一條一樣：引擎裡的知識是真專案撞出來的。上一次「乾淨重來」的 `cds/` 骨架就是因為從零寫，階段 0 到 3 一格沒打勾就被刪了。
現況：本 repo 剛 init，只有規格、工單、授權、專案指示。

**D2 一個引擎，一個 CLI 命名空間，模式由旗標決定。** `--target X` 走開著的 IDE 裡的看門人，`--project P --install I` 起一個無頭 IDE。兩組旗標互斥。
理由：兩個場景互斥，CODESYS 會擋第二個行程開同一個專案檔，所以同一條命令不會兩邊都能走。但兩邊做的是同一件事，給它們兩套詞彙只會讓子命令各自長出只有一邊有的東西。不自動偵測，因為那會讓旗標需求隨執行期狀態變，而且意外的二十秒 IDE 啟動是最難查的那種驚喜。
現況：兩半都有（階段 2）。`--target` 是 `cdsint/target.py`，`--project` 是
`cdsint/headless.py` 配 `cds/ide/headless.py`。兩者對外都是 `run(steps)`，所以 `verify`
只寫一次。argparse 用互斥群組擋住同時給。

**D3 IDE 的 Scripts 選單只有三個入口：匯出、匯入、看門人。本體放在 ScriptDir 外面。**
理由：選單是遞迴掃 ScriptDir 底下所有 `.py`，上游 v2.9.0 實測連隱藏屬性都躲不掉。
現況：選單有十一項，整個 repo 用 junction 掛在 ScriptDir 底下。

**D4 IDE 側程式碼是 IronPython 2.7 可跑的 Python 2/3 相容碼，標準函式庫限定。CPython 3 只存在於 IDE 外。**
理由：目標 3。
現況：已做。

**D5 IDE 內等待命令用 WinForms 計時器掛在 IDE 訊息迴圈上，腳本立刻返回。IDE 側不准 `time.sleep()`、不准 `system.delay()`、不准開執行緒、不准 `execute_on_primary_thread`。** 這條是絕對的，沒有「背景執行緒不碰 API 就可以」的例外。
理由：`system.delay()` 不處理滑鼠鍵盤，`execute_on_primary_thread` SP21 拿掉了，CODESYS API 不是執行緒安全的。整個 IDE 側只有一種併發模式，比一條寫得精確的例外值錢。計時器設計在 ScriptEngine 4.0.0.0 與 4.2.0.0 都有真人驗過。
現況：看門人已經是這樣。`engine/codesys_ui.py` 的 `show_toast` 開一條 .NET Thread 在裡面 sleep 三秒，是唯一的違反者，階段 4 改成 Timer。`engine/codesys_utils.py` 有一把 `threading.Lock`，單執行緒設計下是空轉的，同一階段決定去留。
`tools/headless_watch.py` 的 `park()` 用 `system.delay()`，那是這條規則唯一被允許的地方，而且只在 `--noUI`：沒有視窗就沒有畫面會凍住，而沒有東西撐著行程的話 IDE 在腳本返回的瞬間就結束，看門人一次 tick 都跑不到。它在跑之前檢查 `system.ui_present`，有 UI 就拒絕停住，所以這個例外離不開它成立的那個情況。它是驗收用的工具，不在 `cds/ide/` 底下。

**D6 命令交接用檔案協定，不換 named pipe、不換 HTTP。**
理由：現有協定已經跑過真專案，IronPython 與 CPython 都只需要標準函式庫。
現況：已做，協定規格在 `docs/WATCHER.md`。

**D7 cdsint 自己的對話框由旗標回答，永不猜。沒有旗標就回 `needs_input`。** IDE 自己的提示不在這條的範圍內：無頭模式下它們走 `system.prompt_answers`，由 `--answer KEY=VALUE` 填，沒填到的取 IDE 的預設值並把鍵名記進 report。
理由：場景 B 的前提是 agent 看不到視窗。IDE 內建提示那半是 IDE 在猜不是 cdsint 在猜，規格得老實寫這條界線，不能宣稱全面不猜。
現況：都有（階段 2）。替身 UI 在 `cds/ide/silent.py`，兩種形式共用。`--answer` 是
`--project` 形式的旗標，填進 `system.prompt_answers`；一個都不預設，因為
`UpgradeProjectConfirmation` 答 Yes 會改寫專案的儲存格式，之後舊版 IDE 就開不了它。
沒答到的提示靠 `LogMessageKeys` 把鍵名印到 stdout，訊息會說去補哪個 `--answer`。

**D8 只有碰 PLC 的動作受權限管，兩層。** 專案屬性 `cds-sync-plc` 決定這個專案允不允許，`-y` 確認這一次呼叫。看門人模式一律拒絕 PLC 命令。
理由：一個 agent 下錯命令現在能直接下載到 PLC。`export`、`import`、`compare`、`build` 不碰硬體，把它們放進權限清單只會讓每個命令多一次預檢，換來三個場景都用不到的功能。看門人跑在使用者的 IDE 裡，登入會搶走使用者的線上狀態。
現況：沒有。

**D9 產品名是 `cdsint`。** 同一個字串用在 pip 套件、Python 套件、命令、`%LOCALAPPDATA%` 目錄、ScriptDir 子資料夾、視窗標題。
理由：上游同名、93 顆星，readMe 與安裝腳本到今天還指著上游。沒有連字號，所以 pip 名、import 名、命令名不用兩種拼法。`cds-ide` 會跟它驅動的 IDE 撞名，寫文件時每句都得多解釋一次。
現況：readMe、junction、實例目錄都還叫 `cds-text-sync`，CLI 叫 `cds-ide`。

**D10 專案屬性前綴留 `cds-sync-`，不跟產品名走。**
理由：它描述的是同步功能，不是產品。改名要掃 13 個檔案，再加一段對每個現有 `.project` 跑的遷移，收益是零。除了手動加屬性以外沒人看得到原名。
現況：13 處字面值，沒有集中的常數。階段 4 收成一個。

**D11 四支入口回傳結果，替身 UI 讀回傳值判斷成功失敗。**
理由：現在四支 `main()` 不管成功失敗都回 `None`，替身 UI 只能看 `system.ui.warning` 和 `error` 有沒有被呼叫來推。這讓「warning 只准在中止點呼叫」變成所有未來作者都得記住的規則，違反的後果離現場很遠：有人在匯出中途寫一句無害的 warning，一次成功的匯出就變成 exit 1。
現況：已做（階段 1）。回傳的形狀是 `engine/entry.py` 的 `result(ok, summary, **data)`，替身 UI 讀 `ok`；回傳 `None` 算失敗。`ok` 的意思是「這個命令把該做的每個物件都做完了」：任何一個物件分類不出來、建不出來、匯不出去，`ok` 就是 False，名字列在 `data` 裡（D13）；命令仍然把其他物件做完，不中途放棄。

**D12 三條可以用 grep 驗的分層規則。** `cds/core` 不准 import `system`、`projects`、`online`、`clr`。`cds/ide` 不准 import `online`，不准 import 引擎模組。引擎不准 import `cds/ide`。
理由：`cds/core` 要在 CI 上被完整測。`cds/ide` 只做管線，也就是協定端點、計時器、替身 UI、prompt 答案、狀態視窗、無頭模式的 `projects.open`。走物件樹和碰 PLC 的事全在引擎。依賴方向是 `cds/ide` 用入口名字驅動引擎，不反過來。
現況：三條都成立。唯一例外是 `cds/ide/silent.py` 以字串名字載入 `engine.codesys_ui`，只為了把三個對話框函式換成替身再換回去，不呼叫它任何東西；程式碼用 `__import__` 並附註解說明，grep 規則以 `from engine`、`import engine` 為準。原本 `session.py` 讀版本號的例外在階段 0 消失了。

**D13 不准靜默跳過物件。** 分類不出來、建不出來、匯不進去都要以名字報出來。
理由：目標 6。
現況：階段 1 做了「報出來」那一半。`engine/unhandled.py` 是一次命令的登記簿，處理不了的物件以名字記在那裡，`export`、`compare`、`import` 三個命令把它寫進回傳結果的 `data.failed_objects`並讓 `ok` 是 False（D11）。攔的地方有兩處，各是一個迴圈的「處理這一個物件」那一步：`classify_object` 自己不再丟例外，`find_all_changes` 的 Pass 1 與匯出的主迴圈各包一層。匯出還多一條：這一輪有物件處理不了就不刪孤兒檔，因為分不出哪個檔屬於它們。引擎裡仍有 119 處空白 `except:`，見 6.1。

**D14 帳密不准出現在命令列、檔案、report 裡。** 只從環境變數讀。
理由：report 會進 git 或被貼到工單。
現況：探路腳本已經這樣做。

**D15 `.st` 格式與 pragma 名稱不准改。** 要改就是一個大版本。
理由：現有專案的 git 歷史都是這個格式，這是相容性的底線。
現況：格式定義見 4.5。

**D16 不准留新舊兩條路並存。** 換掉就刪掉。
理由：PRINCIPLES.md 不留死碼。上次 `cds/` 骨架就是這樣被清掉的。
現況：無。

---

## 4. 使用者看得到的東西

### 4.1 IDE 選單

`Tools > Scripting > Scripts` 底下只有三項（D3）：

| 入口 | 做什麼 | 現況 |
|---|---|---|
| `Project_export.py` | 把 IDE 專案寫成 `.st`。第一次執行時若沒設同步資料夾，先走設定流程（6.7） | 已做（階段 1） |
| `Project_import.py` | 把 `.st` 讀回 IDE，磁碟贏。同樣先走設定流程 | 已做（階段 1） |
| `Project_watch.py` | 啟動看門人，腳本立刻返回；再跑一次就停止 | 有 |

比對、編譯、診斷、資源統計、效能量測都不出現在選單。比對和編譯由 CLI 呼叫。其餘搬到 `tools/`。

### 4.2 CLI

命令名 `cdsint`，CPython 3.11 以上，只依賴標準函式庫，透過 `pyproject.toml` 裝成 console script。套件名不可以叫 `cli`，上游 v2.9.0 就是因為 `cli` 這個頂層套件名跟使用者自己的目錄撞名才改的。

每個命令有兩種形式（D2）。`--target X` 找開著的 IDE 裡的看門人，`--project P --install I` 起一個無頭 IDE。兩組旗標互斥，argparse 直接擋。

| 命令 | `--target X` | `--project P --install I` | 做什麼 |
|---|---|---|---|
| `installs` | 不適用 | 不適用 | 列出這台的 IDE、profile 名稱、要不要管理員 |
| `list`、`ping`、`status`、`stop` | 有 | 不適用 | 看門人的生命週期，不受權限管 |
| `export [--delete-orphans]` | 有 | 有 | 把 IDE 專案寫成 `.st` |
| `import -y [--force]` | 有 | 有 | 把 `.st` 讀回 IDE，磁碟贏 |
| `compare` | 有 | 有 | 列出 IDE 與磁碟的差異 |
| `build [--app NAME]` | 有 | 有 | 編譯，回錯誤清單 |
| `verify` | 有 | 有 | import、export、比對磁碟有沒有 diff、build，一次跑完 |
| `plc connect [--gateway IP --port N]` | 拒絕 | 有 | 唯讀：列檔案、拉 `Application.crc`、比對 |
| `plc download -y` | 拒絕 | 有 | 完整下載、寫開機應用程式、啟動、比 CRC |
| `config get`、`config set KEY=VALUE` | 有 | 有 | 讀寫 4.4 的屬性，`cds-sync-plc` 除外 |

共用旗標：`--timeout 秒`（預設 120）、`--json`。
只在 `--project` 形式有效：`--profile NAME`、`--report 檔案`、`--force-lock`、`--sync-dir D`、
`--answer KEY=VALUE`（可多個，D7）。`--answer` 回答的是 IDE 自己的提示，而 `--target` 那半的
IDE 前面坐著一個人，那些提示是他的，所以它不放在共用那一排。

`-y` 的意思統一是「確認這一步會改狀態」，`import` 和 `plc download` 共用。沒給就印出這趟會做什麼，回 `needs_input`，exit 1，什麼都不改。沒有 `-N`，因為沒給 `-y` 就已經是「不做」，其他有安全預設值的對話框各自有具名旗標，`--force` 答版本和電腦不符，`--delete-orphans` 答刪孤兒。

`plc` 命令拒絕 `--target` 形式的原因見 D8。

### 4.3 Exit code 與輸出

| Exit code | 意思 |
|---|---|
| 0 | 完成 |
| 1 | 命令失敗，包含缺旗標的 `needs_input` |
| 2 | 找不到看門人，或符合的 IDE 不只一個 |
| 3 | 逾時 |
| 4 | 無頭模式：專案被別的行程開著，或 IDE 啟動失敗 |
| 5 | 權限拒絕：專案屬性 `cds-sync-plc` 沒有開放這個命令 |

2 和 4 是同一個問題的兩種原因，都是「這個專案有沒有活著的 IDE」，對 agent 有用所以分開。`list` 不在 2 的範圍內：它問的是「有誰在聽」，一個都沒有時印一句話、`--json` 給空陣列、exit 0，因為空清單是答案不是失敗。`needs_input` 不獨立成一格，因為 agent 反正得讀 JSON 裡的 `needs_input.arg` 才知道該補哪個旗標，獨立的 code 省不掉那次解析。

`--json` 輸出的結構沿用現有結果檔：`ok`、`command`、`elapsed_s`、`messages`、`stdout_tail`、`error`、`needs_input`、`data`。`--project` 形式再加 `ide`（用了哪套）、`report_path`。

### 4.4 專案屬性

設定存在 `.project` 的專案屬性裡，不進 git。前綴 `cds-sync-` 不跟產品名走（D10），程式碼裡收成一個常數。

| 屬性 | 意思 | 預設 |
|---|---|---|
| `cds-sync-folder` | 同步資料夾，可相對於專案檔 | 無，第一次執行時問 |
| `cds-sync-pc` | 設定時的電腦名稱，不同就警告 | 設定時寫入 |
| `cds-sync-version` | 上次同步用的工具版本，不同就警告 | 每次同步寫入 |
| `cds-sync-debug` | 開了才寫 `sync_metadata.json` 與 `*.log` | false |
| `cds-sync-export-xml` | 視覺化、警報、文字清單另存 XML | false |
| `cds-sync-backup-binary` | 匯出時複製一份 `.project` 到同步資料夾 | false |
| `cds-sync-safety-backup` | 匯入前備份 `.project` | true |
| `cds-sync-backup-name`、`cds-sync-backup-retention-count` | 備份檔名與保留數 | 空、10 |
| `cds-sync-save-after-import`、`cds-sync-save-after-export` | 同步後存檔 | true |
| `cds-sync-auto-delete-orphans` | 匯出時自動刪磁碟孤兒 | false |
| `cds-sync-plc` | PLC 授權，逗號分隔，只認 `connect` 與 `download`，見 6.5 | 空 |

### 4.5 磁碟格式

沿用現有格式，一個位元組都不改（D15）：

- 每個物件一個 `.st`，宣告區與實作區用 `// === IMPLEMENTATION ===` 分隔。
- 路徑跟 IDE 樹一致，POU 的成員放在以 POU 命名的資料夾底下，例如 `Function Blocks/MC_BasicControl/MC_BasicControl.Main.st`。
- 只有關鍵字表達不了的種類才蓋 `//% cds-text-sync.kind=<kind>` pragma：持久性 GVL、參數清單、action、介面方法。
- 編譯屬性用 `//% cds-text-sync.<attr>=true`：`exclude_from_build`、`link_always`、`external_implementation`、`enable_system_call`。
- 種類與 GUID 的對照在 `profiles/default.json`：`guid_aliases`（47 種，第一個是主 GUID）、`legacy_kind_names`、`sync_direction`（`bidirectional`、`export_only`、`import_only`、`disabled`）。
- `sync_cache.json` 是本機狀態，gitignore。`sync_metadata.json` 與 `*.log` 只在 debug 開著時寫。

---

## 5. 架構

### 5.1 四層

```
IDE 側（IronPython 2.7，只有標準函式庫）
  engine/   現在的 codesys_*.pyw 加四支入口的本體：分類、匯出、比對、匯入、
            備份、快取、編譯、線上預檢、PLC 連線與下載
  cds/ide/  看門人、替身 UI、訊息庫、專案資訊、狀態視窗、無頭啟動器的 IDE 側
  stub      Project_export.py、Project_import.py、Project_watch.py，各十行

兩邊都跑（Python 2/3 相容，標準函式庫）
  cds/core/ 檔案協定：目錄、實例登記、命令與結果

IDE 外（CPython 3.11 以上）
  cdsint/   CLI、無頭啟動器的 CLI 側、IDE 安裝探測、report 判讀
  tools/    離線工具：call tree、cache doctor、perf probe
```

層與層的界線是 D12 的三條規則。

### 5.2 三個場景的資料流

**場景 A，選單按鈕**：stub 載入引擎，引擎直接呼叫 IDE API，對話框由真人回答。

**場景 B，看門人**：

```
CLI 寫命令檔
  看門人的計時器下一拍撿到，先刪命令檔再執行
    替身 UI 接管 system.ui 與 codesys_ui.ask_yes_no，旗標有答案就答，沒有就丟 NeedsInput
    引擎跑，跟場景 A 同一份程式碼，回傳結果
  寫結果檔，心跳回 idle
CLI 讀到結果檔，刪掉，印出來
```

**場景 C，無頭**：

```
CLI 找 IDE、推 profile、查鎖檔、組命令列
  起 <exe> --profile=… --noUI --runscript=<IDE 側啟動器>
    啟動器 projects.open() 開專案，設同步資料夾，預先填 prompt_answers
    載入引擎跑 export/import/build，對話框由替身 UI 依旗標回答
    寫 report 檔，腳本返回，行程結束
CLI 等行程或逾時，讀 report，判讀 stdout 有沒有回來、退出碼可不可信
```

三個場景的引擎是同一份，差的只有誰回答對話框。

### 5.3 安裝佈局

跟上游 v2.9.0 一樣分成本體與 stub：

```
本體  %LOCALAPPDATA%\cdsint\             或任何 git clone
      engine\  cds\  cdsint\  profiles\  tools\  docs\ …

ScriptDir\cdsint\                       IDE 掃的地方，只有三個 stub
      Project_export.py   每支十行：寫死本體路徑，把它加進 sys.path，呼叫本體
      Project_import.py
      Project_watch.py
```

ScriptDir 的位置三家不同，這是安裝時最容易踩的坑，安裝器必須自己判斷：

| IDE | ScriptEngine.plugin | 掃哪裡 |
|---|---|---|
| 原廠 3.5.21 | 4.2.0.0 | `%LOCALAPPDATA%\CODESYS\ScriptDir` |
| Lenze 4.0 | 4.1.0.0 | `%LOCALAPPDATA%\PLCDesigner\ScriptDir` |
| Lenze 3.24 | 4.0.0.0 | `C:\ProgramData\PLCDesigner\ScriptDir` |
| Delta 1.8、1.10 | 4.0.0.0 | `<安裝目錄>\CODESYS\ScriptDir`，需要管理員 |

開發模式維持現在的 NTFS junction，但 junction 指向的是「stub 資料夾」，不是整個 repo。

---

## 6. 各元件規格

### 6.1 引擎

現有的 `codesys_*.pyw` 加上四支入口的本體。這一版對它的要求：

- **髒檔保護**。匯出時若磁碟上的 `.st` 自上次同步後被改過而還沒匯入，不覆蓋，列出來報「待匯入」。現況：沒有保護。`_try_cache_skip` 只拿快取裡的 `disk_mtime` 當跳過的快速路徑，磁碟檔變了就回 `None`，接著匯出照樣覆蓋。
- **每次操作只存檔備份一次**。現況：已做，`def7590`。
- **等待人按鈕的時間不算進耗時**。現況：已做，`fc1b9da`。
- **新寫的程式碼不准空白 `except:`**。現有的 119 處不要求一次清完，但每次碰到的函式順手改。
- **對話框只透過 `codesys_ui.ask_yes_no`、`ask_yes_no_cancel`、`system.ui.choose`**，因為替身 UI 只攔這幾個。新的對話框要先登記在替身 UI 的答案表裡，`test_every_yes_no_dialog_has_an_answer` 會擋沒登記的。那條測試掃的是一張寫死的檔名清單，10.1 搬檔案時要跟著改。
- **成功失敗的訊號**走回傳值（D11）。每一條 `return` 都要回一個 `result()`，訊息等級不再影響判決。

### 6.2 看門人

規格在 `docs/WATCHER.md`，本文不重抄。要點：

- 實例目錄 `%LOCALAPPDATA%\cdsint\instances\<專案主檔名>-<pid>\`，登記檔每 2 秒心跳，`busy` 的登記檔永不自動清。
- 命令先刪後跑。一個做到一半死掉的匯入寧可讓呼叫端逾時，也不要重跑。
- 同一個 IDE 不准兩支看門人。
- 有狀態視窗（現況：`cds/ide/statusform.py`），顯示在做什麼、做了幾個、上一個結果。視窗標題是 `cdsint`。

### 6.3 CLI

現有 `cli/cds_ide.py` 的行為全部保留，套件改名 `cdsint`，加上 4.2 的新形式與新子命令。結構上拆成：目標解析與結果印製、無頭啟動器、IDE 安裝探測、PLC 子命令，各自一個模組，每個不超過 300 行。

### 6.4 無頭啟動器

從 `sample_slitter_dev/scripts/codesys-probe.ps1` 與 `tools/codesys_probe.py` 搬過來，改成 CPython 的 CLI 側加 IronPython 的 IDE 側，PowerShell 那支退役。要保留的行為，每一條都是踩過坑才寫的：

| 行為 | 為什麼 |
|---|---|
| 列出安裝：掃 `Program Files` 的 `CODESYS *` 與 `Delta Industrial Automation\DIAStudio\DIADesigner-AX*`，讀 `Profiles\*.profile.xml` 的檔名當 profile 名 | `--noUI` 沒有 `--profile` 直接退出，而正確的名字是「CODESYS V3.5 SP21 Patch 4」這種形狀，不是安裝目錄名 |
| 查登錄檔 `AppCompatFlags\Layers` 有沒有 `RUNASADMIN` | manifest 是 asInvoker 的 exe 仍然可能被這個旗標擋，錯誤訊息不會說是誰要求的 |
| 多於一套符合就拒絕，不猜 | 這台裝了五套，猜錯會安靜地探到不相干的那套 |
| 開跑前查 `.~u` 鎖檔，兩種檔名形狀都查 | 省下二十秒 IDE 啟動，訊息裡有人看得懂的路徑 |
| 專案路徑走環境變數，不走 `--project` 也不走 `--scriptargs` | `--project` 在 `--noUI` 底下不會真的開專案；`--scriptargs` 的引號規則吃不了中文路徑 |
| 命令列組成單一字串，不用陣列 | PowerShell 5.1 的陣列參數會重新加引號弄壞 `--profile="有空白的名字"` |
| stdout 與 stderr 重導向到跟 report 同名的檔案 | GUI 子系統的 exe 從 shell 拿不到輸出；檔名跟著 report 走是為了兩個行程並行不搶檔 |
| 逾時就 kill，逾時當成「有對話框卡住」的結論記下來 | 掛住比報錯難查十倍 |
| 腳本把打算用的退出碼寫進 report，CLI 比對實際收到的 | 退出碼傳不傳得回來要驗，驗不過就改看 report |
| `system.prompt_handling` 開 `LogMessageKeys`，沒答到的提示會把鍵名印出來；`--answer KEY=VALUE` 填進 `prompt_answers` | Delta 1.10 開 1.8 的專案會問要不要升級，預設答案是「不開了」。這是 D7 明寫的例外 |
| 開完不 close | close 會問要不要存檔，`--noUI` 底下沒人能答 |

已知還沒解的：Delta 1.10 無頭、專案剛升級過儲存格式之後第一次 `save()` 丟 NullReferenceException。啟動器印一行繼續，不中止。

現況：階段 2 做完，CLI 側是 `cdsint/headless.py`，IDE 側是 `cds/ide/headless.py`，PowerShell 那支退役。
表裡「專案路徑走環境變數」的落地是一個環境變數 `CDSINT_HEADLESS_JOB` 指向一個 JSON 工作檔，
專案路徑、命令清單、`--answer` 的答案都在裡面；理由跟原本那一列一樣，而且順帶讓兩側不必為了
每個新旗標各長一個環境變數。IDE 側跑完寫 JSON 報告，CLI 側再把只有外面知道的事補進去：
`stdout_reached`（兩個標記都看到才算）、`exit_code_actual` 與 `exit_code_trusted`、`timed_out`。

### 6.5 權限

D8 的落地。

**專案屬性 `cds-sync-plc`**，由人在 IDE 裡設，逗號分隔，值只認 `connect` 和 `download`，預設空。`plc` 命令執行前先查，不在表裡就回 exit 5 與一句「這個專案沒有開放 plc X，請在 IDE 裡把 X 加進 cds-sync-plc」。

**`plc download` 另外要 `-y`。** 沒給就印出這趟會做什麼（完整下載、停機、寫開機應用程式、啟動），回 `needs_input`，exit 1。這跟 `import` 沒給 `-y` 一模一樣。exit 5 只有「屬性沒開」一個意思。

**`config set` 不碰 `cds-sync-plc`。** 這是政策不是牆，無頭模式本來就在 IDE 裡跑任意 IronPython，誰想繞都繞得過。留這條的理由只有一個：這個屬性的意思是「一個人在 IDE 裡決定過」，讓 CLI 能寫它就把這個意思抹掉了。

其他所有命令不受權限管。

### 6.6 PLC 連線與下載

從探針搬，放在引擎裡跟 `codesys_online.pyw` 並排（D12），只在 `--project` 形式提供（D8）。

- `connect`：`online.set_auth_fallback_modes(None)` 關掉憑證對話框，帳密只從環境變數 `CDS_DEV_USER`、`CDS_DEV_PASS` 讀（D14）。列閘道，`find_address_by_ip`，`set_gateway_and_ip_address` 設到裝置節點，`create_online_device` 連線，列 `PlcLogic/Application`，拉 `Application.crc`，跟本機 `create_boot_application` 產出的 `.crc` 比第 5 到 8 個位元組。有原始碼封存就拉回來。
- `download`：`login(OnlineChangeOption.Never, False)` 完整下載，`create_boot_application`，`start`，`logout`，再建一次 boot app 比 CRC。
- 這兩個命令的 report 要包含比對結果 `MATCH` 或 `DIFFERENT`，pipeline 拿這個當閘門。

現況：探針的程式碼有，註解裡有實測痕跡，但 9 月 4 日留下的 report 沒跑到這段。搬過來之後要在台架上重驗一次。

### 6.7 設定流程

取代 `Project_directory.py` 與 `Project_parameters.py`：

1. `Project_export.py` 或 `Project_import.py` 啟動時若 `cds-sync-folder` 不存在，開資料夾對話框，存成相對路徑，寫入 `cds-sync-pc` 與 `cds-sync-version`，寫 `.gitattributes` 與 `.gitignore`。這個對話框沒有旗標可以回答，所以 `--target` 形式第一次跑會回 `needs_input`，解法是先跑 `cdsint config set cds-sync-folder=...` 再來；`--project` 形式用 `--sync-dir`。
2. 電腦名稱不符：警告，問要不要繼續，`--force` 回答。
3. 其他屬性透過 `cdsint config get/set` 讀寫。看門人的狀態視窗放一個「設定」按鈕，開跟現在 `Project_parameters.py` 一樣的對話框。這樣沒有 CLI 的人也改得到。

現況：階段 1 已做，程式在 `engine/settings.py`。「存成相對路徑」的落地是：選到的資料夾在專案檔那一層或底下才寫成 `./...`，其他情形（別的磁碟、專案外面）維持絕對路徑，理由是 `..\..\` 這種相對路徑只在專案不搬家時才成立。`config get/set` 階段 2 做了，在 `cds/ide/config.py`，兩種形式都有；讀寫的是 4.4 那張表列的屬性，名字不在表上就拒絕，`cds-sync-plc` 只讀不寫。`config set` 寫完會存檔，因為一個只活在記憶體裡的設定在專案關掉時就沒了，而無頭模式沒有人會禮貌地關它；代價是使用者手上還沒存的編輯會跟著落地，所以 summary 會說「project saved」。第一次跑 export 或 import 而還沒設同步資料夾時，`--target` 形式仍然回 `needs_input`，訊息現在會告訴你三條路：`cdsint config set`、Project Information > Properties、或從選單跑一次匯出。

---

## 7. 相容性矩陣

「驗過」是有 report 或真人紀錄的意思，其餘是「應該可以」。

| 功能 | 原廠 3.5.21.40 | Lenze 3.24 | Lenze 4.0 | Delta 1.8 | Delta 1.10 |
|---|---|---|---|---|---|
| 選單匯出匯入 | 驗過 | 驗過，日常在用 | 裝過，未驗 | 驗過，k1.1.1 的 bug 就是在它上面抓到的 | 驗過 |
| 看門人不卡 IDE | 驗過，真實點擊 | 應該可以，同 4.0.0.0 | 應該可以 | 應該可以 | 驗過，真人 |
| CLI export、import、build | 驗過，229 個物件 | 未驗 | 未驗 | 未驗 | 驗過 |
| 無頭起得來 | 驗過 | 驗過 | 未驗 | 未驗 | 驗過 |
| 無頭開得了專案、跑得了引擎 | 驗過 | 未驗 | 未驗 | 未驗 | 驗過 |
| 無頭 build | 驗過 | 未驗 | 未驗 | 未驗 | 驗過，要修過才會真的編譯，見底下 |
| `verify --project` 一條命令跑完 | 驗過 | 未驗 | 未驗 | 未驗 | 驗過 |
| 無頭 boot app 產出 | 未驗 | 未驗 | 未驗 | 未驗 | 失敗，NullReferenceException |
| PLC connect、download | 未驗 | 未驗 | 未驗 | 未驗 | 未驗 |

這張表的每一格都是「同一家 IDE 開它自己的專案」。9 月 5 日階段 1 驗收各驗了一輪：原廠 3.5.21.40 開 softplc 副本、Delta 1.10 開 Shm 副本，`export`、`import`、`compare`、`build` 都 exit 0，229 個物件，build 0 errors。階段 2 用 `verify --project` 對同樣兩個副本各再跑一輪，四步全過。

**ScriptEngine 4.0.0.0 的 build 有兩個坑，兩個都是階段 2 在 Delta 1.10 上量出來、修掉的**，Lenze 3.24 同版本應該一樣（未驗）。一是 `get_message_objects` 在 4.0.0.0 沒有單參數的形式，兩個多載都要再給一個 severity；只給 category 會丟 `Value cannot be null. Parameter name: category`，整份 build 結果就變成一個 traceback。二是那個 category 還得正在裝著訊息，一次什麼都沒重編的 build 讓它空著，同一個呼叫同樣丟那句話。4.2.0.0 兩件都容忍，所以原廠一直沒露出來。

更要緊的是底下那一個：**Delta 1.10 一個行程裡的第一次 `app.build()` 不會真的編譯**。同一個 IDE 連跑三次量到 7.4 秒沒有任何訊息、31.7 秒 101 個警告、5.8 秒同樣 101 個。而 `--project` 形式一個行程只跑得到第一次，所以它本來會回報一份它根本沒編過的乾淨結果。現在的做法是：一次 build 如果連自己的摘要行都沒寫，就再 build 一次；兩次都沒有的話回報「這台 IDE 沒有產出任何 build 輸出」而不是 0 個錯誤。

跨家開專案是另一回事，而且現在有明確的行為：原廠開 Delta 的 Shm 專案時，7 個物件的外掛不在，三個命令都 exit 1、把那 7 個名字放進 `data.failed_objects`、其他 229 個照常處理完（D13、D11）。這不是「支援跨家」，是「跨家時不騙人」。

效能基準，229 個物件，main 上 9 月 5 日的數字，perf 分支的改善還沒量：

| 操作 | 原廠 | Delta |
|---|---|---|
| export | 59.7 秒 | 56.6 秒 |
| compare，只改一個 POU | 50.6 秒 | 47.1 秒 |
| build | 23.3 秒 | 32.5 秒 |

階段 2 的 `verify --project` 一整趟，同樣 229 個物件，9 月 5 日量的。這一組的每一步都是
「沒有差異」的情況（磁碟與 IDE 早已一致），所以比上面那組快；上面那組留著當基準，
兩組不能互相取代。IDE 啟動加開專案另外算，兩家都是三十幾秒。

| 步驟 | 原廠 3.5.21.40（softplc 副本） | Delta 1.10（Shm 副本） |
|---|---|---|
| import | 24.2 秒 | 18.4 秒 |
| export | 14.8 秒 | 14.8 秒 |
| compare | 13.2 秒 | 14.0 秒 |
| build | 23.5 秒 | 31.3 秒 |
| 一整趟（含啟動） | 124.6 秒 | 142.3 秒 |

---

## 8. 品質要求

**PRINCIPLES.md 要改寫**。它現在說「檔案超過 400 行就是 bug」，而引擎有三個檔超過 1100 行。改成兩級：新寫的程式碼與 `cds/`、`cdsint/` 適用硬上限；`engine/` 只要求「碰到的函式不能變長、新函式遵守上限」。文件跟程式碼講不同的話，比沒有文件更糟。

**測試分三層**：

| 層 | 跑在哪 | 現況 |
|---|---|---|
| `cds/core` 與 CLI 的純函式 | CI，CPython 3.12 | 有 |
| 引擎邏輯，用假 IDE 物件 | CI | 有，389 個 |
| 真 IDE 驗收：無頭起一個專案副本，跑 export、import、build，比對輸出 | 本機，手動或排程，三家各一次 | `cdsint verify --project` 就是那個腳本（階段 2）。`--target` 那半要一個開著的 IDE，`tools/headless_watch.py` 起得出來 |

**CI** 在 push 到任何分支都跑，不只 `main` 與 `claude/**`。

**版本只有一個來源**：`codesys_constants.pyw` 的 `SCRIPT_VERSION`。readMe、`pyproject.toml`、看門人登記檔都從它讀或由 release 腳本同步。每個 release 打 tag。

---

## 9. 文件

- `readMe.md`：定位、三個場景各一段十行內的例子、安裝（三家的 ScriptDir 表）、CLI 命令表、exit code、權限、FAQ。安裝來源指向本 repo。`WORKFLOW.md` 裡還成立的內容併進三個場景那段。
- `docs/AI_WORKFLOW.md` 與 `skills/cdsint/SKILL.md`：場景 B 的操作手冊，跟著改路徑與命令名。加上 `--project` 形式那一段。
- `docs/SPEC.md`：本文，做完的樣子。
- `docs/WATCHER.md`：新檔。看門人的協定規格、看門人規格、計時器設計，從 `WATCHER_CLI_PLAN.md` 第 5、6、14 節抽出來。程式碼裡引用節號的六處指標改指它。
- `docs/history/`：`WATCHER_CLI_PLAN.md`、`RESEARCH_HTTP_IDE_CONTROL.md`、`REWORK_PLAN.md`、`WORKFLOW.md`。都是決策紀錄不是現況。
- `CHANGELOG.md`：每個 release 一段，寫「症狀、根因、改法」，不寫檔案清單。

---

## 10. 從現在的 repo 走到這裡

### 10.1 檔案對照

| 現在 | 之後 |
|---|---|
| `Project_export.py`、`Project_import.py`、`Project_watch.py` | 留在 stub 資料夾，各十行，本體邏輯搬進 `engine/` 並回傳結果（D11） |
| `Project_compare.py`、`Project_Build.py` | 改成引擎模組，只由 CLI 與看門人呼叫 |
| `Project_directory.py`、`Project_parameters.py` | 併進 6.7 的設定流程後刪除 |
| `Project_discover.py`、`Project_resources.py`、`Project_perf_probe.py` | 搬到 `tools/`，無頭啟動器可以跑它們 |
| `Project_perf_test.py` | 刪除。`perf_probe` 已經取代它，而且它的檔名符合 `*_test.py`，今天讓 `python -m pytest` 在收集階段就報錯 |
| `codesys_*.pyw` | 搬進 `engine/`，副檔名改回 `.py`，因為已經不在 ScriptDir 裡 |
| `cli/cds_ide.py` | 改成 `cdsint/` 套件，拆成四個模組 |
| `tools/open_copy_and_watch.py`、`tools/watch_harness.py` | 開專案那半歸 `cds/ide/headless.py`；「掛看門人再停住不退出」那半留在 `tools/headless_watch.py`，因為它用 `system.delay()`，而 D5 禁的就是那個（見 D5 現況） |
| 分紙機的 `codesys-probe.ps1`、`codesys_probe.py` | 搬進本 repo，PowerShell 退役，分紙機的 Makefile 改呼叫 `cdsint ... --project` |
| `cds/__init__.py` 的 `VERSION` | 刪除，沒人讀 |
| `docs/WATCHER_CLI_PLAN.md`、`docs/RESEARCH_HTTP_IDE_CONTROL.md`、`docs/REWORK_PLAN.md`、`WORKFLOW.md` | 進 `docs/history/`，見第 9 節 |
| `irm/` | 安裝腳本，跟著 5.3 的佈局改寫，改指本 repo |
| `img/` | 留著，readMe 用 |
| `Performance_tests/` | 空目錄，刪除 |

### 10.2 分階段與驗收

每一階段獨立可合併，合併前 CI 綠。

**階段 0，搬家與身分。** 從來源 repo 把程式碼搬進 5.1 的佈局：`codesys_*.pyw` 進 `engine/` 改 `.py`，四支入口的本體進 `engine/`，stub 進 `stub/`，`cli/cds_ide.py` 進 `cdsint/`，`cds/`、`tools/`、`profiles/`、`tests/`、`irm/`、`img/` 照搬。補 `pyproject.toml`，套件名和命令名都是 `cdsint`。實例目錄用 `%LOCALAPPDATA%\cdsint`，不寫遷移，因為只有這台機器有，看門人重啟就好。抽 `docs/WATCHER.md`，改程式碼指標，四份決策紀錄進 `docs/history/`。CHANGELOG 沿用來源的，頂上加一段說明搬家。刪掉沒人讀的 `cds.VERSION` 與擋住 pytest 收集的 `Project_perf_test.py`。
驗收：測試通過數不少於來源的 389。從乾淨的 clone 照 readMe 裝，裝到的是這個 repo，命令叫 `cdsint`。三家 IDE 用無頭模式都能載入引擎且沒有 traceback。
驗收：從乾淨的 clone 照 readMe 裝，裝到的是這個 repo，命令叫 `cdsint`。

**階段 1，三個入口。** ScriptDir 底下的子資料夾叫 `cdsint`，安裝器會判斷三家的 ScriptDir。設定流程併進匯出匯入，stub 減到三支。四支入口的本體改成回傳結果（D11）。視窗標題改名。
驗收：三家 IDE 的 Scripts 選單各只有三項，toolbar 按鈕不用重設，`cdsint export/import/compare/build --target` 照常。替身 UI 讀回傳值的測試取代讀等級的測試。

**階段 2，無頭前門。** 搬啟動器，做 `installs`、`--project` 形式、`verify`。
驗收：對一個專案副本在原廠與 Delta 各跑一次 `cdsint verify --project`，report 裡 stdout 回得來、退出碼可信、匯出後磁碟無 diff、build 0 errors。專案被 IDE 開著時 exit 4，訊息含鎖檔路徑。逾時 exit 3。`verify --target` 對開著的 IDE 也跑得完。

**階段 3，權限與 PLC。** `cds-sync-plc`、exit 5、`plc connect`、`plc download`。
驗收：屬性沒開時 `plc download -y` exit 5 且 PLC 沒有任何變化；開了但沒 `-y` 回 `needs_input`、exit 1，PLC 同樣沒變化；都給了在台架上下載成功，report 的 CRC 比對 `MATCH`。`plc connect --target` 被拒絕並說明原因。

**階段 4，引擎品質。** 髒檔保護、perf 量測、碰到的空白 except、`show_toast` 改 Timer、`threading.Lock` 去留、`cds-sync-` 前綴收成常數。
驗收：磁碟改了沒匯入就跑 export，該檔沒被覆蓋且被列為待匯入，有測試。IDE 側 grep 不到 `time.sleep`、`Thread`、`threading`。perf 表更新，跟第 7 節的基準比。

---

## 11. 未決事項

1. **速度引擎。** 階段 4 量完 perf 之後再決定要不要換成 `export_native` 整包倒出。換的話是引擎內部的事，三個入口與磁碟格式不動。
2. **Delta 1.10 無頭升級後 `save()` 的 NullReferenceException。** 沒查到根因。先繞過，記在相容性矩陣。
3. **看門人跑著時 Scripts 選單能不能啟動別的腳本。** 主線註記說沒驗。階段 1 順手驗。
