# 給 agent 的工作迴圈：改 `.st`、同步進 IDE、編譯、看錯誤、修

這份是寫給「會跑 shell 但看不到 IDE 畫面」的人或 agent 看的。目標是讓你自己完成一輪
「改程式、進 IDE、編譯、讀錯誤、再修」，不必請人去點選單。

CODESYS 的專案檔是二進位的，你改不了。你能改的是同步資料夾裡的 `.st` 文字檔，
再叫 IDE 把它們讀進去。

有兩種情況，命令一樣，只差你怎麼指定要驅動哪個 IDE：

- **人開著 IDE**，你用 `--target` 對他那個 IDE 裡的看門人下命令。這是第 0 節到第 3 節。
- **沒有人、也沒有開著的 IDE**，你用 `--project P --install I` 讓 cdsint 自己起一個
  無頭的 IDE、跑完、收掉。這是第 4 節。

兩組旗標不能同時給，argparse 會直接擋。原因是 CODESYS 不允許兩個行程開同一個專案檔，
所以同一條命令本來就只有一條路走得通。

---

## 0. `--target` 形式的前提：IDE 開著、看門人啟動了

第 0 到 3 節講的都是「人開著 IDE」那條路。IDE 沒開的話直接跳到第 4 節。

人要先做兩件事，你做不到：打開 CODESYS 或 DIADesigner、開好專案，
然後從 **Tools > Scripting** 跑一次 `Project_watch.py`。那支腳本會立刻結束，
IDE 照常可以用，但它留下了一個監聽器。

你這邊確認它在：

```
cdsint list
```

看得到一行就對了，長這樣：

```
Shm_2026.07.29-14012    idle    D:\...\Shm_2026.07.29.project
```

**什麼都沒有的話就停下來，請人去啟動 `Project_watch.py`。** 不要自己想辦法啟動它，
從命令列開一個新的 IDE 實例是開不了人家已經開著的那個專案的（專案檔會被鎖住）。

同步資料夾在哪，問 `status`：

```
cdsint status --json
```

回來的 JSON 裡 `data.sync_dir` 就是那個資料夾的絕對路徑。**這是你唯一該編輯的地方。**
如果它是 `null`，代表那個專案的設定檔還沒寫同步資料夾（第 5 節），請人去寫，你不要猜。

---

## 1. 迴圈

```
編輯 sync_dir 底下的 .st
        ↓
cdsint compare          看差異，什麼都不會被改
        ↓
cdsint import --yes     把磁碟上的改動送進 IDE
        ↓
cdsint build            編譯，看錯誤數
        ↓
有錯 → 讀錯誤訊息 → 回到第一步
```

每一步都先看 exit code，再看輸出。

### `compare`：先看清楚再動手

```
cdsint compare
```

它只讀不寫。人類可讀的輸出有兩層：一行摘要（改了幾個、只在 IDE 有幾個、只在磁碟有幾個），
以及逐物件清單。兩層都從 `data` 來：計數在 `different`、`new_in_ide`、`new_on_disk`、`moved`，
逐物件清單在 `data.changes`，每筆有 `name`、`path` 與 `state`（`changed`、`new_in_ide`、
`new_on_disk`、`moved` 之一）。搬過位置的那一筆多一個 `moved_from`，`path` 是它現在在磁碟上的
位置。用 `--json` 讀的是同一份東西。

若它回報 `failed_objects`，下一步是 `cdsint discover`（見第 4 節）。

**改完之後先 compare 一次是好習慣**，因為它會告訴你 IDE 那邊是不是也有人動過。
如果同一個物件兩邊都改了，匯入會以磁碟為準覆蓋掉 IDE 那邊。

### `import`：磁碟蓋過 IDE

```
cdsint import --yes
```

`--yes` 是必要的，那是「我確定要改這個專案」的意思。不帶它的話命令會回 `needs_input`、
exit code 1，**而且 IDE 裡什麼都不會變**——這是設計，不是失敗。

匯入是**磁碟贏**。磁碟上有、IDE 裡沒有的檔案會被建立成新物件；兩邊都有但內容不同的，
以磁碟為準。這也是為什麼不確定的時候要先 `compare`。

磁碟贏也表示：同步資料夾底下一個 `.st` 都沒有的時候，匯入會**拒絕執行**。空資料夾不是
「這個專案應該是空的」這個答案，是還沒 export 或路徑指錯，照磁碟贏做下去等於把專案裡
每一個物件都刪掉。三條路（選單、`--target`、`--project`）都一樣拒絕，訊息會說是哪個
資料夾。碰到的話先跑 export，或去修設定檔的 `sync_folder`（`--project` 形式可以改用
`--sync-dir`）。

### `build`：編譯，拿錯誤數

```
cdsint build
cdsint build --app MyApplication     # 專案有多個 application 時
```

結果的 `messages` 裡會有 application 名稱、錯誤數、警告數、耗時。錯誤數大於 0 時
exit code 是 1，錯誤的詳細內容（訊息、物件、行號）在 `stdout_tail` 裡。

專案有多個 application 而你沒給 `--app` 的話，會回 `needs_input` 並列出可選的名字。

### `export`：從 IDE 倒出來

```
cdsint export
```

方向相反：把 IDE 裡的東西寫成 `.st` 檔。你通常在開工前跑一次，確保磁碟上的檔案是最新的；
或者在匯入之後跑一次，確認 IDE 真的收下了你的改動。

---

## 2. 怎麼讀結果

### exit code

| Code | 意思 | 你該做什麼 |
|---|---|---|
| 0 | 成功 | 往下走 |
| 1 | 命令失敗，或缺一個旗標 | 讀 `error` 與 `needs_input`，補旗標或修錯誤 |
| 2 | 命令列本身不對：旗標湊不起來，或找不到唯一一個活著的 IDE | 別重跑同一行。旗標的問題照訊息改；IDE 的問題跑 `list` 看有幾個，用 `--target` 指定 |
| 3 | 等結果等到逾時，而且沒有拿到報告 | 加大 `--timeout`（預設 120 秒，指的是**一個步驟**的上限），大專案的匯入會超過 |
| 4 | 專案被別的行程開著，或 IDE 起不來 | 只有 `--project` 形式會出現，見第 4 節 |
| 5 | 這個專案沒有開放你下的那個 `plc` 命令 | 沒有旗標可以補。去專案旁的設定檔把那個字加進 `plc` 清單，見第 6 節 |

### `--json` 的結構

```json
{
  "ok": true,
  "command": "build",
  "elapsed_s": 7.4,
  "messages": [{"level": "info", "text": "MyApp\nErrors: 0\nWarnings: 2"}],
  "stdout_tail": "…腳本印出來的最後 200 行…",
  "error": null,
  "needs_input": null,
  "denied": null,
  "data": null
}
```

`--project` 形式再多四個欄位：`ide`（用了哪套）、`sync_dir`、`report_path`，以及 `notes`。

- `messages` 是 IDE 本來要彈給人看的對話框內容，`level` 是 `info`、`warning` 或 `error`。
- `stdout_tail` 是腳本一路印出來的最後 200 行。build 的錯誤清單（物件、行號）在這裡；
  compare 的逐物件差異不在，它在 `data.changes`。一趟成功的命令不會印它。
- `error` 有值就代表失敗，`ok` 一定是 false。
- `needs_input` 有值代表「有個問題沒人回答」，裡面的 `arg` 直接告訴你該補哪個旗標。
- `denied` 有值代表這個專案不准你下這個命令（只有 `plc` 會出現），exit code 是 5。
  這個不是補旗標能解決的，見第 6 節。
- `notes` 是啟動器對這一趟說的話，不是對工作說的：清掉了一個鎖檔、不得不 kill 一個 IDE、
  退出碼跟腳本自己記的對不上。只有 `--project` 形式有。一趟的每一筆紀錄帶同一份清單，
  所以 `verify` 的四筆讀任何一筆都夠。
- `data` 是這個命令自己的數字與清單：匯出匯入的計數、compare 的差異數與 `changes`、
  build 的錯誤與警告數。處理不了的物件會以名字列在 `data.failed_objects` 裡，而且 `ok` 是 false。
  這個清單不空的時候，下一步是 `cdsint discover`：它走同一棵樹，把沒有任何 kind 認得的
  型別 GUID 連同一個例子物件的名字列出來（`data.unknown`）。把那些 GUID 接到
  `profiles/default.json` 的 `guid_aliases` 裡對應 kind 的清單後面，再跑一次。
- 匯出還有一個 `data.pending_import`：那些檔案你在磁碟上改過而還沒匯入，匯出不會覆蓋它們，
  也會讓那一趟 `ok` 是 false。這不是錯誤，是提醒你先跑一次 `import`（或者你不要那份改動，
  就把檔案刪掉再匯出一次）。
- `--project` 形式的紀錄還多三個欄位：`ide`（用了哪一套）、`sync_dir`（這一趟把哪個
  資料夾當成事實來源）與 `report_path`（完整報告在哪）。

### `needs_input` 出現時

不要重試同一個命令，也不要猜。照 `arg` 補旗標：

| `arg` | 補上 | 那個問題是 |
|---|---|---|
| `yes` | `--yes` | 「確定要把 N 個改動匯入 IDE 嗎？」 |
| `app` | `--app <名稱>` | 專案有多個 application，要編哪一個 |
| `delete_orphans` | `--delete-orphans` | 匯出時，同步資料夾裡有 IDE 已經沒有的檔案，要刪嗎 |

還有一種 `needs_input` 沒有旗標可以補：專案還沒有同步資料夾。訊息會告訴你要在專案旁邊
寫哪一個檔、裡面放什麼（第 5 節），或者這一趟先用 `--sync-dir` 頂著。

---

## 3. 命令執行中 IDE 會忙，那是正常的

看門人等待命令的時候不佔用 IDE，人照樣可以打字。但**命令真正在跑的那幾秒到幾十秒，
IDE 會停止回應**——匯出、匯入、編譯都是這樣。原因是 CODESYS 的物件模型只能在 UI 執行緒上呼叫，
這是平台的性質，工具改不了。

對你的影響有兩個。一是不要在一個命令還沒回來的時候送下一個，等它回來。
二是大專案的匯入或編譯可能超過預設的 120 秒逾時，該加大就加大。`--timeout` 說的是
**一個步驟**的上限，兩種形式一致。`--project` 形式還要起一個 IDE，所以它的行程期限是
「啟動寬限 + 步數 × timeout + 關閉寬限」，實際等待會比你寫的數字久：

```
cdsint import --yes --timeout 600
```

---

## 4. 沒有開著的 IDE：`--project` 形式

沒有人在鍵盤前的時候，改用這一組旗標，cdsint 會自己起一個無頭的 IDE、開專案、
跑命令、寫報告，然後讓那個行程自己結束。

先看這台有哪些 IDE：

```
cdsint installs
```

每一套印出名字、執行檔、profile 名稱與 ScriptDir。`--install` 收的就是那個名字的一段，
例如 `3.5.21.40` 或 `DIADesigner-AX 1.10`。**符合的不只一套就會被拒絕，不會替你猜**，
因為猜錯的代價是整趟跑在一個開不了這個專案的 IDE 上。

然後跟前面一樣的命令，換一組旗標：

```
cdsint compare --project C:\p\line.project --install 3.5.21.40 --sync-dir C:\p\exported
cdsint import -y --project C:\p\line.project --install 3.5.21.40 --sync-dir C:\p\exported
cdsint build --project C:\p\line.project --install 3.5.21.40 --sync-dir C:\p\exported --report r.json
```

`--sync-dir` 是選用的。給了就是「這一趟用這個資料夾」，它蓋過設定檔裡的 `sync_folder`，
而且永遠不寫回任何檔案——所以指著一份副本跑是安全的。不給就用設定檔裡寫的；兩個都沒有的話，
export 與 import 會回 `needs_input`，什麼都不改。真正被採用的資料夾會印在輸出第一行，
也寫在報告檔頂層的 `sync_dir`。

只有這個形式才有的旗標：

| 旗標 | 做什麼 |
|---|---|
| `--sync-dir D` | 選用。這一趟用這個同步資料夾，蓋過設定檔的 `sync_folder`，不寫回去 |
| `--report FILE` | 把完整報告寫到這裡。不給就寫進 `%TEMP%\cdsint\` |
| `--profile NAME` | 一套安裝有多個 profile 時指定用哪個 |
| `--force-lock` | 明知鎖檔是舊的殘留，硬跑 |
| `--answer KEY=VALUE` | 回答 IDE 自己彈的提示，可以給多個 |

### `verify`：一條命令跑完整趟

```
cdsint verify -y --project C:\p\line.project --install 3.5.21.40 --sync-dir C:\p\exported --report r.json
```

它依序跑 import、export、compare、build，任何一步失敗就停在那裡。exit 0 的意思是四件事
同時成立：磁碟進得了 IDE、IDE 出得來、進出一輪之後兩邊對每一個物件的看法都一致、而且編得過。
中間那一步是關鍵——import 和 export 各自都可能「成功」卻其實什麼都沒做，只有事後問
compare 還有沒有差異，這一輪才算被驗過。

`verify` 含匯入，所以跟 `import` 一樣要 `-y`，兩種形式都要。不帶 `-y` 的時候它只跑
compare，把匯入那步會改幾個、建幾個、從 IDE 刪幾個列出來，然後回 `needs_input`、exit 1，
IDE 一個物件都不動。看過那三個數字覺得對，再補 `-y` 跑一次。

### 報告檔裡有什麼

`--report` 寫出來的 JSON 除了每一步的紀錄，還記了幾件只有外面看得到的事：

- `stdout_reached`：IDE 印的東西有沒有真的回到 stdout。
- `exit_code_actual` 與 `exit_code_trusted`：腳本打算用的退出碼，跟外面實際收到的一不一致。
  不一致就代表在這台機器上退出碼不能當閘門，要改讀報告檔。
- `timed_out`：逾時被殺掉的話是 true。這時要看報告完不完整：報告裡有 `intended_exit`
  就代表腳本把四步都跑完、報告也寫好了，只是 IDE 自己關太慢被殺掉，那份報告就是答案，
  exit code 照報告走；報告不完整才是「有個沒人能按的對話框」，那趟 exit 3。
  被殺掉的 IDE 留下的鎖檔（`.~u`）只有在「這一趟開跑之前那個鎖檔不在」的時候才由 cdsint 清掉，
  並在 `notes` 印一行說明。開跑前就有鎖檔（也就是你用了 `--force-lock` 硬跑）的話它不動，
  因為那個鎖可能是別的 IDE 真的開著專案，清掉它下一趟就會有兩個 IDE 開同一個專案；
  這種情況下一趟還是要 `--force-lock`，`notes` 會說為什麼。

### 這個形式的兩個坑

**專案被開著就跑不了。** cdsint 在起 IDE 之前先看鎖檔（`.~u`），有的話直接 exit 4 並印出
鎖檔路徑，省下二十秒的 IDE 啟動。人自己開著那個專案就是這個情況，那是預期行為，不是 bug。

**IDE 自己的提示 cdsint 不會替你回答。** 舊版 IDE 存的專案開起來會問
`UpgradeProjectConfirmation`，而答 Yes 會改寫它的儲存格式，改完原本那套 IDE 就再也開不了它。
所以沒有預設答案：跑不起來的時候訊息會告訴你是哪個鍵，你決定要不要
`--answer UpgradeProjectConfirmation=Yes`。

---

## 5. 專案設定：專案旁邊的一份 JSON

同步資料夾、要不要存檔、備份幾份，這些都寫在專案檔旁邊、照專案名命名的一個 JSON 檔裡：
`Line.project` 旁邊是 `Line.cdsint.json`。它是純文字，你可以直接讀、直接改，不需要 IDE，
也沒有 `config` 命令——檔案本身就是介面。

檔案裡只放有人決定過的鍵，沒寫的鍵一律用程式碼裡的預設值：

```json
{
  "plc": ["connect"],
  "sync_folder": "./sync"
}
```

十一個鍵、型別與預設值列在 readMe 的 **Settings** 一節。`sync_folder` 以 `./` 開頭就是
相對於 `.project` 所在的目錄，其他寫法照原樣用。

**寫錯會讓整個命令拒絕執行。** 不認識的鍵、型別不對、`plc` 裡有不認識的字、JSON 本身壞掉，
任何一種都會讓命令回 exit 1，訊息裡附上十一個鍵的完整清單。這是刻意的：安靜地沒效果比
明講一句錯誤更難查。

---

## 6. 碰控制器：`plc`

`plc download` 是唯一一個會改到機器的命令，所以它前面有兩道關，而且兩道都得過。

第一道是專案准不准。設定檔（第 5 節）裡的 `plc` 是一個字串清單，只認 `connect` 與
`download` 兩個字：

```json
{ "plc": ["connect", "download"] }
```

你下的命令不在清單裡就是 exit 5，訊息會說是哪個檔、現在寫了什麼、要加什麼。
**這一道你補不了旗標。** 這是一道政策而不是一道牆——誰寫得了那個檔就寫得了這個鍵——
所以真正擋住下載的是下面那個 `-y`。要開清單的話請人去改那個檔。

第二道是這一次算不算數。`plc download` 要 `-y`，跟 `import`、`verify` 的 `-y` 同一個意思。
沒給就印出這趟會做什麼，回 `needs_input`、exit 1，控制器一個位元組都不動。

`plc` 沒有 `--target` 形式。看門人跑在別人正在用的 IDE 裡，登入控制器會搶走那個人的線上狀態，
所以 PLC 命令一律自己起一個 IDE。

```
cdsint plc connect  --project C:\p\line.project --install 3.5.21.40 --sync-dir C:\p\exported
cdsint plc download -y --project C:\p\line.project --install 3.5.21.40 --sync-dir C:\p\exported     --gateway 192.168.1.5 --report r.json
```

兩個命令最後都回同一個問題的答案：**這台控制器上跑的還是不是 cdsint 放上去的那份**。
比法是控制器現在的 `Application.crc`，跟這個專案上一次下載完留在上面的那個值比。
下載時會把那個值記在專案檔旁邊的 `<專案名>.cdsint-plc.json`，一個控制器一筆。

比的不是「本機編出來的 boot application」。那條路試過，行不通：離線編出來的 `.app`
跟控制器上那顆根本不是同一個檔（大小差兩萬多位元組），而且離線那個值每次改到專案就變一次。
量到的證據在 `engine/plc_crc.py` 的檔頭。

| `data.crc` | 意思 | exit code |
|---|---|---|
| `MATCH` | 控制器上還是上次下載放上去的那份 | 0 |
| `DIFFERENT` | 上次下載之後有別的東西被下載到這台上面 | 1 |
| `UNKNOWN` | 沒有可比的：這個專案從來沒下載到這台，或控制器上什麼都沒有 | 1 |

**這個答案不包含「專案有沒有改過」。** 改了 POU 但沒有重新下載，`connect` 還是 `MATCH`，
因為控制器確實沒變。專案跟磁碟一不一致是 `compare` 與 `verify` 的問題，
它們是把每個物件讀過一遍才回答的，那才是不會漏掉的問法。

帳密只從環境變數 `CDS_DEV_USER`、`CDS_DEV_PASS` 讀，不進命令列、不進報告。
`--gateway` 不給的話就用專案自己帶的閘道設定；給了才會去改裝置節點，`--port` 不給是 11740。

---

## 7. 多個 IDE 同時開著

`list` 會列出全部。有超過一個的時候，每個命令都要指定 `--target`，
不指定的話會以 exit code 2 結束並列出候選：

```
cdsint build --target Shm_2026.07.29
```

`--target` 收兩種值：完整的 instance id（例如 `Shm_2026.07.29-14012`），
或專案主檔名（不分大小寫）。專案名有多個 IDE 開著同名專案時才需要用完整 id。

---

## 8. `.st` 檔的格式

一個檔案就是一個物件，宣告區和實作區用一行標記分開：

```
FUNCTION_BLOCK Counter
VAR
    count : INT;
END_VAR

// === IMPLEMENTATION ===
count := count + 1;
```

檔案開頭可能有 `//% cds-text-sync.<key>=<value>` 的 pragma 行，那些是 kind 與建置屬性，
匯入時會被讀走。**不要自己刪掉或改寫 pragma 行**，除非你確定要改那個屬性。
完整說明在 readMe 的
[Sync pragmas in `.st` files](../readMe.md#sync-pragmas-in-st-files) 與
[Type profiles](../readMe.md#type-profiles-profilesdefaultjson) 兩節。

**在磁碟上新建一個 `.st` 檔就等於在 IDE 裡新建一個物件。** 檔案放在哪個資料夾，
物件就會出現在 IDE 裡對應的位置。

---

## 9. 不要做的事

- **不要改 `.project` 檔。** 那是二進位的，你改了會壞掉。
- **不要改同步資料夾以外的東西。** `sync_cache.json` 是機器本地的快取，不要碰也不要提交。
- **PLC 在線上（logged in）時不要匯入。** 工具會自己擋下來並告訴你，別想繞過；
  上線狀態下 IDE 拒絕所有物件的建立、搬移與刪除。
- **不要自己去啟動或關閉人開著的那個 IDE。** 開著的專案是人的工作現場。
  `--project` 形式起的是它自己的行程、開的是你給的專案，那條路不受這一條限制。

---

## 10. 一輪完整的例子

```bash
# 這個 IDE 開著什麼、同步資料夾在哪
cdsint status --json

# 先確保磁碟是最新的
cdsint export

# 改一個 POU（用你平常編輯檔案的方式）
#   <sync_dir>/Application/POUs/Counter.st

# 看看只有它變了
cdsint compare

# 送進 IDE
cdsint import --yes

# 編譯
cdsint build --json

# 錯誤數不是 0 的話，錯誤清單在 stdout_tail，修完回到第三步
```
