'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { Save, Shield, MapPin, DollarSign, Store } from 'lucide-react';
import { useRouter } from 'next/navigation';

export default function Preferences() {
  const [budget, setBudget] = useState('150');
  const [zip, setZip] = useState('');
  const [minRating, setMinRating] = useState('4.0');
  const [riskTolerance, setRiskTolerance] = useState('low');
  const [stores, setStores] = useState(['amazon', 'walmart', 'target']);
  const router = useRouter();

  const toggleStore = (store: string) => {
    setStores(prev => 
      prev.includes(store) ? prev.filter(s => s !== store) : [...prev, store]
    );
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    // Save to backend
    alert('Preferences saved successfully!');
    router.push('/'); // Go back to home after saving
  };

  return (
    <div className="flex-1 container mx-auto px-4 py-8 max-w-3xl">
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-3xl font-bold text-zinc-900 mb-2">Your Preferences</h1>
        <p className="text-zinc-500 mb-8">Set your defaults to speed up future searches.</p>

        <form onSubmit={handleSave} className="space-y-8 bg-white p-6 md:p-8 rounded-xl shadow-sm border border-zinc-100">
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-zinc-700 mb-1.5 flex items-center gap-2">
                <DollarSign className="w-4 h-4 text-zinc-400" /> Default Max Budget
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-3 flex items-center pointer-events-none text-zinc-500">$</div>
                <input
                  type="number"
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                  className="w-full pl-8 pr-4 py-2.5 bg-zinc-50 border border-zinc-200 rounded-xl focus:bg-white focus:border-orange-500 focus:ring-0 outline-none transition-all"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-700 mb-1.5 flex items-center gap-2">
                <MapPin className="w-4 h-4 text-zinc-400" /> Delivery ZIP Code
              </label>
              <input
                type="text"
                value={zip}
                onChange={(e) => setZip(e.target.value)}
                placeholder="e.g. 90210"
                className="w-full px-4 py-2.5 bg-zinc-50 border border-zinc-200 rounded-xl focus:bg-white focus:border-orange-500 focus:ring-0 outline-none transition-all"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-3 flex items-center gap-2">
              <Store className="w-4 h-4 text-zinc-400" /> Preferred Stores
            </label>
            <div className="flex flex-wrap gap-3">
              {['amazon', 'walmart', 'target', 'bestbuy', 'sephora'].map((store) => (
                <button
                  key={store}
                  type="button"
                  onClick={() => toggleStore(store)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition-colors border ${
                    stores.includes(store) 
                      ? 'bg-orange-600 text-white border-orange-600' 
                      : 'bg-white text-zinc-600 border-zinc-200 hover:border-zinc-400'
                  }`}
                >
                  {store}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-zinc-700 mb-1.5">Minimum Rating</label>
              <select
                value={minRating}
                onChange={(e) => setMinRating(e.target.value)}
                className="w-full px-4 py-2.5 bg-zinc-50 border border-zinc-200 rounded-xl focus:bg-white focus:border-orange-500 focus:ring-0 outline-none transition-all"
              >
                <option value="3.0">3.0+ Stars</option>
                <option value="4.0">4.0+ Stars</option>
                <option value="4.5">4.5+ Stars</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-700 mb-1.5 flex items-center gap-2">
                <Shield className="w-4 h-4 text-zinc-400" /> Risk Tolerance
              </label>
              <select
                value={riskTolerance}
                onChange={(e) => setRiskTolerance(e.target.value)}
                className="w-full px-4 py-2.5 bg-zinc-50 border border-zinc-200 rounded-xl focus:bg-white focus:border-orange-500 focus:ring-0 outline-none transition-all"
              >
                <option value="low">Low (Verified sellers only, strict fake review filtering)</option>
                <option value="medium">Medium (Standard filtering)</option>
                <option value="high">High (Show me everything, I&apos;ll decide)</option>
              </select>
            </div>
          </div>

          <div className="pt-4 border-t border-zinc-100 flex justify-end">
            <button
              type="submit"
              className="bg-orange-600 text-white px-6 py-2.5 rounded-xl font-medium hover:bg-orange-700 transition-colors flex items-center gap-2"
            >
              <Save className="w-4 h-4" />
              Save Preferences
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  );
}
