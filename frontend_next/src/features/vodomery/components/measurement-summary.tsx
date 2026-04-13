import { StatCard } from "@/components/ui/stat-card";
import type { VodomeryMeasurementSeriesRow } from "@/lib/api/vodomery";


type MeasurementSummaryProps = {
  rows: VodomeryMeasurementSeriesRow[];
  eventCount: number;
};


function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("cs-CZ", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(parsed);
}


function formatNumber(value: number | null): string {
  if (value === null || value === undefined) {
    return "-";
  }
  return `${value.toFixed(3)} m3`;
}


export function MeasurementSummary({ rows, eventCount }: MeasurementSummaryProps) {
  const latest = rows.length ? rows[rows.length - 1] : null;
  const validRows = rows.filter((row) => row.platne).length;
  const nightRows = rows.filter((row) => row.nocni_odber).length;

  return (
    <div className="stats-grid">
      <StatCard label="Posledni stav" value={formatNumber(latest?.objem ?? null)} hint={formatDate(latest?.date ?? null)} />
      <StatCard label="Mereni v 30 dnech" value={rows.length} hint={`${validRows} validnich bodu`} />
      <StatCard label="Nocni odbery" value={nightRows} hint="Pocet radku s priznakem nocniho odberu." />
      <StatCard label="Eventy v historii" value={eventCount} hint="Posledni event history endpoint pro toto zarizeni." />
    </div>
  );
}
