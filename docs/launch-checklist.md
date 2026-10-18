# Before a real Paylane launch

This repository demonstrates a synthetic, single-instance mock service. Real card/refund systems and production identity are not connected.

- Confirm the four policy questions in policy-decisions.md.
- Replace email/last-four knowledge checks with Paylane-authenticated identity and account authorization.
- Integrate the real payments API with provider idempotency keys and reconciliation of unknown outcomes. The mock's atomic SQLite refund is not proof of remote exactly-once delivery.
- Connect a staffed support queue. Define owner, operating hours, urgent-fraud handling and response expectations; the mock ticket does not contact a real human.
- Establish approved model providers, data residency, retention, access controls, incident handling and monitoring. No legal/compliance certification is implied by the demo.
- Test representative anonymized customer queries, including paraphrases, mixed intents, language variants, false-positive handoffs and API outages.
- Review failed cases and a repeat-run sample; a passing seven-run synthetic cohort does not establish a production success rate. Have support specialists independently grade a held-out sample and validate the authored judge-reference labels.
- Use a persistent database appropriate to deployment. This demo supports one application instance with persistent SQLite; ephemeral serverless disk or unsynchronized replicas are not supported.
- Put hosted live mode behind HTTPS, demo admission and rate/spend limits. Never embed provider keys in the frontend.
- Roll out to a small supervised audience with a reversible disable switch. Saved replay can remain available while live inference is disabled.
