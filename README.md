# 客脈 AI 影片工坊

客脈品牌的免費文案轉影片網站，採用 MoneyPrinterTurbo 語音與字幕核心，搭配 FFmpeg 直接合成影片。此版本由完整文案與使用者圖片製作短片；不提供 AI 寫稿、庫存影片搜尋、文字生成實拍畫面、社群自動發布或管理員設定入口。

## 功能與限制

- 10–220 字文案、台灣中文三種配音、0.9／1／1.1 倍語速。
- 最多 5 張 JPG／PNG／WebP；每張 4 MB、1,200 萬像素、單邊 8,000 px。未上傳時採原創漸層背景。
- MP4 H.264/AAC、720p、24 fps、最長 60 秒；9:16／16:9／1:1；另外下載 SRT。
- 單一背景消費者、最多 4 個處理／排隊工作；每個網路來源 24 小時 3 支、全站 30 支。失敗工作不計完成配額。
- 上傳和成品完成後暫存 30 分鐘；Render 免費主機休眠或重新啟動會提早清除，配額資料也會重置。這是免費體驗容量，不是永久雲端儲存。
- 配音文字交由 Microsoft 線上 TTS 處理，未使用付費 API 金鑰；服務可用性不受本網站控制。
- 任務採 192-bit 隨機存取連結，無作品列表。持有連結者可讀取；請勿傳送機密／敏感素材。

## 執行

本機 Python 3.12、FFmpeg；Render 已部署 Python 3.11.16。安裝 `requirements.txt` 後：

```sh
uvicorn server:app --host 127.0.0.1 --port 4181 --workers 1 --no-access-log
python check.py
node check-worker.mjs
```

`check.py` 另需 `httpx`（開發測試依賴）。瀏覽器完整驗收與影片檢查位於工作區 `work/video-studio/`；它們不是公開網站素材。

## 部署

前端 Cloudflare Pages 部署 `static/`，後端 Render Free 使用原生 Python（平台提供 FFmpeg）。服務網址 `https://kemai-ai-video.onrender.com`，主站 `https://kemai-ai-video.pages.dev/`。建立後端需以下環境設定：

- `KEMAI_PROXY_SECRET`：隨機金鑰，Render 與 Pages 使用相同值，不能放進程式庫。
- `PUBLIC_ORIGIN=https://kemai-ai-video.pages.dev`
- `KEMAI_RELEASE_URL`、`KEMAI_RELEASE_SHA256`：取自 `static/releases/release.json`。
- Pages `VIDEO_BACKEND`：本次 Render 服務的 HTTPS origin。

`python build_release.py` 只打包明列的程式、公開靜態檔與 OFL 字型；不含 runtime、使用者資料或金鑰。先部署 Pages，再核對公開檔案 SHA256。Render 的建置命令下載及驗證 manifest 所列的 bootstrap，帶 `--build` 執行；它會再驗證版本包並安裝必要依賴。啟動命令：

```sh
cd kemai-release && OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uvicorn server:app --host 0.0.0.0 --port $PORT --workers 1 --no-access-log
```

目前 Render 的 Git 來源使用 MoneyPrinterTurbo 官方庫，只用於取得 Python 執行環境；實際服務程式由校驗後的客脈版本包決定。客脈 GitHub 庫的匿名訪問目前回傳 404，尚不能直接用於 Render 公開 Git 部署。保留 Dockerfile 供具備容器建置環境時使用。

只有 `/api/*` 會呼叫後端，靜態頁面不受 Render 休眠影響。API 不快取、不索引，原始 MoneyPrinterTurbo API 不對外開放。免費主機的帳戶與超額政策須以實際部署當日帳戶設定為準；不得開啟付費方案或自動升級。

## 來源

- MoneyPrinterTurbo commit `5ac2b5d979adba31f6489ba50f94f4771427549f`，MIT；授權與改動記錄在 `vendor/moneyprinter/`。
- 原專案字型與素材未打包。使用 Google Noto Sans TC（SIL OFL），將字重固定為 500 以確保影片可讀；字型與授權在 `assets/`。
- 網站介面、佇列、限制、原創背景與部署整合由客脈版本新增。

目前部署與驗收狀態見 [LAUNCH.md](LAUNCH.md)；Google 索引狀態與網站上線分開紀錄。
