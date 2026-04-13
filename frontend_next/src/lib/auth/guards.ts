import { redirect } from "next/navigation";

import type { AuthUser } from "@/lib/api/auth";
import { getCurrentUser } from "@/lib/auth/session";
import { canAccessDevice, getDefaultDashboardHref, hasPageAccess } from "@/lib/permissions";


export async function requireAuthenticatedUser() {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/login");
  }
  return user;
}


export async function redirectIfAuthenticated() {
  const user = await getCurrentUser();
  if (user) {
    redirect(getDefaultDashboardHref(user));
  }
}


export async function requirePageAccess(pageKey: string) {
  const user = await requireAuthenticatedUser();
  if (!hasPageAccess(user, pageKey)) {
    redirect(getDefaultDashboardHref(user));
  }
  return user;
}


export function requireDeviceAccess(user: AuthUser, identifikace: string): void {
  if (!canAccessDevice(user, identifikace)) {
    redirect(getDefaultDashboardHref(user));
  }
}
