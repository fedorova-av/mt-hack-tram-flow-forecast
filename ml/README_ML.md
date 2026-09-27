# ML-модель прогноза загрузки трамвайных маршрутов — v3

Эта папка содержит артефакт выбранной модели, полный код обучения и инференса, финальный submission и инструкцию воспроизведения. Её можно загрузить в чистовой GitHub-репозиторий и использовать ссылку на папку в поле «Артефакты ML-модели и код обучения/инференса».

## Выбранное решение

Модель — route-specific regime-aware robust seasonal ensemble:

- прогноз строится отдельно по маршрутам, дням недели и часам;
- используются mean, median, trimmed mean и exponentially weighted mean;
- учитываются режимы `regular`, `summer`, `winter_break`;
- государственные праздники получают воскресный профиль;
- стабильная и консервативная конфигурации смешиваются с отдельными весами по маршрутам;
- поверх базового прогноза применяются заранее заданные календарные и транспортные изменения.

Для финальной загрузки выбран основной `submission.csv` из v3. Его leaderboard-score — `0.89577`.

### Учитывается ли T1

Да. Финальный submission **учитывает T1**:

- начало влияния: `2025-11-12`;
- полный эффект: `2025-11-19`;
- steady factor маршрута 7: `0.90`;
- в первую неделю применяется плавный factor `0.95`.

Вариант `--t1-factor 1.00` означал бы отсутствие дополнительного влияния T1, но это отдельный probe и не выбранный submission.

## Структура

```text
.
├── README_ML.md
├── MODEL_CARD.md
├── requirements.txt
├── data/
│   └── README.md
├── docs/
│   └── EXTERNAL_SOURCES.md
├── models/
│   └── seasonal_route_model.json
├── outputs/
│   └── submission.csv
├── predictions/
│   └── validation_scores.csv
├── reports/
│   ├── experiments.csv
│   └── scoremax_report.md
├── scripts/
│   └── check_submission.py
└── src/
    ├── __init__.py
    ├── features.py
    ├── interventions.py
    ├── load_data.py
    ├── metrics.py
    ├── predict.py
    ├── train.py
    └── validate.py
```

## Требования

- Python 3.10 или новее;
- `numpy>=1.26`;
- `pandas>=2.2`.

CatBoost, LightGBM и PyTorch для выбранной модели не требуются.

## Подготовка данных

Скачайте `dataset.zip` из задания:

https://disk.yandex.ru/d/DiFwlfMOauxjBg

После распаковки разместите три файла так:

```text
work/dataset/
├── labels/
│   ├── labels_day_train.csv
│   └── labels_day_test.csv
└── test_submission.csv
```

Исходный dataset не включён в GitHub-папку. Подробности находятся в `data/README.md`.

## Установка

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Обучение и валидация

Из корня этой папки выполните:

```bash
python src/train.py
```

Команда:

1. восстанавливает полную почасовую сетку, заполняя отсутствующие комбинации нулями;
2. выполняет временной backtest;
3. сохраняет конфигурацию в `models/seasonal_route_model.json`;
4. сохраняет validation scores и OOF-прогнозы в `predictions/`.

## Инференс

Для точного воспроизведения выбранного submission:

```bash
python src/predict.py --t1-factor 0.90 --output outputs/submission_reproduced.csv
```

Модель проверяет:

- наличие ровно 14 640 строк;
- уникальность ключа `route + date + hour`;
- отсутствие NaN;
- отсутствие отрицательных прогнозов.

## Проверка результата

```bash
python scripts/check_submission.py outputs/submission_reproduced.csv
```

Ожидаемые характеристики выбранного файла:

| Проверка | Значение |
|---|---:|
| Строк данных | 14 640 |
| Сумма `prediction` | 12 550 152 |
| SHA-256 | `91db17acbbc18bb8ac845a2c90ddd946a1d6fff74cf4123a51ac6b31f45cc8f8` |

Файл `outputs/submission.csv` уже содержит проверенный результат.

## Что является артефактом модели

`models/seasonal_route_model.json` — паспорт выбранной конфигурации, весов и результатов валидации. Это не бинарный `.pkl` или `.cbm`: модель является детерминированным ансамблем статистических профилей, а рабочая логика находится в `src/features.py` и `src/interventions.py`.

Для инференса нужны исторические labels, потому что профиль рассчитывается по ним при запуске `predict.py`.

## Внешние данные

Ссылки на использованные календарные и транспортные источники приведены в `docs/EXTERNAL_SOURCES.md`. Погода и дорожный трафик исследовались, но не вошли в финальный v3.

## Ограничения

- область прогноза: 10 заданных маршрутов;
- временная гранулярность: маршрут × дата × час;
- модель не прогнозирует пассажиропоток отдельных остановок;
- финальный горизонт: `2025-11-01` — `2025-12-31`;
- перенос на другие периоды требует обновить календарь, транспортные события и входную прогнозную сетку;
- коэффициенты событий уже включены в `outputs/submission.csv` и не должны применяться повторно.

## Ссылка для формы

После загрузки этой папки в GitHub укажите прямую ссылку на неё. Ссылка должна открываться без авторизации и показывать `README_ML.md`, `models/`, `src/` и `outputs/submission.csv`.
