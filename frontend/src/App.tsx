import { type FormEvent, useEffect, useState } from "react";

import "./App.css";

type RuntimeConfig = {
  default_llm_mode: string;
  default_prompt_version: string;
  default_model: string;
  default_base_url: string;
  available_prompt_versions: string[];
  real_mode_supported: boolean;
  json_object_request_enabled: boolean;
};

type ModelsListSource = "live" | "stub_mode" | "no_api_key" | "provider_error";

type ModelsInfo = {
  models: string[];
  source: ModelsListSource;
  detail: string | null;
  base_url: string;
};

type LLMModeUi = "stub" | "real";

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

const THEME_STORAGE_KEY = "taskmind-theme";

type ThemeChoice = "light" | "dark";

type BatchRow = { id: string; text: string; mode: Mode };

const INITIAL_BATCH_ROWS: BatchRow[] = [
  { id: "row-a", text: "Hello world", mode: "analyze" },
  { id: "row-b", text: "- First action\n- Second action", mode: "extract_tasks" },
];

function formatPrettyRaw(raw: string | null): string {
  if (raw == null || raw === "") {
    return "";
  }
  const t = raw.trim();
  try {
    return JSON.stringify(JSON.parse(t) as object, null, 2);
  } catch {
    return raw;
  }
}

function newBatchRow(): BatchRow {
  return { id: crypto.randomUUID(), text: "", mode: "analyze" };
}

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

function buildRuntimePayload(
  llmMode: LLMModeUi,
  promptVersion: string,
  model: string,
  baseUrl: string,
): { llm_mode: LLMModeUi; prompt_version?: string; model?: string; base_url?: string } {
  const r: {
    llm_mode: LLMModeUi;
    prompt_version?: string;
    model?: string;
    base_url?: string;
  } = { llm_mode: llmMode };
  const pv = promptVersion.trim();
  const m = model.trim();
  const b = baseUrl.trim();
  if (pv) {
    r.prompt_version = pv;
  }
  if (m) {
    r.model = m;
  }
  if (b) {
    r.base_url = b;
  }
  return r;
}

export default function App() {
  const [panel, setPanel] = useState<"single" | "batch">("single");

  const [text, setText] = useState("");
  const [mode, setMode] = useState<Mode>("analyze");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);

  const [batchBody, setBatchBody] = useState(BATCH_PLACEHOLDER);
  const [batchEditorMode, setBatchEditorMode] = useState<"structured" | "raw">("structured");
  const [batchRows, setBatchRows] = useState<BatchRow[]>(() => [...INITIAL_BATCH_ROWS]);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [batchResult, setBatchResult] = useState<BatchResponse | null>(null);

  const [lastRun, setLastRun] = useState<LastRun>(INITIAL_LAST);
  const [showRawJson, setShowRawJson] = useState(true);

  const [runtimeConfig, setRuntimeConfig] = useState<RuntimeConfig | null>(null);
  const [cfgError, setCfgError] = useState<string | null>(null);
  const [modelsInfo, setModelsInfo] = useState<ModelsInfo | null>(null);
  const [opLlmMode, setOpLlmMode] = useState<LLMModeUi>("stub");
  const [opPromptVersion, setOpPromptVersion] = useState("v1");
  const [opModel, setOpModel] = useState("gpt-4o-mini");
  const [opBaseUrl, setOpBaseUrl] = useState("https://api.openai.com/v1");

  const [theme, setTheme] = useState<ThemeChoice>(() => {
    if (typeof window === "undefined") {
      return "dark";
    }
    try {
      const t = localStorage.getItem(THEME_STORAGE_KEY);
      if (t === "light" || t === "dark") {
        return t;
      }
    } catch {
      /* ignore */
    }
    return "dark";
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  useEffect(() => {
    let cancelled = false;
    fetch(`${apiBase}/runtime_config`)
      .then((r) => {
        if (!r.ok) {
          throw new Error(`runtime_config ${r.status}`);
        }
        return r.json() as Promise<RuntimeConfig>;
      })
      .then((cfg) => {
        if (cancelled) {
          return;
        }
        setRuntimeConfig(cfg);
        setCfgError(null);
        setOpLlmMode(cfg.default_llm_mode === "real" ? "real" : "stub");
        setOpPromptVersion(cfg.default_prompt_version);
        setOpModel(cfg.default_model);
        setOpBaseUrl(cfg.default_base_url);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setCfgError(e instanceof Error ? e.message : "Failed to load /runtime_config");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch(`${apiBase}/models`)
      .then((r) => {
        if (!r.ok) {
          throw new Error(`models ${r.status}`);
        }
        return r.json() as Promise<ModelsInfo>;
      })
      .then((data) => {
        if (!cancelled) {
          setModelsInfo(data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setModelsInfo(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function resetRuntimeToServerDefaults() {
    if (!runtimeConfig) {
      return;
    }
    setOpLlmMode(runtimeConfig.default_llm_mode === "real" ? "real" : "stub");
    setOpPromptVersion(runtimeConfig.default_prompt_version);
    setOpModel(runtimeConfig.default_model);
    setOpBaseUrl(runtimeConfig.default_base_url);
  }

  function switchPanel(next: "single" | "batch") {
    setPanel(next);
    setError(null);
    setBatchError(null);
  }

  function handleBatchEditorMode(next: "structured" | "raw") {
    if (next === batchEditorMode) {
      return;
    }
    if (next === "raw") {
      const items = batchRows.map((r) => ({ text: r.text, mode: r.mode }));
      setBatchBody(JSON.stringify({ items }, null, 2));
    } else {
      try {
        const p = JSON.parse(batchBody) as { items?: { text?: string; mode?: string }[] };
        if (p.items && Array.isArray(p.items)) {
          setBatchRows(
            p.items.map((it) => {
              const m = it.mode;
              const mode: Mode =
                m === "reply" || m === "extract_tasks" || m === "analyze" ? m : "analyze";
              return {
                id: crypto.randomUUID(),
                text: typeof it.text === "string" ? it.text : "",
                mode,
              };
            }),
          );
        }
      } catch {
        /* keep existing rows */
      }
    }
    setBatchEditorMode(next);
  }

  function updateBatchRow(id: string, patch: Partial<Pick<BatchRow, "text" | "mode">>) {
    setBatchRows((rows) =>
      rows.map((r) => (r.id === id ? { ...r, ...patch } : r)),
    );
  }

  function addBatchRow() {
    setBatchRows((rows) => [...rows, newBatchRow()]);
  }

  function removeBatchRow(id: string) {
    setBatchRows((rows) => (rows.length <= 1 ? rows : rows.filter((r) => r.id !== id)));
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
        body: JSON.stringify({
          text,
          mode,
          runtime: buildRuntimePayload(opLlmMode, opPromptVersion, opModel, opBaseUrl),
        }),
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
      if (batchEditorMode === "structured") {
        const items = batchRows
          .map((r) => ({ text: r.text.trim(), mode: r.mode }))
          .filter((it) => it.text.length > 0);
        if (items.length === 0) {
          const latencyMs = Math.round(performance.now() - t0);
          setLastRun({
            interaction: "batch",
            httpStatus: null,
            requestId: null,
            latencyMs,
            resultStatus: "error",
            rawJson: "Add at least one row with non-empty text.",
            batchLine: null,
          });
          setBatchError("Add at least one row with non-empty text.");
          return;
        }
        parsed = { items };
      } else {
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
      const batchPayload = {
        ...(parsed as object),
        runtime: buildRuntimePayload(opLlmMode, opPromptVersion, opModel, opBaseUrl),
      };
      const res = await fetch(`${apiBase}/process_batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(batchPayload),
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
          <div className="app-header__top">
            <div className="app-header__titles">
              <h1 className="app-title">
                Task<span>Mind</span>
              </h1>
            </div>
            <button
              type="button"
              className="theme-toggle"
              onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
              title={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
            >
              {theme === "dark" ? "Light" : "Dark"}
            </button>
          </div>
          <p className="app-subtitle">
            Operator console — runtime defaults load from <code>GET /runtime_config</code>; optional{" "}
            <code>runtime</code> overrides apply per request only.
          </p>
          {cfgError && (
            <p className="alert" style={{ marginTop: "0.75rem", maxWidth: "36rem" }}>
              Config: {cfgError} (operator fields use fallbacks)
            </p>
          )}
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
            <div className="batch-editor-bar">
              <span className="batch-editor-bar__label">Editor</span>
              <div
                className="batch-mode-toggle"
                role="group"
                aria-label="Batch editor mode"
              >
                <button
                  type="button"
                  aria-pressed={batchEditorMode === "structured"}
                  onClick={() => handleBatchEditorMode("structured")}
                >
                  Rows
                </button>
                <button
                  type="button"
                  aria-pressed={batchEditorMode === "raw"}
                  onClick={() => handleBatchEditorMode("raw")}
                >
                  Raw JSON
                </button>
              </div>
            </div>

            {batchEditorMode === "structured" && (
              <div className="field">
                <div className="batch-rows">
                  {batchRows.map((row, idx) => (
                    <div key={row.id} className="batch-row">
                      <div className="batch-row__main">
                        <span className="batch-row__index">Item {idx + 1}</span>
                        <textarea
                          className="batch-row__textarea"
                          value={row.text}
                          onChange={(e) => updateBatchRow(row.id, { text: e.target.value })}
                          placeholder="Text for this item…"
                          rows={3}
                        />
                      </div>
                      <div className="batch-row__mode">
                        <select
                          value={row.mode}
                          onChange={(e) =>
                            updateBatchRow(row.id, { mode: e.target.value as Mode })
                          }
                          aria-label={`Mode for item ${idx + 1}`}
                        >
                          <option value="analyze">analyze</option>
                          <option value="reply">reply</option>
                          <option value="extract_tasks">extract_tasks</option>
                        </select>
                      </div>
                      <button
                        type="button"
                        className="batch-row__remove"
                        onClick={() => removeBatchRow(row.id)}
                        disabled={batchRows.length <= 1}
                        aria-label={`Remove item ${idx + 1}`}
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
                <button
                  type="button"
                  className="btn btn--secondary"
                  style={{ marginTop: "0.65rem" }}
                  onClick={addBatchRow}
                >
                  Add row
                </button>
                <p className="hint">
                  Builds <code>items</code> for <code>POST /process_batch</code>. Empty rows are
                  skipped.
                </p>
              </div>
            )}

            {batchEditorMode === "raw" && (
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
                  Advanced: full request body (must include <code>items</code>). Switch to Rows to
                  return to the structured editor (content is synced when you toggle).
                </p>
              </div>
            )}
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
              {lastRun.rawJson
                ? formatPrettyRaw(lastRun.rawJson)
                : "No response captured yet. Run a request to populate."}
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

        <h2 className="operator-panel__title">Runtime overrides</h2>
        <div className="op-section">
          <p className="op-hint" style={{ marginTop: 0 }}>
            Sent as <code>runtime</code> on each <code>/process</code> or <code>/process_batch</code>{" "}
            call. Empty optional fields fall back to server defaults. Does not change{" "}
            <code>.env</code>.
          </p>
          {runtimeConfig && !runtimeConfig.real_mode_supported && opLlmMode === "real" && (
            <p className="op-placeholder" style={{ marginBottom: "0.5rem" }}>
              Server reports no API key — real mode will return 503 unless{" "}
              <code>OPENAI_API_KEY</code> is set.
            </p>
          )}
          <div className="op-row">
            <span className="op-label">LLM mode</span>
            <select
              className="op-select"
              value={opLlmMode}
              onChange={(e) => setOpLlmMode(e.target.value as LLMModeUi)}
              aria-label="LLM mode override"
            >
              <option value="stub">stub</option>
              <option value="real">real</option>
            </select>
          </div>
          <div className="op-row">
            <span className="op-label">Prompt version</span>
            <input
              className="op-input"
              value={opPromptVersion}
              onChange={(e) => setOpPromptVersion(e.target.value)}
              list={runtimeConfig ? "prompt-versions" : undefined}
              placeholder="v1"
              aria-label="Prompt version"
            />
            {runtimeConfig && (
              <datalist id="prompt-versions">
                {runtimeConfig.available_prompt_versions.map((v) => (
                  <option key={v} value={v} />
                ))}
              </datalist>
            )}
          </div>
          <div className="op-row">
            <span className="op-label">Model</span>
            {modelsInfo?.source === "live" && modelsInfo.models.length > 0 ? (
              <select
                className="op-select"
                value={opModel}
                onChange={(e) => setOpModel(e.target.value)}
                aria-label="Model override"
              >
                {!modelsInfo.models.includes(opModel) && opModel.trim() !== "" && (
                  <option value={opModel}>{opModel} (current)</option>
                )}
                {modelsInfo.models.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            ) : (
              <input
                className="op-input"
                value={opModel}
                onChange={(e) => setOpModel(e.target.value)}
                placeholder="e.g. gpt-4o-mini"
                aria-label="Model override"
              />
            )}
          </div>
          {modelsInfo && modelsInfo.source !== "live" && modelsInfo.detail && (
            <p className="op-placeholder" style={{ marginTop: "0.35rem", marginBottom: 0 }}>
              Models list: {modelsInfo.detail}{" "}
              <span className="op-value--dim">({modelsInfo.base_url})</span>
            </p>
          )}
          {modelsInfo?.source === "live" && modelsInfo.models.length > 0 && (
            <p className="op-placeholder" style={{ marginTop: "0.35rem", marginBottom: 0 }}>
              Loaded from provider at{" "}
              <span className="op-value--dim">{modelsInfo.base_url}</span> (server{" "}
              <code>OPENAI_BASE_URL</code>). Changing Base URL below does not change this list.
            </p>
          )}
          <div className="op-row">
            <span className="op-label">Base URL</span>
            <input
              className="op-input"
              value={opBaseUrl}
              onChange={(e) => setOpBaseUrl(e.target.value)}
              aria-label="OpenAI-compatible base URL"
            />
          </div>
          <button type="button" className="op-btn-reset" onClick={resetRuntimeToServerDefaults}>
            Reset to server defaults
          </button>
        </div>
      </aside>
    </div>
  );
}
