# Среда разработки и запуска

Целевая среда соответствует техническому заданию:

- Linux-контейнер: Ubuntu 22.04;
- ROS 2 Humble;
- Docker Desktop с WSL2 backend;
- вход: ROS 2 bag с `sensor_msgs/msg/PointCloud2`;
- датасет подключается в контейнер как `/datasets` только для чтения.

Ubuntu 24.04 может использоваться как пользовательский WSL-хост, но код собирается и проверяется внутри контейнера Ubuntu 22.04. Это исключает зависимость от ROS 2 Jazzy и библиотек Ubuntu 24.04.

## Автоматическая проверка

В PowerShell из корня проекта:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_environment.ps1
```

Скрипт:

1. проверяет доступность Docker Linux engine;
2. собирает образ `lct26-lidar:humble`;
3. проверяет Ubuntu 22.04 и ROS 2 Humble;
4. проверяет пакеты `ros2bag` и `sensor_msgs`;
5. выполняет `ros2 bag info` на реальном `doubleT_obstacle`;
6. подтверждает доступность NumPy;
7. воспроизводит реальный bag и получает один заголовок `PointCloud2` через ROS 2 topic.

Smoke-тест pub/sub использует `roundT_doubleT` с кадрами около 8 МБ. Положительный `doubleT_obstacle` содержит кадры около 24 МБ; его SQLite-файл на Windows bind mount читается Docker заметно медленнее. Для длительных прогонов и измерения производительности датасет следует скопировать в файловую систему WSL2 или Docker volume, иначе измеряется накладная стоимость NTFS-монтирования.

## Интерактивный контейнер

```powershell
docker compose run --rm lidar-dev
```

Внутри контейнера:

```bash
echo "$ROS_DISTRO"
ros2 bag info /datasets/doubleT_obstacle
ros2 bag play /datasets/doubleT_obstacle
```

Entrypoint автоматически подключает `/opt/ros/humble/setup.bash`. Если в `/workspace/install/setup.bash` появится собранный colcon workspace, он также подключится автоматически.

## Архитектура WSL

Фактически проверяемая цепочка:

```text
Windows → Docker Desktop → WSL2 Linux engine → Ubuntu 22.04 container → ROS 2 Humble
```

Отдельный пользовательский дистрибутив Ubuntu 24.04 для выполнения контейнера не обязателен. Если он установлен, проект можно запускать теми же командами Docker из его терминала, открыв каталог Windows через `/mnt/c/Users/Lev Kalitikov/Desktop/hacatone`.

## Ограничение визуализации

Текущий базовый образ не включает RViz2: графический интерфейс увеличивает образ и требует отдельной настройки WSLg/X11. На этапе алгоритма используются локальные PNG-проекции. RViz2 будет добавлен отдельным профилем после появления ROS node и marker topic, чтобы графическая часть не мешала воспроизводимой пакетной проверке.
