// Інтеграційний тест: справжній Api-клієнт проти запущеного бекенду.
import { Api, ApiError } from "../src/api";
import { MockBilling } from "../src/billing";
import { PRODUCTS } from "../src/products";

const mem = new Map<string, string>();
const storage = { get: async (k: string) => mem.get(k) ?? null, set: async (k: string, v: string) => { mem.set(k, v); } };
const eq = (a: unknown, b: unknown, m: string) => { if (JSON.stringify(a) !== JSON.stringify(b)) { throw new Error(`FAIL ${m}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`); } console.log("ok  ", m); };

(async () => {
  const api = new Api(process.env.API_URL ?? "http://127.0.0.1:8000", storage, () => "test-device-" + Math.random().toString(36).slice(2));
  await api.init();
  eq((await api.wallet()).coins, 0, "новий гаманець порожній");
  const series = await api.series();
  eq(series.length >= 1, true, "каталог не порожній");
  const eps = await api.episodes(series[0].id);
  eq(eps.slice(0, 2).every((e) => !e.locked) && eps[2].locked, true, "2 безкоштовні, 3-тя заблокована");
  try { await api.play(eps[2].id); throw new Error("мало бути 402"); } catch (e) { eq((e as ApiError).status, 402, "play заблокованої = 402"); }
  const billing = new MockBilling();
  const pack = PRODUCTS.find((p) => p.id === "coins_499")!;
  const r = await billing.buy(pack);
  eq((await api.verifyPurchase(r.productId, r.purchaseToken)).coins, 500, "покупка 500 коїнів");
  eq((await api.verifyPurchase(r.productId, r.purchaseToken)).duplicate, true, "повторний токен ідемпотентний");
  const u = await api.unlock(eps[2].id);
  eq([u.charged, u.coins], [20, 480], "розблокування списує 20");
  eq((await api.play(eps[2].id)).next_episode_id, eps[3].id, "play повертає наступну серію");
  eq((await api.dailyBonus()).bonus, 5, "щоденний бонус +5");
  try { await api.dailyBonus(); throw new Error("мало бути 429"); } catch (e) { eq((e as ApiError).status, 429, "другий бонус = 429"); }
  const vip = await api.verifyPurchase("vip_week", (await billing.buy(PRODUCTS.find((p) => p.id === "vip_week")!)).purchaseToken);
  eq(vip.vip, true, "VIP активовано");
  await api.saveProgress(eps[0].id, 7.4);
  console.log("E2E PASSED");
})().catch((e) => { console.error(e); process.exit(1); });
