# Codex and Claude Subscription Backends Design

**Status:** Approved design, ready for implementation planning

**Date:** 2026-08-01

**Scope:** Local `optimize-anything` CLI, Python runtime, generated evaluators, and packaged coding-agent skills

## Summary

Add a provider-neutral completion layer so LLM work can run through one of three backends:

- the existing LiteLLM/API-key path;
- a local Codex subscription through the official Codex Python SDK; or
- a local Claude subscription through the installed Claude Code CLI.

Direct CLI and Python use remain API-backed by default. Packaged skills instead select the subscription belonging to their host coding agent: Codex-hosted skills select Codex, and Claude-hosted skills select Claude. This selection is explicit in the skill's generated command, not inferred by the core CLI from ambient environment variables.

A subscription backend covers every built-in LLM role in a run: GEPA proposal/reflection, built-in judging, dimension analysis, scoring, and validation. Deterministic command and HTTP evaluators remain unchanged. Subscription calls are serialized per provider by default. On an eligible subscription failure, the run automatically switches that role to the corresponding vendor API if a usable key and fallback model are available, while warning immediately and recording the billing/provenance change.

The deliberately asymmetric implementation is:

- Codex uses the purpose-built `openai-codex` Python SDK and reuses the user's saved Codex authentication.
- Claude uses a tightly sandboxed `claude -p` subprocess because Anthropic's Agent SDK does not permit third-party products to offer Claude.ai subscription login. The Claude bridge is therefore local-only, opt-in, experimental, and carries an explicit policy caveat.

## Context

Today, proposer selection resolves to a model string and passes that string to GEPA's `ReflectionConfig.reflection_lm`. Built-in judging and dimension analysis call LiteLLM directly. CLI configuration exposes model names and API base URLs, and generated judge/composite evaluators also call LiteLLM directly.

That arrangement assumes every LLM operation is an API request. It misses a useful local workflow: the person invoking an optimization skill may already have an authenticated Codex or Claude Code subscription in the host agent. It also means subscription support cannot be added only to the proposer; doing so would leave judging, scoring, and analysis dependent on API keys.

GEPA already accepts a callable reflection LM, so the proposer does not need a GEPA fork. The new completion layer can supply that callable while also replacing the direct LiteLLM calls in the built-in evaluator paths.

## Research conclusions

### Codex

OpenAI documents both ChatGPT subscription login and API-key login for Codex. Non-interactive `codex exec` normally reuses saved CLI authentication, and the official Python SDK likewise reuses existing Codex authentication. The SDK exposes the app-server/thread model directly and is a better fit than parsing CLI output for an embedded Python application.

Relevant official documentation:

- [Codex authentication](https://developers.openai.com/codex/auth/)
- [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive/)
- [Codex SDK](https://developers.openai.com/codex/sdk/)
- [Codex Python SDK README](https://github.com/openai/codex/blob/main/sdk/python/README.md)
- [Codex Python SDK API reference](https://github.com/openai/codex/blob/main/sdk/python/docs/api-reference.md)

The adapter must reuse an existing ChatGPT login. It must not initiate login, accept tokens, copy credentials, or silently use an API-key-authenticated Codex session when the user requested a subscription.

### Claude

Anthropic documents `claude -p` for non-interactive use, JSON Schema output, `claude auth status`, and `--safe-mode`. Safe mode is important because it disables project instructions, skills, plugins, hooks, MCP servers, and other customizations while preserving authentication. The CLI also supports disabling tools and session persistence.

Anthropic's authentication precedence gives API tokens, API keys, and cloud-provider credentials priority over subscription login. A Claude subscription adapter must therefore perform auth preflight and execution with those overrides removed; otherwise a run advertised as subscription-backed could incur API or cloud charges.

Relevant official documentation:

- [Claude Code headless/programmatic mode](https://code.claude.com/docs/en/headless)
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)
- [Claude Code authentication](https://code.claude.com/docs/en/authentication)
- [Claude Code environment variables](https://code.claude.com/docs/en/env-vars)
- [Claude Code legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)
- [Claude Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)

Anthropic states that third-party developers should use API keys and may not offer Claude.ai login or route requests through Free, Pro, or Max credentials on behalf of users without approval. This design does not claim such approval. It limits the integration to a local subprocess chosen by the logged-in user, never handles login or credentials, labels the feature experimental, and excludes hosted/service use. That reduces credential and delegation risk but does not eliminate the policy risk; distribution documentation must disclose it plainly.

### GEPA

GEPA's reflection configuration accepts a callable language model. Its documentation also describes using a Claude CLI callable as a proposer. The backend abstraction can therefore present `complete_text(request)` as the GEPA reflection callable without modifying GEPA.

- [GEPA ReflectionConfig](https://gepa-ai.github.io/gepa/api/optimize_anything/ReflectionConfig/)
- [GEPA FAQ](https://gepa-ai.github.io/gepa/guides/faq/)
- [Using Claude Code as a proposer](https://gepa-ai.github.io/gepa/guides/claude-cli-as-proposer/)

## Goals

- Let local users run all built-in LLM roles with an existing Codex or Claude subscription.
- Preserve existing API-backed behavior for direct CLI and Python callers.
- Make coding-agent skills default to their host agent's subscription.
- Keep credentials outside `optimize-anything` and prove which auth class actually handled each call.
- Provide consistent structured-output, timeout, error, fallback, concurrency, cache, and provenance behavior across backends.
- Keep deterministic command/HTTP evaluators and their concurrency behavior unchanged.
- Make generated judge/composite evaluators use the same installed runtime rather than embedding a separate API-only implementation.

## Non-goals

- Implementing OAuth, device-code login, logout, token refresh, or credential storage.
- Supporting subscriptions from a hosted service, CI runner, shared daemon, or remote multi-user process.
- Making subscription execution the default for ordinary CLI or Python calls.
- Normalizing subscription limits into API token budgets or promising equivalent model availability across auth classes.
- Giving Codex or Claude access to the repository, MCP servers, shell tools, network tools, skills, hooks, or host-agent conversation state.
- Changing command/HTTP evaluator transport or parallelism.
- Preserving standalone portability for generated LLM judge/composite scripts; they will require the installed `optimize-anything` runtime.

## Design decisions

1. Use one completion contract and three adapters: LiteLLM API, Codex SDK, and Claude CLI.
2. Use the Codex Python SDK rather than `codex exec`; the SDK is purpose-built for embedding and exposes account, thread, sandbox, and structured-result concepts without CLI parsing.
3. Use `claude -p`, not the Claude Agent SDK, for the local Claude experiment. Do not expose or automate Claude login.
4. Keep direct invocation API-first. Host-agent behavior lives in skill instructions that pass explicit backend flags.
5. Use a selected subscription backend for every built-in LLM role, not only GEPA proposal.
6. Serialize subscription calls per provider by default. Allow an explicit concurrency override, with a warning, for advanced users.
7. Automatically fail over only for a narrow set of eligible failures. Once a role fails over, keep that role on API for the rest of the run.
8. Do not fail over on timeout because the subscription request may still have consumed usage, creating duplicate work and billing.
9. Route generated LLM evaluators through a shared installed runtime. Keep non-LLM verification and simulation templates self-contained.

## Architecture

### Package layout

The implementation should introduce a focused backend package rather than adding provider conditionals to CLI and judge modules:

```text
src/optimize_anything/
  llm_backends/
    __init__.py
    base.py              # contracts, capabilities, typed errors
    litellm_backend.py   # existing API path
    codex_backend.py     # optional Codex SDK adapter
    claude_backend.py    # local Claude CLI adapter
    fallback.py          # eligible-error circuit breaker
    factory.py           # config resolution and preflight
    provenance.py        # call and run summaries
  evaluator_runtime.py   # stable entry point for generated LLM evaluators
```

`cli_optimize.py`, `llm_judge.py`, validation, score, and analysis code should depend on the completion contract or factory, never on a concrete subscription adapter. LiteLLM imports should move behind `LiteLLMBackend`, apart from compatibility shims being removed in the same change.

### Completion contract

The central contract is deliberately stateless. A backend receives a fully assembled prompt and returns one completion; it does not inherit the host conversation or retain provider sessions between calls.

```python
@dataclass(frozen=True)
class CompletionRequest:
    prompt: str
    role: Literal["proposer", "judge", "analysis", "score", "validation"]
    model: str | None = None
    output_schema: Mapping[str, object] | None = None
    timeout_seconds: float | None = None
    sampling: SamplingOptions | None = None

@dataclass(frozen=True)
class CompletionResult:
    text: str
    structured: JsonValue | None
    requested_backend: str
    actual_backend: str
    requested_model: str | None
    actual_model: str | None
    auth_class: Literal["api", "subscription"]
    auth_source: Literal[
        "chatgpt", "claude_subscription", "openai_api", "anthropic_api", "other_api"
    ]
    usage: Usage | None
    fallback: FallbackRecord | None

class CompletionBackend(Protocol):
    def preflight(self) -> BackendStatus: ...
    def complete(self, request: CompletionRequest) -> CompletionResult: ...
```

`JsonValue` covers any JSON Schema result, although the initial built-in roles use objects. `Usage` contains provider-reported input, output, and total tokens when available. Cost remains nullable because subscription calls do not have a meaningful per-call API price. `FallbackRecord` contains the original backend, normalized failure category, and switch timestamp, but never raw credential-bearing provider payloads. `auth_source` identifies only the billing/auth mechanism, never an account or credential.

Each adapter publishes capabilities for structured output, model override, sampling controls, cancellation, and usage reporting. Unsupported requested controls cause `ConfigurationError` before dispatch; adapters must not silently ignore them. The initial optimization integration needs plain text and JSON Schema output. Chat history and multi-turn provider sessions are intentionally absent.

### Backend specification

Resolved configuration becomes an immutable role-specific `BackendSpec`:

```python
@dataclass(frozen=True)
class BackendSpec:
    backend: Literal["api", "codex", "claude"]
    model: str | None
    api_base: str | None
    api_fallback: bool
    api_fallback_model: str | None
    max_concurrency: int
```

The factory validates the whole run once, resolves fallback models, performs auth/capability preflight, and returns shared backend instances. It does not preflight on every candidate evaluation.

When fallback is enabled, the factory returns a `FallbackBackend` that wraps the subscription primary and corresponding `LiteLLMBackend`. The wrapper owns role circuits, eligible-error classification, billing warnings, and requested-versus-actual provenance; concrete provider adapters do not decide whether to switch transports.

### LiteLLM API backend

`LiteLLMBackend` preserves current behavior:

- it accepts existing provider/model strings and `api_base`;
- it calls LiteLLM for text and structured completions;
- it maps LiteLLM/provider failures to the shared typed errors;
- it reports `auth_class="api"`; and
- it remains the default when no backend is specified by a direct caller.

No existing API key is copied into a `BackendSpec`, result, log, or cache key. LiteLLM continues to discover credentials through its supported environment/config mechanisms.

### Codex SDK backend

`CodexSdkBackend` is installed through the optional extra:

```text
optimize-anything[codex]
```

The extra pins `openai-codex` to the tested compatible range in the project lockfile. The release gate must verify the required account-status, ephemeral-thread, sandbox, cancellation, and structured-output APIs against that range before enabling the adapter.

Preflight uses the SDK's account-status surface and succeeds only when the saved session is authenticated through ChatGPT. An API-key-authenticated Codex session does not count as a subscription backend. The adapter reports a direct remediation command such as `codex login`, but never runs it.

Every request uses a fresh thread in a newly created private temporary workspace. The thread configuration must enforce:

- read-only filesystem access to the empty temporary workspace;
- no repository working directory or inherited project instructions;
- no MCP servers;
- no shell, file mutation, or other agent tools;
- no model-accessible network tools;
- no user/project configuration except the minimum needed to reuse authentication; and
- no session reuse after the completion.

The SDK/app-server transport may reach OpenAI; “no network tools” means the model cannot browse or initiate arbitrary network access. If the tested SDK cannot enforce every isolation property, the Codex adapter is release-blocked rather than weakened silently.

The prompt is submitted through the SDK request body, never a process argument. JSON Schema requests use the SDK's structured-output support and are validated again locally before returning.

### Claude CLI backend

`ClaudeCliBackend` depends on an external `claude` executable and introduces no Python package extra. Preflight checks the executable's version/capabilities and runs `claude auth status` under the same scrubbed environment used for completions. It succeeds only for a logged-in Claude subscription, not an API token, API key, Bedrock, Vertex, or Foundry configuration.

The subprocess shape is capability-equivalent to:

```text
claude -p \
  --safe-mode \
  --tools "" \
  --disable-slash-commands \
  --strict-mcp-config \
  --mcp-config <private-empty-config> \
  --no-session-persistence \
  --max-turns 1 \
  --output-format json \
  --json-schema <sanitized-structural-schema-when-requested>
```

The prompt is written to stdin, never appended to the argument vector. Anthropic's documented interface requires the JSON Schema value as the `--json-schema` argument. Before dispatch, the adapter removes non-structural annotations such as `title`, `description`, `$comment`, `examples`, and `default`, and rejects schemas containing non-static external references. This keeps objective, candidate, and other user artifact text out of the process list while retaining validation keywords. The original schema is still applied locally to the returned value. The empty MCP file is created with user-only permissions in a private temporary directory and removed after the call. stdout and stderr are captured separately with bounded size.

The child environment removes the documented API/cloud authentication overrides and the `CLAUDECODE` parent-agent marker. At minimum this covers Anthropic API/auth variables, Claude OAuth-token overrides, Bedrock/AWS selectors and credentials, Vertex/Google selectors and credentials, Foundry/Azure selectors and credentials, and any configured API-key helper. The denylist is maintained beside the adapter with tests derived from Anthropic's authentication precedence documentation. The parent environment remains intact so an API fallback can still use its API key after the subscription subprocess exits.

`--bare` must not be used because it bypasses the credential stores needed for subscription authentication. Safe mode plus explicit tool/MCP/session restrictions provides isolation while preserving the user's saved login.

The implementation publishes a tested minimum Claude CLI version whose documented flags satisfy this contract. A missing flag or an auth-status response that cannot distinguish subscription from paid API/cloud auth is `BackendUnavailable`, not a reason to run with weaker isolation.

### GEPA proposer integration

GEPA receives a callable instead of a model string when the resolved proposer backend is Codex or Claude. The callable builds a `CompletionRequest(role="proposer")`, calls the shared backend, and returns the result text expected by GEPA.

The API path also uses the callable backed by `LiteLLMBackend`, so error mapping and provenance are uniform across proposer backends. Regression tests must prove that this internal plumbing change preserves existing GEPA proposal behavior and defaults.

### Built-in judge, analysis, score, and validation

Direct `litellm.completion` calls in built-in judging and dimension analysis move behind `CompletionBackend.complete`. JSON-producing operations provide a schema and reject invalid local validation rather than trying to recover provider-specific output in each caller.

The same mechanism covers:

- optimize's built-in LLM judge;
- `score`;
- `analyze` and dimension discovery;
- analysis performed while generating an evaluator; and
- each LLM provider entry used by `validate`.

The role field remains distinct even when multiple roles share one configured judge backend. This preserves independent fallback circuits and useful provenance.

### Generated evaluator runtime

Judge and composite evaluator templates stop importing LiteLLM or embedding provider calls. They become thin wrappers around a stable installed entry point in `optimize_anything.evaluator_runtime`.

The wrapper still obeys the existing evaluator JSON-lines contract: it reads an input containing `candidate` and writes an object containing numeric `score`. It passes template configuration and the candidate to the shared runtime, which resolves the configured backend and performs structured judging.

Consequences:

- generated LLM evaluators require a compatible installed `optimize-anything` package;
- their generated metadata records that runtime requirement and minimum compatible contract version;
- deterministic verification/simulation templates remain standalone; and
- preflight probes must remain local and must not trigger an LLM call.

## Configuration and selection

### CLI

The optimize command gains explicit role-specific backend flags:

```text
optimize-anything optimize seed.txt \
  --proposer-backend codex \
  --judge-backend codex \
  --objective "Improve clarity"
```

Rules:

- `--proposer-backend` and `--judge-backend` accept `api`, `codex`, or `claude`.
- Omitted backend flags resolve to `api` for direct CLI calls.
- Existing `--model`, `--judge-model`, and `--api-base` behavior remains unchanged for API backends.
- A subscription model may be omitted to use the coding agent's default model. An explicit model is passed through only if the adapter reports model-override support.
- Selecting `--judge-backend` selects the built-in judge and remains mutually exclusive with command and HTTP evaluator options.
- Commands that already expose a single LLM role gain the corresponding backend flag: `score` uses `--judge-backend`; `analyze` and evaluator analysis use `--analysis-backend` while retaining their existing model flags.
- All subscription-using commands expose `--subscription-concurrency`, default `1`. Values above `1` emit a warning and are applied per provider, not to command/HTTP evaluators.
- `--no-api-fallback` disables automatic fallback. Fallback is otherwise enabled for explicit subscription selection when a corresponding API key and resolvable fallback model exist.
- `--openai-api-fallback-model` and `--anthropic-api-fallback-model` override every matching role for that invocation. When proposer and judge need different API fallback models for the same vendor, configure their separate TOML role tables and omit the provider-wide CLI override.
- An explicit `--api-base` is used by an API fallback as well as a primary API backend; the backend plan prints that a custom base is active without printing credentials.

`validate --providers` continues accepting existing API model strings and additionally accepts reserved subscription selectors:

```text
codex
codex:<model>
claude
claude:<model>
```

Reserved selectors are parsed before LiteLLM model strings. API validation providers keep their current behavior.

### TOML

Legacy scalar model configuration remains valid. Structured role tables add backend configuration:

```toml
[model.proposer]
backend = "codex"
model = "gpt-5.6-sol" # optional for subscriptions
api_fallback = true
api_fallback_model = "openai/gpt-5.6-sol"

[model.judge]
backend = "codex"
api_fallback = true
api_fallback_model = "openai/gpt-5.6-luna"
```

Analysis and score commands use the judge role configuration unless explicitly overridden on their command line. This keeps the configuration model compact while preserving distinct runtime role labels and circuits.

For a subscription role, omitted `api_fallback` defaults to `true`; for an API role it is ignored. Fallback still requires ready corresponding-vendor credentials and a resolvable model. The CLI's `--no-api-fallback` overrides all role tables for that invocation.

Resolution precedence is:

1. command-line role option;
2. structured role table;
3. legacy scalar role value, interpreted as `backend="api"`;
4. existing API default.

Mixing a legacy scalar and a structured table for the same role is a configuration error with the conflicting keys named in the diagnostic.

### Python

Existing Python entry points keep API defaults. Advanced callers may construct a `BackendSpec` through the public backend factory and pass it to supported optimization/judge entry points. Concrete SDK/CLI clients stay internal so the project can evolve adapter details without expanding the compatibility surface.

### Host-agent skills

Core code does not guess its host from `CLAUDECODE`, terminal metadata, or other ambient markers. Packaged skill instructions know which agent is executing them and pass explicit flags:

- in Codex: `--proposer-backend codex --judge-backend codex`;
- in Claude Code: `--proposer-backend claude --judge-backend claude`;
- in an unknown or unsupported host: omit the flags and retain API behavior.

The skill passes a judge backend only when the workflow actually uses the built-in judge; an external command or HTTP evaluator does not need one. Before execution, the skill announces that it will use the host's logged-in subscription, that calls are serialized, and that eligible failures can switch to billed API usage when a corresponding key is available. The CLI's own preflight remains authoritative.

## Preflight and runtime flow

For each distinct requested backend, startup performs one preflight:

1. Validate configuration and optional dependency/executable availability.
2. Check required structured-output and isolation capabilities.
3. Inspect auth status without reading a credential.
4. Confirm the auth class is the requested subscription.
5. Resolve the corresponding vendor API fallback and test only for the presence of supported credential configuration without retaining or logging its value.
6. Create a provider-wide semaphore and independent role circuits.
7. Print a concise backend plan before any paid or quota-consuming request.

Preflight does not send a model request. If subscription preflight fails with an eligible error and fallback is ready, the affected role starts directly on API, emits the fallback warning, and records the preflight cause. If no fallback is ready, the command exits with remediation that names the missing executable, extra, login, API key, or fallback model as appropriate.

During execution, a subscription call acquires its provider semaphore, dispatches one isolated request, validates the result, records provenance, and releases the semaphore in `finally`. Codex and Claude have separate semaphores; command/HTTP evaluator concurrency does not acquire them.

## Error model and fallback

All adapters normalize failures into:

- `BackendUnavailable`
- `AuthenticationError`
- `RateLimitError`
- `QuotaExceeded`
- `Timeout`
- `InvalidResponse`
- `ConfigurationError`

Fallback behavior is deliberately conservative:

| Failure | API fallback? | Reason |
|---|---:|---|
| Missing optional SDK or executable | Yes | Subscription backend is unavailable before dispatch |
| Logged out or wrong auth class | Yes | Subscription cannot serve the request |
| Subscription quota exhausted | Yes | API is the configured continuity path |
| Provider rate limit / temporary availability | Yes | Retry would otherwise block the run |
| Timeout or cancellation | No | The original request may still consume usage; avoid duplicate work/billing |
| Invalid request or unsupported control | No | Switching transport will not repair caller/configuration defects |
| Malformed or schema-invalid response | No | Preserve deterministic failure and expose adapter/provider defect |
| Internal programming/configuration error | No | Never hide implementation defects behind paid fallback |

Codex falls back only to an OpenAI API model; Claude falls back only to an Anthropic API model. Fallback requires both a resolvable API model and a positive, non-secret readiness probe for the corresponding LiteLLM credentials. Initially, readiness means a non-empty canonical `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` is present; future credential resolvers may participate only through a boolean/status interface that does not expose the value. The model may be explicit or come from the project's centralized provider-and-role fallback defaults. If either requirement is absent, fallback is unavailable and the original normalized error is raised with remediation.

The first eligible failure opens a circuit for that backend and role for the rest of the run. Later calls for that role go directly to API. Proposer, judge, analysis, score, and validation circuits are independent, so a judge failure does not move the proposer. A run that mixes backends is marked `mixed_backend=true`; this is especially visible for judges because a backend change can affect score comparability.

There is no silent fallback. The first switch produces an immediate stderr warning containing role, source backend, target API model, reason category, and the fact that API billing may apply. Final summaries repeat the switch and counts.

## Concurrency and cancellation

Each subscription provider has an in-process semaphore with default capacity one. Every proposer, judge, analysis, score, and validation call through that provider shares it. This avoids bursts against interactive subscription limits and prevents multiple local agent sessions from contending for credential/session state.

An explicit concurrency override changes the semaphore capacity and emits a warning. It does not change GEPA worker count, command evaluator concurrency, HTTP evaluator concurrency, or cross-provider concurrency.

On provider timeout, the backend attempts provider-supported cancellation, terminates a Claude child process with a bounded graceful period, cleans private temporary files, and raises `Timeout` without API fallback. A user interruption propagates through the CLI's existing interruption path, also without fallback, after the same cleanup. Cleanup failures are reported without masking the primary error.

## Security and credential handling

The feature follows these invariants:

- Never read credential file contents or parse, copy, return, cache, or log OAuth tokens, API keys, cookies, or authorization headers. Fallback readiness may test only whether a canonical credential environment variable is present and non-empty.
- Inspect only provider-supported account/auth status metadata.
- Never initiate login or open a browser/device-code flow.
- Never put prompts, user artifact text, or secrets on a process command line. Claude receives only a stripped structural schema in its documented `--json-schema` argument.
- Use user-only private temporary directories and deterministic cleanup.
- Bound captured stdout/stderr and redact known credential-shaped values before diagnostics.
- Exclude repository contents, host-agent conversation state, project instructions, skills, plugins, hooks, MCP configuration, and user tools from subscription requests.
- Preserve the minimum environment needed for the provider's saved local authentication while removing overrides that would change the billed auth class.
- Record `subscription` versus `api` auth class, never credential identity.

Security tests must inspect the actual child argument vector, environment keys, temporary permissions, backend configuration, and produced logs/artifacts. A release is blocked if isolation depends only on prompt instructions.

## Provenance, summaries, and cache identity

Every completion records:

- run and call identifier;
- semantic role;
- requested and actual backend;
- requested and actual model, when the provider reports it;
- auth class (`subscription` or `api`);
- auth source (`chatgpt`, `claude_subscription`, or the resolved API provider class);
- start time and duration;
- provider-reported usage, when available;
- retry count;
- fallback source and normalized reason; and
- schema/prompt contract version.

Run summaries aggregate calls and usage by backend, model, auth class, and role; list fallback causes; show whether the run mixed backends; and keep cost nullable for subscription calls. The canonical optimize summary contract should gain additive optional fields so existing consumers remain valid.

Cache fingerprints include:

- actual backend;
- actual model or a stable `provider-default` marker;
- auth class;
- role;
- prompt/schema contract version; and
- candidate/input identity.

Fallback output is written under the actual API fingerprint, not the requested subscription fingerprint. Auth class is part of identity because provider defaults, system behavior, and limits can differ even when model names appear equal.

## Backward compatibility

- No backend option means API, exactly as today.
- Existing model strings, API bases, environment keys, evaluator command/URL options, and legacy TOML scalar values retain their meaning.
- Existing command/HTTP evaluator JSON contracts and concurrency remain unchanged.
- New summary data is additive and optional.
- Existing generated deterministic evaluators remain standalone.
- Generated LLM evaluator portability changes intentionally and is called out in generated comments, CLI output, migration notes, and release notes.
- The Codex dependency remains optional; ordinary installs do not gain the SDK.
- Missing Claude CLI has no effect unless Claude is selected explicitly or by a host skill.

## Verification strategy

### Offline unit and contract tests

All default project gates remain network-free. Shared backend contract tests use fakes and cover:

- text and schema completions;
- schema validation and invalid responses;
- timeout and cancellation;
- every normalized error category;
- unsupported capabilities;
- provenance completeness;
- bounded/redacted diagnostics; and
- absence of secrets in results, logs, cache keys, and artifacts.

Codex adapter tests use a fake SDK/app-server and verify:

- optional-extra diagnostics;
- account status accepts ChatGPT auth and rejects API-key auth;
- one ephemeral thread and private empty workspace per request;
- read-only sandbox, no tools, no MCP, no project/user instructions, and no model network tools;
- prompt and schema request placement;
- structured result and local schema validation;
- cleanup and cancellation; and
- failure when any isolation capability cannot be enforced.

Claude adapter tests use a fake executable and verify:

- exact safe-mode/tool/MCP/session/schema flags;
- prompt arrives through stdin and is absent from argv;
- auth preflight uses the same scrubbed environment as completion;
- API, OAuth override, Bedrock, Vertex, Foundry, and `CLAUDECODE` variables are absent;
- necessary saved-login environment remains available;
- JSON/stdout parsing, bounded stderr, exit-code mapping, timeout termination, and cleanup; and
- missing required CLI capabilities block execution.

Fallback tests verify:

- only eligible categories switch;
- missing auth, quota, rate limit, and backend-unavailable paths;
- no fallback on timeout, cancellation, invalid request, invalid response, or configuration error;
- corresponding-vendor key/model requirements;
- an immediate billing warning;
- independent per-role circuits;
- no second subscription attempt after a circuit opens; and
- correct mixed-backend summary and cache identity.

Concurrency tests prove the default maximum is one active request per subscription provider, an override changes only that provider's semaphore, and command/HTTP evaluators remain unaffected.

Compatibility tests cover:

- unchanged CLI defaults and help behavior;
- existing `--model`, `--judge-model`, and API-base paths;
- legacy and structured TOML parsing plus conflict diagnostics;
- reserved `validate --providers` selectors;
- current Python entry-point defaults;
- canonical result-contract compatibility;
- generated judge/composite wrappers contain no direct LiteLLM call;
- generated wrapper/runtime contract versioning; and
- Codex-, Claude-, and unknown-host skill command fixtures.

### Opt-in live integration gates

Live gates are separate from `scripts/check.py`, skipped unless explicitly enabled, and never run in normal CI:

1. `integration_codex_subscription` performs one JSON Schema completion using existing ChatGPT Codex auth, then asserts subscription provenance and isolation evidence.
2. `integration_claude_subscription` performs one safe-mode JSON Schema completion after API/cloud overrides are removed, then asserts subscription provenance and the expected CLI mode.
3. Each provider runs one minimal end-to-end optimization with budget `1` and a deterministic command evaluator, proving the GEPA callable path without introducing an LLM judge variable.
4. API fallback is tested with fakes by default. A paid live fallback requires a separate explicit marker and prints a billing warning before dispatch.

Live evidence records compatible SDK/CLI versions, operating system, auth class without account identity, requested/actual model, and pass/fail isolation assertions. It must not retain prompts that contain user artifacts unless the user explicitly requests artifact retention.

### Release gates

The feature may ship only when:

- the complete existing test suite and `scripts/check.py` pass offline;
- all backend, fallback, concurrency, compatibility, and skill fixture tests pass;
- no credential, prompt, or user artifact text appears in argv, logs, cache keys, or retained temporary artifacts;
- tested Codex SDK and Claude CLI versions are pinned/documented;
- Codex and Claude isolation capabilities are verified rather than inferred;
- direct CLI/Python behavior is demonstrably backward-compatible;
- subscription calls serialize by default;
- opt-in live gates provide passing evidence on supported platforms; and
- Claude documentation prominently includes the local-only experimental scope and Anthropic policy caveat.

Failure to enforce isolation, distinguish subscription auth from API/cloud auth, or validate structured output blocks the affected adapter. The implementation must not fall back to a less isolated invocation.

## Documentation and rollout

Ship in three layers:

1. Introduce the completion contract and migrate existing LiteLLM behavior with no user-visible default change.
2. Add Codex behind the optional extra and opt-in flags, then update Codex-hosted skills after live verification.
3. Add Claude as an experimental local adapter and update Claude-hosted skills only after the CLI capability, auth-class, isolation, and policy disclosures are verified.

Documentation must include installation, auth preflight, backend/model selection, API fallback and billing behavior, concurrency, generated evaluator runtime requirements, troubleshooting, supported versions/platforms, data handling, and removal/disable instructions. Examples must never instruct users to paste tokens into `optimize-anything`.

## Acceptance criteria

The design is implemented when a local, already logged-in Codex or Claude user can invoke the corresponding host skill and complete a budget-1 optimization without an API key, including any built-in LLM role selected by that workflow; direct CLI calls still use the API by default; eligible failures switch only to a ready corresponding-vendor API fallback with an immediate billing warning; all actual backend/auth/model choices are visible in the final summary; subscription calls serialize; generated LLM evaluators use the shared runtime; and the isolation, compatibility, offline, and opt-in live gates above pass.
