import { useState } from "react";
import { Box, Text, TextField, Button, Flex, Card, Callout } from "@radix-ui/themes";
import { login } from "../lib/api";

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    if (!email || !password) return;
    setLoading(true);
    setError("");
    try {
      await login(email, password);
      onLogin();
    } catch (e: any) {
      setError(e.message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

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

          {error && (
            <Callout.Root color="red" size="1" className="w-full">
              <Callout.Text>{error}</Callout.Text>
            </Callout.Root>
          )}

          <Box className="w-full">
            <Text size="1" className="text-[var(--color-dim)] mb-1 block">Email</Text>
            <TextField.Root
              placeholder="email@example.com"
              size="3"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
            />
          </Box>

          <Box className="w-full">
            <Text size="1" className="text-[var(--color-dim)] mb-1 block">Password</Text>
            <TextField.Root
              placeholder="Password"
              size="3"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
            />
          </Box>

          <Button
            size="3"
            className="w-full"
            disabled={!email || !password || loading}
            onClick={handleLogin}
          >
            {loading ? "Signing in..." : "Sign In"}
          </Button>
        </Flex>
      </Card>
    </Flex>
  );
}
