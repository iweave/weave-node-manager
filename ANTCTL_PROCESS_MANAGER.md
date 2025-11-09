# antctl
In the file ANTCTL_README.md is the README.md for the the Autonomi antctl tool.

We want to plan on integrating antctl as a new progress manager.

`antup` installation has been covered for installing `antnode`, the same process `antup antctl` will install antctl in ~/.local/bin/

There is a lot of similarity in the ways antctl manages nodes and supports report formats that are similar to what we already built.

for now, completely ignore --peer. --peer and local networks are beyond the current scope of this project.

our current executor is built around singular atomic operations, so other than teardown, (which is allowed to magically clean up the cluster before we delete all nodes from the database), we'll focus on adding one node at a time with --count 1 and using --service-name to address each process (start/stop/remove/upgrade) that we do.

in our current codebase, we choose the nodename and node number. with antctl, antctl decides what the node name/numbers are (creating holes that can't be filled later if nodes are removed until reset/teardown) and which directories the node binary, node path and log path (although I think we can override the default paths if we want)

Help me plan how to implement antctl. feel free to ask questions for clarity.

