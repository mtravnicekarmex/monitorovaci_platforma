export function resolveSafeNextPath(value: string | null | undefined): string {
  const candidate = String(value || "").trim();

  if (!candidate.startsWith("/") || candidate.startsWith("//")) {
    return "/";
  }

  return candidate;
}
