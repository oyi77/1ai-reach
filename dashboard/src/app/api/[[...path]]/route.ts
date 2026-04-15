import { type NextRequest } from "next/server";

const FLASK_BASE = "http://localhost:8766";

async function proxyRequest(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const targetUrl = `${FLASK_BASE}${pathname}${search}`;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");
  headers.delete("upgrade");

  const method = request.method;

  let body: ReadableStream<Uint8Array> | null | undefined = undefined;
  if (method !== "GET" && method !== "HEAD") {
    body = request.body;
  }

  const flaskResponse = await fetch(targetUrl, {
    method,
    headers,
    body,
    // @ts-expect-error duplex needed for streaming requests in Node
    duplex: body ? "half" : undefined,
  });

  const responseHeaders = new Headers();
  for (const [key, value] of flaskResponse.headers.entries()) {
    const lower = key.toLowerCase();
    if (lower === "transfer-encoding") continue;
    responseHeaders.set(key, value);
  }

  return new Response(flaskResponse.body, {
    status: flaskResponse.status,
    statusText: flaskResponse.statusText,
    headers: responseHeaders,
  });
}

export async function GET(request: NextRequest) {
  return proxyRequest(request);
}

export async function POST(request: NextRequest) {
  return proxyRequest(request);
}

export async function PUT(request: NextRequest) {
  return proxyRequest(request);
}

export async function PATCH(request: NextRequest) {
  return proxyRequest(request);
}

export async function DELETE(request: NextRequest) {
  return proxyRequest(request);
}

export async function OPTIONS(request: NextRequest) {
  return proxyRequest(request);
}
