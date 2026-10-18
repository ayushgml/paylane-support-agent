# Security verification

The dependency report records a fresh scan of the locked runtime/evaluation and frontend dependencies. `pip-audit 2.9.0` checked 88 dependencies with no skips; `npm audit` checked the frontend tree. Neither reported a known vulnerability at scan time. Raw audit outputs are included. Unknown vulnerabilities and application logic are outside a dependency feed's guarantee.

Provider credentials stay in the backend environment. Environment files, runtime databases, signing keys, caches and build outputs are excluded from the submission. Gitleaks scans the final tracked snapshot, built frontend, one-commit history and extracted ZIP before delivery. Publication verification records the results; no live key is an input to the public snapshot.

The final behavioral attack report is under `../reliability/cohort-10/attack-report.md`: 24 authored attack cases, seven executions each, plus four benign controls. The complete cohort also reports unsafe attempts, unmeasured outcomes and benign-control failures. Zero observed attack success on this authored suite is not universal security assurance. Real authentication, privacy review and payment-provider reconciliation remain launch prerequisites.
