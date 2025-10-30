  let's add our first report 'node-status'. 
  
  ## node-status report

  using the database as the source of truth (surveying the cluster is an expensive operation in large fleets and
  has it's own place in the workflow), and supporting --service-name (which now can be a comma separated list of
  nodes), we'll need to add that to the force task methods. We also need multi service-name capability to support
  multiple-operation requests in the future.
  
  When no --service_name is defined, report nodes in increasing numerical order. If --service_name is defined,
  parse the results of a comma separated list as the order to report the nodes.
   
  Output a header row that has proper spaces to align the columns 
  "Service Name    Peer ID       Status      Connected Peers"

  and then one row per node, fill in the known data (Peer ID may be unknown, in which event use '-')

  ### code
  antnode0001            12D3KooWAgR9UqQ4MeYq5kfyEG29HktnnM6QRKdbWbYdghqxQj6s RUNNING               0
  ### /code
  
  ## node-status-details report
  and our next report 'node-status-details' gives multiple lines of output in 'key: value' format or json format if --report_format is set to json.

  ### code
  Version: 0.4.6
  Port: 55555
  Metrics Port: 13555
  Data path: /Users/dawn/Library/Application Support/autonomi/node/antnode0001
  Log path: /Users/dawn/Library/Application Support/autonomi/node/antnode0001/logs
  Bin Path: /Users/dawn/Library/Application Support/autonomi/node/antnode0001/antnode
  Connected peers: 0
  Rewards address: 0x00455d78f850b0358E8cea5be24d415E01E107CF
  Age: <sec>
  Status: RUNNING
  ### /code
  The json version of this report is new and should use the snake_case column name from the model as the key names of the returned node data