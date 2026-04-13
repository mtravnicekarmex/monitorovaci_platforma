import Link from "next/link";
import { redirect } from "next/navigation";

import { DetailMetadata } from "@/features/vodomery/components/detail-metadata";
import { EventHistoryTable } from "@/features/vodomery/components/event-history-table";
import { MeasurementHistoryTable } from "@/features/vodomery/components/measurement-history-table";
import { MeasurementSummary } from "@/features/vodomery/components/measurement-summary";
import { BackendApiError } from "@/lib/api/backend";
import {
  getVodomeryDeviceDetail,
  getVodomeryEventHistory,
  getVodomeryMeasurementSeries,
} from "@/lib/api/vodomery";
import { requirePageAccess } from "@/lib/auth/guards";
import { requireSessionToken } from "@/lib/auth/session";
import { canAccessDevice, getDefaultDashboardHref } from "@/lib/permissions";


type DetailPageProps = {
  params: Promise<{
    identifikace: string;
  }>;
};


function formatDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}


function buildDefaultDateRange() {
  const endDate = new Date();
  const startDate = new Date(endDate);
  startDate.setDate(endDate.getDate() - 29);
  return {
    startDate: formatDate(startDate),
    endDate: formatDate(endDate),
  };
}


export default async function VodomeryDetailPage({ params }: DetailPageProps) {
  const user = await requirePageAccess("vodomery_detail");
  const { identifikace } = await params;
  if (!canAccessDevice(user, identifikace)) {
    redirect(getDefaultDashboardHref(user));
  }
  const token = await requireSessionToken();
  const range = buildDefaultDateRange();

  try {
    const [detailResponse, measurementResponse, eventHistoryResponse] = await Promise.all([
      getVodomeryDeviceDetail(token, identifikace),
      getVodomeryMeasurementSeries(token, {
        identifikace,
        startDate: range.startDate,
        endDate: range.endDate,
        sourceFilter: "VSE",
      }),
      getVodomeryEventHistory(token, identifikace, 20),
    ]);

    if (!detailResponse.found) {
      return (
        <section className="content-card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Detail vodomeru</p>
              <h1>{identifikace}</h1>
              <p className="section-copy">Zvolene zarizeni API nevratilo. Identifikace pravdepodobne neexistuje.</p>
            </div>
            <Link href="/vodomery" className="ghost-button">
              Zpet na overview
            </Link>
          </div>
        </section>
      );
    }

    const measurementRows = [...measurementResponse.rows].sort((left, right) => left.date.localeCompare(right.date));
    const recentRows = [...measurementRows].reverse().slice(0, 40);

    return (
      <>
        <section className="content-card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Detail vodomeru</p>
              <h1>{identifikace}</h1>
              <p className="section-copy">
                Minimalni detail migrace nad FastAPI. Data kombinuji endpointy `device-detail`,
                `measurement-series` a `event-history`.
              </p>
            </div>
            <div className="detail-actions">
              <span className="pill">
                {range.startDate} az {range.endDate}
              </span>
              <Link href="/vodomery" className="ghost-button">
                Zpet na overview
              </Link>
            </div>
          </div>

          <MeasurementSummary rows={measurementRows} eventCount={eventHistoryResponse.total} />
        </section>

        <section className="content-card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Metadata</p>
              <h2>Detail odberneho mista</h2>
            </div>
          </div>
          <DetailMetadata detail={detailResponse.device} />
        </section>

        <section className="content-card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Mereni</p>
              <h2>Poslednich 40 radku z poslednich 30 dnu</h2>
            </div>
            <span className="pill">{measurementResponse.total} radku v API odpovedi</span>
          </div>
          <MeasurementHistoryTable rows={recentRows} />
        </section>

        <section className="content-card">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Event history</p>
              <h2>Poslednich 20 eventu</h2>
            </div>
            <span className="pill">{eventHistoryResponse.total} zaznamu</span>
          </div>
          <EventHistoryTable rows={eventHistoryResponse.rows} />
        </section>
      </>
    );
  } catch (error) {
    const message =
      error instanceof BackendApiError ? error.message : "Nepodarilo se nacist detail vodomeru z backend API.";

    return (
      <section className="content-card">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Detail vodomeru</p>
            <h1>{identifikace}</h1>
            <p className="section-copy">
              Frontend route existuje, ale backend vratil chybu. To je dalsi validacni krok migrace.
            </p>
          </div>
          <Link href="/vodomery" className="ghost-button">
            Zpet na overview
          </Link>
        </div>
        <p className="form-error">{message}</p>
      </section>
    );
  }
}
