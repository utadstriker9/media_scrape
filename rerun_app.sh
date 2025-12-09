#!/bin/bash

# Define variables
CONTAINER_ID=$(sudo docker ps -aqf "name=media_scrape")
IMAGE_ID=$(sudo docker images -q media_scrape)

# Remove existing container
sudo docker rm -f $CONTAINER_ID

# Remove existing image
sudo docker rmi -f $IMAGE_ID

# Build the Docker image
sudo docker build -f DockerFile -t media_scrape .

# Run the Docker container in detached mode, mapping port 8801
sudo docker run -d -p 8801:8801 --name media_scrape --shm-size="2g" media_scrape
