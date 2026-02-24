# MMS - Multi-runtime capsules working together
# Python API + Node frontend + Shell monitor

[capsule.api]
runtime = "python"
deps = ["fastapi", "uvicorn", "httpx"]
entrypoint = "main.py"
ports = [8080]

[capsule.api.code.main_py]
source = '''
from fastapi import FastAPI
app = FastAPI()

@app.get("/data")
def get_data():
    return {"items": [1, 2, 3], "source": "python-capsule"}
'''

[capsule.frontend]
runtime = "node"
entrypoint = "main.js"
ports = [3000]

[capsule.frontend.code.main_js]
source = '''
const http = require("http");
const server = http.createServer((req, res) => {
    res.writeHead(200, {"Content-Type": "text/html"});
    res.end("<h1>MMS Frontend</h1><p>Served from Node.js capsule</p>");
});
server.listen(3000, () => console.log("Frontend on :3000"));
'''

[capsule.monitor]
runtime = "shell"
entrypoint = "main.sh"

[capsule.monitor.code.main_sh]
source = '''
#!/bin/sh
while true; do
    echo "[$(date)] System load: $(cat /proc/loadavg 2>/dev/null || echo N/A)"
    sleep 10
done
'''

[pipeline.start-all]
steps = [
    { capsule = "api", action = "start" },
    { capsule = "frontend", action = "start" },
    { capsule = "monitor", action = "start" },
]

[instruction]
run = [
    { target = "api", command = "pip install requests" },
]
