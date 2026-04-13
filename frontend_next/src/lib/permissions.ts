import type { AuthUser } from "@/lib/api/auth";
import {
  canAccessDevice,
  canAccessVodomery,
  getDefaultDashboardHref,
  hasPageAccess,
  hasSectionAccess,
} from "@/lib/dashboard-navigation";

export { canAccessDevice, canAccessVodomery, getDefaultDashboardHref, hasPageAccess, hasSectionAccess };

export type { AuthUser };
