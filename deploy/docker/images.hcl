# All three targets share a BuildKit solve, including the Python and web builds.
variable "CANDIDATE_TAG" { default = "" }
variable "LOCAL_TAG" { default = "ci" }
variable "CACHE_SUFFIX" { default = "" }

# docker/metadata-action supplies release labels for the publishing workflow.
target "docker-metadata-action" {}

group "default" {
  targets = ["images"]
}

target "images" {
  matrix = { role = ["backend", "worker", "frontend"] }
  name = role
  inherits = ["docker-metadata-action"]
  context = "."
  dockerfile = "deploy/docker/Dockerfile"
  target = role
  platforms = ["linux/amd64"]
  tags = CANDIDATE_TAG == "" ? ["3252a8/remnawave-minishop-${role}:${LOCAL_TAG}"] : [
    "ghcr.io/3252a8/remnawave-minishop-${role}:${CANDIDATE_TAG}",
    "docker.io/3252a8/remnawave-minishop-${role}:${CANDIDATE_TAG}",
  ]
  cache-from = CACHE_SUFFIX == "" ? [] : ["type=gha,scope=${role}-${CACHE_SUFFIX}"]
  cache-to = CACHE_SUFFIX == "" ? [] : ["type=gha,mode=max,scope=${role}-${CACHE_SUFFIX}"]
}
