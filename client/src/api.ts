export type Wallet = { coins: number; vip: boolean; vip_until: string | null; bonus_streak: number };
export type Series = {
  id: number; title: string; description: string; genre: string; poster_url: string;
  free_episodes: number; coin_price: number; episodes_count: number;
};
export type Episode = { id: number; number: number; title: string; duration_sec: number; locked: boolean };
export type Play = { video_url: string; next_episode_id: number | null };

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`API ${status}: ${JSON.stringify(detail)}`);
  }
}

export interface KeyValueStorage {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
}

export class Api {
  private token: string | null = null;
  constructor(
    private baseUrl: string,
    private storage: KeyValueStorage,
    private newId: () => string,
  ) {}

  /** Повторює init() при мережевих помилках (сервер прокидається). */
  async initWithRetry(attempts = 3, delayMs = 3000, onRetry?: (n: number) => void): Promise<void> {
    for (let i = 1; ; i++) {
      try { return await this.init(); }
      catch (e) {
        if (e instanceof ApiError || i >= attempts) throw e; // відповіді сервера (4xx/5xx) не повторюємо
        onRetry?.(i);
        await new Promise((r) => setTimeout(r, delayMs));
      }
    }
  }

  async init(): Promise<void> {
    let deviceId = await this.storage.get("device_id");
    if (!deviceId) {
      deviceId = this.newId();
      await this.storage.set("device_id", deviceId);
    }
    const r = await this.raw<{ token: string }>("POST", "/auth/guest", { device_id: deviceId }, false);
    this.token = r.token;
  }

  private async raw<T>(method: string, path: string, body?: unknown, auth = true): Promise<T> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (auth && this.token) headers.Authorization = `Bearer ${this.token}`;
    // Безкоштовний хостинг "засинає": перший запит може тривати ~1 хв, тому довгий таймаут
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 75000);
    let res: Response;
    try {
      res = await fetch(this.baseUrl + path, {
        method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: ctrl.signal,
      });
    } finally { clearTimeout(timer); }
    const text = await res.text();
    const data = text ? JSON.parse(text) : null;
    if (!res.ok) throw new ApiError(res.status, data?.detail ?? data);
    return data as T;
  }

  wallet = () => this.raw<Wallet>("GET", "/wallet");
  series = () => this.raw<Series[]>("GET", "/series");
  episodes = (seriesId: number) => this.raw<Episode[]>("GET", `/series/${seriesId}/episodes`);
  play = (episodeId: number) => this.raw<Play>("GET", `/episodes/${episodeId}/play`);
  unlock = (episodeId: number) =>
    this.raw<Wallet & { unlocked: boolean; charged: number }>("POST", `/episodes/${episodeId}/unlock`);
  dailyBonus = () => this.raw<Wallet & { bonus: number }>("POST", "/wallet/daily-bonus");
  verifyPurchase = (productId: string, purchaseToken: string) =>
    this.raw<Wallet & { duplicate: boolean }>("POST", "/billing/verify", {
      product_id: productId, purchase_token: purchaseToken,
    });
  saveProgress = (episodeId: number, positionSec: number) =>
    this.raw<{ ok: boolean }>("POST", "/progress", { episode_id: episodeId, position_sec: Math.floor(positionSec) });
}
