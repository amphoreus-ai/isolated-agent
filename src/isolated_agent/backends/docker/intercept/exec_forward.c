/*
 * exec_forward.c — LD_PRELOAD library that intercepts execve and forwards
 * non-whitelisted commands to task-env via SSH.
 *
 * Replaces the 4-layer shell shim approach (sh-wrapper, tool symlinks,
 * task-shell, fake-bwrap) with a single, comprehensive interception point.
 *
 * Build:  gcc -shared -fPIC -o libexec_forward.so exec_forward.c -ldl
 * Usage:  LD_PRELOAD=/lib/libexec_forward.so EXEC_FORWARD_LOCAL=/usr/local/bin/codex <agent>
 */

#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int (*real_execve)(const char *, char *const[], char *const[]) = NULL;

/* Guard against re-entrance during SSH forwarding. */
static __thread int forwarding = 0;

__attribute__((constructor))
static void init(void) {
    real_execve = dlsym(RTLD_NEXT, "execve");
    if (!real_execve) {
        fprintf(stderr, "exec_forward: failed to resolve real execve\n");
        _exit(127);
    }
}

/* ------------------------------------------------------------------ */
/* Whitelist check                                                     */
/* ------------------------------------------------------------------ */

/*
 * EXEC_FORWARD_LOCAL is a colon-separated list of absolute paths that
 * should execute locally (not be forwarded). Example:
 *   /usr/local/bin/codex:/usr/bin/ssh:/bin/bash
 *
 * Additionally, /usr/bin/ssh and /usr/bin/env are always local.
 */
static int is_local(const char *pathname) {
    /* Always-local binaries (needed by the interceptor and shim layer). */
    if (strcmp(pathname, "/usr/bin/ssh") == 0) return 1;
    if (strcmp(pathname, "/usr/bin/env") == 0) return 1;
    if (strcmp(pathname, "/bin/sh.real") == 0) return 1;
    if (strcmp(pathname, "/usr/local/bin/task-run") == 0) return 1;
    if (strcmp(pathname, "/usr/local/bin/task-shell") == 0) return 1;
    if (strcmp(pathname, "/usr/local/bin/task-exec") == 0) return 1;
    if (strcmp(pathname, "/usr/local/bin/agent-entrypoint") == 0) return 1;
    /* Bash is needed by the shim scripts themselves. */
    if (strcmp(pathname, "/bin/bash") == 0) return 1;
    if (strcmp(pathname, "/usr/bin/bash") == 0) return 1;
    if (strcmp(pathname, "/usr/local/bin/bash") == 0) return 1;

    /* Resolve symlinks so we match canonical paths. */
    char resolved[PATH_MAX];
    const char *check = pathname;
    if (realpath(pathname, resolved) != NULL)
        check = resolved;

    const char *whitelist = getenv("EXEC_FORWARD_LOCAL");
    if (!whitelist || whitelist[0] == '\0')
        return 0;

    /* Walk the colon-separated list. */
    const char *p = whitelist;
    while (*p) {
        const char *sep = strchr(p, ':');
        size_t len = sep ? (size_t)(sep - p) : strlen(p);

        if (strncmp(check, p, len) == 0 && check[len] == '\0')
            return 1;

        /* Also match un-resolved pathname. */
        if (strncmp(pathname, p, len) == 0 && pathname[len] == '\0')
            return 1;

        p += len;
        if (*p == ':') p++;
    }

    return 0;
}

/* ------------------------------------------------------------------ */
/* Argument quoting for SSH                                            */
/* ------------------------------------------------------------------ */

/* Single-quote a string for safe shell transport.  'foo' -> 'foo'
 * Embedded single-quotes: hello'world -> 'hello'\''world'           */
static void quote_into(char *dst, size_t dst_sz, const char *src) {
    size_t pos = 0;
    dst[pos++] = '\'';
    for (const char *s = src; *s && pos + 5 < dst_sz; s++) {
        if (*s == '\'') {
            dst[pos++] = '\'';  /* close quote */
            dst[pos++] = '\\';
            dst[pos++] = '\'';  /* escaped literal ' */
            dst[pos++] = '\'';  /* reopen quote */
        } else {
            dst[pos++] = *s;
        }
    }
    dst[pos++] = '\'';
    dst[pos] = '\0';
}

/* ------------------------------------------------------------------ */
/* Build the SSH-forwarded command                                     */
/* ------------------------------------------------------------------ */

static int forward_via_ssh(const char *pathname, char *const argv[],
                           char *const envp[]) {
    /* Working directory — clamp to /workspace. */
    char cwd[PATH_MAX];
    if (getcwd(cwd, sizeof(cwd)) == NULL)
        strcpy(cwd, "/workspace");
    if (strncmp(cwd, "/workspace", 10) != 0)
        strcpy(cwd, "/workspace");

    /* Build the remote command string. */
    char remote[65536];
    int off = 0;

    char qcwd[PATH_MAX * 2];
    quote_into(qcwd, sizeof(qcwd), cwd);
    off += snprintf(remote + off, sizeof(remote) - off, "cd %s && exec", qcwd);

    /* Append each argument (argv[0] is usually the program name). */
    for (int i = 0; argv[i] != NULL; i++) {
        char qarg[8192];
        quote_into(qarg, sizeof(qarg), argv[i]);
        off += snprintf(remote + off, sizeof(remote) - off, " %s", qarg);
        if (off >= (int)sizeof(remote) - 64) break;
    }

    /* Build new argv for ssh. */
    char *ssh_argv[] = {
        "ssh", "task-env", remote, NULL
    };

    /*
     * Strip LD_PRELOAD from envp so SSH and the remote process
     * don't load the interceptor.
     */
    int env_count = 0;
    for (int i = 0; envp[i] != NULL; i++) env_count++;

    char **clean_envp = alloca((env_count + 1) * sizeof(char *));
    int j = 0;
    for (int i = 0; envp[i] != NULL; i++) {
        if (strncmp(envp[i], "LD_PRELOAD=", 11) == 0) continue;
        clean_envp[j++] = envp[i];
    }
    clean_envp[j] = NULL;

    return real_execve("/usr/bin/ssh", ssh_argv, clean_envp);
}

/* ------------------------------------------------------------------ */
/* The hook                                                            */
/* ------------------------------------------------------------------ */

int execve(const char *pathname, char *const argv[], char *const envp[]) {
    /* Re-entrance guard: if we're already forwarding, pass through. */
    if (forwarding)
        return real_execve(pathname, argv, envp);

    /* Whitelisted binaries execute locally. */
    if (is_local(pathname))
        return real_execve(pathname, argv, envp);

    /* Forward everything else via SSH. */
    forwarding = 1;
    int ret = forward_via_ssh(pathname, argv, envp);
    forwarding = 0;
    return ret;
}
