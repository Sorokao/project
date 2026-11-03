// Ідентифікатори продуктів мають збігатися з Play Console і з backend/app/billing.py
export type Product = { id: string; title: string; subtitle: string; price: string; kind: "coins" | "vip" };

export const PRODUCTS: Product[] = [
  { id: "coins_499", title: "500 коїнів", subtitle: "Стартовий пакет", price: "$4.99", kind: "coins" },
  { id: "coins_999", title: "1100 коїнів", subtitle: "+10% бонус", price: "$9.99", kind: "coins" },
  { id: "coins_1999", title: "2400 коїнів", subtitle: "+20% бонус", price: "$19.99", kind: "coins" },
  { id: "coins_4999", title: "6500 коїнів", subtitle: "+30% бонус", price: "$49.99", kind: "coins" },
  { id: "coins_9999", title: "14000 коїнів", subtitle: "+40% бонус", price: "$99.99", kind: "coins" },
  { id: "vip_week", title: "VIP на тиждень", subtitle: "Усі серії без коїнів", price: "$9.99", kind: "vip" },
  { id: "vip_month", title: "VIP на місяць", subtitle: "Усі серії без коїнів", price: "$19.99", kind: "vip" },
  { id: "vip_year", title: "VIP на рік", subtitle: "Найвигідніше", price: "$99.99", kind: "vip" },
];
