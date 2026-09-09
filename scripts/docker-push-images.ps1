$ErrorActionPreference = "Stop"

if (-not $env:IMAGE_TAG) {
    throw "Set IMAGE_TAG to the release tag you want to push"
}

$imageRegistry = if ($env:IMAGE_REGISTRY) { $env:IMAGE_REGISTRY } else { "docker.io" }
$imageNamespace = if ($env:IMAGE_NAMESPACE) { $env:IMAGE_NAMESPACE } else { "3252a8" }
$imageTag = $env:IMAGE_TAG
$imagePrefix = if ($env:IMAGE_PREFIX) { $env:IMAGE_PREFIX } else { "remnawave-minishop" }

function Push-Image {
    param([string]$Target)
    $image = "$imageRegistry/$imageNamespace/$imagePrefix-$Target`:$imageTag"
    Write-Host "Pushing $image" -ForegroundColor Cyan
    docker push $image
}

Push-Image backend
Push-Image worker
Push-Image frontend
