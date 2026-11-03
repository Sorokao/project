import type { Product } from "./products";

export type PurchaseResult = { productId: string; purchaseToken: string };

export interface Billing {
  /** Відкриває платіжний потік і повертає токен покупки, який ми віддаємо бекенду. */
  buy(product: Product): Promise<PurchaseResult>;
  /** Викликати ПІСЛЯ успішної верифікації бекендом, щоб підтвердити/спожити покупку. */
  complete(result: PurchaseResult, product: Product): Promise<void>;
}

let counter = 0;
export class MockBilling implements Billing {
  async buy(product: Product): Promise<PurchaseResult> {
    counter += 1;
    return { productId: product.id, purchaseToken: `mock-${Date.now()}-${counter}` };
  }
  async complete(): Promise<void> {}
}

/** Реальний Google Play Billing через expo-iap (потрібен dev/production build, не Expo Go). */
export class PlayBilling implements Billing {
  private connected = false;
  private pending = new Map<string, any>();

  private async ensure() {
    const { Platform } = await import("react-native");
    if (Platform.OS !== "android") throw new Error("Play Billing працює лише на Android");
    if (!this.connected) {
      const iap = await import("expo-iap");
      await iap.initConnection();
      this.connected = true;
    }
    return import("expo-iap");
  }

  async buy(product: Product): Promise<PurchaseResult> {
    const iap = await this.ensure();
    const isSubs = product.kind === "vip";
    const found = await iap.fetchProducts({ skus: [product.id], type: isSubs ? "subs" : "in-app" });
    if (!found || found.length === 0) throw new Error(`Продукт ${product.id} не знайдено в Play Console`);

    const purchase = await new Promise<any>((resolve, reject) => {
      const ok = iap.purchaseUpdatedListener((p: any) => {
        if (p.productId === product.id) { ok.remove(); err.remove(); resolve(p); }
      });
      const err = iap.purchaseErrorListener((e: any) => { ok.remove(); err.remove(); reject(new Error(e?.message ?? "purchase_error")); });
      const start = isSubs
        ? iap.requestPurchase({
            type: "subs",
            request: {
              google: {
                skus: [product.id],
                subscriptionOffers: (found[0] as any).subscriptionOffers
                  ?.filter((o: any) => o.offerTokenAndroid)
                  .slice(0, 1)
                  .map((o: any) => ({ sku: product.id, offerToken: o.offerTokenAndroid })),
              },
            },
          })
        : iap.requestPurchase({ type: "in-app", request: { google: { skus: [product.id] } } });
      Promise.resolve(start).catch((e) => { ok.remove(); err.remove(); reject(e); });
    });

    const token: string | null | undefined = purchase.purchaseToken;
    if (!token) throw new Error("Немає purchaseToken у відповіді Play");
    this.pending.set(token, purchase);
    return { productId: product.id, purchaseToken: token };
  }

  async complete(result: PurchaseResult, product: Product): Promise<void> {
    const iap = await this.ensure();
    const purchase = this.pending.get(result.purchaseToken);
    if (!purchase) return;
    await iap.finishTransaction({ purchase, isConsumable: product.kind === "coins" });
    this.pending.delete(result.purchaseToken);
  }
}
