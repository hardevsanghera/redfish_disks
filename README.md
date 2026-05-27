# Running query_disk.py (Python-only)

This project contains a small script `query_disk.py` that uses the `redfish` Python library to query storage drive information from an iLO / Redfish-enabled system.

The instructions below use only `python` and `python -m` commands so you can run everything directly with Python.

Provided as-is, no warranty or support
hardev@nutanix.com May 2026

## Prerequisites

- Python 3.8 or newer installed and on your PATH. Check with:

```powershell
python --version
```

## Create a virtual environment (no shell activation required)

Create a virtual environment with Python and install/upgrade pip. You can either activate the venv in your shell, or invoke the venv's Python executable directly (shown below) so no shell-specific activation is required.

```bash
# create venv
python -m venv .venv

# upgrade pip using the venv python (recommended)
.venv/bin/python -m pip install --upgrade pip   # macOS / Linux
.venv\Scripts\python.exe -m pip install --upgrade pip  # Windows (CMD or PowerShell)
```

If you prefer to activate the venv in your shell, use the platform-specific activation command for your shell. Activation is optional when you invoke the venv python directly.

## Install dependencies

Install dependencies using the venv Python to ensure packages go into the virtual environment.

```bash
.venv/bin/python -m pip install -r requirements.txt   # macOS / Linux
.venv\Scripts\python.exe -m pip install -r requirements.txt  # Windows
```

This installs the `redfish` library and other requirements used by `query_disk.py`.

## Configure credentials

The script reads credentials from the environment variables `ILO_IP`, `ILO_USER`, and `ILO_PASS` by default. This avoids storing secrets in the code. You can also pass credentials on the command line with `--ilo`, `--user`, and `--password` (note: passing passwords on the command line may be visible in process lists).

Examples (set environment variables before running):

# Windows (Command Prompt / CMD)
```cmd
set ILO_IP=10.10.10.11
set ILO_USER=Adminuser
set ILO_PASS=YourSecretPassword
.venv\Scripts\python.exe query_disk.py --output-csv drives.csv --any-size
```

# macOS / Linux / Git Bash / WSL
```bash
export ILO_IP=10.10.10.11
export ILO_USER=Adminuser
export ILO_PASS=YourSecretPassword
.venv/bin/python query_disk.py --output-csv drives.csv --any-size
```

If you prefer not to set env vars, pass the password interactively or on the CLI (less secure):

```bash
.venv/bin/python query_disk.py --ilo 10.10.10.11 --user Adminuser --password "YourSecretPassword" --output-csv drives.csv --any-size
```

## Run the script

You can run the script directly with your system Python or the venv Python. Using the venv python executable avoids the need to activate the venv in your shell (handy in scripts or automation).

# Run with the venv python (Windows)
.venv\Scripts\python.exe query_disk.py --ilo 10.10.10.11 --user Adminuser --any-size --output-csv .\drives.csv

# Run with the venv python (macOS / Linux)
.venv/bin/python query_disk.py --ilo 10.10.10.11 --user Adminuser --any-size --output-csv ./drives.csv

Or, if you activated the venv in your shell, you can run simply:

```bash
python query_disk.py --any-size --output-csv drives.csv
```

## Common issues / notes

- SSL certificate errors: Many iLO endpoints use self-signed certificates. If you get SSL verification errors, do one of:
  - Import the iLO CA into your OS / Python trust store (recommended), or
  - Temporarily disable verification in the script for testing (not recommended for production). If you need this for testing, you can add after creating the client:

```python
import requests
requests.packages.urllib3.disable_warnings()
# if the redfish client exposes a `session` attribute you can set verify=False on it
# remote_mgmt.session.verify = False
```

- Don't commit credentials. Use environment variables or a secrets manager.

## Next steps / improvements

- I can update `query_disk.py` to read credentials from environment variables and add an `--insecure` command-line flag that disables SSL verification for testing. I can also add a small PowerShell helper script to run it while injecting credentials from the environment.

## CSV output and metadata

When you pass `--output-csv <path>` the script writes a CSV file with the discovered drives. The file now begins with a single metadata line containing a JSON blob (prefixed with `#`) that records the UTC timestamp of the run and the effective query parameters used (the `password` value is omitted for safety).

This makes it easy to trace when and with which flags a CSV was produced. Example top of the CSV file:

```csv
# {"timestamp":"2026-05-13T12:34:56.789012Z","params":{"ilo":"10.38.243.33","user":"ADMIN","password":null,"verbose":true,"any_size":true,"output_csv":"./drives.csv"}}
slot,make,model,serial,capacity_bytes,drive_uri
Bay 1,HPE,MK001920GWSSE,SABCDE,1920383410176,/redfish/v1/Systems/1/Storage/DE080000/Drives/0
```

Notes:
- The metadata line is prefixed with `#` so many CSV tools will ignore it as a comment. It is a JSON object with `timestamp` (ISO8601 UTC) and `params` (the argparse namespace as a dict, with the `password` removed).
- If you prefer a separate metadata file, or a different header format, I can change the behavior to write a sidecar JSON file like `drives.csv.meta.json` instead.

## Example Run (Windows)

Below is an example PowerShell/Python session showing a typical run on Windows. The command and the resulting output are shown exactly as produced by the script in a test run:

```powershell
python .\query_disk.py --ilo 10.10.10.11 --user Adminuser --verbose --any-size --output-csv .\drives.csv
Login response: None
Root service object keys: ['@odata.context', '@odata.etag', '@odata.id', '@odata.type', 'Id', 'AccountService', 'CertificateService', 'Chassis', 'EventService', 'Fabrics', 'JsonSchemas', 'Links', 'Managers', 'Name', 'Oem', 'Product', 'ProtocolFeaturesSupported', 'RedfishVersion', 'Registries', 'SessionService', 'Systems', 'Tasks', 'TelemetryService', 'UUID', 'UpdateService', 'Vendor']
Found systems members: 1
  system: /redfish/v1/Systems/1/
  Storage at /redfish/v1/Systems/1/Storage/: 2 members
Aggregated storage members to check: 2
Any-size mode: showing all discovered drives (no capacity filter)
  drive item URIs: 1
    drive capacity/raw: 240057000000 name: Secondary Storage Device desc: None

Drive object dump:
{
  "@odata.context": "/redfish/v1/$metadata#Drive.Drive",
  "@odata.etag": "W/\"67EABCDE\"",
  "@odata.id": "/redfish/v1/Systems/1/Storage/DA000004/Drives/DDC16951/",
  "@odata.type": "#Drive.v1_16_0.Drive",
  "Id": "DDC16951",
  "Actions": {
    "#Drive.Reset": {
      "ResetValue@Redfish.AllowableValues": [
        "ForceOff",
        "ForceOn",
        "PowerCycle"
      ],
      "target": "/redfish/v1/Systems/1/Storage/DA000004/Drives/DDC16951/Actions/Drive.Reset/"
    }
  },
  "CapacityBytes": 240057000000,
  "Identifiers": [],
  "Location": [
    {
      "Info": "N/A",
      "InfoFormat": "BayNumber"
    }
  ],
  "MediaType": "SSD",
  "Model": "MR000240GWFLU",
  "Name": "Secondary Storage Device",
  "Oem": {
    "Hpe": {
      "@odata.context": "/redfish/v1/$metadata#HpeiLODriveExt.HpeiLODriveExt",
      "@odata.type": "#HpeiLODriveExt.v2_0_1.HpeiLODriveExt",
      "DriveStatus": {},
      "TemperatureStatus": {}
    }
  },
  "Operations": [],
  "PhysicalLocation": {
    "PartLocation": {
      "LocationOrdinalValue": 0,
      "LocationType": "Bay",
      "ServiceLabel": "N/A"
    }
  },
  "PredictedMediaLifeLeftPercent": null,
  "Revision": "HPGG",
  "SerialNumber": "2022289ABCDE",
  "Status": {
    "Health": "OK"
  }
}
Slot: N/A
Make: HPE
Model: MR000240GWFLU
Serial: 2022289ABCDE
--------------------
  drive item URIs: 6
    drive capacity/raw: 1920383410176 name: 1.92TB 6G SATA SSD desc: None
Slot: Bay 1
Make: HPE
Model: MK001920GWSSE
Serial: S523NA0N3ABCDE
--------------------
    drive capacity/raw: 1920383410176 name: 1.92TB 6G SATA SSD desc: None
Slot: Bay 2
Make: HPE
Model: MK001920GWSSE
Serial: S523NA0N3ABCDE
--------------------
    drive capacity/raw: 1920383410176 name: 1.92TB 6G SATA SSD desc: None
Slot: Bay 3
Make: HPE
Model: MK001920GWSSE
Serial: S523NA0N3ABCDE
--------------------
    drive capacity/raw: 1920383410176 name: 1.92TB 6G SATA SSD desc: None
Slot: Bay 4
Make: HPE
Model: MK001920GWSSE
Serial: S523NA0N3ABCDE
--------------------
    drive capacity/raw: 1920383410176 name: 1.92TB 6G SATA SSD desc: None
Slot: Bay 5
Make: HPE
Model: MK001920GWSSE
Serial: S523NA0N3ABCDE
--------------------
    drive capacity/raw: 1920383410176 name: 1.92TB 6G SATA SSD desc: None
Slot: Bay 6
Make: HPE
Model: MK001920GWSSE
Serial: S523NA0N3ABCDE
--------------------
Found 7 drive(s) matching the filter.
Counts by make:
  HPE: 7
Counts by model:
  MK001920GWSSE: 6
  MR000240GWFLU: 1
Wrote 7 rows to .\drives.csv
(.venv) PS C:\Users\user1\Documents
```
