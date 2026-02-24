import { useEffect, useRef, useState } from "react";
import { Box, Text, Flex, Card, Select, Button } from "@radix-ui/themes";
import { listCapsules, execInCapsule, type Capsule } from "../lib/api";

interface Line {
  type: "cmd" | "stdout" | "stderr" | "info";
  text: string;
}

export default function Terminal() {
  const [capsules, setCapsules] = useState<Capsule[]>([]);
  const [target, setTarget] = useState("");
  const [cmd, setCmd] = useState("");
  const [lines, setLines] = useState<Line[]>([
    { type: "info", text: "MMS Terminal - Select a capsule and run commands" },
  ]);
  const [ws, setWs] = useState<WebSocket | null>(null);
  const outputRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listCapsules("running").then((d) => setCapsules(d.capsules));
  }, []);

  useEffect(() => {
    outputRef.current?.scrollTo(0, outputRef.current.scrollHeight);
  }, [lines]);

  const addLine = (line: Line) => setLines((prev) => [...prev, line]);

  const exec = async () => {
    if (!cmd.trim() || !target) return;
    addLine({ type: "cmd", text: `$ ${cmd}` });
    const input = cmd;
    setCmd("");

    try {
      const { result } = await execInCapsule(target, input);
      if (result.stdout) addLine({ type: "stdout", text: result.stdout });
      if (result.stderr) addLine({ type: "stderr", text: result.stderr });
      if (result.error) addLine({ type: "stderr", text: result.error });
    } catch (e: any) {
      addLine({ type: "stderr", text: e.message });
    }
  };

  const connectWs = () => {
    if (!target) return;
    if (ws) ws.close();
    const token = localStorage.getItem("mms_token") || "";
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(
      `${proto}//${location.host}/ws/terminal/${target}?token=${token}`
    );
    socket.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === "output") {
        if (data.stdout) addLine({ type: "stdout", text: data.stdout });
        if (data.stderr) addLine({ type: "stderr", text: data.stderr });
      } else if (data.type === "connected") {
        addLine({ type: "info", text: data.data });
      }
    };
    socket.onclose = () => addLine({ type: "info", text: "WebSocket disconnected" });
    setWs(socket);
    addLine({ type: "info", text: "Connecting via WebSocket..." });
  };

  const COLOR: Record<string, string> = {
    cmd: "text-green-400",
    stdout: "text-[var(--color-text)]",
    stderr: "text-red-400",
    info: "text-[var(--color-accent2)]",
  };

  return (
    <Box>
      <Text size="5" weight="bold" className="text-[var(--color-accent2)] mb-4 block">
        Terminal
      </Text>

      <Card className="overflow-hidden p-0">
        {/* Header */}
        <Flex gap="2" align="center" className="p-2 bg-[var(--color-bg3)] border-b border-[var(--color-border)]">
          <Select.Root value={target} onValueChange={setTarget}>
            <Select.Trigger placeholder="Select capsule..." className="w-48" />
            <Select.Content>
              {capsules.map((c) => (
                <Select.Item key={c.id} value={c.id}>
                  {c.name} ({c.id.slice(0, 6)})
                </Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
          <Button size="1" variant="soft" onClick={connectWs} disabled={!target}>
            WebSocket
          </Button>
          <Button
            size="1"
            variant="soft"
            color="red"
            onClick={() => setLines([{ type: "info", text: "Cleared" }])}
          >
            Clear
          </Button>
        </Flex>

        {/* Output */}
        <div
          ref={outputRef}
          className="h-96 overflow-y-auto p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap"
        >
          {lines.map((l, i) => (
            <div key={i} className={COLOR[l.type] || ""}>{l.text}</div>
          ))}
        </div>

        {/* Input */}
        <form
          onSubmit={(e) => { e.preventDefault(); exec(); }}
          className="flex border-t border-[var(--color-border)]"
        >
          <span className="px-3 py-2 text-green-400 font-bold font-mono">$</span>
          <input
            value={cmd}
            onChange={(e) => setCmd(e.target.value)}
            placeholder="command..."
            autoComplete="off"
            className="flex-1 bg-transparent text-[var(--color-text)] font-mono text-sm px-2 py-2 outline-none"
          />
        </form>
      </Card>
    </Box>
  );
}
