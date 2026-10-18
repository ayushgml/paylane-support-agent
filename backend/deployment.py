"""Railway entrypoint: accept API traffic only through the configured Vercel proxy."""
import hmac
import os
from urllib.parse import urlsplit
from fastapi.responses import JSONResponse
from paylane.server import create_app


def create_hosted_app(base_app=None):
    secret = os.getenv('PAYLANE_ORIGIN_SECRET', '')
    public_origin = os.getenv('PAYLANE_PUBLIC_ORIGIN', '').rstrip('/')
    parsed = urlsplit(public_origin)
    if (
        len(secret) < 32 or parsed.scheme != 'https' or not parsed.netloc
        or parsed.path or parsed.query or parsed.fragment or parsed.username
        or parsed.password
    ):
        raise ValueError('deployment_configuration_required')
    live = os.getenv('PAYLANE_READ_ONLY', 'false').lower() != 'true'
    if live and not os.getenv('PAYLANE_DEMO_INVITE'):
        raise ValueError('deployment_admission_required')
    application = base_app if base_app is not None else create_app(hosted=True, live_enabled=live)

    @application.middleware('http')
    async def trusted_proxy(request, call_next):
        if request.method == 'GET' and request.url.path == '/api/health':
            return await call_next(request)
        supplied = request.headers.get('x-paylane-origin-secret', '')
        if not supplied or not hmac.compare_digest(secret.encode(), supplied.encode()):
            return JSONResponse({'detail':'proxy_required'}, status_code=403, headers={'Cache-Control':'no-store'})
        origin = request.headers.get('origin')
        if origin and origin != public_origin:
            return JSONResponse({'detail':'origin_not_allowed'}, status_code=403, headers={'Cache-Control':'no-store'})
        # The proxy is authenticated first; the canonical host comes only from
        # server configuration, never arbitrary X-Forwarded-Host input.
        request.scope['headers'] = [
            (key, value) for key, value in request.scope['headers']
            if key.lower() not in {b'host', b'x-paylane-origin-secret'}
        ] + [(b'host', parsed.netloc.encode())]
        request.scope['scheme'] = 'https'
        return await call_next(request)

    return application
