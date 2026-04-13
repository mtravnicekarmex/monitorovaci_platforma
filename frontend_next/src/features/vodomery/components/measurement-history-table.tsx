import type { VodomeryMeasurementSeriesRow } from "@/lib/api/vodomery";


type MeasurementHistoryTableProps = {
  rows: VodomeryMeasurementSeriesRow[];
};


function formatDateTime(value: string): string {
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
  return value.toFixed(3);
}


function formatFlags(row: VodomeryMeasurementSeriesRow): string {
  const flags: string[] = [];
  if (!row.platne) flags.push("invalid");
  if (row.synthetic) flags.push("synthetic");
  if (row.gap_detected) flags.push("gap");
  if (row.reset_detected) flags.push("reset");
  if (row.nocni_odber) flags.push("night");
  return flags.length ? flags.join(", ") : "-";
}


export function MeasurementHistoryTable({ rows }: MeasurementHistoryTableProps) {
  if (!rows.length) {
    return <p className="empty-state">Ve zvolenem obdobi nejsou k dispozici zadna mereni.</p>;
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Cas</th>
            <th>Zdroj</th>
            <th>Objem</th>
            <th>Delta</th>
            <th>Interval [min]</th>
            <th>Flagy</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.identifikace}-${row.date}-${row.zdroj}`}>
              <td>{formatDateTime(row.date)}</td>
              <td>{row.zdroj}</td>
              <td>{formatNumber(row.objem)}</td>
              <td>{formatNumber(row.delta)}</td>
              <td>{row.interval_minutes}</td>
              <td>{formatFlags(row)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
