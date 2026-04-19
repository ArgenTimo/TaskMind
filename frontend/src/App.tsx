import { type FormEvent, useState } from "react";

import "./App.css";

type Mode = "analyze" | "reply" | "extract_tasks";

type Result = {
  summary: string;
  intent: string;
  reply: string;
  tasks: string[];
};

type BatchItemSuccess = { success: true; result: Result };
type BatchItemFailure = {
  success: false;
  error: { status_code: number; detail: string };
};
type BatchResponse = { items: (BatchItemSuccess | BatchItemFailure)[] };

type OpResultStatus = "idle" | "ok" | "error" | "partial";

type LastRun = {
  interaction: "single" | "batch" | null;
  httpStatus: number | null;
  requestId: string | null;
  latencyMs: number | null;
  resultStatus: OpResultStatus;
  rawJson: string | null;
  batchLine: string | null;
};

const apiBase =
  import.meta.env.VITE_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

const BATCH_PLACEHOLDER = JSON.stringify(
  {
    items: [
      { text: "Hello world", mode: "analyze" },
      { text: "- First action\n- Second action", mode: "extract_tasks" },
    ],
  },
  null,
  2,
);

const INITIAL_LAST: LastRun = {
  interaction: null,
  httpStatus: null,
  requestId: null,
  latencyMs: null,
  resultStatus: "idle",
  rawJson: null,
  batchLine: null,
};

function batchStats(data: BatchResponse): { ok: number; fail: number; line: string } {
  let ok = 0;
  let fail = 0;
  for (const it of data.items) {
    if (it.success) {
      ok += 1;
    } else {
      fail += 1;
    }
  }
  const n = data.items.length;
  const line =
    fail === 0 ? `${n} item(s), all succeeded` : `${n} item(s), ${ok} ok · ${fail} failed`;
  return { ok, fail, line };
}

async function parseHttpErrorBody(res: Response, bodyText: string): Promise<string> {
  try {
    const j = JSON.parse(bodyText) as { detail?: unknown };
    if (j.detail !== undefined) {
      return typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    }
  } catch {
    /* ignore */
  }
  return bodyText || `${res.status} ${res.statusText}`;
}

export default function App() {
  const [panel, setPanel] = useState<"single" | "batch">("single");

  const [text, setText] = useState("");
  const [mode, setMode] = useState<Mode>("analyze");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);

  const [batchBody, setBatchBody] = useState(BATCH_PLACEHOLDER);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [batchResult, setBatchResult] = useState<BatchResponse | null>(null);

  const [lastRun, setLastRun] = useState<LastRun>(INITIAL_LAST);
  const [showRawJson, setShowRawJson] = useState(true);

  function switchPanel(next: "single" | "batch") {
    setPanel(next);
    setError(null);
    setBatchError(null);
  }

  async function onSubmitSingle(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const t0 = performance.now();
    try {
      const res = await fetch(`${apiBase}/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, mode }),
      });
      const latencyMs = Math.round(performance.now() - t0);
      const requestId = res.headers.get("x-request-id");
      const bodyText = await res.text();

      if (!res.ok) {
        const msg = await parseHttpErrorBody(res, bodyText);
        setLastRun({
          interaction: "single",
          httpStatus: res.status,
          requestId,
          latencyMs,
          resultStatus: "error",
          rawJson: bodyText.trim() || msg,
          batchLine: null,
        });
        setResult(null);
        throw new Error(msg);
      }

      let data: Result;
      try {
        data = JSON.parse(bodyText) as Result;
      } catch {
        setLastRun({
          interaction: "single",
          httpStatus: res.status,
          requestId,
          latencyMs,
          resultStatus: "error",
          rawJson: bodyText,
          batchLine: null,
        });
        setResult(null);
        throw new Error("Response was not valid JSON");
      }
      setResult(data);
      setBatchResult(null);
      setLastRun({
        interaction: "single",
        httpStatus: res.status,
        requestId,
        latencyMs,
        resultStatus: "ok",
        rawJson: bodyText,
        batchLine: null,
      });
    } catch (err) {
      setResult(null);
      const latencyMs = Math.round(performance.now() - t0);
      if (err instanceof TypeError) {
        setLastRun({
          interaction: "single",
          httpStatus: null,
          requestId: null,
          latencyMs,
          resultStatus: "error",
          rawJson: `Network error: ${err.message}`,
          batchLine: null,
        });
      }
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function onSubmitBatch(e: FormEvent) {
    e.preventDefault();
    setBatchLoading(true);
    setBatchError(null);
    const t0 = performance.now();
    try {
      let parsed: unknown;
      try {
        parsed = JSON.parse(batchBody) as unknown;
      } catch {
        const latencyMs = Math.round(performance.now() - t0);
        setLastRun({
          interaction: "batch",
          httpStatus: null,
          requestId: null,
          latencyMs,
          resultStatus: "error",
          rawJson: "Invalid JSON — check commas and quotes.",
          batchLine: null,
        });
        setBatchError("Invalid JSON — check commas and quotes.");
        return;
      }
      if (
        typeof parsed !== "object" ||
        parsed === null ||
        !("items" in parsed) ||
        !Array.isArray((parsed as { items: unknown }).items)
      ) {
        const latencyMs = Math.round(performance.now() - t0);
        setLastRun({
          interaction: "batch",
          httpStatus: null,
          requestId: null,
          latencyMs,
          resultStatus: "error",
          rawJson: 'Body must be a JSON object with an "items" array.',
          batchLine: null,
        });
        throw new Error('Body must be a JSON object with an "items" array.');
      }
      const res = await fetch(`${apiBase}/process_batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed),
      });
      const latencyMs = Math.round(performance.now() - t0);
      const requestId = res.headers.get("x-request-id");
      const bodyText = await res.text();

      if (!res.ok) {
        const msg = await parseHttpErrorBody(res, bodyText);
        setLastRun({
          interaction: "batch",
          httpStatus: res.status,
          requestId,
          latencyMs,
          resultStatus: "error",
          rawJson: bodyText.trim() || msg,
          batchLine: null,
        });
        setBatchResult(null);
        throw new Error(msg);
      }

      let data: BatchResponse;
      try {
        data = JSON.parse(bodyText) as BatchResponse;
      } catch {
        setLastRun({
          interaction: "batch",
          httpStatus: res.status,
          requestId,
          latencyMs,
          resultStatus: "error",
          rawJson: bodyText,
          batchLine: null,
        });
        setBatchResult(null);
        throw new Error("Response was not valid JSON");
      }
      setBatchResult(data);
      setResult(null);
      const { line } = batchStats(data);
      const st: OpResultStatus = line.includes("failed") ? "partial" : "ok";
      setLastRun({
        interaction: "batch",
        httpStatus: res.status,
        requestId,
        latencyMs,
        resultStatus: st,
        rawJson: bodyText,
        batchLine: line,
      });
    } catch (err) {
      setBatchResult(null);
      const latencyMs = Math.round(performance.now() - t0);
      if (err instanceof TypeError) {
        setLastRun({
          interaction: "batch",
          httpStatus: null,
          requestId: null,
          latencyMs,
          resultStatus: "error",
          rawJson: `Network error: ${err.message}`,
          batchLine: null,
        });
        setBatchError(err.message);
      } else {
        setBatchError(err instanceof Error ? err.message : "Request failed");
      }
    } finally {
      setBatchLoading(false);
    }
  }

  const statusLabel =
    lastRun.resultStatus === "idle"
      ? "—"
      : lastRun.resultStatus === "ok"
        ? "Success"
        : lastRun.resultStatus === "partial"
          ? "Partial (batch)"
          : "Error";

  return (
    <div className="app-shell">
      <main className="app-main">
        <header className="app-header">
          <h1 className="app-title">
            Task<span>Mind</span>
          </h1>
          <p className="app-subtitle">
            Operator console — run single or batch requests against the TaskMind API. Diagnostics on
            the right update from the last completed call (client-side timing + response headers
            when exposed).
          </p>
        </header>

        <div className="panel-toggle" role="group" aria-label="Request type">
          <button
            type="button"
            aria-pressed={panel === "single"}
            onClick={() => switchPanel("single")}
          >
            Single
          </button>
          <button
            type="button"
            aria-pressed={panel === "batch"}
            onClick={() => switchPanel("batch")}
          >
            Batch
          </button>
        </div>

        {panel === "single" && (
          <form className="card" onSubmit={onSubmitSingle} aria-busy={loading}>
            <div className="field">
              <label className="card__label" htmlFor="input-text">
                Input
              </label>
              <textarea
                id="input-text"
                className="textarea"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Message to process…"
                rows={7}
                required
              />
            </div>
            <div className="field">
              <div className="card__label">Process mode</div>
              <div className="select-wrap">
                <label htmlFor="mode-select" className="sr-only">
                  Mode
                </label>
                <select
                  id="mode-select"
                  value={mode}
                  onChange={(e) => setMode(e.target.value as Mode)}
                >
                  <option value="analyze">Analyze</option>
                  <option value="reply">Reply</option>
                  <option value="extract_tasks">Extract tasks</option>
                </select>
              </div>
              <p className="hint">Maps to <code>mode</code> in <code>POST /process</code>.</p>
            </div>
            <div className="actions">
              <button
                type="submit"
                className="btn btn--primary"
                disabled={loading || !text.trim()}
              >
                {loading && <span className="btn__spinner" aria-hidden />}
                {loading ? "Running…" : "Run"}
              </button>
            </div>
          </form>
        )}

        {panel === "batch" && (
          <form className="card" onSubmit={onSubmitBatch} aria-busy={batchLoading}>
            <div className="field">
              <label className="card__label" htmlFor="batch-json">
                Batch body (JSON)
              </label>
              <textarea
                id="batch-json"
                className="textarea textarea--mono"
                value={batchBody}
                onChange={(e) => setBatchBody(e.target.value)}
                spellCheck={false}
              />
              <p className="hint">
                Sent as the body of <code>POST /process_batch</code>. HTTP 200 with per-item
                outcomes.
              </p>
            </div>
            <div className="actions">
              <button type="submit" className="btn btn--primary" disabled={batchLoading}>
                {batchLoading && <span className="btn__spinner" aria-hidden />}
                {batchLoading ? "Running…" : "Run batch"}
              </button>
            </div>
          </form>
        )}

        {panel === "single" && error && (
          <div className="alert" role="alert">
            {error}
          </div>
        )}

        {panel === "batch" && batchError && (
          <div className="alert" role="alert">
            {batchError}
          </div>
        )}

        {panel === "single" && result && (
          <section className="results" aria-label="Result">
            <h2 className="results__heading">Structured result</h2>
            <div className="card result-block">
              <h3 className="result-block__title">Summary</h3>
              <p className="result-block__body">{result.summary}</p>
            </div>
            <div className="card result-block">
              <h3 className="result-block__title">Intent</h3>
              <p className="result-block__body">{result.intent}</p>
            </div>
            <div className="card result-block">
              <h3 className="result-block__title">Reply</h3>
              <p className="result-block__body">{result.reply}</p>
            </div>
            <div className="card result-block">
              <h3 className="result-block__title">Tasks</h3>
              <ul className="task-list">
                {result.tasks.map((t, i) => (
                  <li key={`${i}-${t.slice(0, 24)}`}>{t}</li>
                ))}
              </ul>
            </div>
          </section>
        )}

        {panel === "batch" && batchResult && (
          <section className="results" aria-label="Batch results">
            <h2 className="results__heading">Per-item results</h2>
            {batchResult.items.map((item, i) => (
              <div
                key={i}
                className={`batch-item ${item.success ? "batch-item--ok" : "batch-item--fail"}`}
              >
                <div className="batch-item__meta">
                  #{i + 1} · {item.success ? "OK" : `HTTP-style ${item.error.status_code}`}
                </div>
                {item.success ? (
                  <>
                    <div className="result-block">
                      <h3 className="result-block__title">Summary</h3>
                      <p className="result-block__body">{item.result.summary}</p>
                    </div>
                    <div className="result-block">
                      <h3 className="result-block__title">Intent</h3>
                      <p className="result-block__body">{item.result.intent}</p>
                    </div>
                    <div className="result-block">
                      <h3 className="result-block__title">Reply</h3>
                      <p className="result-block__body">{item.result.reply}</p>
                    </div>
                    <div className="result-block">
                      <h3 className="result-block__title">Tasks</h3>
                      <ul className="task-list">
                        {item.result.tasks.map((t, j) => (
                          <li key={`${j}-${t.slice(0, 24)}`}>{t}</li>
                        ))}
                      </ul>
                    </div>
                  </>
                ) : (
                  <pre className="batch-error-detail">{item.error.detail}</pre>
                )}
              </div>
            ))}
          </section>
        )}

        {showRawJson && (
          <details className={`raw-json ${!lastRun.rawJson ? "raw-json--disabled" : ""}`} open>
            <summary>Raw last response</summary>
            <pre className="raw-json__pre">
              {lastRun.rawJson ?? "No response captured yet. Run a request to populate."}
            </pre>
          </details>
        )}
      </main>

      <aside className="operator-panel" aria-label="Operator diagnostics">
        <h2 className="operator-panel__title">Session</h2>
        <div className="op-section">
          <div className="toggle-row">
            <span className="op-label" style={{ marginBottom: 0 }}>
              Raw JSON panel
            </span>
            <label>
              <input
                type="checkbox"
                checked={showRawJson}
                onChange={(e) => setShowRawJson(e.target.checked)}
              />
              Show
            </label>
          </div>
          <p className="op-hint">
            Collapsible block under the main form shows the last response body (or error payload)
            for demos.
          </p>
        </div>

        <h2 className="operator-panel__title">Last request</h2>
        <div className="op-section">
          <div className="op-row">
            <span className="op-label">Interaction</span>
            <span className="op-value op-value--dim">
              {lastRun.interaction ?? "—"}
            </span>
          </div>
          <div className="op-row">
            <span className="op-label">Result</span>
            <span
              className={`op-value ${
                lastRun.resultStatus === "ok"
                  ? "op-value--ok"
                  : lastRun.resultStatus === "error"
                    ? "op-value--err"
                    : lastRun.resultStatus === "partial"
                      ? "op-value--dim"
                      : "op-value--dim"
              }`}
            >
              {statusLabel}
            </span>
          </div>
          <div className="op-row">
            <span className="op-label">HTTP</span>
            <span className="op-value op-value--dim">
              {lastRun.httpStatus !== null ? lastRun.httpStatus : "—"}
            </span>
          </div>
          <div className="op-row">
            <span className="op-label">Latency</span>
            <span className="op-value op-value--dim">
              {lastRun.latencyMs !== null ? `${lastRun.latencyMs} ms` : "—"}
            </span>
          </div>
          <div className="op-row">
            <span className="op-label">Request-ID</span>
            {lastRun.requestId ? (
              <span className="op-value op-value--dim">{lastRun.requestId}</span>
            ) : (
              <p className="op-placeholder">
                Not exposed to JS unless the API adds{" "}
                <code>Access-Control-Expose-Headers: X-Request-ID</code> (CORS).
              </p>
            )}
          </div>
          {lastRun.batchLine && (
            <div className="op-row">
              <span className="op-label">Batch</span>
              <span className="op-value op-value--dim">{lastRun.batchLine}</span>
            </div>
          )}
        </div>

        <h2 className="operator-panel__title">Server context (not in API)</h2>
        <div className="op-section">
          <p className="op-placeholder">
            The API does not return runtime config. Values below are placeholders for a future
            config surface or server support.
          </p>
          <div className="op-row">
            <span className="op-label">LLM source</span>
            <input
              className="op-input"
              readOnly
              disabled
              value="stub vs real (LLM_MODE)"
              aria-label="LLM source placeholder"
            />
          </div>
          <div className="op-row">
            <span className="op-label">Prompt version</span>
            <input
              className="op-input"
              readOnly
              disabled
              value="e.g. v1 (PROMPT_VERSION)"
              aria-label="Prompt version placeholder"
            />
          </div>
          <div className="op-row">
            <span className="op-label">Model</span>
            <input
              className="op-input"
              readOnly
              disabled
              value="OPENAI_MODEL on server"
              aria-label="Model placeholder"
            />
          </div>
          <div className="op-row">
            <span className="op-label">Environment</span>
            <input
              className="op-input"
              readOnly
              disabled
              value="Configure via .env / Compose"
              aria-label="Environment placeholder"
            />
          </div>
        </div>
      </aside>
    </div>
  );
}
