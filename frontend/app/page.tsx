"use client";

import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Sparkles,
  ArrowRight,
  Star,
  MessageSquare,
} from "lucide-react";
import { motion } from "framer-motion";
import FloatingIcons from "@/components/FloatingIcons";

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
  const router = useRouter();
  const authorizeUrl = useMemo(() => buildAuthorizeUrl(), []);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<
    "logged_out" | "exchanging" | "logged_in" | "error"
  >("logged_out");
  const [errorMsg, setErrorMsg] = useState("");

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

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      router.push(`/results?q=${encodeURIComponent(query)}`);
    }
  };

  const presets = [
    "Carbon fiber tennis racket under $200, 4.5+ stars",
    "Best trail running shoes for wide feet under $150",
    "Adjustable dumbbells set up to 50lbs, fast shipping",
  ];

  const handlePresetClick = (preset: string) => {
    setQuery(preset);
    router.push(`/results?q=${encodeURIComponent(preset)}`);
  };

  const suggestedProducts = [
    {
      id: "1",
      name: "ProStaff RF97 Autograph",
      category: "Tennis",
      price: 249.0,
      rating: 4.8,
      reviews: 1240,
      image:
        "https://images.unsplash.com/photo-1595435934249-5df7ed86e1c0?auto=format&fit=crop&q=80&w=400",
      shortReview:
        "Exceptional control and stability. Heavy frame suited for advanced players.",
    },
    {
      id: "2",
      name: "SpeedCross 6 Trail Shoes",
      category: "Running",
      price: 140.0,
      rating: 4.6,
      reviews: 890,
      image:
        "https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&q=80&w=400",
      shortReview:
        "Aggressive grip for muddy terrain. Snug fit, might need half size up.",
    },
    {
      id: "3",
      name: "PowerBlock Elite EXP",
      category: "Fitness",
      price: 359.0,
      rating: 4.9,
      reviews: 3100,
      image:
        "https://images.unsplash.com/photo-1586401100295-7a8096fd231a?auto=format&fit=crop&q=80&w=400",
      shortReview:
        "Space-saving and durable. Quick weight changes up to 50 lbs per hand.",
    },
    {
      id: "4",
      name: "Manduka PRO Yoga Mat",
      category: "Yoga",
      price: 129.0,
      rating: 4.7,
      reviews: 2150,
      image:
        "https://images.unsplash.com/photo-1601925260368-ae2f83cf8b7f?auto=format&fit=crop&q=80&w=400",
      shortReview:
        "Unmatched density and cushion. Lifetime guarantee, but heavy to carry.",
    },
    {
      id: "5",
      name: "Giro Aether MIPS Helmet",
      category: "Cycling",
      price: 299.0,
      rating: 4.8,
      reviews: 420,
      image:
        "https://images.unsplash.com/photo-1565183928294-7063f23ce0f8?auto=format&fit=crop&q=80&w=400",
      shortReview:
        "Incredible ventilation and safety tech. Premium price but worth it.",
    },
    {
      id: "6",
      name: "Everlast Pro Style Gloves",
      category: "Boxing",
      price: 45.0,
      rating: 4.5,
      reviews: 5600,
      image:
        "https://images.unsplash.com/photo-1549719386-74dfcbf7dbed?auto=format&fit=crop&q=80&w=400",
      shortReview:
        "Great starter gloves. Good wrist support and durable synthetic leather.",
    },
  ];

  const idToken =
    typeof window !== "undefined" ? localStorage.getItem("id_token") : null;

  return (
    <div className="flex min-h-screen flex-col items-center justify-start bg-zinc-50 px-4 pt-12 pb-12 font-sans md:px-8 md:pt-20 dark:bg-black">
      <div className="relative mx-auto w-full max-w-5xl">
        <FloatingIcons />

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8 w-full text-center"
        >
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-orange-200 bg-orange-50 px-3 py-1 text-xs font-medium text-orange-700">
            <Sparkles className="h-3 w-3 text-orange-500" />
            <span>AI Shopping Assistant</span>
          </div>

          <h1 className="mb-3 text-3xl font-bold tracking-tight text-zinc-900 md:text-5xl dark:text-zinc-50">
            Find your perfect gear.
            <br className="hidden md:block" />
            <span className="text-zinc-400">Just ask.</span>
          </h1>

          <p className="mx-auto max-w-xl text-base text-zinc-600 dark:text-zinc-400">
            Tell me what you need, your budget, and skill level. I&apos;ll
            compare prices, check reviews, and find the best options across the
            web.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="z-10 mx-auto w-full max-w-2xl"
        >
          {status !== "logged_in" ? (
            <div className="mb-6 flex flex-col items-center gap-3 rounded-2xl border border-zinc-200 bg-white p-6 text-center shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
              <p className="text-base text-zinc-700 dark:text-zinc-300">
                {status === "logged_out" && "Login to start."}
                {status === "exchanging" && "Signing you in..."}
                {status === "error" && "Login failed."}
              </p>

              {status === "error" && (
                <p className="max-w-md text-sm text-red-600">{errorMsg}</p>
              )}

              <div className="flex flex-col gap-3 sm:flex-row">
                <button
                  onClick={login}
                  className="rounded-xl bg-zinc-900 px-5 py-3 text-sm font-medium text-white transition hover:bg-zinc-800"
                >
                  Login with Cognito
                </button>

                <a
                  className="rounded-xl border border-zinc-300 px-5 py-3 text-sm font-medium text-zinc-700 transition hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                  href={authorizeUrl}
                  target="_self"
                  rel="noreferrer"
                >
                  Fallback Login URL
                </a>
              </div>
            </div>
          ) : (
            <div className="mb-6 flex flex-col items-center gap-3 rounded-2xl border border-zinc-200 bg-white p-6 text-center shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
              <p className="text-base text-zinc-700 dark:text-zinc-300">
                Logged in ✅
              </p>

              <div className="flex flex-col gap-3 sm:flex-row">
                <button
                  onClick={logout}
                  className="rounded-xl border border-black/10 px-5 py-3 text-sm font-medium transition hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
                >
                  Logout
                </button>
              </div>

              <details className="text-left text-sm text-zinc-600 dark:text-zinc-400">
                <summary className="cursor-pointer">Show token (debug)</summary>
                <pre className="mt-2 max-w-2xl whitespace-pre-wrap break-all rounded-md bg-zinc-100 p-3 dark:bg-zinc-900">
                  {idToken?.slice(0, 300)}...
                </pre>
              </details>
            </div>
          )}

          <form onSubmit={handleSearch} className="group relative">
            <div className="pointer-events-none absolute inset-y-0 left-4 flex items-center">
              <MessageSquare className="h-5 w-5 text-orange-500" />
            </div>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask me anything about sports gear..."
              className="w-full rounded-2xl border-2 border-zinc-200 bg-white py-4 pl-12 pr-32 text-base shadow-sm outline-none transition-all focus:border-orange-500 focus:ring-4 focus:ring-orange-500/10 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-50"
            />
            <div className="absolute inset-y-2 right-2 flex items-center">
              <button
                type="submit"
                disabled={!query.trim()}
                className="flex items-center gap-2 rounded-xl bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Ask Agent
                <Sparkles className="h-3 w-3" />
              </button>
            </div>
          </form>

          <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
            <span className="mr-1 text-xs text-zinc-500">Try:</span>
            {presets.map((preset, i) => (
              <button
                key={i}
                type="button"
                onClick={() => handlePresetClick(preset)}
                className="rounded-lg border border-zinc-200 bg-white/80 px-3 py-1.5 text-xs font-medium text-zinc-600 backdrop-blur-sm transition-colors hover:border-orange-300 hover:text-orange-700 dark:border-zinc-700 dark:bg-zinc-900/80 dark:text-zinc-300"
              >
                {preset}
              </button>
            ))}
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="z-10 mt-16 w-full"
        >
          <div className="mb-6 flex items-center justify-between">
            <h2 className="text-xl font-bold text-zinc-900 dark:text-zinc-50">
              Suggested for you
            </h2>
            <button
              onClick={() => router.push("/explore")}
              className="flex items-center gap-1 text-sm font-medium text-orange-600 hover:text-orange-700"
            >
              View all <ArrowRight className="h-4 w-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
            {suggestedProducts.map((product) => (
              <div
                key={product.id}
                onClick={() => router.push(`/product/${product.id}`)}
                className="group flex cursor-pointer flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white transition-all hover:border-orange-300 hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900"
              >
                <div className="relative h-48 w-full bg-zinc-100 dark:bg-zinc-800">
                  <Image
                    src={product.image}
                    alt={product.name}
                    fill
                    className="object-cover transition-transform duration-500 group-hover:scale-105"
                    referrerPolicy="no-referrer"
                  />
                  <div className="absolute top-3 left-3 rounded-md bg-white/90 px-2 py-1 text-xs font-bold text-zinc-800 backdrop-blur-sm dark:bg-zinc-900/90 dark:text-zinc-100">
                    {product.category}
                  </div>
                </div>

                <div className="flex flex-1 flex-col p-5">
                  <div className="mb-2 flex items-start justify-between gap-3">
                    <h3 className="line-clamp-1 font-bold text-zinc-900 dark:text-zinc-50">
                      {product.name}
                    </h3>
                    <span className="font-bold text-orange-600">
                      ${product.price}
                    </span>
                  </div>

                  <div className="mb-3 flex items-center gap-1">
                    <Star className="h-4 w-4 fill-amber-400 text-amber-400" />
                    <span className="text-sm font-bold text-zinc-700 dark:text-zinc-300">
                      {product.rating}
                    </span>
                    <span className="text-xs text-zinc-500">
                      ({product.reviews})
                    </span>
                  </div>

                  <p className="mt-auto line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">
                    &quot;{product.shortReview}&quot;
                  </p>
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  );
}