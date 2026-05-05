import type {
  Filters,
  Kpis,
  LeaderboardResponse,
  MonthlyResponse,
  PivotResponse,
  Selection,
} from './types';

class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'HttpError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const text = await res.text();

  // Detect proxied login redirects (HTML response when expecting JSON).
  if (text.trim().startsWith('<')) {
    throw new HttpError(
      res.status,
      'Backend returned HTML instead of JSON — likely an auth redirect. ' +
        'If using the remote backend, check that DATABRICKS_TOKEN is valid.',
    );
  }

  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    throw new HttpError(res.status, `Invalid JSON from ${path}: ${text.slice(0, 200)}`);
  }

  if (!res.ok) {
    let msg = `Request to ${path} failed (${res.status})`;
    if (body && typeof body === 'object' && 'message' in body) {
      const m = (body as { message: unknown }).message;
      if (typeof m === 'string' && m.length > 0) msg = m;
    }
    throw new HttpError(res.status, msg);
  }
  return body as T;
}

export const api = {
  health: () => request<{ ok: boolean; mode: string }>('/api/health'),
  filters: () => request<Filters>('/api/dashboard/filters'),
  kpis: (sel: Selection) =>
    request<Kpis>('/api/dashboard/kpis', { method: 'POST', body: JSON.stringify(sel) }),
  monthly: (sel: Selection) =>
    request<MonthlyResponse>('/api/dashboard/monthly', {
      method: 'POST',
      body: JSON.stringify(sel),
    }),
  regionProduct: (sel: Selection) =>
    request<PivotResponse>('/api/dashboard/region-product', {
      method: 'POST',
      body: JSON.stringify(sel),
    }),
  leaderboard: (year: number, month: number) =>
    request<LeaderboardResponse>('/api/dashboard/leaderboard', {
      method: 'POST',
      body: JSON.stringify({ year, month }),
    }),
};
