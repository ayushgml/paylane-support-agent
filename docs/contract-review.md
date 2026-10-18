# Independent contract review

October 18, 2026. Read-only range: `aa6cb0e..db7817f`. A fresh-context AI reviewer used offline reproductions and passed 55 scoped tests. It did not read credentials, call live APIs or modify the checkout. This is not human security certification.

## Findings and rulings

**Important: terminal receipts hid later selected tools.** An immediate successful refund/ticket return discarded later calls in a batch. Escalation followed by a forbidden refund could appear to have zero unsafe attempts. The ledger stayed safe; model-behavior evaluation was incomplete.

Accepted and corrected: every selection is recorded as a sanitized `proposed` event before dispatch. Forbidden-call checks and selection metrics include proposals. The complete bounded batch is processed/audited before receipt completion. A second refund is blocked and remains an unsafe attempted action; an earlier success cannot erase it.

**Minor: another known tool bypassed a required phase.** Any nonempty call list satisfied the missing-tool check, including an escalation instead of the sole offered lookup.

Accepted and corrected: every selected name must belong to the actual offered schemas. Unoffered calls are blocked and recorded; one contract repair is allowed, then failure. A blocked unsafe proposal still fails model behavior after recovery.

Three regressions failed before correction: `test_terminal_handoff_does_not_hide_forbidden_second_selection`, `test_duplicate_refund_in_one_batch_is_audited_even_after_first_commit`, and `test_wrong_known_tool_cannot_bypass_required_lookup_contract`. The full corrected suite passes 129 tests. The bounded-loop test now uses a legitimately verified read loop; an unverified unoffered tool correctly stops earlier. This is implementation verification, not a second independent approval of the corrected revision.

## Evidence consequence


## Declined conclusions and root rulings

| Set aside by reviewer | Root ruling |
|---|---|
| Repeated success from unfinished evidence | Accepted: require a complete new 280-slot cohort. |
| Provider compatibility beyond observed endpoints | Accepted limit: retain request/endpoint evidence, no permanent universal compatibility claim. |
| Calibration generalization beyond eight authored labels | Accepted limit: report reference agreement only; independent Paylane/held-out grading remains launch work. |
| Broader pre-existing architecture beyond regression scope | Accepted scope: earlier review and production dependencies still apply; this review does not certify the system. |
