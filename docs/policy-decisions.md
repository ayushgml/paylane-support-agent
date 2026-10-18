# Policy decisions to confirm

Policy assumptions to confirm before connecting real accounts.

1. Does the $75 limit apply to the original payment or the amount requested, and are partial refunds permitted? I’m using the original payment amount and disallowing partial/split workarounds.
2. Should a transaction exactly 30 days old be eligible, and what timezone defines its age? I’m interpreting 'under 30 days' strictly and using elapsed UTC time; date-only fixtures mean UTC midnight.
3. Can urgent legal/fraud/closure requests create a human ticket before identity verification, and what customer ID should we use? The mock implementation uses an anonymous session identifier and discloses no account details.
4. The customer API has no card-freeze reason. Where should that come from, and should suspected fraud at $500 or less also go to humans? I’m not inventing freeze reasons and conservatively escalating all suspected fraud.

These decisions remain launch questions until the policy owner approves the documented assumptions.
