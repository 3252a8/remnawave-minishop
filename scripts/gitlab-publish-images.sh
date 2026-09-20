#!/usr/bin/env bash
set -euo pipefail

PUBLISH_CHANNEL="${PUBLISH_CHANNEL:?Set PUBLISH_CHANNEL to dev or release}"
DOCKERHUB_USERNAME="${DOCKERHUB_USERNAME:?Set DOCKERHUB_USERNAME}"
DOCKERHUB_TOKEN="${DOCKERHUB_TOKEN:?Set DOCKERHUB_TOKEN}"
SIGSTORE_ID_TOKEN="${SIGSTORE_ID_TOKEN:?GitLab must provide SIGSTORE_ID_TOKEN}"
CI_COMMIT_SHA="${CI_COMMIT_SHA:?GitLab must provide CI_COMMIT_SHA}"
CI_COMMIT_REF_NAME="${CI_COMMIT_REF_NAME:?GitLab must provide CI_COMMIT_REF_NAME}"
CI_JOB_ID="${CI_JOB_ID:?GitLab must provide CI_JOB_ID}"
CI_PIPELINE_ID="${CI_PIPELINE_ID:?GitLab must provide CI_PIPELINE_ID}"
CI_PROJECT_PATH="${CI_PROJECT_PATH:?GitLab must provide CI_PROJECT_PATH}"
CI_PROJECT_URL="${CI_PROJECT_URL:?GitLab must provide CI_PROJECT_URL}"
CI_SERVER_URL="${CI_SERVER_URL:?GitLab must provide CI_SERVER_URL}"

IMAGE_PREFIX="${IMAGE_PREFIX:-remnawave-minishop}"
TARGETS="${TARGETS:-backend worker frontend}"
TRIVY_IMAGE="${TRIVY_IMAGE:-aquasec/trivy:0.70.0}"
# OCI_IMAGE_SOURCE="${OCI_IMAGE_SOURCE:-https://github.com/3252a8/remnawave-minishop}"
OCI_IMAGE_SOURCE="${OCI_IMAGE_SOURCE:-https://gitlab.com/3252a8/remnawave-minishop}"
dockerhub_owner="$(printf '%s' "$DOCKERHUB_USERNAME" | tr '[:upper:]' '[:lower:]')"
context_name="minishop-context-$CI_JOB_ID"
builder_name="minishop-$CI_JOB_ID"
metadata_dir="${CI_PROJECT_DIR:-$PWD}/.publish-metadata-$CI_JOB_ID"
export TRIVY_USERNAME="$DOCKERHUB_USERNAME"
export TRIVY_PASSWORD="$DOCKERHUB_TOKEN"

cleanup() {
  docker buildx rm "$builder_name" >/dev/null 2>&1 || true
  unset DOCKER_CONTEXT
  docker context rm --force "$context_name" >/dev/null 2>&1 || true
}

trap cleanup EXIT

registry_digest() {
  local reference="$1"
  local manifest

  if ! manifest="$(docker buildx imagetools inspect "$reference" --format '{{json .Manifest}}' 2>/dev/null)"; then
    return 1
  fi
  jq -er '.digest' <<< "$manifest"
}

wait_for_registry_digest() {
  local reference="$1"
  local expected_digest="$2"
  local actual_digest=""
  local attempt
  local sleep_seconds

  for attempt in 1 2 3 4 5 6; do
    actual_digest="$(registry_digest "$reference" || true)"
    if [ "$actual_digest" = "$expected_digest" ]; then
      return 0
    fi
    if [ "$attempt" -lt 6 ]; then
      sleep_seconds=$((attempt * 2))
      echo "Digest for $reference is not visible yet; retrying in ${sleep_seconds}s."
      sleep "$sleep_seconds"
    fi
  done

  echo "Digest verification failed for $reference (expected $expected_digest, got ${actual_digest:-none})" >&2
  return 1
}

verify_remote_head() {
  local branch="$1"
  local remote_commit

  remote_commit="$(git ls-remote origin "refs/heads/$branch" | awk '{print $1}')"
  if [ -z "$remote_commit" ]; then
    echo "Unable to resolve current $branch" >&2
    exit 1
  fi
  if [ "$CI_COMMIT_SHA" != "$remote_commit" ]; then
    if [ "$PUBLISH_CHANNEL" = "dev" ]; then
      echo "Skipping superseded dev commit $CI_COMMIT_SHA (current: $remote_commit)"
      exit 0
    fi
    echo "Release tag ${CI_COMMIT_TAG:-unknown} must point exactly at current $branch ($remote_commit)" >&2
    exit 1
  fi
}

promote_tag() {
  local image="$1"
  local digest="$2"
  local tag="$3"
  local destination="$image:$tag"

  docker buildx imagetools create --tag "$destination" "$image@$digest"
  wait_for_registry_digest "$destination" "$digest"
}

verify_signature() {
  local reference="$1"
  local expected_tag="$2"
  local attempt
  local sleep_seconds

  for attempt in 1 2 3 4 5 6; do
    if cosign verify \
      --experimental-oci11 \
      --annotations "tag=$expected_tag" \
      --annotations "org.opencontainers.image.revision=$CI_COMMIT_SHA" \
      --certificate-identity "$certificate_identity" \
      --certificate-oidc-issuer "$CI_SERVER_URL" \
      "$reference" | jq -e 'length > 0' > /dev/null; then
      return 0
    fi
    if [ "$attempt" -lt 6 ]; then
      sleep_seconds=$((attempt * 2))
      echo "Signature for $reference is not visible yet; retrying in ${sleep_seconds}s."
      sleep "$sleep_seconds"
    fi
  done

  echo "Unable to verify the signature for $reference" >&2
  return 1
}

case "$PUBLISH_CHANNEL" in
  dev)
    publish_tag=dev
    build_branch="$CI_COMMIT_REF_NAME"
    release_tag=""
    release_version=""
    certificate_ref="refs/heads/$CI_COMMIT_REF_NAME"
    verify_remote_head dev
    ;;
  release)
    release_tag="${CI_COMMIT_TAG:?Release publishing requires CI_COMMIT_TAG}"
    if ! [[ "$release_tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      echo "Release tag must use the stable vX.Y.Z form: $release_tag" >&2
      exit 1
    fi
    release_version="${release_tag#v}"
    publish_tag="$release_version"
    build_branch=main
    certificate_ref="refs/tags/$release_tag"
    verify_remote_head main
    ;;
  *)
    echo "Unsupported PUBLISH_CHANNEL: $PUBLISH_CHANNEL" >&2
    exit 1
    ;;
esac

certificate_identity="$CI_PROJECT_URL//.gitlab-ci.yml@$certificate_ref"
build_provenance=custom
if [ "$CI_PROJECT_PATH" = "3252a8/remnawave-minishop" ]; then
  build_provenance=official
fi

mkdir -p "$metadata_dir"

docker_host="${DOCKER_HOST:?GitLab DinD must provide DOCKER_HOST}"
docker_cert_path="${DOCKER_CERT_PATH:?GitLab DinD must provide DOCKER_CERT_PATH}"
docker context create "$context_name" \
  --docker "host=$docker_host,ca=$docker_cert_path/ca.pem,cert=$docker_cert_path/cert.pem,key=$docker_cert_path/key.pem" \
  >/dev/null
unset DOCKER_HOST DOCKER_TLS_VERIFY DOCKER_CERT_PATH DOCKER_TLS_CERTDIR
export DOCKER_CONTEXT="$context_name"
docker buildx create \
  --driver docker-container \
  --name "$builder_name" \
  --use \
  "$context_name" \
  >/dev/null
docker buildx inspect --bootstrap

for target in $TARGETS; do
  image="docker.io/$dockerhub_owner/$IMAGE_PREFIX-$target"
  candidate_tag="candidate-$CI_COMMIT_SHA-$CI_PIPELINE_ID-$CI_JOB_ID"
  build_metadata="$metadata_dir/$target-build.json"
  candidate_metadata="$metadata_dir/$target.json"
  build_args=(
    --build-arg "REMNAWAVE_MINISHOP_BRANCH=$build_branch"
    --build-arg "REMNAWAVE_MINISHOP_BUILD_PROVENANCE=$build_provenance"
  )
  release_args=()

  if [ "$PUBLISH_CHANNEL" = "release" ]; then
    build_args+=(
      --build-arg "REMNAWAVE_MINISHOP_BUILD_TAG=$release_tag"
      --build-arg "REMNAWAVE_MINISHOP_BUILD_COMMIT=$CI_COMMIT_SHA"
    )
    release_args+=(--no-cache)
  fi

  docker buildx build \
    --file deploy/docker/Dockerfile \
    --target "$target" \
    --platform linux/amd64 \
    --pull \
    --push \
    --provenance=mode=max \
    --sbom=true \
    --tag "$image:$candidate_tag" \
    --label "org.opencontainers.image.source=$OCI_IMAGE_SOURCE" \
    --label "org.opencontainers.image.revision=$CI_COMMIT_SHA" \
    --label "org.opencontainers.image.version=$publish_tag" \
    --label "org.opencontainers.image.ref.name=${release_tag:-$publish_tag}" \
    --metadata-file "$build_metadata" \
    "${build_args[@]}" \
    "${release_args[@]}" \
    .

  digest="$(jq -er '."containerimage.digest"' "$build_metadata")"
  if ! [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo "Build returned a malformed digest for $target: $digest" >&2
    exit 1
  fi
  wait_for_registry_digest "$image:$candidate_tag" "$digest"

  immutable_ref="$image@$digest"
  labels="$(docker buildx imagetools inspect "$immutable_ref" --format '{{json .Image.Config.Labels}}')"
  jq -e \
    --arg source "$OCI_IMAGE_SOURCE" \
    --arg revision "$CI_COMMIT_SHA" \
    --arg version "$publish_tag" \
    --arg ref_name "${release_tag:-$publish_tag}" \
    '."org.opencontainers.image.source" == $source and ."org.opencontainers.image.revision" == $revision and ."org.opencontainers.image.version" == $version and ."org.opencontainers.image.ref.name" == $ref_name' \
    <<< "$labels" > /dev/null

  cosign sign --yes \
    --identity-token "$SIGSTORE_ID_TOKEN" \
    --registry-referrers-mode oci-1-1 \
    --annotations "tag=$publish_tag" \
    --annotations "com.gitlab.ci.pipeline.id=$CI_PIPELINE_ID" \
    --annotations "com.gitlab.ci.job.id=$CI_JOB_ID" \
    --annotations "com.gitlab.ci.commit.sha=$CI_COMMIT_SHA" \
    --annotations "com.gitlab.ci.project.path=$CI_PROJECT_PATH" \
    --annotations "org.opencontainers.image.source=$OCI_IMAGE_SOURCE" \
    --annotations "org.opencontainers.image.revision=$CI_COMMIT_SHA" \
    "$immutable_ref"
  verify_signature "$immutable_ref" "$publish_tag"

  if [ "$PUBLISH_CHANNEL" = "release" ]; then
    docker run --rm \
      -e TRIVY_USERNAME \
      -e TRIVY_PASSWORD \
      "$TRIVY_IMAGE" image \
      --platform linux/amd64 \
      --scanners vuln \
      --severity CRITICAL,HIGH \
      --exit-code 1 \
      --no-progress \
      "$immutable_ref"
  fi

  jq -n \
    --arg target "$target" \
    --arg name "$IMAGE_PREFIX-$target" \
    --arg image "$image" \
    --arg candidate_tag "$candidate_tag" \
    --arg digest "$digest" \
    --arg commit "$CI_COMMIT_SHA" \
    --arg tag "${release_tag:-$publish_tag}" \
    --arg version "$publish_tag" \
    '{target: $target, name: $name, image: $image, candidate_tag: $candidate_tag, digest: $digest, commit: $commit, tag: $tag, version: $version}' \
    > "$candidate_metadata"
done

mapfile -t metadata_files < <(find "$metadata_dir" -maxdepth 1 -type f -name '*.json' ! -name '*-build.json' | sort)
if [ "${#metadata_files[@]}" -ne 3 ]; then
  echo "Expected metadata for exactly three images" >&2
  exit 1
fi

if [ "$PUBLISH_CHANNEL" = "dev" ]; then
  verify_remote_head dev
fi

for metadata in "${metadata_files[@]}"; do
  image="$(jq -r '.image' "$metadata")"
  digest="$(jq -r '.digest' "$metadata")"
  existing_digest="$(registry_digest "$image:$publish_tag" || true)"
  if [ -n "$existing_digest" ] && [ "$PUBLISH_CHANNEL" = "release" ] && [ "$existing_digest" != "$digest" ]; then
    echo "Refusing to overwrite existing stable tag $image:$publish_tag" >&2
    exit 1
  fi
done

if [ "$PUBLISH_CHANNEL" = "release" ]; then
  for metadata in "${metadata_files[@]}"; do
    image="$(jq -r '.image' "$metadata")"
    digest="$(jq -r '.digest' "$metadata")"
    latest_digest="$(registry_digest "$image:latest" || true)"
    if [ -z "$latest_digest" ]; then
      continue
    fi
    latest_labels="$(docker buildx imagetools inspect "$image@$latest_digest" --format '{{json .Image.Config.Labels}}')"
    if ! latest_version="$(jq -er '."org.opencontainers.image.version"' <<< "$latest_labels")"; then
      echo "Current latest image has no version label: $image@$latest_digest" >&2
      exit 1
    fi
    highest_version="$(printf '%s\n%s\n' "$latest_version" "$release_version" | sort -V | tail -n 1)"
    if [ "$highest_version" != "$release_version" ]; then
      echo "Refusing to move latest backwards from $latest_version to $release_version for $image" >&2
      exit 1
    fi
    if [ "$latest_version" = "$release_version" ] && [ "$latest_digest" != "$digest" ]; then
      echo "Refusing to replace current latest release $release_version for $image" >&2
      exit 1
    fi
  done
fi

for metadata in "${metadata_files[@]}"; do
  image="$(jq -r '.image' "$metadata")"
  digest="$(jq -r '.digest' "$metadata")"
  if [ "$(registry_digest "$image:$publish_tag" || true)" != "$digest" ]; then
    promote_tag "$image" "$digest" "$publish_tag"
  fi
  verify_signature "$image:$publish_tag" "$publish_tag"
done

if [ "$PUBLISH_CHANNEL" = "release" ]; then
  for metadata in "${metadata_files[@]}"; do
    image="$(jq -r '.image' "$metadata")"
    digest="$(jq -r '.digest' "$metadata")"
    if [ "$(registry_digest "$image:latest" || true)" != "$digest" ]; then
      promote_tag "$image" "$digest" latest
    fi
    verify_signature "$image:latest" "$publish_tag"
  done
fi

manifest_path="${CI_PROJECT_DIR:-$PWD}/${PUBLISH_CHANNEL}-images.json"
jq -s \
  --arg repository "$CI_PROJECT_PATH" \
  --arg source_repository "$OCI_IMAGE_SOURCE" \
  --arg channel "$PUBLISH_CHANNEL" \
  --arg tag "${release_tag:-$publish_tag}" \
  --arg version "$publish_tag" \
  --arg commit "$CI_COMMIT_SHA" \
  --arg pipeline_id "$CI_PIPELINE_ID" \
  --arg pipeline_url "${CI_PIPELINE_URL:-}" \
  '{
    schema_version: 2,
    release: {repository: $repository, source_repository: $source_repository, channel: $channel, tag: $tag, version: $version, commit: $commit},
    pipeline: {provider: "gitlab", id: $pipeline_id, url: $pipeline_url},
    security: {signature: "sigstore-keyless", provenance: "slsa-buildkit-max", sbom: "spdx", scan: (if $channel == "release" then "trivy-high-critical-blocking" else "not-required" end)},
    images: (map({target, digest, dockerhub: .image, dockerhub_ref: (.image + "@" + .digest)}) | sort_by(.target))
  }' \
  "${metadata_files[@]}" > "$manifest_path"
jq -e '(.images | length == 3) and ([.images[].target] | sort == ["backend", "frontend", "worker"])' "$manifest_path" > /dev/null

if [ "$PUBLISH_CHANNEL" = "release" ]; then
  sha256sum "$manifest_path" > "$manifest_path.sha256"
  cosign sign-blob --yes \
    --identity-token "$SIGSTORE_ID_TOKEN" \
    --bundle "$manifest_path.sigstore.json" \
    "$manifest_path"
  cosign verify-blob \
    --bundle "$manifest_path.sigstore.json" \
    --certificate-identity "$certificate_identity" \
    --certificate-oidc-issuer "$CI_SERVER_URL" \
    "$manifest_path"
fi

if [ -n "${IMAGE_CHANNEL_DOWNSTREAM_REPOSITORY:-}" ] && [ -n "${IMAGE_CHANNEL_DOWNSTREAM_TOKEN:-}" ]; then
  images="$(jq -c '.images | map({key: .target, value: .dockerhub_ref}) | from_entries' "$manifest_path")"
  if [ "$PUBLISH_CHANNEL" = "release" ]; then
    payload="$(jq -cn \
      --arg event_type core-release-images-published \
      --arg repository "$CI_PROJECT_PATH" \
      --arg tag "$release_tag" \
      --arg version "$release_version" \
      --arg commit "$CI_COMMIT_SHA" \
      --argjson images "$images" \
      '{event_type: $event_type, client_payload: {core_repository: $repository, core_release: $tag, core_version: $version, core_commit: $commit, images: $images}}')"
  else
    payload="$(jq -cn \
      --arg event_type core-dev-images-published \
      --arg repository "$CI_PROJECT_PATH" \
      --arg commit "$CI_COMMIT_SHA" \
      --arg ref_name "$CI_COMMIT_REF_NAME" \
      --argjson images "$images" \
      '{event_type: $event_type, client_payload: {core_repository: $repository, core_commit: $commit, core_ref: $ref_name, images: $images}}')"
  fi
  curl --fail-with-body --silent --show-error \
    --request POST \
    --header "Accept: application/vnd.github+json" \
    --header "Authorization: Bearer $IMAGE_CHANNEL_DOWNSTREAM_TOKEN" \
    --header "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/$IMAGE_CHANNEL_DOWNSTREAM_REPOSITORY/dispatches" \
    --data "$payload"
else
  echo "No downstream image consumer is configured; skipping notification."
fi
