from fastapi import APIRouter

router = APIRouter()

_CATALOG = {
    "services": [
        {
            "id": "f8ccf060-3b28-4e8b-a9f5-00000000cafe",
            "name": "load-balancer",
            "description": "Self-service edge load balancing via Envoy",
            "bindable": False,
            "plans": [
                {
                    "id": "a1b2c3d4-0000-0000-0000-000000000001",
                    "name": "standard",
                    "description": "Single-region, TLS termination, basic routing",
                }
            ],
        }
    ]
}


@router.get("/catalog")
async def get_catalog() -> dict:
    return _CATALOG
