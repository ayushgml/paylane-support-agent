# Submission verification

Final cohort started at **2026-10-18T07:50:42.529180+00:00**. Raw trial timestamps are unchanged. Its fixed October 17 fixture clock controls synthetic transaction age; it is not the execution date.

This repository is a one-commit final snapshot. Raw evidence retains the original local evaluated build ID `0d94f6be98f216a55e5be6678d5286441790009c`. Source/configuration fingerprints, rather than a rewritten Git history, connect that evidence to the submitted code. Source SHA-256: `fdee12f76ced64fb95d6dab32d9e58c34133c62b6d0ab5df4190cbcc9045a665`.

| Check | Result |
|---|---|
| Clean final snapshot, locked install, no environment file | 155 offline backend tests passed |
| Full repeated evaluation | 280/280, every case 7/7 |
| Hard assertions | 4,200/4,200 |
| Required-tool contract omissions | Six, all recovered within the predeclared one-repair limit; retained in report |
| DeepEval quality | 840 valid ratings; three per transcript |
| Judge calibration | 22/22 engineering labels; 66 ratings; excluded from agent execution totals |
| Observed attack successes | 0/168 |
| Unsafe-attempt trials | 0/280 |
| Benign-control failures | 0/28 |
| Frontend | TypeScript/Vite build and five installed-Chrome Playwright tests passed |

Browser tests cover navigation, responsive layout, evidence display, stable retry identity and verification-badge state. Network fault/state tests use explicit mocked responses; actual agent behavior is measured by the full OpenRouter cohort. Offline backend tests use test-only providers. Submission transcripts are actual OpenRouter executions. Canonical twelve examples use trial 1; every trial remains under the final cohort.

[Repeated metrics](../backend/reports/reliability.md) · [Judge operations](../backend/reports/reliability/cohort-10/judge-operations.md) · [Calibration](../backend/reports/reliability/calibration-12/calibration.md) · [Security](../backend/reports/security/README.md)

The independent release verifier checks source/configuration hashes, trial completeness, recomputed hard checks, rating completeness and median scores. CI runs it without a key. Finite, authored, in-sample successes do not establish a production success rate, universal attack resistance or independent Paylane approval.

## Standalone hosting revision

The recorded 280-run core-agent benchmark predates the deployment adapter and application-title branding change. Its raw results and timestamps are unchanged. Only the OpenRouter `X-Title` literal differs inside `backend/src/paylane/`; every other package file, all prompts, scenarios, models, sampling settings, evaluator logic and lockfile match the benchmark. `deployment-compatibility.json` records original file hashes and a provider source hash with only that title normalized. `verify_release.py --recorded-baseline` checks these exact bounds and the full original evidence; default strict mode does not grant an exact-source release to a different fingerprint.

The Railway ASGI entrypoint is outside that package and receives separate tests. The current suite passes 159 backend tests, including four new proxy-authentication, exact-origin, Secure-cookie, invite and CSRF checks. This is separate deployment validation, not a claim of 280 new hosted executions.

Hosted validation passed all 16 checks, including private proxy admission, exact-origin rejection, signed Secure/HttpOnly cookies, CSRF, a real synthetic refund, exact replay, restart persistence and duplicate-refund denial. Five browser tests pass on the updated frontend. The public-response scan checks actual secret values against seven deployed HTML/asset/API responses without recording those values. See `backend/reports/security/hosted-smoke.json` and `hosted-public-scan.json`.
