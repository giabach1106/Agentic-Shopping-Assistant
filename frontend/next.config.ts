import type { NextConfig } from 'next';
import path from 'path';

const nextConfig: NextConfig = {
  reactStrictMode: true,

  turbopack: {
    root: '.', 
  },
  
  outputFileTracingRoot: path.join(__dirname),
  
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'picsum.photos', pathname: '/**' },
      { protocol: 'https', hostname: 'images.unsplash.com', pathname: '/**' },
    ],
  },
  transpilePackages: ['framer-motion', 'motion'],
};

export default nextConfig;