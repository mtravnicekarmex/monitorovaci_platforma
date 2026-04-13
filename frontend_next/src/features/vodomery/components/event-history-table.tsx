import type { VodomeryEventHistoryRow } from "@/lib/api/vodomery";


type EventHistoryTableProps = {
  rows: VodomeryEventHistoryRow[];
};


function formatDateTime(value: string | null): string {
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


export function EventHistoryTable({ rows }: EventHistoryTableProps) {
  if (!rows.length) {
    return <p className="empty-state">API pro tento vodomer zatim nevratilo zadnou historii eventu.</p>;
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Typ</th>
            <th>Zacatek</th>
            <th>Konec</th>
            <th>Trvani [min]</th>
            <th>Max Z</th>
            <th>Avg Z</th>
            <th>Severity</th>
            <th>Stav</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.event_type}-${row.start_time}-${index}`}>
              <td>{row.event_type}</td>
              <td>{formatDateTime(row.start_time)}</td>
              <td>{formatDateTime(row.end_time)}</td>
              <td>{row.duration_minutes}</td>
              <td>{row.max_z_score.toFixed(2)}</td>
              <td>{row.avg_z_score.toFixed(2)}</td>
              <td>{row.severity}</td>
              <td>{row.is_active ? "Aktivni" : row.resolved ? "Vyreseny" : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
