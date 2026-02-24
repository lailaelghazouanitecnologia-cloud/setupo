# MMS Workspace: default
# Root workspace for zarnetti.com

[workspace]
name = "default"
description = "Main workspace for zarnetti.com"
domain = "zarnetti.com"
root = "workspaces/default"

# The landing page capsule
[capsule.landing]
runtime = "static"
entrypoint = "public/index.html"
ports = [80, 443]
