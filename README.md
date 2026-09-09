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

Assets are registered in the `assets` table and auto-seeded from the code on startup. Full catalog also available via `GET /finance/assets`.

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

The list above is the catalogue available today. More assets (stocks, ETFs, FX pairs, indexes, metals, crypto) can be added on demand via `POST /finance/admin/assets` — the endpoint validates the symbol against Yahoo Finance live, so the catalogue is not fixed to this list.

## Public endpoints

| Method | Endpoint                            | Description                                                       |
| ------ | ----------------------------------- | ----------------------------------------------------------------- |
| GET    | `/finance/fx/rates`                 | Latest price for all FX pairs                                     |
| GET    | `/finance/fx/rates/{pair}`          | Latest price for one pair (e.g. `EURUSD`)                         |
| GET    | `/finance/fx/history/{pair}`        | 5-year daily history for one pair                                 |
| GET    | `/finance/indexes`                  | Latest value for all indexes                                      |
| GET    | `/finance/indexes/{symbol}`         | Latest value for one index (e.g. `^GSPC`, `^N225`)                |
| GET    | `/finance/indexes/{symbol}/history` | 5-year daily history for one index                                |
| GET    | `/finance/metals`                   | Latest price for all metals                                       |
| GET    | `/finance/metals/{metal}`           | Latest price for one metal (`gold`, `silver`, `copper`, …)        |
| GET    | `/finance/metals/{metal}/history`   | 5-year daily history for one metal                                |
| GET    | `/finance/stocks`                   | Latest price for all stocks                                       |
| GET    | `/finance/stocks/{symbol}`          | Latest price for one stock (e.g. `NVDA`)                          |
| GET    | `/finance/stocks/{symbol}/history`  | 5-year daily history for one stock                                |
| GET    | `/finance/etfs`                     | Latest price for all ETFs                                         |
| GET    | `/finance/etfs/{symbol}`            | Latest price for one ETF (e.g. `VOO`, `QQQ`)                      |
| GET    | `/finance/etfs/{symbol}/history`    | 5-year daily history for one ETF                                  |
| GET    | `/finance/crypto`                   | Latest price for all cryptocurrencies                             |
| GET    | `/finance/crypto/{symbol}`          | Latest price for one crypto (e.g. `BTC-USD`)                      |
| GET    | `/finance/crypto/{symbol}/history`  | 5-year daily history for one crypto                               |
| GET    | `/finance/history/all`              | Full dump, every stored bar, all assets (default cap 50,000 rows) |
| GET    | `/finance/history/range?from&to`    | Every bar between two inclusive dates, all assets (`YYYY-MM-DD`)  |
| GET    | `/finance/symbol/{symbol}`          | Latest bar for any stored symbol (incl. ad-hoc additions)         |
| GET    | `/finance/symbol/{symbol}/history`  | Full history for any stored symbol                                |
| GET    | `/finance/assets`                   | Full catalogue of tracked assets, grouped by type                 |
| GET    | `/finance/last-updated`             | Most recent stored date per asset                                 |
| GET    | `/finance/cache/status`             | In-memory cache stats                                             |
| GET    | `/finance/cache/all`                | All data straight from the cache (no DB hit)                      |
| GET    | `/finance/cache/stocks`             | All stock histories from the cache (no DB hit)                    |
| GET    | `/finance/cache/indexes`            | All index histories from the cache (no DB hit)                    |
| GET    | `/finance/cache/metals`             | All metal histories from the cache (no DB hit)                    |
| GET    | `/finance/cache/etfs`               | All ETF histories from the cache (no DB hit)                      |
| GET    | `/finance/cache/cryptos`            | All crypto histories from the cache (no DB hit)                   |
| GET    | `/finance/cache/{symbol}`           | One symbol's history from the cache                               |

## Admin endpoints (require `X-Admin-Key` when `ADMIN_KEY` is set)

| Method | Endpoint                                  | Description                                                                                |
| ------ | ----------------------------------------- | ------------------------------------------------------------------------------------------ |
| GET    | `/finance/admin/assets`                   | List tracked assets from the `assets` table                                                |
| GET    | `/finance/admin/assets/check?symbol=`     | Verify a symbol exists on Yahoo Finance (combines `yf.Ticker` + `yf.download`)             |
| POST   | `/finance/admin/assets`                   | Add an asset to the tracked catalogue (name/type auto-inferred from Yahoo)                 |
| POST   | `/finance/admin/assets/{symbol}/backfill` | **Fast** 5-year backfill for one tracked asset                                             |
| GET    | `/finance/admin/backfill-symbol`          | **Fast** 5-year backfill for one arbitrary Yahoo symbol                                    |
| POST   | `/finance/admin/backfill-missing`         | **Slow & safe** backfill of assets missing ~5y history (gentle pacing, no rate-limit risk) |
| POST   | `/finance/admin/backfill`                 | **Medium** backfill of ALL assets (throttled ~2s between symbols)                          |
| POST   | `/finance/admin/ingest-daily`             | Run the daily fetch now                                                                    |
| GET    | `/finance/admin/cache/details`            | Detailed cache report (per-symbol coverage, rows, estimated memory)                        |
| GET    | `/finance/logs`                           | Recent ingestion logs (last 7 days)                                                        |

Admin endpoints require the `X-Admin-Key` header when `ADMIN_KEY` is set in the environment.

The scheduler runs the daily fetch automatically on weekdays at:

| Timezone           | Local time (weekdays)                             |
| ------------------ | ------------------------------------------------- |
| UTC                | 23:00                                             |
| London (GMT/BST)   | 23:00 (winter) / 00:00 next day (summer)          |
| Zürich (CET/CEST)  | 00:00 next day (winter) / 01:00 next day (summer) |
| New York (EST/EDT) | 18:00 (winter) / 19:00 (summer)                   |
| Tokyo (JST)        | 08:00 next day (no DST)                           |

## In-memory cache

All stored `daily_prices` rows are loaded into an in-memory cache at startup and served by the `/finance/cache/*` endpoints **without any database round-trip** — ideal for read-heavy public pages.

- **Memory footprint:** ~116 assets × ~1,300 bars ≈ 150k rows ≈ **~70 MB** (grows ~52 KB/day from the daily fetch — negligible).
- **Lifecycle:** loaded once at startup → refreshed automatically after each scheduled ingestion (Mon-Fri 23:00 UTC) → fully **invalidated and rebuilt** whenever a manual admin fetch (`ingest-daily`, `backfill`, `backfill-symbol`) writes new data, so stale data is never served during a fetch cycle.
- **Monitoring:** `GET /finance/cache/status` (public) gives quick stats; `GET /finance/admin/cache/details` (admin) gives per-symbol coverage and an estimated memory footprint — handy to confirm the cache rebuilt correctly after a deploy.

> Note: the cache is in-process, so every deploy starts fresh and rebuilds from the database in a few seconds.

## Compression

The API applies **gzip compression** (via `GZipMiddleware`, level 5) to every response ≥ 1 KB for clients that advertise `Accept-Encoding: gzip` (all browsers and `curl`).

Because JSON is highly repetitive, this reduces payload sizes by roughly **75-80%**:

| Endpoint                  | Uncompressed | Gzipped (approx.) |
| ------------------------- | ------------ | ----------------- |
| `/finance/cache/all`      | ~15.3 MB     | ~3-3.5 MB         |
| `/finance/cache/stocks`   | ~9.6 MB      | ~2 MB             |
| `/finance/cache/{symbol}` | ~130 KB      | ~30 KB            |

This is especially relevant on Render's free tier, which caps outbound HTTP bandwidth at **5 GB/month**, per-symbol or per-asset-class calls use ~100× less bandwidth than the full dump.

## License

This project is licensed under the MIT License, see the [LICENSE](LICENSE) file for details.

## Author

Made with 💚 by João Barreto.

- **Email:** barretobit@gmail.com
- **LinkedIn:** [linkedin.com/in/barretobit](linkedin.com/in/barretobit)
- **GitHub:** [github.com/barretobit](github.com/barretobit)
