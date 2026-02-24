import { useEffect, useState } from "react";
import { Box, Text, Card, Flex, Button, TextField, Select, Badge } from "@radix-ui/themes";
import {
  listEnvironments, createEnvironment, destroyEnvironment,
  type Environment,
} from "../lib/api";

export default function Environments() {
  const [envs, setEnvs] = useState<Environment[]>([]);
  const [name, setName] = useState("");
  const [runtime, setRuntime] = useState("python");
  const [packages, setPackages] = useState("");

  const load = () => listEnvironments().then((d) => setEnvs(d.environments));

  useEffect(() => { load(); }, []);

  const submit = async () => {
    if (!name) return;
    await createEnvironment({
      name,
      runtime,
      packages: packages.split(",").map((p) => p.trim()).filter(Boolean),
    });
    setName(""); setPackages("");
    load();
  };

  return (
    <Box>
      <Text size="5" weight="bold" className="text-[var(--color-accent2)] mb-4 block">
        Environments
      </Text>

      <Card className="mb-4">
        <Text size="2" weight="bold" className="text-[var(--color-dim)] mb-2 block">
          Create Environment
        </Text>
        <Flex gap="2" wrap="wrap">
          <TextField.Root
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="flex-1"
          />
          <Select.Root value={runtime} onValueChange={setRuntime}>
            <Select.Trigger />
            <Select.Content>
              <Select.Item value="python">Python</Select.Item>
              <Select.Item value="node">Node.js</Select.Item>
              <Select.Item value="shell">Shell</Select.Item>
            </Select.Content>
          </Select.Root>
          <TextField.Root
            placeholder="Packages (comma sep)"
            value={packages}
            onChange={(e) => setPackages(e.target.value)}
            className="flex-1"
          />
          <Button onClick={submit} disabled={!name}>Create</Button>
        </Flex>
      </Card>

      <div className="space-y-2">
        {envs.map((env) => (
          <Card key={env.id}>
            <Flex justify="between" align="center">
              <Box>
                <Flex gap="2" align="center">
                  <Text weight="bold">{env.name}</Text>
                  <Badge size="1" color="violet">{env.runtime}</Badge>
                </Flex>
                <Text size="1" className="text-[var(--color-dim)]">
                  {env.id} | packages: {env.packages || "[]"}
                </Text>
              </Box>
              <Button
                size="1" color="red" variant="soft"
                onClick={() => destroyEnvironment(env.id).then(load)}
              >
                Delete
              </Button>
            </Flex>
          </Card>
        ))}
        {envs.length === 0 && (
          <Text size="2" className="text-[var(--color-dim)]">No environments</Text>
        )}
      </div>
    </Box>
  );
}
