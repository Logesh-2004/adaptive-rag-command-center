/** @type {import('next').NextConfig} */
const nextConfig = {
  async redirects() {
    // The 3D relay used to live at /wormhole while it was a preview; it is now the home page.
    return [{ source: "/wormhole", destination: "/", permanent: false }];
  },
};

export default nextConfig;
