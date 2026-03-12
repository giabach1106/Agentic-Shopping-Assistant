export function Footer() {
  return (
    <footer className="border-t border-[color:var(--border)] bg-[color:var(--surface)]/88 backdrop-blur-xl">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-4 py-6 text-sm text-[color:var(--text-muted)] md:flex-row md:items-center md:justify-between md:px-8">
        <p>AgentCart hackathon build. Session-first, evidence-first, supplements-first.</p>
        <div className="flex items-center gap-4">
          <span className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border)] bg-[color:var(--surface-strong)] px-3 py-1">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            Systems operational
          </span>
          <span>Checkout automation always stops before payment.</span>
        </div>
      </div>
    </footer>
  );
}
