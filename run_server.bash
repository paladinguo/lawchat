#!/usr/bin/env bash

# 启动服务
# 1. 启动rasa server
source /home/ecs-user/miniconda3/bin/activate env-p310 && 
screen -S s1 -dm rasa run -m models --endpoints endpoints.yml --credentials credentials.yml --port 5005
# screen -S s1 -dm rasa run -m models --endpoints endpoints.yml --credentials credentials.yml --port 5005 --enable-api --cors "*"
# python -m rasa run actions --port 5055 --actions actions
# 2. 启动action server
screen -S s2 -dm rasa run actions --port 5055 --actions actions
# python -m rasa run actions --port 5055 --actions actions --debug
# 3. 启动main.py
# python main.py
