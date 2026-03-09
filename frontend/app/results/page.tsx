'use client';

import { useState, useEffect, Suspense, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { motion } from 'motion/react';
import { Search, Filter, SlidersHorizontal, ArrowRight, CheckCircle2, Loader2, AlertCircle, ChevronDown, ExternalLink, Star, Clock, Send, Bot, User } from 'lucide-react';
import Link from 'next/link';

// Mock data
const mockResults = [
  {
    id: '1',
    title: 'Babolat Pure Drive Tennis Racket',
    store: 'Dick\'s Sporting Goods',
    price: 249.00,
    rating: 4.8,
    reviews: 342,
    delivery: 'Tomorrow',
    score: 98,
    image: 'https://picsum.photos/seed/racket1/400/400',
    risk: 'low',
    pros: ['Incredible power', 'Large sweet spot', 'Great for all levels'],
    cons: ['Can be stiff on the arm']
  },
  {
    id: '2',
    title: 'Wilson Clash 100 V2',
    store: 'Tennis Warehouse',
    price: 269.00,
    rating: 4.7,
    reviews: 512,
    delivery: 'Wednesday, Oct 25',
    score: 94,
    image: 'https://picsum.photos/seed/racket2/400/400',
    risk: 'low',
    pros: ['Very arm-friendly', 'Excellent control'],
    cons: ['Less free power than Pure Drive']
  },
  {
    id: '3',
    title: 'Generic Carbon Fiber Racket',
    store: 'Amazon',
    price: 89.99,
    rating: 3.9,
    reviews: 124,
    delivery: 'Friday, Oct 27',
    score: 72,
    image: 'https://picsum.photos/seed/racket3/400/400',
    risk: 'medium',
    pros: ['Very affordable', 'Lightweight'],
    cons: ['Poor string quality', 'Vibrates heavily', 'Fake review signals detected']
  }
];

import { useRouter } from 'next/navigation';

function ResultsContent() {
  const searchParams = useSearchParams();
  const query = searchParams.get('q') || '';
  const router = useRouter();
  
  const [step, setStep] = useState(0);
  const [isEditingConstraints, setIsEditingConstraints] = useState(false);
  const [budget, setBudget] = useState(300);
  const [minRating, setMinRating] = useState(4.0);
  
  const [messages, setMessages] = useState([
    { role: 'agent', content: `I found some great options for "${query}". Let me know if you want to refine these results!` }
  ]);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    
    setMessages(prev => [...prev, { role: 'user', content: input }]);
    setInput('');
    
    // Simulate agent response
    setTimeout(() => {
      setMessages(prev => [...prev, { role: 'agent', content: 'I have updated the results based on your feedback.' }]);
    }, 1000);
  };
  
  // Filter results based on constraints
  const filteredResults = mockResults.filter(r => r.price <= budget && r.rating >= minRating);
  
  // Simulate pipeline progress
  useEffect(() => {
    const timer1 = setTimeout(() => setStep(1), 1500); // Extracting
    const timer2 = setTimeout(() => setStep(2), 3000); // Reviews
    const timer3 = setTimeout(() => setStep(3), 4500); // Ranking
    const timer4 = setTimeout(() => setStep(4), 5500); // Done
    
    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
      clearTimeout(timer4);
    };
  }, [query]);

  const steps = [
    { label: 'Searching stores', active: step === 0, done: step > 0 },
    { label: 'Extracting details', active: step === 1, done: step > 1 },
    { label: 'Analyzing reviews', active: step === 2, done: step > 2 },
    { label: 'Ranking options', active: step === 3, done: step > 3 },
  ];

  return (
    <div className={`flex-1 bg-zinc-50 ${step >= 4 ? 'lg:pr-[380px]' : ''}`}>
      <div className="bg-white border-b border-zinc-200 sticky top-14 z-30">
        <div className="container mx-auto px-4 py-4 max-w-7xl">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h1 className="text-xl font-bold text-zinc-900 line-clamp-1">&quot;{query}&quot;</h1>
              <div className="flex items-center gap-2 mt-1 text-sm text-zinc-500">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-lg bg-orange-500"></span> Using default preferences</span>
              </div>
            </div>
            <button 
              onClick={() => setIsEditingConstraints(!isEditingConstraints)}
              className="px-4 py-2 bg-zinc-100 hover:bg-zinc-200 text-zinc-700 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 w-fit"
            >
              <SlidersHorizontal className="w-4 h-4" />
              Edit Constraints
            </button>
          </div>

          {isEditingConstraints && (
            <motion.div 
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              className="mt-4 pt-4 border-t border-zinc-100 grid grid-cols-2 md:grid-cols-4 gap-4"
            >
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1">Max Budget</label>
                <input 
                  type="number" 
                  value={budget} 
                  onChange={(e) => setBudget(Number(e.target.value))} 
                  className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 rounded-lg text-sm focus:ring-0 focus:border-orange-500 outline-none" 
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1">Min Rating</label>
                <select 
                  value={minRating} 
                  onChange={(e) => setMinRating(Number(e.target.value))} 
                  className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 rounded-lg text-sm focus:ring-0 focus:border-orange-500 outline-none"
                >
                  <option value={3.0}>3.0+</option>
                  <option value={4.0}>4.0+</option>
                  <option value={4.5}>4.5+</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1">Delivery By</label>
                <input type="date" className="w-full px-3 py-2 bg-zinc-50 border border-zinc-200 rounded-lg text-sm focus:ring-0 focus:border-orange-500 outline-none" />
              </div>
              <div className="flex items-end">
                <button onClick={() => setIsEditingConstraints(false)} className="w-full px-4 py-2 bg-orange-600 text-white rounded-lg text-sm font-medium hover:bg-orange-700 transition-colors">
                  Update Search
                </button>
              </div>
            </motion.div>
          )}
        </div>
      </div>

      <div className="container mx-auto px-4 py-8 max-w-7xl">
        {step < 4 ? (
          <div className="max-w-2xl mx-auto mt-12 bg-white p-8 rounded-xl border border-zinc-200 shadow-sm">
            <h2 className="text-xl font-bold text-zinc-900 mb-6 text-center">Agent is working...</h2>
            <div className="space-y-6">
              {steps.map((s, i) => (
                <div key={i} className={`flex items-center gap-4 ${s.active ? 'opacity-100' : s.done ? 'opacity-60' : 'opacity-30'}`}>
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${s.done ? 'bg-orange-100 text-orange-600' : s.active ? 'bg-orange-600 text-white' : 'bg-zinc-100 text-zinc-400'}`}>
                    {s.done ? <CheckCircle2 className="w-5 h-5" /> : s.active ? <Loader2 className="w-4 h-4 animate-spin" /> : <div className="w-2 h-2 rounded-lg bg-current" />}
                  </div>
                  <span className={`font-medium ${s.active ? 'text-zinc-900' : 'text-zinc-700'}`}>{s.label}</span>
                </div>
              ))}
            </div>
            <div className="mt-8 pt-6 border-t border-zinc-100 flex justify-center">
              <button onClick={() => router.push('/')} className="text-sm text-red-600 font-medium hover:text-red-700">Cancel Search</button>
            </div>
          </div>
        ) : (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col gap-8">
            {/* Results */}
            <div className="flex-1 min-w-0 w-full">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-bold text-zinc-900">Top Recommendations</h2>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-zinc-500">Sort by:</span>
                  <select className="bg-white border border-zinc-200 text-sm rounded-lg px-3 py-1.5 outline-none focus:border-orange-500">
                    <option>Match Score</option>
                    <option>Price: Low to High</option>
                    <option>Delivery Time</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-6">
                {filteredResults.length > 0 ? filteredResults.map((product, index) => (
                  <div key={product.id} className="bg-white rounded-xl border border-zinc-200 overflow-hidden shadow-sm hover:shadow-md transition-shadow flex flex-col md:flex-row">
                    <div className="w-full md:w-48 h-48 md:h-auto bg-zinc-100 relative shrink-0">
                      <img src={product.image} alt={product.title} className="w-full h-full object-cover mix-blend-multiply p-4" />
                      <div className="absolute top-3 left-3 bg-white/90 backdrop-blur-sm px-2.5 py-1 rounded-md text-xs font-bold border border-zinc-200 shadow-sm">
                        #{index + 1}
                      </div>
                    </div>
                    
                    <div className="p-6 flex-1 flex flex-col">
                      <div className="flex justify-between items-start gap-4 mb-2">
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-xs font-bold uppercase tracking-wider text-zinc-500">{product.store}</span>
                            {product.risk === 'medium' && (
                              <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                                <AlertCircle className="w-3 h-3" /> Medium Risk
                              </span>
                            )}
                          </div>
                          <Link href={`/product/${product.id}`} className="text-lg font-bold text-zinc-900 hover:text-orange-600 transition-colors line-clamp-2">
                            {product.title}
                          </Link>
                        </div>
                        <div className="flex flex-col items-end shrink-0">
                          <div className="flex items-center justify-center w-12 h-12 rounded-lg bg-orange-50 border border-orange-100 text-orange-700 font-bold text-lg">
                            {product.score}
                          </div>
                          <span className="text-[10px] text-zinc-500 font-medium uppercase mt-1">Match</span>
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-4 text-sm text-zinc-600 mb-4">
                        <div className="font-bold text-xl text-zinc-900">${product.price.toFixed(2)}</div>
                        <div className="flex items-center gap-1">
                          <Star className="w-4 h-4 fill-amber-400 text-amber-400" />
                          <span className="font-medium text-zinc-900">{product.rating}</span>
                          <span className="text-zinc-400">({product.reviews})</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Clock className="w-4 h-4 text-zinc-400" />
                          {product.delivery}
                        </div>
                      </div>

                      <div className="mt-auto pt-4 border-t border-zinc-100 grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <div className="text-xs font-bold text-emerald-600 uppercase tracking-wider mb-1">Pros</div>
                          <ul className="text-sm text-zinc-600 space-y-1">
                            {product.pros.map((pro, i) => <li key={i} className="flex items-start gap-1.5"><CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" /> {pro}</li>)}
                          </ul>
                        </div>
                        <div>
                          <div className="text-xs font-bold text-red-600 uppercase tracking-wider mb-1">Cons</div>
                          <ul className="text-sm text-zinc-600 space-y-1">
                            {product.cons.map((con, i) => <li key={i} className="flex items-start gap-1.5"><AlertCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" /> {con}</li>)}
                          </ul>
                        </div>
                      </div>

                      <div className="mt-6 flex flex-col sm:flex-row items-center gap-3">
                        <Link href={`/product/${product.id}`} className="w-full sm:flex-1 text-center px-4 py-2.5 bg-zinc-100 hover:bg-zinc-200 text-zinc-900 rounded-xl text-sm font-medium transition-colors">
                          View Full Analysis
                        </Link>
                        <button onClick={() => window.open('https://amazon.com', '_blank')} className="w-full sm:flex-1 px-4 py-2.5 bg-orange-600 hover:bg-orange-700 text-white rounded-xl text-sm font-medium transition-colors flex items-center justify-center gap-2">
                          Buy on {product.store}
                          <ExternalLink className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                )) : (
                  <div className="text-center py-12 bg-white rounded-xl border border-zinc-200">
                    <p className="text-zinc-500 font-medium">No results match your constraints.</p>
                    <button onClick={() => { setBudget(300); setMinRating(3.0); }} className="mt-4 text-orange-600 font-medium hover:text-orange-700">Clear constraints</button>
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </div>

      {/* Chat Box - Fixed Sidebar on Desktop */}
      {step >= 4 && (
        <div className="w-full lg:w-[380px] shrink-0 flex flex-col h-[600px] lg:h-[calc(100vh-3.5rem)] bg-white border-t lg:border-t-0 lg:border-l border-zinc-200 lg:fixed lg:right-0 lg:top-14 lg:bottom-0 z-40 shadow-2xl lg:shadow-none">
          <div className="p-4 border-b border-zinc-100 bg-zinc-50 flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-orange-100 flex items-center justify-center text-orange-600">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-zinc-900 text-sm">AI Shopping Agent</h3>
              <p className="text-xs text-zinc-500">Ask follow-up questions</p>
            </div>
          </div>
          
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((msg, idx) => (
              <div key={idx} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${msg.role === 'user' ? 'bg-zinc-100 text-zinc-600' : 'bg-orange-100 text-orange-600'}`}>
                  {msg.role === 'user' ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                </div>
                <div className={`p-3 rounded-2xl max-w-[80%] text-sm ${msg.role === 'user' ? 'bg-zinc-900 text-white rounded-tr-sm' : 'bg-zinc-100 text-zinc-800 rounded-tl-sm'}`}>
                  {msg.content}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
          
          <form onSubmit={handleSendMessage} className="p-4 border-t border-zinc-100 bg-white">
            <div className="relative">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Refine results (e.g., under $200)..."
                className="w-full pl-4 pr-12 py-3 bg-zinc-50 border border-zinc-200 rounded-xl text-sm focus:ring-0 focus:border-orange-500 outline-none"
              />
              <button
                type="submit"
                disabled={!input.trim()}
                className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 flex items-center justify-center bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

export default function Results() {
  return (
    <Suspense fallback={<div className="flex-1 flex items-center justify-center"><Loader2 className="w-8 h-8 animate-spin text-zinc-400" /></div>}>
      <ResultsContent />
    </Suspense>
  );
}
