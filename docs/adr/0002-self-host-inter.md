# Self-host Inter as the fallback font

Apple platforms use the system font; elsewhere Inter (latin 400, 500, 600, 700 woff2, SIL OFL licence) is served from `haam/static/fonts/`. The CSP already allows `font-src 'self'`, so it is not loosened. Alternative rejected: a Google Fonts link, which would need a CSP change and leaks visitors' requests to a third party.
