#!/usr/bin/env bash
set -euo pipefail

grep -q '^VERSION_ID="22.04"' /etc/os-release
test "${ROS_DISTRO}" = "humble"
ros2 pkg prefix ros2bag >/dev/null
ros2 pkg prefix sensor_msgs >/dev/null
ros2 bag info /datasets/doubleT_obstacle >/tmp/bag_info.txt
grep -q 'sensor_msgs/msg/PointCloud2' /tmp/bag_info.txt
python3 -c 'import numpy; print("NumPy", numpy.__version__)'

echo "Ubuntu 22.04: OK"
echo "ROS 2 Humble: OK"
echo "SQLite3 ROS bag: OK"

