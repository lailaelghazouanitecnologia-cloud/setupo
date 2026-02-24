import { useEffect, useState } from "react";
import { Box, Text, Flex, Card, Badge, Table } from "@radix-ui/themes";
import { getHealth, listCapsules, type Capsule } from "../lib/api";

interface Stats {
  capsules_total: number;
  capsules_running: number;
  environments: number;
  pipelines: number;
  docker_available: boolean;
  disk_free_gb: number;
  disk_total_gb: number;
}

const STATE_COLOR: Record<string, "green" | "red" | "orange" | "blue" | "gray"> = {
  running: "green",
  stopped: "red",
  error: "red",
  ready: "blue",
  building: "orange",
  created: "gray",
};

export default function Overview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [capsules, setCapsules] = useState<Capsule[]>([]);

  useEffect(() => {
    const load = () => {
      getHealth().then((d: any) => setStats(d));
      listCapsules().then((d) => setCapsules(d.capsules));
    };
    load();
    const id = setInterval(load, 8000);
    return () => clearInterval(id);
  }, []);

  return (
    <Box>
      <Text size="5" weight="bold" className="text-[var(--color-accent2)] mb-4 block">
        Dashboard
      </Text>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <StatCard label="Capsules" value={stats?.capsules_total ?? 0} />
        <StatCard label="Running" value={stats?.capsules_running ?? 0} />
        <StatCard label="Environments" value={stats?.environments ?? 0} />
        <StatCard label="Disk Free" value={`${stats?.disk_free_gb ?? "-"} GB`} />
      </div>

      {/* System info */}
      <div className="grid grid-cols-2 gap-3 mb-6">
        <Card>
          <Flex gap="2" align="center">
            <Text size="2" className="text-[var(--color-dim)]">Docker:</Text>
            <Badge color={stats?.docker_available ? "green" : "red"} size="1">
              {stats?.docker_available ? "Available" : "Not available"}
            </Badge>
          </Flex>
        </Card>
        <Card>
          <Flex gap="2" align="center">
            <Text size="2" className="text-[var(--color-dim)]">Disk:</Text>
            <Text size="2">
              {stats?.disk_free_gb ?? "?"} / {stats?.disk_total_gb ?? "?"} GB
            </Text>
          </Flex>
        </Card>
      </div>

      {/* Capsules table */}
      <Card>
        <Text size="3" weight="bold" className="mb-3 block text-[var(--color-dim)]">
          All Capsules
        </Text>
        {capsules.length === 0 ? (
          <Text size="2" className="text-[var(--color-dim)]">
            No capsules yet. Create one in the Capsules tab.
          </Text>
        ) : (
          <Table.Root variant="surface">
            <Table.Header>
              <Table.Row>
                <Table.ColumnHeaderCell>ID</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell>Name</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell>Runtime</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell>State</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell>IP</Table.ColumnHeaderCell>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {capsules.map((c) => (
                <Table.Row key={c.id}>
                  <Table.Cell>
                    <code className="text-xs">{c.id}</code>
                  </Table.Cell>
                  <Table.Cell>{c.name}</Table.Cell>
                  <Table.Cell>{c.manifest.runtime}</Table.Cell>
                  <Table.Cell>
                    <Badge color={STATE_COLOR[c.state] ?? "gray"} size="1">
                      {c.state}
                    </Badge>
                  </Table.Cell>
                  <Table.Cell>
                    <code className="text-xs">{c.ip || "-"}</code>
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table.Root>
        )}
      </Card>
    </Box>
  );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <Card>
      <Flex direction="column" align="center" gap="1">
        <Text size="6" weight="bold" className="text-[var(--color-accent2)]">
          {value}
        </Text>
        <Text size="1" className="text-[var(--color-dim)]">
          {label}
        </Text>
      </Flex>
    </Card>
  );
}
