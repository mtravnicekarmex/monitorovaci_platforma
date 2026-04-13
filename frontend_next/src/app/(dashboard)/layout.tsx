import type { ReactNode } from "react";

import { DashboardShell } from "@/components/layout/dashboard-shell";
import { requireAuthenticatedUser } from "@/lib/auth/guards";
import { getAccessiblePageDefinitions } from "@/lib/dashboard-navigation";


export default async function DashboardLayout({ children }: { children: ReactNode }) {
  const user = await requireAuthenticatedUser();
  const mainPages = getAccessiblePageDefinitions(user, "main", {
    implementedOnly: true,
    navigableOnly: true,
  });
  const footerPages = getAccessiblePageDefinitions(user, "footer", {
    implementedOnly: true,
    navigableOnly: true,
  });

  return <DashboardShell user={user} mainPages={mainPages} footerPages={footerPages}>{children}</DashboardShell>;
}
