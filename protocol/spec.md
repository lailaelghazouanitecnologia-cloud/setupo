# Setupo Protocol Specification v0.1

## Overview

The Setupo Protocol is a domain-specific language (DSL) for orchestrating VMs and MicroVMs. It provides a simple, declarative syntax for creating, managing, and connecting instances.

## Syntax

```
# Comments start with #

# Create instances
CREATE microvm "worker-1" vcpus=2 memory=512
CREATE vm "database" vcpus=4 memory=2048 disk=8192

# Execute commands
EXEC "worker-1" run "apt update"

# Capsule management
CAPSULE "worker-1" load "nginx-proxy"

# Instance lifecycle
STOP "worker-1"
START "worker-1"
DESTROY "worker-1"
INFO "worker-1"

# Listing
LIST microvms
LIST vms

# Networking
CONNECT "worker-1" -> "worker-2" port=8080

# SSH to external systems
SSH "user@host" run "uptime"

# Piping between instances
PIPE "worker-1" exec "cat /data" -> "worker-2" exec "tee /import"
```

## Types

| Type     | Value Format          |
|----------|-----------------------|
| STRING   | `"double quoted"`     |
| NUMBER   | `123`                 |
| IDENT    | `word-with-dashes`    |
| KEYWORD  | `CREATE`, `EXEC`, ... |

## Commands

### CREATE
Create a new VM or MicroVM.
```
CREATE <type> "<name>" [key=value ...]
```
- `type`: `microvm` or `vm`
- Params: `vcpus`, `memory`, `disk`

### EXEC
Execute a command on an instance.
```
EXEC "<target>" run "<command>"
```

### CAPSULE
Load a capsule plugin into an instance.
```
CAPSULE "<target>" load "<capsule-name>"
```

### CONNECT
Create a network connection between instances.
```
CONNECT "<source>" -> "<dest>" [port=N]
```

### PIPE
Pipe output from one instance's command to another.
```
PIPE "<src>" exec "<cmd>" -> "<dest>" exec "<cmd>"
```

### SSH
Execute on external host via SSH (from base).
```
SSH "<user@host>" run "<command>"
```

## API Endpoint

Send protocol code via the API:
```bash
curl -X POST https://zarnetti.com/api/commands/protocol \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"code": "CREATE microvm \"web\" vcpus=1 memory=256"}'
```
