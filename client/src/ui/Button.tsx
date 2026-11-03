import React from "react";
import { Pressable, Text, StyleSheet, ActivityIndicator } from "react-native";
import { C } from "./theme";

export function Button({ title, onPress, kind = "primary", busy = false }: {
  title: string; onPress: () => void; kind?: "primary" | "ghost"; busy?: boolean;
}) {
  return (
    <Pressable onPress={busy ? undefined : onPress}
      style={[s.btn, kind === "ghost" ? s.ghost : s.primary]} accessibilityRole="button">
      {busy ? <ActivityIndicator color="#fff" /> : <Text style={s.t}>{title}</Text>}
    </Pressable>
  );
}
const s = StyleSheet.create({
  btn: { paddingVertical: 14, paddingHorizontal: 18, borderRadius: 12, alignItems: "center", minHeight: 48, justifyContent: "center" },
  primary: { backgroundColor: C.accent },
  ghost: { borderWidth: 1, borderColor: C.border, backgroundColor: "transparent" },
  t: { color: C.text, fontWeight: "700", fontSize: 16 },
});
