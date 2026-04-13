import type { VodomeryOverviewMetrics } from "@/lib/api/vodomery";


type OverviewInsightsProps = {
  metrics: VodomeryOverviewMetrics;
};


function formatDecimal(value: number, digits = 1): string {
  return new Intl.NumberFormat("cs-CZ", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}


function getLoadTone(value: number, warnThreshold: number, alertThreshold: number): string {
  if (value >= alertThreshold) {
    return "is-alert";
  }
  if (value >= warnThreshold) {
    return "is-watch";
  }
  return "is-calm";
}


export function OverviewInsights({ metrics }: OverviewInsightsProps) {
  const measurementsPerDevice = metrics.zarizeni ? metrics.mereni / metrics.zarizeni : 0;
  const anomalyShare = metrics.mereni ? (metrics.anomalie / metrics.mereni) * 100 : 0;
  const activeEventsPer100 = metrics.zarizeni ? (metrics.aktivni_eventy / metrics.zarizeni) * 100 : 0;

  const cards = [
    {
      label: "Hustota dat",
      value: `${formatDecimal(measurementsPerDevice)} mereni / zarizeni`,
      copy: "Rychly signal, jestli je 7denni okno dostatecne saturovane pro operativni pohled.",
      tone: getLoadTone(measurementsPerDevice, 30, 80),
    },
    {
      label: "Podil anomalii",
      value: `${formatDecimal(anomalyShare)} %`,
      copy: "Pomaha odlisit bezny provoz od dne, kdy se v datech nebo odberu neco zmenilo.",
      tone: getLoadTone(anomalyShare, 1.5, 4),
    },
    {
      label: "Aktivni eventova zatez",
      value: `${formatDecimal(activeEventsPer100)} / 100 zarizeni`,
      copy: "Vyssi hodnota znamena, ze ma smysl jit po eventech a detailu pred dalsim rozsirenim datoveho okna.",
      tone: getLoadTone(activeEventsPer100, 8, 20),
    },
  ];

  return (
    <section className="overview-insights-grid">
      {cards.map((card) => (
        <article key={card.label} className={`insight-card ${card.tone}`}>
          <span className="meta-label">{card.label}</span>
          <strong className="insight-value">{card.value}</strong>
          <p className="insight-copy">{card.copy}</p>
        </article>
      ))}
    </section>
  );
}
