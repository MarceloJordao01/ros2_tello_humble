#!/bin/bash
set -euo pipefail

# =========================
# CONFIG BÁSICA / CONTEXTO
# =========================

# Diretório do repositório (pasta onde este script está)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Diretórios relevantes no host
MODULES_DIR="${PROJECT_ROOT}/modules"

# Nome da imagem já construída
IMAGE_NAME="tello_ros2_humble"

# Nome do container (só para facilitar identificar)
CONTAINER_NAME="px4_container"

# Workspace dentro do container (deve casar com o Dockerfile)
WS_IN_CONTAINER="/tello_ros_ws"

# =========================
# PREP X11 / ÁUDIO / NVIDIA
# =========================

# Permitir conexões locais ao X para apps GUI no Docker
if command -v xhost >/dev/null 2>&1; then
  xhost +local:docker || true
fi

# Setup para X11 forwarding
XAUTH="/tmp/.docker.xauth"
touch "$XAUTH"
if command -v xauth >/dev/null 2>&1; then
  xauth nlist "$DISPLAY" | sed -e 's/^..../ffff/' | xauth -f "$XAUTH" nmerge - || true
fi

# =========================
# COLETA DE VOLUMES
# =========================

VOLUMES=()

# 1) Montar todos os pacotes ROS (pastas em modules/* que contenham package.xml)
VOLUMES+=("-v" "${PWD}/modules/:${WS_IN_CONTAINER}/src")

# 3) X11 socket e XAUTH (GUI)
VOLUMES+=("-v" "/tmp/.X11-unix:/tmp/.X11-unix:rw")
VOLUMES+=("-v" "${XAUTH}:${XAUTH}:rw")

# 4) Dispositivos do host (para simulação/sensores, se necessário)
VOLUMES+=("-v" "/dev:/dev")

# =========================
# LOG DOS VOLUMES MAPEADOS
# =========================
echo "==> Volumes que serão montados:"
for v in "${VOLUMES[@]}"; do
  echo "   ${v}"
done
echo

# =========================
# EXECUÇÃO DO CONTAINER
# =========================

docker run -it --rm \
  --name "${CONTAINER_NAME}" \
  --privileged \
  --user=root \
  --network=host \
  --gpus all \
  --runtime nvidia \
  --env "DISPLAY=${DISPLAY:-}" \
  --env "WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-}" \
  --env "XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-}" \
  --env "PULSE_SERVER=${PULSE_SERVER:-}" \
  --env "QT_X11_NO_MITSHM=1" \
  --env "XAUTHORITY=${XAUTH}" \
  "${VOLUMES[@]}" \
  "${IMAGE_NAME}"
