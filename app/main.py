from fastapi import FastAPI
from .routers import random_data 
from .endpoints import text_utils

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Welcome to Randata! Version: 1.0 - Made in Switzerland - João Barreto"}

app.include_router(random_data.router)
app.include_router(text_utils.router)