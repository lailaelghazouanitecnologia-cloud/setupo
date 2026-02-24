# MMS Example: Create a FastAPI capsule with inline code

CAPSULE CREATE "hello-api" runtime=python isolation=container deps=fastapi,uvicorn

WRITE "hello-api" "main.py" <<<
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Hello from MMS capsule!"}

@app.get("/health")
def health():
    return {"status": "ok"}
>>>

CAPSULE BUILD "hello-api"
CAPSULE START "hello-api"
CAPSULE LIST
