import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";


const SESSION_COOKIE_NAME = process.env.SESSION_COOKIE_NAME?.trim() || "monitoring_access_token";


function hasSessionCookie(request: NextRequest): boolean {
  return Boolean(request.cookies.get(SESSION_COOKIE_NAME)?.value);
}


export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const isAuthenticated = hasSessionCookie(request);

  if ((pathname.startsWith("/vodomery") || pathname.startsWith("/ucet")) && !isAuthenticated) {
    const loginUrl = new URL("/login", request.url);
    const nextParam = `${pathname}${search}`.trim();
    if (nextParam) {
      loginUrl.searchParams.set("next", nextParam);
    }
    return NextResponse.redirect(loginUrl);
  }

  if (pathname === "/login" && isAuthenticated) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
}


export const config = {
  matcher: ["/login", "/vodomery/:path*", "/ucet/:path*"],
};
