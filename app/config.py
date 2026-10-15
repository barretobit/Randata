import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_KEY = os.getenv("ADMIN_KEY")

# How many years of daily history to fetch and consider "full". The rolling
# window start is `today - 365 * HISTORY_YEARS`. Assets whose inception date is
# later than that are only expected to have history since inception.
HISTORY_YEARS = int(os.getenv("HISTORY_YEARS", "10"))
# Tolerance (weekends/holidays/multi-day backfills) when deciding whether an
# asset's stored history reaches back far enough to count as covered.
HISTORY_GRACE_DAYS = int(os.getenv("HISTORY_GRACE_DAYS", "14"))
# Years of history to hold in the in-memory price cache. Deliberately kept
# separate from (and much smaller than) HISTORY_YEARS: the database stores the
# full history, but the RAM cache must stay within the host's memory budget.
# The cache serves recent date-range reads without touching the database; a
# full initial load (10y) is expected to go to the database once. At ~400
# bytes/row, 1y x ~186 assets (~47k rows) is only ~20 MB.
CACHE_HISTORY_YEARS = int(os.getenv("CACHE_HISTORY_YEARS", "1"))

# Throttling for large multi-symbol Yahoo Finance fetches.
BACKFILL_DELAY_SECONDS = float(os.getenv("BACKFILL_DELAY_SECONDS", "2.0"))
BACKFILL_JITTER_SECONDS = float(os.getenv("BACKFILL_JITTER_SECONDS", "1.0"))
INGEST_DELAY_SECONDS = float(os.getenv("INGEST_DELAY_SECONDS", "1.0"))
INGEST_JITTER_SECONDS = float(os.getenv("INGEST_JITTER_SECONDS", "0.5"))

# Extra-gentle throttle used by the slow bulk backfill endpoint
# (POST /finance/admin/backfill-missing). "Really slow" on purpose so a
# wholesale backfill never trips Yahoo's rate limiter.
SLOW_BACKFILL_DELAY_SECONDS = float(os.getenv("SLOW_BACKFILL_DELAY_SECONDS", "12.0"))
SLOW_BACKFILL_JITTER_SECONDS = float(os.getenv("SLOW_BACKFILL_JITTER_SECONDS", "4.0"))

# Retry policy for rate-limit responses during a single symbol fetch.
YF_MAX_RETRIES = int(os.getenv("YF_MAX_RETRIES", "5"))
YF_RETRY_BASE_SECONDS = float(os.getenv("YF_RETRY_BASE_SECONDS", "4.0"))
# Backoff base used by the slow mode (waits even longer between retries).
SLOW_YF_RETRY_BASE_SECONDS = float(os.getenv("SLOW_YF_RETRY_BASE_SECONDS", "10.0"))