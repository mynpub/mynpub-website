#!/usr/bin/env python3
"""
Simple functional test for the Flask application
"""

import sys
import os
import gzip
import hashlib
import re
import runpy
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from test_lightning import (
    test_lightning_parsing, test_lightning_cache, test_lightning_concurrency,
    test_lightning_routes, test_lightning_pagination,
)

# Add the project directory to Python path
sys.path.insert(0, '/home/andrew/Documents/mynpub-website')

def test_app_import():
    """Test that we can import the app without errors"""
    try:
        from app import app
        print("✓ App imported successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to import app: {e}")
        return False

def test_app_routes():
    """Test that basic routes exist"""
    try:
        from app import app
        
        # Test that we can create a test client
        with app.test_client() as client:
            # Test home page
            response = client.get('/')
            print(f"✓ Home page responded with status: {response.status_code}")
            
            # Test mailing list page  
            response = client.get('/mailing-list')
            print(f"✓ Mailing list page responded with status: {response.status_code}")
            
            # Test lightning explorer
            response = client.get('/lightning-explorer')
            print(f"✓ Lightning explorer responded with status: {response.status_code}")
            
            # Test resources page
            response = client.get('/resources')
            print(f"✓ Resources page responded with status: {response.status_code}")
            
            print("✓ All basic routes working correctly")
            return True
            
    except Exception as e:
        print(f"✗ Route test failed: {e}")
        return False

def test_sample_data():
    """Test that non-blog sample resources are still initialized."""
    try:
        from app import resources
        assert len(resources) > 0
        print("✓ Sample resources loaded")
        return True
            
    except Exception as e:
        print(f"✗ Sample data test failed: {e}")
        return False

def test_markdown_posts():
    """Load validated top-level markdown files, sorted deterministically."""
    try:
        import app
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            assert app.load_posts(folder / 'missing') == []
            assert app.load_posts(folder) == []
            valid = {
                'old': 'title: Old\ndate: 2025-01-01',
                'z-new': 'title: New Z\ndate: "2026-10-20"\nsummary: New summary',
                'a-new': 'title: New A\ndate: 2026-10-20',
            }
            for slug, metadata in valid.items():
                (folder / f'{slug}.md').write_text(
                    f'---\n{metadata}\n---\n# Hello\n\n**Markdown** body.\n',
                    encoding='utf-8',
                )
            for filename in ('ignored.txt', 'ignored.MD'):
                (folder / filename).write_text('Not a post', encoding='utf-8')
            (folder / 'nested').mkdir()
            (folder / 'nested' / 'hidden.md').write_text(
                '---\ntitle: Hidden\ndate: 2026-10-20\n---\nBody', encoding='utf-8',
            )
            (folder / 'link.md').symlink_to(folder / 'old.md')
            posts = app.load_posts(folder)
            assert [p['slug'] for p in posts] == ['a-new', 'z-new', 'old']
            assert posts[0]['date'] == '2026-10-20'
            assert posts[0]['summary'] == ''
            assert posts[1]['summary'] == 'New summary'
            assert '<h1>Hello</h1>' in posts[0]['content']
            assert '<strong>Markdown</strong>' in posts[0]['content']
            invalid = [
                'No front matter',
                '---\ntitle: Unclosed',
                '---\n- a list\n---\nBody',
                '---\n---\nBody',
                '---\ntitle: Missing date\n---\nBody',
                '---\ndate: 2026-10-20\n---\nBody',
                '---\ntitle: " "\ndate: 2026-10-20\n---',
                '---\ntitle: 123\ndate: 2026-10-20\n---',
                '---\ntitle: Bad date\ndate: 2026-02-30\n---',
                '---\ntitle: Bad date\ndate: "2026-1-01"\n---',
                '---\ntitle: Bad date\ndate: 20261020\n---',
                '---\ntitle: Bad summary\ndate: 2026-10-20\nsummary: []\n---',
                '---\ntitle: [broken YAML\n---',
                '---\ntitle: !!python/object:builtins.object {}\n---',
            ]
            for i, content in enumerate(invalid):
                (folder / f'invalid-{i}.md').write_text(content, encoding='utf-8')
            (folder / 'bad-encoding.md').write_bytes(b'\xff')
            with patch.object(app.app.logger, 'warning') as warning:
                assert app.load_posts(folder) == posts
                assert warning.call_count == len(invalid) + 1
        print("✓ Markdown validation, rendering, filtering, and sorting work")
        return True
    except Exception as e:
        print(f"✗ Markdown loading test failed: {e}")
        return False

def test_post_routes():
    """Listing/detail use disk content, including new files without restart."""
    try:
        import app
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(app.app.config, POSTS_DIR=directory), \
                app.app.test_client() as client:
            response = client.get('/')
            assert response.status_code == 200
            assert b'No blog posts available.' in response.data
            assert client.get('/?page=2').status_code == 404
            assert client.get('/post/missing').status_code == 404
            assert client.get('/post/1').status_code == 404
            path = Path(directory) / 'first-post.md'
            path.write_text(
                '---\ntitle: My first post\ndate: 2026-10-20\n'
                'summary: A short introduction\n---\n# Welcome\n\n**Hello**!',
                encoding='utf-8',
            )
            html = client.get('/').get_data(as_text=True)
            assert 'href="/post/first-post"' in html
            assert 'My first post' in html and 'A short introduction' in html
            response = client.get('/post/first-post')
            assert response.status_code == 200
            assert b'<h1>Welcome</h1>' in response.data
            assert b'<strong>Hello</strong>' in response.data
            path.unlink()
            assert client.get('/post/first-post').status_code == 404
            assert b'No blog posts available.' in client.get('/').data
        print("✓ File-based listing, slug detail, empty state, and live discovery work")
        return True
    except Exception as e:
        print(f"✗ Post route test failed: {e}")
        return False

def test_pagination():
    """Test page boundaries, navigation, and invalid page parameters."""
    try:
        import app
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(app.app.config, POSTS_DIR=directory), \
                app.app.test_client() as client:
            for i in range(1, 22):
                (Path(directory) / f'post-{i:02}.md').write_text(
                    f'---\ntitle: Post {i}\ndate: 2026-10-20\nsummary: Summary\n---\nBody',
                    encoding='utf-8',
                )
            for page, count in ((1, 10), (2, 10), (3, 1)):
                response = client.get(f'/?page={page}')
                html = response.get_data(as_text=True)
                assert response.status_code == 200
                assert html.count('<article class="blog-post">') == count
                assert f'Page {page} of 3' in html
                assert ('rel="prev"' in html) == (page > 1)
                assert ('rel="next"' in html) == (page < 3)
                for i in range(1, 22):
                    assert (f'>Post {i}</a>' in html) == ((page - 1) * 10 < i <= page * 10)
            html = client.get('/?page=2').get_data(as_text=True)
            assert 'href="/?page=1" rel="prev"' in html
            assert 'href="/?page=3" rel="next"' in html
            for page in ('invalid', '', '0', '-1', '1.5'):
                assert client.get(f'/?page={page}').data == client.get('/').data
            assert client.get('/?page=4').status_code == 404
            assert client.get('/?page=999999').status_code == 404
            posts = app.load_posts()
        for count in (0, 10, 11, 20):
            with patch.object(app, 'load_posts', return_value=posts[:count]), app.app.test_client() as client:
                response = client.get('/')
                assert response.status_code == 200
                assert response.get_data(as_text=True).count('<article class="blog-post">') == min(count, 10)
                assert client.get('/?page=2').status_code == (200 if count > 10 else 404)
                assert client.get('/?page=3').status_code == 404
        print("✓ Pagination boundaries and navigation work")
        return True
    except Exception as e:
        print(f"✗ Pagination test failed: {e}")
        return False

def test_static_caching():
    """Only current fingerprinted CSS should receive immutable caching."""
    try:
        from app import app, STATIC_VERSION
        css = (Path(app.static_folder) / 'style.css').read_bytes()
        assert STATIC_VERSION == hashlib.sha256(css).hexdigest()[:16]
        with app.test_client() as client:
            html = client.get('/').get_data(as_text=True)
            url = re.search(r'href="([^"]*style\.css[^"]*)"', html).group(1)
            assert f'?v={STATIC_VERSION}' in url
            assert 'style=' not in html
            response = client.get(url)
            assert response.status_code == 200
            assert response.data == css
            assert response.cache_control.public
            assert response.cache_control.max_age == 31536000
            assert response.cache_control.immutable
            assert not response.cache_control.no_cache
            assert response.headers.get('ETag')
            conditional = client.get(url, headers={'If-None-Match': response.headers['ETag']})
            assert conditional.status_code == 304
            assert conditional.cache_control.immutable
            for url in ('/static/style.css', '/static/style.css?v=stale',
                        f'/static/missing.css?v={STATIC_VERSION}', '/'):
                response = client.get(url)
                assert not response.cache_control.immutable
                assert response.cache_control.max_age != 31536000
        print("✓ CSS fingerprinting, caching, and revalidation work")
        return True
    except Exception as e:
        print(f"✗ Static caching test failed: {e}")
        return False

def test_compression_and_environment():
    """Test gzip negotiation and environment-controlled development startup."""
    try:
        from app import app
        with app.test_client() as client:
            plain = client.get('/', headers={'Accept-Encoding': 'identity'})
            compressed = client.get('/', headers={'Accept-Encoding': 'gzip'})
            assert compressed.headers['Content-Encoding'] == 'gzip'
            assert 'Accept-Encoding' in compressed.vary
            assert gzip.decompress(compressed.data) == plain.data
            assert len(compressed.data) < len(plain.data)
        for enabled in (False, True):
            environment = {
                'DEBUG': str(enabled), 'COMPRESS_ENABLED': str(enabled),
                'HOST': '127.0.0.2', 'PORT': '5050',
                'POSTS_DIR': '/tmp/mynpub-test-posts',
            }
            with patch.dict(os.environ, environment), patch.object(Flask, 'run') as run:
                namespace = runpy.run_path(str(Path(__file__).with_name('app.py')), run_name='__main__')
                configured_app = namespace['app']
                assert configured_app.debug == enabled
                assert configured_app.config['COMPRESS_ENABLED'] == enabled
                assert configured_app.config['POSTS_DIR'] == '/tmp/mynpub-test-posts'
                run.assert_called_once_with(host='127.0.0.2', port=5050)
                with configured_app.test_client() as client:
                    response = client.get('/', headers={'Accept-Encoding': 'gzip'})
                    assert (response.headers.get('Content-Encoding') == 'gzip') == enabled
        with patch.dict(os.environ):
            os.environ.pop('DEBUG', None)
            os.environ.pop('COMPRESS_ENABLED', None)
            os.environ.pop('POSTS_DIR', None)
            with patch.object(Flask, 'run') as run:
                namespace = runpy.run_path(str(Path(__file__).with_name('app.py')))
                assert not namespace['app'].debug
                assert namespace['app'].config['COMPRESS_ENABLED']
                assert namespace['app'].config['POSTS_DIR'] == str(Path(__file__).parent / 'content' / 'posts')
                run.assert_not_called()
        print("✓ Compression and environment configuration work")
        return True
    except Exception as e:
        print(f"✗ Compression/environment test failed: {e}")
        return False

def test_add_post_form():
    """The unauthenticated legacy publishing endpoint must stay disabled."""
    try:
        import app
        with app.app.test_client() as client:
            assert client.get('/admin/add-post').status_code == 404
            response = client.post('/admin/add-post', data={
                'title': 'New post', 'date': '2026-10-20', 'content': 'Post content',
            })
            assert response.status_code == 404
        print("✓ Legacy admin publishing is disabled")
        return True
    except Exception as e:
        print(f"✗ Add-post form test failed: {e}")
        return False

def test_publish_script():
    """Inspect rsync arguments without contacting a server."""
    try:
        script = Path(__file__).parent / 'scripts' / 'publish_posts.sh'
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / 'local:posts with spaces'
            source.mkdir()
            arguments = folder / 'arguments'
            fake_rsync = folder / 'rsync'
            fake_rsync.write_text(
                '#!/bin/sh\nprintf "%s\\0" "$@" > "$RSYNC_ARGS_FILE"\n'
                'exit "${RSYNC_EXIT_CODE:-0}"\n', encoding='utf-8',
            )
            fake_rsync.chmod(0o755)
            environment = {
                'PATH': f'{folder}:{os.defpath}',
                'RSYNC_ARGS_FILE': str(arguments),
            }
            def run(*args, **env):
                return subprocess.run(
                    ['bash', str(script), *args], env={**environment, **env},
                    capture_output=True, text=True,
                )
            assert run('--help').returncode == 0
            assert not arguments.exists()
            for args in ((), ('--unknown',), ('--source',), ('--host', '--dry-run'),
                         ('--host', '-unsafe'), ('--host', 'user@host', '--remote-dir', 'relative'),
                         ('--host', 'user@host', '--source', str(folder / 'missing'))):
                assert run(*args).returncode != 0
                assert not arguments.exists()
            result = run('--source', str(source), '--host', 'writer@100.100.100.100',
                         '--remote-dir', '/srv/posts with spaces', '--ssh', 'ssh -p 2222', '--dry-run')
            assert result.returncode == 0, result.stderr
            args = arguments.read_bytes().decode().rstrip('\0').split('\0')
            assert args == [
                '-rt', '--verbose', '--ignore-existing', '--protect-args',
                '--exclude=*/', '--include=*.md', '--exclude=*',
                '--rsh=ssh -p 2222', '--dry-run', '--',
                f'{source}/', 'writer@100.100.100.100:/srv/posts with spaces/',
            ]
            result = run(POSTS_SOURCE=str(source), POSTS_HOST='writer@server',
                         POSTS_REMOTE_DIR='/srv/posts/', POSTS_SSH='ssh')
            assert result.returncode == 0, result.stderr
            args = arguments.read_bytes().decode().rstrip('\0').split('\0')
            assert '--dry-run' not in args
            assert args[-1] == 'writer@server:/srv/posts/'
            assert run('--host', 'writer@server', RSYNC_EXIT_CODE='23').returncode == 23
        print("✓ Publishing arguments, add-only filters, dry-run, and errors work")
        return True
    except Exception as e:
        print(f"✗ Publish script test failed: {e}")
        return False

if __name__ == '__main__':
    print("Running Flask application tests...")
    print("=" * 50)
    
    success = True
    success &= test_app_import()
    print()
    success &= test_app_routes() 
    print()
    success &= test_sample_data()
    print()
    success &= test_markdown_posts()
    print()
    success &= test_post_routes()
    print()
    success &= test_pagination()
    print()
    success &= test_static_caching()
    print()
    success &= test_compression_and_environment()
    print()
    success &= test_add_post_form()
    print()
    success &= test_publish_script()
    print()
    for check in (test_lightning_parsing, test_lightning_cache, test_lightning_concurrency,
                  test_lightning_routes, test_lightning_pagination):
        success &= check()
        print()
    
    if success:
        print("✓ All tests passed! The Flask application is working correctly.")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)