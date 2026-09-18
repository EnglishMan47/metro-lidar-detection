#!/usr/bin/env bash
set -euo pipefail

topic="/lidar_points"
bag="/datasets/roundT_doubleT"

ros2 bag play "${bag}" \
  --topics "${topic}" \
  --read-ahead-queue-size 10 \
  --delay 2 \
  --disable-keyboard-controls \
  >/tmp/rosbag_play.log 2>&1 &
player_pid=$!

cleanup() {
  kill "${player_pid}" 2>/dev/null || true
  wait "${player_pid}" 2>/dev/null || true
}
trap cleanup EXIT

if ! timeout 45 ros2 topic echo "${topic}" sensor_msgs/msg/PointCloud2 \
  --once \
  --field header \
  --no-daemon \
  --spin-time 2 \
  --qos-profile sensor_data \
  --no-lost-messages \
  >/tmp/pointcloud_header.txt 2>/tmp/topic_echo.log; then
  echo "--- ros2 bag play log ---" >&2
  cat /tmp/rosbag_play.log >&2 || true
  echo "--- ros2 topic echo log ---" >&2
  cat /tmp/topic_echo.log >&2 || true
  exit 1
fi

grep -q 'frame_id: hesai_lidar' /tmp/pointcloud_header.txt
cat /tmp/pointcloud_header.txt
echo "ROS 2 PointCloud2 playback: OK"
