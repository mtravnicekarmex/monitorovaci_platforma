import { NextResponse } from "next/server";

import { loginAgainstBackend } from "@/lib/api/auth";
import { BackendApiError } from "@/lib/api/backend";
import { setSessionToken } from "@/lib/auth/cookies";


export async function POST(request: Request) {
  let payload: { username?: string; password?: string } | null = null;
  try {
    payload = (await request.json()) as { username?: string; password?: string };
  } catch {
    return NextResponse.json({ detail: "Neplatny JSON payload." }, { status: 400 });
  }

  const username = String(payload?.username || "").trim();
  const password = String(payload?.password || "");

  if (!username || !password) {
    return NextResponse.json({ detail: "Uzivatelske jmeno i heslo jsou povinne." }, { status: 400 });
  }

  try {
    const session = await loginAgainstBackend(username, password);
    await setSessionToken(session.access_token, session.expires_at);
    return NextResponse.json({
      user: session.user,
      expires_at: session.expires_at,
    });
  } catch (error) {
    if (error instanceof BackendApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }
    return NextResponse.json({ detail: "Prihlaseni selhalo." }, { status: 500 });
  }
}
