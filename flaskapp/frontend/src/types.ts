export interface Filters {
  years: number[];
  regions: string[];
  products: string[];
}

export interface Selection {
  year: number;
  regions: string[];
  products: string[];
}

export interface Kpis {
  revenue: number;
  orders: number;
  completed: number;
  refunded: number;
}

export interface MonthlyPoint {
  month: number;
  revenue: number;
  orders: number;
}

export interface MonthlyResponse {
  points: MonthlyPoint[];
}

export interface PivotRow {
  region: string;
  product: string;
  revenue: number;
}

export interface PivotResponse {
  rows: PivotRow[];
}

export interface LeaderRow {
  rank: number;
  sales_rep: string;
  orders: number;
  revenue: number;
}

export interface LeaderboardResponse {
  rows: LeaderRow[];
}

export interface ApiError {
  error: string;
  message: string;
}
