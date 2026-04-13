import { LoginForm } from "@/features/auth/components/login-form";
import { redirectIfAuthenticated } from "@/lib/auth/guards";


export default async function LoginPage() {
  await redirectIfAuthenticated();

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
        <h2>Pokračovat do dashboardu</h2>
        <p className="helper-text">
          Formulář volá existující API endpoint a ukládá access token pouze do serverem spravované session cookie.
        </p>
        <LoginForm />
      </section>
    </main>
  );
}
