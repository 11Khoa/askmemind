from fastapi import FastAPI

from app import models
from app.routers import auth, chat

app = FastAPI()

app.include_router(auth.router)
app.include_router(chat.router)
