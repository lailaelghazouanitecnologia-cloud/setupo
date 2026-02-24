# MMS Example: Capsules in different runtimes working together

# Python API
CAPSULE CREATE "api" runtime=python deps=fastapi,uvicorn,httpx

# Node.js frontend
CAPSULE CREATE "frontend" runtime=node

# Shell utility
CAPSULE CREATE "monitor" runtime=shell

# Write the API code
WRITE "api" "main.py" <<<
from fastapi import FastAPI
app = FastAPI()

@app.get("/data")
def get_data():
    return {"items": [1, 2, 3], "source": "python-capsule"}
>>>

# Write the Node frontend
WRITE "frontend" "main.js" <<<
const http = require('http');
const server = http.createServer((req, res) => {
    res.writeHead(200, {'Content-Type': 'text/html'});
    res.end('<h1>MMS Frontend</h1><p>Served from Node.js capsule</p>');
});
server.listen(3000, () => console.log('Frontend on :3000'));
>>>

# Write monitor script
WRITE "monitor" "main.sh" <<<
#!/bin/sh
while true; do
    echo "[$(date)] System load: $(cat /proc/loadavg 2>/dev/null || echo 'N/A')"
    sleep 10
done
>>>

CAPSULE START "api"
CAPSULE START "frontend"
CAPSULE START "monitor"
CAPSULE LIST
