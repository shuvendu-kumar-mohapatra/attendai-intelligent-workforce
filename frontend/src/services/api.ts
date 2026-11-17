import axios from 'axios';

const resolveApiBase = (): string => {
  const envUrl = (import.meta.env.VITE_API_URL || '').trim().replace(/\/+$/, '');
  if (!envUrl) return '/api/v1';
  if (envUrl.endsWith('/api/v1')) return envUrl;
  return `${envUrl}/api/v1`;
};

export const API_BASE = resolveApiBase();

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor to inject JWT token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('attendai_token');
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Interceptor to handle 401 token expiry
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && !error.config._retry && !error.config.url.includes('/auth/login')) {
      error.config._retry = true;
      const refreshToken = localStorage.getItem('attendai_refresh_token');
      if (refreshToken) {
        try {
          const res = await axios.post(`${API_BASE}/auth/refresh`, { refresh_token: refreshToken });
          const { access_token, refresh_token: new_refresh } = res.data;
          localStorage.setItem('attendai_token', access_token);
          localStorage.setItem('attendai_refresh_token', new_refresh);
          error.config.headers.Authorization = `Bearer ${access_token}`;
          return api(error.config);
        } catch {
          localStorage.removeItem('attendai_token');
          localStorage.removeItem('attendai_refresh_token');
          localStorage.removeItem('attendai_user');
          window.location.href = '/login';
        }
      } else {
        localStorage.removeItem('attendai_token');
        localStorage.removeItem('attendai_refresh_token');
        localStorage.removeItem('attendai_user');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);
