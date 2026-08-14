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

import json
from time import time

try:
    from utils import data
    from utils import crypto
except ImportError:
    from realme_ota.utils import data
    from realme_ota.utils import crypto

class Request:
    def __init__(self, req_version=1, model=None, ota_version=None, nv_identifier=None,
        os_version=None, brand="coloros", region=None, deviceId=None, imei0=None, imei1=None,
        beta=False, language=None):
        self.brand = brand
        self.os_version = os_version

        self.properties = {
            'model': model,
            'productName': model,
            'nvId': nv_identifier,
            'otaVersion': ota_version,
            'os_version': os_version,
            'region': region,
            'deviceId': deviceId,
            'imei': imei0,
            'imei1': imei1
        }
        self.beta = beta
        self.req_version = req_version
        if deviceId:
            self.properties['deviceId'] = crypto.sha256(deviceId)   # This is done by the OTA application on the phone
        elif imei0:
            self.properties['deviceId'] = crypto.sha256(imei0)  # This is done by the realme update tool companion app
        else:
            self.properties['deviceId'] = crypto.sha256(data.default_headers['imei'])

        # ---- Determine whether this is a "legacy v1 era" request (ECB encryption, old URL, resp_key='resps')
        #      RealmeUI 1 / ColorOS <= 7 / OnePlus(old h2os endpoint) are legacy.
        if self.brand == "realme":
            self.is_legacy = (os_version == 1)
        elif self.brand == "oneplus":
            # For OnePlus we still prefer the allawnos new endpoint by default;
            # legacy only if caller explicitly forced req_version=1
            self.is_legacy = (req_version == 1)
        else:  # coloros
            self.is_legacy = (os_version <= 7)

        if self.is_legacy:
            self.properties['version'] = '2'

        # ---- Pick server URL
        if self.brand == "oneplus" and model in ('OnePlus', 'oneplus', 'Oneplus'):
            # Old HydrogenOS endpoint kept for compatibility
            self.url = 'https://otag.h2os.com/post/Query_Update'
            # Note: h2os endpoint is legacy-style, treat it like v1 for enc/dec
            self.is_legacy = True
        elif (not self.is_legacy) and req_version == 2:
            # New style allawnos/allawntech endpoint (used by RUI2+, ColorOS 8+, OnePlus modern)
            self.url = data.server_params[region]['serverURL']
        else:
            # Legacy per-region endpoints. urls{} only has keys 1 and 2, and both work for any legacy era.
            # For ColorOS <= 7 we use the same legacy endpoints; newer ColorOS will hit the allawnos branch above.
            self.url = data.urls[2 if not self.is_legacy else 1][region]

        self.resp_key = 'resps' if self.is_legacy else 'body'

        if language is not None:
            self.properties['language'] = language

        self.key = None
        self.body = None
        self.headers = dict()

    def encrypt(self, buf):
        if self.is_legacy:
            return crypto.encrypt_ecb(buf), None, None
        elif self.req_version == 2:
            return crypto.encrypt_ctr_v2(buf)
        else:
            return crypto.encrypt_ctr(buf), None, None

    def decrypt(self, buf):
        if self.is_legacy:
            return crypto.decrypt_ecb(buf)
        elif self.req_version == 2:
            body_object = json.loads(buf)
            return crypto.decrypt_ctr_v2(body_object['cipher'], self.key, body_object['iv'])
        else:
            return crypto.decrypt_ctr(buf)

    # ------------------------------------------------------------------
    # Version-mapping helpers: normalize brand+os_version into the values
    # the OTA server actually wants (androidVersion, colorOSVersion).
    # ------------------------------------------------------------------
    @staticmethod
    def _map_android_and_coloros(brand, os_version):
        """Return (androidVersion_str, colorOSVersion_str).

        Official / observed mapping (server-side values are lenient, these
        are the values that best match what the real OTA clients send):

        RealmeUI 1..7 : Android 10..16
            RUI 1 = Android 10, ColorOS 7
            RUI 2 = Android 11, ColorOS 11  (ColorOS skipped 8/9/10 between 7 and 11)
            RUI 3 = Android 12, ColorOS 12
            ...
            RUI 7 = Android 16, ColorOS 16

        ColorOS 1..16 :
            ColorOS 1..6 -> Android 10.0 (pre-Android 10 era, clamped so server doesn't choke)
            ColorOS 7    -> Android 10.0
            ColorOS 8    -> Android 11.0
            ColorOS 9    -> Android 12.0
            ColorOS 10   -> Android 13.0
            ColorOS 11   -> Android 14.0
            ColorOS 12   -> Android 15.0
            ColorOS 13   -> Android 16.0
            ColorOS 14   -> Android 17.0   (future, for "query history up to ColorOS 16")
            ColorOS 15   -> Android 18.0
            ColorOS 16   -> Android 19.0

        OnePlus OxygenOS / HydrogenOS modern builds share the same ColorOS
        versioning scheme, so os_version is treated as the ColorOS version.
        """
        if brand == "realme":
            # RealmeUI N  ->  Android (10 + N - 1)
            android = 10 + (os_version - 1)
            if os_version == 1:
                cos = 7
            else:
                # RUI 2 -> ColorOS 11, then 1:1
                cos = 11 + (os_version - 2)   # i.e. os_version + 9
        else:
            # coloros / oneplus
            cos = os_version
            android = 10 + max(0, os_version - 7)

        # Safety clamp for ColorOS 1..6 (they were based on Android 5~9 but
        # the modern component-OTA server rarely cares; 10 is the safe floor).
        if android < 10:
            android = 10

        return f"Android{android}.0", f"ColorOS{cos}"

    def set_vars(self):
        region = self.properties.get('region')
        os_version = self.os_version
        brand = self.brand
        nvId = self.properties.get('nvId')

        #
        # @name(s): trackRegion, uRegion
        # @value(s): ro.oppo.regionmark, persist.sys.oppo.region
        #
        self.properties['trackRegion'] = self.properties['uRegion'] = \
            'CN' if region == 1 else 'IN' if region == 2 else 'EU' if region == 3 else 'GL'

        #
        # @name(s): language
        # @value(s): LOCALE
        #
        if region == 1 and not self.properties.get('language'):
            self.properties['language'] = 'zh-CN'

        #
        # @name(s): androidVersion, colorOSVersion
        #
        android_str, cos_str = self._map_android_and_coloros(brand, os_version)
        self.properties['androidVersion'] = android_str
        self.properties['colorOSVersion'] = cos_str

        #
        # @name(s): nvCarrer, partCarrier, localCarrier
        # @value(s): ro.build.oplus_nv_id
        #
        if nvId and nvId != '0':
            self.properties['nvCarrier'] =  self.properties['partCarrier'] = \
                self.properties['localCarrier'] = nvId
        else:
            self.properties['nvCarrier'] = self.properties['partCarrier'] = \
                self.properties['localCarrier'] = \
                    '10010111' if region == 1 else '01000100' if region == 3 else '00011011'

        #
        # @name(s): isRealme
        # @value(s): 1 for realme brand (model RMX* usually), 0 for OPPO/OnePlus/ColorOS
        #
        self.properties['isRealme'] = '1' if (brand == 'realme' or 'RMX' in (self.properties.get('model') or '')) else '0'

        #
        # @name(s): romPrefix, romVersion, otaPrefix
        # @value(s): ro.build.version.ota
        #
        self.properties['romPrefix'] = self.properties['romVersion'] = \
            self.properties['otaPrefix'] = '_'.join(self.properties.get('otaVersion').split('_')[:2])

        #
        # @name(s): time
        # @value(s): Current system time in milliseconds
        #
        self.properties['time'] = str(int(time() * 1000))

    def set_body_headers(self):
        new_body = dict()

        for entry in list(data.default_body.keys()):
            new_body[entry] = self.properties.get(entry) or data.default_body[entry]
            if entry == 'mode' and self.beta:
                new_body[entry] = '1'

        for entry in list(data.default_headers.keys()):
            self.headers[entry] = self.properties.get(entry) or data.default_headers[entry]

        if self.req_version == 2:
            self.headers['version'] = '2'

            cipher, self.key, iv = self.encrypt(json.dumps(new_body))
            self.body = json.dumps({'params': json.dumps({'cipher': cipher, 'iv': iv})})

            region = self.properties.get('region', 0)
            protectedKey = crypto.generate_protectedKey(self.key, data.server_params[region]['pubKey'])
            negotiationVersion = data.server_params[region]['negotiationVersion']
            version = str(int(self.properties['time']) + (86400 * 1000))  # 1 day in the future

            self.headers['protectedKey'] = json.dumps({'SCENE_1': {'protectedKey': protectedKey, 'version': version, 'negotiationVersion': negotiationVersion}})
        else:
            cipher = self.encrypt(json.dumps(new_body))[0]
            self.body = json.dumps({'params': cipher})

        return self.body, self.headers, new_body

    def validate_response(self, response):
        if response.status_code != 200:
            raise RuntimeError(f"Response status mismatch, expected '200' got '{response.status_code}'!")
        elif json.loads(response.content).get('responseCode', 200) != 200:
            raise RuntimeError(f"Response status mismatch, expected '200' got '{json.loads(response.content)['responseCode']}' ({json.loads(response.content)['errMsg']})!")

    def validate_content(self, content):
        if 'checkFailReason' in content and content['checkFailReason'] != None:
            raise RuntimeError(f"Response contents mismatch, expected '{self.resp_key}' got '{content['checkFailReason']}'!")
