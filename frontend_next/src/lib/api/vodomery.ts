import { backendFetch } from "@/lib/api/backend";


export type VodomeryOverviewMetrics = {
  source_filter: string;
  start_date: string;
  end_date: string;
  zarizeni: number;
  mereni: number;
  anomalie: number;
  aktivni_eventy: number;
};

export type VodomeryDeviceListResponse = {
  source_filter: string;
  total: number;
  devices: string[];
};

export type VodomeryDeviceDetail = {
  identifikace: string;
  seriove_cislo: string | null;
  mbus: string | null;
  objekt: string | null;
  patro: string | null;
  mistnost: string | null;
  umisteni: string | null;
  napaji: string | null;
  koncovy_odberatel: string | null;
  platnost_cejchu: string | null;
  poznamka: string | null;
};

export type VodomeryDeviceDetailResponse = {
  identifikace: string;
  found: boolean;
  device: VodomeryDeviceDetail | null;
};

export type VodomeryMeasurementSeriesRow = {
  date: string;
  identifikace: string;
  seriove_cislo: string;
  zdroj: string;
  objem: number;
  delta: number | null;
  platne: boolean;
  interval_minutes: number;
  day_of_week: number;
  slot: number;
  synthetic: boolean;
  nocni_odber: boolean;
  gap_detected: boolean;
  reset_detected: boolean;
};

export type VodomeryMeasurementSeriesResponse = {
  source_filter: string;
  identifikace: string;
  start_date: string;
  end_date: string;
  total: number;
  rows: VodomeryMeasurementSeriesRow[];
};

export type VodomeryEventHistoryRow = {
  event_type: string;
  start_time: string;
  end_time: string | null;
  duration_minutes: number;
  max_z_score: number;
  avg_z_score: number;
  severity: string;
  is_active: boolean;
  resolved: boolean;
};

export type VodomeryEventHistoryResponse = {
  identifikace: string;
  total: number;
  rows: VodomeryEventHistoryRow[];
};


export async function getVodomeryDevices(
  token: string,
  sourceFilter = "VSE",
  limit = 500,
): Promise<VodomeryDeviceListResponse> {
  return backendFetch<VodomeryDeviceListResponse>("/api/v1/vodomery/devices", {
    token,
    query: {
      source: sourceFilter,
      limit,
    },
  });
}


export async function getVodomeryOverviewMetrics(
  token: string,
  params: {
    startDate: string;
    endDate: string;
    sourceFilter?: string;
  },
): Promise<VodomeryOverviewMetrics> {
  return backendFetch<VodomeryOverviewMetrics>("/api/v1/vodomery/overview-metrics", {
    token,
    query: {
      start_date: params.startDate,
      end_date: params.endDate,
      source: params.sourceFilter ?? "VSE",
    },
  });
}


export async function getVodomeryDeviceDetail(
  token: string,
  identifikace: string,
): Promise<VodomeryDeviceDetailResponse> {
  return backendFetch<VodomeryDeviceDetailResponse>("/api/v1/vodomery/device-detail", {
    token,
    query: {
      identifikace,
    },
  });
}


export async function getVodomeryMeasurementSeries(
  token: string,
  params: {
    identifikace: string;
    startDate: string;
    endDate: string;
    sourceFilter?: string;
  },
): Promise<VodomeryMeasurementSeriesResponse> {
  return backendFetch<VodomeryMeasurementSeriesResponse>("/api/v1/vodomery/measurement-series", {
    token,
    query: {
      identifikace: params.identifikace,
      start_date: params.startDate,
      end_date: params.endDate,
      source: params.sourceFilter ?? "VSE",
    },
  });
}


export async function getVodomeryEventHistory(
  token: string,
  identifikace: string,
  limit = 20,
): Promise<VodomeryEventHistoryResponse> {
  return backendFetch<VodomeryEventHistoryResponse>("/api/v1/vodomery/event-history", {
    token,
    query: {
      identifikace,
      limit,
    },
  });
}
