# Paylane demo frontend

The approved visual direction is A: Finance workspace. Keep the frontend in `frontend/`, separate from the independently runnable `backend/`. The frontend is an optional hosted demo; the backend is the core README and architecture deliverable. Use OpenRouter for model inference; credentials belong exclusively to the backend environment. Backend-first structure and provider choice supersede the earlier single-application/static-folder proposal. See `architecture.md` for the implemented architecture.

Purpose: let visitors understand, try, and inspect the support agent in minutes. This is the reviewer workspace for an demonstration, using synthetic customers and mock money movement. The customer-facing chat stays short and free of implementation detail; reviewer evidence is outside the chat.

## Reference selection

Source requested by Ayush: https://bestdesignsonx.com/websites

The public gallery data was read on October 17, 2026. Its finance collection includes Slash (site 106), Structured (149), Slush (139), Varo Bank (114), and Jeton (72). The metadata, original gallery preview links, and destination links are recorded in `design-references.json`.

Primary reference: [Slash](https://www.slash.com/), a finance/SaaS entry in the requested collection. Its live page and content were accessible. The gallery itself is client rendered; browsing returned an error, so its public gallery data was read instead. Structured's destination was unavailable. No claim is made that all gallery screenshots were visually reviewed.

Use the reference as inspiration for a finance product's confident hierarchy and product-first presentation. Create original Paylane layouts and assets. Do not reuse proprietary cards, photographs, logos, marketing claims, or source code. Visual details below are our proposed adaptation, rather than a description of screenshots we could not inspect.

## Visual direction

A quiet, light support workspace with a dark navigation rail and one expressive element: a large, typographic conversation heading. Most space belongs to the actual conversation. Use rows and panels according to function; avoid a dashboard filled with invented statistics.

Palette: Paper `#F6F8FB`, Surface `#FFFFFF`, Ink `#172536`, Muted `#526478`, Line `#DCE3EB`, Action `#2549D8`. Use text and icons alongside any status color. Reserve red for failures and amber for human review; label both explicitly.

Type: locally bundled, open-licensed Manrope for the interface, using 14/16/20/28/40px roles. Use tabular numerals for money and test results. Do not rely on a remote font request to make the submission readable.

Layout: left-aligned navigation and text. At desktop widths use a 200px navigation rail, a flexible conversation pane, and an evidence pane around 340px. Collapse evidence into an accessible disclosure below chat on narrow screens. At 375px, keep the composer, controls, and result rows inside the viewport.

```
+----------------+------------------------------+----------------------+
| Paylane        | Try the support agent        | Session              |
|                | Mock environment             | Identity: unverified |
| Playground     +------------------------------+----------------------+
| Scenarios      | Conversation                 | Tool activity        |
| Policy         |                              | Expandable events    |
|                |                              |                      |
|                +------------------------------+----------------------+
|                | Message input / Send         | Applicable policy    |
+----------------+------------------------------+----------------------+
```

Playground: a real chat, new-session action, optional scenario starter, explicit provider availability, and short synthetic-data instructions. Show a compact verification form when needed; also support the demonstration's ordinary conversation flow for email and last four. Form values are treated as customer-provided proof and are never prefilled silently.

Scenarios: twelve rows with title, intent, edge-case rationale, and status. Selecting a row shows its redacted transcript, tool events, and named assertions. Initial status is 'Not run'. Saved report viewing needs no API key. Replay does not perform a refund or count as a new evaluation.

Policy: readable rulebook with demonstration rules separated from conservative assumptions. Include the customer note and launch questions as downloadable submission documents, not extra navigation pages.

## Interaction and accessibility

Keyboard-operable navigation and event disclosures; visible focus; labeled fields; live announcements for replies; disabled duplicate sends while a request is in flight. Respect reduced motion. Preserve typed text on failure and offer retry guidance. A missing provider key produces a useful setup message; it never starts an undisclosed scripted agent. Do not put provider secrets in browser storage or HTTP responses.

## Design review

Removed a proposed marketing landing page because the reviewer needs to try the agent immediately. Removed generic performance charts because there is no production dataset. The dark rail is an orientation aid, and the blue accent identifies actions. Evidence occupies a separate pane because explaining a policy decision is the distinctive requirement of this demonstration.

## Verification

Browser checks at 1440px and 375px: complete one verified refund, inspect the confirmed mock tool result, reset session, select an escalation scenario, open its assertions, and inspect an unavailable-provider state. Check keyboard flow, no horizontal overflow, and reduced-motion behavior. Implemented screenshots are under `docs/screenshots/`; the browser suite and verification record the checks.
