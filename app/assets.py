FX_PAIRS = [
    {"symbol": "EURUSD=X", "name": "Euro / US Dollar",             "display": "EUR/USD"},
    {"symbol": "CHFUSD=X", "name": "Swiss Franc / US Dollar",      "display": "CHF/USD"},
    {"symbol": "GBPUSD=X", "name": "British Pound / US Dollar",    "display": "GBP/USD"},
    {"symbol": "JPYUSD=X", "name": "Japanese Yen / US Dollar",     "display": "JPY/USD"},
    {"symbol": "CNYUSD=X", "name": "Chinese Yuan / US Dollar",     "display": "CNY/USD"},
    {"symbol": "NOKUSD=X", "name": "Norwegian Krone / US Dollar",  "display": "NOK/USD"},
    {"symbol": "DKKUSD=X", "name": "Danish Krone / US Dollar",     "display": "DKK/USD"},
    {"symbol": "HKDUSD=X", "name": "Hong Kong Dollar / US Dollar", "display": "HKD/USD"},
    {"symbol": "SEKUSD=X", "name": "Swedish Krona / US Dollar",    "display": "SEK/USD"},
    {"symbol": "NZDUSD=X", "name": "New Zealand Dollar / US Dollar","display": "NZD/USD"},
    {"symbol": "AUDUSD=X", "name": "Australian Dollar / US Dollar", "display": "AUD/USD"},
    {"symbol": "CADUSD=X", "name": "Canadian Dollar / US Dollar",  "display": "CAD/USD"},
]

INDEXES = [
    {"symbol": "^GSPC",     "name": "S&P 500",          "region": "US"},
    {"symbol": "^SSMI",     "name": "SMI",              "region": "CH"},
    {"symbol": "^IXIC",     "name": "NASDAQ Composite",  "region": "US"},
    {"symbol": "^DJI",      "name": "Dow Jones",         "region": "US"},
    {"symbol": "^GDAXI",    "name": "DAX",               "region": "DE"},
    {"symbol": "^STOXX50E", "name": "Euro Stoxx 50",     "region": "EU"},
    {"symbol": "^FTSE",     "name": "FTSE 100",          "region": "UK"},
    {"symbol": "^FCHI",     "name": "CAC 40",            "region": "FR"},
    {"symbol": "^N225",     "name": "Nikkei 225",        "region": "JP"},
    {"symbol": "^HSI",      "name": "Hang Seng",         "region": "HK"},
]

PRECIOUS_METALS = [
    {"symbol": "GC=F",  "name": "Gold",      "display": "XAU", "unit": "USD per troy ounce"},
    {"symbol": "SI=F",  "name": "Silver",    "display": "XAG", "unit": "USD per troy ounce"},
    {"symbol": "HG=F",  "name": "Copper",    "display": "XCU", "unit": "USD per pound"},
    {"symbol": "PL=F",  "name": "Platinum",  "display": "XPT", "unit": "USD per troy ounce"},
    {"symbol": "PA=F",  "name": "Palladium", "display": "XPD", "unit": "USD per troy ounce"},
]

STOCKS = [
    {"symbol": "NVDA",  "name": "NVIDIA"},
    {"symbol": "AAPL",  "name": "Apple"},
    {"symbol": "GOOG",  "name": "Alphabet (Google)"},
    {"symbol": "MSFT",  "name": "Microsoft"},
    {"symbol": "AMZN",  "name": "Amazon"},
    {"symbol": "AVGO",  "name": "Broadcom"},
    {"symbol": "META",  "name": "Meta Platforms"},
    {"symbol": "TSLA",  "name": "Tesla"},
    {"symbol": "MU",    "name": "Micron Technology"},
    {"symbol": "BRK-B", "name": "Berkshire Hathaway"},
    {"symbol": "LLY",   "name": "Eli Lilly"},
    {"symbol": "JPM",   "name": "JPMorgan Chase"},
    {"symbol": "AMD",   "name": "AMD"},
    {"symbol": "WMT",   "name": "Walmart"},
    {"symbol": "V",     "name": "Visa"},
    {"symbol": "XOM",   "name": "Exxon Mobil"},
    {"symbol": "JNJ",   "name": "Johnson & Johnson"},
    {"symbol": "INTC",  "name": "Intel"},
    {"symbol": "MA",    "name": "Mastercard"},
    {"symbol": "ORCL",  "name": "Oracle"},
    {"symbol": "ABBV",  "name": "AbbVie"},
    {"symbol": "BAC",   "name": "Bank of America"},
    {"symbol": "CSCO",  "name": "Cisco"},
    {"symbol": "CVX",   "name": "Chevron"},
    {"symbol": "PLTR",  "name": "Palantir"},
    {"symbol": "COST",  "name": "Costco"},
    {"symbol": "LRCX",  "name": "Lam Research"},
    {"symbol": "KO",    "name": "Coca-Cola"},
    {"symbol": "CAT",   "name": "Caterpillar"},
    {"symbol": "AMAT",  "name": "Applied Materials"},
    {"symbol": "MRK",   "name": "Merck"},
    {"symbol": "UNH",   "name": "UnitedHealth"},
    {"symbol": "DELL",  "name": "Dell"},
    {"symbol": "MS",    "name": "Morgan Stanley"},
    {"symbol": "GE",    "name": "General Electric"},
    {"symbol": "PG",    "name": "Procter & Gamble"},
    {"symbol": "NFLX",  "name": "Netflix"},
    {"symbol": "HD",    "name": "Home Depot"},
    {"symbol": "GS",    "name": "Goldman Sachs"},
    {"symbol": "PM",    "name": "Philip Morris International"},
    {"symbol": "PANW",  "name": "Palo Alto Networks"},
    {"symbol": "WFC",   "name": "Wells Fargo"},
    {"symbol": "RTX",   "name": "RTX"},
    {"symbol": "SNDK",  "name": "Sandisk"},
    {"symbol": "GEV",   "name": "GE Vernova"},
    {"symbol": "ANET",  "name": "Arista Networks"},
    {"symbol": "KLAC",  "name": "KLA"},
    {"symbol": "TXN",   "name": "Texas Instruments"},
    {"symbol": "C",     "name": "Citigroup"},
    {"symbol": "IBM",   "name": "IBM"},
    {"symbol": "RO.SW",    "name": "Roche"},
    {"symbol": "NOVN.SW",  "name": "Novartis"},
    {"symbol": "NESN.SW",  "name": "Nestlé"},
    {"symbol": "UBSG.SW",  "name": "UBS"},
    {"symbol": "ABBN.SW",  "name": "ABB"},
    {"symbol": "CFR.SW",   "name": "Richemont"},
    {"symbol": "ZURN.SW",  "name": "Zurich Insurance"},
    {"symbol": "SREN.SW",  "name": "Swiss Re"},
    {"symbol": "LONN.SW",  "name": "Lonza"},
    {"symbol": "HOLN.SW",  "name": "Holcim"},
    {"symbol": "SIE.DE",   "name": "Siemens"},
    {"symbol": "SAP.DE",   "name": "SAP"},
    {"symbol": "ENR.DE",   "name": "Siemens Energy"},
    {"symbol": "ALV.DE",   "name": "Allianz"},
    {"symbol": "DTE.DE",   "name": "Deutsche Telekom"},
    {"symbol": "AIR.DE",   "name": "Airbus"},
    {"symbol": "MUV2.DE",  "name": "Munich Re"},
    {"symbol": "RHM.DE",   "name": "Rheinmetall"},
    {"symbol": "DBK.DE",   "name": "Deutsche Bank"},
    {"symbol": "MBG.DE",   "name": "Mercedes-Benz"},
    {"symbol": "7203.T",   "name": "Toyota"},
    {"symbol": "8306.T",   "name": "Mitsubishi UFJ Financial"},
    {"symbol": "9984.T",   "name": "SoftBank Group"},
    {"symbol": "6501.T",   "name": "Hitachi"},
]

ETFS = [
    {"symbol": "VOO",  "name": "Vanguard S&P 500 ETF"},
    {"symbol": "IVV",  "name": "iShares Core S&P 500 ETF"},
    {"symbol": "SPY",  "name": "SPDR S&P 500 ETF"},
    {"symbol": "VTI",  "name": "Vanguard Total Stock Market ETF"},
    {"symbol": "VT",   "name": "Vanguard Total World Stock ETF"},
    {"symbol": "QQQ",  "name": "Invesco Nasdaq-100 ETF"},
    {"symbol": "VEA",  "name": "Vanguard FTSE Developed Markets ETF"},
    {"symbol": "VXUS", "name": "Vanguard Total International Stock ETF"},
    {"symbol": "VWO",  "name": "Vanguard FTSE Emerging Markets ETF"},
    {"symbol": "BND",  "name": "Vanguard Total Bond Market ETF"},
]

CRYPTO = [
    {"symbol": "BTC-USD",  "name": "Bitcoin",  "display": "BTC"},
    {"symbol": "ETH-USD",  "name": "Ethereum", "display": "ETH"},
    {"symbol": "USDT-USD", "name": "Tether",   "display": "USDT"},
    {"symbol": "SOL-USD",  "name": "Solana",   "display": "SOL"},
    {"symbol": "BNB-USD",  "name": "BNB",      "display": "BNB"},
]

ALL_ASSETS = FX_PAIRS + INDEXES + PRECIOUS_METALS + STOCKS + ETFS + CRYPTO

SYMBOL_MAP = {a["symbol"]: a for a in ALL_ASSETS}

METAL_MAP = {a["name"].lower(): a for a in PRECIOUS_METALS}

STOCK_MAP = {a["symbol"].lower(): a for a in STOCKS}

ETF_MAP = {a["symbol"].lower(): a for a in ETFS}

CRYPTO_MAP = {a["symbol"].lower(): a for a in CRYPTO}