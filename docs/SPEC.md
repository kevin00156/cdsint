# 產品規格：cdsint

> 這份文件描述「做完之後的樣子」，不是施工順序，也不是進度表。
> 「現在做到哪裡」不寫在這裡：那是 `git log` 與 `CHANGELOG.md` 回答的問題，而寫在規格裡的進度必然過期。施工順序的紀錄在 [`docs/history/SPEC_10_CONSTRUCTION.md`](history/SPEC_10_CONSTRUCTION.md)。
> 所有規則只寫在第 3 節的決策表裡，其他章節和程式碼註解用 D 編號引用，不重抄內容。
> 程式碼來源是 `kevin-cds-text-sync`（`C:\Users\qazsskevin\Documents\repo\kevin-cds-text-sync`，分支 `fix/member-creation-parent-resolution`，commit 9aa9886）。本 repo 只從它讀，不寫回去。

---

## 0. 一句話定位

**磁碟上的 `.st` 文字檔是 PLC 專案的事實來源，cdsint 負責把它和 CODESYS 系列 IDE 之間的搬運、驅動與驗證做成可以從外面呼叫的東西。**

名字的拆法：`cdsint` 是產品，也是專案旁設定檔 `<專案名>.cdsint.json` 的名字（D9、D10）。

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

**場景 C，pipeline。** IDE 沒開。`make` 或 CI 起一個無頭的 IDE 行程，開專案副本，匯入、匯出驗證、編譯、下載到台架，再確認台架上還是剛剛放上去的那份。整趟沒有人在鍵盤前。

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

每一條有編號、決定、理由。其他章節只引編號。做到哪裡了不寫在這裡，那是 git log 與 `CHANGELOG.md` 回答的問題。

**D1 開新 repo `cdsint`，程式碼從 `kevin-cds-text-sync` 搬過來，不重寫。**
理由：產品換名字、目錄佈局整個換，在舊 repo 原地改等於每個檔案都搬一次還要顧舊路徑；新 repo 的 git 歷史從搬家那一刻開始，舊歷史留在來源 repo。引擎、看門人、CLI 的程式碼原封搬過來再整理，理由跟非目標第一條一樣：引擎裡的知識是真專案撞出來的。上一次「乾淨重來」的 `cds/` 骨架就是因為從零寫，一格驗收都沒打勾就被刪了。

**D2 一個引擎，一個 CLI 命名空間，模式由旗標決定。** `--target X` 走開著的 IDE 裡的看門人，`--project P --install I` 起一個無頭 IDE。兩組旗標互斥，argparse 用互斥群組擋住同時給。
理由：兩個場景互斥，CODESYS 會擋第二個行程開同一個專案檔，所以同一條命令不會兩邊都能走。但兩邊做的是同一件事，給它們兩套詞彙只會讓子命令各自長出只有一邊有的東西。不自動偵測，因為那會讓旗標需求隨執行期狀態變，而且意外的二十秒 IDE 啟動是最難查的那種驚喜。兩半（`cdsint/target.py`，以及 `cdsint/headless.py` 配 `cds/ide/headless.py`）對外都是 `run(steps)`，所以 `verify` 只寫一次。

**D3 IDE 的 Scripts 選單只有三個入口：匯出、匯入、看門人。本體放在 ScriptDir 外面。**
理由：選單是遞迴掃 ScriptDir 底下所有 `.py`，上游 v2.9.0 實測連隱藏屬性都躲不掉。

**D4 IDE 側程式碼是 IronPython 2.7 可跑的 Python 2/3 相容碼，標準函式庫限定。CPython 3 只存在於 IDE 外。**
理由：目標 3。

**D5 IDE 內等待命令用 WinForms 計時器掛在 IDE 訊息迴圈上，腳本立刻返回。IDE 側不准 `time.sleep()`、不准 `system.delay()`、不准開執行緒、不准 `execute_on_primary_thread`。** 這條是絕對的，沒有「背景執行緒不碰 API 就可以」的例外。
理由：`system.delay()` 不處理滑鼠鍵盤，`execute_on_primary_thread` SP21 拿掉了，CODESYS API 不是執行緒安全的。整個 IDE 側只有一種併發模式，比一條寫得精確的例外值錢。計時器設計在 ScriptEngine 4.0.0.0 與 4.2.0.0 都有真人驗過。規則由 `tests/test_single_threaded_ide_side.py` 守著：它 parse `engine/`、`cds/ide/`、`stub/` 底下每一支 `.py`，加上 `tools/` 裡會載進 IDE 的那幾支（判準是那支檔 import 不 import 得到 `engine`、`cds` 或 `tools/_root.py`）。看的是呼叫與 import 這兩種語法節點，不是文字，所以講到「thread」的註解不會被誤判。

這條規則唯一被允許的例外是 `tools/headless_watch.py` 的 `park()`，它用 `system.delay()`，而且只在 `--noUI`：沒有視窗就沒有畫面會凍住，而沒有東西撐著行程的話 IDE 在腳本返回的瞬間就結束，看門人一次 tick 都跑不到。它在跑之前檢查 `system.ui_present`，有 UI 就拒絕停住，所以這個例外離不開它成立的那個情況。它是驗收用的工具，不在 `cds/ide/` 底下。

**D6 命令交接用檔案協定，不換 named pipe、不換 HTTP。** 協定規格在 `docs/WATCHER.md`。
理由：現有協定已經跑過真專案，IronPython 與 CPython 都只需要標準函式庫。

**D7 cdsint 自己的對話框由旗標回答，永不猜。沒有旗標就回 `needs_input`。** IDE 自己的提示不在這條的範圍內：無頭模式下它們走 `system.prompt_answers`，由 `--answer KEY=VALUE` 填，沒填到的取 IDE 的預設值並把鍵名記進 report。
理由：場景 B 的前提是 agent 看不到視窗。IDE 內建提示那半是 IDE 在猜不是 cdsint 在猜，規格得老實寫這條界線，不能宣稱全面不猜。替身 UI 在 `cds/ide/silent.py`，兩種形式共用。`--answer` 只有 `--project` 形式有，而且一個都不預設，因為 `UpgradeProjectConfirmation` 答 Yes 會改寫專案的儲存格式，之後舊版 IDE 就開不了它。沒答到的提示靠 `LogMessageKeys` 把鍵名印到 stdout，訊息會說去補哪個 `--answer`。

**D8 只有碰 PLC 的動作受權限管，兩層。** 設定檔的 `plc` 清單決定這個專案允不允許，`-y` 確認這一次呼叫。看門人模式一律拒絕 PLC 命令。
理由：一個 agent 下錯命令現在能直接下載到 PLC。`export`、`import`、`compare`、`build` 不碰硬體，把它們放進權限清單只會讓每個命令多一次預檢，換來三個場景都用不到的功能。看門人跑在使用者的 IDE 裡，登入會搶走使用者的線上狀態。第一層以前是專案屬性，意思是「一個人在 IDE 裡決定過」；設定搬到文字檔之後（D10）那個意思不再成立，第一層只是「檔案裡有寫」，真正的門是 `-y`。

**D9 產品名是 `cdsint`。** 同一個字串用在 pip 套件、Python 套件、命令、`%LOCALAPPDATA%` 目錄、ScriptDir 子資料夾、視窗標題。
理由：上游同名、93 顆星，舊的 readMe 與安裝腳本都指著上游。沒有連字號，所以 pip 名、import 名、命令名不用兩種拼法。`cds-ide` 會跟它驅動的 IDE 撞名，寫文件時每句都得多解釋一次。

**D10 設定存在專案檔旁邊的 `<專案名>.cdsint.json`，不存在 `.project` 的專案屬性裡。**
理由：`.project` 是二進位檔，只有 IDE 行程開得了，所以存在裡面的設定要改就得先弄到一個活著的 IDE，agent 要看設定得起一個 IDE，每個新專案從零開始。這一個事實養出了四條入口（Properties 表格、Settings 視窗、`config` 命令、第一次匯出的對話框）和三個只為它存在的機制（強制 `--sync-dir`、電腦名稱戳記、`config set` 之後再按引擎收尾）。文字檔任何編輯器都能改，不需要 IDE。放專案旁而不放同步資料夾裡，是因為十一個設定大多是這台機器的事，不是團隊政策，而且只有這樣同步資料夾本身才能一起搬出來，讓專案屬性那條路整個關掉。舊的 `cds-sync-*` 屬性不讀、不遷移：還沒發布過版本，唯一沒預設值的是同步資料夾，而它本來就有對話框會問。schema 在 `cds/core/settings.py`，一份，兩側共用，CI 測得到。

**D11 四支入口回傳結果，替身 UI 讀回傳值判斷成功失敗。**
理由：四支 `main()` 本來不管成功失敗都回 `None`，替身 UI 只能看 `system.ui.warning` 和 `error` 有沒有被呼叫來推。這讓「warning 只准在中止點呼叫」變成所有未來作者都得記住的規則，違反的後果離現場很遠：有人在匯出中途寫一句無害的 warning，一次成功的匯出就變成 exit 1。回傳的形狀是 `engine/entry.py` 的 `result(ok, summary, **data)`，替身 UI 讀 `ok`；回傳 `None` 算失敗。`ok` 的意思是「這個命令把該做的每個物件都做完了」：任何一個物件分類不出來、建不出來、匯不出去，`ok` 就是 False，名字列在 `data` 裡（D13）；命令仍然把其他物件做完，不中途放棄。

**D12 三條分層規則，由解析後的 import 驗。** `cds/core` 不准 import `system`、`projects`、`online`、`clr`。`cds/ide` 不准 import `online`，不准 import 引擎模組。引擎不准 import `cds/ide`。
理由：`cds/core` 要在 CI 上被完整測。`cds/ide` 只做管線，也就是協定端點、計時器、替身 UI、prompt 答案、狀態視窗、無頭模式的 `projects.open`。走物件樹和碰 PLC 的事全在引擎。依賴方向是 `cds/ide` 用入口名字驅動引擎，不反過來。守門的是 `tests/test_layering.py`，讀 AST 不讀文字：grep 會把 `cds/ide/silent.py` 那段說明「這裡不 import 引擎」的註解算成一筆命中，而被假命中騙過一次的人，下一次真的命中也不會信。唯一例外是 `silent.py` 以字串名字載入 `engine.codesys_ui`，只為了把三個對話框函式換成替身再換回去，不呼叫它任何東西；那個 `__import__` 在測試裡登記成一筆，第二筆出現就紅。

**D13 不准靜默跳過物件。** 分類不出來、建不出來、匯不進去都要以名字報出來。這一輪有物件處理不了，匯出就不刪孤兒檔，因為分不出哪個檔屬於它們。
理由：目標 6。`engine/unhandled.py` 是一次命令的登記簿，處理不了的物件以名字記在那裡，`export`、`compare`、`import` 三個命令把它寫進回傳結果的 `data.failed_objects` 並讓 `ok` 是 False（D11）。攔的地方是每個迴圈的「處理這一個物件」那一步，所以一個物件壞掉不會把整趟拖下去。搬過來的程式碼裡還有一批空白 `except:`，數目與棘輪在 `tests/test_bare_excepts.py`，見 6.1。

**D14 帳密不准出現在命令列、檔案、report 裡。** 只從環境變數讀。
理由：report 會進 git 或被貼到工單。`engine/plc_link.py` 的 `USER_ENV`、`PASS_ENV` 是唯一讀它們的地方；密碼交給 `set_default_credentials` 之後就不再出現在任何字串裡，帳號名字會出現在 notes（誰登入的是事後判讀的依據）。有一條測試跑完一整趟下載再確認結果紀錄、stdout、messages 裡都沒有那個密碼。

**D15 `.st` 格式與 pragma 名稱不准改。** 要改就是一個大版本。格式定義見 4.5。
理由：現有專案的 git 歷史都是這個格式，這是相容性的底線。

**D16 不准留新舊兩條路並存。** 換掉就刪掉。
理由：PRINCIPLES.md 不留死碼。上次 `cds/` 骨架就是這樣被清掉的。

---

## 4. 使用者看得到的東西

### 4.1 IDE 選單

`Tools > Scripting > Scripts` 底下只有三項（D3）：

| 入口 | 做什麼 |
|---|---|
| `Project_export.py` | 把 IDE 專案寫成 `.st`。第一次執行時若沒設同步資料夾，先走設定流程（6.7） |
| `Project_import.py` | 把 `.st` 讀回 IDE，磁碟贏。同樣先走設定流程 |
| `Project_watch.py` | 啟動看門人，腳本立刻返回；再跑一次就停止 |

比對、編譯、診斷、資源統計、效能量測都不出現在選單。比對和編譯由 CLI 呼叫。其餘搬到 `tools/`。

### 4.2 CLI

命令名 `cdsint`，CPython 3.11 以上，只依賴標準函式庫，透過 `pyproject.toml` 裝成 console script。套件名不可以叫 `cli`，上游 v2.9.0 就是因為 `cli` 這個頂層套件名跟使用者自己的目錄撞名才改的。

每個命令有兩種形式（D2）。`--target X` 找開著的 IDE 裡的看門人，`--project P --install I` 起一個無頭 IDE。兩組旗標互斥，argparse 直接擋。

| 命令 | `--target X` | `--project P --install I` | 做什麼 |
|---|---|---|---|
| `installs` | 不適用 | 不適用 | 列出這台的 IDE、profile 名稱、要不要管理員 |
| `list` | 不適用 | 不適用 | 列出正在聽的 IDE。它問的是「有誰在聽」，不是問某一個，所以兩種形式都不收 |
| `ping`、`status`、`stop` | 有 | 不適用 | 看門人的生命週期，不受權限管 |
| `export [--delete-orphans]` | 有 | 有 | 把 IDE 專案寫成 `.st` |
| `import -y` | 有 | 有 | 把 `.st` 讀回 IDE，磁碟贏 |
| `compare` | 有 | 有 | 列出 IDE 與磁碟的差異 |
| `discover` | 有 | 有 | 唱名每一個物件與它算成哪一種 kind，並列出沒有任何 kind 認得的型別 GUID（`data.unknown`）。唯讀，不需要權限 |
| `build [--app NAME]` | 有 | 有 | 編譯，回錯誤清單 |
| `verify -y` | 有 | 有 | import、export、比對磁碟有沒有 diff、build，一次跑完。含匯入，所以跟 `import` 一樣要 `-y` |
| `plc connect [--gateway IP --port N]` | 拒絕 | 有 | 唯讀：列檔案、拉 `Application.crc`、跟上次下載記下的值比 |
| `plc download -y` | 拒絕 | 有 | 完整下載、寫開機應用程式、啟動、讀回 CRC 並記下來 |

沒有 `config` 命令。設定是專案旁的一個文字檔（4.4），檔案就是介面；驗證在讀檔那一支，所有路都經過它。

共用旗標：`--timeout 秒`（預設 120，是**一個命令步驟**的上限；`--project` 形式的行程期限由它推導：啟動寬限 + 步數 × timeout + 關閉寬限，所以 `verify` 的實際等待上限比字面值大）、`--json`。
只在 `--project` 形式有效：`--profile NAME`、`--report 檔案`、`--force-lock`、`--sync-dir D`（選用，語意在下面）、
`--answer KEY=VALUE`（可多個，D7）。`--answer` 回答的是 IDE 自己的提示，而 `--target` 那半的
IDE 前面坐著一個人，那些提示是他的，所以它不放在共用那一排。

一條跟「磁碟贏」有關的安全界線。`import`（三條路都是：選單、`--target`、`--project`）在同步資料夾裡一個 `.st` 都沒有時拒絕，因為那不是「磁碟上什麼都沒有」這個事實，是還沒 export 或路徑指錯，照磁碟贏的規則做下去等於把專案清空。

`--sync-dir` 的語意是「這一趟用這個資料夾」：它是命令的一個引數，跟 `-y` 走同一條路進 IDE 側，引擎讀到就用它蓋過設定檔裡的 `sync_folder`，永遠不寫回任何檔案。沒給就用設定檔的；兩個都沒有，export 與 import 回 `needs_input`，跟 `--target` 形式一樣。以前它是必填，理由是副本的 `.project` 帶著原專案的資料夾屬性；設定搬到專案旁的文字檔之後（D10），只複製 `.project` 的副本什麼都不帶，這個理由就沒了。解析後的同步資料夾印在輸出第一行並寫進 report 的 `sync_dir`，那個欄位填的是 IDE 側實際生效的值，不是旗標上寫的值。

`-y` 的意思統一是「確認這一步會改狀態」，`import`、`verify` 和 `plc download` 共用。沒給就印出這趟會做什麼，回 `needs_input`，exit 1，什麼都不改。沒有 `-N`，因為沒給 `-y` 就已經是「不做」，其他有安全預設值的對話框各自有具名旗標，`--delete-orphans` 答刪孤兒。

`plc` 命令拒絕 `--target` 形式的原因見 D8。

### 4.3 Exit code 與輸出

| Exit code | 意思 |
|---|---|
| 0 | 完成 |
| 1 | 命令失敗，包含缺旗標的 `needs_input` |
| 2 | 命令列本身不對：旗標不搭，或找不到唯一一個活著的 IDE |
| 3 | 逾時 |
| 4 | 無頭模式：這個專案沒有一套能用的 IDE — 專案被別的行程開著、`--install` 對不到任何一套（訊息會列出裝了哪些）、或 IDE 啟動失敗 |
| 5 | 權限拒絕：設定檔的 `plc` 清單沒有這個命令 |

2 有兩個原因，旗標不搭和找不到唯一一個活著的 IDE，合在一格是因為呼叫端的處置相同：同一行不要重試，先讀訊息。2 和 4 是「這個專案有沒有活著的 IDE」的兩種原因，對 agent 有用所以分開。`list` 不在 2 的範圍內：它問的是「有誰在聽」，一個都沒有時印一句話、`--json` 給空陣列、exit 0，因為空清單是答案不是失敗。`needs_input` 不獨立成一格，因為 agent 反正得讀 JSON 裡的 `needs_input.arg` 才知道該補哪個旗標，獨立的 code 省不掉那次解析。

`--json` 輸出的結構沿用現有結果檔：`ok`、`command`、`elapsed_s`、`messages`、`stdout_tail`、`error`、`needs_input`、`denied`、`data`。`--project` 形式再加 `ide`（用了哪套）、`sync_dir`（這一趟的事實來源，跟 report 頂層同一個值）、`report_path`、`notes`。

`notes` 是啟動器對「這一趟」而不是對「這件工作」說的話：清掉了一個鎖檔、不得不 kill 一個 IDE、退出碼跟腳本自己記的對不上。它只有 `--project` 形式有，因為只有那半會起 IDE。放進紀錄而不是只印在 stderr，是因為 agent 讀的正是這份 JSON，而「我幫你清了一個鎖檔」這種話它必須聽得到。一趟的每一筆紀錄帶的是同一份清單，所以只讀其中一筆也不會漏掉。

`denied` 平常是 `null`，被設定檔擋下來的時候是 `{"file", "key", "action"}`，exit code 就是從它決定 5 的。它跟 `needs_input` 分開兩個欄位，因為兩者要呼叫端做的事不一樣：`needs_input` 是「補一個旗標再跑一次」，`denied` 是「去設定檔的 `plc` 清單加一個字」。

### 4.4 設定檔

設定存在專案檔旁邊、照專案名命名的 JSON 檔（D10）：`Line.project` 旁邊是 `Line.cdsint.json`。UTF-8，真的 JSON 型別：布林、整數、字串、清單。跟下載紀錄 `Line.cdsint-plc.json` 是兩個檔，因為人決定的偏好和機器跑完留下的紀錄生命週期不同。

檔案裡只出現人決定過的鍵；沒寫的鍵用程式碼裡的預設值，預設值只有那一份。所以「我選的」和「它填的」分得出來，改程式碼的預設值不用回頭改任何檔案。第一次跑匯出或匯入時對話框問完資料夾寫出來的檔，只有 `sync_folder` 一個鍵。

| 鍵 | 型別 | 意思 | 預設 |
|---|---|---|---|
| `sync_folder` | 字串 | 同步資料夾。`./` 開頭就相對於專案檔所在目錄，否則照用 | 無，第一次執行時問 |
| `plc` | 字串清單 | PLC 授權，元素只認 `connect` 與 `download`，見 6.5 | 空清單 |
| `debug` | 布林 | 開了才寫 `sync_metadata.json` 與 `*.log` | false |
| `export_xml` | 布林 | 視覺化、警報、文字清單另存 XML | false |
| `backup_binary` | 布林 | 匯出時複製一份 `.project` 到同步資料夾 | false |
| `safety_backup` | 布林 | 匯入前備份 `.project` | true |
| `backup_name` | 字串 | 備份檔名 | 空 |
| `backup_retention_count` | 整數 | 備份保留數 | 10 |
| `save_after_import`、`save_after_export` | 布林 | 同步後存檔 | true |
| `auto_delete_orphans` | 布林 | 匯出時自動刪磁碟孤兒 | false |

讀檔那一支是唯一的驗證：不認識的鍵、型別不對、`plc` 裡有不認識的字、JSON 壞掉，整個命令拒絕，訊息列出十一個鍵和各自的預設值。檔案是人手改的，打錯字必然發生，安靜地沒效果比錯誤更糟。

沒有電腦名稱戳記，沒有工具版本戳記。前者是「資料夾在不在這台機器上」的代理人，而且只有對話框那條路會寫它；後者想擋的情況被 D15 排除了，只會在每次升級後多要一個旗標。`.st` 檔和同步資料夾的路徑一如既往不受這個檔影響（4.5）。

### 4.5 磁碟格式

沿用現有格式，一個位元組都不改（D15）：

- 每個物件一個 `.st`，宣告區與實作區用 `// === IMPLEMENTATION ===` 分隔。
- 路徑跟 IDE 樹一致，POU 的成員放在以 POU 命名的資料夾底下，例如 `Function Blocks/MC_BasicControl/MC_BasicControl.Main.st`。
- 只有關鍵字表達不了的種類才蓋 `//% cds-text-sync.kind=<kind>` pragma：持久性 GVL、參數清單、action、介面方法。
- 編譯屬性用 `//% cds-text-sync.<attr>=true`：`exclude_from_build`、`link_always`、`external_implementation`、`enable_system_call`。
- 種類與 GUID 的對照在 `profiles/default.json`：`guid_aliases`（每個 kind 一串 GUID，第一個是建物件時用的主 GUID）、`legacy_kind_names`、`sync_direction`（`bidirectional`、`export_only`、`import_only`、`disabled`）。有幾種 kind 由那個檔決定，這裡不抄。
- `sync_cache.json` 是本機狀態，gitignore。`sync_metadata.json` 與 `*.log` 只在 debug 開著時寫。

---

## 5. 架構

### 5.1 四層

```
IDE 側（IronPython 2.7，只有標準函式庫）
  engine/   同步引擎與四支入口的本體：分類、匯出、比對、匯入、
            備份、快取、編譯、線上預檢、PLC 連線與下載
  cds/ide/  看門人、替身 UI、訊息庫、專案資訊、狀態視窗、無頭啟動器的 IDE 側
  stub      Project_export.py、Project_import.py、Project_watch.py

兩邊都跑（Python 2/3 相容，標準函式庫）
  cds/core/ 檔案協定：目錄、實例登記、命令與結果

IDE 外（CPython 3.11 以上）
  cdsint/   CLI、無頭啟動器的 CLI 側、IDE 安裝探測、report 判讀
  tools/    維護者的儀器：call tree、cache doctor、perf probe、幾支探針。
            有幾支、各做什麼，readMe 的 `tools/` 一節說了算，這裡不抄
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
    啟動器 projects.open() 開專案，把 --sync-dir 當這一趟的覆蓋值放進每個命令的引數，預先填 prompt_answers
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
      Project_export.py   寫死本體路徑，把它加進 sys.path，呼叫本體
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

`engine/` 底下的同步引擎，加上四支入口的本體。對它的要求：

- **髒檔保護**。匯出時若磁碟上的 `.st` 自上次同步後被改過而還沒匯入，不覆蓋，列出來報「待匯入」。判斷在 `ObjectManager._disk_moved_since_sync`，只在兩邊內容確定不一樣之後才問，問的是「這個檔的 mtime 與大小跟上次同步記下的一不一樣」；一樣就是 IDE 那邊動了，照舊覆蓋，不一樣就是磁碟這邊動了，留著不寫，路徑進 `data.pending_import`，而且那一趟 `ok` 是 False。快取裡沒有這個檔的紀錄時不擋，因為那不是「沒被改過」而是「不知道」——快取是本機狀態又 gitignore，剛 clone 的資料夾一筆都沒有。只看的命令不准把這個依據拿走：`find_all_changes` 對「不同」與「這一趟讀不到」的物件保留舊的快取項目，因為那一項描述的是「上次同步的時候磁碟長什麼樣」，而那正是這個判斷要問的事。以前它只寫回自己看到相同的那些，於是任何一次 `compare`、`verify`，或是沒有確認的 `import`（比對跑在確認對話框之前），都會讓下一次匯出直接蓋掉那個編輯。
- **每次操作只存檔備份一次**。
- **等待人按鈕的時間不算進耗時**。
- **新寫的程式碼不准空白 `except:`**。搬過來的那些不要求一次清完，但每次碰到的函式順手改。`tests/test_bare_excepts.py` 是棘輪，新寫的地方釘在零，搬過來的每個檔各記一個數字，只准往下。
- **對話框只透過 `codesys_ui.ask_yes_no`、`system.ui.choose`**，因為替身 UI 只攔這兩個。新的對話框要先登記在替身 UI 的答案表裡，`test_every_yes_no_dialog_has_an_answer` 會擋沒登記的。那條測試問 `engine/` 目錄現在有哪些檔，只維護一張排除清單，所以加一支新的引擎模組不會漏掉。
- **成功失敗的訊號**走回傳值（D11）。每一條 `return` 都要回一個 `result()`，訊息等級不再影響判決。

### 6.2 看門人

規格在 `docs/WATCHER.md`，本文不重抄。要點：

- 實例目錄 `%LOCALAPPDATA%\cdsint\instances\<專案主檔名>-<pid>\`，登記檔每 2 秒心跳，`busy` 的登記檔永不自動清。
- 命令先刪後跑。一個做到一半死掉的匯入寧可讓呼叫端逾時，也不要重跑。
- 同一個 IDE 不准兩支看門人。
- 有狀態視窗（`cds/ide/statusform.py`），顯示在做什麼、做了幾個、上一個結果。視窗標題是 `cdsint`。

### 6.3 CLI

套件叫 `cdsint`，行為是 4.2 那張表。結構上拆成：目標解析與結果印製、無頭啟動器、IDE 安裝探測、PLC 子命令，各自一個模組，每個不超過 300 行。

### 6.4 無頭啟動器

CLI 側是 `cdsint/headless.py`，IDE 側是 `cds/ide/headless.py`。行為是從分紙機專案的 `codesys-probe.ps1` 與它的 Python 版搬過來的，兩支都已退役，這裡是唯一的一份。要保留的行為，每一條都是踩過坑才寫的：

| 行為 | 為什麼 |
|---|---|
| 列出安裝：掃 `Program Files` 的 `CODESYS *` 與 `Delta Industrial Automation\DIAStudio\DIADesigner-AX*`，讀 `Profiles\*.profile.xml` 的檔名當 profile 名 | `--noUI` 沒有 `--profile` 直接退出，而正確的名字是「CODESYS V3.5 SP21 Patch 4」這種形狀，不是安裝目錄名 |
| 查登錄檔 `AppCompatFlags\Layers` 有沒有 `RUNASADMIN` | manifest 是 asInvoker 的 exe 仍然可能被這個旗標擋，錯誤訊息不會說是誰要求的 |
| 多於一套符合就拒絕，不猜 | 這台裝了五套，猜錯會安靜地探到不相干的那套 |
| 開跑前查 `.~u` 鎖檔，兩種檔名形狀都查 | 省下二十秒 IDE 啟動，訊息裡有人看得懂的路徑 |
| 專案路徑走環境變數，不走 `--project` 也不走 `--scriptargs` | `--project` 在 `--noUI` 底下不會真的開專案；`--scriptargs` 的引號規則吃不了中文路徑 |
| 命令列組成單一字串，不用陣列 | PowerShell 5.1 的陣列參數會重新加引號弄壞 `--profile="有空白的名字"` |
| stdout 與 stderr 重導向到跟 report 同名的檔案 | GUI 子系統的 exe 從 shell 拿不到輸出；檔名跟著 report 走是為了兩個行程並行不搶檔 |
| 逾時就 kill。report 不完整（沒有 `intended_exit`）才當成「有對話框卡住」；report 完整就以 report 為準，只記「腳本做完了但 IDE 沒在期限內退出」。kill 之後等行程真的不在 | 掛住比報錯難查十倍；而一份完整的 report 就是證據，不該被一個慢的關閉蓋掉 |
| kill 之後只清「這一趟開跑之前不存在」的鎖檔，清了就寫進 `notes`；開跑前就有鎖檔（也就是用了 `--force-lock`）就留著不動，並說明為什麼 | `--force-lock` 的意思是「還是跑」，不是「那個鎖是我的」。把它清掉可能放掉另一個 IDE 真的開著的專案，下一趟就有兩個 IDE 開同一個專案。行程沒被 kill 掉的時候同理，鎖也留著 |
| 腳本把打算用的退出碼寫進 report，CLI 比對實際收到的 | 退出碼傳不傳得回來要驗，驗不過就改看 report |
| `system.prompt_handling` 開 `LogMessageKeys`，沒答到的提示會把鍵名印出來；`--answer KEY=VALUE` 填進 `prompt_answers` | Delta 1.10 開 1.8 的專案會問要不要升級，預設答案是「不開了」。這是 D7 明寫的例外 |
| 開完不 close | close 會問要不要存檔，`--noUI` 底下沒人能答 |

已知還沒解的：Delta 1.10 無頭、專案剛升級過儲存格式之後第一次 `save()` 丟 NullReferenceException。啟動器印一行繼續，不中止。

表裡「專案路徑走環境變數」的落地是一個環境變數 `CDSINT_HEADLESS_JOB` 指向一個 JSON 工作檔，
專案路徑、命令清單、`--answer` 的答案都在裡面；理由跟那一列一樣，而且順帶讓兩側不必為了
每個新旗標各長一個環境變數。IDE 側跑完寫 JSON 報告，CLI 側再把只有外面知道的事補進去：
`stdout_reached`（兩個標記都看到才算）、`exit_code_actual` 與 `exit_code_trusted`、`timed_out`。

### 6.5 權限

D8 的落地。

**設定檔的 `plc` 清單**（4.4），元素只認 `connect` 和 `download`，大小寫不拘，預設空。`plc` 命令執行前先查，不在清單裡就回 exit 5，拒絕訊息說三件事：檔案在哪、現在的值是什麼、要加什麼。拼錯的字不會被猜成正確的那個，讀檔那一支會把它原樣印出來拒絕整個命令（4.4）。

**`plc download` 另外要 `-y`。** 沒給就印出這趟會做什麼（完整下載、停機、寫開機應用程式、啟動），回 `needs_input`，exit 1。這跟 `import` 沒給 `-y` 一模一樣。exit 5 只有「清單沒開」一個意思。

第一層以前有「只有人在 IDE 裡能寫」這一層意思，那是專案屬性時代的事（D8）。現在它是一個文字檔裡的一個鍵，誰能寫檔誰就能寫它。真正的門是 `-y`，它已經在。

其他所有命令不受權限管。

### 6.6 PLC 連線與下載

從探針搬，放在引擎裡跟 `codesys_online.py` 並排（D12），只在 `--project` 形式提供（D8）。分成四個檔：`entry_plc.py` 是兩個命令的門面，`plc_trip.py` 是一趟的步驟，`plc_link.py` 是連到控制器的那一段，`plc_crc.py` 是判定本身（純位元組、路徑與 JSON，不碰 IDE）。

- `connect`：把 `online.auth_fallback_modes` 設成 `CredentialSourceKind.None` 關掉憑證對話框（ScriptEngine 4.2.0.0 實測是可寫屬性，不是方法；屬性不存在才退而呼叫 `set_auth_fallback_modes`，兩個都沒有就拒絕連線，因為 `--noUI` 底下一個關不掉的對話框是掛住不是失敗），帳密只從環境變數 `CDS_DEV_USER`、`CDS_DEV_PASS` 讀（D14）。列閘道，`find_address_by_ip`，`set_gateway_and_ip_address` 設到裝置節點，`create_online_device` 連線，列 `PlcLogic/Application`，拉 `Application.crc` 取第 5 到 8 個位元組。有原始碼封存就拉回來。不編譯任何東西。
- `download`：先拉一次控制器現在的 `Application.crc`，然後 `login(OnlineChangeOption.Never, False)` 完整下載、`create_boot_application`、`start`、`logout`，再拉一次。兩次的值一定要不一樣——每次編譯都會在 boot application 的每個區塊蓋一個新的四位元組識別碼，所以下載真的落地了值就會變；沒變就是「沒有報錯但什麼都沒寫進去」，這趟算失敗。落地了就把新的值記下來。
- **比的是什麼。** 控制器現在的 `Application.crc`，對上這個專案上一次下載完留在這台控制器上的那個值。紀錄寫在專案檔旁邊的 `<專案名>.cdsint-plc.json`，一個控制器一筆（鍵是 `IP:埠`；沒給 `--gateway` 的那種跑法鍵是 `project`），所以同一份副本可以同時服務兩台台架而不互相蓋掉。專案複製到別的地方，紀錄不跟著走，那是對的——它描述的是這一份工作副本做過什麼。
- **不比本機編出來的 boot application。** 那是原本的做法，在台架上量出兩個獨立的理由都不成立（2026-09-06，3.5.21.40／ScriptEngine 4.2.0.0）：一，控制器上的 `.app` 是 2118764 位元組，離線編的是 2098340，有 168 萬個位元組不同，兩個檔案根本不是同一個東西，CRC 不可能相等；二，離線那個值不是原始碼的性質，只要專案被寫過就會換一個——把裝置指到閘道會換，登入會換，設一個專案屬性也會換，而 `--project` 每一趟都會設 `cds-sync-folder`，所以兩趟隔一分鐘的 `plc connect` 編出 128DBA21 與 59B20109。它只對「沒被碰過的工作副本」穩定，連同樣位元組的副本換個路徑都不一樣，因為它來自 IDE 放在專案檔旁邊的 `.compileinfo` 與 `.bootinfo`。
- **`MATCH` 的意思因此比原本窄：「這台控制器上還是 cdsint 從這個專案放上去的那份」，不是「控制器跑的是這棵原始碼樹」。** 專案改了沒有重新下載，`connect` 仍然回 `MATCH`，因為控制器確實沒變。專案跟磁碟一不一致由 `compare` 與 `verify` 回答，它們把每個物件讀過一遍，那是唯一不會漏掉「改了但沒存檔」的問法。要更強的宣稱只有一條路：下載時一併做 source download，`connect` 再把原始碼封存拉回來比，那是另一件事，還沒做。
- 這兩個命令的 report 要包含比對結果 `MATCH` 或 `DIFFERENT`，pipeline 拿這個當閘門。

還有幾件事。`connect` 只在給了 `--gateway` 的時候才動裝置節點的閘道設定；沒給就用專案自己帶的，
因為那是別人設過的答案，一個唯讀命令不該順手改掉它。`--port` 不給就用 11740。
專案裡不只一個裝置節點時兩個命令都拒絕並列出名字，沒有旗標可以指定哪一個，猜一個下載目標不是可以有預設值的事（D7）。
比對的三種答案是 `MATCH`、`DIFFERENT`、`UNKNOWN`，兩邊有一邊拿不到就是 `UNKNOWN`；只有 `MATCH` 是 exit 0，
理由是這兩個命令外面沒有 `verify` 那種把發現變成判決的東西，退出碼本身就得是判決。
本機的 boot application 與從 PLC 拉回來的檔案寫在 `%TEMP%\cdsint\plc\<專案名>\`，同一個專案每次覆蓋，
寫之前先刪，免得某次呼叫沒寫檔而讓上一趟的答案被讀成這一趟的。

### 6.7 設定流程

設定的三條路，各自對應一種使用者：

1. **第一次跑。** `Project_export.py` 或 `Project_import.py` 啟動時若設定檔沒有 `sync_folder`，開資料夾對話框。選到的資料夾在專案檔那一層或底下就寫成 `./...`，其他情形（別的磁碟、專案外面）維持絕對路徑，理由是 `..\..\` 這種相對路徑只在專案不搬家時才成立。寫出只有 `sync_folder` 一個鍵的設定檔，建目錄，寫 `.gitattributes` 與 `.gitignore`。確認訊息說其他設定和預設值在 readMe 的設定表。這個對話框沒有旗標可以回答，所以無人時（`--target` 形式，或 `--project` 形式沒給 `--sync-dir`）回 `needs_input`，訊息說去專案旁寫哪個檔、哪個鍵，或從選單跑一次匯出。
2. **之後要改。** 開檔案改。沒有 `config` 命令、沒有 Settings 視窗，因為那是同一個檔案的第二個編輯器，每加一個鍵就要多一列。
3. **這一趟臨時換資料夾。** `--sync-dir`，語意在 4.2。

不再有的：電腦名稱不符的對話框、版本不符的對話框、`--force`（4.4 說了為什麼）。

---

## 7. 相容性矩陣

這一節跟本文其他地方不同：它是量測紀錄，不是規格。每一格說的是「到那一天為止有人驗過什麼」，所以每張表都標了日期，而且日期比數字重要 — 沒標日期的量測沒有意義。

**相容性矩陣，2026-09-06 為止。**「驗過」是有 report 或真人紀錄的意思，其餘是「應該可以」。

| 功能 | 原廠 3.5.21.40 | Lenze 3.24 | Lenze 4.0 | Delta 1.8 | Delta 1.10 |
|---|---|---|---|---|---|
| 選單匯出匯入 | 驗過 | 驗過，日常在用 | 裝過，未驗 | 驗過，k1.1.1 的 bug 就是在它上面抓到的 | 驗過 |
| 看門人不卡 IDE | 驗過，真實點擊 | 應該可以，同 4.0.0.0 | 應該可以 | 應該可以 | 驗過，真人 |
| CLI export、import、build | 驗過，229 個物件 | 未驗 | 未驗 | 未驗 | 驗過 |
| 無頭起得來 | 驗過 | 驗過 | 未驗 | 未驗 | 驗過 |
| 無頭開得了專案、跑得了引擎 | 驗過 | 未驗 | 未驗 | 未驗 | 驗過 |
| 無頭 build | 驗過 | 未驗 | 未驗 | 未驗 | 驗過，要修過才會真的編譯，見底下 |
| `verify --project` 一條命令跑完 | 驗過 | 未驗 | 未驗 | 未驗 | 驗過 |
| PLC connect、download | 驗過，2026-09-06 兩台 WSL soft PLC 整輪 | 未驗 | 未驗 | 未驗 | 未驗 |

這張表的每一格都是「同一家 IDE 開它自己的專案」。2026-09-05 各驗了一輪：原廠 3.5.21.40 開 softplc 副本、Delta 1.10 開 Shm 副本，`export`、`import`、`compare`、`build` 都 exit 0，229 個物件，build 0 errors。同一天稍晚用 `verify --project` 對同樣兩個副本各再跑一輪，四步全過。

PLC 那一列的細節（2026-09-06，兩個 WSL soft PLC）：A 與 B 各 `download -y` 接 `connect` 都是 `MATCH` exit 0；同一台連下兩次，控制器的值從 DC848126 變成 CF9DD644，所以 6.6 說的「值沒變就是沒落地」這條檢查在真機上站得住；換一份副本下載到 A 之後，原本那份 `connect` 回 `DIFFERENT` exit 1，而 B 不受影響仍是 `MATCH`。`connect` 不編譯，一趟 63 到 71 秒。

**ScriptEngine 4.0.0.0 的 build 有兩個坑，兩個都是在 Delta 1.10 上量出來、修掉的**，Lenze 3.24 同版本應該一樣（未驗）。一是 `get_message_objects` 在 4.0.0.0 沒有單參數的形式，兩個多載都要再給一個 severity；只給 category 會丟 `Value cannot be null. Parameter name: category`，整份 build 結果就變成一個 traceback。二是那個 category 還得正在裝著訊息，一次什麼都沒重編的 build 讓它空著，同一個呼叫同樣丟那句話。4.2.0.0 兩件都容忍，所以原廠一直沒露出來。

更要緊的是底下那一個：**Delta 1.10 一個行程裡的第一次 `app.build()` 不會真的編譯**。同一個 IDE 連跑三次量到 7.4 秒沒有任何訊息、31.7 秒 101 個警告、5.8 秒同樣 101 個。而 `--project` 形式一個行程只跑得到第一次，所以它本來會回報一份它根本沒編過的乾淨結果。現在的做法是：一次 build 如果連自己的摘要行都沒寫，就再 build 一次；兩次都沒有的話回報「這台 IDE 沒有產出任何 build 輸出」而不是 0 個錯誤。

跨家開專案是另一回事，而且現在有明確的行為：原廠開 Delta 的 Shm 專案時，7 個物件的外掛不在，三個命令都 exit 1、把那 7 個名字放進 `data.failed_objects`、其他 229 個照常處理完（D13、D11）。這不是「支援跨家」，是「跨家時不騙人」。

**效能基準，229 個物件，2026-09-05 量的，commit `1645a62`。**每格是三次的中位數。
量的是命令那一步的 `elapsed_s`，也就是報告裡呼叫端看到的那個數字；IDE 啟動加開專案不算在內，
另外列在底下。原廠開 softplc 副本，Delta 開 Shm 副本，各自開自己家的專案。

條件：export 每次跑之前把同步資料夾清空，所以每次都是 229 個檔案從頭寫；
compare 之前在磁碟上改一個 POU，所以剛好一個差異；build 兩次之間什麼都不動。

**同一台機器有沒有剛跑過，差兩到三倍，這是這次量到最重要的一件事。**

| 操作 | 原廠（機器冷） | 原廠（機器熱） | Delta（機器冷） | Delta（機器熱） |
|---|---|---|---|---|
| export | 33.4 秒 | 12.2 秒 | 26.6 秒 | 9.9 秒 |
| compare，只改一個 POU | 30.6 秒 | 10.9 秒 | 23.7 秒 | 8.6 秒 |
| build | 44.1 秒 | 14.8 秒 | 42.9 秒 | 16.3 秒 |

「冷」是這台機器一陣子沒有起過無頭 IDE 之後的頭幾趟，三次之間差到 ±20%（Delta 的 build 從
23.9 到 45.4 秒）。「熱」是同一組再跑一遍，三次之間差不到 2%。整趟的牆上時間跟著走：
冷的時候一趟 78 到 184 秒，熱的時候 33 到 48 秒，差的那一段是 IDE 啟動與開專案。

差別不是專案副本也不是同步資料夾的路徑：熱過之後另外複製一份全新的專案到一個從來沒用過的
路徑，再跑一次 export，還是 12.1 秒。所以是整台機器的狀態（作業系統的檔案快取、.NET 組件、
防毒對新路徑的掃描這一類），不是任何一份檔案。要拿數字比較的人，兩邊都得是同一種狀態。

更早的一組基準是 export 59.7／56.6 秒、compare 50.6／47.1 秒、build 23.3／32.5 秒，同樣 2026-09-05、
同樣 229 個物件，但那一組沒有記錄機器是冷是熱，也沒記錄同步資料夾是不是空的，
所以只能當參考，不能拿來算改善幅度。

**`verify --project` 一整趟，同樣 229 個物件，2026-09-05 量的。**這一組的每一步都是
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

**規則寫在 `PRINCIPLES.md`**，尺寸上限分兩級：本 repo 寫的程式碼適用硬上限，搬來的 `engine/` 只要求「碰到的函式不能變長、新加的函式與檔案遵守上限」。文件跟程式碼講不同的話，比沒有文件更糟。

**測試分三層**：

| 層 | 跑在哪 | 怎麼做 |
|---|---|---|
| `cds/core` 與 CLI 的純函式 | CI | 一般單元測試 |
| 引擎邏輯 | CI | 對假 IDE 物件跑，替身在 `tests/fakes.py` |
| 真 IDE 驗收：無頭起一個專案副本，跑 export、import、build，比對輸出 | 本機，手動或排程，三家各一次 | `cdsint verify --project` 就是那個腳本。`--target` 那半要一個開著的 IDE，`tools/headless_watch.py` 起得出來 |

**CI** 在 push 到任何分支都跑，不只 `main` 與 `claude/**`。

**版本只有一個來源**：`engine/codesys_constants.py` 的 `SCRIPT_VERSION`。`pyproject.toml` 用 `[tool.setuptools.dynamic]` 的 `version = {attr = "engine.codesys_constants.SCRIPT_VERSION"}` 直接讀那一行，看門人登記檔由 `stub/Project_watch.py` 傳進去，readMe 不寫版本號。沒有 release 腳本也不需要：一個 release 就是改那一行加打一個 tag。

---

## 9. 文件

- `readMe.md`：定位、三個場景各一段十行內的例子、安裝（三家的 ScriptDir 表）、CLI 命令表、exit code、權限、FAQ。安裝來源指向本 repo。`WORKFLOW.md` 裡還成立的內容併進三個場景那段。
- `docs/AI_WORKFLOW.md` 與 `skills/cdsint/SKILL.md`：場景 B 的操作手冊，跟著改路徑與命令名。加上 `--project` 形式那一段。
- `docs/SPEC.md`：本文，做完的樣子。
- `docs/WATCHER.md`：新檔。看門人的協定規格、看門人規格、計時器設計，從 `WATCHER_CLI_PLAN.md` 第 5、6、14 節抽出來。程式碼裡引用節號的六處指標改指它。
- `docs/history/`：做完的工單、被取代的研究、搬出去的施工順序。都是某一天的決策紀錄，不描述今天的程式碼，所以不改也不維護。
- `CHANGELOG.md`：每個 release 一段，寫「症狀、根因、改法」，不寫檔案清單。

---

## 10. 從現在的 repo 走到這裡

這一節的施工順序已經走完，整節搬到 [`docs/history/SPEC_10_CONSTRUCTION.md`](history/SPEC_10_CONSTRUCTION.md)。

---

## 11. 未決事項

1. **速度引擎。** 要不要換成 `export_native` 整包倒出，對著第 7 節的基準表決定。換的話是引擎內部的事，三個入口與磁碟格式不動。
2. **Delta 1.10 無頭升級後 `save()` 的 NullReferenceException。** 沒查到根因。先繞過，記在相容性矩陣。
3. **看門人跑著時 Scripts 選單能不能啟動別的腳本。** 沒驗過。
