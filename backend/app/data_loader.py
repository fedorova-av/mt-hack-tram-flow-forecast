"""
data_loader.py — отвечает ТОЛЬКО за одно: загрузить таблицу прогнозов
в память и дать другим частям кода функции для фильтрации по ней.

Почему не читаем CSV на каждый запрос:
Файл прогноза — 14 640 строк, это очень мало для компьютера (доли МБ).
Прочитать такой файл с диска на КАЖДЫЙ HTTP-запрос — не только медленно,
но и не нужно: данные не меняются, пока сервер работает. Поэтому мы
читаем файл ОДИН РАЗ при старте сервера (в main.py), кладём в pandas
DataFrame, и дальше все запросы фильтруют уже то, что лежит в оперативной
памяти — это микросекунды на операцию, что и даёт нужную производительность
(p95 < 200-300 мс из требований хакатона мы получим с огромным запасом).
"""

import pandas as pd
from pathlib import Path


class ForecastData:
    """
    Обёртка над DataFrame с прогнозами.
    Хранит данные и умеет отдавать отфильтрованные срезы.
    """

    def __init__(self, csv_path: str):
        self.df = self._load(csv_path)

    @staticmethod
    def _load(csv_path: str) -> pd.DataFrame:
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Не найден файл с прогнозами: {csv_path}. "
                f"Положи submission.csv в папку backend/data/."
            )

        df = pd.read_csv(path, sep=";", encoding="utf-8")

        # Проверяем, что структура файла соответствует ожидаемой —
        # если ML-инженер вдруг отдаст файл с другими названиями колонок,
        # мы узнаем об этом сразу при старте сервера, а не через непонятную
        # ошибку где-то в середине работы API.
        required_columns = {"route", "date", "hour", "prediction"}
        missing = required_columns - set(df.columns)
        if missing:
            raise ValueError(
                f"В файле {csv_path} не хватает колонок: {missing}. "
                f"Ожидается формат: route;date;hour;prediction"
            )

        # Validate before the fast JSON response bypasses per-row Pydantic.
        import numpy as np
        if df.empty or df[list(required_columns)].isna().any().any():
            raise ValueError("Forecast contains empty or missing values")
        for column in ["route", "hour", "prediction"]:
            df[column] = pd.to_numeric(df[column], errors="raise")
            if not np.isfinite(df[column]).all():
                raise ValueError(f"Non-finite forecast column: {column}")
        if any((df[c] % 1 != 0).any() for c in ["route", "hour"]):
            raise ValueError("Route and hour must be integers")
        if not df.hour.between(0, 23).all() or (df.prediction < 0).any():
            raise ValueError("Invalid hour or negative prediction")
        dates = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="raise")
        if not dates.dt.strftime("%Y-%m-%d").eq(df["date"]).all():
            raise ValueError("Dates must use YYYY-MM-DD")
        if df.duplicated(["route", "date", "hour"]).any():
            raise ValueError("Duplicate forecast keys")
        df = df[["route", "date", "hour", "prediction"]].copy()

        # Приводим типы явно, чтобы не гадать, что там подхватилось из CSV
        df["route"] = df["route"].astype(int)
        df["hour"] = df["hour"].astype(int)
        df["prediction"] = df["prediction"].astype(float)
        # дата остаётся строкой в формате YYYY-MM-DD — так её удобнее
        # сравнивать с параметрами запроса, которые тоже придут строками

        return df

    def get_available_routes(self) -> list[int]:
        """Список всех маршрутов, которые есть в прогнозе."""
        return sorted(self.df["route"].unique().tolist())

    def filter(
        self,
        route: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        hour: int | None = None,
    ) -> pd.DataFrame:
        """
        Основная функция фильтрации. Все параметры опциональны —
        если параметр не передан (None), фильтр по нему не применяется.
        """
        result = self.df

        if route is not None:
            result = result[result["route"] == route]

        if date_from is not None:
            result = result[result["date"] >= date_from]

        if date_to is not None:
            result = result[result["date"] <= date_to]

        if hour is not None:
            result = result[result["hour"] == hour]

        return result

    def total_by_route(self) -> pd.Series:
        """Суммарный прогноз по каждому маршруту — для сводки/карты."""
        return self.df.groupby("route")["prediction"].sum()
