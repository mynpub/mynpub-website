from flask import Flask, render_template, request
import markdown
import os

app = Flask(__name__)

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

# Simple in-memory storage for blog posts, mailing list subscribers, and resources
blog_posts = []
mailing_list_subscribers = []
resources = []

def init_sample_data():
    global blog_posts, resources

    # Sample blog posts - this includes the initial markdown content
    blog_posts = [
        {
            'id': 1,
            'title': 'Welcome to My Personal Website',
            'date': '2026-10-19',
            'summary': 'This is my first post explaining the purpose of this website.',
            'content': '# Welcome\n\nThis is a **personal website** featuring:\n\n- A blog with technical content\n- Mailing list signup\n- Lightning network explorer\n- Helpful resources\n\nStay tuned for updates!'
        },
        {
            'id': 2,
            'title': 'Introduction to Flask Web Development',
            'date': '2026-10-18',
            'summary': 'Exploring the power of Python Flask for web development.',
            'content': '# Flask Web Development\n\nFlask is a powerful Python microframework that makes it easy to build web applications.\n\n## Key Features\n\n- Simple routing system\n- Template engine support\n- Easy database integration\n- Extensible with extensions'
        }
    ]

    # Process all markdown content for blog posts at startup
    for post in blog_posts:
        post['content'] = render_markdown(post['content'])
    
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
    return render_template('index.html',
                         posts=blog_posts,
                         config=SITE_CONFIG)

@app.route('/post/<int:post_id>')
def post(post_id):
    post = next((p for p in blog_posts if p['id'] == post_id), None)
    if post:
        return render_template('post.html', post=post, config=SITE_CONFIG)
    else:
        return "Post not found", 404

@app.route('/lightning-explorer')
def lightning_explorer():
    # Here you would integrate with your actual Lightning node
    # For now, we'll show a placeholder page
    return render_template('lightning.html', config=SITE_CONFIG)

@app.route('/resources')
def resources_page():
    return render_template('resources.html', resources=resources, config=SITE_CONFIG)

# Additional route for adding new blog posts (admin functionality)
@app.route('/admin/add-post', methods=['GET', 'POST'])
def add_post():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        date = request.form.get('date')

        if title and content:
            new_id = len(blog_posts) + 1
            blog_posts.append({
                'id': new_id,
                'title': title,
                'date': date,
                'summary': content[:100] + '...',  # First 100 characters as summary
                'content': content
            })
            return render_template('success.html', message='Blog post added successfully!', config=SITE_CONFIG)
        else:
            return render_template('error.html', message='Please provide both title and content.', config=SITE_CONFIG)

    return render_template('add_post.html', config=SITE_CONFIG)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)