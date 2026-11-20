# nginx

nginx doesn't set the forwarded headers by itself, and `X-Forwarded-For` must be set so a visitor can't add to it. `$remote_addr` replaces whatever the visitor sent.

`/etc/nginx/conf.d/mealwright.conf`:

```nginx
server {
    listen 80;
    server_name mealwright.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    http2 on;
    server_name mealwright.example.com;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;

    location / {
        proxy_pass http://mealwright:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }
}
```

Use your real certificate (Let's Encrypt with certbot, or your own). Run nginx in the same compose file as `compose.example.yaml` (or join its network as an external one), so it is inside the fixed network `172.28.10.0/24` that `MEALWRIGHT_TRUSTED_PROXIES` already names there. If nginx is somewhere else, set `MEALWRIGHT_TRUSTED_PROXIES` to nginx's own address (for example `192.0.2.10`) instead.

Don't publish Mealwright's port 8080. Mealwright sends `X-Accel-Buffering: no` on its live-updates stream, so nginx's buffering needs no change.

**Tested:** `scripts/test-proxies.sh nginx` (nginx 1.28, self-signed certificate, this exact `location` block): HTTPS answers, sign-in sets the `__Host-` cookie, Mealwright logs the visitor's address (not nginx's), the right host name is seen, and no "not trusted" warning.
