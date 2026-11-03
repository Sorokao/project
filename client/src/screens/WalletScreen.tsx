import React, { useState } from "react";
import { ScrollView, Text, View, StyleSheet, Alert } from "react-native";
import { useApp } from "../AppContext";
import { PRODUCTS, type Product } from "../products";
import { ApiError } from "../api";
import { C } from "../ui/theme";
import { Button } from "../ui/Button";

export function WalletScreen() {
  const { api, billing, wallet, setWallet } = useApp();
  const [busyId, setBusyId] = useState<string | null>(null);

  const claim = async () => {
    setBusyId("bonus");
    try { const r = await api.dailyBonus(); setWallet(r); Alert.alert("Бонус", `+${r.bonus} коїнів`); }
    catch (e) { Alert.alert("Бонус", e instanceof ApiError && e.status === 429 ? "Бонус уже отримано, повертайтесь завтра" : "Помилка"); }
    finally { setBusyId(null); }
  };

  const buy = async (p: Product) => {
    setBusyId(p.id);
    try {
      const res = await billing.buy(p);
      const w = await api.verifyPurchase(res.productId, res.purchaseToken); // спочатку перевірка на бекенді
      await billing.complete(res, p);                                        // потім підтвердження в Play
      setWallet(w);
    } catch (e) { Alert.alert("Покупка не вдалася", String((e as Error).message ?? e)); }
    finally { setBusyId(null); }
  };

  return (
    <ScrollView contentContainerStyle={s.root}>
      <View style={s.card}>
        <Text style={s.big}>🪙 {wallet?.coins ?? 0}</Text>
        <Text style={s.sub}>{wallet?.vip ? `VIP до ${wallet.vip_until?.slice(0, 10)}` : "VIP не активний"}</Text>
        <Button kind="ghost" title="Щоденний бонус" onPress={claim} busy={busyId === "bonus"} />
      </View>
      {PRODUCTS.map((p) => (
        <View key={p.id} style={s.row}>
          <View style={{ flex: 1 }}><Text style={s.t}>{p.title}</Text><Text style={s.sub}>{p.subtitle}</Text></View>
          <View style={{ width: 110 }}><Button title={p.price} onPress={() => buy(p)} busy={busyId === p.id} /></View>
        </View>
      ))}
    </ScrollView>
  );
}
const s = StyleSheet.create({
  root: { padding: 16, gap: 12 }, card: { backgroundColor: C.card, borderRadius: 16, padding: 16, gap: 10 },
  big: { color: C.gold, fontSize: 32, fontWeight: "800" }, sub: { color: C.sub }, t: { color: C.text, fontWeight: "700", fontSize: 16 },
  row: { flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: C.card, borderRadius: 12, padding: 12 },
});
