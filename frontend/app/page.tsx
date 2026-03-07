'use client';

import { useState } from 'react';
import { Search, Sparkles, ArrowRight, Clock, Star, ShieldCheck, MessageSquare } from 'lucide-react';
import { motion } from 'framer-motion';
import { useRouter } from 'next/navigation';
import FloatingIcons from '@/components/FloatingIcons';
import Image from 'next/image';

export default function Home() {
  const [query, setQuery] = useState('');
  const router = useRouter();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      router.push(`/results?q=${encodeURIComponent(query)}`);
    }
  };

  const presets = [
    "Carbon fiber tennis racket under $200, 4.5+ stars",
    "Best trail running shoes for wide feet under $150",
    "Adjustable dumbbells set up to 50lbs, fast shipping"
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
      price: 249.00,
      rating: 4.8,
      reviews: 1240,
      image: "https://images.unsplash.com/photo-1595435934249-5df7ed86e1c0?auto=format&fit=crop&q=80&w=400",
      shortReview: "Exceptional control and stability. Heavy frame suited for advanced players.",
    },
    {
      id: "2",
      name: "SpeedCross 6 Trail Shoes",
      category: "Running",
      price: 140.00,
      rating: 4.6,
      reviews: 890,
      image: "https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&q=80&w=400",
      shortReview: "Aggressive grip for muddy terrain. Snug fit, might need half size up.",
    },
    {
      id: "3",
      name: "PowerBlock Elite EXP",
      category: "Fitness",
      price: 359.00,
      rating: 4.9,
      reviews: 3100,
      image: "https://images.unsplash.com/photo-1586401100295-7a8096fd231a?auto=format&fit=crop&q=80&w=400",
      shortReview: "Space-saving and durable. Quick weight changes up to 50 lbs per hand.",
    },
    {
      id: "4",
      name: "Manduka PRO Yoga Mat",
      category: "Yoga",
      price: 129.00,
      rating: 4.7,
      reviews: 2150,
      image: "https://images.unsplash.com/photo-1601925260368-ae2f83cf8b7f?auto=format&fit=crop&q=80&w=400",
      shortReview: "Unmatched density and cushion. Lifetime guarantee, but heavy to carry.",
    },
    {
      id: "5",
      name: "Giro Aether MIPS Helmet",
      category: "Cycling",
      price: 299.00,
      rating: 4.8,
      reviews: 420,
      image: "https://images.unsplash.com/photo-1565183928294-7063f23ce0f8?auto=format&fit=crop&q=80&w=400",
      shortReview: "Incredible ventilation and safety tech. Premium price but worth it.",
    },
    {
      id: "6",
      name: "Everlast Pro Style Gloves",
      category: "Boxing",
      price: 45.00,
      rating: 4.5,
      reviews: 5600,
      image: "https://images.unsplash.com/photo-1549719386-74dfcbf7dbed?auto=format&fit=crop&q=80&w=400",
      shortReview: "Great starter gloves. Good wrist support and durable synthetic leather.",
    }
  ];

  return (
    <div className="flex-1 flex flex-col items-center justify-start pt-12 md:pt-20 pb-12 px-4 md:px-8 max-w-5xl mx-auto w-full relative">
      <FloatingIcons />

      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center mb-8 w-full"
      >
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-orange-50 text-orange-700 text-xs font-medium mb-4 border border-orange-200">
          <Sparkles className="w-3 h-3 text-orange-500" />
          <span>AI Shopping Assistant</span>
        </div>
        <h1 className="text-3xl md:text-5xl font-bold tracking-tight text-zinc-900 mb-3">
          Find your perfect gear. <br className="hidden md:block" />
          <span className="text-zinc-400">Just ask.</span>
        </h1>
        <p className="text-base text-zinc-600 max-w-xl mx-auto">
          Tell me what you need, your budget, and skill level. I&apos;ll compare prices, check reviews, and find the best options across the web.
        </p>
      </motion.div>

      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="w-full max-w-2xl z-10"
      >
        <form onSubmit={handleSearch} className="relative group">
          <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none">
            <MessageSquare className="w-5 h-5 text-orange-500" />
          </div>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask me anything about sports gear..."
            className="w-full pl-12 pr-32 py-4 text-base bg-white border-2 border-zinc-200 rounded-2xl shadow-sm focus:border-orange-500 focus:ring-4 focus:ring-orange-500/10 outline-none transition-all"
          />
          <div className="absolute inset-y-2 right-2 flex items-center">
            <button
              type="submit"
              disabled={!query.trim()}
              className="bg-zinc-900 text-white px-4 py-2 rounded-xl text-sm font-medium hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              Ask Agent
              <Sparkles className="w-3 h-3" />
            </button>
          </div>
        </form>

        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
          <span className="text-xs text-zinc-500 mr-1">Try:</span>
          {presets.map((preset, i) => (
            <button
              key={i}
              type="button"
              onClick={() => handlePresetClick(preset)}
              className="text-xs font-medium bg-white/80 backdrop-blur-sm border border-zinc-200 text-zinc-600 px-3 py-1.5 rounded-lg hover:border-orange-300 hover:text-orange-700 transition-colors"
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
        className="mt-16 w-full z-10"
      >
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-zinc-900">Suggested for you</h2>
          <button 
            onClick={() => router.push('/explore')}
            className="text-sm font-medium text-orange-600 hover:text-orange-700 flex items-center gap-1"
          >
            View all <ArrowRight className="w-4 h-4" />
          </button>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {suggestedProducts.map((product) => (
            <div 
              key={product.id}
              onClick={() => router.push(`/product/${product.id}`)}
              className="group bg-white rounded-2xl border border-zinc-200 overflow-hidden hover:border-orange-300 hover:shadow-md transition-all cursor-pointer flex flex-col"
            >
              <div className="relative h-48 w-full bg-zinc-100">
                <Image
                  src={product.image}
                  alt={product.name}
                  fill
                  className="object-cover group-hover:scale-105 transition-transform duration-500"
                  referrerPolicy="no-referrer"
                />
                <div className="absolute top-3 left-3 bg-white/90 backdrop-blur-sm px-2 py-1 rounded-md text-xs font-bold text-zinc-800">
                  {product.category}
                </div>
              </div>
              <div className="p-5 flex flex-col flex-1">
                <div className="flex justify-between items-start mb-2">
                  <h3 className="font-bold text-zinc-900 line-clamp-1">{product.name}</h3>
                  <span className="font-bold text-orange-600">${product.price}</span>
                </div>
                <div className="flex items-center gap-1 mb-3">
                  <Star className="w-4 h-4 fill-amber-400 text-amber-400" />
                  <span className="text-sm font-bold text-zinc-700">{product.rating}</span>
                  <span className="text-xs text-zinc-500">({product.reviews})</span>
                </div>
                <p className="text-sm text-zinc-600 line-clamp-2 mt-auto">
                  &quot;{product.shortReview}&quot;
                </p>
              </div>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
