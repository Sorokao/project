import React, { useEffect, useState } from "react";
import { FlatList, Pressable, Text, View, StyleSheet, ActivityIndicator, Image } from "react-native";
import { useApp } from "../AppContext";
import type { Series } from "../api";
import { C } from "../ui/theme";
import { Button } from "../ui/Button";

export function HomeScreen({ onOpen }: { onOpen: (s: Series) => void }) {
  const { api } = useApp();
  const [items, setItems] = useState<Series[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = () => { setErr(null); api.series().then(setItems).catch((e) => setErr(String(e.message ?? e))); };
  useEffect(load, []);

  if (err) return (
    <View style={s.center}><Text style={s.err}>Не вдалося завантажити каталог</Text>
      <Text style={s.sub}>{err}</Text><Button title="Повторити" onPress={load} /></View>);
  if (!items) return <View style={s.center}><ActivityIndicator color={C.accent} /></View>;
  if (items.length === 0) return <View style={s.center}><Text style={s.sub}>Каталог порожній</Text></View>;

  return (
    <FlatList data={items} numColumns={2} keyExtractor={(x) => String(x.id)} contentContainerStyle={{ padding: 12 }}
      columnWrapperStyle={{ gap: 12 }} ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
      renderItem={({ item }) => (
        <Pressable style={s.card} onPress={() => onOpen(item)} accessibilityRole="button" accessibilityLabel={item.title}>
          {item.poster_url ? <Image source={{ uri: item.poster_url }} style={s.poster} />
            : <View style={[s.poster, s.ph]}><Text style={s.phT}>{item.title.slice(0, 1)}</Text></View>}
          <Text style={s.title} numberOfLines={2}>{item.title}</Text>
          <Text style={s.sub}>{item.genre} · {item.episodes_count} серій</Text>
        </Pressable>
      )} />
  );
}
const s = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12, padding: 24 },
  card: { flex: 1 }, poster: { aspectRatio: 3 / 4, borderRadius: 12, backgroundColor: C.card },
  ph: { alignItems: "center", justifyContent: "center" }, phT: { color: C.accent, fontSize: 48, fontWeight: "800" },
  title: { color: C.text, fontWeight: "700", marginTop: 8 }, sub: { color: C.sub, fontSize: 13 }, err: { color: C.text, fontSize: 16 },
});
