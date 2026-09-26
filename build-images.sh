#!/bin/bash

#
# Copyright (C) 2023 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-3.0-or-later
#

# Terminate on error
set -e

# Prepare variables for later use
images=()
# The image will be pushed to GitHub container registry
repobase="${REPOBASE:-ghcr.io/platypuschan}"
# Keep the published image name aligned with module-info.yml, which derives
# "ntfy-reworked" from the repository name "ns8-ntfy-reworked".
reponame="ntfy-reworked"
repository_source="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-Platypuschan/ns8-ntfy-reworked}"
NTFY_TAG="v2.14"
# Create a new empty container image
container=$(buildah from scratch)

# Reuse existing nodebuilder-ntfy container, to speed up builds
if ! buildah containers --format "{{.ContainerName}}" | grep -q nodebuilder-ntfy; then
	echo "Pulling NodeJS runtime..."
	buildah from --name nodebuilder-ntfy -v "${PWD}:/usr/src:Z" docker.io/library/node:lts
fi

echo "Build static UI files with node..."
buildah run \
	--workingdir=/usr/src/ui \
	--env="NODE_OPTIONS=--openssl-legacy-provider" \
	nodebuilder-ntfy \
	sh -c "yarn install && yarn build"

# Add imageroot directory to the container image
buildah add "${container}" imageroot /imageroot
buildah add "${container}" ui/dist /ui
# Declare the pinned ntfy runtime image, one reserved web port and a rootless container.
# IMAGETAG overrides the published module tag (latest by default).
buildah config --entrypoint=/ \
	--label="org.opencontainers.image.source=${repository_source}" \
	--label="org.nethserver.authorizations=traefik@node:routeadm" \
	--label="org.nethserver.tcp-ports-demand=1" \
	--label="org.nethserver.rootfull=0" \
	--label="org.nethserver.images=docker.io/binwiederhier/ntfy:${NTFY_TAG}" \
	"${container}"
# Commit the image
buildah commit "${container}" "${repobase}/${reponame}"

# Append the image URL to the images array
images+=("${repobase}/${reponame}")

#
# NOTICE:
#
# It is possible to build and publish multiple images.
#
# 1. create another buildah container
# 2. add things to it and commit it
# 3. append the image url to the images array
#

#
# Setup CI when pushing to Github.
# Warning! docker::// protocol expects lowercase letters (,,)
if [[ -n "${CI}" ]]; then
	# Set output value for Github Actions
	printf "images=%s\n" "${images[*],,}" >>"${GITHUB_OUTPUT}"
else
	# Just print info for manual push
	printf "Publish the images with:\n\n"
	for image in "${images[@],,}"; do printf "  buildah push %s docker://%s:%s\n" "${image}" "${image}" "${IMAGETAG:-latest}"; done
	printf "\n"
fi
