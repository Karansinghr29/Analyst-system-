"""
Phase 1 Analytics Engine -- deterministic, offline metric execution over the immutable
exported CSV evidence package, gated by the semantic layer's trust rules.

Per implementation_roadmap.md Phase 1: this package implements evidence loading, metric
resolution, dimension resolution, execution, and provenance -- NOT natural-language parsing,
NOT LLM integration, NOT a chat interface. Question -> metric_id resolution is the caller's
job (Phase 4); this engine is invoked with an already-resolved metric_id.
"""
