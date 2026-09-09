import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_KEY = os.getenv("ADMIN_KEY")

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