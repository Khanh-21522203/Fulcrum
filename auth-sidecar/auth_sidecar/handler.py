# ext_authz HTTP API contract (envoy.service.auth.v3.Authorization):
#
# Envoy sends POST / with a JSON body (CheckRequest):
#   {
#     "attributes": {
#       "request": {
#         "http": {
#           "method": "GET",
#           "headers": { "authorization": "Bearer <token>", ... },
#           "path": "/api/resource",
#           ...
#         }
#       }
#     }
#   }
#
# Response:
#   200 → Envoy forwards the request upstream
#   403 → Envoy rejects the request; body/headers from CheckResponse are returned to the client

from fastapi import Request, Response


async def check(request: Request) -> Response:
    # TODO: extract Authorization header from request body
    # TODO: validate JWT or API key against configured policy
    # TODO: return 200 (allow) with injected headers, or 403 (deny)
    raise NotImplementedError
