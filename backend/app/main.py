from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, analytics, pricing, uploads

app = FastAPI(title="AI Revenue Manager API", version="0.1.0")

# NOTE: restrict allow_origins to your actual frontend URL before going live.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(analytics.router)
app.include_router(pricing.router)
app.include_router(uploads.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
