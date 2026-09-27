# Входные данные

Исходный датасет не дублируется в репозитории. Ссылка на архив из задания:

https://disk.yandex.ru/d/DiFwlfMOauxjBg

После распаковки нужны три файла со следующей структурой:

```text
work/dataset/
├── labels/
│   ├── labels_day_train.csv
│   └── labels_day_test.csv
└── test_submission.csv
```

## Схема файлов

`labels_day_train.csv` и `labels_day_test.csv`:

```text
route;date;hour;boardings
```

`test_submission.csv`:

```text
route;date;hour;prediction
```

Разделитель — точка с запятой. Даты читаются `pandas` как календарные даты, часы должны быть целыми от 0 до 23. Исторические наблюдения после `2025-10-31` в обучение финального решения не попадают.

`labels_day_test.csv` — часть доступной истории, а не прогнозный target. Файл `test_submission.csv` задаёт строки и порядок итогового прогноза.
