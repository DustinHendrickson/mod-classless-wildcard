#!/bin/bash
# Builds the mpqtool binary (StormLib-based MPQ pack/extract/list utility).
set -e
cd "$(dirname "$0")"

if [ ! -d StormLib ]; then
    git clone --depth 1 https://github.com/ladislav-zezula/StormLib.git
fi

cmake -S StormLib -B StormLib/build -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=OFF -DSTORM_USE_BUNDLED_LIBRARIES=ON
cmake --build StormLib/build -j"$(nproc)"

gcc -O2 -o mpqtool mpqtool.c -I StormLib/src StormLib/build/libstorm.a -lz -lbz2 -lstdc++ -lm
echo "built ./mpqtool"
