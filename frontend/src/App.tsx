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

async function parseHttpError(res: Response): Promise<string> {
  const t = await res.text();
  try {
    const j = JSON.parse(t) as { detail?: unknown };
    if (j.detail !== undefined) {
      return typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    }
  } catch {
    /* ignore */
  }
  return t || `${res.status} ${res.statusText}`;
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

  function switchPanel(next: "single" | "batch") {
    setPanel(next);
    setError(null);
    setBatchError(null);
  }

  async function onSubmitSingle(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, mode }),
      });
      if (!res.ok) {
        throw new Error(await parseHttpError(res));
      }
      setResult((await res.json()) as Result);
      setBatchResult(null);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function onSubmitBatch(e: FormEvent) {
    e.preventDefault();
    setBatchLoading(true);
    setBatchError(null);
    try {
      const parsed = JSON.parse(batchBody) as unknown;
      if (
        typeof parsed !== "object" ||
        parsed === null ||
        !("items" in parsed) ||
        !Array.isArray((parsed as { items: unknown }).items)
      ) {
        throw new Error('Body must be a JSON object with an "items" array.');
      }
      const res = await fetch(`${apiBase}/process_batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed),
      });
      if (!res.ok) {
        throw new Error(await parseHttpError(res));
      }
      setBatchResult((await res.json()) as BatchResponse);
      setResult(null);
    } catch (err) {
      setBatchResult(null);
      setBatchError(
        err instanceof SyntaxError
          ? "Invalid JSON — check commas and quotes."
          : err instanceof Error
            ? err.message
            : "Request failed",
      );
    } finally {
      setBatchLoading(false);
    }
  }

  return (
    <div className="app">
      <div className="app__inner">
        <header className="app__header">
          <h1 className="app__title">TaskMind</h1>
          <p className="app__subtitle">
            AI Work Assistant — analyze, reply, or extract tasks from your text.
          </p>
        </header>

        <div className="panel-toggle" role="group" aria-label="Request type">
          <button
            type="button"
            aria-pressed={panel === "single"}
            onClick={() => switchPanel("single")}
          >
            Single request
          </button>
          <button
            type="button"
            aria-pressed={panel === "batch"}
            onClick={() => switchPanel("batch")}
          >
            Batch (demo)
          </button>
        </div>

        {panel === "single" && (
          <form className="card" onSubmit={onSubmitSingle} aria-busy={loading}>
            <div className="field">
              <label className="card__label" htmlFor="input-text">
                Your text
              </label>
              <textarea
                id="input-text"
                className="textarea"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste or type the message you want to process…"
                rows={8}
                required
              />
            </div>
            <div className="field">
              <div className="card__label">Mode</div>
              <div className="select-wrap">
                <label htmlFor="mode-select" className="sr-only">
                  Processing mode
                </label>
                <select
                  id="mode-select"
                  value={mode}
                  onChange={(e) => setMode(e.target.value as Mode)}
                >
                  <option value="analyze">Analyze — summary &amp; intent focus</option>
                  <option value="reply">Reply — draft a response</option>
                  <option value="extract_tasks">
                    Extract tasks — pull out actionable items
                  </option>
                </select>
              </div>
              <p className="hint">Choose how the assistant should prioritize the output fields.</p>
            </div>
            <div className="actions">
              <button
                type="submit"
                className="btn btn--primary"
                disabled={loading || !text.trim()}
              >
                {loading && <span className="btn__spinner" aria-hidden />}
                {loading ? "Processing…" : "Run"}
              </button>
            </div>
          </form>
        )}

        {panel === "batch" && (
          <form className="card" onSubmit={onSubmitBatch} aria-busy={batchLoading}>
            <div className="field">
              <label className="card__label" htmlFor="batch-json">
                Batch JSON
              </label>
              <textarea
                id="batch-json"
                className="textarea textarea--mono"
                value={batchBody}
                onChange={(e) => setBatchBody(e.target.value)}
                spellCheck={false}
              />
              <p className="hint">
                POST body for <code>/process_batch</code>: an object with an{" "}
                <code>items</code> array. Each item has <code>text</code> and{" "}
                <code>mode</code> (analyze, reply, or extract_tasks). HTTP 200 returns per-item
                success or error.
              </p>
            </div>
            <div className="actions">
              <button type="submit" className="btn btn--primary" disabled={batchLoading}>
                {batchLoading && <span className="btn__spinner" aria-hidden />}
                {batchLoading ? "Running batch…" : "Run batch"}
              </button>
            </div>
          </form>
        )}

        {panel === "single" && error && (
          <div className="alert alert--error" role="alert">
            {error}
          </div>
        )}

        {panel === "batch" && batchError && (
          <div className="alert alert--error" role="alert">
            {batchError}
          </div>
        )}

        {panel === "single" && result && (
          <section className="results" aria-label="Result">
            <h2 className="results__heading">Result</h2>
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
            <h2 className="results__heading">Batch results</h2>
            {batchResult.items.map((item, i) => (
              <div
                key={i}
                className={`batch-item ${item.success ? "batch-item--ok" : "batch-item--fail"}`}
              >
                <div className="batch-item__meta">
                  Item {i + 1} — {item.success ? "success" : `error ${item.error.status_code}`}
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
      </div>
    </div>
  );
}
