import type { VodomeryDeviceDetail } from "@/lib/api/vodomery";


type DetailMetadataProps = {
  detail: VodomeryDeviceDetail | null;
};


function displayValue(value: string | null | undefined): string {
  return value && value.trim() ? value : "-";
}


export function DetailMetadata({ detail }: DetailMetadataProps) {
  if (!detail) {
    return <p className="empty-state">Metadata zarizeni nebyla v API nalezena.</p>;
  }

  const fields = [
    ["Identifikace", detail.identifikace],
    ["Seriove cislo", detail.seriove_cislo],
    ["MBUS", detail.mbus],
    ["Objekt", detail.objekt],
    ["Patro", detail.patro],
    ["Mistnost", detail.mistnost],
    ["Umisteni", detail.umisteni],
    ["Napaji", detail.napaji],
    ["Koncovy odberatel", detail.koncovy_odberatel],
    ["Platnost cejchu", detail.platnost_cejchu],
    ["Poznamka", detail.poznamka],
  ] as const;

  return (
    <div className="metadata-grid">
      {fields.map(([label, value]) => (
        <div key={label} className="metadata-item">
          <span className="meta-label">{label}</span>
          <strong>{displayValue(value)}</strong>
        </div>
      ))}
    </div>
  );
}
