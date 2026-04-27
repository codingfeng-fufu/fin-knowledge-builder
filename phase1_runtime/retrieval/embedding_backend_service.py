from __future__ import annotations

from typing import Any

from .embedding_backend import available_embedding_backends, default_embedding_backend


def get_active_embedding_backend_metadata() -> dict[str, Any]:
    active_backend = default_embedding_backend()
    available_backends = available_embedding_backends()
    active_backend_meta = dict(available_backends.get(active_backend.backend_id, {}))
    active_backend_meta["backend_id"] = active_backend.backend_id
    active_backend_meta["device"] = getattr(active_backend, "device", "cpu")
    return active_backend_meta


def get_embedding_backend_status() -> dict[str, Any]:
    available_backends = available_embedding_backends()
    return {
        "active_backend": get_active_embedding_backend_metadata(),
        "available_backends": available_backends,
    }
