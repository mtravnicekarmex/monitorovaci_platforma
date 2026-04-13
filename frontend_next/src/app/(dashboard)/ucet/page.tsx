import { DASHBOARD_PAGES, getAccessiblePageDefinitions, getAccessibleSectionDefinitions } from "@/lib/dashboard-navigation";
import { requirePageAccess } from "@/lib/auth/guards";


export default async function AccountPage() {
  const user = await requirePageAccess("muj_ucet");
  const accessibleSections = getAccessibleSectionDefinitions(user);
  const accessiblePages = getAccessiblePageDefinitions(user);
  const implementedPages = accessiblePages.filter((page) => page.implemented);
  const plannedPages = accessiblePages.filter((page) => !page.implemented);
  const previewDevices = user.allowed_devices.slice(0, 18);
  const hiddenDeviceCount = Math.max(user.allowed_devices.length - previewDevices.length, 0);
  const futurePageCount = DASHBOARD_PAGES.filter((page) => !page.implemented && accessiblePages.some((item) => item.key === page.key)).length;

  return (
    <>
      <section className="content-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Muj ucet</p>
            <h1>Pristupy a dostupne moduly</h1>
            <p className="section-copy">
              Tahle stranka sklada dashboard podle stejnych prav jako Streamlit: sekce, stranky i seznam povolenych
              zarizeni.
            </p>
          </div>
          <div className="overview-meta-grid">
            <div className="overview-meta-card">
              <span className="meta-label">Role</span>
              <strong>{user.is_admin ? "Admin" : "Uzivatel"}</strong>
            </div>
            <div className="overview-meta-card">
              <span className="meta-label">Dostupne sekce</span>
              <strong>{user.is_admin ? "Vsechny" : accessibleSections.length}</strong>
            </div>
            <div className="overview-meta-card">
              <span className="meta-label">Dostupne stranky</span>
              <strong>{user.is_admin ? "Vsechny" : accessiblePages.length}</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="content-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Sekce</p>
            <h2>Sekce dostupne aktualnimu uzivateli</h2>
          </div>
        </div>

        <div className="access-grid">
          {accessibleSections.length ? (
            accessibleSections.map((section) => (
              <article key={section.key} className="access-card">
                <span className="meta-label">{section.label}</span>
                <strong>{section.key}</strong>
                <p className="section-copy">{section.description}</p>
              </article>
            ))
          ) : (
            <p className="empty-state">Tomuto uzivateli neni aktualne prirazena zadna sekce s vlastnimi zarizenimi.</p>
          )}
        </div>
      </section>

      <section className="content-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Stranky</p>
            <h2>Dostupne routy a dalsi moduly</h2>
          </div>
          <span className="pill">{futurePageCount} dalsich stranek ceka na migraci</span>
        </div>

        <div className="access-grid">
          {implementedPages.map((page) => (
            <article key={page.key} className="access-card">
              <span className="meta-label">Jiz dostupne v Next.js</span>
              <strong>{page.title}</strong>
              <p className="section-copy">{page.description}</p>
              <span className="status-chip is-live">{page.href ?? "Bez prime route"}</span>
            </article>
          ))}

          {plannedPages.map((page) => (
            <article key={page.key} className="access-card">
              <span className="meta-label">Dostupne pravem, frontend se teprve portuje</span>
              <strong>{page.title}</strong>
              <p className="section-copy">{page.description}</p>
              <span className="status-chip is-planned">Migrace ceka</span>
            </article>
          ))}
        </div>
      </section>

      <section className="content-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Zarizeni</p>
            <h2>Rozsah pristupu k zarizenim</h2>
          </div>
        </div>

        {user.is_admin ? (
          <p className="empty-state">Admin vidi vsechna zarizeni, frontend proto neomezuje identifikace seznamem.</p>
        ) : previewDevices.length ? (
          <>
            <div className="tag-list">
              {previewDevices.map((deviceId) => (
                <span key={deviceId} className="tag">
                  {deviceId}
                </span>
              ))}
            </div>
            {hiddenDeviceCount ? (
              <p className="table-note">Dalsich skrytych zarizeni: {hiddenDeviceCount}. Celkovy seznam drzi API.</p>
            ) : null}
          </>
        ) : (
          <p className="empty-state">Uzivatel nema prideleno zadne konkretni zarizeni.</p>
        )}
      </section>
    </>
  );
}
