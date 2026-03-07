"use client";

import { useState } from 'react';
import { motion } from "framer-motion";
import { Search, Filter, Star, ArrowLeft } from 'lucide-react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import FloatingIcons from '@/components/FloatingIcons';

const allProducts = [
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
  },
  {
    id: "7",
    name: "Spalding TF-1000 Basketball",
    category: "Basketball",
    price: 65.00,
    rating: 4.8,
    reviews: 1800,
    image: "https://images.unsplash.com/photo-1519861531473-9200262188bf?auto=format&fit=crop&q=80&w=400",
    shortReview: "Excellent indoor grip and moisture management. Classic feel.",
  },
  {
    id: "8",
    name: "Crossrope Get Lean Set",
    category: "Fitness",
    price: 119.00,
    rating: 4.9,
    reviews: 3200,
    image: "https://images.unsplash.com/photo-1518611012118-696072aa579a?auto=format&fit=crop&q=80&w=400",
    shortReview: "Premium weighted jump rope system. Smooth rotation and great app.",
  },
  {
    id: "9",
    name: "Garmin Forerunner 265",
    category: "Running",
    price: 449.00,
    rating: 4.8,
    reviews: 1100,
    image: "https://images.unsplash.com/photo-1508685096489-7aacd43bd3b1?auto=format&fit=crop&q=80&w=400",
    shortReview: "Bright AMOLED display and incredible training readiness metrics.",
  }
];

const CATEGORIES = ["All", "Tennis", "Running", "Fitness", "Yoga", "Cycling", "Boxing", "Basketball"];

export default function Explore() {
  const router = useRouter();
  const [activeCategory, setActiveCategory] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");

  const filteredProducts = allProducts.filter(product => {
    const matchesCategory = activeCategory === "All" || product.category === activeCategory;
    const matchesSearch = product.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                          product.category.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  });

  return (
    <div className="flex-1 flex flex-col pt-8 pb-12 px-4 md:px-8 max-w-6xl mx-auto w-full relative">
      <FloatingIcons />
      
      <div className="z-10 relative">
        <button 
          onClick={() => router.back()}
          className="flex items-center gap-2 text-zinc-500 hover:text-zinc-900 mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>

        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-8">
          <div>
            <h1 className="text-3xl md:text-4xl font-bold text-zinc-900 mb-2">Explore Gear</h1>
            <p className="text-zinc-600">Discover top-rated equipment curated for your goals.</p>
          </div>
          
          <div className="flex items-center gap-3 w-full md:w-auto">
            <div className="relative flex-1 md:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
              <input 
                type="text"
                placeholder="Search products..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-4 py-2 bg-white border border-zinc-200 rounded-xl focus:border-orange-500 focus:ring-2 focus:ring-orange-500/20 outline-none transition-all"
              />
            </div>
            <button className="p-2 bg-white border border-zinc-200 rounded-xl text-zinc-600 hover:border-orange-500 hover:text-orange-600 transition-colors">
              <Filter className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="flex overflow-x-auto pb-4 mb-6 gap-2 scrollbar-hide">
          {CATEGORIES.map(category => (
            <button
              key={category}
              onClick={() => setActiveCategory(category)}
              className={`whitespace-nowrap px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                activeCategory === category 
                  ? 'bg-zinc-900 text-white' 
                  : 'bg-white border border-zinc-200 text-zinc-600 hover:border-zinc-300'
              }`}
            >
              {category}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredProducts.map((product, index) => (
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
              key={product.id}
              onClick={() => router.push(`/product/${product.id}`)}
              className="group bg-white rounded-2xl border border-zinc-200 overflow-hidden hover:border-orange-300 hover:shadow-md transition-all cursor-pointer flex flex-col"
            >
              <div className="relative h-56 w-full bg-zinc-100">
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
            </motion.div>
          ))}
          
          {filteredProducts.length === 0 && (
            <div className="col-span-full py-12 text-center">
              <p className="text-zinc-500">No products found matching your criteria.</p>
              <button 
                onClick={() => {
                  setSearchQuery("");
                  setActiveCategory("All");
                }}
                className="mt-4 text-orange-600 font-medium hover:underline"
              >
                Clear filters
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
