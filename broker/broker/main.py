import uvicorn
from fastapi import FastAPI
from broker.api import catalog, instances

app = FastAPI(title="Fulcrum Service Broker")
app.include_router(catalog.router, prefix="/v2")
app.include_router(instances.router, prefix="/v2")

if __name__ == "__main__":
    uvicorn.run("broker.main:app", host="0.0.0.0", port=8080, reload=False)
