'use client';

import { motion } from "framer-motion";
import { Clock, Search, ArrowRight } from 'lucide-react';
import Link from 'next/link';

export default function History() {
  const pastRuns = [
    {
      id: '1',
      query: 'Ergonomic chair under $150, 4+ stars, by Friday',
      date: '2 hours ago',
      results: 12
    },
    {
      id: '2',
      query: 'Best noise-canceling headphones for travel under $300',
      date: 'Yesterday',
      results: 8
    },
    {
      id: '3',
      query: 'Organic mineral sunscreen for sensitive skin',
      date: 'Oct 20, 2023',
      results: 24
    }
  ];

  return (
    <div className="flex-1 container mx-auto px-4 py-8 max-w-4xl">
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-zinc-900 mb-2">Search History</h1>
            <p className="text-zinc-500">Your past agent runs and shortlists.</p>
          </div>
          <button className="text-sm font-medium text-red-600 hover:text-red-700 transition-colors">
            Clear History
          </button>
        </div>

        <div className="space-y-4">
          {pastRuns.map((run) => (
            <Link 
              key={run.id} 
              href={`/results?q=${encodeURIComponent(run.query)}`}
              className="block bg-white p-6 rounded-2xl border border-zinc-200 shadow-sm hover:shadow-md hover:border-zinc-300 transition-all group"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-full bg-zinc-100 flex items-center justify-center shrink-0 text-zinc-500 group-hover:bg-zinc-900 group-hover:text-white transition-colors">
                    <Search className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-bold text-zinc-900 mb-1 line-clamp-1">{run.query}</h3>
                    <div className="flex items-center gap-4 text-sm text-zinc-500">
                      <span className="flex items-center gap-1"><Clock className="w-3.5 h-3.5" /> {run.date}</span>
                      <span>{run.results} results found</span>
                    </div>
                  </div>
                </div>
                <div className="shrink-0 text-zinc-400 group-hover:text-zinc-900 transition-colors">
                  <ArrowRight className="w-5 h-5" />
                </div>
              </div>
            </Link>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
