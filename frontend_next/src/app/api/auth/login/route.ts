import { NextResponse } from "next/server";

import { loginAgainstBackend } from "@/lib/api/auth";
import { BackendApiError } from "@/lib/api/backend";
import { resolveSafeNextPath } from "@/lib/auth/next-path";
import { setSessionToken } from "@/lib/auth/cookies";


function buildLoginRedirectUrl(request: Request, params?: { error?: string; nextPath?: string }): URL {
  const redirectUrl = new URL("/login", request.url);
  const nextPath = resolveSafeNextPath(params?.nextPath);

  if (nextPath !== "/") {
    redirectUrl.searchParams.set("next", nextPath);
  }
  if (params?.error) {
    redirectUrl.searchParams.set("error", params.error);
  }

  return redirectUrl;
}


export async function POST(request: Request) {
  const contentType = request.headers.get("content-type") || "";
  const expectsJson = contentType.includes("application/json");

  let username = "";
  let password = "";
  let nextPath = "/";

  if (expectsJson) {
    let payload: { username?: string; password?: string; next?: string } | null = null;
    try {
      payload = (await request.json()) as { username?: string; password?: string; next?: string };
    } catch {
      return NextResponse.json({ detail: "Neplatny JSON payload." }, { status: 400 });
    }

    username = String(payload?.username || "").trim();
    password = String(payload?.password || "");
    nextPath = resolveSafeNextPath(payload?.next);
  } else {
    const formData = await request.formData();
    username = String(formData.get("username") || "").trim();
    password = String(formData.get("password") || "");
    nextPath = resolveSafeNextPath(String(formData.get("next") || ""));
  }

  if (!username || !password) {
    if (expectsJson) {
      return NextResponse.json({ detail: "Uzivatelske jmeno i heslo jsou povinne." }, { status: 400 });
    }
    return NextResponse.redirect(buildLoginRedirectUrl(request, {
      error: "Uzivatelske jmeno i heslo jsou povinne.",
      nextPath,
    }), { status: 303 });
  }

  try {
    const session = await loginAgainstBackend(username, password);
    await setSessionToken(session.access_token, session.expires_at);

    if (!expectsJson) {
      return NextResponse.redirect(new URL(nextPath, request.url), { status: 303 });
    }

    return NextResponse.json({
      user: session.user,
      expires_at: session.expires_at,
    });
  } catch (error) {
    if (error instanceof BackendApiError) {
      if (expectsJson) {
        return NextResponse.json({ detail: error.message }, { status: error.status });
      }
      return NextResponse.redirect(buildLoginRedirectUrl(request, {
        error: error.message,
        nextPath,
      }), { status: 303 });
    }
    if (expectsJson) {
      return NextResponse.json({ detail: "Prihlaseni selhalo." }, { status: 500 });
    }
    return NextResponse.redirect(buildLoginRedirectUrl(request, {
      error: "Prihlaseni selhalo.",
      nextPath,
    }), { status: 303 });
  }
}
