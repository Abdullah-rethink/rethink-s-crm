// Frontend API Configuration
// In production on Vercel, requests to /api are proxied to FastAPI Cloud via vercel.json edge rewrites, completely preventing CORS restrictions.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

