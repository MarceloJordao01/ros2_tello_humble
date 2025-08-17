#!/bin/bash

# Store the current directory
ROOT_DIR=$(pwd)

# Allow local connections to the X server for GUI applications in Docker
xhost +local:docker

# Setup for X11 forwarding to enable GUI
XAUTH=/tmp/.docker.xauth
touch $XAUTH
xauth nlist $DISPLAY | sed -e 's/^..../ffff/' | xauth -f $XAUTH nmerge -

IMAGE_NAME=tello_ros2_humble


# Run the Docker container with the selected image and configurations for GUI applications
docker run -it \
  --rm \
  --name px4_container \
  --privileged \
  --user=root \
  --network=host \
  --env="DISPLAY=$DISPLAY" \
  --env WAYLAND_DISPLAY=$WAYLAND_DISPLAY \
  --env XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR \
  --env PULSE_SERVER=$PULSE_SERVER \
  --env NVIDIA_VISIBLE_DEVICES=all \
  --env NVIDIA_DRIVER_CAPABILITIES=all \
  --env="QT_X11_NO_MITSHM=1" \
  --volume="/tmp/.X11-unix:/tmp/.X11-unix:rw" \
  --env="XAUTHORITY=$XAUTH" \
  --volume="$XAUTH:$XAUTH" \
  --runtime nvidia \
  --gpus all \
  --volume="/dev:/dev" \
  $IMAGE_NAME