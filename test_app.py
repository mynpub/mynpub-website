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
from pathlib import Path
from unittest.mock import patch
from flask import Flask

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
    """Test that sample data is initialized"""
    try:
        from app import blog_posts, resources
        
        if len(blog_posts) > 0:
            print("✓ Sample blog posts loaded")
        else:
            print("✗ No blog posts found")
            
        if len(resources) > 0:
            print("✓ Sample resources loaded")
        else:
            print("✗ No resources found")
            
        return True
            
    except Exception as e:
        print(f"✗ Sample data test failed: {e}")
        return False

def test_pagination():
    """Test page boundaries, navigation, and invalid page parameters."""
    try:
        import app
        posts = [
            {'id': i, 'title': f'Post {i}', 'date': '2026-10-20', 'summary': 'Summary'}
            for i in range(1, 22)
        ]
        with patch.object(app, 'blog_posts', posts), app.app.test_client() as client:
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
        for count in (0, 10, 11, 20):
            with patch.object(app, 'blog_posts', posts[:count]), app.app.test_client() as client:
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
            }
            with patch.dict(os.environ, environment), patch.object(Flask, 'run') as run:
                namespace = runpy.run_path(str(Path(__file__).with_name('app.py')), run_name='__main__')
                configured_app = namespace['app']
                assert configured_app.debug == enabled
                assert configured_app.config['COMPRESS_ENABLED'] == enabled
                run.assert_called_once_with(host='127.0.0.2', port=5050)
                with configured_app.test_client() as client:
                    response = client.get('/', headers={'Accept-Encoding': 'gzip'})
                    assert (response.headers.get('Content-Encoding') == 'gzip') == enabled
        with patch.dict(os.environ):
            os.environ.pop('DEBUG', None)
            os.environ.pop('COMPRESS_ENABLED', None)
            with patch.object(Flask, 'run') as run:
                namespace = runpy.run_path(str(Path(__file__).with_name('app.py')))
                assert not namespace['app'].debug
                assert namespace['app'].config['COMPRESS_ENABLED']
                run.assert_not_called()
        print("✓ Compression and environment configuration work")
        return True
    except Exception as e:
        print(f"✗ Compression/environment test failed: {e}")
        return False

def test_add_post_form():
    """Test the previously missing GET form and existing submission path."""
    try:
        import app
        with patch.object(app, 'blog_posts', []), app.app.test_client() as client:
            response = client.get('/admin/add-post')
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert 'method="post" action="/admin/add-post"' in html
            for field in ('title', 'date', 'content'):
                assert f'name="{field}"' in html
                assert f'for="{field}"' in html
            assert 'type="submit"' in html
            response = client.post('/admin/add-post', data={
                'title': 'New post', 'date': '2026-10-20', 'content': 'Post content',
            })
            assert response.status_code == 200
            assert b'Blog post added successfully!' in response.data
            assert b'New post' in client.get('/').data
            assert client.get('/post/1').status_code == 200
        print("✓ Add-post form and submission render correctly")
        return True
    except Exception as e:
        print(f"✗ Add-post form test failed: {e}")
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
    success &= test_pagination()
    print()
    success &= test_static_caching()
    print()
    success &= test_compression_and_environment()
    print()
    success &= test_add_post_form()
    print()
    
    if success:
        print("✓ All tests passed! The Flask application is working correctly.")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)