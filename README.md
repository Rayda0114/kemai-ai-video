# 客脈 AI 影片工坊

客脈品牌的免費文案轉影片網站，採用 MoneyPrinterTurbo 語音與字幕核心，搭配 FFmpeg 直接合成影片。輸入主題即可自動寫稿、安排分鏡、搜尋 Pexels 素材，無合適影片時補查 Pixabay；可先預覽、修改分鏡與換素材，確認後再剪輯。也可保留完整文案或使用自有圖片。素材來自既有圖庫，並非文字生成全新實拍畫面。

## 功能與限制

- 2–220 字主題自動寫稿；或保留 10–220 字文案、台灣中文三種配音、0.9／1／1.1 倍語速。
- 自動素材最多 3 段，每段最多 3 個候選項目，切換時重用同次搜尋結果。可修改標題、各段旁白，或逐段上傳圖片；確認後才開始 TTS、字幕與剪輯，保留指定素材與編輯後的文字，不重新呼叫 AI 或暗中替換素材。提供實際分鏡編號、素材來源與上傳圖片標示。
- `POST /api/jobs` 帶 `preview=1` 先建立分鏡；狀態 `ready` 保留 30 分鐘。`POST /api/jobs/{id}/confirm` 只接受候選索引與受限圖片，確認同一工作不重複扣額度；重送確認不會建立第二支影片。舊 API 未帶 preview 的請求維持直接出片及素材備援行為。
- 自有圖片模式最多 5 張 JPG／PNG／WebP；每張 4 MB、1,200 萬像素、單邊 8,000 px。未上傳時採原創漸層背景。
- 內建 3 種合成純音樂，可試聽與調整 0–40% 配樂音量；自動循環、淡入淡出，旁白出現時壓低配樂。預設溫暖日常／25%，API 舊請求省略配樂則保持純旁白。
- MP4 H.264/AAC、720p、24 fps、最長 60 秒；9:16／16:9／1:1；另外下載 SRT。
- 單一背景消費者、最多 4 個處理／排隊工作；每個網路來源 24 小時 3 次、全站 30 次；安排分鏡即計次，確認同一份分鏡不重複計次；已接受的失敗工作也計次，避免反覆失敗耗盡第三方免費額度。
- 待確認分鏡保留 30 分鐘，上傳和成品完成後另暫存 30 分鐘；Render 免費主機休眠或重新啟動會提早清除，配額資料也會重置。這是免費體驗容量，不是永久雲端儲存。
- 文案分析由 Cloudflare Workers AI 提供，搜尋字詞傳至 Pexels，必要時傳至 Pixabay。2026-09-15 帳戶 Workers 方案頁確認目前為 Free，10,000 neurons／日，用完停止，未升級付費。
- 配音文字交由 Microsoft 線上 TTS 處理，未使用付費 API 金鑰；服務可用性不受本網站控制。
- 任務採 192-bit 隨機存取連結，無作品列表。持有連結者可讀取；請勿傳送機密／敏感素材。

## 執行

本機 Python 3.12、FFmpeg；Render 已部署 Python 3.11.16。安裝 `requirements.txt` 後：

```sh
uvicorn server:app --host 127.0.0.1 --port 4181 --workers 1 --no-access-log
python check.py
python check-story.py
python check_music.py
node check-worker.mjs
node check-ui.mjs
```

`check.py` 另需 `httpx`（開發測試依賴）。瀏覽器完整驗收與影片檢查位於工作區 `work/video-studio/`；它們不是公開網站素材。

## 部署

前端 Cloudflare Pages 部署 `static/`，後端 Render Free 使用原生 Python（平台提供 FFmpeg）。服務網址 `https://kemai-ai-video.onrender.com`，主站 `https://kemai-ai-video.pages.dev/`。建立後端需以下環境設定：

- `KEMAI_PROXY_SECRET`：隨機金鑰，Render 與 Pages 使用相同值，不能放進程式庫。
- `PUBLIC_ORIGIN=https://kemai-ai-video.pages.dev`
- `KEMAI_RELEASE_URL`、`KEMAI_RELEASE_SHA256`：取自 `static/releases/release.json`。
- Pages `VIDEO_BACKEND`：本次 Render 服務的 HTTPS origin。
- Pages `PEXELS_API_KEY`：Cloudflare 加密設定中的既有素材庫金鑰；不放入前端、版本包或 Render。
- Pages `PIXABAY_API_KEY`：可選的第二素材庫金鑰，存入 Cloudflare 加密設定後才啟用影片補找。僅送往 Pixabay API，不進入快取鍵、瀏覽器、Git 或 Render。
- Pages `AI`：Wrangler 的 Workers AI binding。`/api/internal/plan` 在一般代理前驗證共用服務金鑰，只由已接受的後端工作呼叫。
- Pexels 每段查 1 次影片、1 次照片，無合適影片時再查 1 次 Pixabay 影片，最多 9 次／工作，成功搜尋快取 24 小時；不重試 429。單一素材庫出錯仍可用另一來源或照片完成。下載只接受官方 HTTPS CDN，拒絕重新導向，影片上限 12 MB／60 秒／150 萬像素，圖片 4 MB。

`python build_release.py` 只打包明列的程式、公開靜態檔、3 首配樂與 OFL 字型；不含 runtime、使用者資料或金鑰。先部署 Pages，再核對公開檔案 SHA256。Render 的建置命令下載及驗證 manifest 所列的 bootstrap，帶 `--build` 執行；它會再驗證版本包並安裝必要依賴。啟動命令：

```sh
cd kemai-release && OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uvicorn server:app --host 0.0.0.0 --port $PORT --workers 1 --no-access-log
```

目前 Render 的 Git 來源使用 MoneyPrinterTurbo 官方庫，只用於取得 Python 執行環境；實際服務程式由校驗後的客脈版本包決定。客脈 GitHub 庫的匿名訪問目前回傳 404，尚不能直接用於 Render 公開 Git 部署。保留 Dockerfile 供具備容器建置環境時使用。

只有 `/api/*` 會呼叫後端，靜態頁面不受 Render 休眠影響。API 不快取、不索引，原始 MoneyPrinterTurbo API 不對外開放。免費主機的帳戶與超額政策須以實際部署當日帳戶設定為準；不得開啟付費方案或自動升級。

## 來源

- MoneyPrinterTurbo commit `5ac2b5d979adba31f6489ba50f94f4771427549f`，MIT；授權與改動記錄在 `vendor/moneyprinter/`。
- 原專案字型與素材未打包。使用 Google Noto Sans TC（SIL OFL），將字重固定為 500 以確保影片可讀；字型與授權在 `assets/`。
- 配樂以 `make_music.py` 和既有 NumPy／FFmpeg 合成，未收錄外部歌曲或錄音；可用現有環境重建 `static/music/*.mp3`，不需新的 API 或付費服務。
- 網站介面、佇列、限制、原創背景與部署整合由客脈版本新增。

目前部署與驗收狀態見 [LAUNCH.md](LAUNCH.md)；Google 索引狀態與網站上線分開紀錄。
