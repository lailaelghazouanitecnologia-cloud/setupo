import { useState } from "react";
import { Box, Text, Card, Button, Flex, ScrollArea } from "@radix-ui/themes";
import { execProtocol } from "../lib/api";

const EXAMPLE = `# MMS Protocol Example (TOML-like)
# Create a capsule, build it, and start it

[capsule.demo-api]
runtime = "python"
isolation = "container"
entrypoint = "main.py"
deps = ["fastapi", "uvicorn"]
ports = [8080]

[capsule.demo-api.code.main_py]
source = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def root():
    return {"hello": "from MMS"}
"""

[pipeline.demo]
steps = [
    { capsule = "demo-api", action = "build" },
    { capsule = "demo-api", action = "start" },
]`;

export default function Protocol() {
  const [code, setCode] = useState(EXAMPLE);
  const [output, setOutput] = useState("");
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    setOutput("Executing...");
    try {
      const d = await execProtocol(code);
      setOutput(JSON.stringify(d.results, null, 2));
    } catch (e: any) {
      setOutput(`Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box>
      <Text size="5" weight="bold" className="text-[var(--color-accent2)] mb-4 block">
        MMS Protocol
      </Text>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Editor */}
        <Card className="p-0 overflow-hidden">
          <Flex
            justify="between"
            align="center"
            className="px-3 py-2 bg-[var(--color-bg3)] border-b border-[var(--color-border)]"
          >
            <Text size="1" className="text-[var(--color-dim)]">protocol.mms</Text>
            <Button size="1" onClick={run} disabled={loading}>
              {loading ? "Running..." : "Execute"}
            </Button>
          </Flex>
          <textarea
            value={code}
            onChange={(e) => setCode(e.target.value)}
            spellCheck={false}
            className="w-full h-[500px] bg-[var(--color-bg2)] text-[var(--color-text)] font-mono text-xs p-3 outline-none resize-none leading-relaxed border-none"
          />
        </Card>

        {/* Output */}
        <Card className="p-0 overflow-hidden">
          <Box className="px-3 py-2 bg-[var(--color-bg3)] border-b border-[var(--color-border)]">
            <Text size="1" className="text-[var(--color-dim)]">Output</Text>
          </Box>
          <ScrollArea className="h-[500px]">
            <pre className="p-3 font-mono text-xs text-[var(--color-dim)] whitespace-pre-wrap">
              {output || "Click Execute to run the protocol code."}
            </pre>
          </ScrollArea>
        </Card>
      </div>

      <Card className="mt-4">
        <Text size="2" weight="bold" className="text-[var(--color-dim)] mb-2 block">
          Syntax Reference
        </Text>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono text-[var(--color-dim)]">
          <div>
            <p className="text-[var(--color-accent2)] mb-1"># Capsule</p>
            <pre>{`[capsule.name]
runtime = "python"
deps = ["fastapi"]
entrypoint = "main.py"`}</pre>
          </div>
          <div>
            <p className="text-[var(--color-accent2)] mb-1"># Pipeline</p>
            <pre>{`[pipeline.deploy]
steps = [
  { capsule = "api", action = "start" }
]`}</pre>
          </div>
          <div>
            <p className="text-[var(--color-accent2)] mb-1"># Inline Code</p>
            <pre>{`[capsule.x.code.main_py]
source = """
print("hello")
"""`}</pre>
          </div>
          <div>
            <p className="text-[var(--color-accent2)] mb-1"># Instructions</p>
            <pre>{`[instruction]
run = [
  { target = "x", command = "ls" }
]`}</pre>
          </div>
        </div>
      </Card>
    </Box>
  );
}
