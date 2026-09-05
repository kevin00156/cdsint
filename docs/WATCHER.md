# 看門人與命令交接協定

> 這份文件描述現況，不是計畫。決策紀錄在 `docs/history/WATCHER_CLI_PLAN.md`。
> 程式碼註解引用本文用節號，例如「WATCHER.md 6」。

看門人是一個掛在 IDE 自己訊息迴圈上的計時器。它每一拍撿一次命令檔，有就執行、寫結果檔、
更新心跳，沒有就直接返回。啟動它的腳本立刻結束，所以 IDE 在兩次命令之間完全可以操作。

---

## 1. 為什麼是檔案

命令與結果都是磁碟上的 JSON 檔（SPEC D6）。IDE 側跑在 IronPython 2.7、只有標準函式庫，
CLI 側跑在 CPython 3；檔案是這兩邊唯一都不必額外安裝東西就會用的東西。

## 2. 目錄與登記檔

根目錄是 `%LOCALAPPDATA%\cdsint\instances\`，可以用環境變數 `CDS_INSTANCES_DIR` 蓋掉。
每個開著的 IDE 一個子目錄：

```
instances\
  <instance-id>.json          實例登記檔，含心跳
  <instance-id>\
    cmd\                      CLI 寫進來的命令檔
    result\                   看門人寫回去的結果檔
```

`instance-id` 是「專案檔主檔名-程序編號」，例如 `Shm_2026.07.29-14012`。專案路徑取自
`projects.primary.path`，程序編號取自 `os.getpid()`。

登記檔的欄位：`instance_id`、`pid`、`ide`、`project_path`、`project_name`、`sync_dir`、
`state`、`busy_since`、`heartbeat`、`started_at`、`watcher_version`。時間有兩份，
字串那份給打開檔案的人看，`heartbeat_epoch` 與 `busy_since_epoch` 是給程式相減用的。
存數字就不必解析本地時間字串，也避開日光節約時間那一小時的模糊地帶。

### 2.1 幾個時間常數

程式碼在 `cds/core/instances.py`。這四個數字是起點不是定案：

| 常數 | 值 | 意思 |
|---|---|---|
| `HEARTBEAT_INTERVAL_S` | 2 秒 | 看門人多久重寫一次登記檔 |
| `ALIVE_TIMEOUT_S` | 10 秒 | idle 的實例心跳多久沒更新就當它死了 |
| `BUSY_TIMEOUT_S` | 120 秒 | busy 的實例可以忙多久還算活著；CLI 的 `--timeout` 會蓋掉它 |
| `STALE_TIMEOUT_S` | 60 秒 | 啟動時清掉多久沒動靜的 idle 登記檔 |

**`busy` 的登記檔一律不清。** 「清掉死掉的行程留下的檔案」跟「判斷一個命令跑太久」是兩件事，
綁在同一個數字上，保護就只在命令跑得比逾時短的時候成立，而真專案的匯入本來就會超過兩分鐘。
卡在 `busy` 的實例用「再跑一次 `Project_watch.py`」清掉。

**不要用 `os.kill(pid, 0)` 檢查行程還在不在。** CPython 在 Windows 上的 `os.kill` 會直接終止目標行程。
要查就用 `ctypes` 的 `OpenProcess`，或乾脆只信心跳。

**覆寫登記檔的方式看執行環境。** 有 `os.replace` 就用它，覆蓋是原子的；沒有就退回「先刪目標再 rename」，
IronPython 2.7 走這條。Windows 上 `os.rename` 碰到目標已存在會直接失敗，而登記檔每兩秒覆寫同一個檔名。
這也是 CLI 判死之前要多等一拍的原因：刪掉與 rename 之間有一瞬間沒有檔案。

## 3. 命令檔與結果檔

命令檔名是 `<13 位毫秒時間戳>-<6 位隨機十六進位>.json`，看門人按檔名排序一次處理一個。
結果檔同名，放在 `result\`。

```json
{"id": "1725453665123-a3f9c1", "command": "import",
 "args": {"yes": true, "force": false}, "created_at": "..."}
```

```json
{"id": "1725453665123-a3f9c1", "ok": true, "command": "import",
 "started_at": "...", "finished_at": "...", "elapsed_s": 4.2,
 "messages": [{"level": "info", "text": "Import complete! ..."}],
 "stdout_tail": "…最後 200 行…", "error": null, "needs_input": null, "data": null}
```

- `ok` 是 false 的時候 `error` 一定有文字。
- 引擎問了問題而命令參數沒帶答案，`ok` 是 false，`needs_input` 放問題原文與該用哪個旗標回答。
- 寫檔一律先寫 `<名稱>.tmp` 再 rename 成正式名稱，讀的一方永遠看不到半個檔，也永遠忽略 `.tmp`。
- CLI 讀到結果檔就刪掉。看門人啟動時清掉 `result\` 裡超過一小時的殘留。

## 4. 命令清單

| 命令 | 參數 | 對話框怎麼答 |
|---|---|---|
| `ping` | 無 | 無 |
| `status` | 無 | 無 |
| `stop` | 無 | 無 |
| `export` | `delete_orphans`，預設 false | 「Delete Orphaned Files?」由它回答 |
| `import` | `yes` 必要、`force` 預設 false | 「Confirm Import」由 `yes` 回答，沒給回 `needs_input`；「Version Mismatch」與「Computer Mismatch」由 `force` 回答，預設不繼續 |
| `compare` | 無 | 互動式挑選視窗在無人模式開不了，換成一則寫著數字的訊息；逐物件的清單本來就印在 stdout，會進 `stdout_tail` |
| `build` | 多個 application 時要 `app` | `system.ui.choose` 用 `app` 的名字對應選項，沒給回 `needs_input` |

## 5. 一拍做什麼

程式碼在 `cds/ide/watcher.py`，可以在 CPython 底下完整測試，因為它把 IDE 的全域當參數收。

1. 還在跑嗎、正在忙嗎、`silent.running()` 嗎，三個有一個成立就直接返回。
2. 撿一個命令檔，**先刪它再執行**。
3. 執行前把 `state` 改成 `busy` 並寫入 `busy_since`。
4. 執行，寫結果檔。
5. `finally` 裡把 `state` 寫回 `idle`。

**命令檔在執行前就刪掉。** 看門人如果在匯入做到一半死掉，那個匯入下次啟動會再被撿到再跑一次。
丟掉一個結果只是讓呼叫端等到逾時，重跑一次匯入會動到專案。

**同一個 IDE 不准兩支看門人。** 實例編號是專案名加程序編號，同一個 IDE 裡跑兩支會拿到同一個編號、
搶同一個目錄。啟動時發現 `sys` 上已經有活著的看門人，就當作「再跑一次等於停止」。

**一拍裡面接住一切。** WinForms 的 tick 處理器丟出沒接住的例外會變成 IDE 的執行緒例外對話框，
可能把 IDE 帶下去。

## 6. 為什麼是計時器，不是主迴圈

原本的設計是一個 `while` 迴圈配 `system.delay(50)`。它會讓 IDE 點不動，而且看起來不像壞掉：
視窗照常重繪、Windows 不判定它凍結、送達型訊息照常回應。2026-09-05 用真的滑鼠量出來的結果是
**`system.delay()` 抽送的是重繪、計時器與非輸入訊息，滑鼠鍵盤被過濾掉**。

| 情境 | 腳本開始前 | `system.delay(50)` 迴圈期間 |
|---|---|---|
| 從 Scripts 選單啟動 | File 下拉開得出來 | 每次都開不出來 |
| 用 `--runscript` 啟動 | 未量到基準 | 每次都開不出來 |

所以換啟動方式沒有用。解法是讓腳本結束，把工作掛在 IDE 自己的訊息迴圈上：`Project_watch.py`
建一個 WinForms `Timer`（間隔 250 毫秒），掛上處理器，**立刻返回**。腳本一結束，進度顯示消失、
IDE 完全回到使用者手上。

前提是「腳本返回之後 CODESYS 的 API 物件還能用」。這件事 2012 年官方警告過，所以實測了兩輪，
原廠 SP21（ScriptEngine 4.2.0.0）與 Delta 1.10（4.0.0.0）都過：抓在手上的 `projects.primary.path`、
`get_children()`、`system.write_message`、`system.delay` 在腳本返回後、甚至在使用者又從選單跑了
另一支腳本之後，都還能用，`__main__.projects` 也還是同一個物件。

只在原廠 3.5.21.40 上做過真實點擊測試。Delta 1.10 沒有量輸入，但機制相同，不另外假設它會不一樣。

## 7. 計時器設計的規則

- **狀態放在 `sys` 的屬性上**（`sys._cds_watcher`），不放在腳本模組的全域。腳本結束後模組命名空間
  不保證還在，`sys` 一定在。計時器物件也放在裡面，免得被回收。
- **重入保護。** 匯入、編譯這類命令會抽送訊息，抽送期間計時器會再 tick。tick 一進來先看 busy 旗標。
- **不開執行緒、不 `time.sleep()`、不 `execute_on_primary_thread`**（SPEC D5）。
  tick 本身就在 UI 執行緒上，不需要任何跨執行緒的東西。
- **停止方式有兩種**：CLI 的 `stop`，以及再跑一次 `Project_watch.py`。兩種走同一個收尾：
  停計時器、關狀態視窗、刪登記檔與目錄、清掉 `sys` 上的狀態。
- **心跳照舊在 tick 裡做。** 命令執行中發不出心跳，登記檔的 `busy` 狀態已經處理這件事。
- **狀態視窗用 `Show()` 不用 `ShowDialog()`。** 模態視窗會佔住主執行緒，把 IDE 送回這整個設計
  要避開的狀態。視窗歸 IDE 主視窗所有，不設 TopMost，所以它跟著 IDE 最小化，不會壓在別人的視窗上。

## 8. 真實輸入的驗收怎麼做

儀器是 `tools/probe_click_menu.py`：`SetForegroundWindow` 加 `mouse_event` 對選單列最左邊的 File
做真實點擊，用 `EnumWindows` 數有沒有長出下拉視窗。啟動器是 `tools/probe_watcher_ui.py`，
它建一個臨時專案、設好 `cds-sync-folder`、走 `Project_watch.py` 的啟動路徑然後返回。

流程是：起 IDE 跑啟動器，儀器每 5 秒點一次 File 選單要求每次都開得出下拉，同時從外面跑
`cdsint ping`、`export`、`stop`。`export` 那幾秒點不開是正常的，之後要恢復；`stop` 之後登記檔消失、
選單仍可點。

2026-09-05 的結果：原廠 3.5.21.40 全過。Delta 1.10 的點擊儀器失效，原因是桌面上另一個視窗搶著
在最上層，`SetForegroundWindow` 一直回 False，跟看門人無關——連沒有任何腳本在跑的時候也點不開。
Delta 1.10 那一格後來由使用者手動補上：他在自己的真專案上從 Tools 選單啟動看門人，回報 IDE 確實可操作，
同時外面量到 `status` 往返 57 毫秒。所以計時器設計在 ScriptEngine 4.0.0.0 與 4.2.0.0 兩個大版本上
都有真人資料。

## 9. 這個設計擋不住的事

`cds/ide/silent.py` 有一個模組層級的旗標 `silent.running()`，tick 看到就直接返回。

**它擋不住使用者從 Scripts 選單手動啟動的腳本。** 那條路走 IDE 自己的執行器，根本不經過 `silent.run`，
這個模組看不到它。目前沒有已知的辦法從計時器裡偵測到那種腳本。這個旗標實際擋住的是「另一個呼叫端」：
別處建出來的第二個 `Watcher`，或以後包在外面的 MCP。

## 10. 無人模式的替身 UI

引擎是為人寫的，它會問「Confirm Import?」然後等。看門人改成從命令參數回答，答不出來就大聲拒絕，
不猜（SPEC D7）。要讓這件事成立，有三樣東西要換掉：

| 換掉什麼 | 為什麼 |
|---|---|
| 本體自己命名空間裡的 `system` | 本體讀的就是這個 |
| `__main__.system` | `codesys_utils.resolve_system` 找不到模組自己的 `system` 時會走到 `__main__` |
| `sys.modules["engine.codesys_ui"]` 的 `ask_yes_no`、`ask_yes_no_cancel`、`show_compare_dialog` | 這幾個自己開 WinForms 視窗，完全不經過 `system.ui` |

三件實作上踩過的坑：

- **`NeedsInput` 繼承 `BaseException` 不是 `Exception`。** `entry_build.py` 把 `system.ui.choose`
  整段包在 `except Exception` 裡；如果 `NeedsInput` 是普通例外就會被吃掉，然後引擎退回「編譯 active
  application」，等於使用者沒指定要編哪個、卻默默編了另一個。跟 `KeyboardInterrupt` 不能被應用層
  錯誤處理吃掉是同一個道理。
- **`exec` 要餵位元組不能餵 unicode。** 本體都有 `# -*- coding: utf-8 -*-`，Python 2 的 `compile()`
  碰到帶編碼宣告的 unicode 原始碼會直接丟 SyntaxError，也不吃 BOM。
- **本體用 exec 不用 import。** 替身 `system` 必須在本體的模組層級程式碼跑起來之前就在它的命名空間裡。
  選單那條路沒有這個需求，走的是 `engine/entry.py`。

成功失敗現在是從訊息等級推的：替身 UI 收到 `warning` 或 `error` 就算失敗，整輪跑完連一則 `info`
都沒有也算失敗。這是過渡辦法，SPEC D11 要換成讀回傳值。在那之前的紀律是：`warning` 與 `error`
只准在中止的地方呼叫，純資訊用 `info`。
