from fastapi import FastAPI

from app import models
from app.routers import auth, chat, document, upload

app = FastAPI()

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(upload.router)
app.include_router(document.router)
