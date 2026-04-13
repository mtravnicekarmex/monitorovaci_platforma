import { backendFetch } from "@/lib/api/backend";


export type AuthUser = {
  username: string;
  email: string | null;
  is_admin: boolean;
  is_active: boolean;
  allowed_sections: string[];
  allowed_pages: string[];
  allowed_devices: string[];
  last_login_at: string | null;
};

export type LoginResponse = {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: AuthUser;
};


export async function loginAgainstBackend(username: string, password: string): Promise<LoginResponse> {
  return backendFetch<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    jsonBody: {
      username,
      password,
    },
  });
}


export async function getCurrentUserFromBackend(token: string): Promise<AuthUser> {
  return backendFetch<AuthUser>("/api/v1/auth/me", {
    token,
  });
}


export async function logoutFromBackend(token: string): Promise<void> {
  await backendFetch<void>("/api/v1/auth/logout", {
    method: "POST",
    token,
  });
}
