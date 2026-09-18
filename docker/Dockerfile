FROM ros:humble-ros-base-jammy

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV DEBIAN_FRONTEND=noninteractive \
    ROS_DISTRO=humble \
    ROS_DOMAIN_ID=42 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-numpy \
        python3-pip \
        ros-humble-ros2bag \
        ros-humble-rosbag2-storage-default-plugins \
        ros-humble-sensor-msgs \
        ros-humble-visualization-msgs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY docker/ros_entrypoint.sh /ros_entrypoint_project.sh
RUN chmod +x /ros_entrypoint_project.sh

ENTRYPOINT ["/ros_entrypoint_project.sh"]
CMD ["bash"]
