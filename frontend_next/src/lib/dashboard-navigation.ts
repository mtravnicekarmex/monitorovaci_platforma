import type { AuthUser } from "@/lib/api/auth";


export type SidebarLocation = "main" | "footer";

export type DashboardSectionDefinition = {
  key: string;
  label: string;
  description: string;
  requiresDevicePermissions: boolean;
};

export type DashboardPageDefinition = {
  key: string;
  title: string;
  description: string;
  sectionKey: string | null;
  sidebarLocation: SidebarLocation;
  adminOnly: boolean;
  implemented: boolean;
  navigable: boolean;
  href: string | null;
};


export const DASHBOARD_SECTIONS: DashboardSectionDefinition[] = [
  {
    key: "vodomery",
    label: "Vodomery",
    description: "Mereni, detail a provozni eventy vodomeru.",
    requiresDevicePermissions: true,
  },
  {
    key: "plynomery",
    label: "Plynomery",
    description: "Spotreba a detail plynomeru.",
    requiresDevicePermissions: true,
  },
  {
    key: "elektromery",
    label: "Elektromery",
    description: "Spotreba a detail elektromeru.",
    requiresDevicePermissions: true,
  },
  {
    key: "kalorimetry",
    label: "Kalorimetry",
    description: "Teplo a provozni data kalorimetru.",
    requiresDevicePermissions: true,
  },
];

export const DASHBOARD_PAGES: DashboardPageDefinition[] = [
  {
    key: "vodomery_overview",
    title: "Prehled",
    description: "Operativni overview vodomeru.",
    sectionKey: "vodomery",
    sidebarLocation: "main",
    adminOnly: false,
    implemented: true,
    navigable: true,
    href: "/vodomery",
  },
  {
    key: "vodomery_branch_overview",
    title: "Prehled vetve",
    description: "Administratorsky prehled vetve.",
    sectionKey: "vodomery",
    sidebarLocation: "main",
    adminOnly: true,
    implemented: false,
    navigable: false,
    href: null,
  },
  {
    key: "vodomery_anomalie_eventy",
    title: "Anomalie a eventy",
    description: "Historie a aktualni eventy vodomeru.",
    sectionKey: "vodomery",
    sidebarLocation: "main",
    adminOnly: false,
    implemented: false,
    navigable: false,
    href: null,
  },
  {
    key: "vodomery_detail",
    title: "Detail",
    description: "Detail zarizeni, mereni a event history.",
    sectionKey: "vodomery",
    sidebarLocation: "main",
    adminOnly: false,
    implemented: true,
    navigable: false,
    href: null,
  },
  {
    key: "plynomery_overview",
    title: "Prehled",
    description: "Prehled plynomeru.",
    sectionKey: "plynomery",
    sidebarLocation: "main",
    adminOnly: false,
    implemented: false,
    navigable: false,
    href: null,
  },
  {
    key: "plynomery_detail",
    title: "Detail",
    description: "Detail plynomeru.",
    sectionKey: "plynomery",
    sidebarLocation: "main",
    adminOnly: false,
    implemented: false,
    navigable: false,
    href: null,
  },
  {
    key: "elektromery_overview",
    title: "Prehled",
    description: "Prehled elektromeru.",
    sectionKey: "elektromery",
    sidebarLocation: "main",
    adminOnly: false,
    implemented: false,
    navigable: false,
    href: null,
  },
  {
    key: "elektromery_detail",
    title: "Detail",
    description: "Detail elektromeru.",
    sectionKey: "elektromery",
    sidebarLocation: "main",
    adminOnly: false,
    implemented: false,
    navigable: false,
    href: null,
  },
  {
    key: "kalorimetry_overview",
    title: "Prehled",
    description: "Prehled kalorimetru.",
    sectionKey: "kalorimetry",
    sidebarLocation: "main",
    adminOnly: false,
    implemented: false,
    navigable: false,
    href: null,
  },
  {
    key: "kalorimetry_detail",
    title: "Detail",
    description: "Detail kalorimetru.",
    sectionKey: "kalorimetry",
    sidebarLocation: "main",
    adminOnly: false,
    implemented: false,
    navigable: false,
    href: null,
  },
  {
    key: "sprava_uzivatelu",
    title: "Sprava uzivatelu",
    description: "Administrace dashboard uctu.",
    sectionKey: null,
    sidebarLocation: "footer",
    adminOnly: true,
    implemented: false,
    navigable: false,
    href: null,
  },
  {
    key: "web_search_monitor",
    title: "Web search",
    description: "Administratorsky monitoring web search.",
    sectionKey: null,
    sidebarLocation: "footer",
    adminOnly: true,
    implemented: false,
    navigable: false,
    href: null,
  },
  {
    key: "expected_zero",
    title: "Expected zero",
    description: "Administratorske kontroly expected zero.",
    sectionKey: null,
    sidebarLocation: "footer",
    adminOnly: true,
    implemented: false,
    navigable: false,
    href: null,
  },
  {
    key: "vodomery_alerting",
    title: "Alerting vodomeru",
    description: "Administrace alert rules pro vodomery.",
    sectionKey: null,
    sidebarLocation: "footer",
    adminOnly: true,
    implemented: false,
    navigable: false,
    href: null,
  },
  {
    key: "scheduler_health",
    title: "Health scheduleru",
    description: "Stav scheduleru a jobu.",
    sectionKey: null,
    sidebarLocation: "footer",
    adminOnly: true,
    implemented: false,
    navigable: false,
    href: null,
  },
  {
    key: "vodomery_outlier_review",
    title: "Review outlieru",
    description: "Review outlier kandidatu pro vodomery.",
    sectionKey: null,
    sidebarLocation: "footer",
    adminOnly: true,
    implemented: false,
    navigable: false,
    href: null,
  },
  {
    key: "muj_ucet",
    title: "Muj ucet",
    description: "Prehled opravneni, sekci a pristupu.",
    sectionKey: null,
    sidebarLocation: "footer",
    adminOnly: false,
    implemented: true,
    navigable: true,
    href: "/ucet",
  },
];

const sectionMap = new Map(DASHBOARD_SECTIONS.map((section) => [section.key, section]));
const pageMap = new Map(DASHBOARD_PAGES.map((page) => [page.key, page]));


export function getSectionDefinition(sectionKey: string): DashboardSectionDefinition | null {
  return sectionMap.get(sectionKey) ?? null;
}


export function getPageDefinition(pageKey: string): DashboardPageDefinition | null {
  return pageMap.get(pageKey) ?? null;
}


export function hasSectionAccess(user: AuthUser, sectionKey: string): boolean {
  const section = getSectionDefinition(sectionKey);
  if (!section) {
    return false;
  }
  if (user.is_admin) {
    return true;
  }
  if (!user.allowed_sections.includes(sectionKey)) {
    return false;
  }
  if (section.requiresDevicePermissions && !user.allowed_devices.length) {
    return false;
  }
  return true;
}


export function hasPageAccess(user: AuthUser, pageKey: string): boolean {
  const page = getPageDefinition(pageKey);
  if (!page) {
    return false;
  }
  if (page.adminOnly) {
    return user.is_admin;
  }
  if (user.is_admin) {
    return true;
  }
  if (page.sectionKey) {
    if (!hasSectionAccess(user, page.sectionKey)) {
      return false;
    }
    return user.allowed_pages.includes(page.key);
  }
  return true;
}


export function canAccessDevice(user: AuthUser, identifikace: string): boolean {
  if (user.is_admin) {
    return true;
  }
  return user.allowed_devices.includes(identifikace);
}


export function getAccessibleSectionDefinitions(user: AuthUser): DashboardSectionDefinition[] {
  return DASHBOARD_SECTIONS.filter((section) => hasSectionAccess(user, section.key));
}


export function getAccessiblePageDefinitions(
  user: AuthUser,
  sidebarLocation?: SidebarLocation,
  options?: {
    implementedOnly?: boolean;
    navigableOnly?: boolean;
  },
): DashboardPageDefinition[] {
  const implementedOnly = Boolean(options?.implementedOnly);
  const navigableOnly = Boolean(options?.navigableOnly);

  return DASHBOARD_PAGES.filter((page) => {
    if (sidebarLocation && page.sidebarLocation !== sidebarLocation) {
      return false;
    }
    if (implementedOnly && !page.implemented) {
      return false;
    }
    if (navigableOnly && (!page.navigable || !page.href)) {
      return false;
    }
    return hasPageAccess(user, page.key);
  });
}


export function getDefaultDashboardHref(user: AuthUser): string {
  const firstImplementedPage = getAccessiblePageDefinitions(user, undefined, {
    implementedOnly: true,
    navigableOnly: true,
  })[0];

  return firstImplementedPage?.href ?? "/ucet";
}


export function canAccessVodomery(user: AuthUser): boolean {
  return hasPageAccess(user, "vodomery_overview");
}
