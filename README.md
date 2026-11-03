# Застосунок вертикальних серіалів: MVP для Android (пілот)

Стан: робочий скелет. Бекенд і клієнт зв'язані й перевірені автоматично; збірка APK і реальні платежі потребують ваших акаунтів (див. «Що лишилось»).

## Структура
- `docs/SPEC.md`: специфікація, економіка, модель даних, API.
- `backend/`: FastAPI + SQLite (для пілоту; для зростання замінити на PostgreSQL через `DATABASE_URL`).
- `client/`: Expo (React Native) + TypeScript, Android.

## 1. Запуск бекенду
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python seed.py                      # демо-дані (відео-заглушки)
export JWT_SECRET="$(openssl rand -hex 32)" ADMIN_KEY="$(openssl rand -hex 16)"
uvicorn app.main:app --host 0.0.0.0 --port 8000
pytest                              # 9 автотестів
```
Додати серіал: `POST /admin/series` і `POST /admin/episodes` із заголовком `X-Admin-Key`. Документація API: `http://localhost:8000/docs`.

Деплой: `backend/Dockerfile` (змонтуйте том `/data`). Обов'язково задайте `JWT_SECRET` і `ADMIN_KEY` у змінних середовища.

## 2. Клієнт
```bash
cd client
npm install
npx tsc --noEmit                    # перевірка типів
API_URL=http://127.0.0.1:8000 npx tsx scripts/e2e.ts   # інтеграційний тест клієнта проти бекенду
```
### Збірка APK (EAS Build, у хмарі Expo)
1. Створіть акаунт на expo.dev, `npm i -g eas-cli`, `eas login`, `eas init`.
2. У `client/eas.json` замініть `https://YOUR-BACKEND-URL` на адресу бекенду (має бути HTTPS).
3. У `client/app.json` замініть `android.package` (зараз `com.example.vdrama`) на власний ідентифікатор.
4. `eas build -p android --profile preview` дає APK для встановлення на телефон (платежі в режимі `mock`).
5. Для Play Market: `eas build -p android --profile production` дає AAB.

## 3. Платежі
- Клієнт: `client/src/billing.ts`. `MockBilling` (демо) і `PlayBilling` (бібліотека `expo-iap`, потрібна збірка через EAS, не Expo Go).
- Бекенд: `backend/app/billing.py`. Режим `PLAY_VERIFY_MODE=mock` приймає лише токени `mock-...`. Режим `google` треба дописати: виклик Google Play Developer API із сервісним акаунтом (з'являється після акаунта Play Console). **Без цього не вмикайте реальні покупки**, інакше будь-хто зможе отримати коїни підробленим токеном.
- Продукти в Play Console мають мати ті самі ідентифікатори, що в `client/src/products.ts`: `coins_499`, `coins_999`, `coins_1999`, `coins_4999`, `coins_9999` (одноразові, споживні) і `vip_week`, `vip_month`, `vip_year` (підписки).

## Що перевірено
- Бекенд: 9 автотестів (`pytest`) проходять.
- Клієнт: `tsc --noEmit` без помилок; `scripts/e2e.ts` проходить увесь сценарій клієнт → бекенд (гість, каталог, безкоштовні серії, заборона, покупка, ідемпотентність, розблокування, бонус, VIP); `expo export --platform android` збирає JS-бандл (Hermes, 663 модулі).

## Що НЕ перевірено і що лишилось
- APK не збирався (у хмарному середовищі закритий доступ до Android SDK/Gradle). Перша збірка в EAS може потребувати правок конфігурації.
- Відео-плеєр, свайп і передзавантаження не запускались на пристрої чи емуляторі: перевірте на реальному Android.
- `PlayBilling` написано за типами `expo-iap`, але з реальним Play Billing не тестувалось (потрібен акаунт і тестова доріжка).
- Верифікація квитанцій Google на бекенді не реалізована (режим `google` викидає помилку навмисно).
- Немає: реєстрації через Google, push, rewarded-реклами, DRM, багатомовності, адмін-інтерфейсу (лише API), CDN для відео (замініть заглушки на HLS/MP4 зі свого сховища).
- Публікація в Play Market: акаунт розробника (організаційний уникає 14-денного закритого тесту), політика приватності, Data safety, вікове рейтингування, скріншоти.

## Локальна збірка APK (перевірено в хмарному середовищі)
`npx expo prebuild --platform android`, у `android/gradle.properties` вимкнути minify (`android.enableMinifyInReleaseBuilds=false`), далі `./gradlew assembleRelease -x lint -x lintVitalRelease -x lintVitalAnalyzeRelease -x lintVitalReportRelease` з `EXPO_PUBLIC_API_URL=<адреса бекенду>`. Потрібні JDK 17+ і Android SDK (platform 36/37, build-tools 36). APK підписується debug-ключем: для Play Market використовуйте `eas build --profile production` (AAB, підпис Play App Signing).
Збірка для пілоту містить лише arm64-v8a (не запуститься на x86-емуляторі).

## Хостинг без грошей: Render + Neon (Postgres)
Перевірено: 9 автотестів бекенду проходять на реальному PostgreSQL 16 (SQLAlchemy 2.0 і 2.1, драйвер psycopg 3). Рядок `postgres://` / `postgresql://` бекенд сам перетворює на `postgresql+psycopg://`.
1. Neon: створити акаунт і проєкт, скопіювати рядок підключення (Connection string, має `sslmode=require`).
2. Код покласти в приватний репозиторій GitHub (Render розгортає з нього; файл `render.yaml` у корені).
3. Render: New → Blueprint → вибрати репозиторій. У змінній `DATABASE_URL` вставити рядок з Neon. `JWT_SECRET` і `ADMIN_KEY` Render згенерує сам (їх можна побачити в Environment; `ADMIN_KEY` потрібен для додавання серіалів).
4. Після розгортання адреса буде `https://vdrama-api-xxxx.onrender.com`. Перевірка: відкрити `/health` у браузері (перший запит до 1 хв).
5. Перезібрати APK з `EXPO_PUBLIC_API_URL=<ця адреса>`.
Безкоштовний Render засинає за 15 хв простою, застосунок показує «Сервер прокидається…». Для тестувальників Google Play переходьте на платний always-on.
