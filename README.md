# Randata Finance API

[![Live API](https://img.shields.io/badge/Open_API-Randata-brightgreen.svg)](https://randata.onrender.com/docs)

[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-teal.svg)](https://fastapi.tiangolo.com/)
[![Uvicorn](https://img.shields.io/badge/Uvicorn-ASGI-499848.svg)](https://www.uvicorn.org/)
[![MySQL](https://img.shields.io/badge/MySQL-8.0+-4479A1.svg)](https://www.mysql.com/)
[![Yahoo Finance](https://img.shields.io/badge/yfinance-7+-purple.svg)](https://github.com/ranaroussi/yfinance)

A FastAPI Service that tracks daily financial market data for Stocks, Indexes, ETFs, Precious Metal, FX Pairs and Cryptos, sourced from Yahoo Finance and stored in a Database. Includes Swiss favorites like the SMI. 🇨🇭

## Tracked Assets (+100)

Assets are registered in the `assets` table in the database — the single source of truth served by the API. Full catalog also available via `GET /finance/assets`.

<details>
<summary><strong>FX pairs (+10)</strong> — EUR/USD, CHF/USD, GBP/USD, JPY/USD, CNY/USD, NOK/USD, DKK/USD, HKD/USD, SEK/USD, NZD/USD, AUD/USD, CAD/USD</summary>

- EUR/USD, CHF/USD, GBP/USD, JPY/USD, CNY/USD
- NOK/USD, DKK/USD, HKD/USD, SEK/USD, NZD/USD
- AUD/USD, CAD/USD
</details>

<details>
<summary><strong>Indexes (10)</strong> — S&P 500, SMI, NASDAQ Composite, Dow Jones, DAX, Euro Stoxx 50, FTSE 100, CAC 40, Nikkei 225, Hang Seng</summary>

- S&P 500 (US) — `^GSPC`
- SMI (CH) — `^SSMI`
- NASDAQ Composite (US) — `^IXIC`
- Dow Jones (US) — `^DJI`
- DAX (DE) — `^GDAXI`
- Euro Stoxx 50 (EU) — `^STOXX50E`
- FTSE 100 (UK) — `^FTSE`
- CAC 40 (FR) — `^FCHI`
- Nikkei 225 (JP) — `^N225`
- Hang Seng (HK) — `^HSI`
</details>

<details>
<summary><strong>Precious metals (5)</strong> — Gold, Silver, Copper, Platinum, Palladium</summary>

- Gold (XAU) — `GC=F`
- Silver (XAG) — `SI=F`
- Copper (XCU) — `HG=F`
- Platinum (XPT) — `PL=F`
- Palladium (XPD) — `PA=F`
</details>

<details>
<summary><strong>Stocks (+70)</strong> — 50 US large-caps, 10 Switzerland, 10 Germany, 4 Japan</summary>

- **US (50):** NVDA, AAPL, GOOG, MSFT, AMZN, AVGO, META, TSLA, MU, BRK-B, LLY, JPM, AMD, WMT, V, XOM, JNJ, INTC, MA, ORCL, ABBV, BAC, CSCO, CVX, PLTR, COST, LRCX, KO, CAT, AMAT, MRK, UNH, DELL, MS, GE, PG, NFLX, HD, GS, PM, PANW, WFC, RTX, SNDK, GEV, ANET, KLAC, TXN, C, IBM
- **Switzerland (10, SIX):** RO.SW, NOVN.SW, NESN.SW, UBSG.SW, ABBN.SW, CFR.SW, ZURN.SW, SREN.SW, LONN.SW, HOLN.SW
- **Germany (10, Xetra):** SIE.DE, SAP.DE, ENR.DE, ALV.DE, DTE.DE, AIR.DE, MUV2.DE, RHM.DE, DBK.DE, MBG.DE
- **Japan (4, TSE):** 7203.T, 8306.T, 9984.T, 6501.T
</details>

<details>
<summary><strong>ETFs (10)</strong> — VOO, IVV, SPY, VTI, VT, QQQ, VEA, VXUS, VWO, BND</summary>

- VOO — Vanguard S&P 500 🇺🇸
- IVV — iShares Core S&P 500 🇺🇸
- SPY — SPDR S&P 500 🇺🇸
- VTI — Vanguard Total US Stock Market 🇺🇸
- VT — Vanguard Total World Stock
- QQQ — Invesco Nasdaq-100 🇺🇸
- VEA — Vanguard FTSE Developed Markets
- VXUS — Vanguard Total International Stock
- VWO — Vanguard FTSE Emerging Markets
- BND — Vanguard Total US Bond Market 🇺🇸
</details>

<details>
<summary><strong>Crypto (5)</strong> — Bitcoin, Ethereum, Tether, BNB, Solana</summary>

- Bitcoin — `BTC-USD`
- Ethereum — `ETH-USD`
- Tether — `USDT-USD`
- BNB — `BNB-USD`
- Solana — `SOL-USD`
</details>

The list above is the catalogue available today. More assets (stocks, ETFs, FX pairs, indexes, metals, crypto) can be added on demand via `POST /finance/admin/assets` — the endpoint validates the symbol against Yahoo Finance live, so the catalogue is not fixed to this list. For fully automated onboarding, `POST /finance/admin/assets/onboard` verifies the symbol, adds the asset, backfills the configured history window, and refreshes the cache in a single call.

## Public endpoints

| Method | Endpoint                            | Description                                                       |
| ------ | ----------------------------------- | ----------------------------------------------------------------- |
| GET    | `/finance/fx/rates`                 | Latest price for all FX pairs                                     |
| GET    | `/finance/fx/rates/{pair}`          | Latest price for one pair (e.g. `EURUSD`)                         |
| GET    | `/finance/fx/rates/{pair}/history`  | Full-window daily history for one pair                            |
| GET    | `/finance/fx/history/{pair}`        | Same as above (deprecated path, still served)                     |
| GET    | `/finance/indexes`                  | Latest value for all indexes                                      |
| GET    | `/finance/indexes/{symbol}`         | Latest value for one index (e.g. `^GSPC`, `^N225`)                |
| GET    | `/finance/indexes/{symbol}/history` | Full-window daily history for one index                                |
| GET    | `/finance/metals`                   | Latest price for all metals                                       |
| GET    | `/finance/metals/{metal}`           | Latest price for one metal (`gold`, `silver`, `copper`, …)        |
| GET    | `/finance/metals/{metal}/history`   | Full-window daily history for one metal                                |
| GET    | `/finance/stocks`                   | Latest price for all stocks                                       |
| GET    | `/finance/stocks/{symbol}`          | Latest price for one stock (e.g. `NVDA`)                          |
| GET    | `/finance/stocks/{symbol}/history`  | Full-window daily history for one stock                                |
| GET    | `/finance/etfs`                     | Latest price for all ETFs                                         |
| GET    | `/finance/etfs/{symbol}`            | Latest price for one ETF (e.g. `VOO`, `QQQ`)                      |
| GET    | `/finance/etfs/{symbol}/history`    | Full-window daily history for one ETF                                  |
| GET    | `/finance/crypto`                   | Latest price for all cryptocurrencies                             |
| GET    | `/finance/crypto/{symbol}`          | Latest price for one crypto (e.g. `BTC-USD`)                      |
| GET    | `/finance/crypto/{symbol}/history`  | Full-window daily history for one crypto                               |
| GET    | `/finance/history/all`              | Full dump, every stored bar, all assets (default cap 50,000 rows, `limit` up to 500,000; streamed, so `count`/`from`/`to` follow `data`) |
| GET    | `/finance/history/range?from&to`    | Up to 50,000 bars between two dates, all assets (HTTP 413 if exceeded; served from cache when `from` is within the cache window, else DB) |
| GET    | `/finance/history/year/{year}`      | One calendar year, all assets, per symbol as date-ascending columns (`date`, `open`, `high`, `low`, `close`, `volume`); prepared in memory after every cache load |
| GET    | `/finance/symbol/{symbol}`          | Latest bar for any stored symbol (incl. ad-hoc additions)         |
| GET    | `/finance/symbol/{symbol}/history`  | Full history for any stored symbol                                |
| GET    | `/finance/assets`                   | Full catalogue of tracked assets, grouped by type                 |
| GET    | `/finance/last-updated`             | Most recent stored date per asset                                 |
| GET    | `/finance/logs/all`                 | Every stored ingestion log row (last 90 days), newest first       |
| GET    | `/finance/cache/status`             | In-memory cache stats                                             |
| GET    | `/finance/cache/all`                | All data straight from the cache (no DB hit)                      |
| GET    | `/finance/cache/stocks`             | All stock histories from the cache (no DB hit)                    |
| GET    | `/finance/cache/indexes`            | All index histories from the cache (no DB hit)                    |
| GET    | `/finance/cache/metals`             | All metal histories from the cache (no DB hit)                    |
| GET    | `/finance/cache/etfs`               | All ETF histories from the cache (no DB hit)                      |
| GET    | `/finance/cache/cryptos`            | All crypto histories from the cache (no DB hit)                   |
| GET    | `/finance/cache/{symbol}`           | One symbol's history from the cache                               |

For an existing database, run `sql/migrate_finance_schema.sql` once to add the `assets.inception_date` column and the daily-price date index. New databases get both from the create-table scripts.

## Admin endpoints (require the `X-Admin-Key` header)

| Method | Endpoint                                  | Description                                                                                |
| ------ | ----------------------------------------- | ------------------------------------------------------------------------------------------ |
| GET    | `/finance/admin/assets`                   | List tracked assets from the `assets` table                                                |
| GET    | `/finance/admin/assets/check?symbol=`     | Verify a symbol exists on Yahoo Finance (combines `yf.Ticker` + `yf.download`)             |
| POST   | `/finance/admin/assets`                   | Add an asset to the tracked catalogue (name/type auto-inferred from Yahoo)                 |
| POST   | `/finance/admin/assets/onboard`           | One-call onboarding: verify symbol → add asset → full backfill → refresh cache (~1 min)    |
| POST   | `/finance/admin/assets/{symbol}/backfill` | **Fast** full-window backfill for one tracked asset                                        |
| POST   | `/finance/admin/backfill-symbol?symbol=`  | **Fast** full-window backfill for one arbitrary Yahoo symbol (`GET` still works, deprecated) |
| POST   | `/finance/admin/assets/backfill-inception-dates` | **Slow** capture missing `inception_date`s so young assets are not re-fetched       |
| POST   | `/finance/admin/backfill-missing`         | **Slow & safe** backfill of assets missing their expected history (gentle pacing)          |
| POST   | `/finance/admin/backfill`                 | **Medium** backfill of ALL assets (throttled ~2s between symbols)                          |
| POST   | `/finance/admin/ingest-daily`             | Run the daily fetch now                                                                    |
| POST   | `/finance/admin/cache/refresh`             | Clear and rebuild the cache from the configured window in the database                     |
| GET    | `/finance/admin/cache/details`            | Detailed cache report (per-symbol coverage, rows, estimated memory)                        |
| GET    | `/finance/logs`                           | Recent ingestion logs (last 7 days)                                                        |

Admin endpoints (and `/finance/logs`) require the `X-Admin-Key` header to match the `ADMIN_KEY` environment variable. When `ADMIN_KEY` is not set, they are disabled and answer HTTP 503.

Only one bulk job (nightly ingestion, `backfill`, `backfill-missing`, `backfill-inception-dates`) runs at a time. Starting another while one is running answers HTTP 409; the scheduled run is skipped and logged.

The scheduler runs the daily incremental ingestion automatically every day at:

| Timezone           | Local time                                        |
| ------------------ | ------------------------------------------------- |
| UTC                | 23:00 daily                                       |
| London (GMT/BST)   | 23:00 (winter) / 00:00 next day (summer)          |
| Zürich (CET/CEST)  | 00:00 next day (winter) / 01:00 next day (summer) |
| New York (EST/EDT) | 18:00 (winter) / 19:00 (summer)                   |
| Tokyo (JST)        | 08:00 next day (no DST)                           |

Each nightly run fills assets missing their expected history, scans stored dates for long gaps, repairs detected gaps using Yahoo Finance's returned trading dates, and fetches an overlapping recent window to capture late bars and corrections. `INGEST_OVERLAP_DAYS` controls the recent overlap (default 7). The gap scan tolerates up to `INGEST_MARKET_GAP_DAYS` calendar days (default 14) for market assets and treats any missing day as a gap for crypto, which trades daily. A deterministic rotation gives each tracked asset a full configured-history audit about once every `HISTORY_AUDIT_CYCLE_DAYS` (default 30 days), spreading provider requests across nights. The final nightly check scans all stored bars for malformed OHLC values and abnormal close-to-close moves. It re-fetches suspicious dates with surrounding Yahoo history and replaces stored data only when the returned bar passes the same checks; unresolved cases remain unchanged and are logged for review. Finally, `api_logs` rows older than 90 days are deleted.

During ingestion, invalid OHLC bars are skipped. A bar is also skipped as a **spike** when its close jumps abnormally away from the previous close *and* the next close comes back at least halfway with another abnormal move. Real moves (earnings gaps, crashes, rallies) stay at their new level and are kept. A move is abnormal above the absolute `PRICE_HARD_MAX_RETURN` limit (default 80%), or, after at least `PRICE_OUTLIER_MIN_SAMPLES` recent moves (default 20), beyond the larger of `PRICE_OUTLIER_SIGMA` robust standard deviations (default 8) or the minimum return floor (default 2%). The newest bar has no next bar yet, so it is only held back above the hard limit; the overlap window re-checks it the next night, and if it then turns out to be a spike it is deleted from the database. When filling a gap, the stored bar right after the gap serves as that next bar. Skipped and deleted bars are logged.

Prices are split- and dividend-adjusted by Yahoo. When the overlap window shows that Yahoo rescaled closes the database already holds (a split or dividend), the nightly run re-fetches that asset's full history window instead of appending to the old scale.

## In-memory cache

The rolling `CACHE_HISTORY_YEARS` window of `daily_prices` rows is loaded into an in-memory cache at startup and served by the `/finance/cache/*` endpoints **without any database round-trip** — ideal for read-heavy public pages. This is intentionally smaller than `HISTORY_YEARS`: the database stores the full history (see `/finance/*/history`), while the RAM cache is capped to fit the host's memory budget.

- **Memory footprint:** ~**470 bytes per row** (the cache holds Python dicts with float prices) ≈ 22 MB for ~47k rows (1y), 110 MB (5y) and ~215 MB (10y). The default is `CACHE_HISTORY_YEARS=1` so a 512 Mi instance stays well within budget; raise it only if the deployment has more RAM.
- **Consumer pattern:** a client's first load pulls the full 10-year history one calendar year at a time via `/finance/history/year/{year}` (requests can run in parallel). After every cache load, a background thread prepares those year documents (gzip, ~1 MB each) from the database, so these requests do not wait on it. Subsequent incremental loads pass a recent `from` date to `/finance/history/range`, which is then served from this cache with no database round-trip.
- **Lifecycle:** loaded once at startup → reloaded automatically after each scheduled ingestion (daily 23:00 UTC) → reloaded whenever a manual admin fetch (`ingest-daily`, `backfill`, `backfill-symbol`) writes new data or `POST /finance/admin/cache/refresh` is called. A reload builds the new data first and swaps it in one step, so the cache keeps serving the previous data while a fetch runs and is never empty or half-built.
- **Monitoring:** `GET /finance/cache/status` (public) gives quick stats; `GET /finance/admin/cache/details` (admin) gives per-symbol coverage and an estimated memory footprint — handy to confirm the cache rebuilt correctly after a deploy.

> Note: the cache is in-process, so every deploy starts fresh and rebuilds from the database in a few seconds.

## Compression

The API applies **gzip compression** (via `GZipMiddleware`, level 5) to every response ≥ 4 KB for clients that advertise `Accept-Encoding: gzip` (all browsers and `curl`).

Because JSON is highly repetitive, this reduces payload sizes by roughly **75-80%**:

| Endpoint                  | Uncompressed | Gzipped (approx.) |
| ------------------------- | ------------ | ----------------- |
| `/finance/cache/all`      | ~15.3 MB     | ~3-3.5 MB         |
| `/finance/cache/stocks`   | ~9.6 MB      | ~2 MB             |
| `/finance/cache/{symbol}` | ~130 KB      | ~30 KB            |

This is especially relevant on Render's free tier, which caps outbound HTTP bandwidth at **5 GB/month**, per-symbol or per-asset-class calls use ~100× less bandwidth than the full dump.

## Configuration

Settings are environment variables (a local `.env` file is read too); see [app/config.py](app/config.py) for every one and its default. The Yahoo retry settings were renamed: `YAHOO_MAX_RETRIES`, `YAHOO_RETRY_BASE_SECONDS` and `SLOW_YAHOO_RETRY_BASE_SECONDS`. The old `YF_*` names are still read when the new ones are not set.

Yahoo errors (network failures, unknown symbols, failed price adjustment) are raised and logged to `api_logs` as `ERROR`. Only "Yahoo has no prices for this range" counts as an empty result.

## Code layout

| Module | Responsibility |
| ------ | -------------- |
| `app/main.py` | FastAPI app, middleware, startup (catalogue + cache load) and the nightly scheduler |
| `app/config.py` | Environment settings |
| `app/db.py` | Database engine and sessions |
| `app/asset_repository.py` | SQL for the `assets` table |
| `app/price_repository.py` | SQL for the `daily_prices` table |
| `app/yahoo.py` | Yahoo Finance client: downloads with retries, symbol checks, inception dates |
| `app/price_validation.py` | Bar checks: OHLC structure and isolated price spikes |
| `app/ingestion.py` | Jobs: backfills, nightly update, history audit and repair |
| `app/cache.py`, `app/catalog.py` | In-memory price cache and asset catalogue |
| `app/logging_config.py` | Console logging and the `api_logs` table |
| `app/routers/finance/` | Endpoints: `market_endpoints`, `history_endpoints`, `cache_endpoints`, `admin_endpoints`; OpenAPI examples in `examples.py` |

## Tests

The tests run offline: no database, no Yahoo Finance calls, no scheduler.

```bash
venv/Scripts/python.exe -m pip install -r requirements-dev.txt
venv/Scripts/python.exe -m pytest
```

## License

This project is licensed under the MIT License, see the [LICENSE](LICENSE) file for details.

## Author

Made with 💚 by João Barreto.

- **LinkedIn:** [linkedin.com/in/barretobit](linkedin.com/in/barretobit)
- **GitHub:** [github.com/barretobit](github.com/barretobit)
