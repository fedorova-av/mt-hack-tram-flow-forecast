from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path


EXPECTED_COLUMNS = ["route", "date", "hour", "prediction"]
EXPECTED_ROWS = 14_640
EXPECTED_SUM = 12_550_152
EXPECTED_SHA256 = "91db17acbbc18bb8ac845a2c90ddd946a1d6fff74cf4123a51ac6b31f45cc8f8"


def main() -> None:
    parser = argparse.ArgumentParser(description="Проверка структуры и контрольной суммы submission v3")
    parser.add_argument("path", nargs="?", default="outputs/submission.csv")
    parser.add_argument(
        "--allow-different-hash",
        action="store_true",
        help="проверить только схему и значения, не требуя полного совпадения с эталоном",
    )
    args = parser.parse_args()

    path = Path(args.path)
    raw = path.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()

    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, delimiter=";")
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise ValueError(f"Ожидались колонки {EXPECTED_COLUMNS}, получены {reader.fieldnames}")

        keys: set[tuple[int, str, int]] = set()
        prediction_sum = 0
        row_count = 0
        for row in reader:
            route = int(row["route"])
            date = row["date"]
            hour = int(row["hour"])
            prediction = int(row["prediction"])

            if not 0 <= hour <= 23:
                raise ValueError(f"Недопустимый час: {hour}")
            if prediction < 0:
                raise ValueError(f"Отрицательный прогноз: {prediction}")

            key = (route, date, hour)
            if key in keys:
                raise ValueError(f"Дублирующийся ключ: {key}")
            keys.add(key)
            prediction_sum += prediction
            row_count += 1

    if row_count != EXPECTED_ROWS:
        raise ValueError(f"Ожидалось {EXPECTED_ROWS} строк, получено {row_count}")

    if not args.allow_different_hash:
        if prediction_sum != EXPECTED_SUM:
            raise ValueError(f"Ожидалась сумма {EXPECTED_SUM}, получено {prediction_sum}")
        if sha256 != EXPECTED_SHA256:
            raise ValueError(f"SHA-256 не совпадает: {sha256}")

    print(f"OK: rows={row_count}, prediction_sum={prediction_sum}, sha256={sha256}")


if __name__ == "__main__":
    main()
