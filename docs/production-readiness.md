# Production-readiness controls and boundaries

This is a mock fintech support system. A passing repeated cohort is a release requirement for the demonstration, not authorization to process real payments. The chosen runtime is one persistent backend instance. Each control below distinguishes implemented behavior from production dependencies.

| Area | Implemented in this repository | Evidence / production requirement |
|---|---|---|
| Identity and tenant isolation | Trusted verification, 15-minute authority expiry, three-attempt lock, identity-switch revocation, browser/session ownership | Offline authorization/expiry tests and live attack cases. Replace public synthetic knowledge checks with Paylane-authenticated identity before launch. |
| Input guardrails | Message bound, PAN/credential scrubbing before providers, explicit unsafe-Unicode/encoded-execution/resource-flood handling | Guardrail tests plus A05–A07/A24. Pattern checks are defense layers, not universal injection detection; benign controls measure overblocking. |
| Prompt/data separation | System/rulebook authority, trusted session context, merchant/user text untrusted, narrow tools | Direct/indirect injection tests. No claim of immunity to all new attacks. |
| Action authorization | Pydantic arguments, verified owner, customer-selected transaction, explicit amount consent, current read, policy recheck | Direct malicious-call tests; financial authority never comes from a model or judge. |
| Financial effects | Integer cents, atomic write, unique transaction refund, operation replay, durable handoff latch | Concurrency/restart/replay tests. Real payments need provider idempotency and unknown-outcome reconciliation. |
| Output guardrails | Typed intents, current-request receipt validation, minimal evidence projection, whole-public-result privacy checks | Cannot invent amounts, ticket IDs, freeze reasons or closure/unfreeze results. No raw model-text streaming. |
| Human control | Mandatory handoffs, unsupported partial-refund handoff, operator refund kill switch, read-only inference switch | Tickets are mock records. Paylane must provide a staffed support queue, ownership, operating hours and escalation runbooks. |
| Runtime limits | Logical/tool/response bounds, deadlines, request timeout/retry, circuit breaker, admission and daily limits | Rate-limit fault tests and bounded-load checks. Judge pacing is separate from business runtime admission. Provider credit caps remain necessary. |
| Secrets and data handling | Backend-only key; ignored environment/runtime files; secret/PAN redaction; no raw prompt dashboard export | Gitleaks history/bundle scans. Real deployment needs approved providers, residency/retention/access policies and key rotation ownership. |
| Reliability evaluation | Seven runs per case on configuration-checked cohorts, pass@k/pass^k, confidence intervals, strict error accounting | The final cohort is included; development evidence is archived separately outside this snapshot. Completed-case estimators do not turn missing slots into successes. |
| Grader reliability | Three repeated quality ratings, median, all rating errors retained, disagreement and labelled calibration | Same judge model repeated, not three independent model families. Hard safety cannot be voted away. |
| Adversarial evaluation | 24 explicit attack cases, seven repetitions, four benign controls; ASR separated from task/availability failures | Covers applicable injection, disclosure, excess agency, misinformation and consumption risks. Adaptive discovery and representative held-out queries remain launch work. |
| Observability | Redacted events for risk/model/tools/renderer, guardrail decisions, provider attempts, latency/tokens/available cost | Configure protected monitoring, SLOs, alerts, incident ownership and privacy-reviewed sampling for a deployed service. No public raw-trace endpoint. |
| Recovery and provenance | Request HMAC, stable retry IDs, per-trial durable start/result journal, exact fingerprints, durable schedule | Interrupted attempts fail and are never replaced. No node-level LangGraph checkpoint resume is claimed. |
| Dependencies and CI | Locked Python/npm dependencies, offline tests, production frontend build, local dependency/secret audits | Audit results are time-specific. Continuous vulnerability scanning, reviewed dependency updates and supply-chain ownership are operational requirements. |
| Deployment | Same-origin API, signed HttpOnly/Secure hosted cookies, CSRF/origin validation, CSP, private repository | HTTPS and persistent disk are required. Multi-instance service needs shared transactional storage/session coordination and deployment load testing. |
| Rollout | Documented release prerequisites and disable switches | Start supervised with anonymized real queries, explicit Paylane policy decisions, staffed handoffs, incident drills and rollback approval. |

## Release sequence

1. Pass offline policy, guardrail, concurrency, interruption and statistical tests.
2. Calibrate the judge against labelled positive and negative fixtures; record disagreement and mistakes.
3. Freeze agent, prompts, scenarios, model settings and dependency versions. Run all scheduled repeated trials; provider/judge errors fail strict pass.
4. Investigate failures. A code/prompt/configuration correction creates a new cohort; it never replaces a failed trial in the original cohort.
5. Require every case to pass all seven runs, zero unsafe attempts, zero observed unauthorized effects, and no unmeasured attack outcomes in the accepted cohort. Archive failed development evidence separately.
6. Build/browser-check, scan history and browser assets, review privacy projections, and verify that published evidence matches the evaluated source.
7. For real launch, separately complete Paylane integrations, policy approvals, privacy/security review and operational sign-off. Synthetic scores do not substitute for these.

## Threat coverage

The applicable taxonomy is the [OWASP GenAI 2025 list](https://genai.owasp.org/llm-top-10/). There is no RAG/vector index, model training or user-uploaded package execution in this application; training-data poisoning and embedding attacks are not claimed as exercised. System-prompt exfiltration is constrained by the typed renderer, while actual credentials are never put in model context. A detector score alone never authorizes an account action.

The supplied guidebook's relevant practices and explicit implementation choices are mapped in `guidebook-review.md`. Observability is complementary to offline evaluation; neither certifies future safety under every possible request.
