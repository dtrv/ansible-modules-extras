#!/usr/bin/python
# -*- coding: utf-8 -*-

# Ansible module to manage virtual machine images on SmartOS.
#
# Copyright (C) 2016 Thomas Verchow (thomas@verchow.com)
#
# This code is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This code is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
# or see <http://www.gnu.org/licenses/>.


DOCUMENTATION = '''
---
module: smartos_image
short_description: Manage SmartOS virtual machine images.
description:
    - Import and manage virtual machine images (datasets) on a SmartOS system. 
    - This module uses the C(imgadm import), C(imgadm delete), C(imgadm info)  
      and C(imgadm update). For detailed information see its manual page
      on U(https://smartos.org/man/1m/imgadm).
    - The management of image sources is not part of this module.
version_added: "2.3"
author: Thomas Verchow (@dtrv)
options:
    uuid:
        description:
            - The unique image identifier or a docker-repo:tag.
            - The common used C(name) is not used to avoid confusion with
              the name of the image - which is far from being unique.
        required: True
    state:
        description:
            - Indicate desired state of the image.
        required: false
        default: "present"
        choices: [ "present", "absent" ]
    zpool:
        description:
            - zpool of the image. The pool has to be present, which is 
              checked by C(zpool list).
        required: false
        default: "zones"
    update:
        description:
            - If C(True) and C(state=present), it tries to update the 
              image. Ignored otherwise.
        required: false
        default: false
        choices: ["true", "false"]
'''

EXAMPLES = '''
# Import 'debian-8' image 
smartos_image: uuid=d183f500-9a96-11e6-8976-ff3967dc023a

# Import or update 'debian-8' image 
smartos_image: uuid=d183f500-9a96-11e6-8976-ff3967dc023a update=True

# Import 'debian-8' image into pool 'newpool'
smartos_image: uuid=d183f500-9a96-11e6-8976-ff3967dc023a zpool=newpool

# Delete 'debian-8' image
smartos_image: uuid=d183f500-9a96-11e6-8976-ff3967dc023a state=absent
'''

RETURN = '''
uuid:
    description: Image idenifier.
    returned: always
    type: string
    sample: "d183f500-9a96-11e6-8976-ff3967dc023a"
state:
    description: Desired image status.
    returned: always
    type: string
    sample: "present"
zpool:
    description: zpool of the image.
    returned: always
    type: string
    sample: "zones"
manifest:
    description: JSON manifest of image with lots of information in it.
    returnd: If image is present.
    type: json
    sample: "{ name: ..., description: ..., ... }"
'''

import re
import json


class IMAGE(object):

    UUID_REGEX = r'^[a-f0-9]{8}-([a-f0-9]{4}-){3}[a-f0-9]{12}$'

    def __init__(self, module):
        self.module = module

        self.uuid     = module.params['uuid']
        self.state    = module.params['state']
        self.zpool    = module.params['zpool']
        self.update   = module.params['update']
        self.manifest = 'init'

    def is_local(self):
        cmd = [self.module.get_bin_path('imgadm', True)]
        cmd.append('info')
        if self.zpool:
            cmd.append('-P')
            cmd.append(self.zpool)
        cmd.append(self.uuid)

        (rc, info, _) = self.module.run_command(cmd)

        if rc == 0:
            self.manifest = json.loads(info)['manifest']
            return True
        else:
            return False


    def zpool_exists(self):
        cmd = [self.module.get_bin_path('zpool', True)]
        cmd.append('list')
        cmd.append(self.zpool)

        (rc, _, _) = self.module.run_command(cmd)

        return rc == 0

    def has_valid_uuid(self):
        uuid_re = re.match(self.UUID_REGEX, self.uuid)

        return uuid_re is not None

    def import_image(self):
        cmd = [self.module.get_bin_path('imgadm', True)]
        cmd.append('import')
        if self.zpool:
            cmd.append('-P')
            cmd.append(self.zpool)
        cmd.append(self.uuid)

        return self.module.run_command(cmd)

    def delete(self):
        cmd = [self.module.get_bin_path('imgadm', True)]
        cmd.append('delete')
        if self.zpool:
            cmd.append('-P')
            cmd.append(self.zpool)
        cmd.append(self.uuid)

        return self.module.run_command(cmd)

    def update(self):
        cmd = [self.module.get_bin_path('imgadm', True)]
        cmd.append('update')
        cmd.append(self.uuid)

        return self.module.run_command(cmd)






def main():
    module = AnsibleModule(
        argument_spec=dict(
            uuid   = dict(required = True),
            state  = dict(default = 'present', choices = ['present', 'absent']),
            zpool  = dict(default = 'zones'),
            update = dict(default = False, type = 'bool')
        ),
        supports_check_mode = True
    )

    image = IMAGE(module)

    result  = {'changed': False} # set to True if changes happen
    out     = ''
    err     = ''


# check if uuid is valid
# ---------------------------------------------------------
    if not image.has_valid_uuid():
        module.fail_json(
            msg = 'Invalid image UUID.', 
            uuid = image.uuid, 
            zpool = image.zpool)

# check if zpool exists
# ---------------------------------------------------------
    if not image.zpool_exists():
        module.fail_json(
            msg = 'zpool is not available.', 
            uuid = image.uuid, 
            zpool = image.zpool)

# state: present
# ---------------------------------------------------------
    if image.state == 'present':

        if module.check_mode:
            if image.is_local():
                out = 'Image %s (%s) is already installed, skipping.' % (image.uuid, image.manifest['name'])
            else:
                result['changed'] = True
                result['manifest'] = json.loads('{ "faked": "True", "reason": "check_mode" }')
                out = 'have to download image'
        else:
            (rc, out, err) = image.import_image()
            if rc != 0:
                module.fail_json(
                    msg = 'Error importing image!', 
                    uuid = image.uuid, 
                    zpool = image.zpool, 
                    rc = rc, 
                    stderr = str(err), 
                    stdout = str(out))
            if image.update:
                (rc, out, err) = image.update() 
                if rc != 0:
                    module.fail_json(
                        msg = 'Error updating image!', 
                        uuid = image.uuid, 
                        zpool = image.zpool, 
                        rc = rc, 
                        stderr = str(err), 
                        stdout = str(out))
           
# state: absent
# ---------------------------------------------------------
    if image.state == 'absent':

        if image.is_local():
            result['changed'] = True
            if not module.check_mode:
                (rc, out, err) = image.delete()
                if rc != 0:
                    module.fail_json(
                        msg = 'Error deleting image!', 
                        uuid = image.uuid, 
                        zpool = image.zpool, 
                        rc = rc, 
                        stderr = str(err), 
                        stdout = str(out))
        else:
            out = 'Image "%s" was not found on zpool "%s".' % (image.uuid, image.zpool)

# ---------------------------------------------------------
    result['stdout']   = str(out)
    result['stderr']   = str(err)
    result['uuid']     = image.uuid
    result['state']    = image.state
    result['zpool']    = image.zpool
    if image.is_local():
        result['manifest'] = image.manifest
        

    module.exit_json(**result)

from ansible.module_utils.basic import AnsibleModule
if __name__ == '__main__':
    main()

# vim: ts=4:sw=4:expandtab
