"use client";

import Link from "next/link";
import { useState } from "react";


type DeviceListProps = {
  devices: string[];
  sourceFilter: string;
  canOpenDetail: boolean;
};


function getDeviceGroup(deviceId: string): string {
  const separatorIndex = deviceId.indexOf("_");
  if (separatorIndex > 0) {
    return deviceId.slice(0, separatorIndex);
  }

  return deviceId.slice(0, 1) || "Ostatni";
}


export function DeviceList({ devices, sourceFilter, canOpenDetail }: DeviceListProps) {
  const [query, setQuery] = useState("");
  const [selectedGroup, setSelectedGroup] = useState("ALL");

  if (!devices.length) {
    return <p className="empty-state">API nevratilo zadna zarizeni pro aktualniho uzivatele.</p>;
  }

  const normalizedQuery = query.trim().toLowerCase();
  const groupCounts = devices.reduce<Record<string, number>>((accumulator, deviceId) => {
    const group = getDeviceGroup(deviceId);
    accumulator[group] = (accumulator[group] ?? 0) + 1;
    return accumulator;
  }, {});

  const groups = Object.entries(groupCounts)
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([group, count]) => ({ group, count }));

  const filteredDevices = devices.filter((deviceId) => {
    const matchesGroup = selectedGroup === "ALL" || getDeviceGroup(deviceId) === selectedGroup;
    const matchesQuery = !normalizedQuery || deviceId.toLowerCase().includes(normalizedQuery);
    return matchesGroup && matchesQuery;
  });

  const visibleDevices = filteredDevices.slice(0, 160);

  return (
    <div className="device-list-card">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Operativni seznam</p>
          <h2>Pracovni seznam vodomeru</h2>
          <p className="section-copy">
            Vyhledavani a rychly vstup do detailu konkretniho meridla. Frontend zustava cisty klient nad FastAPI.
          </p>
        </div>
        <span className="pill">{devices.length} zarizeni</span>
      </div>

      <div className="device-toolbar">
        <label className="field search-field">
          <span className="meta-label">Hledat identifikaci</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="text-input search-input"
            placeholder="Napriklad E_V4 nebo A_V3"
          />
        </label>

        <div className="device-summary-strip">
          <div className="summary-chip">
            <span className="meta-label">Po filtru</span>
            <strong>{filteredDevices.length}</strong>
          </div>
          <div className="summary-chip">
            <span className="meta-label">Skupin</span>
            <strong>{groups.length}</strong>
          </div>
          <div className="summary-chip">
            <span className="meta-label">Zdroj</span>
            <strong>{sourceFilter}</strong>
          </div>
        </div>
      </div>

      <div className="filter-row">
        <button
          type="button"
          className={`filter-chip ${selectedGroup === "ALL" ? "is-active" : ""}`}
          onClick={() => setSelectedGroup("ALL")}
        >
          Vsechny ({devices.length})
        </button>
        {groups.map(({ group, count }) => (
          <button
            key={group}
            type="button"
            className={`filter-chip ${selectedGroup === group ? "is-active" : ""}`}
            onClick={() => setSelectedGroup(group)}
          >
            {group} ({count})
          </button>
        ))}
      </div>

      <div className="table-wrap">
        <table className="data-table device-table">
          <thead>
            <tr>
              <th>Identifikace</th>
              <th>Skupina</th>
              <th>Zdroj</th>
              <th>Akce</th>
            </tr>
          </thead>
          <tbody>
            {visibleDevices.map((deviceId) => {
              const group = getDeviceGroup(deviceId);

              return (
                <tr key={deviceId}>
                  <td>
                    <span className="device-id">{deviceId}</span>
                    <span className="device-caption">
                      {canOpenDetail
                        ? "Rychly prechod na trend, historii mereni a eventy."
                        : "Uzivatel ma overview, ale detail zarizeni mu neni povolen."}
                    </span>
                  </td>
                  <td>{group}</td>
                  <td>{sourceFilter}</td>
                  <td>
                    {canOpenDetail ? (
                      <Link href={`/vodomery/${encodeURIComponent(deviceId)}`} className="table-link">
                        Otevrit detail
                      </Link>
                    ) : (
                      <span className="table-muted">Detail neni povolen</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {!filteredDevices.length ? (
        <p className="empty-state">Zadna zarizeni neodpovidaji aktualnimu hledani nebo zvolene skupine.</p>
      ) : null}
      {filteredDevices.length > visibleDevices.length ? (
        <p className="table-note">
          Zobrazuji prvnich {visibleDevices.length} zaznamu z {filteredDevices.length}. Pro uzsi vyber pouzij hledani.
        </p>
      ) : null}
    </div>
  );
}
