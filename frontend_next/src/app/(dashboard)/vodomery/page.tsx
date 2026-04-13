import { DeviceList } from "@/features/vodomery/components/device-list";
import { MetricsGrid } from "@/features/vodomery/components/metrics-grid";
import { OverviewInsights } from "@/features/vodomery/components/overview-insights";
import { BackendApiError } from "@/lib/api/backend";
import { getVodomeryDevices, getVodomeryOverviewMetrics } from "@/lib/api/vodomery";
import { requirePageAccess } from "@/lib/auth/guards";
import { requireSessionToken } from "@/lib/auth/session";
import { hasPageAccess } from "@/lib/permissions";


function formatDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}


function buildDefaultDateRange() {
  const endDate = new Date();
  const startDate = new Date(endDate);
  startDate.setDate(endDate.getDate() - 6);
  return {
    startDate: formatDate(startDate),
    endDate: formatDate(endDate),
  };
}


export default async function VodomeryOverviewPage() {
  const user = await requirePageAccess("vodomery_overview");
  const token = await requireSessionToken();
  const range = buildDefaultDateRange();
  const canOpenDetail = hasPageAccess(user, "vodomery_detail");

  try {
    const [devicesResponse, metrics] = await Promise.all([
      getVodomeryDevices(token, "VSE", 500),
      getVodomeryOverviewMetrics(token, {
        startDate: range.startDate,
        endDate: range.endDate,
        sourceFilter: "VSE",
      }),
    ]);

    return (
      <>
        <section className="content-card overview-hero">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Vodomery</p>
              <h1>Operativni prehled vodomeru</h1>
              <p className="section-copy">
                Prihlasen jako <strong>{user.username}</strong>. Stranka kombinuje rychly provozni souhrn a vstup do
                detailu jednotlivych zarizeni, bez primeho pristupu do DB.
              </p>
            </div>
            <div className="overview-meta-grid">
              <div className="overview-meta-card">
                <span className="meta-label">Sledovane obdobi</span>
                <strong>{range.startDate} az {range.endDate}</strong>
              </div>
              <div className="overview-meta-card">
                <span className="meta-label">Zdroj dat</span>
                <strong>{metrics.source_filter}</strong>
              </div>
              <div className="overview-meta-card">
                <span className="meta-label">Rozsah uzivatele</span>
                <strong>{devicesResponse.total} zarizeni</strong>
              </div>
            </div>
          </div>

          <MetricsGrid metrics={metrics} />
        </section>

        <OverviewInsights metrics={metrics} />

        <DeviceList
          devices={devicesResponse.devices}
          sourceFilter={devicesResponse.source_filter}
          canOpenDetail={canOpenDetail}
        />
      </>
    );
  } catch (error) {
    const message =
      error instanceof BackendApiError ? error.message : "Nepodarilo se nacist data z backend API pro vodomery.";

    return (
      <section className="content-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Vodomery</p>
            <h1>Prehled se nepodarilo nacist</h1>
            <p className="section-copy">
              Frontend route je dostupna, ale backend odpovedel chybou. Tohle je spravne misto pro dalsi ladeni API
              kontraktu, oprav permission modelu nebo deploymentu.
            </p>
          </div>
        </div>
        <p className="form-error">{message}</p>
      </section>
    );
  }
}
