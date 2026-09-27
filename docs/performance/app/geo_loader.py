"""
geo_loader.py — загружает route_stops_map.csv (координаты остановок)
и умеет отдавать геометрию маршрута для отрисовки на карте.

Важное про этот файл (см. пояснения от команды):
- География есть ТОЛЬКО для маршрутов 1, 5, 7, 11, 12.
- У каждого маршрута ровно 2 направления (direction_id 0 и 1 — туда/обратно),
  и это РАЗНЫЕ последовательности остановок (не зеркало друг друга).
- Каждое направление имеет свой trip_id.
- Порядок остановок внутри направления задаётся колонкой stop_sequence —
  рисовать линию на карте нужно строго в этом порядке.
- Прямые линии между остановками — это НЕ точная трасса рельсов, а лишь
  приближение (так и оговорено в исходных данных), но для MVP этого
  достаточно.
"""

import pandas as pd
from pathlib import Path


class GeoData:
    def __init__(self, csv_path: str):
        self.df = self._load(csv_path)

    @staticmethod
    def _load(csv_path: str) -> pd.DataFrame:
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Не найден файл геоданных: {csv_path}. "
                f"Положи route_stops_map.csv в папку data/."
            )

        df = pd.read_csv(path, sep=";", encoding="utf-8")

        # Оставляем только строки, которые пригодны для карты и не помечены
        # как удалённые — это защита на случай, если в будущем в файле
        # появятся "мусорные" строки (сейчас их нет, но лучше перестраховаться)
        df = df[
            (df["map_eligible"] == True)
            & (df["valid_coords"] == True)
            & (df["is_deleted"] == 0)
        ]

        return df

    def get_routes_with_map(self) -> list[int]:
        """Маршруты, для которых есть география (сейчас: 1, 5, 7, 11, 12)."""
        return sorted(self.df["route"].unique().tolist())

    def get_route_geometry(self, route: int) -> list[dict] | None:
        """
        Возвращает геометрию маршрута: список направлений, в каждом —
        список остановок ПО ПОРЯДКУ (stop_sequence).
        Если маршрута нет в геоданных — возвращает None (это нормальная
        ситуация для маршрутов 17, 25, 26, 28, 50 — не ошибка).
        """
        route_df = self.df[self.df["route"] == route]

        if route_df.empty:
            return None

        directions = []
        # группируем по паре (trip_id, direction_id) — это ОДНО направление
        for (trip_id, direction_id), group in route_df.groupby(
            ["trip_id", "direction_id"]
        ):
            # обязательно сортируем по stop_sequence — иначе линия на карте
            # получится "вперемешку"
            group = group.sort_values("stop_sequence")

            stops = [
                {
                    "stop_id": int(row["stop_id"]),
                    "stop_name": row["stop_name"],
                    "stop_sequence": int(row["stop_sequence"]),
                    "lat": float(row["stop_lat"]),
                    "lon": float(row["stop_lon"]),
                }
                for _, row in group.iterrows()
            ]

            directions.append(
                {
                    "trip_id": int(trip_id),
                    "direction_id": int(direction_id),
                    "stops": stops,
                }
            )

        return directions
