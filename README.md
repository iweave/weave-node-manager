# Weave Node Manager

## Overview
Weave Node Manager (wnm) is a Python application designed to manage nodes for decentralized networks.

## Features
- Update node metrics and statuses.
- Manage systemd services and ufw firewall for linux nodes.
- Support for configuration via YAML, JSON, or command-line parameters.

<span style="color:red">## Warning - In Progress</span>

This code is Alpha. It can currently only take over an [anm](https://github.com/safenetforum-community/NTracking/tree/main/anm) initiated set of nodes (at least one node). This project is essentially starting as a Python port of `anm`. It will eventually also have the option of using `antctl` instead of `systemd` to control nodes.

## Installation
1. Create a directory to hold data:
   ```
   mkdir /home/ubuntu/wnm
   ```
2. Navigate to the project directory:
   ```
   cd /home/ubuntu/wnm
3. Install the required dependencies:
   ```
   sudo apt install -y python3.12-venv python3-dotenv
   ```
4. Create a virtual environment
   ```
   python3 -m venv .venv
   ```
5. Activate the virtual environment
   ```
   . .venv/bin/activate
   ```
6. Install the package:
   ```
   pip install wnm 
   ```
7. Run to initialize environment from anm
   ```
   wnm
   ```
8. Add to cron to run every minute
   ```
   echo <<EOF
   SHELL=/bin/bash
   PATH=/home/ubuntu/.local/bin:/home/ubuntu/wnm/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
   */1 * * * * ubuntu cd /home/ubuntu/wnm && wnm > /home/ubuntu/wnm/cron.out 2>&1
   EOF
   ```

## Configuration
Configuration can be done through a `.env` file, YAML, or JSON files. The application will prioritize these configurations over default values.

Upon finding an existing installation of [anm - aatonnomicc node manager](https://github.com/safenetforum-community/NTracking/tree/main/anm), wnm will disable anm and take over management of the cluster. The /var/antctl/config is only read on first ingestion, configuration priority then moves to the `.env` file or a named configuration file.

## Usage
To run the application, execute the following command:
```
python main.py
```

## Contributing
Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for more details.
