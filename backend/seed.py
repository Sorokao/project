"""Демо-дані: 2 серіали з відео-заглушками. Запуск: python seed.py"""
import os
from app.db import Base, SessionLocal, engine
from app.models import Episode, Series

SAMPLE = ["https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
          "https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4",
          "https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4",
          "https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerJoyrides.mp4"]

Base.metadata.create_all(engine)
with SessionLocal() as db:
    if not db.query(Series).first():
        for title, genre in [("Таємниця спадкоємиці", "Романтика"), ("Нічна зміна", "Трилер")]:
            s = Series(title=title, genre=genre, description="Демо-серіал (відео-заглушки)",
                       free_episodes=2, coin_price=20)
            db.add(s); db.flush()
            for n in range(1, 9):
                db.add(Episode(series_id=s.id, number=n, title=f"Серія {n}",
                               video_url=SAMPLE[(n - 1) % 4], duration_sec=15))
        db.commit()
print("seeded")
