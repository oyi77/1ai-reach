import { type NextRequest } from "next/server";

const FASTAPI_BASE = "http://localhost:8001";

export async function GET(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const path = pathname.replace("/api/data/", "/data/");
  const targetUrl = `${FASTAPI_BASE}${path}${search}`;

  try {
    const response = await fetch(targetUrl);

    const responseHeaders = new Headers();
    for (const [key, value] of response.headers.entries()) {
      const lower = key.toLowerCase();
      if (lower === "transfer-encoding") continue;
      if (lower === "content-encoding") continue;
      responseHeaders.set(key, value);
    }

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error(`Image proxy error to ${targetUrl}:`, error);
    return new Response("Not found", { status: 404 });
  }
}
