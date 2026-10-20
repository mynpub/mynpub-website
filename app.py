from flask import Flask, abort, redirect, render_template, request, url_for
from datetime import date
import hashlib
import markdown
import os
from pathlib import Path
import re
import yaml
from lightning import LightningGraph, PUBKEY, valid_scid

app = Flask(__name__)
lightning_graph = LightningGraph(
    executable=os.getenv('CLN_CLI', 'lightning-cli'),
    lightning_dir=os.getenv('CLN_LIGHTNING_DIR'),
    network=os.getenv('CLN_NETWORK', 'bitcoin'),
)
app.config.update(
    DEBUG=os.getenv('DEBUG', 'false').lower() in ('1', 'true', 'yes', 'on'),
    COMPRESS_ENABLED=os.getenv('COMPRESS_ENABLED', 'true').lower() in ('1', 'true', 'yes', 'on'),
    POSTS_DIR=os.getenv('POSTS_DIR', str(Path(__file__).parent / 'content' / 'posts')),
)

if app.config['COMPRESS_ENABLED']:
    from flask_compress import Compress
    Compress(app)

STATIC_VERSION = hashlib.sha256(
    (Path(app.static_folder) / 'style.css').read_bytes()
).hexdigest()[:16]
app.jinja_env.globals['static_version'] = STATIC_VERSION


@app.after_request
def cache_static_assets(response):
    if (request.endpoint == 'static'
            and request.view_args.get('filename') == 'style.css'
            and request.args.get('v') == STATIC_VERSION
            and response.status_code in (200, 304)):
        response.cache_control.public = True
        response.cache_control.max_age = 31536000
        response.cache_control.immutable = True
        response.cache_control.no_cache = None
    return response

# Add markdown filter to Jinja2 environment with extensions for better rendering
def render_markdown(text):
    return markdown.markdown(text, extensions=['fenced_code', 'tables'])

app.jinja_env.filters['markdown'] = render_markdown

# Configuration
SITE_CONFIG = {
    'title': 'My Personal Website',
    'description': 'A personal website with blog, lightning explorer, and resources',
    'author': 'Your Name',
    'adsense_code': '<!-- Google AdSense code would go here -->'
}

# Simple in-memory storage for mailing list subscribers and resources
mailing_list_subscribers = []
resources = []

def load_posts(posts_dir=None):
    posts = []
    for path in sorted(Path(posts_dir if posts_dir is not None else app.config['POSTS_DIR']).glob('*.md')):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
            if not lines or lines[0] != '---':
                raise ValueError('missing opening front matter delimiter')
            end = lines.index('---', 1)
            metadata = yaml.safe_load('\n'.join(lines[1:end]))
            if not isinstance(metadata, dict):
                raise ValueError('front matter must be a mapping')
            title = metadata.get('title')
            post_date = metadata.get('date')
            summary = metadata.get('summary', '')
            if not isinstance(title, str) or not title.strip():
                raise ValueError('title must be a nonempty string')
            if type(post_date) is date:
                post_date = post_date.isoformat()
            if not isinstance(post_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', post_date):
                raise ValueError('date must use YYYY-MM-DD')
            date.fromisoformat(post_date)
            if not isinstance(summary, str):
                raise ValueError('summary must be a string')
            posts.append({
                'slug': path.stem,
                'title': title,
                'date': post_date,
                'summary': summary,
                'content': render_markdown('\n'.join(lines[end + 1:])),
            })
        except (OSError, UnicodeError, ValueError, yaml.YAMLError) as error:
            app.logger.warning('Skipping invalid post %s: %s', path, error)
    posts.sort(key=lambda post: post['slug'])
    posts.sort(key=lambda post: post['date'], reverse=True)
    return posts

def init_sample_data():
    global resources

    # Sample resources
    resources = [
        {
            'title': 'Flask Documentation',
            'url': 'https://flask.palletsprojects.com/',
            'description': 'Official Flask documentation and tutorials'
        },
        {
            'title': 'Python Markdown Library',
            'url': 'https://pypi.org/project/Markdown/',
            'description': 'Python implementation of Markdown parser'
        }
    ]

# Initialize with sample data
init_sample_data()

# Routes
@app.route('/')
def home():
    blog_posts = load_posts()
    per_page = 10
    page = max(1, request.args.get('page', 1, type=int))
    total = len(blog_posts)
    pages = max(1, (total + per_page - 1) // per_page)
    if page > pages:
        abort(404)
    start = (page - 1) * per_page
    return render_template('index.html',
                         posts=blog_posts[start:start + per_page],
                         pagination={
                             'page': page,
                             'pages': pages,
                             'total': total,
                             'per_page': per_page,
                             'has_prev': page > 1,
                             'has_next': page < pages,
                         },
                         config=SITE_CONFIG)

@app.route('/post/<slug>')
def post(slug):
    post = next((p for p in load_posts() if p['slug'] == slug), None)
    if post:
        return render_template('post.html', post=post, config=SITE_CONFIG)
    else:
        return "Post not found", 404

@app.route('/lightning-explorer')
def lightning_explorer():
    query = request.args.get('q', '').strip()
    kind = request.args.get('kind', 'nodes')
    if len(query) > 128 or any(ord(char) < 32 for char in query) or kind not in ('nodes', 'channels'):
        abort(400)
    page, per_page = lightning_page_args()
    if PUBKEY.fullmatch(query):
        return redirect(url_for('lightning_node', pubkey=query.lower()))
    if valid_scid(query):
        return redirect(url_for('lightning_channel', short_channel_id=query))
    state = lightning_graph.get()
    rows = []
    if state.snapshot is not None:
        rows = list(state.snapshot[kind].values())
        if query:
            rows = [node for node in state.snapshot['nodes'].values()
                    if query.casefold() in node['alias'].casefold()]
            kind = 'nodes'
    rows, pagination = lightning_paginate(rows, page, per_page, state.snapshot is not None)
    return render_template('lightning.html', config=SITE_CONFIG, state=state,
                           query=query, kind=kind, rows=rows, pagination=pagination)


def lightning_page_args():
    values = []
    for name, default, maximum in (('page', '1', 1000000000), ('per_page', '50', 100)):
        value = request.args.get(name, default)
        if not re.fullmatch(r'[0-9]{1,10}', value) or not 1 <= int(value) <= maximum:
            abort(400)
        values.append(int(value))
    return values


def lightning_paginate(rows, page, per_page, available=True):
    pages = max(1, (len(rows) + per_page - 1) // per_page)
    if available and page > pages:
        abort(404)
    start = (page - 1) * per_page
    return rows[start:start + per_page], {
        'page': page, 'pages': pages, 'total': len(rows), 'per_page': per_page,
    }


@app.route('/lightning-explorer/node/<pubkey>')
def lightning_node(pubkey):
    if not PUBKEY.fullmatch(pubkey):
        abort(400)
    pubkey = pubkey.lower()
    page, per_page = lightning_page_args()
    state = lightning_graph.get()
    node, rows = None, []
    if state.snapshot is not None:
        node = state.snapshot['nodes'].get(pubkey)
        rows = state.snapshot['node_channels'].get(pubkey, [])
    rows, pagination = lightning_paginate(rows, page, per_page, state.snapshot is not None)
    return render_template('lightning_node.html', config=SITE_CONFIG, state=state,
                           node=node, rows=rows, pagination=pagination), (
                               404 if state.snapshot is not None and node is None else 200)


@app.route('/lightning-explorer/channel/<short_channel_id>')
def lightning_channel(short_channel_id):
    if not valid_scid(short_channel_id):
        abort(400)
    state = lightning_graph.get()
    channel = state.snapshot['channels'].get(short_channel_id) if state.snapshot is not None else None
    return render_template('lightning_channel.html', config=SITE_CONFIG, state=state,
                           channel=channel), (
                               404 if state.snapshot is not None and channel is None else 200)

@app.route('/resources')
def resources_page():
    return render_template('resources.html', resources=resources, config=SITE_CONFIG)

# Publishing is file-based; the unauthenticated admin endpoint is disabled.
@app.route('/admin/add-post', methods=['GET', 'POST'])
def add_post():
    abort(404)

if __name__ == '__main__':
    app.run(host=os.getenv('HOST', '127.0.0.1'),
            port=int(os.getenv('PORT', '5001')))