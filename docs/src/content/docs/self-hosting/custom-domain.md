---
title: Custom domain and Cloudflare
description: Serving your instance on your own domain, optionally through Cloudflare.
---

## Your own domain

1. In Render, add the domain to the service (**Settings → Custom Domains**) and follow its
   DNS instructions: usually a `CNAME` record pointing at your `….onrender.com` address.
2. Once Render shows the certificate as issued, set `PUBLIC_BASE_URL` to the new address,
   and add `<new address>/auth/callback` to the Google OAuth client's redirect URIs.

Requests to any other host, including the `….onrender.com` address, are then redirected
to `PUBLIC_BASE_URL`.

## Behind Cloudflare (optional)

If the domain's DNS is on Cloudflare, you can proxy it (the orange cloud):

- **Encryption:** set the SSL/TLS mode for this hostname to **Full (strict)**, for
  example with a Configuration Rule. Anything weaker leaves the hop to Render unverified.
- **Scanner noise:** as soon as a certificate is issued, scanners that watch the public
  certificate logs start probing for files like `/.env`. Nothing leaks (the app never
  serves them), but every probe reaches the app and can wake it. A free WAF custom rule
  stops them at Cloudflare. Under **Security → Security rules**, create a custom rule with
  the action **Block**, using your hostname:

  ```
  (http.host eq "jobs.example.com" and (
    (http.request.uri.path contains "/." and not starts_with(http.request.uri.path, "/.well-known/"))
    or starts_with(http.request.uri.path, "/wp-")
    or ends_with(http.request.uri.path, ".php")
    or starts_with(http.request.uri.path, "/cgi-bin/")
  ))
  ```

  Keep `/.well-known/` open: certificate renewal uses it.
