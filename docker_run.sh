#!/bin/bash
docker run -e SILENTBOT_WIF -e PIBARA_WIF -e SILENTBOT_DATA_DIR='/mnt' --mount type=bind,source="$(pwd)"/store,target=/mnt -it pibara/silentbot:alpha python /application/silentbot.py silentbot pibara
