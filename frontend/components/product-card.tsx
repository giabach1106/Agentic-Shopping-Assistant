"use client";

import Link from "next/link";
import { ArrowUpRight, BadgeCheck, FlaskConical, ShieldAlert, Star } from "lucide-react";

import type { SessionProduct } from "@/lib/contracts";

function formatMoney(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

export function ProductCard({
  product,
  sessionId,
}: {
  product: SessionProduct;
  sessionId: string;
}) {
  return (
    <article className="grid gap-5 rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)] transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-strong)] lg:grid-cols-[1.3fr_0.9fr]">
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">
              {product.storeName}
            </p>
            <h3 className="mt-2 text-2xl font-semibold text-[color:var(--text-strong)]">{product.title}</h3>
          </div>
          <div className="rounded-[1.3rem] bg-[color:var(--accent-soft)] px-4 py-3 text-right text-[color:var(--accent)]">
            <p className="text-xs uppercase tracking-[0.2em]">Trust</p>
            <p className="text-2xl font-semibold">{product.scientificScore.finalTrust}</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4 text-sm text-[color:var(--text-soft)]">
          <span className="text-lg font-semibold text-[color:var(--text-strong)]">{formatMoney(product.price)}</span>
          <span className="inline-flex items-center gap-1">
            <Star className="h-4 w-4 fill-current text-amber-500" />
            {product.rating ?? "n/a"}
          </span>
          <span>{product.shippingETA}</span>
          <span>{product.returnPolicy}</span>
        </div>

        <p className="text-sm leading-6 text-[color:var(--text-soft)]">{product.ingredientAnalysis.summary}</p>

        <div className="flex flex-wrap gap-2">
          {product.ingredientAnalysis.beneficialSignals.slice(0, 3).map((signal) => (
            <span
              key={signal.ingredient}
              className="inline-flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-700 dark:text-emerald-300"
            >
              <BadgeCheck className="h-3.5 w-3.5" />
              {signal.ingredient}
            </span>
          ))}
          {product.ingredientAnalysis.redFlags.slice(0, 2).map((signal) => (
            <span
              key={signal.ingredient}
              className="inline-flex items-center gap-2 rounded-full border border-rose-500/20 bg-rose-500/10 px-3 py-1 text-xs text-rose-700 dark:text-rose-300"
            >
              <ShieldAlert className="h-3.5 w-3.5" />
              {signal.ingredient}
            </span>
          ))}
        </div>
      </div>

      <div className="flex flex-col justify-between rounded-[1.7rem] border border-[color:var(--border)] bg-[color:var(--surface-muted)] p-5">
        <div className="space-y-3">
          <div className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] px-3 py-1 text-xs text-[color:var(--text-muted)]">
            <FlaskConical className="h-3.5 w-3.5" />
            Ingredient score {product.ingredientAnalysis.score}
          </div>
          <ul className="space-y-2 text-sm text-[color:var(--text-soft)]">
            {product.pros.slice(0, 2).map((pro) => (
              <li key={pro} className="rounded-2xl bg-[color:var(--surface)] px-3 py-2">
                {pro}
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-5 flex flex-col gap-3">
          <Link
            href={`/product/${product.productId}?session=${sessionId}`}
            className="inline-flex items-center justify-center gap-2 rounded-full bg-[color:var(--text-strong)] px-4 py-3 text-sm font-medium text-[color:var(--background)] transition hover:bg-[color:var(--accent)]"
          >
            Full analysis
            <ArrowUpRight className="h-4 w-4" />
          </Link>
          <a
            href={product.sourceUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center justify-center gap-2 rounded-full border border-[color:var(--border)] px-4 py-3 text-sm text-[color:var(--text-strong)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
          >
            Open source
            <ArrowUpRight className="h-4 w-4" />
          </a>
        </div>
      </div>
    </article>
  );
}
