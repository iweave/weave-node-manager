#!/bin/bash
#
declare -A node_details_store=$(sqlite3 /home/ubuntu/weave-node-manager/colony.db 'select nodename,rtrim(service,".service"),peer_id,version,status from node where id < 3' | awk -F'|' 'BEGIN { printf "("};{printf "[%s]=\"%s,%s,%s,%s\" ",$1,$2,$3,$4,$5};END {print ")"}')
