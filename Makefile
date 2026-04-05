# Build a Blender-installable addon zip in releases/ using bl_info version.

ADDON_DIR := io_scene_ac3d
INIT_FILE := $(ADDON_DIR)/__init__.py
RELEASE_DIR := releases

VERSION := $(shell grep -m1 '"version":' $(INIT_FILE) | cut -d: -f2 | tr -cd '0-9,.' | sed 's/,$$//' | tr ',' '.')
ZIP_NAME := blender-ac3d-$(VERSION).zip
ZIP_PATH := $(RELEASE_DIR)/$(ZIP_NAME)

.PHONY: all package clean show-version

all: package

show-version:
	@echo $(VERSION)

package:
	@if [ -z "$(VERSION)" ]; then \
		echo "Could not parse version from $(INIT_FILE)"; \
		exit 1; \
	fi
	@mkdir -p $(RELEASE_DIR)
	@rm -f $(ZIP_PATH)
	@zip -r $(ZIP_PATH) $(ADDON_DIR) \
		-x "*/__pycache__/*" "*.pyc" "*.pyo" ".DS_Store"
	@echo "Created $(ZIP_PATH)"

clean:
	@rm -rf $(RELEASE_DIR)
	@echo "Removed $(RELEASE_DIR)"
