import { NextRequest, NextResponse } from "next/server";

// Server-only: read in this route handler, never shipped to the browser.
// NEXT_PUBLIC_API_BASE_URL is still accepted for existing setups.
const BACKEND_URL = process.env.RAG_BACKEND_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
// Shared with the backend's PROXY_SECRET, so the backend only serves requests that came through here.
const PROXY_SECRET = process.env.RAG_PROXY_SECRET;

export const dynamic = "force-dynamic";
// A sleeping free-tier backend can take close to a minute to wake, and answers stream for a while after.
export const maxDuration = 60;

/** The visitor's address as the hosting platform reports it, so the backend can rate-limit per visitor. */
function clientIp(request: NextRequest) {
  return request.headers.get("x-real-ip") ?? request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
}

async function proxy(request: NextRequest, segments: string[]) {
  const upstreamUrl = `${BACKEND_URL.replace(/\/$/, "")}/${segments.join("/")}${request.nextUrl.search}`;
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.text();
  const headers: Record<string, string> = {
    "Content-Type": request.headers.get("content-type") || "application/json",
    "X-Client-IP": clientIp(request),
  };
  if (PROXY_SECRET) headers["X-Proxy-Secret"] = PROXY_SECRET;
  const adminToken = request.headers.get("x-admin-token");
  if (adminToken) headers["X-Admin-Token"] = adminToken;

  try {
    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
    });

    const contentType = upstream.headers.get("content-type") || "application/json";
    if (contentType.includes("application/x-ndjson")) {
      return new NextResponse(upstream.body, {
        status: upstream.status,
        headers: {
          "Content-Type": contentType,
          "Cache-Control": "no-store",
        },
      });
    }

    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: {
        "Content-Type": contentType,
      },
    });
  } catch {
    return NextResponse.json(
      { status: "error", message: "The backend is starting up or unavailable. Try again in a minute." },
      { status: 503 },
    );
  }
}

export async function GET(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context.params.path);
}

export async function POST(request: NextRequest, context: { params: { path: string[] } }) {
  return proxy(request, context.params.path);
}
