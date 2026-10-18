# Guidebook practices applied to Paylane

Reference read: Ayush's local *AI Engineering: System Design Patterns for LLMs, RAG and Agents*, 2025 edition, Akshay Pachaar and Avi Chawla. The PDF is not copied into this repository. Page references below use the printed page number (the PDF page is one greater). This is a focused review of relevant chapters, not a claim to have read every page.

| Relevant material | Application in this repository | Evidence / remaining limit |
|---|---|---|
| Context engineering, pp.147–151 | Trusted session facts, narrow dynamic tool availability, concise typed tool errors, separate policy and user data | Gateway/context tests; model context does not grant authority |
| Agent building blocks, pp.181–187 | Narrow support role, exactly four tools, Pydantic arguments, explicit guardrails and persistent conversation state | LangGraph service and atomic SQLite ledger; additional agents/tools would add no necessary support capability |
| Multi-turn evaluation, pp.337–340 | Whole-dialogue DeepEval grading, explicit per-turn effects and policy checks | Twelve original conversations and adversarial multi-turn grooming/replay cases |
| Component evaluations, pp.348–351 | Separate risk-classifier/model/tool/renderer events, logical latency/attempt metadata and guardrail decisions | Local redacted traces; no automatic raw-prompt export to a third-party dashboard |
| Red teaming, pp.352–357 | Explicit direct/indirect injection, role/tool spoofing, obfuscation, data leaks, excessive agency, replay and resource-abuse scenarios | 24 attack cases repeated seven times; fixed suite is reproducible but not exhaustive/adaptive penetration testing |
| Deployment patterns, pp.260–263 | Real-time API over one shared backend and persistent state | No unnecessary batch/stream/edge architecture or new MCP server |
| Deployment constraints, pp.359–360 | Bounded calls, retries, deadlines, admission and cost/latency reporting | OpenRouter provides inference; no self-hosted GPU engine is needed for this demonstration |
| Evaluation vs observability, pp.371–373 | Frozen offline cohorts plus runtime structured events and operational aggregates | Hosted alerts, external monitoring and production incident ownership still require deployment configuration |

The guidebook illustrates tools such as Opik and DeepTeam. Its underlying practices are applied while retaining the user's chosen LangGraph/Pydantic/DeepEval stack. A tool illustration is not a requirement to add another framework, and an automatic optimizer must not silently change prompts during a measured cohort. Guardrails are enforced in trusted code; model instructions alone are not the authorization boundary.

Repeated reliability methodology extends this reference with pass@k/pass^k, immutable cohorts, finite-sample intervals, strict error accounting and a seven-success-per-case release gate. The definitions and assumptions are documented in the reliability reports. Actual results are linked from the README and final cohort artifacts.
