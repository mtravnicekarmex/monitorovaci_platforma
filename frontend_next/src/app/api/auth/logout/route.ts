import { NextResponse } from "next/server";

import { logoutFromBackend } from "@/lib/api/auth";
import { getSessionToken, clearSessionToken } from "@/lib/auth/cookies";


export async function POST(request: Request) {
  const token = await getSessionToken();

  if (token) {
    try {
      await logoutFromBackend(token);
    } catch {
      // Logout should clear the local cookie even if backend revocation fails.
    }
  }

  await clearSessionToken();

  const redirectUrl = new URL("/login", request.url);
  return NextResponse.redirect(redirectUrl, { status: 303 });
}
