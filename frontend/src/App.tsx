import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  MessageCircle,
  BookOpen,
  FlaskConical,
  Plus,
  Send,
  ShieldCheck,
  Check,
  ChevronDown,
  ChevronRight,
  ArrowUpRight,
  CircleHelp,
  CreditCard,
  Clock3,
  ReceiptText,
  UserRound,
  RotateCcw,
  Download,
  LockKeyhole,
  AlertCircle,
  ExternalLink,
  Braces,
} from "lucide-react";

type Event = {
  tool: string;
  phase: string;
  origin?: string;
  reason?: string;
  result?: Record<string, unknown>;
  arguments?: unknown;
};
type Guardrail = {
  layer: string;
  rule: string;
  action: string;
  reason: string;
};
type Result = {
  text: string;
  outcome: string;
  verified: boolean;
  events: Event[];
  guardrails?: Guardrail[];
  error?: string;
  latency_ms?: number;
};
type Message = { role: "user" | "assistant"; text: string; result?: Result };
type Case = {
  id: string;
  title: string;
  why: string;
  messages: string[];
  expect: Record<string, unknown>;
};
type Run = {
  id: string;
  title: string;
  why: string;
  passed: boolean;
  checks: { name: string; passed: boolean; reason: string }[];
  metrics: {
    name: string;
    score?: number;
    passed: boolean;
    reason?: string;
    error?: string;
    kind?: string;
  }[];
  transcript: { user: string; result: Result }[];
};
type Report = {
  cases: Run[];
  score?: {
    passed: number;
    total: number;
    hard_checks_passed: number;
    hard_checks_total: number;
    evaluation_errors: number;
  };
  provenance?: { agent_model: string; judge_model: string; run_at: string };
};
type View = "playground" | "scenarios" | "policy";
const mask = (s: string) =>
  s
    .replace(/[\w.+-]+@[\w.-]+\.[a-z]{2,}/gi, "[email redacted]")
    .replace(/\b(?:\d[ -]?){12,18}\d\b/g, "[card redacted]")
    .replace(/(?<![\w-])\d{4}(?![\w-])/g, "[last four redacted]");
const csrf = () =>
  decodeURIComponent(
    document.cookie
      .split("; ")
      .find((x) => x.startsWith("paylane_csrf="))
      ?.split("=")[1] || "",
  );
async function api(path: string, body?: unknown) {
  const r = await fetch("/api" + path, {
    credentials: "same-origin",
    ...(body !== undefined
      ? {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf(),
          },
          body: JSON.stringify(body),
        }
      : {}),
  });
  const data = await r.json();
  if (!r.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : `Request failed (${r.status}).`,
    );
  return data;
}
function Mark() {
  return (
    <svg
      width="35"
      height="39"
      viewBox="0 0 35 39"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M5 3h14a12 12 0 0 1 0 24H13v9H5V19h14a4 4 0 0 0 0-8H5z"
        fill="#3A70FF"
      />
      <path d="M5 3h14a12 12 0 0 1 11.5 8H5z" fill="#7697FF" />
      <path d="M5 19h14v8h-6v9H5z" fill="#2254CF" />
    </svg>
  );
}
function Badge({
  children,
  kind = "neutral",
}: {
  children: ReactNode;
  kind?: string;
}) {
  return <span className={"badge " + kind}>{children}</span>;
}
function ToolActivity({ events }: { events: Event[] }) {
  const visible = events.filter((e) =>
    ["executed", "blocked", "verified", "failed"].includes(e.phase),
  );
  if (!visible.length)
    return (
      <div className="empty-trace">
        <div className="trace-symbol">
          <Braces size={25} />
        </div>
        <strong>No tools called yet.</strong>
        <p>
          As you chat, see what the agent checks and which actions it takes.
        </p>
      </div>
    );
  const titles: Record<string, string> = {
    verification: "Identity check",
    get_customer: "Customer checked",
    get_transaction: "Transaction checked",
    issue_refund: "Refund request",
    escalate_to_human: "Human handoff",
    response: "Response validation",
  };
  return (
    <div className="trace-list">
      {visible.map((e, i) => (
        <details
          className={
            "trace-step " +
            (e.phase === "blocked" || e.phase === "failed" ? "blocked" : "")
          }
          key={i}
        >
          <summary>
            <span className="step-icon">
              {e.phase === "blocked" || e.phase === "failed" ? (
                <AlertCircle size={16} />
              ) : (
                <Check size={16} />
              )}
            </span>
            <span>
              <strong>{titles[e.tool] || e.tool}</strong>
              <small>
                {e.phase === "blocked"
                  ? "Blocked · " + e.reason
                  : e.phase === "verified"
                    ? "Both details confirmed"
                    : e.phase === "executed"
                      ? "Mock API returned a result"
                      : e.phase}
              </small>
            </span>
            <ChevronDown size={14} />
          </summary>
          <div className="event-body">
            <span className="event-origin">Source: {e.origin || "model"}</span>
            <pre>{JSON.stringify(e, null, 2)}</pre>
          </div>
        </details>
      ))}
    </div>
  );
}
export default function App() {
  const [view, setView] = useState<View>("playground");
  const [session, setSession] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [health, setHealth] = useState<{
    live_available: boolean;
    admitted: boolean;
    hosted: boolean;
    model: string;
  } | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [report, setReport] = useState<Report>({ cases: [] });
  const [selected, setSelected] = useState("C01");
  const [policy, setPolicy] = useState("");
  const [invite, setInvite] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const pending = useRef<{
    sid: string;
    text: string;
    request_id: string;
  } | null>(null);
  useEffect(() => {
    let active = true;
    Promise.all([
      api("/health"),
      api("/scenarios"),
      api("/reports/latest"),
      api("/policy"),
    ])
      .then(([h, c, r, p]) => {
        if (active) {
          setHealth(h);
          setCases(c.cases);
          setReport(r);
          setPolicy(p.text);
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [messages, busy]);
  const guardrails = messages.flatMap((m) => m.result?.guardrails || []);
  const events = messages.flatMap((m) => m.result?.events || []);
  const verified =
    messages.filter((m) => m.result).at(-1)?.result?.verified ?? false;
  const activeCase = cases.find((c) => c.id === selected);
  const activeRun = report.cases.find((c) => c.id === selected);
  async function newSession() {
    if (busy) return;
    try {
      const s = await api("/sessions", {});
      setSession(s.session_id);
      pending.current = null;
      setMessages([]);
      setError("");
      setDraft("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!draft.trim() || busy) return;
    const text = draft;
    setDraft("");
    setBusy(true);
    setError("");
    try {
      let sid = session;
      if (!sid) {
        sid = (await api("/sessions", {})).session_id;
        setSession(sid);
      }
      let result: Result | undefined;
      const retry =
        pending.current?.sid === sid && pending.current.text === text;
      if (retry) {
        try {
          const prior = await api(
            `/sessions/${sid}/requests/${pending.current!.request_id}`,
          );
          if (prior.status === "completed") result = prior.result;
        } catch {
          /* Same request ID safely covers a request that never reached the server. */
        }
      } else {
        pending.current = { sid, text, request_id: crypto.randomUUID() };
        setMessages((m) => [...m, { role: "user", text: mask(text) }]);
      }
      if (!result)
        result = await api(`/sessions/${sid}/messages`, {
          request_id: pending.current!.request_id,
          message: text,
        });
      pending.current = null;
      const completed = result!;
      setMessages((m) => [
        ...m,
        { role: "assistant", text: completed.text, result: completed },
      ]);
      if (completed.error)
        setError(
          "The request encountered a service issue. Any confirmed action shown above is preserved.",
        );
    } catch (e) {
      setDraft(text);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function login(event: FormEvent) {
    event.preventDefault();
    try {
      await api("/login", { invite });
      setHealth(await api("/health"));
      setInvite("");
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function starter(c?: Case) {
    setView("playground");
    setDraft(
      c?.messages[0] ||
        "Please refund TXN-1042. My email is alex@example.test and my card last four are 4242.",
    );
  }
  const modelLabel =
    health?.model?.split("/").pop()?.replaceAll("-", " ") ||
    "Agent configuration";
  return (
    <div className="app-shell">
      <aside className="rail">
        <a className="brand" href="/" aria-label="Paylane home">
          <Mark />
          <span>paylane</span>
        </a>
        <div className="rail-caption">Support workspace</div>
        <nav aria-label="Main navigation">
          {(
            [
              { key: "playground", label: "Playground", icon: MessageCircle },
              { key: "scenarios", label: "Scenarios", icon: FlaskConical },
              { key: "policy", label: "Policy", icon: BookOpen },
            ] as const
          ).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              aria-current={view === key ? "page" : undefined}
              className={view === key ? "active" : ""}
              onClick={() => setView(key)}
            >
              <Icon size={20} />
              {label}
              {view === key && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="rail-bottom">
          <div className="rail-note">
            <ShieldCheck size={18} />
            <span>
              Built with boundaries.<small>Mock APIs. Real decisions.</small>
            </span>
          </div>
          <div className="author">
            <span className="author-avatar">AG</span>
            <span>
              Built by Ayush<small>Policy-enforced AI support</small>
            </span>
            <ArrowUpRight size={15} />
          </div>
        </div>
      </aside>
      <main className="workspace">
        <div className="topline">
          <div>
            Workspace <ChevronRight size={13} />
            <strong>
              {view === "playground"
                ? "Playground"
                : view === "scenarios"
                  ? "Scenarios"
                  : "Policy"}
            </strong>
          </div>
          <Badge kind="environment">
            <span className="dot" />
            Mock environment
          </Badge>
        </div>
        <header className="page-heading">
          <div>
            <h1>
              {view === "playground"
                ? "A little help. A clear answer."
                : view === "scenarios"
                  ? "Twelve conversations. Every decision visible."
                  : "Clear rules. Consistent decisions."}
            </h1>
            <p>
              {view === "playground"
                ? "Try the agent. Follow the decisions behind the conversation."
                : view === "scenarios"
                  ? "Real model runs, explicit checks, and the complete conversation."
                  : "The policy the agent follows, including the assumptions we made."}
            </p>
          </div>
          {view === "playground" && (
            <button
              className="button primary"
              onClick={newSession}
              disabled={busy}
            >
              <Plus size={17} />
              New conversation
            </button>
          )}
        </header>
        {error && (
          <div className="error-banner" role="alert">
            <AlertCircle size={17} />
            <span>{error.replaceAll("_", " ")}</span>
            <button onClick={() => setError("")} aria-label="Dismiss error">
              ×
            </button>
          </div>
        )}
        <div className="work-grid">
          <section className="primary-pane">
            {view === "playground" ? (
              <div className="chat-panel">
                <div className="chat-heading">
                  <div className="agent-avatar">
                    <MessageCircle size={21} />
                  </div>
                  <div>
                    <h2>Paylane support</h2>
                    <p>Cards, transfers & refunds</p>
                  </div>
                  <Badge kind={verified ? "success" : "neutral"}>
                    {verified ? (
                      <>
                        <ShieldCheck size={12} />
                        Identity verified
                      </>
                    ) : (
                      <>
                        <LockKeyhole size={12} />
                        Not verified
                      </>
                    )}
                  </Badge>
                </div>
                <div
                  className="conversation"
                  role="log"
                  aria-label="Conversation"
                  aria-live="polite"
                >
                  {!messages.length && (
                    <div className="welcome">
                      <div className="welcome-mark">
                        <Mark />
                      </div>
                      <h2>What can we help you with?</h2>
                      <p>
                        Start with a question about a card or payment.
                        <br />
                        The agent will ask for any details it needs.
                      </p>
                      <div className="starter-options">
                        <button onClick={() => starter()}>
                          <ReceiptText size={18} />
                          <span>
                            Try a payment refund
                            <small>Use a synthetic customer example</small>
                          </span>
                          <ArrowUpRight size={15} />
                        </button>
                        <button
                          onClick={() =>
                            setDraft("My card is frozen. Can you help?")
                          }
                        >
                          <CreditCard size={18} />
                          <span>
                            Get help with a frozen card
                            <small>See when a person takes over</small>
                          </span>
                          <ArrowUpRight size={15} />
                        </button>
                      </div>
                      <p className="welcome-footnote">
                        <ShieldCheck size={13} />
                        Account details stay protected until verification.
                      </p>
                    </div>
                  )}
                  {messages.map((m, i) => (
                    <div key={i} className={"message " + m.role}>
                      <div className={"message-avatar " + m.role}>
                        {m.role === "assistant" ? (
                          <MessageCircle size={16} />
                        ) : (
                          <UserRound size={16} />
                        )}
                      </div>
                      <div className="message-content">
                        <div className="bubble">{m.text}</div>
                        {m.result?.outcome === "refund_confirmed" && (
                          <div className="receipt">
                            <span className="receipt-check">
                              <Check size={17} />
                            </span>
                            <div>
                              <strong>Mock refund confirmed</strong>
                              <small>
                                Confirmed by the backend refund ledger.
                              </small>
                            </div>
                          </div>
                        )}
                        <small className="speaker">
                          {m.role === "user" ? "You" : "Paylane"}
                          {m.result?.latency_ms
                            ? ` · ${(m.result.latency_ms / 1000).toFixed(1)}s`
                            : ""}
                        </small>
                      </div>
                    </div>
                  ))}
                  {busy && (
                    <div className="thinking" role="status">
                      <span className="thinking-dot" />
                      Checking the request and applicable policy…
                    </div>
                  )}
                  <div ref={end} />
                </div>
                {health?.hosted && !health.admitted ? (
                  <form className="admission" onSubmit={login}>
                    <LockKeyhole size={18} />
                    <label htmlFor="invite">
                      Enter the demo invite to try the live agent.
                    </label>
                    <div>
                      <input
                        id="invite"
                        type="password"
                        value={invite}
                        onChange={(e) => setInvite(e.target.value)}
                        autoComplete="off"
                        required
                      />
                      <button className="button primary">Unlock demo</button>
                    </div>
                  </form>
                ) : (
                  <form className="composer" onSubmit={send}>
                    <div className="input-row">
                      <label className="sr-only" htmlFor="message">
                        Message
                      </label>
                      <textarea
                        id="message"
                        placeholder="Write a message…"
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        rows={1}
                        maxLength={4000}
                        disabled={busy || !health?.live_available}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            e.currentTarget.form?.requestSubmit();
                          }
                        }}
                      />
                      <button
                        className="button primary send"
                        disabled={
                          busy || !draft.trim() || !health?.live_available
                        }
                      >
                        <Send size={16} />
                        <span>Send</span>
                      </button>
                    </div>
                    <div className="composer-note">
                      <span>
                        <ShieldCheck size={12} />
                        Synthetic data. No real money moves.
                      </span>
                      <span>Enter to send</span>
                    </div>
                    {health && !health.live_available && (
                      <p className="setup-note">
                        Configure OPENROUTER_API_KEY in the backend environment
                        to enable live chat. Saved scenarios remain available.
                      </p>
                    )}
                  </form>
                )}
              </div>
            ) : view === "scenarios" ? (
              <div className="scenario-layout">
                <div className="case-library">
                  <div className="library-heading">
                    <h2>Scenario library</h2>
                    <Badge>12 cases</Badge>
                  </div>
                  {cases.map((c) => {
                    const run = report.cases.find((r) => r.id === c.id);
                    return (
                      <button
                        key={c.id}
                        data-case={c.id}
                        className={
                          "case-row " + (selected === c.id ? "selected" : "")
                        }
                        onClick={() => setSelected(c.id)}
                      >
                        <span className="case-id">{c.id.slice(1)}</span>
                        <span>
                          <strong>{c.title}</strong>
                          <small>
                            {run
                              ? run.passed
                                ? "Passed"
                                : "Needs attention"
                              : "Not run"}
                          </small>
                        </span>
                        <ChevronRight size={14} />
                      </button>
                    );
                  })}
                </div>
                <div className="case-detail">
                  <div className="case-detail-heading">
                    <Badge kind="replay">Saved replay</Badge>
                    <h2>{activeCase?.title}</h2>
                    <p>{activeCase?.why}</p>
                    <button
                      className="button secondary"
                      onClick={() => starter(activeCase)}
                    >
                      <RotateCcw size={14} />
                      Try this request live
                    </button>
                  </div>
                  {activeRun?.transcript?.length ? (
                    activeRun.transcript.map((t, i) => (
                      <div key={i} className="replay-turn">
                        <span>Customer</span>
                        <p>{t.user}</p>
                        <span>Paylane</span>
                        <p className="replay-answer">{t.result.text}</p>
                        <details>
                          <summary>
                            Inspect tool activity <ChevronDown size={13} />
                          </summary>
                          <pre>{JSON.stringify(t.result.events, null, 2)}</pre>
                        </details>
                      </div>
                    ))
                  ) : (
                    <div className="not-run">
                      <CircleHelp size={24} />
                      <h3>No saved run yet.</h3>
                      <p>
                        Run the backend evaluation to generate actual
                        transcripts and checks.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <article className="policy-panel">
                <div className="policy-heading">
                  <BookOpen size={23} />
                  <div>
                    <h2>Paylane rulebook</h2>
                    <p>Source: backend/prompts/rulebook.md</p>
                  </div>
                  <Badge>v1</Badge>
                </div>
                <div className="policy-text">
                  {policy
                    .split("\n")
                    .filter(Boolean)
                    .map((line, i) =>
                      line.startsWith("# ") ? (
                        <h3 key={i}>{line.slice(2)}</h3>
                      ) : line.startsWith("- ") ? (
                        <p className="policy-rule" key={i}>
                          <Check size={14} />
                          <span>{line.slice(2)}</span>
                        </p>
                      ) : (
                        <p key={i}>{line}</p>
                      ),
                    )}
                </div>
              </article>
            )}
          </section>
          <aside className="inspector" aria-label="Decision evidence">
            {view === "playground" ? (
              <>
                <section className="evidence-panel">
                  <h2>
                    <BookOpen size={19} />
                    Behind the conversation
                  </h2>
                  <p className="panel-subtitle">Actual tool activity</p>
                  <ToolActivity events={events} />
                  {guardrails.length > 0 && (
                    <details className="guardrail-details">
                      <summary>
                        Guardrail decisions ({guardrails.length})
                      </summary>
                      <pre>{JSON.stringify(guardrails, null, 2)}</pre>
                    </details>
                  )}
                </section>
                <section className="rules-panel">
                  <h2>
                    <ShieldCheck size={19} />
                    Refund rules
                  </h2>
                  <div className="rule">
                    <span className="rule-icon">
                      <UserRound size={17} />
                    </span>
                    <div>
                      <strong>Verified customer</strong>
                      <p>Email and card last four confirmed</p>
                    </div>
                  </div>
                  <div className="rule">
                    <span className="rule-icon">
                      <Clock3 size={17} />
                    </span>
                    <div>
                      <strong>Under 30 days</strong>
                      <p>Exactly 30 days needs human review</p>
                    </div>
                  </div>
                  <div className="rule">
                    <span className="rule-icon">
                      <CreditCard size={17} />
                    </span>
                    <div>
                      <strong>$75 or less</strong>
                      <p>Original payment, refunded once</p>
                    </div>
                  </div>
                  <button
                    className="text-link"
                    onClick={() => setView("policy")}
                  >
                    <BookOpen size={16} />
                    View rulebook
                    <ArrowUpRight size={14} />
                  </button>
                </section>
                <div className="model-note">
                  <span
                    className={"dot " + (health?.live_available ? "ready" : "")}
                  />
                  <div>
                    {health?.live_available
                      ? "Model connected"
                      : "Model not configured"}
                    <small>{modelLabel}</small>
                  </div>
                </div>
              </>
            ) : view === "scenarios" ? (
              <>
                <section className="evidence-panel">
                  <h2>
                    <FlaskConical size={19} />
                    Evaluation evidence
                  </h2>
                  {report.score ? (
                    <div className="score">
                      <strong>
                        {report.score.passed}
                        <span> / {report.score.total}</span>
                      </strong>
                      <p>conversations passed</p>
                      <small>
                        {report.score.hard_checks_passed}/
                        {report.score.hard_checks_total} hard assertions ·{" "}
                        {report.score.evaluation_errors} judge errors
                      </small>
                    </div>
                  ) : (
                    <p className="panel-subtitle">Evaluation not run yet.</p>
                  )}
                  <div className="checks">
                    {activeRun?.checks?.map((c) => (
                      <div
                        key={c.name}
                        className={
                          "check-row " + (c.passed ? "passed" : "failed")
                        }
                      >
                        <span>
                          {c.passed ? (
                            <Check size={13} />
                          ) : (
                            <AlertCircle size={13} />
                          )}
                        </span>
                        <p>{c.name.replaceAll("_", " ")}</p>
                      </div>
                    ))}
                  </div>
                  {activeRun?.metrics?.map((m) => (
                    <div className="metric" key={m.name}>
                      <strong>{m.name}</strong>
                      <Badge kind={m.passed ? "success" : "warning"}>
                        {m.score !== undefined
                          ? Math.round(m.score * 100) + "%"
                          : m.error ||
                            (m.kind === "not_applicable" ||
                            m.kind === "routing_observation"
                              ? "N/A"
                              : "Error")}
                      </Badge>
                      {m.reason && <p>{m.reason}</p>}
                    </div>
                  ))}
                </section>
                <section className="rules-panel downloads">
                  <h2>
                    <Download size={18} />
                    Take a closer look
                  </h2>
                  <a href="/api/reports/download/transcripts" download>
                    Customer transcripts
                    <ArrowUpRight size={14} />
                  </a>
                  <a href="/api/reports/download/evaluation" download>
                    Evaluation report
                    <ArrowUpRight size={14} />
                  </a>
                  <a href="/api/reports/download/json" download>
                    Machine-readable results
                    <ArrowUpRight size={14} />
                  </a>
                  <a href="/api/reports/download/reliability" download>
                    Repeated reliability report
                    <ArrowUpRight size={14} />
                  </a>
                  <p>
                    Replays show saved evidence. They do not call the model or
                    move money.
                  </p>
                </section>
              </>
            ) : (
              <section className="rules-panel">
                <h2>
                  <CircleHelp size={19} />
                  Built to hand off
                </h2>
                <p className="policy-aside">
                  Legal action, account closure, suspected fraud, frozen-card
                  requests, and refunds outside policy go to a person.
                </p>
                <div className="aside-note">
                  <LockKeyhole size={17} />
                  <p>
                    The model can request an action. Backend code decides
                    whether it is allowed.
                  </p>
                </div>
                <button
                  className="text-link"
                  onClick={() => setView("playground")}
                >
                  Try the agent
                  <ArrowUpRight size={14} />
                </button>
              </section>
            )}
          </aside>
        </div>
        <footer className="workspace-footer">
          <span>
            Paylane support agent <span className="footer-dot">·</span> An
            engineering demonstration
          </span>
          <span>
            LangGraph <span className="footer-dot">/</span> Pydantic{" "}
            <span className="footer-dot">/</span> DeepEval
          </span>
        </footer>
      </main>
    </div>
  );
}
