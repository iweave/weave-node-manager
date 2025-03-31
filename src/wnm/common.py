# Primary node for want of one
QUEEN = 1

# Donation address, default to faucet vault, can be overridden in config
DONATE = "0x00455d78f850b0358E8cea5be24d415E01E107CF"
# Keep these as strings so they can be grepped in logs
STOPPED = "STOPPED"  # 0 Node is not responding to it's metrics port
RUNNING = "RUNNING"  # 1 Node is responding to it's metrics port
UPGRADING = "UPGRADING"  # 2 Upgrade in progress
DISABLED = "DISABLED"  # -1 Do not start
RESTARTING = "RESTARTING"  # 3 re/starting a server intionally
MIGRATING = "MIGRATING"  # 4 Moving volumes in progress
REMOVING = "REMOVING"  # 5 Removing node in progress
DEAD = "DEAD"  # -86 Broken node to cleanup
