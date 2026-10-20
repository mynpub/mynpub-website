# My Personal Website

This is a Flask-based personal website with the following features:

## Features

1. **Blog Section** - Main landing page showing latest blog posts with individual post pages
2. **Mailing List Signup** - GNU Mailman integration for collecting email subscribers
3. **Lightning Network Explorer** - Public, read-only network graph from server-local Core Lightning
4. **Resources Section** - Collection of helpful links and resources

## Structure

- `app.py` - Main Flask application with routes and logic
- `templates/` - HTML templates for all pages including base template
- `static/` - CSS styles and other static assets
- `requirements.txt` - Python dependencies needed for the project

## Installation

1. Install Python 3.10 or newer if you haven't already
2. Navigate to the project directory:
   ```bash
   cd /home/andrew/Documents/mynpub-website
   ```
3. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Website

1. Ensure you're in the project directory and virtual environment is activated
2. Run the application:
   ```bash
   python app.py
   ```
3. Visit `http://localhost:5001` in your browser

The development server defaults to `127.0.0.1:5001` with debug disabled.
Set `DEBUG=true` for local debugging, and use `HOST` and `PORT` to override
the bind address. Do not enable debug on a public server.

### Production

Run the WSGI app with Gunicorn behind a reverse proxy providing HTTPS:

```bash
gunicorn --bind "${HOST:-127.0.0.1}:${PORT:-5001}" app:app
```

Compression is enabled by default; set `COMPRESS_ENABLED=false` to disable
it when your proxy handles compression. CSS URLs include a content hash
computed at startup. Matching versioned CSS responses are cached publicly
for one year with `immutable`; unversioned or stale-version requests retain
Flask's default revalidation behavior. Restart the app after changing CSS
and configure the proxy to preserve query strings and cache headers.

The homepage displays 10 posts per page, with Previous/Next navigation
and `?page=2` URLs. Invalid or nonpositive page values use page 1;
pages beyond the last page return 404.

Blog posts are loaded from markdown files on each request, so all workers
see published files without a restart. The obsolete, unauthenticated
`/admin/add-post` endpoint now returns 404 for both GET and POST. Keep it
blocked at the reverse proxy and unused in production.

### Tests

```bash
python test_app.py
```

### Lightning Network Explorer

`/lightning-explorer` shows network-wide node/channel counts, capacity in sat/BTC,
and the last successful snapshot time (UTC). Browse nodes or channels; search by
case-insensitive alias substring, full compressed node pubkey, or short channel
ID (`blockxtxxout`, for example `800000x123x0`). Exact IDs redirect to
`/lightning-explorer/node/<pubkey>` or
`/lightning-explorer/channel/<short_channel_id>`. Node pages show advertised
addresses, announcement time, and channels; channel pages show endpoints,
capacity, and directional base fee (msat), fee rate (ppm), and CLTV delta.
Missing metadata is labeled unknown. All lists use server-side pagination:
`?page=2&per_page=50` (default 50, allowed 1–100); invalid parameters return 400,
out-of-range pages return 404. Search terms are limited to 128 characters and
rendered with HTML escaping.

This is the **public gossip graph known to this node**, not an authoritative
global census, payment history, or local wallet dashboard. Directions are
deduplicated by short channel ID for totals; explicitly private channels are
excluded. Gossip may be incomplete while CLN syncs. “Last updated” is the
website snapshot time, not proof of current channel liveness; individual
announcement/policy times are shown separately.

Install Core Lightning's `lightning-cli` on the website server and configure:

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `CLN_CLI` | `lightning-cli` | Executable path, e.g. `/usr/local/bin/lightning-cli` (no shell arguments) |
| `CLN_LIGHTNING_DIR` | CLI default for service user | Absolute CLN data directory containing the network RPC socket |
| `CLN_NETWORK` | `bitcoin` | CLN network, e.g. `bitcoin`, `testnet`, or `regtest` |

Set these in the website's service environment and restart its workers.
They are trusted operator settings, never URL parameters. The website user
needs access to the configured **local Unix RPC socket** and traversal of its
parent directories. Do not run the website as root, make `/root` traversable,
or make the RPC socket world-accessible to work around permission errors.
For a node currently using `/root/.lightning`, arrange a dedicated service
account/data directory or a local method-filtering Unix-socket proxy before
deployment. A raw CLN socket grants broader capabilities than this explorer
uses: for least privilege, restrict the website's local proxy to
`listnodes` and `listchannels`. Keep wallet files inaccessible to the website.
No remote RPC listener, browser credential, firewall opening, or wallet
mutation endpoint is needed or added. Only those two fixed read methods are
called; neither browser input nor search terms reach RPC.

`lightning.py` caches one complete graph snapshot **per worker** for 45 seconds,
refreshing lazily on the first request after expiry. Each CLI call has a
10-second timeout (at most two calls per refresh). A nonblocking lock prevents
concurrent refresh storms: other requests immediately see the previous
snapshot or a “refresh in progress” message. Failed refreshes back off for
45 seconds and retain the last good snapshot, clearly marked stale with its
original timestamp. With no snapshot, all explorer pages render a friendly
unavailable state rather than a 500; CLI stderr and local paths are not shown.
Snapshots are memory-only, disappear on restart, and may differ briefly
between Gunicorn workers. Budget memory for the gossip graph per worker;
use a modest worker count and a WSGI/proxy timeout above the two-call refresh
budget. No historical graph storage or background scheduler is required.
If capacity is missing on a channel, totals explicitly indicate a lower bound.

Run `python test_lightning.py` for focused mock-RPC parsing, cache/concurrency,
search/escaping, pagination, and outage checks. These are also included in
`python test_app.py`. No live node is required for tests. Before production,
verify `listnodes` and `listchannels` as the actual website service account
using the same directory/network settings, then check overview and both
detail pages. If `lightningd` is unhealthy (including a PID-lock conflict),
repair the node service separately; the website does not start, stop, or
otherwise manage it.

## Adding New Pages

To add new pages to your website:

1. Create a new route in `app.py`
2. Create a new HTML template in `/templates/`
3. Add the navigation link in the base template (`templates/base.html`)

## Adding Content

### Blog Posts
Use the markdown publishing workflow below, not the former admin form.

### Resources Section
Resources are added directly to the resources list in `app.py`.

## Markdown publishing workflow

### Write posts

The default layout is relative to the application, not the working directory:

```text
content/
  posts/
    2026-10-20-my-first-post.md
scripts/
  publish_posts.sh
```

Only regular, top-level `*.md` files are loaded; nested folders, symlinks,
and other extensions (including `.MD`) are ignored. Keep drafts outside
your publishing folder. Each file must start with YAML front matter:

```markdown
---
title: My First Post
date: 2026-10-20
summary: A short introduction to my website.
---

# Welcome

This is my first **markdown** post.
```

`title` must be a nonempty string and `date` a valid calendar date in
`YYYY-MM-DD` format (quoted or unquoted). `summary` is an optional string,
defaulting to empty. Invalid YAML, missing/invalid metadata, unreadable files,
and invalid UTF-8 files are skipped with warnings in the Gunicorn/application
logs; valid posts still display. A missing or empty posts folder renders
“No blog posts available.”

The filename without `.md` is the stable slug, for example
`/post/2026-10-20-my-first-post`. Prefer unique lowercase, hyphenated
filenames; renaming one changes its URL. Posts sort newest date first,
then by slug ascending for equal dates, with 10 posts per index page.
Markdown supports fenced code and tables, including raw HTML. **Only trusted
authors should have write access to the content directory**; this is not
an untrusted-user publishing system.

### Configure production storage

Keep production content outside the application checkout so deployments do
not replace it. For example, if `website` is your existing SSH publishing
account and Gunicorn service user:

```bash
sudo install -d -o website -g website -m 0750 \
  /srv/mynpub-content /srv/mynpub-content/posts
sudo systemctl edit mynpub-website
```

Add this service override:

```ini
[Service]
Environment=POSTS_DIR=/srv/mynpub-content/posts
```

Then apply the configuration once:

```bash
sudo systemctl daemon-reload
sudo systemctl restart mynpub-website
```

Adapt the account/group to your server. The SSH publishing account needs
write access, and the Gunicorn account needs directory traversal and read
access to uploaded files. If using separate accounts, arrange shared group
permissions, including group-readable files. Do not make the folder
world-writable. `POSTS_DIR` should be an absolute path; locally you can use
`POSTS_DIR=/path/to/posts python app.py`.

**Migration:** the former in-memory sample posts are no longer displayed;
there is intentionally no sample-post fallback. Save any posts you want
to retain as files before deployment. Old integer IDs have no durable
mapping and return 404 unless a file happens to have that numeric slug.
Resources and other non-blog routes are unchanged.

### Publish from your laptop

Install Bash, SSH, and rsync 3.x on the laptop, and rsync 3.x on the server.
The remote folder must already exist. Use an authorized SSH account over
your Tailscale address or MagicDNS hostname; no public SSH access is needed:

```bash
./scripts/publish_posts.sh \
  --source "$HOME/Blog/published" \
  --host website@100.100.100.100 \
  --remote-dir /srv/mynpub-content/posts \
  --dry-run
```

Review the output, then repeat without `--dry-run` to publish. Subsequent
web requests discover new files without a service restart. You can also
set `POSTS_SOURCE`, `POSTS_HOST`, `POSTS_REMOTE_DIR`, and `POSTS_SSH`
(default `ssh`); CLI options override these values. For example,
`--ssh 'ssh -p 2222'` selects a nondefault SSH port. Run
`./scripts/publish_posts.sh --help` for defaults and usage. Errors, including
SSH/rsync failures, produce a nonzero exit status.

### Create a local publishing shortcut

After configuring SSH access and verifying the publishing command above,
create a wrapper on your desktop, outside the repository:

```bash
nano ~/publish-blog.sh
```

Paste this script:

```bash
#!/usr/bin/env bash
set -euo pipefail

exec bash "$HOME/Documents/mynpub-website/scripts/publish_posts.sh" \
  --source "$HOME/Blog/published" \
  --host "publisher@100.100.100.100" \
  --remote-dir "/srv/mynpub-content/posts" \
  "$@"
```

Change the repository path on the `exec bash` line to your local checkout.
Set `--source` to your local folder of ready-to-publish Markdown files,
`--host` to your authorized SSH account and confirmed Tailscale IP or
MagicDNS hostname, and `--remote-dir` to your existing server posts folder
(the production `POSTS_DIR`). The host above is only an example. Keep paths
quoted; use `$HOME` or absolute paths rather than `~` inside quotes.

Save with **Ctrl+O**, **Enter**, then exit with **Ctrl+X**. Make it executable:

```bash
chmod +x ~/publish-blog.sh
```

From any directory, preview without uploading:

```bash
~/publish-blog.sh --dry-run
```

Review the output, then publish:

```bash
~/publish-blog.sh
```

`"$@"` forwards extra arguments, such as `--dry-run`, to the repository
script. This shortcut keeps the same add-only behavior: existing remote
filenames are skipped even when edited locally, and remote files are never
deleted. Use the correction procedure below for intentional updates.

### Add-only behavior and corrections

The script uses rsync over SSH with `--ignore-existing`, markdown-only
filters, and no deletion options. An existing remote filename is skipped
even if its local contents have changed. Deleting a laptop file never
deletes its server copy. Files transfer through rsync's temporary files
and rename on completion; do not use `--inplace` for publishing.

For an intentional correction, back up the server copy, review your changes,
then explicitly overwrite **that one file** outside the add-only script:

```bash
rsync -t --protect-args -e ssh -- \
  "$HOME/Blog/published/2026-10-20-my-first-post.md" \
  website@100.100.100.100:/srv/mynpub-content/posts/
```

This separate command can overwrite that file; it does not delete others.
To unpublish, manually remove the specific server file after backing it up.
Back up `/srv/mynpub-content/posts` independently of the application Git repo.

### Workflow tests

`python test_app.py` tests loading/validation, deterministic ordering,
listing/detail routes, live discovery, pagination, and the disabled admin
endpoint. Script tests substitute a recording rsync executable to verify
arguments, environment configuration, filters, dry-run, and error exit
codes without contacting a server.

Before first production use, dry-run against a disposable remote folder.
Publish a markdown file alongside a non-markdown file, change and republish
the markdown file, then remove it locally and republish: only the original
markdown file should remain remotely, unchanged. Verify the result over
SSH; this checks the real rsync/SSH installation and permissions.