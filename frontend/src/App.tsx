import { type FormEvent, useState } from "react";

type Mode = "analyze" | "reply" | "extract_tasks";

type Result = {
  summary: string;
  intent: string;
  reply: string;
  tasks: string[];
};

const apiBase =
  import.meta.env.VITE_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export default function App() {
  const [text, setText] = useState("");
  const [mode, setMode] = useState<Mode>("analyze");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);

  async function onSubmit(e: FormEvent) {
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
        const body = await res.text();
        throw new Error(body || `${res.status} ${res.statusText}`);
      }
      setResult((await res.json()) as Result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        maxWidth: 720,
        margin: "2rem auto",
        fontFamily: "system-ui, sans-serif",
        padding: "0 1rem",
      }}
    >
      <h1 style={{ fontSize: "1.5rem" }}>TaskMind</h1>
      <form onSubmit={onSubmit}>
        <label style={{ display: "block", marginBottom: "0.5rem" }}>
          Text
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={6}
            style={{ display: "block", width: "100%", marginTop: "0.35rem" }}
          />
        </label>
        <label style={{ display: "block", marginBottom: "0.5rem" }}>
          Mode
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as Mode)}
            style={{ display: "block", marginTop: "0.35rem" }}
          >
            <option value="analyze">analyze</option>
            <option value="reply">reply</option>
            <option value="extract_tasks">extract_tasks</option>
          </select>
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Submitting…" : "Submit"}
        </button>
      </form>
      {error && (
        <p style={{ color: "crimson", marginTop: "1rem" }} role="alert">
          {error}
        </p>
      )}
      {result && (
        <section style={{ marginTop: "1.5rem" }}>
          <h2 style={{ fontSize: "1.1rem" }}>Summary</h2>
          <p>{result.summary}</p>
          <h2 style={{ fontSize: "1.1rem" }}>Intent</h2>
          <p>{result.intent}</p>
          <h2 style={{ fontSize: "1.1rem" }}>Reply</h2>
          <p>{result.reply}</p>
          <h2 style={{ fontSize: "1.1rem" }}>Tasks</h2>
          <ul>
            {result.tasks.map((t, i) => (
              <li key={`${i}-${t}`}>{t}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
