#!/usr/bin/env bash
set -euo pipefail

channel="$1"
commit="$2"
tag="$3"
metadata_dir="$4"
original_manifest="${5:-}"
source="$GITHUB_SERVER_URL/$GITHUB_REPOSITORY"
branch=dev
version="$tag"
if [ "$channel" = release ]; then
  branch=main
  version="${tag#v}"
fi

head="$(git ls-remote "$source.git" "refs/heads/$branch" | cut -f1)"
test -n "$head"
if [ -n "$original_manifest" ]; then
  test "$channel" = release
  test "$head" = "$GITHUB_SHA"
  jq -e --arg repo "$GITHUB_REPOSITORY" --arg commit "$commit" --arg tag "$tag" '
    .schema_version == 1 and .release.repository == $repo and
    .release.commit == $commit and .release.tag == $tag and
    ([.images[].target] | sort) == ["backend", "frontend", "worker"] and
    all(.images[].digest; test("^sha256:[0-9a-f]{64}$"))
  ' "$original_manifest" > /dev/null
elif [ "$head" != "$commit" ]; then
  if [ "$channel" = dev ]; then
    echo "Skipping dev publication for superseded revision $commit"
    exit 0
  fi
  echo "Stable source $commit must still be current main ($head)" >&2
  exit 1
fi

registries=("ghcr.io/$GITHUB_REPOSITORY_OWNER" "docker.io/$GITHUB_REPOSITORY_OWNER")
targets=(backend worker frontend)
declare -A digests
images='{}'

existing_digest() {
  local result
  if result="$(docker buildx imagetools inspect "$1" --format '{{.Manifest.Digest}}' 2>&1)"; then
    printf '%s\n' "$result"
  elif [[ "$result" != *"not found"* && "$result" != *"manifest unknown"* ]]; then
    printf '%s\n' "$result" >&2
    return 1
  fi
}

for target in "${targets[@]}"; do
  digest="$(cat "$metadata_dir/$target.digest")"
  [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]]
  digests[$target]="$digest"
  for registry in "${registries[@]}"; do
    image="$registry/remnawave-minishop-$target"
    labels="$(docker buildx imagetools inspect "$image@$digest" --format '{{json .Image.Config.Labels}}')"
    jq -e --arg source "$source" --arg sha "$commit" --arg tag "$tag" --arg version "$version" \
      '."org.opencontainers.image.revision" == $sha and ."org.opencontainers.image.source" == $source and
       ."org.opencontainers.image.ref.name" == $tag and ."org.opencontainers.image.version" == $version' \
      <<< "$labels" > /dev/null
    if [ "$channel" = release ]; then
      if [ -n "$original_manifest" ]; then
        original="$(jq -er --arg target "$target" '.images[] | select(.target == $target) | .digest' "$original_manifest")"
        for published_tag in "$version" latest; do
          previous="$(existing_digest "$image:$published_tag")"
          if [ "$previous" != "$original" ] && [ "$previous" != "$digest" ]; then
            echo "Refusing to reissue $image:$published_tag at an unexpected digest" >&2
            exit 1
          fi
        done
        continue
      fi
      previous="$(existing_digest "$image:$version")"
      if [ -n "$previous" ] && [ "$previous" != "$digest" ]; then
        echo "Refusing to overwrite immutable tag $image:$version" >&2
        exit 1
      fi
      previous="$(existing_digest "$image:latest")"
      if [ -n "$previous" ]; then
        labels="$(docker buildx imagetools inspect "$image@$previous" --format '{{json .Image.Config.Labels}}')"
        previous_version="$(jq -er '."org.opencontainers.image.version"' <<< "$labels")"
        if ! [[ "$previous_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] ||
          [ "$(printf '%s\n' "$previous_version" "$version" | sort -V | tail -n 1)" != "$version" ] ||
          { [ "$previous_version" = "$version" ] && [ "$previous" != "$digest" ]; }; then
          echo "Refusing to replace $image:latest at version $previous_version with $version" >&2
          exit 1
        fi
      fi
    fi
  done
  images="$(jq -c --arg target "$target" --arg digest "$digest" '. + {($target): $digest}' <<< "$images")"
done

channel_tags=("$version")
if [ "$channel" = release ]; then channel_tags+=(latest); fi
for channel_tag in "${channel_tags[@]}"; do
  for registry in "${registries[@]}"; do
    for target in "${targets[@]}"; do
      image="$registry/remnawave-minishop-$target"
      digest="${digests[$target]}"
      for attempt in 1 2 3 4; do
        if docker buildx imagetools create --prefer-index=false --tag "$image:$channel_tag" "$image@$digest" &&
          [ "$(docker buildx imagetools inspect "$image:$channel_tag" --format '{{.Manifest.Digest}}')" = "$digest" ]; then
          break
        fi
        [ "$attempt" != 4 ] || exit 1
        sleep "$((attempt * 5))"
      done
    done
  done
done
echo "digests=$images" >> "$GITHUB_OUTPUT"
