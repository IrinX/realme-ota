# Realme / ColorOS / OnePlus OTA Downloader

Fork of [R0rt1z2/realme-ota](https://github.com/R0rt1z2/realme-ota) with added support for **ColorOS 1~16** and **OnePlus (OxygenOS / HydrogenOS)**, keeping backwards compatibility with RealmeUI 1~7.

![License](https://img.shields.io/github/license/IrinX/realme-ota)

## Requirements
* Python 3.9 (or newer).

## Installation

### Windows
Required [Windows Terminal](https://github.com/microsoft/terminal) or [PowerShell](https://github.com/PowerShell/PowerShell).
```powershell
# (Requires privileges - start Terminal/PowerShell as administrator)
Invoke-WebRequest https://raw.githubusercontent.com/IrinX/realme-ota/master/Install.ps1 | Invoke-Expression
```

### Linux
```bash
sudo apt install python3-pip
pip3 install --upgrade git+https://github.com/IrinX/realme-ota
```

## Usage

```bash
usage: realme-ota [-h] [-v {0,1,2,3,4,5} | -s]
                  [-B {auto,realme,coloros,oneplus}]
                  [-r {0,1,2,3}] [-g GUID]
                  [-i IMEI [IMEI ...]] [-b] [-l LANGUAGE]
                  [--old-method] [-d DUMP] [-o ONLY]
                  product_model ota_version {1..16} [nv_identifier]

positional arguments:
  product_model         Product Model (ro.product.name),
                        e.g. RMX3471 (Realme), CPH2447 (OPPO/ColorOS global),
                             PGKM10 / PJD110 (ColorOS China / OnePlus).
  ota_version           OTA Version (ro.build.version.ota).
  {1..16}               OS Version: RealmeUI 1~7  *or*  ColorOS 1~16  *or*
                        OxygenOS/HydrogenOS (use the matching ColorOS version).
  nv_identifier         NV (carrier) identifier (ro.build.oplus_nv_id)
                        (if none, provide 0 or omit).

options:
  -h, --help            show this help message and exit
  -v {0..5}, --verbosity {0..5}
                        Set verbosity level (0 = silent, 5 = debug). Default: 4 (info).
  -s, --silent          Silent output. Shortcut for '-v0'.

request options:
  -B, --brand {auto,realme,coloros,oneplus}
                        Brand of the device. 'auto' (default) guesses by model prefix:
                          RMX*            -> realme
                          CPH*/DE*/PEG*/PF* -> coloros (global OPPO)
                          PG*/PH*/PJD*   -> coloros (explicit --brand=oneplus to override)
  -r {0,1,2,3}, --region {0,1,2,3}
                        Region for the request (GL = 0, CN = 1, IN = 2, EU = 3). Default: 0.
  -g GUID, --guid GUID  The guid of the third line in
                        /data/system/openid_config.xml (only required to
                        extract 'CBT' in China).
  -i IMEI [IMEI ...], --imei IMEI [IMEI ...]
                        Specify one or two IMEIs for the request.
  -b, --beta            Try to get a test version (IMEI probably required).
  -l LANGUAGE, --language LANGUAGE
                        Response language (en-EN by default, zh-CN in China).
  --old-method          Use legacy encryption (ECB / old CTR) instead of the
                        default AES-CTR+RSA v2. Auto-enabled for RealmeUI 1
                        and ColorOS <= 7.

output options:
  -d DUMP, --dump DUMP  Save request response into a file.
  -o ONLY, --only ONLY  Only show the desired value from the response
                        (e.g. realmeUrl, componentVersionName ...).
```

### Quick examples

```bash
# Realme (RUI 7, global)
realme-ota RMX3471 RMX3471_11.F.00_0000_000000000001 7 -r 0

# ColorOS 16 (China region, model PGKM10)
realme-ota PGKM10 PGKM10_11.C.00_0000_000000000001 16 -B coloros -r 1

# ColorOS 7 (legacy encryption, India)
realme-ota CPH2095 CPH2095_11.A.00_0000_000000000001 7 -B coloros -r 2

# OnePlus (modern allawnos endpoint, global)
realme-ota PJD110 PJD110_11.C.00_0000_000000000001 16 -B oneplus -r 0

# Only print the direct OTA download URL and also save full JSON
realme-ota RMX3471 RMX3471_11.F.00_0000_000000000001 7 -r 0 -o realmeUrl -d out.json
```

## OS version ⇄ Android / ColorOS mapping

| RealmeUI | ColorOS equiv. | Android |
|---------:|---------------:|--------:|
| 1        | 7              | 10      |
| 2        | 11             | 11      |
| 3        | 12             | 12      |
| 4        | 13             | 13      |
| 5        | 14             | 14      |
| 6        | 15             | 15      |
| 7        | 16             | 16      |

When using `--brand coloros` the positional `os_version` argument **is** the ColorOS version directly (1~16), e.g. `16` produces `ColorOS16` + `Android16.0`.

## Additional notes

* If your request returns `flow limit` or status code `500`, wait a few minutes and retry.
* Use `ALL_PROXY` env var to route requests through a proxy (useful for region-locked updates):
  * Windows: `set ALL_PROXY=ADDRESS:PORT`
  * Linux / macOS: `export ALL_PROXY=ADDRESS:PORT`
* Since Android 11 (RealmeUI 2 / ColorOS 11+) OPPO/Realme/OnePlus use component OTAs,
  so you may get multiple per-component download entries instead of one full OTA zip.
* `--beta` is not fully tested.

## License
* GNU General Public License v3. See `LICENSE` for the full text.
