# MMS Workspace: default
# This is the default workspace for zarnetti.com

[workspace]
name = "default"
description = "Default MMS workspace"
domain = "zarnetti.com"

[capsule.landing]
runtime = "shell"
entrypoint = "serve.sh"
ports = [80]

[capsule.landing.code.serve_sh]
source = '''
#!/bin/sh
# The landing page is served directly by nginx from /opt/mms/public/
echo "Landing page active at zarnetti.com"
'''
