#!/usr/bin/env bash
set -euo pipefail

base="$RUNNER_TEMP/houji-public-ram"
mkdir "$base"
fetch() {
    local name=$1 repository=$2 revision=$3
    mkdir "$base/$name"
    git -C "$base/$name" init -q
    git -C "$base/$name" fetch -q --depth=1 "https://github.com/$repository.git" "$revision"
    git -C "$base/$name" -c advice.detachedHead=false checkout -q FETCH_HEAD
    test "$(git -C "$base/$name" rev-parse HEAD)" = "$revision"
    printf '%s %s\n' "$name" "$revision"
}

git rev-parse HEAD
uname -m
xcodebuild -version
xcrun --sdk iphoneos --show-sdk-version
python3 --version
fetch houji lonzzi/UniXNU-houji "$HOUJI_PUBLIC_REVISION"
fetch apple-xnu apple-oss-distributions/xnu ac9718fb1af618d5ce8678d0dc6e8a58f252216f
fetch hfs apple-oss-distributions/hfs 124b970fd5390f1c2cd6f985478616a04f6eeb1f
fetch hakios superboyyy/hakios-arm64e-dada f1ae906fcc43ba8f763663257724ba938fb820ab
git -C "$base/houji" apply --index "$GITHUB_WORKSPACE/ci/houji-public-ram/local.patch"
git -C "$base/houji" apply --index "$GITHUB_WORKSPACE/ci/houji-public-ram/symbolsets.patch"
python3 "$base/houji/tools/update-source-manifest.py"
python3 "$base/houji/tools/check-source-tree.py"
sdk=$(xcrun --sdk macosx --show-sdk-path)
ram_id=$(python3 -c 'import uuid; print(uuid.uuid4())')
python3 "$base/houji/tools/prepare-ios26-sources.py" kernel \
    --upstream "$base/apple-xnu" --hfs-upstream "$base/hfs" --reference "$base/hakios" \
    --target-conditionals "$sdk/usr/include/TargetConditionals.h" \
    --ram-only-id "$ram_id" --output "$base/xnu"
git -C "$base/hakios" apply "$base/houji/kernel/ios26/patches/reference-toolchain.patch"
