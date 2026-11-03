import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, SafeAreaView, StatusBar, StyleSheet, Text, View } from "react-native";
import * as SecureStore from "expo-secure-store";
import * as Crypto from "expo-crypto";
import { Api, type Episode, type Series, type Wallet } from "./src/api";
import { MockBilling, PlayBilling, type Billing } from "./src/billing";
import { API_URL, BILLING_MODE } from "./src/config";
import { AppCtx } from "./src/AppContext";
import { HomeScreen } from "./src/screens/HomeScreen";
import { SeriesScreen } from "./src/screens/SeriesScreen";
import { PlayerScreen } from "./src/screens/PlayerScreen";
import { WalletScreen } from "./src/screens/WalletScreen";
import { Button } from "./src/ui/Button";
import { C } from "./src/ui/theme";

type Route =
  | { name: "home" } | { name: "wallet" }
  | { name: "series"; series: Series }
  | { name: "player"; series: Series; episodes: Episode[]; index: number };

export default function App() {
  const api = useMemo(() => new Api(API_URL, {
    get: (k) => SecureStore.getItemAsync(k),
    set: (k, v) => SecureStore.setItemAsync(k, v),
  }, () => Crypto.randomUUID()), []);
  const billing: Billing = useMemo(() => (BILLING_MODE === "play" ? new PlayBilling() : new MockBilling()), []);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [waking, setWaking] = useState(false);
  const [route, setRoute] = useState<Route>({ name: "home" });

  const boot = () => {
    setError(null);
    api.initWithRetry(3, 3000, () => setWaking(true)).then(() => api.wallet()).then((w) => { setWallet(w); setReady(true); setWaking(false); })
      .catch((e) => { setWaking(false); setError(String(e?.message ?? e)); });
  };
  useEffect(boot, []);

  if (error) return (
    <SafeAreaView style={s.center}><Text style={s.t}>Немає зв'язку з сервером</Text>
      <Text style={s.sub}>{error}</Text><Button title="Повторити" onPress={boot} /></SafeAreaView>);
  if (!ready) return (
    <View style={s.center}><ActivityIndicator color={C.accent} />
      {waking ? <Text style={s.sub}>Сервер прокидається, зачекайте до хвилини…</Text> : null}</View>);

  const tab = route.name === "wallet" ? "wallet" : "home";
  return (
    <AppCtx.Provider value={{ api, billing, wallet, setWallet }}>
      <StatusBar barStyle="light-content" />
      {route.name === "player" ? (
        <PlayerScreen title={route.series.title} coinPrice={route.series.coin_price} episodes={route.episodes}
          startIndex={route.index} onBack={() => setRoute({ name: "series", series: route.series })}
          onOpenWallet={() => setRoute({ name: "wallet" })} />
      ) : (
        <SafeAreaView style={s.root}>
          <View style={s.top}><Text style={s.logo}>Драма</Text><Text style={s.coins}>🪙 {wallet?.coins ?? 0}{wallet?.vip ? "  VIP" : ""}</Text></View>
          <View style={{ flex: 1 }}>
            {route.name === "home" && <HomeScreen onOpen={(series) => setRoute({ name: "series", series })} />}
            {route.name === "series" && (
              <SeriesScreen series={route.series} onBack={() => setRoute({ name: "home" })}
                onPlay={(episodes, index) => setRoute({ name: "player", series: route.series, episodes, index })} />)}
            {route.name === "wallet" && <WalletScreen />}
          </View>
          <View style={s.tabs}>
            <Pressable style={s.tab} onPress={() => setRoute({ name: "home" })}><Text style={tab === "home" ? s.on : s.off}>Каталог</Text></Pressable>
            <Pressable style={s.tab} onPress={() => setRoute({ name: "wallet" })}><Text style={tab === "wallet" ? s.on : s.off}>Гаманець</Text></Pressable>
          </View>
        </SafeAreaView>
      )}
    </AppCtx.Provider>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg }, center: { flex: 1, backgroundColor: C.bg, alignItems: "center", justifyContent: "center", gap: 12, padding: 24 },
  top: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: 16, paddingTop: 36, paddingBottom: 8 },
  logo: { color: C.accent, fontSize: 24, fontWeight: "900" }, coins: { color: C.gold, fontWeight: "700" },
  tabs: { flexDirection: "row", borderTopWidth: 1, borderTopColor: C.border }, tab: { flex: 1, alignItems: "center", paddingVertical: 14 },
  on: { color: C.accent, fontWeight: "700" }, off: { color: C.sub }, t: { color: C.text, fontSize: 18 }, sub: { color: C.sub, textAlign: "center" },
});
