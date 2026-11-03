import React, { useCallback, useEffect, useRef, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View, useWindowDimensions, Alert } from "react-native";
import { VideoView, useVideoPlayer } from "expo-video";
import { useApp } from "../AppContext";
import { ApiError, type Episode } from "../api";
import { C } from "../ui/theme";
import { Button } from "../ui/Button";

type ItemProps = {
  ep: Episode; coinPrice: number; height: number; active: boolean; near: boolean;
  onOpenWallet: () => void;
};

function EpisodeItem({ ep, coinPrice, height, active, near, onOpenWallet }: ItemProps) {
  const { api, wallet, setWallet } = useApp();
  const [locked, setLocked] = useState(ep.locked);
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const player = useVideoPlayer(url, (p) => { p.loop = true; });

  // Передзавантаження: URL запитуємо, коли серія активна або наступна/попередня
  useEffect(() => {
    if (!near || url || locked) return;
    api.play(ep.id).then((r) => setUrl(r.video_url)).catch((e) => {
      if (e instanceof ApiError && e.status === 402) setLocked(true);
    });
  }, [near, url, locked, ep.id]);

  useEffect(() => {
    if (!url) return;
    if (active) player.play();
    else {
      if (player.currentTime > 0) api.saveProgress(ep.id, player.currentTime).catch(() => {});
      player.pause();
    }
  }, [active, url]);

  const unlock = async () => {
    setBusy(true);
    try {
      const r = await api.unlock(ep.id);
      setWallet(r);
      setLocked(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) {
        Alert.alert("Недостатньо коїнів", "Поповніть гаманець або оформіть VIP", [
          { text: "Скасувати", style: "cancel" }, { text: "Гаманець", onPress: onOpenWallet }]);
      }
    } finally { setBusy(false); }
  };

  return (
    <View style={{ height, backgroundColor: "#000" }}>
      {url && !locked ? <VideoView player={player} style={StyleSheet.absoluteFill} contentFit="cover" nativeControls={false} /> : null}
      <View style={s.badge}><Text style={s.badgeT}>Серія {ep.number}</Text></View>
      {locked ? (
        <View style={s.paywall}>
          <Text style={s.pwT}>🔒 Серія {ep.number}</Text>
          <Text style={s.pwS}>Розблокуйте за {coinPrice} коїнів або оформіть VIP. Баланс: {wallet?.coins ?? 0}</Text>
          <View style={{ gap: 10, alignSelf: "stretch" }}>
            <Button title={`Розблокувати за ${coinPrice} 🪙`} onPress={unlock} busy={busy} />
            <Button kind="ghost" title="Гаманець і VIP" onPress={onOpenWallet} />
          </View>
        </View>
      ) : null}
    </View>
  );
}

export function PlayerScreen({ title, coinPrice, episodes, startIndex, onBack, onOpenWallet }: {
  title: string; coinPrice: number; episodes: Episode[]; startIndex: number; onBack: () => void; onOpenWallet: () => void;
}) {
  const { height } = useWindowDimensions();
  const [index, setIndex] = useState(startIndex);
  const onViewable = useRef(({ viewableItems }: { viewableItems: { index?: number | null }[] }) => {
    const i = viewableItems[0]?.index;
    if (typeof i === "number") setIndex(i);
  }).current;
  const cfg = useRef({ itemVisiblePercentThreshold: 80 }).current;
  const getLayout = useCallback((_: unknown, i: number) => ({ length: height, offset: height * i, index: i }), [height]);

  return (
    <View style={{ flex: 1, backgroundColor: "#000" }}>
      <FlatList data={episodes} keyExtractor={(e) => String(e.id)} pagingEnabled showsVerticalScrollIndicator={false}
        initialScrollIndex={startIndex} getItemLayout={getLayout} windowSize={3} maxToRenderPerBatch={2}
        onViewableItemsChanged={onViewable} viewabilityConfig={cfg}
        renderItem={({ item, index: i }) => (
          <EpisodeItem ep={item} coinPrice={coinPrice} height={height} active={i === index}
            near={Math.abs(i - index) <= 1} onOpenWallet={onOpenWallet} />
        )} />
      <Pressable style={s.back} onPress={onBack} accessibilityRole="button" accessibilityLabel="Назад">
        <Text style={s.backT}>← {title}</Text>
      </Pressable>
    </View>
  );
}

const s = StyleSheet.create({
  back: { position: "absolute", top: 40, left: 12, backgroundColor: "rgba(0,0,0,0.5)", paddingHorizontal: 12, paddingVertical: 8, borderRadius: 20 },
  backT: { color: C.text, fontWeight: "700" },
  badge: { position: "absolute", bottom: 40, left: 16, backgroundColor: "rgba(0,0,0,0.5)", paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  badgeT: { color: C.text },
  paywall: { ...StyleSheet.absoluteFill as object, backgroundColor: "rgba(14,14,18,0.96)", alignItems: "center", justifyContent: "center", gap: 14, padding: 24 },
  pwT: { color: C.text, fontSize: 24, fontWeight: "800" }, pwS: { color: C.sub, textAlign: "center" },
});
