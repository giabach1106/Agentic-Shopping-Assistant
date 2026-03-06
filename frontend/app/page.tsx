"use client";

import Image from "next/image";
import { useEffect, useMemo, useState } from "react";

function buildAuthorizeUrl() {
  const domain = process.env.NEXT_PUBLIC_COGNITO_DOMAIN!;
  const clientId = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID!;
  const redirectUri = process.env.NEXT_PUBLIC_COGNITO_REDIRECT_URI!;

  const params = new URLSearchParams({
    client_id: clientId,
    response_type: "code",
    scope: "openid email",
    redirect_uri: redirectUri,
  });

  return `https://${domain}/oauth2/authorize?${params.toString()}`;
}

async function exchangeCodeForTokens(code: string) {
  const domain = process.env.NEXT_PUBLIC_COGNITO_DOMAIN!;
  const clientId = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID!;
  const redirectUri = process.env.NEXT_PUBLIC_COGNITO_REDIRECT_URI!;

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: clientId,
    code,
    redirect_uri: redirectUri,
  });

  const res = await fetch(`https://${domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });

  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`Token exchange failed: ${res.status} ${txt}`);
  }

  return res.json() as Promise<{
    id_token: string;
    access_token: string;
    refresh_token?: string;
    expires_in: number;
    token_type: string;
  }>;
}

export default function Home() {
  const authorizeUrl = useMemo(() => buildAuthorizeUrl(), []);
  const [status, setStatus] = useState<
    "logged_out" | "exchanging" | "logged_in" | "error"
  >("logged_out");
  const [errorMsg, setErrorMsg] = useState<string>("");

  useEffect(() => {
    const url = new URL(window.location.href);
    const code = url.searchParams.get("code");

    const existing = localStorage.getItem("id_token");
    if (existing) setStatus("logged_in");

    if (!code) return;

    (async () => {
      try {
        setStatus("exchanging");
        const tokens = await exchangeCodeForTokens(code);

        localStorage.setItem("id_token", tokens.id_token);
        localStorage.setItem("access_token", tokens.access_token);

        // clean up the URL (remove ?code=...)
        url.searchParams.delete("code");
        window.history.replaceState({}, "", url.toString());

        setStatus("logged_in");
      } catch (e: any) {
        console.error(e);
        setErrorMsg(e?.message ?? "Unknown error");
        setStatus("error");
      }
    })();
  }, []);

  const login = () => {
    const domain = process.env.NEXT_PUBLIC_COGNITO_DOMAIN;
    const clientId = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID;
    const redirectUri = process.env.NEXT_PUBLIC_COGNITO_REDIRECT_URI;

    const loginUrl =
      `https://${domain}/oauth2/authorize` +
      `?response_type=code` +
      `&client_id=${encodeURIComponent(clientId ?? "")}` +
      `&redirect_uri=${encodeURIComponent(redirectUri ?? "")}` +
      `&scope=openid+email`;

    // helpful debug: if env is not loaded, you'll see "undefined" here
    alert(loginUrl);

    window.location.href = loginUrl;
  };

  const logout = () => {
    const domain = process.env.NEXT_PUBLIC_COGNITO_DOMAIN!;
    const clientId = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID!;
    const redirectUri = process.env.NEXT_PUBLIC_COGNITO_REDIRECT_URI!;
    localStorage.removeItem("id_token");
    localStorage.removeItem("access_token");
    window.location.href = `https://${domain}/logout?client_id=${encodeURIComponent(
      clientId
    )}&logout_uri=${encodeURIComponent(redirectUri)}`;
  };

  const idToken =
    typeof window !== "undefined" ? localStorage.getItem("id_token") : null;

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex min-h-screen w-full max-w-3xl flex-col items-center justify-center gap-10 py-32 px-16 bg-white dark:bg-black sm:items-start">
        <Image
          className="dark:invert"
          src="/next.svg"
          alt="Next.js logo"
          width={120}
          height={24}
          priority
        />

        <div className="flex flex-col items-center gap-3 text-center sm:items-start sm:text-left">
          <h1 className="text-4xl font-semibold tracking-tight text-black dark:text-zinc-50">
            Agentic Shopping Assistant
          </h1>
          <p className="max-w-md text-lg text-zinc-600 dark:text-zinc-400">
            {status === "logged_out" && "Login to start."}
            {status === "exchanging" && "Signing you in..."}
            {status === "logged_in" &&
              "Logged in ✅ (token stored locally for MVP)."}
            {status === "error" && "Login failed ❌"}
          </p>
          {status === "error" && (
            <p className="max-w-md text-sm text-red-600">{errorMsg}</p>
          )}
        </div>

        {status !== "logged_in" ? (
          <div className="flex flex-col gap-3">
            <button
              onClick={login}
              className="flex h-12 items-center justify-center rounded-full bg-black text-white px-6 text-base font-medium transition hover:bg-zinc-800"
            >
              Login with Cognito
            </button>

            <a
              className="text-sm text-zinc-600 underline"
              href={authorizeUrl}
              target="_self"
              rel="noreferrer"
            >
              (Fallback) Open authorize URL
            </a>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <button
              onClick={logout}
              className="flex h-12 items-center justify-center rounded-full border border-black/10 px-6 text-base font-medium transition hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
            >
              Logout
            </button>

            <details className="text-sm text-zinc-600 dark:text-zinc-400">
              <summary className="cursor-pointer">Show token (debug)</summary>
              <pre className="mt-2 max-w-2xl whitespace-pre-wrap break-all rounded-md bg-zinc-100 p-3 dark:bg-zinc-900">
                {idToken?.slice(0, 300)}...
              </pre>
            </details>
          </div>
        )}
      </main>
    </div>
  );
}