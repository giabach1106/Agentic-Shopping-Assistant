'use client';

import { useState } from 'react';
import { motion } from 'motion/react';
import { ArrowRight, Check, Activity, Dumbbell, Bike, Flame, Target, TrendingUp, Heart, Trophy, Wallet } from 'lucide-react';
import { useRouter } from 'next/navigation';
import FloatingIcons from '@/components/FloatingIcons';

const SPORTS = [
  { id: 'running', name: 'Running', icon: Activity },
  { id: 'fitness', name: 'Fitness & Gym', icon: Dumbbell },
  { id: 'cycling', name: 'Cycling', icon: Bike },
  { id: 'outdoor', name: 'Outdoor & Hiking', icon: Flame },
];

const SKILL_LEVELS = [
  { id: 'beginner', name: 'Beginner', desc: 'Just starting out' },
  { id: 'intermediate', name: 'Intermediate', desc: 'Active regularly' },
  { id: 'advanced', name: 'Advanced', desc: 'Competitive / Pro' },
];

const GOALS = [
  { id: 'weight_loss', name: 'Weight Loss', icon: TrendingUp },
  { id: 'muscle_gain', name: 'Muscle Gain', icon: Dumbbell },
  { id: 'endurance', name: 'Endurance', icon: Activity },
  { id: 'general_fitness', name: 'General Fitness', icon: Heart },
  { id: 'competition', name: 'Competition', icon: Trophy },
];

const BUDGETS = [
  { id: 'budget', name: 'Budget-Friendly', desc: 'Best value for money', icon: '$' },
  { id: 'mid', name: 'Mid-Range', desc: 'Great quality, reasonable price', icon: '$$' },
  { id: 'premium', name: 'Premium', desc: 'Top-tier, professional gear', icon: '$$$' },
];

export default function Onboarding() {
  const [step, setStep] = useState(1);
  const [selectedSports, setSelectedSports] = useState<string[]>([]);
  const [skillLevel, setSkillLevel] = useState<string>('');
  const [goal, setGoal] = useState<string>('');
  const [budget, setBudget] = useState<string>('');
  const router = useRouter();

  const handleSportToggle = (id: string) => {
    setSelectedSports(prev => 
      prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]
    );
  };

  const handleNext = () => {
    if (step === 1 && selectedSports.length > 0) {
      setStep(2);
    } else if (step === 2 && skillLevel) {
      setStep(3);
    } else if (step === 3 && goal) {
      setStep(4);
    } else if (step === 4 && budget) {
      // Save preferences and redirect
      console.log('Preferences saved:', { sports: selectedSports, skillLevel, goal, budget });
      router.push('/');
    }
  };

  const isNextDisabled = () => {
    if (step === 1) return selectedSports.length === 0;
    if (step === 2) return !skillLevel;
    if (step === 3) return !goal;
    if (step === 4) return !budget;
    return false;
  };

  const getStepTitle = () => {
    switch (step) {
      case 1: return 'What are your main interests?';
      case 2: return 'What is your skill level?';
      case 3: return 'What is your primary goal?';
      case 4: return 'What is your typical budget?';
      default: return '';
    }
  };

  const getStepDesc = () => {
    switch (step) {
      case 1: return 'Select the sports and activities you want gear for.';
      case 2: return 'This helps us recommend the right products for your needs.';
      case 3: return 'We will tailor suggestions to help you achieve this.';
      case 4: return 'We will find the best gear within your price range.';
      default: return '';
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center p-4 relative overflow-hidden">
      <FloatingIcons />
      
      <motion.div 
        key={step}
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -20 }}
        className="w-full max-w-xl bg-white/90 backdrop-blur-md p-8 md:p-10 rounded-2xl shadow-sm border border-zinc-100 z-10"
      >
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className={`h-2 flex-1 rounded-full ${step >= i ? 'bg-orange-500' : 'bg-zinc-200'}`} />
            ))}
          </div>
          <h1 className="text-3xl font-bold text-zinc-900 mb-2">
            {getStepTitle()}
          </h1>
          <p className="text-zinc-500">
            {getStepDesc()}
          </p>
        </div>

        {step === 1 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
            {SPORTS.map((sport) => {
              const isSelected = selectedSports.includes(sport.id);
              const Icon = sport.icon;
              return (
                <button
                  key={sport.id}
                  onClick={() => handleSportToggle(sport.id)}
                  className={`flex items-center gap-4 p-4 rounded-xl border-2 text-left transition-all ${
                    isSelected 
                      ? 'border-orange-500 bg-orange-50' 
                      : 'border-zinc-200 hover:border-orange-200 bg-white'
                  }`}
                >
                  <div className={`p-2 rounded-lg ${isSelected ? 'bg-orange-500 text-white' : 'bg-zinc-100 text-zinc-500'}`}>
                    <Icon className="w-6 h-6" />
                  </div>
                  <span className={`font-medium ${isSelected ? 'text-orange-900' : 'text-zinc-700'}`}>
                    {sport.name}
                  </span>
                  {isSelected && <Check className="w-5 h-5 text-orange-500 ml-auto" />}
                </button>
              );
            })}
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4 mb-8">
            {SKILL_LEVELS.map((level) => {
              const isSelected = skillLevel === level.id;
              return (
                <button
                  key={level.id}
                  onClick={() => setSkillLevel(level.id)}
                  className={`w-full flex items-center justify-between p-5 rounded-xl border-2 text-left transition-all ${
                    isSelected 
                      ? 'border-orange-500 bg-orange-50' 
                      : 'border-zinc-200 hover:border-orange-200 bg-white'
                  }`}
                >
                  <div>
                    <h3 className={`font-bold text-lg ${isSelected ? 'text-orange-900' : 'text-zinc-900'}`}>
                      {level.name}
                    </h3>
                    <p className={`text-sm ${isSelected ? 'text-orange-700' : 'text-zinc-500'}`}>
                      {level.desc}
                    </p>
                  </div>
                  <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center ${
                    isSelected ? 'border-orange-500 bg-orange-500' : 'border-zinc-300'
                  }`}>
                    {isSelected && <div className="w-2 h-2 bg-white rounded-full" />}
                  </div>
                </button>
              );
            })}
          </div>
        )}

        {step === 3 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
            {GOALS.map((g) => {
              const isSelected = goal === g.id;
              const Icon = g.icon;
              return (
                <button
                  key={g.id}
                  onClick={() => setGoal(g.id)}
                  className={`flex items-center gap-4 p-4 rounded-xl border-2 text-left transition-all ${
                    isSelected 
                      ? 'border-orange-500 bg-orange-50' 
                      : 'border-zinc-200 hover:border-orange-200 bg-white'
                  }`}
                >
                  <div className={`p-2 rounded-lg ${isSelected ? 'bg-orange-500 text-white' : 'bg-zinc-100 text-zinc-500'}`}>
                    <Icon className="w-6 h-6" />
                  </div>
                  <span className={`font-medium ${isSelected ? 'text-orange-900' : 'text-zinc-700'}`}>
                    {g.name}
                  </span>
                  {isSelected && <Check className="w-5 h-5 text-orange-500 ml-auto" />}
                </button>
              );
            })}
          </div>
        )}

        {step === 4 && (
          <div className="space-y-4 mb-8">
            {BUDGETS.map((b) => {
              const isSelected = budget === b.id;
              return (
                <button
                  key={b.id}
                  onClick={() => setBudget(b.id)}
                  className={`w-full flex items-center justify-between p-5 rounded-xl border-2 text-left transition-all ${
                    isSelected 
                      ? 'border-orange-500 bg-orange-50' 
                      : 'border-zinc-200 hover:border-orange-200 bg-white'
                  }`}
                >
                  <div className="flex items-center gap-4">
                    <div className={`w-12 h-12 rounded-full flex items-center justify-center font-bold text-lg ${
                      isSelected ? 'bg-orange-500 text-white' : 'bg-zinc-100 text-zinc-500'
                    }`}>
                      {b.icon}
                    </div>
                    <div>
                      <h3 className={`font-bold text-lg ${isSelected ? 'text-orange-900' : 'text-zinc-900'}`}>
                        {b.name}
                      </h3>
                      <p className={`text-sm ${isSelected ? 'text-orange-700' : 'text-zinc-500'}`}>
                        {b.desc}
                      </p>
                    </div>
                  </div>
                  <div className={`w-6 h-6 rounded-full border-2 flex items-center justify-center ${
                    isSelected ? 'border-orange-500 bg-orange-500' : 'border-zinc-300'
                  }`}>
                    {isSelected && <div className="w-2 h-2 bg-white rounded-full" />}
                  </div>
                </button>
              );
            })}
          </div>
        )}

        <div className="flex justify-between items-center">
          {step > 1 ? (
            <button 
              onClick={() => setStep(step - 1)}
              className="text-zinc-500 font-medium hover:text-zinc-900 px-4 py-2"
            >
              Back
            </button>
          ) : (
            <div /> // Placeholder for layout
          )}
          <button
            onClick={handleNext}
            disabled={isNextDisabled()}
            className="bg-orange-600 text-white px-8 py-3 rounded-xl font-medium hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            {step === 4 ? 'Finish Setup' : 'Continue'}
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </motion.div>
    </div>
  );
}
