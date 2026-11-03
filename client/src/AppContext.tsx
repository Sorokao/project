import React, { createContext, useContext } from "react";
import type { Api, Wallet } from "./api";
import type { Billing } from "./billing";

export type Ctx = { api: Api; billing: Billing; wallet: Wallet | null; setWallet: (w: Wallet) => void };
export const AppCtx = createContext<Ctx | null>(null);
export function useApp(): Ctx {
  const c = useContext(AppCtx);
  if (!c) throw new Error("AppCtx missing");
  return c;
}
