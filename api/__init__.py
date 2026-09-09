"""
api -- Phase 9. The production service boundary.

This package is the ONLY door between a client and the engine. Its job is serialization and
routing; it computes nothing. Every payload it serves comes from `engine/view_models.py`, which
in turn comes from the Phase 1-6 deterministic pipeline.

The constraint that shapes the whole package (Phase 8 brief 19, carried forward):

    no calculation or business logic may be duplicated outside the engine

So the API has no filter language, no formula parameter, and no query endpoint. A client can name
a metric_id, a role_id, a catalogued dimension, or ask a natural-language question -- and nothing
else. There is no request shape through which a client could ask the service to compute something
the engine did not already define.
"""
