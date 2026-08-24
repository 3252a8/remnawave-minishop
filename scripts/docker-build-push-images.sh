#!/usr/bin/env bash
set -euo pipefail

IMAGE_REGISTRIES="${IMAGE_REGISTRIES:-ghcr.io docker.io}"
IMAGE_NAMESPACE="${IMAGE_NAMESPACE:-3252a8}"
IMAGE_TAG="${IMAGE_TAG:?Set IMAGE_TAG to the release tag you want to build and push}"
IMAGE_PREFIX="${IMAGE_PREFIX:-remnawave-minishop}"
DOCKERFILE="${DOCKERFILE:-deploy/docker/Dockerfile}"
TARGETS="${TARGETS:-backend worker frontend}"
REMNAWAVE_MINISHOP_BUILD_PROVENANCE="${REMNAWAVE_MINISHOP_BUILD_PROVENANCE:-custom}"

normalize_list() {
  local value="$1"
  value="${value//,/ }"
  value="${value//;/ }"
  echo "$value"
}

read -r -a registries <<< "$(normalize_list "$IMAGE_REGISTRIES")"
read -r -a targets <<< "$(normalize_list "$TARGETS")"

image_name() {
  local registry="$1"
  local target="$2"
  echo "$registry/$IMAGE_NAMESPACE/$IMAGE_PREFIX-$target:$IMAGE_TAG"
}

build_image() {
  local target="$1"
  local tags=()
  local registry

  for registry in "${registries[@]}"; do
    tags+=("-t" "$(image_name "$registry" "$target")")
  done

  echo "Building $target for: ${registries[*]}"
  docker build \
    -f "$DOCKERFILE" \
    --target "$target" \
    --build-arg "REMNAWAVE_MINISHOP_BUILD_PROVENANCE=$REMNAWAVE_MINISHOP_BUILD_PROVENANCE" \
    "${tags[@]}" \
    .
}

push_image() {
  local target="$1"
  local registry
  local image

  for registry in "${registries[@]}"; do
    image="$(image_name "$registry" "$target")"
    echo "Pushing $image"
    docker push "$image"
  done
}

for target in "${targets[@]}"; do
  build_image "$target"
done

for target in "${targets[@]}"; do
  push_image "$target"
done
