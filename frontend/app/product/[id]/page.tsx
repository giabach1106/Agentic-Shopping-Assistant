'use client';

import { useState } from 'react';
import { motion } from 'motion/react';
import { Star, Clock, ShieldCheck, AlertCircle, CheckCircle2, ExternalLink, ArrowLeft, ThumbsUp, ThumbsDown, MessageSquare, Info } from 'lucide-react';
import Link from 'next/link';

export default function ProductDetail() {
  const [activeTab, setActiveTab] = useState('summary');

  // Mock data
  const product = {
    id: '1',
    title: 'Babolat Pure Drive Tennis Racket',
    store: 'Dick\'s Sporting Goods',
    price: 249.00,
    rating: 4.8,
    reviews: 342,
    delivery: 'Tomorrow',
    score: 98,
    image: 'https://picsum.photos/seed/racket1/800/800',
    risk: 'low',
    description: 'The iconic Babolat Pure Drive offers explosive power and great feel. Widely used by professionals and club players alike, it features the new HTR System and SWX Pure Feel technology.',
    scoreBreakdown: [
      { factor: 'Price Match', score: 100, weight: '40%' },
      { factor: 'Rating Quality', score: 95, weight: '30%' },
      { factor: 'Delivery Speed', score: 100, weight: '20%' },
      { factor: 'Seller Trust', score: 90, weight: '10%' },
    ],
    reviewSummary: {
      pros: ['Incredible free power on serves and groundstrokes', 'Large, forgiving sweet spot', 'Great maneuverability at the net'],
      cons: ['Can be stiff on the arm for players with tennis elbow', 'Control can be erratic if you overhit'],
      sources: [
        { name: 'Tennis Warehouse', count: 156, sentiment: 'positive' },
        { name: 'Reddit', count: 89, sentiment: 'mixed', note: 'r/10s generally recommends it but warns about stiffness.' },
        { name: 'TikTok', count: 45, sentiment: 'positive', warning: 'Some videos flagged as possible paid promotion by Babolat.' }
      ]
    }
  };

  return (
    <div className="flex-1 bg-zinc-50 pb-20">
      <div className="bg-white border-b border-zinc-200 sticky top-16 z-40">
        <div className="container mx-auto px-4 py-3 max-w-7xl">
          <Link href="/results" className="inline-flex items-center gap-2 text-sm font-medium text-zinc-500 hover:text-zinc-900 transition-colors">
            <ArrowLeft className="w-4 h-4" />
            Back to Results
          </Link>
        </div>
      </div>

      <div className="container mx-auto px-4 py-8 max-w-7xl">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          
          {/* Left Column: Image & Basic Info */}
          <div className="lg:col-span-1 space-y-6">
            <div className="bg-white rounded-xl border border-zinc-200 overflow-hidden shadow-sm p-6">
              <div className="aspect-square bg-zinc-100 rounded-xl mb-6 relative">
                <img src={product.image} alt={product.title} className="w-full h-full object-cover mix-blend-multiply rounded-xl" />
                <div className="absolute top-4 left-4 flex flex-col items-center justify-center w-16 h-16 rounded-xl bg-orange-50 border-2 border-orange-100 text-orange-700 font-bold text-2xl shadow-sm">
                  {product.score}
                  <span className="text-[8px] font-bold uppercase tracking-wider mt-0.5">Match</span>
                </div>
              </div>
              
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs font-bold uppercase tracking-wider text-zinc-500">{product.store}</span>
                <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded">
                  <ShieldCheck className="w-3 h-3" /> Low Risk
                </span>
              </div>
              
              <h1 className="text-2xl font-bold text-zinc-900 mb-4">{product.title}</h1>
              
              <div className="flex flex-wrap items-center gap-4 text-sm text-zinc-600 mb-6 pb-6 border-b border-zinc-100">
                <div className="font-bold text-3xl text-zinc-900">${product.price.toFixed(2)}</div>
                <div className="flex items-center gap-1">
                  <Star className="w-5 h-5 fill-amber-400 text-amber-400" />
                  <span className="font-medium text-zinc-900 text-lg">{product.rating}</span>
                  <span className="text-zinc-400">({product.reviews})</span>
                </div>
              </div>

              <div className="space-y-3 mb-6">
                <div className="flex items-center gap-3 text-sm text-zinc-700">
                  <Clock className="w-5 h-5 text-zinc-400" />
                  <span>Delivery by <span className="font-medium text-zinc-900">{product.delivery}</span></span>
                </div>
                <div className="flex items-center gap-3 text-sm text-zinc-700">
                  <CheckCircle2 className="w-5 h-5 text-zinc-400" />
                  <span>Free returns within 30 days</span>
                </div>
              </div>

              <button onClick={() => window.open('https://amazon.com', '_blank')} className="w-full py-4 bg-orange-600 hover:bg-orange-700 text-white rounded-xl font-medium transition-colors flex items-center justify-center gap-2 text-lg">
                Buy on {product.store}
                <ExternalLink className="w-5 h-5" />
              </button>
              
              <button onClick={() => alert('Added to shortlist!')} className="w-full mt-3 py-3 bg-white border border-zinc-200 hover:bg-zinc-50 text-zinc-900 rounded-xl font-medium transition-colors text-sm">
                Save to Shortlist
              </button>
            </div>
          </div>

          {/* Right Column: Analysis */}
          <div className="lg:col-span-2 space-y-6">
            
            {/* Tabs */}
            <div className="flex items-center gap-2 border-b border-zinc-200 pb-px">
              {['summary', 'reviews', 'scoring'].map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-2.5 text-sm font-medium capitalize border-b-2 transition-colors ${
                    activeTab === tab 
                      ? 'border-orange-600 text-orange-600' 
                      : 'border-transparent text-zinc-500 hover:text-zinc-700 hover:border-zinc-300'
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* Tab Content */}
            <motion.div 
              key={activeTab}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
            >
              {activeTab === 'summary' && (
                <div className="space-y-6">
                  <div className="bg-white p-6 rounded-xl border border-zinc-200 shadow-sm">
                    <h3 className="text-lg font-bold text-zinc-900 mb-4">Why it&apos;s a match</h3>
                    <p className="text-zinc-600 leading-relaxed mb-6">{product.description}</p>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="bg-emerald-50/50 p-5 rounded-xl border border-emerald-100/50">
                        <div className="flex items-center gap-2 mb-3 text-emerald-800 font-bold">
                          <ThumbsUp className="w-5 h-5" />
                          Top Pros
                        </div>
                        <ul className="space-y-2">
                          {product.reviewSummary.pros.map((pro, i) => (
                            <li key={i} className="text-sm text-zinc-700 flex items-start gap-2">
                              <span className="w-1.5 h-1.5 rounded-sm bg-emerald-400 mt-1.5 shrink-0" />
                              {pro}
                            </li>
                          ))}
                        </ul>
                      </div>
                      
                      <div className="bg-red-50/50 p-5 rounded-xl border border-red-100/50">
                        <div className="flex items-center gap-2 mb-3 text-red-800 font-bold">
                          <ThumbsDown className="w-5 h-5" />
                          Top Cons
                        </div>
                        <ul className="space-y-2">
                          {product.reviewSummary.cons.map((con, i) => (
                            <li key={i} className="text-sm text-zinc-700 flex items-start gap-2">
                              <span className="w-1.5 h-1.5 rounded-sm bg-red-400 mt-1.5 shrink-0" />
                              {con}
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'reviews' && (
                <div className="space-y-6">
                  <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                    <div>
                      <h4 className="text-sm font-bold text-amber-800">Paid Promotion Warning</h4>
                      <p className="text-sm text-amber-700 mt-1">We detected that some TikTok reviews for this product contain paid promotion disclosures. We have weighted these reviews lower in our analysis.</p>
                    </div>
                  </div>

                  <div className="bg-white p-6 rounded-xl border border-zinc-200 shadow-sm">
                    <h3 className="text-lg font-bold text-zinc-900 mb-6">Review Sources</h3>
                    <div className="space-y-4">
                      {product.reviewSummary.sources.map((source, i) => (
                        <div key={i} className="flex items-start gap-4 p-4 rounded-xl border border-zinc-100 bg-zinc-50/50">
                          <div className="w-10 h-10 rounded-xl bg-white border border-zinc-200 flex items-center justify-center shrink-0">
                            <MessageSquare className="w-5 h-5 text-zinc-400" />
                          </div>
                          <div className="flex-1">
                            <div className="flex items-center justify-between mb-1">
                              <h4 className="font-bold text-zinc-900">{source.name}</h4>
                              <span className="text-xs font-medium text-zinc-500">{source.count} mentions</span>
                            </div>
                            <div className="flex items-center gap-2 mb-2">
                              <span className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                                source.sentiment === 'positive' ? 'bg-emerald-100 text-emerald-700' :
                                source.sentiment === 'mixed' ? 'bg-amber-100 text-amber-700' :
                                'bg-red-100 text-red-700'
                              }`}>
                                {source.sentiment}
                              </span>
                            </div>
                            {source.note && <p className="text-sm text-zinc-600">{source.note}</p>}
                            {source.warning && <p className="text-sm text-amber-600 mt-1 flex items-center gap-1"><AlertCircle className="w-3 h-3" /> {source.warning}</p>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'scoring' && (
                <div className="space-y-6">
                  <div className="bg-white p-6 rounded-xl border border-zinc-200 shadow-sm">
                    <div className="flex items-center justify-between mb-6">
                      <h3 className="text-lg font-bold text-zinc-900">Score Breakdown</h3>
                      <div className="flex items-center gap-1 text-sm text-zinc-500 cursor-help" title="How scoring works">
                        <Info className="w-4 h-4" />
                        Methodology
                      </div>
                    </div>
                    
                    <div className="space-y-5">
                      {product.scoreBreakdown.map((item, i) => (
                        <div key={i}>
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium text-zinc-700">{item.factor} <span className="text-zinc-400 font-normal ml-1">(Weight: {item.weight})</span></span>
                            <span className="text-sm font-bold text-zinc-900">{item.score}/100</span>
                          </div>
                          <div className="h-2 w-full bg-zinc-100 rounded-lg overflow-hidden">
                            <div 
                              className="h-full bg-orange-500 rounded-lg" 
                              style={{ width: `${item.score}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="bg-white p-6 rounded-xl border border-zinc-200 shadow-sm">
                    <h3 className="text-lg font-bold text-zinc-900 mb-4">Risk Analysis</h3>
                    <div className="flex items-start gap-3">
                      <ShieldCheck className="w-6 h-6 text-emerald-500 shrink-0" />
                      <div>
                        <h4 className="font-bold text-zinc-900">Low Risk Profile</h4>
                        <p className="text-sm text-zinc-600 mt-1">This product passes our authenticity checks. The seller is verified, review patterns appear organic, and the return policy is standard for this category.</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </motion.div>

          </div>
        </div>
      </div>
    </div>
  );
}
