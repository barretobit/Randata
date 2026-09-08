FX_PAIRS = [
    {"symbol": "EURUSD=X", "name": "Euro / US Dollar",            "display": "EUR/USD"},
    {"symbol": "GBPUSD=X", "name": "British Pound / US Dollar",   "display": "GBP/USD"},
    {"symbol": "JPYUSD=X", "name": "Japanese Yen / US Dollar",    "display": "JPY/USD"},
    {"symbol": "CHFUSD=X", "name": "Swiss Franc / US Dollar",     "display": "CHF/USD"},
    {"symbol": "AUDUSD=X", "name": "Australian Dollar / US Dollar","display": "AUD/USD"},
    {"symbol": "CADUSD=X", "name": "Canadian Dollar / US Dollar", "display": "CAD/USD"},
    {"symbol": "CNYUSD=X", "name": "Chinese Yuan / US Dollar",    "display": "CNY/USD"},
    {"symbol": "HKDUSD=X", "name": "Hong Kong Dollar / US Dollar","display": "HKD/USD"},
    {"symbol": "NZDUSD=X", "name": "New Zealand Dollar / US Dollar","display":"NZD/USD"},
    {"symbol": "SEKUSD=X", "name": "Swedish Krona / US Dollar",   "display": "SEK/USD"},
]

INDEXES = [
    {"symbol": "^GSPC",  "name": "S&P 500",          "region": "US"},
    {"symbol": "^IXIC",  "name": "NASDAQ Composite",  "region": "US"},
    {"symbol": "^DJI",   "name": "Dow Jones",         "region": "US"},
    {"symbol": "^FTSE",  "name": "FTSE 100",          "region": "UK"},
    {"symbol": "^GDAXI", "name": "DAX",               "region": "DE"},
    {"symbol": "^FCHI",  "name": "CAC 40",            "region": "FR"},
    {"symbol": "^N225",  "name": "Nikkei 225",        "region": "JP"},
    {"symbol": "^HSI",   "name": "Hang Seng",         "region": "HK"},
    {"symbol": "^STOXX50E", "name": "Euro Stoxx 50",  "region": "EU"},
    {"symbol": "^SSMI",   "name": "SMI",              "region": "CH"},
]

PRECIOUS_METALS = [
    {"symbol": "GC=F",  "name": "Gold",      "display": "XAU", "unit": "USD per troy ounce"},
    {"symbol": "SI=F",  "name": "Silver",    "display": "XAG", "unit": "USD per troy ounce"},
    {"symbol": "PL=F",  "name": "Platinum",  "display": "XPT", "unit": "USD per troy ounce"},
    {"symbol": "PA=F",  "name": "Palladium", "display": "XPD", "unit": "USD per troy ounce"},
]

ALL_ASSETS = FX_PAIRS + INDEXES + PRECIOUS_METALS

SYMBOL_MAP = {a["symbol"]: a for a in ALL_ASSETS}

METAL_MAP = {a["name"].lower(): a for a in PRECIOUS_METALS}