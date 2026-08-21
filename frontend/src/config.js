// Frontend API Configuration
// Automatically connects to FastAPI Cloud backend in production, or uses local Vite proxy / VITE_API_BASE_URL env if provided.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (typeof window !== 'undefined' &&
  window.location.hostname !== 'localhost' &&
  window.location.hostname !== '127.0.0.1' &&
  !window.location.hostname.includes('fastapicloud.dev')
    ? 'https://rethink-s-crm-5e5c3bf8.fastapicloud.dev'
    : '');
