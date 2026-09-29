FROM nginx:alpine

# Copy static assets and templates
COPY static /usr/share/nginx/html/static
COPY templates /usr/share/nginx/html/templates

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
