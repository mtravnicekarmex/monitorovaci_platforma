import { StatCard } from "@/components/ui/stat-card";
import type { VodomeryOverviewMetrics } from "@/lib/api/vodomery";


type MetricsGridProps = {
  metrics: VodomeryOverviewMetrics;
};


export function MetricsGrid({ metrics }: MetricsGridProps) {
  const numberFormat = new Intl.NumberFormat("cs-CZ");

  return (
    <div className="stats-grid">
      <StatCard
        label="Sledovana zarizeni"
        value={numberFormat.format(metrics.zarizeni)}
        hint="Unikatni vodomery v aktualnim rozsahu."
      />
      <StatCard
        label="Zpracovana mereni"
        value={numberFormat.format(metrics.mereni)}
        hint="Importovana mereni dostupna v API."
      />
      <StatCard
        label="Anomalni score"
        value={numberFormat.format(metrics.anomalie)}
        hint="Zaznamy scoringu aktivniho modelu v danem okne."
      />
      <StatCard
        label="Aktivni eventy"
        value={numberFormat.format(metrics.aktivni_eventy)}
        hint="Aktivne otevrene situace nad alerting limitem."
      />
    </div>
  );
}
