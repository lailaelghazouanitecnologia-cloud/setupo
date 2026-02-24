import { useEffect, useState } from "react";
import {
  Box, Text, Card, Flex, Badge, Button, TextField, TextArea,
  Select, Dialog, ScrollArea,
} from "@radix-ui/themes";
import {
  listCapsules, createCapsule, startCapsule, stopCapsule,
  destroyCapsule, getCapsuleLogs, type Capsule, type LogEntry,
} from "../lib/api";

const STATE_COLOR: Record<string, "green" | "red" | "orange" | "blue" | "gray"> = {
  running: "green", stopped: "red", error: "red",
  ready: "blue", building: "orange", created: "gray",
};

export default function Capsules() {
  const [capsules, setCapsules] = useState<Capsule[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [logCapsule, setLogCapsule] = useState("");

  const load = () => listCapsules().then((d) => setCapsules(d.capsules));

  useEffect(() => {
    load();
    const id = setInterval(load, 6000);
    return () => clearInterval(id);
  }, []);

  const viewLogs = async (id: string) => {
    setLogCapsule(id);
    const d = await getCapsuleLogs(id);
    setLogs(d.logs);
  };

  return (
    <Box>
      <Flex justify="between" align="center" className="mb-4">
        <Text size="5" weight="bold" className="text-[var(--color-accent2)]">
          Capsules
        </Text>
        <Button onClick={() => setShowCreate(true)}>+ Create Capsule</Button>
      </Flex>

      {/* Create dialog */}
      <CreateDialog open={showCreate} onClose={() => setShowCreate(false)} onCreated={load} />

      {/* Logs dialog */}
      <Dialog.Root open={!!logCapsule} onOpenChange={() => setLogCapsule("")}>
        <Dialog.Content maxWidth="600px">
          <Dialog.Title>Logs: {logCapsule}</Dialog.Title>
          <ScrollArea className="h-64">
            <Box className="font-mono text-xs space-y-1">
              {logs.map((l, i) => (
                <div key={i} className={l.level === "error" ? "text-red-400" : "text-[var(--color-dim)]"}>
                  <span className="opacity-50">{l.created_at}</span> {l.message}
                </div>
              ))}
              {logs.length === 0 && <Text size="1" className="text-[var(--color-dim)]">No logs</Text>}
            </Box>
          </ScrollArea>
        </Dialog.Content>
      </Dialog.Root>

      {/* Capsule grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {capsules.map((c) => (
          <Card key={c.id}>
            <Flex justify="between" align="start">
              <Box>
                <Flex gap="2" align="center" className="mb-1">
                  <Text weight="bold">{c.name}</Text>
                  <Badge color={STATE_COLOR[c.state] ?? "gray"} size="1">{c.state}</Badge>
                </Flex>
                <Text size="1" className="text-[var(--color-dim)] block">
                  {c.id} | {c.manifest.runtime} | {c.manifest.isolation}
                </Text>
                {c.ip && (
                  <Text size="1" className="text-[var(--color-dim)] block">
                    IP: {c.ip}
                  </Text>
                )}
                {c.error && (
                  <Text size="1" color="red" className="block mt-1">{c.error}</Text>
                )}
              </Box>
              <Flex gap="1">
                {c.state !== "running" && (
                  <Button size="1" onClick={() => startCapsule(c.id).then(load)}>
                    Start
                  </Button>
                )}
                {c.state === "running" && (
                  <Button size="1" color="orange" onClick={() => stopCapsule(c.id).then(load)}>
                    Stop
                  </Button>
                )}
                <Button size="1" variant="soft" onClick={() => viewLogs(c.id)}>
                  Logs
                </Button>
                <Button size="1" color="red" variant="soft" onClick={() => {
                  if (confirm("Destroy this capsule?")) destroyCapsule(c.id).then(load);
                }}>
                  Destroy
                </Button>
              </Flex>
            </Flex>
          </Card>
        ))}
        {capsules.length === 0 && (
          <Text size="2" className="text-[var(--color-dim)] col-span-2">
            No capsules. Click "Create Capsule" to get started.
          </Text>
        )}
      </div>
    </Box>
  );
}

function CreateDialog({
  open, onClose, onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [runtime, setRuntime] = useState("python");
  const [isolation, setIsolation] = useState("container");
  const [entrypoint, setEntrypoint] = useState("main.py");
  const [deps, setDeps] = useState("");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setLoading(true);
    try {
      await createCapsule({
        name,
        runtime,
        isolation,
        entrypoint,
        code: code || undefined,
        dependencies: deps.split(",").map((d) => d.trim()).filter(Boolean),
      });
      onCreated();
      onClose();
      setName(""); setCode(""); setDeps("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onClose}>
      <Dialog.Content maxWidth="550px">
        <Dialog.Title>Create Capsule</Dialog.Title>
        <Flex direction="column" gap="3" className="mt-3">
          <TextField.Root placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <Flex gap="2">
            <Select.Root value={runtime} onValueChange={setRuntime}>
              <Select.Trigger placeholder="Runtime" />
              <Select.Content>
                <Select.Item value="python">Python</Select.Item>
                <Select.Item value="node">Node.js</Select.Item>
                <Select.Item value="shell">Shell</Select.Item>
                <Select.Item value="go">Go</Select.Item>
                <Select.Item value="rust">Rust</Select.Item>
              </Select.Content>
            </Select.Root>
            <Select.Root value={isolation} onValueChange={setIsolation}>
              <Select.Trigger placeholder="Isolation" />
              <Select.Content>
                <Select.Item value="container">Container</Select.Item>
                <Select.Item value="venv">Venv</Select.Item>
                <Select.Item value="none">None</Select.Item>
              </Select.Content>
            </Select.Root>
          </Flex>
          <TextField.Root
            placeholder="Entrypoint (main.py)"
            value={entrypoint}
            onChange={(e) => setEntrypoint(e.target.value)}
          />
          <TextField.Root
            placeholder="Dependencies (comma sep): fastapi, uvicorn"
            value={deps}
            onChange={(e) => setDeps(e.target.value)}
          />
          <TextArea
            placeholder="# Paste your code here..."
            rows={10}
            className="font-mono text-sm"
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          <Flex gap="2" justify="end">
            <Button variant="soft" onClick={onClose}>Cancel</Button>
            <Button disabled={!name || loading} onClick={submit}>
              {loading ? "Creating..." : "Create"}
            </Button>
          </Flex>
        </Flex>
      </Dialog.Content>
    </Dialog.Root>
  );
}
