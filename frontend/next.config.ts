import type { NextConfig } from 'next';
import fs from 'fs';
import path from 'path';

function stripWrappingQuotes(value: string) {
  const trimmed = value.trim();
  if (
    trimmed.length >= 2 &&
    ((trimmed.startsWith('"') && trimmed.endsWith('"')) ||
      (trimmed.startsWith("'") && trimmed.endsWith("'")))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function loadRootEnvDefaults() {
  const envPath = path.resolve(__dirname, '..', '.env');
  if (!fs.existsSync(envPath)) {
    return;
  }

  const lines = fs.readFileSync(envPath, 'utf8').split(/\r?\n/);
  for (const rawLine of lines) {
    let line = rawLine.trim();
    if (!line || line.startsWith('#')) {
      continue;
    }
    if (line.startsWith('export ')) {
      line = line.slice('export '.length).trim();
    }
    const separatorIndex = line.indexOf('=');
    if (separatorIndex <= 0) {
      continue;
    }
    const key = line.slice(0, separatorIndex).trim();
    if (!key) {
      continue;
    }

    // Keep root .env as single source of truth for browser-exposed settings.
    const shouldOverride = key.startsWith('NEXT_PUBLIC_');
    if (!shouldOverride && process.env[key]) {
      continue;
    }
    const rawValue = line.slice(separatorIndex + 1);
    process.env[key] = stripWrappingQuotes(rawValue);
  }
}

loadRootEnvDefaults();

const nextConfig: NextConfig = {
  reactStrictMode: true,

  turbopack: {
    root: path.join(__dirname),
  },

  outputFileTracingRoot: path.join(__dirname),

  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'picsum.photos', pathname: '/**' },
      { protocol: 'https', hostname: 'images.unsplash.com', pathname: '/**' },
      { protocol: 'https', hostname: 'images-na.ssl-images-amazon.com', pathname: '/**' },
      { protocol: 'https', hostname: 'm.media-amazon.com', pathname: '/**' },
      { protocol: 'https', hostname: 'i.ebayimg.com', pathname: '/**' },
      { protocol: 'https', hostname: 'i5.walmartimages.com', pathname: '/**' },
      { protocol: 'https', hostname: 'i.redd.it', pathname: '/**' },
      { protocol: 'https', hostname: 'external-preview.redd.it', pathname: '/**' },
      { protocol: 'https', hostname: 'preview.redd.it', pathname: '/**' },
    ],
  },
};

export default nextConfig;
