// Адреса бекенду. Для емулятора Android localhost хоста = 10.0.2.2.
export const API_URL: string = process.env.EXPO_PUBLIC_API_URL ?? "http://10.0.2.2:8000";
// "mock" = тестові покупки (токен mock-...), "play" = реальний Google Play Billing
export const BILLING_MODE: "mock" | "play" = (process.env.EXPO_PUBLIC_BILLING_MODE as "mock" | "play") ?? "mock";
