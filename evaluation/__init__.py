"""Evaluation harness for the Kalakriti RAG pipeline.

This package is intentionally dependency-light (stdlib only) so the metrics
can be unit tested without a live Supabase/Ollama connection. `evaluate.py`
wires these metrics up against the real `RAGEngine` for an end-to-end run.
"""
