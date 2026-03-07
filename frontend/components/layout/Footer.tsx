export function Footer() {
  return (
    <footer className="border-t border-zinc-200 bg-white py-4 mt-auto">
      <div className="container mx-auto px-4 max-w-7xl flex flex-col md:flex-row items-center justify-between gap-2 text-xs text-zinc-500">
        <p>© {new Date().getFullYear()} AgentCart. All rights reserved.</p>
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            Systems Operational
          </span>
          <p className="italic">Note: We may earn a commission on sponsored links.</p>
        </div>
      </div>
    </footer>
  );
}
