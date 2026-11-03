# Специфікація MVP: застосунок вертикальних серіалів (Android)

Орієнтири: ReelShort, DramaBox, NetShort, My Drama. Пілот: Android, Google Play Billing, бекенд з нуля.

## 1. Користувацький шлях
1. Перший запуск: гостьовий акаунт (device id), без реєстрації. Пізніше додаємо вхід через Google.
2. Головна: стрічка категорій і каталог серіалів (постер, назва, жанр, кількість серій).
3. Екран серіалу: опис, список серій, кнопка «Дивитись».
4. Плеєр: вертикальне відео на весь екран, свайп вгору/вниз між серіями, прогрес, передзавантаження наступної серії.
5. Перші N серій (за замовчуванням 8) безкоштовні. Далі paywall: розблокування коїнами або VIP.
6. Гаманець: баланс, пакети коїнів, щоденний бонус, VIP-підписка (тиждень, місяць, рік).
7. Профіль: історія переглядів, залишок коїнів, статус VIP.

## 2. Економіка (початкові значення, налаштовуються в адмінці)
- Безкоштовних серій: 8.
- Вартість розблокування серії: 10–50 коїнів (поле `coin_price` на серіал).
- Пакети коїнів: $4,99 / $9,99 / $19,99 / $49,99 / $99,99.
- VIP: тиждень $9,99, місяць $19,99, рік; VIP відкриває всі серії без коїнів.
- Щоденний бонус: 5 коїнів, серія днів збільшує бонус до максимуму 30.

## 3. Модель даних
- `users` (id, device_id, created_at, vip_until, coins_balance, last_bonus_at, bonus_streak)
- `series` (id, title, description, genre, poster_url, free_episodes, coin_price, published)
- `episodes` (id, series_id, number, title, video_url, duration_sec)
- `unlocks` (user_id, episode_id, created_at, method)
- `transactions` (id, user_id, kind, coins_delta, product_id, purchase_token, created_at)
- `watch_progress` (user_id, episode_id, position_sec, updated_at)

## 4. API (REST, JWT)
- POST /auth/guest, GET /me
- GET /series, GET /series/{id}, GET /series/{id}/episodes
- GET /episodes/{id}/play (повертає video_url, якщо серія доступна, інакше 402)
- POST /episodes/{id}/unlock (списує коїни)
- GET /wallet, POST /wallet/daily-bonus
- POST /billing/verify (Google Play квитанція: коїни чи VIP; у MVP перевірка через інтерфейс-заглушку)
- POST /progress
- Адмін (ключ у заголовку): POST /admin/series, POST /admin/episodes, PATCH /admin/series/{id}

## 5. Платежі
Реальна перевірка квитанцій потребує сервісного акаунта Google Play Console. У MVP `PlayVerifier` має два режими: `mock` (для тестів і демо) і `google` (підключається, коли будуть акаунт і ключ). Ідемпотентність за `purchase_token`.

## 6. Поза MVP
Rewarded-реклама, DRM, багатомовні доріжки, web-to-app оплата, push, рекомендації, MMP-атрибуція.
