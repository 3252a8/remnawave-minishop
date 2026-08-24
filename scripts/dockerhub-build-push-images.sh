#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

IMAGE_REGISTRY="docker.io"
IMAGE_NAMESPACE="3252a8"
IMAGE_TAG="${IMAGE_TAG:?Set IMAGE_TAG to the release tag you want to build and push}"
export IMAGE_REGISTRY IMAGE_NAMESPACE IMAGE_TAG

bash "$SCRIPT_DIR/docker-build-images.sh"
bash "$SCRIPT_DIR/docker-push-images.sh"
