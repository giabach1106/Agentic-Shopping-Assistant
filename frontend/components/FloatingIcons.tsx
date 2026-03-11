'use client';

import { motion } from 'framer-motion';
import { Dumbbell, Trophy, Bike, Target, Activity, Medal, Flame, HeartPulse, Timer, Zap, Footprints, Compass, Map, Navigation, Crosshair, Flag, Tent, Mountain, Waves, Wind } from 'lucide-react';

const ICONS = [Dumbbell, Trophy, Bike, Target, Activity, Medal, Flame, HeartPulse, Timer, Zap, Footprints, Compass, Map, Navigation, Crosshair, Flag, Tent, Mountain, Waves, Wind];

export default function FloatingIcons() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
      {ICONS.map((Icon, index) => {
        // We create a "pseudo-random" layout using the index
        // This stays the same every time the page loads!
        const x = (index * 17) % 100; // Spreads them horizontally
        const y = (index * 23) % 100; // Spreads them vertically
        const rotation = (index * 45) % 360;
        const size = 35 + (index % 3) * 10;

        return (
          <div
            key={index}
            className="absolute text-orange-500/10"
            style={{
              left: `${x}vw`,
              top: `${y}vh`,
              transform: `scale(${size / 40}) rotate(${rotation}deg)`,
            }}
          >
            <Icon size={40} strokeWidth={1.5} />
          </div>
        );
      })}
    </div>
  );
}