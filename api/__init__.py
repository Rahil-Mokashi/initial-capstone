"""Local HTTP API for the Electron front end.

A thin layer over the existing services in `app/`: routers parse the
request, call the same service method the Qt window calls, and serialize
the result. Business rules, rounding and permission checks stay in
`app/services`. See docs/adr-js-frontend.md.
"""
