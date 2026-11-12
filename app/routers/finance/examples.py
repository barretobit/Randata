"""Example response bodies shown in the OpenAPI documentation (`/docs`).

Kept apart from the route code so the endpoints stay readable. Each constant is
named after the endpoint function that uses it.
"""

from .responses import example_response

GET_ALL_FX_RATES = example_response([
    {"symbol": "EURUSD=X", "display": "EURUSD", "name": "Euro / US Dollar",
     "latest": {"date": "2026-09-08", "open": 1.162791, "high": 1.163873,
                "low": 1.160000, "close": 1.161710, "volume": 0}},
    {"symbol": "GBPUSD=X", "display": "GBPUSD", "name": "British Pound / US Dollar",
     "latest": {"date": "2026-09-08", "open": 1.354224, "high": 1.355326,
                "low": 1.352265, "close": 1.354536, "volume": 0}},
])

GET_FX_RATE = example_response({
    "symbol": "EURUSD=X",
    "display": "EURUSD",
    "name": "Euro / US Dollar",
    "latest": {"date": "2026-09-08", "open": 1.162791, "high": 1.163873,
               "low": 1.160000, "close": 1.161710, "volume": 0},
})

GET_FX_HISTORY = example_response({
    "symbol": "EURUSD=X",
    "display": "EURUSD",
    "name": "Euro / US Dollar",
    "count": 1300,
    "history": [
        {"date": "2021-09-09", "open": 1.1810, "high": 1.1840, "low": 1.1800, "close": 1.1825, "volume": 0},
        {"date": "2026-09-08", "open": 1.1628, "high": 1.1639, "low": 1.1600, "close": 1.1617, "volume": 0},
    ],
})

GET_ALL_INDEXES = example_response([
    {"symbol": "^GSPC", "name": "S&P 500", "region": "US",
     "latest": {"date": "2026-09-04", "open": 7750.190, "high": 7750.190,
                "low": 7706.120, "close": 7718.600, "volume": 4103570000}},
    {"symbol": "^N225", "name": "Nikkei 225", "region": "JP",
     "latest": {"date": "2026-09-08", "open": 65843.688, "high": 66791.844,
                "low": 65269.328, "close": 65269.328, "volume": 0}},
])

GET_INDEX = example_response({
    "symbol": "^GSPC",
    "name": "S&P 500",
    "region": "US",
    "latest": {"date": "2026-09-04", "open": 7750.190, "high": 7750.190,
               "low": 7706.120, "close": 7718.600, "volume": 4103570000},
})

GET_INDEX_HISTORY = example_response({
    "symbol": "^GSPC",
    "name": "S&P 500",
    "region": "US",
    "count": 1255,
    "history": [
        {"date": "2021-09-09", "open": 4500.0, "high": 4520.0, "low": 4495.0, "close": 4512.5, "volume": 3900000000},
        {"date": "2026-09-04", "open": 7750.2, "high": 7750.2, "low": 7706.1, "close": 7718.6, "volume": 4103570000},
    ],
})

GET_ALL_METALS = example_response([
    {"symbol": "GC=F", "display": "XAU", "name": "Gold", "unit": "USD per troy ounce",
     "latest": {"date": "2026-09-08", "open": 4466.5, "high": 4488.8,
                "low": 4426.2, "close": 4443.5, "volume": 127903}},
    {"symbol": "SI=F", "display": "XAG", "name": "Silver", "unit": "USD per troy ounce",
     "latest": {"date": "2026-09-08", "open": 66.735, "high": 67.835,
                "low": 66.025, "close": 66.735, "volume": 27451}},
])

GET_METAL = example_response({
    "symbol": "GC=F",
    "display": "XAU",
    "name": "Gold",
    "unit": "USD per troy ounce",
    "latest": {"date": "2026-09-08", "open": 4466.5, "high": 4488.8,
               "low": 4426.2, "close": 4443.5, "volume": 127903},
})

GET_METAL_HISTORY = example_response({
    "symbol": "GC=F",
    "display": "XAU",
    "name": "Gold",
    "unit": "USD per troy ounce",
    "count": 1257,
    "history": [
        {"date": "2021-09-09", "open": 1790.0, "high": 1805.0, "low": 1785.5, "close": 1794.2, "volume": 120000},
        {"date": "2026-09-08", "open": 4466.5, "high": 4488.8, "low": 4426.2, "close": 4443.5, "volume": 127903},
    ],
})

GET_ALL_STOCKS = example_response([
    {"symbol": "NVDA", "name": "NVIDIA",
     "latest": {"date": "2026-09-08", "open": 220.0, "high": 225.0,
                "low": 218.0, "close": 223.67, "volume": 50000000}},
    {"symbol": "AAPL", "name": "Apple",
     "latest": {"date": "2026-09-08", "open": 313.0, "high": 316.0,
                "low": 312.0, "close": 315.34, "volume": 30000000}},
])

GET_STOCK = example_response({
    "symbol": "NVDA",
    "name": "NVIDIA",
    "latest": {"date": "2026-09-08", "open": 220.0, "high": 225.0,
               "low": 218.0, "close": 223.67, "volume": 50000000},
})

GET_STOCK_HISTORY = example_response({
    "symbol": "NVDA",
    "name": "NVIDIA",
    "count": 1257,
    "history": [
        {"date": "2021-09-09", "open": 220.0, "high": 225.0, "low": 218.0, "close": 222.5, "volume": 40000000},
        {"date": "2026-09-08", "open": 220.0, "high": 225.0, "low": 218.0, "close": 223.67, "volume": 50000000},
    ],
})

GET_ALL_ETFS = example_response([
    {"symbol": "VOO", "name": "Vanguard S&P 500 ETF",
     "latest": {"date": "2026-09-08", "open": 585.0, "high": 590.0,
                "low": 582.0, "close": 588.9, "volume": 4000000}},
    {"symbol": "QQQ", "name": "Invesco Nasdaq-100 ETF",
     "latest": {"date": "2026-09-08", "open": 560.0, "high": 565.0,
                "low": 557.0, "close": 563.4, "volume": 40000000}},
])

GET_ETF = example_response({
    "symbol": "VOO",
    "name": "Vanguard S&P 500 ETF",
    "latest": {"date": "2026-09-08", "open": 585.0, "high": 590.0,
               "low": 582.0, "close": 588.9, "volume": 4000000},
})

GET_ETF_HISTORY = example_response({
    "symbol": "VOO",
    "name": "Vanguard S&P 500 ETF",
    "count": 1257,
    "history": [
        {"date": "2021-09-09", "open": 400.0, "high": 405.0, "low": 398.0, "close": 402.5, "volume": 3000000},
        {"date": "2026-09-08", "open": 585.0, "high": 590.0, "low": 582.0, "close": 588.9, "volume": 4000000},
    ],
})

GET_ALL_CRYPTO = example_response([
    {"symbol": "BTC-USD", "display": "BTC", "name": "Bitcoin",
     "latest": {"date": "2026-09-08", "open": 110000.0, "high": 112000.0,
                "low": 109000.0, "close": 111500.0, "volume": 30000000000}},
    {"symbol": "ETH-USD", "display": "ETH", "name": "Ethereum",
     "latest": {"date": "2026-09-08", "open": 4200.0, "high": 4300.0,
                "low": 4150.0, "close": 4250.0, "volume": 15000000000}},
])

GET_CRYPTO = example_response({
    "symbol": "BTC-USD",
    "display": "BTC",
    "name": "Bitcoin",
    "latest": {"date": "2026-09-08", "open": 110000.0, "high": 112000.0,
               "low": 109000.0, "close": 111500.0, "volume": 30000000000},
})

GET_CRYPTO_HISTORY = example_response({
    "symbol": "BTC-USD",
    "display": "BTC",
    "name": "Bitcoin",
    "count": 1257,
    "history": [
        {"date": "2021-09-09", "open": 46000.0, "high": 47000.0, "low": 45500.0, "close": 46500.0, "volume": 25000000000},
        {"date": "2026-09-08", "open": 110000.0, "high": 112000.0, "low": 109000.0, "close": 111500.0, "volume": 30000000000},
    ],
})

GET_HISTORY_ALL = example_response({
    "data": [
        {"symbol": "EURUSD=X", "date": "2021-09-09", "open": 1.1810, "high": 1.1840,
         "low": 1.1800, "close": 1.1825, "volume": 0},
        {"symbol": "EURUSD=X", "date": "2026-09-08", "open": 1.1628, "high": 1.1639,
         "low": 1.1600, "close": 1.1617, "volume": 0},
    ],
    "count": 2,
    "from": "2021-09-09",
    "to": "2026-09-08",
})

GET_HISTORY_RANGE = example_response({
    "count": 2,
    "from": "2024-01-02",
    "to": "2024-01-03",
    "source": "cache",
    "data": [
        {"symbol": "EURUSD=X", "date": "2024-01-02", "open": 1.0940, "high": 1.0960,
         "low": 1.0920, "close": 1.0950, "volume": 0},
        {"symbol": "GC=F", "date": "2024-01-03", "open": 2045.0, "high": 2060.0,
         "low": 2040.0, "close": 2052.5, "volume": 150000},
    ],
})

GET_LAST_UPDATED = example_response([
    {"symbol": "EURUSD=X", "last_date": "2026-09-08"},
    {"symbol": "GC=F", "last_date": "2026-09-08"},
])

LIST_ASSETS = example_response({
    "fx_pairs": [{"symbol": "EURUSD=X", "display": "EURUSD", "name": "Euro / US Dollar"}],
    "indexes": [{"symbol": "^GSPC", "name": "S&P 500", "region": "US"}],
    "precious_metals": [{"symbol": "GC=F", "display": "XAU", "name": "Gold", "unit": "USD per troy ounce"}],
    "stocks": [{"symbol": "NVDA", "name": "NVIDIA"}],
    "etfs": [{"symbol": "VOO", "name": "Vanguard S&P 500 ETF"}],
    "crypto": [{"symbol": "BTC-USD", "display": "BTC", "name": "Bitcoin"}],
})

RUN_BACKFILL_SYMBOL = example_response({
    "status": "done",
    "symbol": "^VIX",
    "rows_written": 1250,
    "latest": {"date": "2026-09-08", "open": 15.2, "high": 15.5,
               "low": 14.8, "close": 15.1, "volume": 120000},
})

LIST_TRACKED_ASSETS = example_response({
    "assets": [
        {"symbol": "EURUSD=X", "name": "Euro / US Dollar", "asset_type": "fx",
         "properties": {"display": "EUR/USD"}},
    ],
})

CHECK_ASSET_SYMBOL = example_response({
    "symbol": "LTC-USD",
    "exists": True,
    "confirmed_by": ["yf.Ticker.info", "yf.download"],
    "name": "Litecoin",
    "suggested_type": "crypto",
    "latest_close": 103.2,
    "note": None,
})

ADD_TRACKED_ASSET = example_response({
    "symbol": "LTC-USD",
    "name": "Litecoin",
    "asset_type": "crypto",
    "properties": {},
}, description="The stored asset row")

ONBOARD_ASSET = example_response({
    "status": "done",
    "asset": {"symbol": "LTC-USD", "name": "Litecoin", "asset_type": "crypto", "properties": {}},
    "rows_written": 1250,
    "latest": {"date": "2026-09-08", "open": 102.5, "high": 104.0,
               "low": 101.8, "close": 103.2, "volume": 50000},
}, description="The onboarded asset row, backfill row count and latest daily bar")

BACKFILL_TRACKED_ASSET = example_response({
    "status": "done",
    "symbol": "LTC-USD",
    "rows_written": 1250,
    "latest": {"date": "2026-09-08", "open": 102.5, "high": 104.0,
               "low": 101.8, "close": 103.2, "volume": 50000},
})

GET_CACHE_DETAILS = example_response({
    "loaded_at": "2026-09-10T00:00:00+00:00",
    "symbols": 116,
    "total_rows": 153950,
    "est_memory_mb": 66.1,
    "per_symbol": [
        {"symbol": "EURUSD=X", "rows": 1300, "first_date": "2021-09-09", "last_date": "2026-09-10"},
    ],
})

REFRESH_CACHE_FROM_DATABASE = example_response({
    "status": "done",
    "refreshed_at": "2026-09-10T00:00:00+00:00",
    "symbols": 116,
    "total_rows": 153950,
})

GET_SYMBOL = example_response({
    "symbol": "LTC-USD",
    "latest": {"date": "2026-09-08", "open": 102.5, "high": 104.0,
               "low": 101.8, "close": 103.2, "volume": 50000},
})

GET_SYMBOL_HISTORY = example_response({
    "symbol": "LTC-USD",
    "count": 1200,
    "history": [
        {"date": "2021-09-09", "open": 195.0, "high": 198.5, "low": 194.0,
         "close": 196.2, "volume": 400000},
        {"date": "2026-09-08", "open": 102.5, "high": 104.0, "low": 101.8,
         "close": 103.2, "volume": 50000},
    ],
})

RUN_BACKFILL = example_response({
    "status": "done",
    "fetched_at": "2026-09-08T12:00:00+00:00",
    "results": [
        {"symbol": "EURUSD=X", "name": "Euro / US Dollar", "rows_written": 1300,
         "latest": {"date": "2026-09-08", "open": 1.162791, "high": 1.163873,
                    "low": 1.160000, "close": 1.161710, "volume": 0}},
    ],
})

RUN_BACKFILL_MISSING = example_response({
    "status": "done",
    "fetched_at": "2026-09-08T12:00:00+00:00",
    "results": [
        {"symbol": "NVDA", "name": "NVIDIA", "asset_type": "stock", "rows_written": 1250,
         "latest": {"date": "2026-09-08", "open": 220.0, "high": 225.0,
                    "low": 218.0, "close": 223.67, "volume": 50000000}},
    ],
})

RUN_BACKFILL_INCEPTION_DATES = example_response({
    "status": "done",
    "fetched_at": "2026-09-08T12:00:00+00:00",
    "results": [
        {"symbol": "NVDA", "inception_date": "1999-01-22"},
        {"symbol": "SOME-IPO", "inception_date": "2023-04-11"},
    ],
})

GET_CACHE_ALL = example_response({
    "count": 31250,
    "symbols": 24,
    "data": [
        {"symbol": "EURUSD=X", "history": [
            {"date": "2021-09-09", "open": 1.1810, "high": 1.1840,
             "low": 1.1800, "close": 1.1825, "volume": 0},
        ]},
    ],
})

GET_CACHE_SYMBOL = example_response({
    "symbol": "GC=F",
    "count": 1257,
    "history": [
        {"date": "2021-09-09", "open": 1790.0, "high": 1805.0, "low": 1785.5,
         "close": 1794.2, "volume": 120000},
    ],
})

GET_LOGS = example_response({
    "count": 2,
    "logs": [
        {
            "id": 1,
            "recorded_at": "2026-09-08T23:00:12",
            "logger": "ingestion",
            "level": "INFO",
            "message": "Fetched ^GSPC (period=5d)",
            "symbol": "^GSPC",
            "duration_ms": 1234,
            "rows_written": 5,
            "success": True,
            "exception": None,
        },
    ],
})

RUN_DAILY_INGEST = example_response({
    "status": "done",
    "fetched_at": "2026-09-08T12:00:00+00:00",
    "results": [
        {"symbol": "GC=F", "name": "Gold", "rows_written": 5,
         "latest": {"date": "2026-09-08", "open": 4466.5, "high": 4488.8,
                    "low": 4426.2, "close": 4443.5, "volume": 127903}},
    ],
})
