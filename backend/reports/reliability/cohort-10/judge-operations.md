# Judge transport and cost observations

Judge overhead is outside the customer request path. Latency is per SDK attempt, with gate waiting separated; it is not whole-cohort or conversation elapsed time. Costs include only reported completed-call values. A transport exception can leave unknown provider-side usage; unknown is not zero. Provider fallback stays within the same judge model. This is a derived aggregate of original recorded events; no scores or trials were changed.

Logical ratings: **840**. Recorded SDK requests: **840**. Final response dispositions: `{'accepted': 840}`.

Known judge cost sum: **$0.337335** across 280/280 panels with reported completed-response cost.

| Timing per SDK request | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|
| gate_wait_ms | 1396.5 | 8490.9 | 14642.6 |
| sdk_latency_ms | 3345.5 | 17079.5 | 23944.8 |
| latency_ms | 5371.0 | 19985.5 | 28957.2 |

[Full derived aggregate](judge-operations.json). Original attempts and costs remain in per-trial JSON.
