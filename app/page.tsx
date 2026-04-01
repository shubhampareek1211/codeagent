import Link from "next/link";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col items-center justify-center px-6 py-16 text-center">
      <span className="rounded-full border border-accent/20 bg-accent/10 px-4 py-1 text-xs uppercase tracking-[0.24em] text-accent">
        Standalone Demo
      </span>
      <h1 className="mt-6 text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
        Sports Analytics Workbench
      </h1>
      <p className="mt-4 max-w-2xl text-base text-white/75 sm:text-lg">
        Natural-language sports analytics frontend backed by a FastAPI + LangGraph service with deterministic SQL
        compilation and validation.
      </p>
      <div className="mt-8">
        <Link
          href="/sports-analytics"
          className="inline-flex items-center rounded-full bg-primary px-6 py-3 text-sm font-medium text-primary-foreground transition hover:opacity-90"
        >
          Open Workbench
        </Link>
      </div>
    </main>
  );
}
