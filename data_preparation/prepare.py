"""Подготовка данных инженера 1. Зависимости: pandas, numpy, openpyxl."""
from pathlib import Path
import time
import numpy as np
import pandas as pd

KEY = ['route', 'date', 'hour']
ROUTES = [1, 5, 7, 11, 12, 17, 25, 26, 28, 50]
PERIODS = {'train': ('2025-01-01', '2025-08-31'),
           'valid': ('2025-09-01', '2025-10-31')}


def read_labels(root, split):
    suffix = {'train': 'train', 'valid': 'test'}[split]
    df = pd.read_csv(Path(root) / 'labels' / f'labels_day_{suffix}.csv', sep=';')
    assert list(df.columns) == KEY + ['boardings'], 'Изменилась схема labels'
    assert not df.isna().any().any(), 'Пропуски внутри исходных строк'
    df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d', errors='raise')
    for col in ['route', 'hour', 'boardings']:
        values = pd.to_numeric(df[col], errors='raise')
        assert np.isfinite(values).all() and (values % 1 == 0).all(), col
        df[col] = values.astype('int64')
    assert df.route.isin(ROUTES).all()
    assert df.hour.between(0, 23).all() and df.boardings.ge(0).all()
    assert not df.duplicated(KEY).any(), 'Дубли ключа: не суммируем молча'
    start, end = PERIODS[split]
    assert df.date.between(start, end).all(), 'Дата вне договорённого периода'
    return df.sort_values(KEY).reset_index(drop=True)


def load_grid(root, split='train', policy='preserve'):
    """policy: preserve — NaN; zero — все пропуски 0;
    exclude_anomaly — пропуски 0, но route 50 / 2025-09-21 оставлен NaN.
    Ключи не удаляются. Для обучения фильтруйте target_available.
    Правило zero — предварительная договорённость, а не доказательство нулевого движения.
    """
    if policy not in {'preserve', 'zero', 'exclude_anomaly'}:
        raise ValueError(policy)
    labels = read_labels(root, split)
    start, end = PERIODS[split]
    idx = pd.MultiIndex.from_product([ROUTES, pd.date_range(start, end), range(24)], names=KEY)
    df = idx.to_frame(index=False).merge(labels, on=KEY, how='left', validate='one_to_one', indicator=True)
    df['observed_row'] = df.pop('_merge').eq('both')
    df['boardings_raw'] = df.boardings.copy()
    day_count = df.groupby(['route', 'date']).observed_row.transform('sum')
    route_count = df.groupby('route').observed_row.transform('sum')
    missing = ~df.observed_row
    df['missing_kind'] = 'observed'
    df.loc[missing, 'missing_kind'] = 'missing_hour'
    # Это кандидаты на ночные нули, не подтверждённые нули и не расписание.
    df.loc[missing & df.hour.between(0, 4), 'missing_kind'] = 'night_candidate'
    df.loc[day_count.eq(0), 'missing_kind'] = 'whole_day_missing'
    df.loc[route_count.eq(0), 'missing_kind'] = 'route_absent'
    df['known_anomaly'] = df.route.eq(50) & df.date.eq(pd.Timestamp('2025-09-21'))
    if policy != 'preserve':
        df['boardings'] = df.boardings.fillna(0)
    if policy == 'exclude_anomaly':
        df.loc[df.known_anomaly, 'boardings'] = np.nan
    df['target_available'] = df.boardings.notna()
    df['split'] = split
    df['fill_policy'] = policy
    assert len(df) == len(idx) and not df.duplicated(KEY).any()
    assert df.loc[df.observed_row, 'boardings_raw'].sum() == labels.boardings.sum()
    return df


def quality_summary(root):
    rows = []
    for split in PERIODS:
        g = load_grid(root, split)
        rows.append(dict(split=split, source_rows=int(g.observed_row.sum()), grid_rows=len(g),
                         missing_rows=int((~g.observed_row).sum()),
                         total_boardings=int(g.boardings_raw.sum())))
    return pd.DataFrame(rows)


def profile_predict(train, future):
    """Диагностический профиль; не замена модели инженера 2."""
    tr = train.loc[train.target_available].copy()
    tr['dow'] = tr.date.dt.dayofweek
    keys = ['route', 'dow', 'hour']
    profile = tr.groupby(keys).boardings.mean().rename('prediction').reset_index()
    f = future[KEY].copy()
    f['dow'] = f.date.dt.dayofweek
    f = f.merge(profile, on=keys, how='left', validate='many_to_one')
    assert f.prediction.notna().all(), 'Не хватает профиля: нужен явный fallback'
    return f[KEY + ['prediction']]


def diagnostic_wape(truth, pred):
    """Для чувствительности. Итоговую метрику команды утверждает инженер 3."""
    assert not truth.duplicated(KEY).any() and not pred.duplicated(KEY).any()
    joined = truth.merge(pred, on=KEY, how='outer', validate='one_to_one', indicator=True)
    assert joined['_merge'].eq('both').all(), 'Наборы ключей не совпали'
    assert np.isfinite(joined.prediction).all() and joined.prediction.ge(0).all()
    selected = joined.loc[joined.target_available]
    total = selected.boardings.sum()
    assert total > 0
    return float((selected.boardings - selected.prediction).abs().sum() / total)


def sensitivity(root):
    # На сентябре-октябре аномалия в оценке, а не в обучении.
    train = load_grid(root, 'train', 'zero')
    valid = load_grid(root, 'valid', 'zero')
    pred = profile_predict(train, valid)
    rows = []
    for policy in ['zero', 'exclude_anomaly']:
        truth = load_grid(root, 'valid', policy)
        rows.append(dict(experiment='Jan-Aug -> Sep-Oct', policy=policy,
                         evaluated_rows=int(truth.target_available.sum()),
                         wape=diagnostic_wape(truth, pred)))
    # Чтобы проверить именно влияние на ОБУЧЕНИЕ, день должен попасть в историю.
    # Общий октябрьский holdout: январь-сентябрь -> октябрь.
    future = valid.loc[valid.date.ge('2025-10-01')].copy()
    for policy in ['zero', 'exclude_anomaly']:
        sep = load_grid(root, 'valid', policy)
        history = pd.concat([train, sep.loc[sep.date.lt('2025-10-01')]], ignore_index=True)
        forecast = profile_predict(history, future)
        rows.append(dict(experiment='Jan-Sep -> Oct', policy=policy,
                         evaluated_rows=len(future), wape=diagnostic_wape(future, forecast)))
    result = pd.DataFrame(rows)
    result['score'] = (1 - result.wape).clip(lower=0)
    return result


def load_geography(root):
    files = list((Path(root) / 'spravochniki').glob('*10*маршрутов.xlsx'))
    assert len(files) == 1, files
    path = files[0]
    stops = pd.read_excel(path, sheet_name='Остановки GTFS_STOPS', header=1)
    order = pd.read_excel(path, sheet_name='Порядок_с_координатами')
    routes = pd.read_excel(path, sheet_name='Маршруты GTFS_ROUTES', header=1)
    assert stops.stop_id.notna().all() and not stops.stop_id.duplicated().any(), 'Проверить дубли stop_id'
    order = order.rename(columns={'route_short_name': 'route'})
    order = order.loc[order.route.isin(ROUTES)].copy()
    assert set(order.route) == {1, 5, 7, 11, 12}
    assert not order.duplicated(['route_id', 'trip_id', 'stop_sequence']).any()
    geo = order.merge(stops[['stop_id', 'is_deleted']], on='stop_id', how='left', validate='many_to_one')
    for col in ['stop_lat', 'stop_lon']:
        geo[col] = pd.to_numeric(geo[col], errors='coerce')
    geo['valid_coords'] = geo.stop_lat.between(-90, 90) & geo.stop_lon.between(-180, 180)
    geo['map_eligible'] = geo.valid_coords & geo.is_deleted.eq(0)
    # Не соединяем различные trip_id/направления в единую линию.
    geo = geo.sort_values(['route', 'trip_id', 'direction_id', 'stop_sequence'])
    coverage = pd.DataFrame({'route': ROUTES})
    coverage['has_reference'] = coverage.route.isin(geo.route.unique())
    coverage['has_map_points'] = coverage.route.isin(geo.loc[geo.map_eligible, 'route'].unique())
    routes = routes.rename(columns={'route_short_name': 'route'})
    routes = routes.loc[routes.route.isin(ROUTES)].copy()
    return geo, coverage, routes


def raw_check(root, split='valid', max_chunks=2, chunksize=100_000):
    """Ограниченный просмотр — только нижняя граница, НЕ сверка полных агрегатов.
    max_chunks=None читает весь файл и позволяет точную сверку выбранных дат.
    Читаются только 3 нужные колонки. Порядок raw не предполагается.
    """
    start_time = time.perf_counter()
    suffix = {'train': 'train', 'valid': 'test'}[split]
    dates = (['2025-01-01', '2025-08-31'] if split == 'train'
             else ['2025-09-20', '2025-09-21', '2025-09-22'])
    cols = ['tran_date_time', 'ngpt_route', 'validation_result']
    counts = None
    n = bad = route5 = 0
    with pd.read_csv(Path(root) / f'{suffix}.csv', sep=';', usecols=cols,
                     chunksize=chunksize) as reader:
        import itertools
        chunks = reader if max_chunks is None else itertools.islice(reader, max_chunks)
        for chunk in chunks:
            n += len(chunk)
            ts = pd.to_datetime(chunk.tran_date_time, errors='coerce')
            route = pd.to_numeric(chunk.ngpt_route.astype('string').str.extract(r'^\s*(\d+)\s+трамвай\s*$', expand=False), errors='coerce')
            success = pd.to_numeric(chunk.validation_result, errors='coerce').eq(1)
            bad += int((success & (ts.isna() | route.isna())).sum())
            route5 += int((success & route.eq(5)).sum())
            frame = pd.DataFrame({'route': route, 'date': ts.dt.normalize(), 'hour': ts.dt.hour})
            mask = success & frame.date.isin(pd.to_datetime(dates)) & frame.route.isin(ROUTES)
            part = frame.loc[mask].groupby(KEY).size()
            counts = part if counts is None else counts.add(part, fill_value=0)
    full_scan = max_chunks is None
    reference = load_grid(root, split, 'zero')
    reference = reference.loc[reference.date.isin(pd.to_datetime(dates)), KEY + ['boardings']]
    if counts is None or counts.empty:
        raw = pd.DataFrame(columns=KEY + ['raw_count'])
        comparison = reference.copy()
        comparison['raw_count'] = 0
    else:
        raw = counts.rename('raw_count').reset_index()
        comparison = reference.merge(raw, on=KEY, how='left', validate='one_to_one')
        comparison['raw_count'] = comparison.raw_count.fillna(0)
    comparison['raw_minus_labels'] = comparison.raw_count - comparison.boardings
    comparison['complete_scan'] = full_scan
    stats = {'rows_read': n, 'full_scan': full_scan, 'bad_success_rows': bad,
             'route5_success_seen': route5, 'seconds': round(time.perf_counter()-start_time, 2)}
    # При полном проходе расхождение — повод расследовать; автоматически не исправляем.
    return comparison, stats


def export_all(root, output_dir):
    root = Path(root)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for split in PERIODS:
        for policy in ['preserve', 'zero', 'exclude_anomaly']:
            load_grid(root, split, policy).to_csv(out / f'{split}_{policy}.csv', sep=';', index=False, date_format='%Y-%m-%d')
    geo, coverage, routes = load_geography(root)
    exports = {'quality_summary': quality_summary(root), 'sensitivity': sensitivity(root),
               'route_stops_audit': geo, 'route_stops_map': geo.loc[geo.map_eligible],
               'map_coverage': coverage, 'routes': routes}
    full = pd.concat([load_grid(root, s) for s in PERIODS], ignore_index=True)
    exports['missing_by_route_hour'] = full.groupby(['split', 'route', 'hour']).observed_row.agg(['size', 'sum']).reset_index().rename(columns={'size': 'grid_rows', 'sum': 'observed_rows'})
    exports['missing_days'] = full.groupby(['split', 'route', 'date']).observed_row.sum().rename('observed_hours').reset_index().query('observed_hours == 0')
    for name, frame in exports.items():
        frame.to_csv(out / f'{name}.csv', sep=';', index=False, date_format='%Y-%m-%d')
    return out, exports


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Аудит labels, пропусков и географии")
    parser.add_argument('--dataset', type=Path, required=True, help="Папка распакованного dataset")
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'output')
    args = parser.parse_args()
    output, tables = export_all(args.dataset, args.output)
    print(tables['quality_summary'].to_string(index=False))
    print(tables['sensitivity'].to_string(index=False))
    print('Saved:', output)
