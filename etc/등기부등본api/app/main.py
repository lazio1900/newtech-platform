from fastapi import FastAPI

from .routes import router

app = FastAPI(title="등기부등본 발급 서비스", version="0.1.0")
app.include_router(router)


@app.get("/healthz")
def healthz():
    return {"ok": True}
