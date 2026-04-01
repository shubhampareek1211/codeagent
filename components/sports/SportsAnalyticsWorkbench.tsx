"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import Link from "next/link";
import { Activity, ArrowUpRight, BarChart3, Database, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SectionTitle } from "@/components/ui/SectionTitle";

type AnalyticsHealth = {
  status: string;
  sports_analytics?: {
    status?: string;
    database?: {
      status?: string;
    };
  };
  detail?: string;
};

type QueryResponse = {
  summary: string;
  data: {
    columns: string[];
    rows: Array<Record<string, string | number>>;
    row_count: number;
  };
  visualization: {
    chart_type: string;
    title: string;
    reason: string;
    x_field?: string | null;
    y_fields: string[];
    data: Array<Record<string, string | number>>;
  };
  sql?: {
    sql: string;
  };
  warnings: string[];
};

const SAMPLE_QUERIES = [
  "Which athletes had the highest workload from 1/1/2026 to 1/5/2026?",
  "Show average sprint distance by position over the last 30 days",
  "Who is trending below their baseline performance?",
];

export function SportsAnalyticsWorkbench() {
  const [query, setQuery] = useState(SAMPLE_QUERIES[0]);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [status, setStatus] = useState<AnalyticsHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const response = await fetch("/api/sports-analytics", { cache: "no-store" });
        const payload = (await response.json()) as AnalyticsHealth;
        if (!cancelled) {
          setStatus(payload);
        }
      } catch (fetchError) {
        if (!cancelled) {
          setStatus({
            status: "error",
            detail: fetchError instanceof Error ? fetchError.message : "Unable to reach backend.",
          });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const chartRows = useMemo(() => {
    if (!result?.visualization?.data?.length || !result.visualization.x_field || !result.visualization.y_fields?.length) {
      return [];
    }

    const xField = result.visualization.x_field;
    const yField = result.visualization.y_fields[0];
    const rows = result.visualization.data
      .map((row) => ({
        label: String(row[xField] ?? ""),
        value: Number(row[yField] ?? 0),
      }))
      .filter((row) => Number.isFinite(row.value));

    const maxValue = Math.max(...rows.map((row) => row.value), 1);
    return rows.map((row) => ({
      ...row,
      widthPercent: Math.max((row.value / maxValue) * 100, 6),
    }));
  }, [result]);

  function submitAnalyticsQuery(nextQuery: string) {
    startTransition(async () => {
      setError(null);

      try {
        const response = await fetch("/api/sports-analytics", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ query: nextQuery }),
        });

        const payload = (await response.json()) as QueryResponse & { error?: string };
        if (!response.ok) {
          throw new Error(payload.error || "The backend returned an unexpected error.");
        }

        setResult(payload);
      } catch (submitError) {
        setResult(null);
        setError(submitError instanceof Error ? submitError.message : "Unable to run sports analytics query.");
      }
    });
  }

  return (
    <main className="relative z-[2] overflow-hidden py-14 sm:py-18">
      <section className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
        <SectionTitle
          eyebrow="Live Demo"
          title="Sports Analytics Workbench"
          subtitle="Run natural-language questions through the FastAPI + LangGraph backend and inspect the structured result, chart recommendation, and SQL execution path."
        />

        <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="surface-card rounded-3xl p-5 sm:p-7">
            <div className="flex flex-wrap items-center gap-3">
              <span className="inline-flex items-center gap-2 rounded-full border border-accent/20 bg-accent/10 px-3 py-1 text-xs uppercase tracking-[0.22em] text-accent">
                <Activity className="h-3.5 w-3.5" />
                Backend status
              </span>
              <span className="rounded-full border border-border bg-background/60 px-3 py-1 text-xs text-white/75">
                API: {status?.status ?? "checking"}
              </span>
              <span className="rounded-full border border-border bg-background/60 px-3 py-1 text-xs text-white/75">
                DB: {status?.sports_analytics?.database?.status ?? "unknown"}
              </span>
            </div>

            <div className="mt-5">
              <label htmlFor="sports-query" className="text-sm font-medium text-foreground">
                Ask a sports analytics question
              </label>
              <textarea
                id="sports-query"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                rows={4}
                className="mt-3 w-full rounded-2xl border border-border bg-background/70 px-4 py-3 text-sm text-foreground outline-none transition focus:border-accent/45 focus:ring-2 focus:ring-accent/20"
                placeholder="Which athletes had the highest workload from 1/1/2026 to 1/5/2026?"
              />
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {SAMPLE_QUERIES.map((sampleQuery) => (
                <button
                  key={sampleQuery}
                  type="button"
                  onClick={() => setQuery(sampleQuery)}
                  className="rounded-full border border-border bg-background/60 px-3 py-1.5 text-xs text-white/75 transition hover:border-accent/25 hover:text-foreground"
                >
                  {sampleQuery}
                </button>
              ))}
            </div>

            <p className="mt-3 text-xs text-white/55">
              If your dataset only covers early January 2026, start with the 1/1/2026 to 1/5/2026 sample query.
            </p>

            <div className="mt-5 flex flex-wrap items-center gap-3">
              <Button onClick={() => submitAnalyticsQuery(query)} disabled={isPending || !query.trim()}>
                {isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
                Run query
              </Button>
              <Link
                href="http://127.0.0.1:8000/docs"
                target="_blank"
                className="inline-flex items-center gap-2 rounded-full border border-border bg-background/60 px-4 py-2 text-sm text-white/75 transition hover:border-accent/25 hover:text-foreground"
              >
                Open FastAPI docs
                <ArrowUpRight className="h-4 w-4" />
              </Link>
            </div>

            {status?.detail ? (
              <p className="mt-4 rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
                {status.detail}
              </p>
            ) : null}

            {error ? (
              <p className="mt-4 rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
                {error}
              </p>
            ) : null}
          </div>

          <div className="signal-card rounded-3xl p-5 sm:p-7">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-accent/20 bg-accent/10 p-3 text-accent">
                <Database className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-foreground">What this page is hitting</h3>
                <p className="mt-1 text-sm text-white/75">
                  Next.js calls <code>/api/sports-analytics</code>, which proxies the request to the local FastAPI backend on port <code>8000</code>.
                </p>
              </div>
            </div>

            <ul className="mt-5 space-y-3 text-sm text-white/75">
              <li className="rounded-2xl border border-border bg-background/50 px-4 py-3">
                <strong className="text-foreground">Intent extraction:</strong> metric, grouping, ranking, time window, and ambiguity flags.
              </li>
              <li className="rounded-2xl border border-border bg-background/50 px-4 py-3">
                <strong className="text-foreground">Deterministic SQL:</strong> a constrained plan compiles to safe, select-only SQL.
              </li>
              <li className="rounded-2xl border border-border bg-background/50 px-4 py-3">
                <strong className="text-foreground">Chart guidance:</strong> the backend suggests a chart type and chart-ready data payload.
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section className="mx-auto mt-8 grid w-full max-w-7xl gap-6 px-4 sm:px-6 lg:px-8 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="surface-card rounded-3xl p-5 sm:p-7">
          <div className="flex items-center gap-3">
            <BarChart3 className="h-5 w-5 text-accent" />
            <h3 className="text-lg font-semibold text-foreground">Summary</h3>
          </div>
          <p className="mt-4 text-sm leading-7 text-white/80">
            {result?.summary || "Run a query to see the grounded response summary here."}
          </p>

          {result?.warnings?.length ? (
            <div className="mt-4 rounded-2xl border border-amber-300/20 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
              {result.warnings.join(" ")}
            </div>
          ) : null}

          <div className="mt-6 rounded-2xl border border-border bg-background/55 p-4">
            <p className="text-xs uppercase tracking-[0.22em] text-accent/80">Chart recommendation</p>
            <p className="mt-2 text-base font-semibold text-foreground">
              {result?.visualization?.title || "No chart yet"}
            </p>
            <p className="mt-2 text-sm text-white/75">
              {result?.visualization?.reason || "The backend will explain why a chart type was chosen."}
            </p>
          </div>

          {chartRows.length ? (
            <div className="mt-6 space-y-3">
              {chartRows.map((row) => (
                <div key={row.label}>
                  <div className="mb-1 flex items-center justify-between text-xs text-white/70">
                    <span>{row.label}</span>
                    <span>{row.value}</span>
                  </div>
                  <div className="h-2 rounded-full bg-white/10">
                    <div
                      className="h-2 rounded-full bg-gradient-to-r from-accent/90 to-[#ff6b35]"
                      style={{ width: `${row.widthPercent}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>

        <div className="signal-card rounded-3xl p-5 sm:p-7">
          <h3 className="text-lg font-semibold text-foreground">Result table</h3>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full border-separate border-spacing-y-2">
              <thead>
                <tr>
                  {(result?.data.columns || []).map((column) => (
                    <th
                      key={column}
                      className="px-3 py-2 text-left text-xs uppercase tracking-[0.18em] text-accent/80"
                    >
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result?.data.rows?.length ? (
                  result.data.rows.map((row, index) => (
                    <tr key={`${index}-${String(row[result.data.columns[0]] ?? index)}`} className="code-panel">
                      {result.data.columns.map((column) => (
                        <td key={`${index}-${column}`} className="px-3 py-3 text-sm text-white/80">
                          {String(row[column] ?? "")}
                        </td>
                      ))}
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td className="px-3 py-6 text-sm text-white/55">No rows yet. Run a query to populate this table.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="mt-6 rounded-2xl border border-border bg-background/55 p-4">
            <p className="text-xs uppercase tracking-[0.22em] text-accent/80">SQL</p>
            <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs leading-6 text-white/75">
              {result?.sql?.sql || "The compiled SQL for the current query will appear here."}
            </pre>
          </div>
        </div>
      </section>
    </main>
  );
}
