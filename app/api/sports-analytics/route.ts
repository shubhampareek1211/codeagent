import { NextRequest, NextResponse } from "next/server";
import { env } from "@/lib/env";

export const runtime = "nodejs";

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

function getBaseUrl() {
  return env.SPORTS_ANALYTICS_BACKEND_URL || DEFAULT_BACKEND_URL;
}

export async function GET() {
  try {
    const response = await fetch(`${getBaseUrl().replace(/\/$/, "")}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });

    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        status: "error",
        detail: error instanceof Error ? error.message : "Unable to reach sports analytics backend.",
      },
      { status: 503 },
    );
  }
}

export async function POST(request: NextRequest) {
  let body: { query?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const query = body.query?.trim();
  if (!query) {
    return NextResponse.json({ error: "Query is required." }, { status: 400 });
  }

  try {
    const response = await fetch(`${getBaseUrl().replace(/\/$/, "")}/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query }),
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });

    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Unable to reach sports analytics backend.",
      },
      { status: 503 },
    );
  }
}
