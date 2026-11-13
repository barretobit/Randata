"""Response helpers shared by the finance routers."""

import gzip
import json
import threading
from collections import OrderedDict

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response

from ... import cache

# Compressed large responses, kept until the price cache is reloaded.
_compressed_responses: OrderedDict[tuple, bytes] = OrderedDict()
_compressed_responses_lock = threading.Lock()
# One lock per document being built, so concurrent requests wait for one build instead of repeating it.
_build_locks: dict[tuple, threading.Lock] = {}
# Room for every calendar-year history document (~1 MB each) plus the cache dumps.
_MAX_STORED_RESPONSES = 32
_MAX_STORED_RESPONSE_BYTES = 16 * 1024 * 1024


def example_response(example, description: str = "Successful response") -> dict:
    """OpenAPI `responses` entry showing an example 200 body."""
    return {200: {"description": description, "content": {"application/json": {"example": example}}}}


def _stored(stored_key: tuple) -> bytes | None:
    with _compressed_responses_lock:
        compressed = _compressed_responses.get(stored_key)
        if compressed is not None:
            _compressed_responses.move_to_end(stored_key)
        return compressed


def compressed_document(key: str, producer) -> tuple[bytes, bytes | None]:
    """A JSON document's gzip bytes, encoded and compressed once per cache reload.

    `producer()` builds the document. Its compressed bytes are stored under
    `key` until the next cache reload (least recently used dropped first).
    Returns (compressed, body): `body` is the plain JSON when this call built
    it, otherwise None.
    """
    stored_key = (key, cache.loaded_at())
    compressed = _stored(stored_key)
    if compressed is not None:
        return compressed, None
    with _compressed_responses_lock:
        build_lock = _build_locks.setdefault(stored_key, threading.Lock())
    with build_lock:
        compressed = _stored(stored_key)
        if compressed is not None:
            return compressed, None
        try:
            # `default` only runs for values json cannot encode itself (dates,
            # Decimals): far cheaper than walking the whole document first.
            body = json.dumps(producer(), separators=(",", ":"), default=jsonable_encoder).encode("utf-8")
            compressed = gzip.compress(body, compresslevel=5)
            if len(compressed) <= _MAX_STORED_RESPONSE_BYTES:
                with _compressed_responses_lock:
                    _compressed_responses[stored_key] = compressed
                    while len(_compressed_responses) > _MAX_STORED_RESPONSES:
                        _compressed_responses.popitem(last=False)
        finally:
            with _compressed_responses_lock:
                _build_locks.pop(stored_key, None)
    return compressed, body


def cached_json_response(request: Request, key: str, producer) -> Response:
    """Serve a large JSON document, encoded and gzip-compressed once per cache reload.

    Repeated downloads of e.g. /cache/all cost no encoding or compression.
    Clients that do not accept gzip get the same document uncompressed.
    """
    accepts_gzip = "gzip" in request.headers.get("accept-encoding", "").lower()
    compressed, body = compressed_document(key, producer)
    if accepts_gzip:
        return Response(
            content=compressed,
            media_type="application/json",
            headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"},
        )
    return Response(content=body if body is not None else gzip.decompress(compressed), media_type="application/json")
