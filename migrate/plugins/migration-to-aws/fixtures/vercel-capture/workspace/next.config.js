/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [{ protocol: "https", hostname: "cdn.acme-shop.com" }],
  },
  experimental: {},
};

module.exports = nextConfig;
