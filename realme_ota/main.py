#!/usr/bin/python3
#
# This file is part of realme-ota (https://github.com/R0rt1z2/realme-ota).
# Copyright (c) 2022 Roger Ortiz.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

import os
import sys
import json
import time
import requests
import string

from argparse import ArgumentParser

try:
    from utils import crypto
    from utils import data
    from utils.logger import Logger
    from utils.request import Request
    from utils.models import search_devices, lookup_model, detect_brand_from_model
except ImportError:
    from realme_ota.utils import crypto
    from realme_ota.utils import data
    from realme_ota.utils.request import Request
    from realme_ota.utils.logger import Logger
    from realme_ota.utils.models import search_devices, lookup_model, detect_brand_from_model

def main():
    parser = ArgumentParser()
    # Verbosity
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("-v", "--verbosity", type=int, choices=range(0, 6), default=4, help="Set the verbosity level. Range: 0 (no logging) to 5 (debug). Default: 4 (info).")
    verbosity.add_argument("-s", "--silent", action='store_true', help="Enable silent output (purge logging). Shortcut for '-v0'.")
    # Positional arguments (nargs='?' so --list-models can be used without them)
    parser.add_argument("product_model", type=str, nargs='?', help="Product Model (ro.product.name), e.g. RMX3471 / CPH2447 / PGKM10.")
    parser.add_argument("ota_version", type=str, nargs='?', help="OTA Version (ro.build.version.ota).")
    parser.add_argument("os_version", type=int, nargs='?', choices=range(1, 17), help="OS Version: RealmeUI 1~7 / ColorOS 1~16 (ro.build.version.realmeui / ro.build.version.oplusrom / ro.build.version.coloros).")
    parser.add_argument("nv_identifier", type=str, nargs='?', help="NV (carrier) identifier (ro.build.oplus_nv_id) (if none, provide 0 or omit).")
    # Request attributes
    req_opts = parser.add_argument_group("request options")
    req_opts.add_argument("-B", "--brand", type=str, choices=["auto", "realme", "coloros", "oneplus"], default="auto",
                          help="Brand of the device (auto = detect by model prefix, RMX=realme, CPH/PEG/OP/DE=coloros, PG/PH/PJD/OnePlus=oneplus).")
    req_opts.add_argument("-r", "--region", type=int, choices=[0, 1, 2, 3], default=0, help="Use custom region for the request (GL = 0, CN = 1, IN = 2, EU = 3).")
    req_opts.add_argument("-g", "--guid", type=str, default=None, help="The guid of the third line in the file /data/system/openid_config.xml (only required to extract 'CBT' in China).")
    req_opts.add_argument("-i", "--imei", type=str, nargs='+', help="Specify one or two IMEIs for the request.")
    req_opts.add_argument("-b", "--beta", action='store_true', help="Try to get a test version (IMEI probably required).")
    req_opts.add_argument("-l", "--language", type=str, default=None, help="Specify the language of response (en-EN by default, zh-CN in China).")
    req_opts.add_argument("--old-method", action='store_true', help="Use old method for the request (only applies if os_version >= 2 / equivalent legacy).")
    req_opts.add_argument("--scan", action='store_true', help="Auto-scan common OTA version patterns (tries letters A-G, numbers 00-05, builds 0001/0010). Useful when you don't know the exact ro.build.version.ota.")
    # Output settings
    out_opts = parser.add_argument_group("output options")
    out_opts.add_argument("-d", "--dump", type=str, help="Save request response into a file.")
    out_opts.add_argument("-o", "--only", type=str, help="Only show the desired value from the response.")
    # Device list
    list_opts = parser.add_argument_group("device list options")
    list_opts.add_argument("--list-models", type=str, nargs='?', const='',
                          help="Search BBK device database by model/name/codename (e.g. --list-models RMX3471 or --list-models 'Realme 9'). "
                               "No argument = list all. Data source: Google Play supported_devices.html.")
    list_opts.add_argument("--refresh-cache", action='store_true',
                          help="Force re-download the device list from Google (bypass 7-day cache).")

    args = parser.parse_args()

    # ---- Handle --list-models (device search) and exit early ----
    if args.list_models is not None:
        query = args.list_models.strip()
        try:
            results = search_devices(query, force_refresh=args.refresh_cache)
        except Exception as e:
            print(f"Error fetching device list: {e}", file=sys.stderr)
            print(f"Tip: Set ALL_PROXY=http://your-proxy:port if your network blocks Google APIs.", file=sys.stderr)
            sys.exit(1)
        if not results:
            print(f"No devices found matching '{query}'." if query else "No devices found.")
            sys.exit(0)
        print(f"Found {len(results)} device(s):\n")
        print(f"{'Brand':<10} {'Model':<18} {'Device':<18} {'Marketing Name'}")
        print(f"{'─'*10} {'─'*18} {'─'*18} {'─'*30}")
        for d in results:
            print(f"{d['brand']:<10} {d['model']:<18} {d['device']:<18} {d['name']}")
        sys.exit(0)

    # ---- Validate required positional args (when not using --list-models) ----
    missing = []
    if not args.product_model: missing.append('product_model')
    if args.os_version is None: missing.append('os_version')
    if not args.scan and not args.ota_version: missing.append('ota_version')
    if missing:
        parser.error(f"the following arguments are required: {', '.join(missing)}")

    logger = Logger(
        level = 0 if args.silent else args.verbosity
    )

    # Determine effective brand: --brand=auto first tries Google device DB, then falls back to prefix heuristics
    brand = args.brand
    if brand == "auto":
        try:
            brand = detect_brand_from_model(args.product_model, force_refresh=args.refresh_cache)
            info = lookup_model(args.product_model, force_refresh=args.refresh_cache)
            if info:
                logger.log(f"Device identified: {info['model']} = {info['name']} (brand={brand})", 4)
        except Exception:
            m = (args.product_model or "").upper()
            if m.startswith("RMX"):
                brand = "realme"
            elif any(m.startswith(p) for p in ("CPH", "PEG", "PFG", "PJH", "PJV", "PJU", "PJY", "PKA", "PKB", "PKC", "OP", "DE", "PF")):
                brand = "coloros"
            elif any(m.startswith(p) for p in ("PG", "PH", "PJD", "ONEPLUS")):
                brand = "oneplus"
            else:
                brand = "coloros"

    # Compute request version (1 = legacy ECB/CTR, 2 = new CTR+RSA)
    if brand == "realme":
        legacy_era = (args.os_version == 1)
        os_label = f"RealmeUI V{args.os_version}"
    elif brand == "oneplus":
        legacy_era = False
        os_label = f"OxygenOS/HydrogenOS V{args.os_version}"
    else:  # coloros
        legacy_era = (args.os_version <= 7)
        os_label = f"ColorOS V{args.os_version}"

    req_version = 1 if (args.old_method or legacy_era) else 2

    def _try_request(ota_ver):
        """Send a single OTA request. Returns (True, content) or (False, err_msg)."""
        request = Request(
            req_version=req_version,
            model=args.product_model,
            ota_version=ota_ver,
            os_version=args.os_version,
            brand=brand,
            nv_identifier=args.nv_identifier,
            region=args.region,
            deviceId=args.guid,
            imei0=args.imei[0] if args.imei and len(args.imei) > 0 else None,
            imei1=args.imei[1] if args.imei and len(args.imei) > 1 else None,
            beta=args.beta,
            language=args.language
        )
        try:
            request.set_vars()
            request.set_body_headers()
        except Exception as e:
            return False, str(e)

        logger.log(f"Request headers:\n{json.dumps(request.headers, indent=4, sort_keys=True, ensure_ascii=False)}", 5)

        try:
            response = requests.post(request.url, data=request.body, headers=request.headers, timeout=30)
        except Exception as e:
            return False, str(e)

        try:
            request.validate_response(response)
        except Exception as e:
            if response.content:
                try:
                    json_response = json.loads(response.content)
                    logger.log(f"Response:\n{json.dumps(json_response, indent=4, sort_keys=True, ensure_ascii=False)}", 5)
                except Exception:
                    pass
            return False, str(e)

        try:
            json_response = json.loads(response.content)
            content = json.loads(request.decrypt(json_response[request.resp_key]))
            request.validate_content(content)
        except Exception as e:
            return False, str(e)

        return True, content

    def _output(content):
        """Handle --only and --dump output."""
        if args.only:
            try:
                content = content[args.only]
            except Exception:
                logger.die(f"Invalid response key: {args.only}!", 2)
        if args.dump:
            try:
                with open(args.dump, "w") as fp:
                    json.dump(content, fp, sort_keys=True, indent=4, ensure_ascii=False)
            except Exception as e:
                logger.die(f"Something went wrong while writing the response to {args.dump} {e}!", 1)
            else:
                logger.log(f"Successfully saved request as {args.dump}!")
        else:
            print(f"{json.dumps(content, indent=4, sort_keys=True, ensure_ascii=False)}")

    # ---- Scan mode: try common OTA version patterns ----
    if args.scan:
        model = args.product_model
        letters = list(string.ascii_uppercase[:7])  # A-G
        nums = ['00', '01', '02', '03', '04', '05']
        builds = ['0001', '0010']
        candidates = []
        for letter in letters:
            for num in nums:
                for build in builds:
                    candidates.append(f"{model}_11.{letter}.{num}_{build}_000000000001")

        logger.log(f"Scanning {len(candidates)} OTA version patterns for {model} ({os_label}, brand={brand})")
        found = False
        for i, ota_ver in enumerate(candidates):
            logger.log(f"[{i+1}/{len(candidates)}] Trying {ota_ver} ...")
            ok, result = _try_request(ota_ver)
            if ok:
                logger.log(f"Found valid OTA: {ota_ver}")
                logger.log("Party time")
                _output(result)
                found = True
                break
            else:
                logger.log(f"  -> {result}", 3)
            time.sleep(0.3)
        if not found:
            logger.die(f"No valid OTA version found after scanning {len(candidates)} patterns. "
                       f"Please provide the exact ro.build.version.ota from the device.", 1)
        sys.exit(0)

    # ---- Normal mode: single request ----
    logger.log(f"Load payload for {args.product_model} ({os_label}, brand={brand})")
    ok, result = _try_request(args.ota_version)
    if not ok:
        # Auto-downgrade: retry with suffix 0001_000000000001
        if args.ota_version[-17:] != '0001_000000000001':
            new_ver = args.ota_version[:-17] + '0001_000000000001'
            logger.log(f"Retrying with downgraded version: {new_ver}")
            ok, result = _try_request(new_ver)
        if not ok:
            logger.die(f'{result}', 1)

    logger.log("All good")
    logger.log("Party time")
    _output(result)

if __name__ == '__main__':
    main()
