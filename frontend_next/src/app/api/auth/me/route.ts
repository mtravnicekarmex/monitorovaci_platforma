import { NextResponse } from "next/server";

import { getCurrentUserFromBackend } from "@/lib/api/auth";
import { BackendApiError } from "@/lib/api/backend";
import { clearSessionToken, getSessionToken } from "@/lib/auth/cookies";


export async function GET() {
  const token = await getSessionToken();
  if (!token) {
    return NextResponse.json({ detail: "Nejsi prihlasen." }, { status: 401 });
  }

  try {
    const user = await getCurrentUserFromBackend(token);
    return NextResponse.json(user);
  } catch (error) {
    if (error instanceof BackendApiError && error.status === 401) {
      await clearSessionToken();
      return NextResponse.json({ detail: "Prihlaseni expirovalo." }, { status: 401 });
    }

    if (error instanceof BackendApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Nepodarilo se nacist aktualniho uzivatele." }, { status: 500 });
  }
}
