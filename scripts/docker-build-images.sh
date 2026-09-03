#!/usr/bin/env bash
set -euo pipefail

IMAGE_REGISTRY="${IMAGE_REGISTRY:-docker.io}"
IMAGE_NAMESPACE="${IMAGE_NAMESPACE:-3252a8}"
IMAGE_TAG="${IMAGE_TAG:-local}"
IMAGE_PREFIX="${IMAGE_PREFIX:-remnawave-minishop}"
DOCKERFILE="${DOCKERFILE:-deploy/docker/Dockerfile}"
REMNAWAVE_MINISHOP_BUILD_PROVENANCE="${REMNAWAVE_MINISHOP_BUILD_PROVENANCE:-custom}"
REMNAWAVE_MINISHOP_BRANCH="${REMNAWAVE_MINISHOP_BRANCH:-}"
REMNAWAVE_MINISHOP_BUILD_TAG="${REMNAWAVE_MINISHOP_BUILD_TAG:-}"
REMNAWAVE_MINISHOP_BUILD_COMMIT="${REMNAWAVE_MINISHOP_BUILD_COMMIT:-}"
OCI_IMAGE_REVISION="${OCI_IMAGE_REVISION:-}"

build_image() {
  local target="$1"
  local image="$IMAGE_REGISTRY/$IMAGE_NAMESPACE/$IMAGE_PREFIX-$target:$IMAGE_TAG"
  local labels=()
  if [ -n "$OCI_IMAGE_REVISION" ]; then
    labels+=("--label" "org.opencontainers.image.revision=$OCI_IMAGE_REVISION")
  fi
  echo "Building $image"
  docker build \
    -f "$DOCKERFILE" \
    --target "$target" \
    --build-arg "REMNAWAVE_MINISHOP_BRANCH=$REMNAWAVE_MINISHOP_BRANCH" \
    --build-arg "REMNAWAVE_MINISHOP_BUILD_PROVENANCE=$REMNAWAVE_MINISHOP_BUILD_PROVENANCE" \
    --build-arg "REMNAWAVE_MINISHOP_BUILD_TAG=$REMNAWAVE_MINISHOP_BUILD_TAG" \
    --build-arg "REMNAWAVE_MINISHOP_BUILD_COMMIT=$REMNAWAVE_MINISHOP_BUILD_COMMIT" \
    "${labels[@]}" \
    -t "$image" \
    .
}

build_image backend
build_image worker
build_image frontend
