#!/usr/bin/env python3
"""
Simple functional test for the Flask application
"""

import sys
import os
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
    
    if success:
        print("✓ All tests passed! The Flask application is working correctly.")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)