import { cookies } from "next/headers";

import { getSessionCookieName } from "@/lib/env";


export async function getSessionToken(): Promise<string | null> {
  return (await cookies()).get(getSessionCookieName())?.value ?? null;
}


export async function setSessionToken(token: string, expiresAt: string): Promise<void> {
  (await cookies()).set({
    name: getSessionCookieName(),
    value: token,
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    expires: new Date(expiresAt),
  });
}


export async function clearSessionToken(): Promise<void> {
  (await cookies()).set({
    name: getSessionCookieName(),
    value: "",
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    expires: new Date(0),
  });
}
