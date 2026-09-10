ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG PC_USERNAME
ARG PC_GROUP
ARG PC_UID
ARG PC_GID
ARG PC_HOME
RUN apt-get update && apt-get install -y --no-install-recommends git make ca-certificates libstdc++6 libgomp1 openssh-server xauth && rm -rf /var/lib/apt/lists/*
RUN set -eu; \
    group_entry="$(getent group "$PC_GID" | cut -d: -f1)"; \
    if [ -z "$group_entry" ]; then groupadd -g "$PC_GID" "$PC_GROUP"; \
    elif [ "$group_entry" != "$PC_GROUP" ]; then groupmod -n "$PC_GROUP" "$group_entry"; fi; \
    user_entry="$(getent passwd "$PC_UID" | cut -d: -f1)"; \
    if [ -z "$user_entry" ]; then useradd -u "$PC_UID" -g "$PC_GID" -d "$PC_HOME" -s /bin/bash "$PC_USERNAME"; \
    else if [ "$user_entry" != "$PC_USERNAME" ]; then usermod -l "$PC_USERNAME" "$user_entry"; fi; \
    usermod -d "$PC_HOME" -s /bin/bash -g "$PC_GID" "$PC_USERNAME"; fi; \
    mkdir -p /run/sshd "$PC_HOME"; chown "$PC_UID:$PC_GID" "$PC_HOME"
