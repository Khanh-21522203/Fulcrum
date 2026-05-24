import uvicorn
from fastapi import FastAPI
from auth_sidecar.handler import check

app = FastAPI(title="Fulcrum Auth Sidecar")
app.add_api_route("/", check, methods=["POST"])

if __name__ == "__main__":
    uvicorn.run("auth_sidecar.main:app", host="127.0.0.1", port=9191, reload=False)
