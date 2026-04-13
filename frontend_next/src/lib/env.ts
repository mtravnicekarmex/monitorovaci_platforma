function readRequiredEnv(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}


export function getBackendApiBaseUrl(): string {
  return readRequiredEnv("BACKEND_API_BASE_URL").replace(/\/+$/, "");
}


export function getSessionCookieName(): string {
  return process.env.SESSION_COOKIE_NAME?.trim() || "monitoring_access_token";
}


export function getAppTitle(): string {
  return process.env.NEXT_PUBLIC_APP_TITLE?.trim() || "Monitoring Platform";
}
