# Randata Finance API

[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A FastAPI Service that tracks daily financial market data — FX pairs, indexes, and precious metals — sourced from Yahoo Finance and stored in a MySQL database.

**Live API:** <https://randata.onrender.com> — interactive docs at <https://randata.onrender.com/docs>

> Note: the live deployment currently returns `503`, so the code on Render must be re-deployed to serve the new finance API.

## Tracked Assets (24)

- **FX pairs (10):** EUR/USD, GBP/USD, JPY/USD, CHF/USD, AUD/USD, CAD/USD, CNY/USD, HKD/USD, NZD/USD, SEK/USD
- **Indexes (10):** S&P 500, NASDAQ Composite, Dow Jones, FTSE 100, DAX, CAC 40, Nikkei 225, Hang Seng, Euro Stoxx 50, Bovespa
- **Precious metals (4):** Gold (XAU), Silver (XAG), Platinum (XPT), Palladium (XPD)

## Endpoints

| Method | Endpoint                            | Description                                                            |
| ------ | ----------------------------------- | ---------------------------------------------------------------------- |
| GET    | `/finance/fx/rates`                 | Latest price for all FX pairs                                          |
| GET    | `/finance/fx/rates/{pair}`          | Latest price for one pair (e.g. `EURUSD`)                              |
| GET    | `/finance/fx/history/{pair}`        | 5-year daily history for one pair                                      |
| GET    | `/finance/indexes`                  | Latest value for all indexes                                           |
| GET    | `/finance/indexes/{symbol}`         | Latest value for one index (e.g. `GSPC`, `N225`)                       |
| GET    | `/finance/indexes/{symbol}/history` | 5-year daily history for one index                                     |
| GET    | `/finance/metals`                   | Latest price for all metals                                            |
| GET    | `/finance/metals/{metal}`           | Latest price for one metal (`gold`, `silver`, `platinum`, `palladium`) |
| GET    | `/finance/metals/{metal}/history`   | 5-year daily history for one metal                                     |
| GET    | `/finance/assets`                   | Full list of tracked assets                                            |
| GET    | `/finance/last-updated`             | Most recent stored date per asset                                      |
| GET    | `/finance/ingest-daily`             | Run the daily fetch now for all assets                                 |
| GET    | `/finance/db-check`                 | Database connectivity diagnostic                                       |
| POST   | `/finance/admin/backfill`           | Backfill 5 years of history for all assets                             |
| POST   | `/finance/admin/ingest-daily`       | Daily fetch for all assets (admin-gated)                               |

Admin endpoints require the `X-Admin-Key` header when `ADMIN_KEY` is set in the environment.

The scheduler runs the daily fetch automatically on weekdays at **23:00 UTC**.

## Database

MySQL/MariaDB. A single table stores everything:

| Column                            | Type                         |
| --------------------------------- | ---------------------------- |
| `id`                              | `BIGINT AUTO_INCREMENT` (PK) |
| `symbol`                          | `VARCHAR(20)`                |
| `date`                            | `DATE`                       |
| `open` / `high` / `low` / `close` | `DECIMAL(18,6)`              |
| `volume`                          | `BIGINT`                     |

Indexes (the only two present):

- `PRIMARY` — `id`
- `UNIQUE (symbol, date)` — drives all queries (`latest`, `history`, `last-updated`) and the upsert during ingestion (`INSERT ... ON DUPLICATE KEY UPDATE`)

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Author

João Barreto

- **Email:** barretobit@gmail.com
- **LinkedIn:** [linkedin.com/in/barretobit](linkedin.com/in/barretobit)
- **GitHub:** [github.com/barretobit](github.com/barretobit)

**Thank you for checking out Randata!**
