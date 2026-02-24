# MMS - Pipeline deployment example
# Multiple capsules composed as a pipeline

[capsule.builder]
runtime = "python"
deps = ["build", "wheel"]

[capsule.tester]
runtime = "python"
deps = ["pytest", "httpx"]

[capsule.web]
runtime = "python"
entrypoint = "main.py"
deps = ["fastapi", "uvicorn"]
ports = [8080]

[capsule.web.env]
PORT = "8080"
ENV = "production"

[capsule.web.code.main_py]
source = '''
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def index():
    return {"service": "web", "version": "1.0"}
'''

[pipeline.deploy-flow]
steps = [
    { capsule = "builder", action = "build", command = "python -m build" },
    { capsule = "tester", action = "start", command = "pytest -v" },
    { capsule = "web", action = "start" },
]
