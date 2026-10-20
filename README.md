# My Personal Website

This is a Flask-based personal website with the following features:

## Features

1. **Blog Section** - Main landing page showing latest blog posts with individual post pages
2. **Mailing List Signup** - GNU Mailman integration for collecting email subscribers
3. **Lightning Network Explorer** - Page for accessing your Lightning node information
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

This remains a demo with in-memory storage: changes disappear on restart
and are not shared between workers. The `/admin/add-post` endpoint has no
authentication or CSRF protection; restrict access at the reverse proxy
and add authentication, CSRF protection, and content sanitization before
exposing it publicly.

### Tests

```bash
python test_app.py
```

## Adding New Pages

To add new pages to your website:

1. Create a new route in `app.py`
2. Create a new HTML template in `/templates/`
3. Add the navigation link in the base template (`templates/base.html`)

## Adding Content

### Blog Posts
Blog posts are managed directly in the `app.py` file for this simple implementation. In a production environment, you might consider:
- Using a database to store blog posts
- Implementing a content management system
- Separating content files (e.g., markdown files in a directory)

### Resources Section
Resources are added directly to the resources list in `app.py`.