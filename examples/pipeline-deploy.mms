# MMS Example: Multi-step pipeline

# Create capsules
CAPSULE CREATE "builder" runtime=python deps=build,wheel
CAPSULE CREATE "tester" runtime=python deps=pytest,httpx
CAPSULE CREATE "web" runtime=python deps=fastapi,uvicorn

# Write code
WRITE "web" "main.py" <<<
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def index():
    return {"service": "web", "version": "1.0"}
>>>

# Run as pipeline
PIPELINE "deploy-flow" {
    STEP "build" capsule="builder" command="python -m build"
    STEP "test" capsule="tester" command="pytest -v"
    STEP "serve" capsule="web" command="uvicorn main:app --host 0.0.0.0 --port 8080"
}
