
the antctl process_manager 'add' node function returns the service_name like 'antnode1', which always appends new nodes to the end incrementing the number (deleted node numbers are not reused). unlike the other node_managers, we can't choose the service_name in antctl so we can't depend on that value matching the node directory name.

antctl has a reset command that teardown can use, this removes all the nodes from the filesystem so clear the node table instead of deleting each node individualy.

-----

Regarding s6-overlay. I know it's for inside docker containers. I'm naming this process_manager as s6overlay+user because s6overlay is the process manager inside the container, like we use systemd/launchd as other managers

There exists large fleets of deployments where node operators schedule hundreds of nodes per container. The end goal of the s6overlay process_manager is to load balance new nodes across container groups (with new max_node_per_container and min_container_count init settings).

max_node_per_container creates the step between container allocations.  The intent is the ability to launch multiple add node operations simultaniously, one per container with a methodical port allocation strategy. This implies an abandoment of sequential hole filling strategy for node numbers for this process_manager.

min_container_count sets the initial scale of the cluster, but new containers will be expanded when max_node_per_container * active_containers is reached, node_cap is still allowed and system is within available resources for add mode.

If min_container_count is set to 5 and max_node_container is set to 200, the first containers would be allocated with ports and metric ports like so

### port allocation
Container,Metric_port_range,Node_port_range
a1,13001-13200,55001-55200
a2,13201-13400,55201-55400
a3,13401-13600,55401-55600
a4,13601-13800,55601-55800
a5,13801-14000,55801-56000

There are some things to be discussed.

The s6overlay process_manager needs a way to initialize containers when needed. containers need to map the node_storage path to the containers /var/antctl/services directory so that data persists across container restarts.  containers also need host networking capability so that the node and metrics ports are reachable. an alternative is to launch each container with published ranges based on the allocation strategy specified above. actually, this is the preferred case if we can get it to work.

we need a way to specify the docker image that new containers use

when we start/stop a s6overlay node, we need to write the service run file each time as it could be missing after a container restart. Then we use the 'up' file to start/stop the nodes.  pass in the UID/GID for the `ant` user in the container as a one-shot script so the permissions on the container user work with the node_storage mounted volume.

during teardown for s6overlay, stop and remove the containers after nodes are removed

for the primary command in each container, use sleep forever, we'll sigkill HUP that to stop the container. we don't want the container to stop because we stop a node (we might be upgrading, stopping or removing a node)

we also need a new argument --dockerfile that when using s6overlay process_manager will output a Dockerfile for our s6overlay image. When building the image, create the `ant` user, who doesn't need sudo because we're making things with the correct permissions.

when building the image, run the following

### initialize node binary
RUN apt update && \
    apt install -y curl procps iputils-ping iproute2 && \
    curl -sSL https://raw.githubusercontent.com/maidsafe/antup/main/install.sh | bash && \
    echo 'export PATH=\$PATH:/home/ant/.local/bin' >> ~/.bashrc && \
    source ~/.bashrc && \
    antup node && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*




----
answers
1. option a
2. option b, dont let process managers update the database
3. option a, but max_nodes_per_container and min_container_count are per machine not per container so doesn't seem like new need capacity or max_nodes per container
4. option a
5. option c
