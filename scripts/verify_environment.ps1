$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot

try {
    docker version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Linux engine is unavailable. Start Docker Desktop and retry."
    }

    docker build --file docker/Dockerfile --tag lct26-lidar:humble .
    if ($LASTEXITCODE -ne 0) {
        throw "Docker image build failed."
    }

    docker run --rm `
        --shm-size 512m `
        --volume "${projectRoot}:/workspace" `
        --volume "${projectRoot}/data/extracted/for_hackathon:/datasets:ro" `
        lct26-lidar:humble `
        bash /workspace/docker/smoke_test.sh
    if ($LASTEXITCODE -ne 0) {
        throw "Container smoke test failed."
    }

    docker run --rm `
        --shm-size 512m `
        --volume "${projectRoot}:/workspace" `
        --volume "${projectRoot}/data/extracted/for_hackathon:/datasets:ro" `
        lct26-lidar:humble `
        bash /workspace/docker/playback_test.sh
    if ($LASTEXITCODE -ne 0) {
        throw "ROS 2 PointCloud2 playback test failed."
    }
}
finally {
    Pop-Location
}
