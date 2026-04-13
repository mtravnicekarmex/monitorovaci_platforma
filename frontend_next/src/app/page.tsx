import { redirect } from "next/navigation";

import { getCurrentUser } from "@/lib/auth/session";
import { getDefaultDashboardHref } from "@/lib/permissions";


export default async function HomePage() {
  const user = await getCurrentUser();

  if (!user) {
    redirect("/login");
  }

  redirect(getDefaultDashboardHref(user));
}
