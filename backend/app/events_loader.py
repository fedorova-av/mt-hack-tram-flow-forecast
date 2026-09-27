"""
events_loader.py — отвечает за реестр календарных правил и транспортных
событий, которые ML-инженеры УЖЕ учли внутри прогноза (файл
data/calendar_and_events.json).

Важно: этот модуль ничего не пересчитывает и не меняет prediction.
Он только объясняет пользователю ЧЕЛОВЕЧЕСКИМ ЯЗЫКОМ, какие правила
сработали для конкретных даты и маршрута — чтобы не пришлось второй раз
накладывать эти же поправки в интерфейсе (это задвоило бы эффект).

Тексты ниже написаны нарочно просто, без терминов вроде "фактор" или
"T1-factor" — это то, что увидит на странице дежурный/жюри, а не
ML-инженер.
"""

import json
from datetime import date as date_cls
from pathlib import Path


class EventsRegistry:
    def __init__(self, json_path: str):
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"Не найден файл с календарём событий: {json_path}")
        with open(path, "r", encoding="utf-8") as f:
            self.raw = json.load(f)

        self.sources = {s["id"]: s for s in self.raw.get("sources", [])}
        self.calendar_rules = self.raw.get("calendar_rules", [])
        self.transport_events = self.raw.get("transport_events", [])

    def _source_url(self, source_id: str | None) -> str | None:
        if not source_id:
            return None
        src = self.sources.get(source_id)
        return src["url"] if src else None

    @staticmethod
    def _parse(d: str) -> date_cls:
        y, m, day = map(int, d.split("-"))
        return date_cls(y, m, day)

    @staticmethod
    def _in_range(d: date_cls, start: str | None, end: str | None) -> bool:
        if start and d < EventsRegistry._parse(start):
            return False
        if end and d > EventsRegistry._parse(end):
            return False
        return True

    def applied_for(self, route: int, date_from: str, date_to: str) -> list[dict]:
        """
        Возвращает список правил, которые сработали хотя бы для одного дня
        в диапазоне [date_from, date_to] на заданном маршруте.
        Каждый элемент — готовый для показа на странице текст + ссылка
        на первоисточник (если есть).
        """
        d_from = self._parse(date_from)
        d_to = self._parse(date_to)
        result: list[dict] = []

        # --- Праздничные дни ---
        for rule in self.calendar_rules:
            if rule["id"] == "official_holidays_2025":
                holiday_dates = [self._parse(dd) for dd in rule["dates"]]
                matched = [dd for dd in holiday_dates if d_from <= dd <= d_to]
                if matched:
                    result.append({
                        "text": "В выбранный период попадают праздничные дни — в эти дни "
                                "прогноз строится по воскресному расписанию, а не по обычному.",
                        "url": self._source_url(rule.get("source_id")),
                    })
            elif rule["id"] == "working_saturday_2025_11_01":
                if self._in_range(self._parse("2025-11-01"), date_from, date_to) or \
                   (d_from <= self._parse("2025-11-01") <= d_to):
                    result.append({
                        "text": "1 ноября — рабочая суббота по производственному календарю. "
                                "Прогноз на этот день частично построен как для пятницы.",
                        "url": self._source_url(rule.get("source_id")),
                    })

        # --- Транспортные события ---
        for ev in self.transport_events:
            if route not in ev.get("routes", []):
                continue
            if not self._in_range(d_from, ev.get("date_start"), ev.get("date_end")) and \
               not self._in_range(d_to, ev.get("date_start"), ev.get("date_end")):
                # ни начало, ни конец запрошенного периода не попадают в
                # действие правила — проверим ещё пересечение целиком
                start = self._parse(ev["date_start"]) if ev.get("date_start") else None
                end = self._parse(ev["date_end"]) if ev.get("date_end") else None
                overlaps = (start is None or start <= d_to) and (end is None or end >= d_from)
                if not overlaps:
                    continue

            url = self._source_url(ev.get("source_id"))

            if ev["id"] == "route_5_launch":
                result.append({
                    "text": "Маршрут 5 был запущен 16 декабря 2025 года. До этой даты по нему "
                            "нет движения, прогноз равен нулю. После запуска прогноз строится "
                            "на основе маршрута 25 со сниженным коэффициентом (маршрут новый, "
                            "истории поездок ещё нет).",
                    "url": url,
                })
            elif ev["id"] == "t1_launch_and_route_7_transfer":
                result.append({
                    "text": "С 12 ноября 2025 года запущена линия Т1. Часть пассажиров "
                            "маршрута 7 могла пересесть на неё — прогноз для маршрута 7 "
                            "снижен с учётом этого оттока.",
                    "url": url,
                })
            elif ev["id"] == "early_evening_restriction_routes_7_50":
                result.append({
                    "text": "До 14 ноября 2025 года действовали ограничения поздних рейсов "
                            "на маршрутах 7 и 50 — прогноз на поздние вечерние часы (22:00–23:00) "
                            "в этот период снижен.",
                    "url": url,
                })
            elif ev["id"] == "weekend_route_restore_7_50":
                result.append({
                    "text": "С 15 ноября 2025 года на маршрутах 7 и 50 восстановлено обычное "
                            "движение по выходным — прогноз на выходные дни с этой даты "
                            "рассчитан как для обычного, а не сокращённого маршрута.",
                    "url": url,
                })
            elif ev["id"] == "late_weekend_restriction_routes_7_50":
                result.append({
                    "text": "С 13 декабря 2025 года по выходным на маршрутах 7 и 50 введено "
                            "ограничение позднего вечернего движения (23:00) — прогноз на этот "
                            "час в выходные снижен.",
                    "url": url,
                })

        return result
