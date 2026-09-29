# Hospital Queue Management System - Frontend

This folder contains the UI templates, stylesheets, JavaScript, and static media files for the Hospital Queue Management System.

## Directory Structure

```
frontend/
├── templates/         # Jinja2 HTML templates
│   ├── admin/
│   ├── payment/
│   ├── base.html
│   ├── index.html
│   └── ...
├── static/            # CSS, JavaScript, Images
│   ├── css/
│   ├── js/
│   └── images/
├── Dockerfile         # Nginx container setup
├── nginx.conf         # Nginx reverse proxy configuration
└── package.json       # Optional frontend runner configuration
```

## Deployment Options

### Option 1: Docker (Nginx)
```bash
docker build -t hospital-queue-frontend .
docker run -d -p 80:80 --name frontend hospital-queue-frontend
```

### Option 2: CDN / Static Web Host (Vercel, Netlify, Cloudflare Pages)
Upload the `static/` and template assets or serve them via CDN configured to proxy API requests to the Flask backend.
