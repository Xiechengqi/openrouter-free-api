#!/usr/bin/env bash

BASEPATH=`dirname $(readlink -f ${BASH_SOURCE[0]})` && cd $BASEPATH

name="chromium"
# docker rm -f ${name}
docker run -itd \
  --restart=always \
  -e IF_IDE_ON="false" \
  -e IF_CCSWITCH_ON="false" \
  -e IF_DUFS_ON="false" \
  -e IF_SOCKS_PROXY="false" \
  -e IF_CURSOR_CLI_ON="false" \
  -e IF_GEMINI_CLI_ON="false" \
  -e IF_CODEX_CLI_ON="false" \
  -e IF_CLAUDE_CLI_ON="false" \
  -e IF_GOLANG_ON="false" \
  -e IF_NODEJS_ON="false" \
  -e IF_JUPYTER_ON="false" \
  -e IF_NPS_ON="false" \
  -e IF_NPC_ON="false" \
  -e IF_YPROMPT_ON="false" \
  -e IF_TERMINAL_ON="true" \
  -e TERMINAL_USER="root" \
  -e TERMINAL_PASSWORD="123123" \
  -e LANG=C.UTF-8 \
  -e CHROMIUM_CLEAN_SINGLETONLOCK=true \
  -e CHROMIUM_START_URLS="chrome://version" \
  -v ${PWD}/start.sh:/app/start.sh \
  -v ${PWD}/main.py:/app/main.py \
  -v ${PWD}/requirements.txt:/app/requirements.txt \
  -v ${PWD}/data:/app/data \
  --name ${name} fullnode/remote-chromium-ubuntu:latest

docker ps

sleep 10

docker ps
docker logs --tail 30 ${name}

# cat /etc/os-release
sleep 10

# pwd
# ls
docker exec -i ${name} "pwd"
docker exec -i ${name} "ls --color=auto -alht"
docker exec -i ${name} "/app/start.sh"
