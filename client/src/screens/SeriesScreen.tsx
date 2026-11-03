import React, { useEffect, useState } from "react";
import { FlatList, Pressable, Text, View, StyleSheet, ActivityIndicator } from "react-native";
import { useApp } from "../AppContext";
import type { Episode, Series } from "../api";
import { C } from "../ui/theme";
import { Button } from "../ui/Button";

export function SeriesScreen({ series, onPlay, onBack }: {
  series: Series; onPlay: (eps: Episode[], index: number) => void; onBack: () => void;
}) {
  const { api } = useApp();
  const [eps, setEps] = useState<Episode[] | null>(null);
  useEffect(() => { api.episodes(series.id).then(setEps).catch(() => setEps([])); }, [series.id]);
  return (
    <View style={s.root}>
      <Pressable onPress={onBack} accessibilityRole="button"><Text style={s.back}>← Назад</Text></Pressable>
      <Text style={s.h1}>{series.title}</Text>
      <Text style={s.sub}>{series.genre} · перші {series.free_episodes} серій безкоштовно</Text>
      <Text style={s.desc}>{series.description}</Text>
      {!eps ? <ActivityIndicator color={C.accent} /> : (
        <>
          <Button title="Дивитись" onPress={() => onPlay(eps, Math.max(0, eps.findIndex((e) => !e.locked)))} />
          <FlatList data={eps} keyExtractor={(e) => String(e.id)} style={{ marginTop: 12 }}
            renderItem={({ item, index }) => (
              <Pressable style={s.row} onPress={() => onPlay(eps, index)}>
                <Text style={s.rowT}>Серія {item.number}</Text>
                <Text style={item.locked ? s.lock : s.free}>{item.locked ? `🔒 ${series.coin_price}` : "Відкрито"}</Text>
              </Pressable>
            )} />
        </>
      )}
    </View>
  );
}
const s = StyleSheet.create({
  root: { flex: 1, padding: 16, gap: 8 }, back: { color: C.accent, fontSize: 16, paddingVertical: 8 },
  h1: { color: C.text, fontSize: 24, fontWeight: "800" }, sub: { color: C.sub }, desc: { color: C.text, marginBottom: 8 },
  row: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: C.border },
  rowT: { color: C.text, fontSize: 16 }, lock: { color: C.gold }, free: { color: C.sub },
});
