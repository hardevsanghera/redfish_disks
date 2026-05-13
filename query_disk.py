""" Provided as-is, no warranty or support
""" hardev@nutanix.com
""" May 2026
"""
import os
import argparse
import redfish
import json
from datetime import datetime
import re
from collections import Counter
import requests


def main():
    parser = argparse.ArgumentParser(description='Query disks via Redfish')
    parser.add_argument('--ilo', default=os.environ.get('ILO_IP', '192.168.1.100'), help='iLO host or IP')
    parser.add_argument('--user', default=os.environ.get('ILO_USER', 'admin'), help='username')
    parser.add_argument('--password', default=os.environ.get('ILO_PASS', None), help='password (or set ILO_PASS)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Print verbose debug information')
    parser.add_argument('--insecure', action='store_true', help='Disable SSL verification (for testing only)')
    parser.add_argument('--any-size', '--all', dest='any_size', action='store_true', help='Show drives of any size (no capacity filter)')
    parser.add_argument('--probe', action='store_true', help='Probe root and Systems collections and print diagnostics')
    parser.add_argument('--inspect-storage', action='store_true', help='Fetch each storage member and print its properties and linked collections')
    parser.add_argument('--min-size', help='Minimum drive size (e.g. 7.5TB, 7680GB). If no unit provided, TB is assumed')
    parser.add_argument('--max-size', help='Maximum drive size (e.g. 8TB). If no unit provided, TB is assumed')
    parser.add_argument('--output-csv', help='Write results to CSV file path')

    args = parser.parse_args()

    def find_field(obj, candidates):
        """Search obj (dict/list) for the first matching candidate key (case-insensitive).
        Returns the value or None. Recurses into nested dicts/lists.
        """
        if obj is None:
            return None
        if isinstance(obj, dict):
            # direct keys
            for k, v in obj.items():
                for cand in candidates:
                    if k.lower() == cand.lower():
                        return v
            # recurse
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    found = find_field(v, candidates)
                    if found is not None:
                        return found
            return None
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    found = find_field(item, candidates)
                    if found is not None:
                        return found
            return None
        return None

    def parse_slot(data, storage_entry=None):
        # Try common places for human-friendly slot/bay info
        try:
            part = (data.get('PhysicalLocation', {}) or {}).get('PartLocation', {})
            service = part.get('ServiceLabel') if isinstance(part, dict) else None
            loc_ord = part.get('LocationOrdinalValue') if isinstance(part, dict) else None
            # If ServiceLabel contains Bay=<n> or Bay=n, extract it
            if service and isinstance(service, str):
                m = re.search(r'[Bb]ay[=:\s]*([0-9]+)', service)
                if m:
                    return f'Bay {m.group(1)}'
                # if it's a readable label and not N/A, return it
                if service.strip() and service.strip().upper() != 'N/A':
                    return service
            # Fall back to LocationOrdinalValue
            if isinstance(loc_ord, int) and loc_ord > 0:
                return f'Bay {loc_ord}'
            # Some implementations put location in a Location list
            loc = data.get('Location')
            if isinstance(loc, list) and len(loc) > 0 and isinstance(loc[0], dict):
                info = loc[0].get('Info')
                if info and isinstance(info, str) and info.strip().upper() != 'N/A':
                    return info
        except Exception:
            pass
        # last resorts
        return data.get('Slot') or data.get('DeviceLocation') or 'N/A'

    if not args.password:
        # try to read from environment if not provided on CLI
        args.password = os.environ.get('ILO_PASS')

    if not args.password:
        raise SystemExit('Password is required: set ILO_PASS env var or pass --password')

    base_url = f"https://{args.ilo}"

    # Optionally disable warnings for self-signed certs when --insecure is used
    if args.insecure:
        requests.packages.urllib3.disable_warnings()

    # Create the Redfish client
    try:
        remote_mgmt = redfish.redfish_client(base_url=base_url, username=args.user, password=args.password)
    except Exception as e:
        raise SystemExit(f'Failed to create Redfish client: {e}')

    # If the redfish client exposes a requests.Session, set verify as requested
    try:
        if args.insecure and hasattr(remote_mgmt, 'session'):
            remote_mgmt.session.verify = False
    except Exception:
        # ignore if not supported
        pass

    try:
        login_resp = remote_mgmt.login()
        if args.verbose:
            print(f'Login response: {getattr(login_resp, "status", repr(login_resp))}')
    except Exception as e:
        raise SystemExit(f'Login failed: {e}')

    # Probe root and Systems collections; don't assume Systems/1 exists
    systems_members = []
    try:
        root = remote_mgmt.get('/redfish/v1/', None)
        if args.probe or args.verbose:
            print('Root service object keys:', list(root.obj.keys()) if hasattr(root, 'obj') else repr(root))
    except Exception as e:
        print(f'Warning: failed to get Redfish root: {e}')

    try:
        systems = remote_mgmt.get('/redfish/v1/Systems/', None)
        if hasattr(systems, 'obj'):
            systems_members = systems.obj.get('Members', []) or []
        if args.probe or args.verbose:
            print(f'Found systems members: {len(systems_members)}')
            for s in systems_members:
                print(f"  system: {s.get('@odata.id')}")
    except Exception as e:
        print(f'Warning: failed to get Systems collection: {e}')

    # Gather storage members across all systems
    members = []
    for s in systems_members:
        sys_id = s.get('@odata.id')
        if not sys_id:
            continue
        storage_uri = sys_id.rstrip('/') + '/Storage/'
        try:
            storage_collection = remote_mgmt.get(storage_uri, None)
            if hasattr(storage_collection, 'obj'):
                sm = storage_collection.obj.get('Members', []) or []
                if args.probe or args.verbose:
                    print(f'  Storage at {storage_uri}: {len(sm)} members')
                # annotate each storage member with its parent storage uri
                for entry in sm:
                    members.append(entry)
        except Exception as e:
            if args.verbose or args.probe:
                print(f'  failed to get storage at {storage_uri}: {e}')

    if args.probe:
        # If probe-only, exit after printing diagnostics
        if not systems_members:
            print('Probe complete: no Systems found under /redfish/v1/Systems/')
        else:
            print('Probe complete.')
        remote_mgmt.logout()
        return

    if args.verbose:
        print(f'Aggregated storage members to check: {len(members)}')
    if args.any_size and args.verbose:
        print('Any-size mode: showing all discovered drives (no capacity filter)')

    def parse_size_to_bytes(s):
        if not s:
            return None
        s = str(s).strip()
        m = re.match(r'^([0-9]*\.?[0-9]+)\s*([A-Za-z]{1,4})?$', s)
        if not m:
            raise ValueError(f'unrecognized size: {s}')
        num = float(m.group(1))
        unit = (m.group(2) or '').lower()
        # default to TB (decimal) if no unit provided
        if unit == '':
            return int(num * 10**12)
        # decimal units
        if unit in ('b',):
            return int(num)
        if unit in ('kb', 'k'):
            return int(num * 10**3)
        if unit in ('mb', 'm'):
            return int(num * 10**6)
        if unit in ('gb', 'g'):
            return int(num * 10**9)
        if unit in ('tb', 't'):
            return int(num * 10**12)
        # binary units
        if unit in ('kib',):
            return int(num * 1024)
        if unit in ('mib',):
            return int(num * 1024**2)
        if unit in ('gib',):
            return int(num * 1024**3)
        if unit in ('tib',):
            return int(num * 1024**4)
        raise ValueError(f'unsupported unit: {unit}')

    min_bytes = None
    max_bytes = None
    try:
        if args.min_size:
            min_bytes = parse_size_to_bytes(args.min_size)
        if args.max_size:
            max_bytes = parse_size_to_bytes(args.max_size)
    except Exception as e:
        raise SystemExit(f'Invalid size argument: {e}')

    import csv
    csv_rows = []

    matched = 0
    for storage in members:
        # Fetch the storage member resource to inspect its properties
        storage_odata_id = storage.get('@odata.id', '')
        if not storage_odata_id:
            if args.verbose:
                print(f'skipping storage entry with missing @odata.id: {storage!r}')
            continue

        # We'll fetch the storage member resource for inspection and to find where drives are linked
        storage_entry = None
        try:
            storage_entry = remote_mgmt.get(storage_odata_id, None)
        except Exception as e:
            if args.verbose:
                print(f'  failed to fetch storage member {storage_odata_id}: {e}')
            storage_entry = None

        # If inspect-storage requested, print the storage entry and linked collections
        if args.inspect_storage:
            print('\n--- Storage member: ' + storage_odata_id + ' ---')
            if storage_entry is not None and hasattr(storage_entry, 'obj'):
                try:
                    print(json.dumps(storage_entry.obj, indent=2, default=str))
                except Exception:
                    print(repr(storage_entry.obj))
                # Look for common link properties that may contain drives
                for key, val in (storage_entry.obj.items() if hasattr(storage_entry, 'obj') else []):
                    # If val is a dict with @odata.id
                    if isinstance(val, dict) and '@odata.id' in val:
                        uri = val.get('@odata.id')
                        try:
                            coll = remote_mgmt.get(uri, None)
                            count = len(coll.obj.get('Members', [])) if hasattr(coll, 'obj') else 'unknown'
                        except Exception as e:
                            count = f'error: {e}'
                        print(f'  linked {key}: {uri} -> members: {count}')
                    # If val is a list of dicts with @odata.id
                    elif isinstance(val, list) and val and isinstance(val[0], dict) and '@odata.id' in val[0]:
                        # print each member's @odata.id
                        for item in val:
                            uri = item.get('@odata.id')
                            print(f'  linked {key} item: {uri}')
            else:
                print('  (no object returned for storage member)')

        # Prefer iterating explicit Drives items from the storage member resource
        drive_item_uris = []
        if storage_entry is not None and hasattr(storage_entry, 'obj') and storage_entry.obj.get('Drives'):
            for item in storage_entry.obj.get('Drives', []):
                if isinstance(item, dict) and item.get('@odata.id'):
                    drive_item_uris.append(item.get('@odata.id'))

        # If no explicit items, fall back to querying the Drives collection URI
        if not drive_item_uris:
            drive_uri = f"{storage_odata_id.rstrip('/')}" + '/Drives/'
            if args.verbose:
                print(f'Checking drives collection at: {drive_uri}')

            drives = None
            try:
                drives = remote_mgmt.get(drive_uri, None)
                # some implementations expose Members under the collection
                if drives is not None and hasattr(drives, 'obj'):
                    for m in drives.obj.get('Members', []):
                        if isinstance(m, dict) and m.get('@odata.id'):
                            drive_item_uris.append(m.get('@odata.id'))
            except Exception as e:
                if args.verbose:
                    print(f'  failed to get drives at {drive_uri}: {e}')
                # continue; drive_item_uris may still be empty

        if args.verbose:
            print(f'  drive item URIs: {len(drive_item_uris)}')

        for drive_uri in drive_item_uris:
            drive_details = None
            try:
                drive_details = remote_mgmt.get(drive_uri, None)
            except Exception as e:
                if args.verbose:
                    print(f'    failed to get drive details for {drive_uri}: {e}')
                continue

            data = drive_details.obj if (drive_details is not None and hasattr(drive_details, 'obj')) else {}

            # Filter for your 7.68TB drives — CapacityBytes contains bytes, so we check human-readable fields too
            capacity = data.get('CapacityBytes', '')
            # also check any DisplayName or Description fields for the string
            if args.verbose:
                print(f'    drive capacity/raw: {capacity} name: {data.get("Name")} desc: {data.get("Description")}')

            # Filtering logic: numeric min/max takes precedence when provided
            show = False
            if min_bytes is not None or max_bytes is not None:
                # attempt to use CapacityBytes first
                try:
                    cap = int(capacity) if capacity not in (None, '') else None
                except Exception:
                    cap = None
                # if no numeric capacity, try to parse from Name (e.g. '1.92TB')
                if cap is None:
                    name = str(data.get('Name', '') or '')
                    nm = None
                    m = re.search(r'([0-9]*\.?[0-9]+)\s*(TB|T|GB|G|MB|M|TiB|GiB|MiB)', name, re.IGNORECASE)
                    if m:
                        try:
                            nm = parse_size_to_bytes(m.group(1) + (m.group(2) or ''))
                        except Exception:
                            nm = None
                    cap = nm

                if cap is not None:
                    if min_bytes is not None and cap < min_bytes:
                        show = False
                    elif max_bytes is not None and cap > max_bytes:
                        show = False
                    else:
                        show = True
                else:
                    # cannot determine capacity -> do not show when min/max are requested
                    show = False
            else:
                # If --any-size is passed, skip capacity filtering and show every drive
                show = args.any_size or '7.68' in str(capacity) or '7.68' in str(data.get('Name', '')) or '7.68' in str(data.get('Description', ''))

            if show:
                matched += 1
                slot = parse_slot(data, storage_entry)
                # Try to infer make/manufacturer from common fields or nested OEM sections
                make = find_field(data, ['Manufacturer', 'Make', 'Vendor', 'ManufacturerName', 'ModelName', 'ManufacturerId', 'VendorId', 'VendorName', 'DeviceManufacturer'])

                # If not found, try OEM key in the drive object (e.g. Oem -> Hpe)
                if make is None:
                    oem = data.get('Oem') if isinstance(data.get('Oem'), dict) else None
                    if oem:
                        # pick the first OEM vendor key
                        try:
                            first = next(iter(oem.keys()))
                            make = first.upper()
                        except StopIteration:
                            make = None

                # If still not found, try parent storage name (often contains vendor)
                if make is None and storage_entry is not None and hasattr(storage_entry, 'obj'):
                    sname = storage_entry.obj.get('Name', '')
                    if sname:
                        # common vendor tokens to look for
                        vendors = ['HPE', 'HP', 'DELL', 'LENOVO', 'IBM', 'SUPERMICRO', 'SEAGATE', 'WD', 'WESTERN', 'KINGSTON', 'SAMSUNG', 'MICRON']
                        for v in vendors:
                            if v.lower() in sname.lower():
                                make = v if v != 'HP' else 'HPE'
                                break

                if make is None:
                    make = 'Unknown'
                # If verbose and we couldn't find make or slot is blank, dump the drive object for inspection
                if args.verbose and (make == 'Unknown' or slot in (None, '', 'N/A')):
                    try:
                        print('\nDrive object dump:')
                        print(json.dumps(data, indent=2, default=str))
                    except Exception:
                        print(repr(data))

                print(f"Slot: {slot}")
                print(f"Make: {make}")
                print(f"Model: {data.get('Model')}")
                print(f"Serial: {data.get('SerialNumber')}")
                print("-" * 20)
                # collect csv row
                csv_rows.append({
                    'slot': slot,
                    'make': make,
                    'model': data.get('Model'),
                    'serial': data.get('SerialNumber'),
                    'capacity_bytes': data.get('CapacityBytes'),
                    'drive_uri': drive_uri,
                })

    if matched == 0:
        if args.any_size:
            print('No drives were found.')
        else:
            print('No matching 7.68TB drives were found.')

    # Summary: counts per make and per model
    makes = Counter(r['make'] for r in csv_rows)
    models = Counter(r['model'] for r in csv_rows)
    total = len(csv_rows)
    print(f'Found {total} drive(s) matching the filter.')
    if total > 0:
        print('Counts by make:')
        for make, cnt in makes.most_common():
            print(f'  {make}: {cnt}')
        print('Counts by model:')
        for model, cnt in models.most_common():
            print(f'  {model}: {cnt}')

    # Write CSV if requested
    if args.output_csv:
        try:
            # Build a metadata header with timestamp and effective query parameters (exclude password)
            params_copy = {k: v for k, v in vars(args).items() if k != 'password'}
            metadata = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'params': params_copy,
            }
            with open(args.output_csv, 'w', newline='', encoding='utf-8') as f:
                # Write a single metadata line as a JSON blob prefixed with '#' so tools that accept
                # comment lines in CSV can ignore it. This keeps the metadata readable and machine-parseable.
                f.write(f"# {json.dumps(metadata, default=str)}\n")
                writer = csv.DictWriter(f, fieldnames=['slot', 'make', 'model', 'serial', 'capacity_bytes', 'drive_uri'])
                writer.writeheader()
                for row in csv_rows:
                    writer.writerow(row)
            print(f'Wrote {len(csv_rows)} rows to {args.output_csv}')
        except Exception as e:
            print(f'Failed to write CSV to {args.output_csv}: {e}')

    remote_mgmt.logout()


if __name__ == '__main__':
    main()
