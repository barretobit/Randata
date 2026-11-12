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
_MAX_STORED_RESPONSES = 16
_MAX_STORED_RESPONSE_BYTES = 16 * 1024 * 1024


def example_response(example, description: str = "Successful response") -> dict:
    """OpenAPI `responses` entry showing an example 200 body."""
    return {200: {"description": description, "content": {"application/json": {"example": example}}}}


def cached_json_response(request: Request, key: str, producer) -> Response:
    """Serve a large JSON document, encoded and gzip-compressed once per cache reload.

    `producer()` builds the document. Its compressed bytes are stored under
    `key` until the next cache reload (least recently used dropped first), so
    repeated downloads of e.g. /cache/all cost no encoding or compression.
    Clients that do not accept gzip get the same document uncompressed.
    """
    accepts_gzip = "gzip" in request.headers.get("accept-encoding", "").lower()
    stored_key = (key, cache.loaded_at())
    with _compressed_responses_lock:
        compressed = _compressed_responses.get(stored_key)
        if compressed is not None:
            _compressed_responses.move_to_end(stored_key)

    body = None
    if compressed is None:
        body = json.dumps(jsonable_encoder(producer()), separators=(",", ":")).encode("utf-8")
        compressed = gzip.compress(body, compresslevel=5)
        if len(compressed) <= _MAX_STORED_RESPONSE_BYTES:
            with _compressed_responses_lock:
                _compressed_responses[stored_key] = compressed
                while len(_compressed_responses) > _MAX_STORED_RESPONSES:
                    _compressed_responses.popitem(last=False)

    if accepts_gzip:
        return Response(
            content=compressed,
            media_type="application/json",
            headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"},
        )
    return Response(content=body if body is not None else gzip.decompress(compressed), media_type="application/json")
