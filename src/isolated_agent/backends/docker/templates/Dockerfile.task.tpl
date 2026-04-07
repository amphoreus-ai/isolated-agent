FROM $base_image

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       bash ca-certificates curl git python3-full python3-pip \
       openssh-server $extra_packages $required_apt_tools \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/sshd /root/.ssh \
    && chmod 700 /root/.ssh \
    && ssh-keygen -A

# Key-only auth, no password
RUN sed -i 's/#PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config \
    && sed -i 's/#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config

COPY .ssh/agent_key.pub /root/.ssh/authorized_keys
RUN chmod 600 /root/.ssh/authorized_keys

WORKDIR /workspace
CMD ["/usr/sbin/sshd", "-D", "-e"]
