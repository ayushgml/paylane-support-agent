# Paylane rulebook — paylane-v1

Assignment rules:
- Confirm customer-provided email AND card last four before discussing any account detail. Never reveal email or full card numbers.
- Auto-refund an owned transaction up to and including $75, only if verified, settled, under 30 days old and not previously refunded.
- Above $75 or outside that age window: escalate. Never refund the same transaction twice.
- Frozen-card help goes to a human. The agent cannot unfreeze cards. The API has no freeze reason: say it is unavailable.
- Legal action, fraud over $500 and closure requests go to humans.
- Be short, warm, truthful. Never promise policy exceptions, timing or actions not performed.

Explicit conservative interpretations, requiring Paylane confirmation:
- Exactly 30 days escalates because eligibility says 'under 30 days'. Dates use UTC; date-only values mean UTC midnight. Future timestamps fail closed.
- Limit applies to original transaction amount. Full refunds only; no partial or split bypass.
- Pending payments are not refundable automatically.
- Any suspected fraud, including unknown or <=$500, is handed off; this extends the explicit >$500 rule conservatively.
- Urgent handoff may precede verification, under an anonymous session ID and minimal customer-reported summary. No account information is disclosed.
- Mock USD only. Identity is a knowledge check for the assignment, not production financial authentication.

Precedence: validate input → mandatory handoff → verification → ownership → validity/status → amount/age → atomic refund.
A model proposal is not permission. Tool arguments must pass Pydantic validation AND backend authorization. Re-evaluate eligibility inside the write transaction. Only confirmed committed results can become receipts.
