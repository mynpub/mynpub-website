#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: publish_posts.sh [--source DIR] [--host USER@HOST] [--remote-dir DIR]
                        [--ssh COMMAND] [--dry-run] [--help]

Upload new top-level *.md files only, over SSH. Existing remote filenames
are never overwritten and remote files are never deleted.

Options (corresponding environment variables):
  --source DIR      Local posts folder (POSTS_SOURCE; default: content/posts)
  --host USER@HOST  SSH target, e.g. website@100.100.100.100 (POSTS_HOST)
  --remote-dir DIR  Absolute server folder (POSTS_REMOTE_DIR;
                    default: /srv/mynpub-content/posts)
  --ssh COMMAND     SSH transport (POSTS_SSH; default: ssh)
  --dry-run         Show planned transfers without uploading
  --help, -h        Show this help

Requires rsync 3.x on both machines and an existing writable remote folder.
EOF
}

source_dir=${POSTS_SOURCE:-"$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)/content/posts"}
host=${POSTS_HOST:-}
remote_dir=${POSTS_REMOTE_DIR:-/srv/mynpub-content/posts}
ssh_command=${POSTS_SSH:-ssh}
dry_run=()

while (($#)); do
    case "$1" in
        --source|--host|--remote-dir|--ssh)
            if (($# < 2)) || [[ -z "$2" || "$2" == --* ]]; then
                echo "Missing value for $1" >&2
                exit 2
            fi
            case "$1" in
                --source) source_dir=$2 ;;
                --host) host=$2 ;;
                --remote-dir) remote_dir=$2 ;;
                --ssh) ssh_command=$2 ;;
            esac
            shift 2
            ;;
        --dry-run) dry_run=(--dry-run); shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [[ ! "$host" =~ ^([a-zA-Z0-9_.-]+@)?[a-zA-Z0-9_][a-zA-Z0-9_.-]*$ ]]; then
    echo "Set --host or POSTS_HOST to an SSH target (USER@HOST)." >&2
    exit 2
fi
if [[ "$remote_dir" != /* || ! -d "$source_dir" ]]; then
    echo "Source must be an existing directory; remote directory must be absolute." >&2
    exit 2
fi
source_dir=$(cd -- "$source_dir" && pwd)

exec rsync -rt --verbose --ignore-existing --protect-args \
    --exclude='*/' --include='*.md' --exclude='*' \
    --rsh="$ssh_command" "${dry_run[@]}" -- \
    "$source_dir/" "$host:${remote_dir%/}/"
