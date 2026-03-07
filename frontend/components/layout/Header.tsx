'use client';

import Link from 'next/link';
import { Search, User, Settings, LogOut, History, ShoppingCart } from 'lucide-react';

export function Header() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-zinc-200 bg-white/80 backdrop-blur-md">
      <div className="container mx-auto px-4 h-14 flex items-center justify-between max-w-7xl">
        <Link href="/" className="flex items-center gap-2">
          <div className="bg-orange-600 text-white p-1 rounded-lg">
            <ShoppingCart className="w-4 h-4" />
          </div>
          <span className="font-bold text-base tracking-tight">AgentCart</span>
        </Link>
        
        <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-zinc-600">
          <Link href="/" className="hover:text-zinc-900 transition-colors flex items-center gap-1.5">
            <Search className="w-4 h-4" />
            New Search
          </Link>
          <Link href="/history" className="hover:text-zinc-900 transition-colors flex items-center gap-1.5">
            <History className="w-4 h-4" />
            History
          </Link>
          <Link href="/preferences" className="hover:text-zinc-900 transition-colors flex items-center gap-1.5">
            <Settings className="w-4 h-4" />
            Preferences
          </Link>
        </nav>

        <div className="flex items-center gap-3">
          <Link href="/login" className="text-sm font-medium text-zinc-600 hover:text-zinc-900 hidden sm:block">
            Log in
          </Link>
          <Link href="/signup" className="text-sm font-medium bg-orange-600 text-white px-3 py-1.5 rounded-lg hover:bg-orange-700 transition-colors">
            Sign up
          </Link>
        </div>
      </div>
    </header>
  );
}
