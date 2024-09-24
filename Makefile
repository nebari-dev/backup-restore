# Variables (defaults can be overridden by environment variables or command-line arguments)
IMAGE_NAME ?= $(or $(ENV_IMAGE_NAME), backup_restore)
IMAGE_TAG ?= $(or $(ENV_IMAGE_TAG), latest)
REGISTRY ?= $(or $(ENV_REGISTRY), "")
DOCKERFILE ?= $(or $(ENV_DOCKERFILE), Dockerfile)

# Check if REGISTRY is set; if not, exit with an error
ifeq ($(strip $(REGISTRY)),)
  $(error REGISTRY is not set)
endif

# Full image name including registry
FULL_IMAGE_NAME := $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

# Phony targets (not files)
.PHONY: all build tag push run clean

# Default target when running 'make' without arguments
all: build tag push

# Build the Docker image
build:
	docker build -f $(DOCKERFILE) -t $(IMAGE_NAME):$(IMAGE_TAG) .

# Tag the Docker image with the registry name
tag:
	docker tag $(IMAGE_NAME):$(IMAGE_TAG) $(FULL_IMAGE_NAME)

# Push the Docker image to the registry
push:
	docker push $(FULL_IMAGE_NAME)

# Run the Docker image (useful for testing)
run:
	docker run -it --rm $(IMAGE_NAME):$(IMAGE_TAG)

# Clean up local images
clean:
	-docker rmi -f $(IMAGE_NAME):$(IMAGE_TAG)
	-docker rmi -f $(FULL_IMAGE_NAME)
