# MMS - Hello API example
# Creates a FastAPI capsule with inline code

[capsule.hello-api]
runtime = "python"
isolation = "container"
entrypoint = "main.py"
deps = ["fastapi", "uvicorn"]
ports = [8080]

[capsule.hello-api.env]
PORT = "8080"

[capsule.hello-api.code.main_py]
source = '''
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Hello from MMS capsule!", "service": "hello-api"}

@app.get("/health")
def health():
    return {"status": "ok"}
'''

[pipeline.start]
steps = [
    { capsule = "hello-api", action = "build" },
    { capsule = "hello-api", action = "start" },
]
