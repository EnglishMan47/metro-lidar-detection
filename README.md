# ЛЦТ 2026 — задача №5

Система обнаружения посторонних объектов для беспилотных поездов в тоннеле метро по данным 3D-лидара.

Рабочий план и ежедневная нагрузка: [PROJECT_PLAN.md](PROJECT_PLAN.md). Подтверждённые требования: [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md). Аудит данных: [docs/DATA_REPORT.md](docs/DATA_REPORT.md). Конспект Q&A: [docs/QNA_NOTES.md](docs/QNA_NOTES.md). Инструкция GitHub: [docs/GITHUB_SYNC.md](docs/GITHUB_SYNC.md). Текущее состояние: [docs/STATUS.md](docs/STATUS.md).

План версии 0.3 основан на истории Telegram, локальном ТЗ, полной записи Q&A и файловом аудите датасета по состоянию на 17 сентября 2026 года. Оценка — 106 командо-часов всего, из них 4 уже закрыты разбором требований; расчётный остаток — 102 часа. Подтверждены 6 ROS 2 bag, обязательные Ubuntu 22.04/ROS 2 Humble/Docker и скрытая финальная проверка. Проект пока не содержит реализованного детектора.

## Инструменты данных

Инвентаризация файлов — Python 3.11+, без сторонних зависимостей:

```powershell
python scripts/audit_dataset.py --input "ПУТЬ_К_ДАТАСЕТУ" --output artifacts/data_audit.json
```

Инструмент рекурсивно инвентаризирует обычные файлы, считает размеры и SHA-256, показывает распределение по расширениям, дубликаты и ошибки чтения. Он не распаковывает архивы, не интерпретирует координаты и не считает метрики детекции. Символические ссылки и Windows junction пропускаются.

Проверка реальных `PointCloud2` напрямую из SQLite3 bag требует NumPy:

```powershell
python scripts/inspect_pointcloud_bag.py data/extracted/for_hackathon --frames 3 --output artifacts/pointcloud_inspection.json
python scripts/render_pointcloud_frame.py data/extracted/for_hackathon/doubleT_obstacle/doubleT_obstacle_0.db3 --index 100 --output artifacts/frame.png --lateral -3 3 --forward 0 90 --height -2 2.5
```

Первый скрипт проверяет CDR, поля, размеры и диапазоны координат; второй строит три диагностические проекции в PNG без ROS и графических библиотек. Для финальной проверки всё равно требуется ROS 2 Humble/RViz2.

Исходные материалы помещать в `data/raw/`, результаты — в `artifacts/`. Приватная переписка хранится в `private/`; эти каталоги исключены из Git. Пароль материалов находится в сообщении организатора от 15.09, а не в исходном коде.
