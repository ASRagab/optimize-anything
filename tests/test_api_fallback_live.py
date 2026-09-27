"""Opt-in live gate for the paid same-vendor API fallback path."""

# Fallback trigger design (Verification Contract step 11).
#
# Chosen: option (a), a test-only fake subscription adapter. `create_backend`
# has no DI parameter, so the tests monkeypatch the module attributes it
# resolves lazily (`codex_backend.CodexSdkBackend`,
# `claude_backend.ClaudeCliBackend`) and `factory.LiteLLMBackend`, then build
# backends through `resolve_backend_spec` + `create_backend`. Real spec
# resolution, `FallbackBackend`, `RunCoordinator`, and `LiteLLMBackend` run,
# and `--no-api-fallback` hits its real branch (`_CoordinatedBackend`, which
# never builds an API backend); constructing `FallbackBackend` directly would
# skip both.
#
# Not (b): `CODEX_HOME` / `PATH` can make the real adapters fail, but that
# depends on the local install layout, and counting subscription attempts would
# still need a wrapper around the real adapter. The fake is deterministic and
# never touches subscription credentials. Adapter isolation is untouched; the
# only new environment variable is the opt-in gate.
#
# Invariants (checked offline with fakes before writing the tests):
# - The fake passes `preflight()` and raises `BackendUnavailable` only from
#   `complete()`: a preflight failure sends every role straight to API and
#   would hide the per-role circuit.
# - The fake accepts `model=` and exposes `capabilities`, which
#   `_CoordinatedBackend` reads unconditionally.
# - The API leg subclasses the real `LiteLLMBackend`, only records each call
#   (count, model, order relative to stderr), and calls `super().complete()`
#   without `completion=`, so calls are real, billed, and report real usage.
# - Each case passes an explicit `RunCoordinator.create()`, so circuits use the
#   production store and provenance events carry usage and the no-API proof.
