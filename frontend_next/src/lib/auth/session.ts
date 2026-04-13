import { getCurrentUserFromBackend, type AuthUser } from "@/lib/api/auth";
import { BackendApiError } from "@/lib/api/backend";
import { getSessionToken } from "@/lib/auth/cookies";


export async function getCurrentUser(): Promise<AuthUser | null> {
  const token = await getSessionToken();
  if (!token) {
    return null;
  }

  try {
    return await getCurrentUserFromBackend(token);
  } catch (error) {
    if (error instanceof BackendApiError && error.status === 401) {
      return null;
    }
    throw error;
  }
}


export async function requireSessionToken(): Promise<string> {
  const token = await getSessionToken();
  if (!token) {
    throw new Error("Missing session token.");
  }
  return token;
}
