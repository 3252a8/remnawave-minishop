$ErrorActionPreference = "Stop"

if (-not $env:IMAGE_TAG) {
    throw "Set IMAGE_TAG to the release tag you want to build and push"
}

$imageRegistriesRaw = if ($env:IMAGE_REGISTRIES) { $env:IMAGE_REGISTRIES } else { "ghcr.io,docker.io" }
$imageRegistries = @($imageRegistriesRaw -split "[,;\s]+" | Where-Object { $_ })
$imageNamespace = if ($env:IMAGE_NAMESPACE) { $env:IMAGE_NAMESPACE } else { "3252a8" }
$imageTag = $env:IMAGE_TAG
$imagePrefix = if ($env:IMAGE_PREFIX) { $env:IMAGE_PREFIX } else { "remnawave-minishop" }
$dockerfile = if ($env:DOCKERFILE) { $env:DOCKERFILE } else { "deploy/docker/Dockerfile" }
$targetsRaw = if ($env:TARGETS) { $env:TARGETS } else { "backend,worker,frontend" }
$targets = @($targetsRaw -split "[,;\s]+" | Where-Object { $_ })
$buildProvenance = if ($env:REMNAWAVE_MINISHOP_BUILD_PROVENANCE) { $env:REMNAWAVE_MINISHOP_BUILD_PROVENANCE } else { "custom" }

function Get-ImageName {
    param(
        [string]$Registry,
        [string]$Target
    )

    return "$Registry/$imageNamespace/$imagePrefix-$Target`:$imageTag"
}

function Build-Image {
    param([string]$Target)

    $tagArgs = @()
    foreach ($registry in $imageRegistries) {
        $tagArgs += @("-t", (Get-ImageName -Registry $registry -Target $Target))
    }

    Write-Host "Building $Target for: $($imageRegistries -join ', ')" -ForegroundColor Cyan
    docker build `
        -f $dockerfile `
        --target $Target `
        --build-arg "REMNAWAVE_MINISHOP_BUILD_PROVENANCE=$buildProvenance" `
        @tagArgs `
        .
}

function Push-Image {
    param([string]$Target)

    foreach ($registry in $imageRegistries) {
        $image = Get-ImageName -Registry $registry -Target $Target
        Write-Host "Pushing $image" -ForegroundColor Cyan
        docker push $image
    }
}

foreach ($target in $targets) {
    Build-Image -Target $target
}

foreach ($target in $targets) {
    Push-Image -Target $target
}
