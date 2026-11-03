"""Каталог продуктів і верифікація квитанцій Google Play.

Режим `mock` (за замовчуванням) довіряє токенам, що починаються з "mock-".
Режим `google` буде викликати Google Play Developer API після появи акаунта.
"""
import os
from dataclasses import dataclass
from datetime import timedelta

# Базова ставка: $0.99 = 100 коїнів. Чим більший пакет, тим більший бонус (+0% … +60%).
COIN_PACKS = {
    "coins_099": 100, "coins_199": 220, "coins_499": 600, "coins_999": 1300,
    "coins_1999": 2800, "coins_4999": 7500, "coins_9999": 16000,
}
# Одноразовий бонус за першу покупку коїнів: стартовий пакет утричі, решта +100.
FIRST_PURCHASE_BONUS = {"coins_099": 200}
FIRST_PURCHASE_DEFAULT = 100
VIP_PLANS = {
    "vip_week": timedelta(days=7), "vip_month": timedelta(days=30), "vip_year": timedelta(days=365),
}


@dataclass
class Verified:
    ok: bool
    reason: str = ""


def verify_purchase(product_id: str, purchase_token: str) -> Verified:
    mode = os.getenv("PLAY_VERIFY_MODE", "mock")
    if product_id not in COIN_PACKS and product_id not in VIP_PLANS:
        return Verified(False, "unknown_product")
    if mode == "mock":
        return Verified(purchase_token.startswith("mock-"), "" if purchase_token.startswith("mock-") else "bad_token")
    if mode == "google":
        raise NotImplementedError("Підключіть Google Play Developer API (сервісний акаунт) у Play Console")
    return Verified(False, "bad_mode")
