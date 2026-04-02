#!/bin/bash
# 打包 AstrBot 插件为 zip

set -e

NAME="dingtalk-feishu-forwarder"
FILES="__init__.py main.py metadata.yaml README.md _conf_schema.json"

rm -rf "$NAME.zip" _pkg
mkdir -p "_pkg/$NAME"
cp $FILES "_pkg/$NAME/"
cd _pkg
zip -r "../$NAME.zip" "$NAME/"
cd ..
rm -rf _pkg

echo "✅ 打包完成: $NAME.zip"
