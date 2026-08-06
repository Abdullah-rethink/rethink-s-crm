// Frontend API Configuration
// Uses VITE_API_BASE_URL from .env if defined, or defaults to relative base URL ("") for deployment portability
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
