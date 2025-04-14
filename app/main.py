from fastapi import FastAPI
from .routers import random_data

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Welcome to Randata!"}

app.include_router(random_data.router)