import { useState } from "react";
import { Box, Text, TextField, Button, Flex, Card } from "@radix-ui/themes";

export default function Login({ onLogin }: { onLogin: (token: string) => void }) {
  const [token, setToken] = useState("");

  return (
    <Flex align="center" justify="center" className="h-screen bg-[var(--color-bg)]">
      <Card size="3" className="w-96">
        <Flex direction="column" gap="4" align="center">
          <Text size="7" weight="bold" className="text-[var(--color-accent2)] tracking-widest">
            mms
          </Text>
          <Text size="2" className="text-[var(--color-dim)]">
            micro module system
          </Text>
          <Box className="w-full">
            <TextField.Root
              placeholder="API Token"
              size="3"
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && token && onLogin(token)}
            />
          </Box>
          <Button
            size="3"
            className="w-full"
            disabled={!token}
            onClick={() => onLogin(token)}
          >
            Connect
          </Button>
          <Text size="1" className="text-[var(--color-dim)]">
            Token is generated at boot time in /etc/mms/token
          </Text>
        </Flex>
      </Card>
    </Flex>
  );
}
