import Link from "next/link";
import type { ReactNode } from "react";

import type { AuthUser } from "@/lib/api/auth";
import { DASHBOARD_SECTIONS, type DashboardPageDefinition } from "@/lib/dashboard-navigation";


type DashboardShellProps = {
  user: AuthUser;
  mainPages: DashboardPageDefinition[];
  footerPages: DashboardPageDefinition[];
  children: ReactNode;
};


export function DashboardShell({ user, mainPages, footerPages, children }: DashboardShellProps) {
  const pagesBySection = DASHBOARD_SECTIONS.map((section) => ({
    section,
    pages: mainPages.filter((page) => page.sectionKey === section.key),
  })).filter((entry) => entry.pages.length > 0);

  return (
    <div className="dashboard-shell">
      <aside className="sidebar-card">
        <div>
          <p className="eyebrow">ARMEX Monitoring</p>
          <h1 className="sidebar-title">Prehled vodomeru a anomalii</h1>
          <p className="sidebar-copy">
            Internetovy frontend nad existujicim FastAPI. Zatim pokryva overview a detail vodomeru s cestou k dalsim
            provoznim modulum.
          </p>
        </div>

        <nav className="sidebar-nav">
          {pagesBySection.map(({ section, pages }) => (
            <div key={section.key} className="sidebar-section-group">
              <span className="sidebar-section-title">{section.label}</span>
              {pages.map((page) => (
                <Link key={page.key} href={page.href ?? "/"} className="sidebar-link">
                  {page.title}
                </Link>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-meta">
          <div>
            <span className="meta-label">Uzivatel</span>
            <strong>{user.username}</strong>
          </div>
          <div>
            <span className="meta-label">Role</span>
            <strong>{user.is_admin ? "Admin" : "Uzivatel"}</strong>
          </div>
          <div>
            <span className="meta-label">Email</span>
            <strong>{user.email || "-"}</strong>
          </div>
          <div>
            <span className="meta-label">Sekce</span>
            <strong>{user.is_admin ? "Vsechny" : user.allowed_sections.length}</strong>
          </div>
          <div>
            <span className="meta-label">Zarizeni</span>
            <strong>{user.is_admin ? "Vsechna" : user.allowed_devices.length}</strong>
          </div>
        </div>

        {footerPages.length ? (
          <nav className="sidebar-footer-nav">
            {footerPages.map((page) => (
              <Link key={page.key} href={page.href ?? "/"} className="ghost-button">
                {page.title}
              </Link>
            ))}
          </nav>
        ) : null}

        <form action="/api/auth/logout" method="post">
          <button type="submit" className="ghost-button">
            Odhlasit
          </button>
        </form>
      </aside>

      <main className="main-panel">{children}</main>
    </div>
  );
}
