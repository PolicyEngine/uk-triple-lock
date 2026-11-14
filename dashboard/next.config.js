/** @type {import('next').NextConfig} */
const basePath = "/uk/triple-lock";

const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@policyengine/ui-kit"],
  // Served through the policyengine.org multizone rewrite at
  // /uk/triple-lock, so pages and /_next assets must
  // resolve under that prefix.
  basePath,
  // Next.js only auto-prefixes next/link, next/image and static imports. Raw
  // fetch() calls and plain <img src> need this explicitly.
  env: {
    NEXT_PUBLIC_BASE_PATH: basePath,
  },
  // The working paper is a static wrapper at public/paper/index.html that
  // frames the rendered manuscript in public/paper/web/. Its links are
  // relative (web/index.html, ../), so it must be served at /paper/ with the
  // trailing slash. Next's default redirect would strip it, so that redirect
  // is skipped; proxy.js sends a bare /paper to /paper/.
  skipTrailingSlashRedirect: true,
  // Keep the bare deployment URL (linked from the README and repo page)
  // working now that the app lives under basePath.
  async redirects() {
    return [
      { source: "/", destination: basePath, basePath: false, permanent: false },
    ];
  },
  async rewrites() {
    return {
      beforeFiles: [{ source: "/paper/", destination: "/paper/index.html" }],
    };
  },
};

module.exports = nextConfig;
