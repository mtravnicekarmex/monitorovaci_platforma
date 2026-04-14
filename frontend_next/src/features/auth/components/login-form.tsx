"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, useTransition } from "react";

import { resolveSafeNextPath } from "@/lib/auth/next-path";


type LoginFormState = {
  username: string;
  password: string;
};


export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [formState, setFormState] = useState<LoginFormState>({
    username: "",
    password: "",
  });
  const [errorMessage, setErrorMessage] = useState("");

  const nextPath = resolveSafeNextPath(searchParams.get("next"));
  const urlErrorMessage = searchParams.get("error") || "";

  function updateField(field: keyof LoginFormState, value: string) {
    setFormState((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage("");

    startTransition(async () => {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: formState.username,
          password: formState.password,
        }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        setErrorMessage(payload?.detail || "Prihlaseni selhalo.");
        return;
      }

      router.replace(nextPath);
      router.refresh();
    });
  }

  return (
    <form action="/api/auth/login" className="login-form" method="post" onSubmit={handleSubmit}>
      <input name="next" type="hidden" value={nextPath} />

      <label className="field">
        <span>Uzivatelske jmeno</span>
        <input
          autoComplete="username"
          className="text-input"
          name="username"
          onChange={(event) => updateField("username", event.target.value)}
          required
          value={formState.username}
        />
      </label>

      <label className="field">
        <span>Heslo</span>
        <input
          autoComplete="current-password"
          className="text-input"
          name="password"
          onChange={(event) => updateField("password", event.target.value)}
          required
          type="password"
          value={formState.password}
        />
      </label>

      {errorMessage || urlErrorMessage ? <p className="form-error">{errorMessage || urlErrorMessage}</p> : null}

      <button className="primary-button" disabled={isPending} type="submit">
        {isPending ? "Prihlasuji..." : "Prihlasit"}
      </button>
    </form>
  );
}
