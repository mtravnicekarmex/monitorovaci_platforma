import { redirect } from "next/navigation";

import { LoginForm } from "@/features/auth/components/login-form";
import { redirectIfAuthenticated } from "@/lib/auth/guards";
import { resolveSafeNextPath } from "@/lib/auth/next-path";


type LoginPageProps = {
  searchParams: Promise<{
    error?: string | string[];
    next?: string | string[];
    password?: string | string[];
    username?: string | string[];
  }>;
};


function getSingleValue(value: string | string[] | undefined): string {
  if (Array.isArray(value)) {
    return value[0] || "";
  }
  return value || "";
}


export default async function LoginPage({ searchParams }: LoginPageProps) {
  await redirectIfAuthenticated();
  const query = await searchParams;

  if (query.username !== undefined || query.password !== undefined) {
    const sanitizedParams = new URLSearchParams();
    const nextPath = resolveSafeNextPath(getSingleValue(query.next));
    const error = getSingleValue(query.error).trim();

    if (nextPath !== "/") {
      sanitizedParams.set("next", nextPath);
    }
    if (error) {
      sanitizedParams.set("error", error);
    }

    const sanitizedTarget = sanitizedParams.size ? `/login?${sanitizedParams.toString()}` : "/login";
    redirect(sanitizedTarget);
  }

  return (
    <main className="login-shell">
      <section className="hero-card">
        <p className="eyebrow">Monitoring Platform</p>
        <h1>Prvni migracni krok dashboardu do Next.js.</h1>
        <p className="lead-copy">
          Tato verze zamerne resi jen architektonicke minimum: login, session v cookie a prvni vodomerovy overview nad
          existujicim FastAPI.
        </p>
        <div className="hero-grid">
          <span className="hero-chip">FastAPI auth</span>
          <span className="hero-chip">HttpOnly cookie</span>
          <span className="hero-chip">SSR overview</span>
        </div>
      </section>

      <section className="login-card">
        <p className="eyebrow">Prihlaseni</p>
        <h2>Pokracovat do dashboardu</h2>
        <p className="helper-text">
          Formular vola existujici API endpoint a uklada access token pouze do serverem spravovane session cookie.
        </p>
        <LoginForm />
      </section>
    </main>
  );
}
