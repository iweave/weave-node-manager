# Weave Node Manager

## Overview
Weave Node Manager (wnm) is a Python application designed to manage nodes for decentralized networks.

## Features
- Update node metrics and statuses.
- Manage systemd services and ufw firewall for linux nodes.
- Support for configuration via YAML, JSON, or command-line parameters.

## Installation
1. Clone the repository:
   ```
   git clone https://github.com/iweave/weave-node-manager.git
   ```
2. Navigate to the project directory:
   ```
   cd weave-node-manager
3. Create a virtual environment
   ```
   python3 -m venv .venv
   ```
4. Activate the virtual environment
   ```
   . .venv/bin/activate
   ```
5. Install the required dependencies:
   ```
   pip install -r requirements.txt
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