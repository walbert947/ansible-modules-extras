#!/usr/bin/python
# -*- coding: utf-8 -*-

# pylint: disable=bad-whitespace,line-too-long,unused-wildcard-import,wildcard-import


"""
Copyright (C) 2015 CallFire Inc.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""



DOCUMENTATION = '''
---
module: gcdns_zone
short_description: Creates or removes zones in Google Cloud DNS
description:
    - Creates or removes managed zones in Google Cloud DNS
version_added: "2.0"
author: William Albert (@walbert947) <walbert@callfire.com>
requirements:
    - "python >= 2.6"
    - "apache-libcloud >= 0.16.0"
options:
    state:
        description:
            - Whether the given zone should or should not be present.
        required: false
        choices: ["present", "absent"]
        default: "present"
        version_added: "2.0"
    zone:
        description:
            - The DNS domain name of the zone.
        required: true
        default: null
        version_added: "2.0"
    description:
        description:
            - An arbitrary text string to use for the zone description.
        required: false
        default: ""
        version_added: "2.0"
    require_extra:
        description:
            - Determines if the value of the extra parameters are considered
              when checking to see if the given zone exists. This setting is
              only used when creating zones.
            - Google Cloud DNS cannot update a zone's configuration in place,
              so certain extra parameters (e.g., description, TTL, etc.) can
              only be set when the zone is created. This setting controls
              whether deviations in the configuration of the extra parameters
              are ignored or considered a failure.
            - If this setting is set to "yes", the module will check the extra
              parameters of an existing zone to see if it matches the extra
              parameters of the desired zone, and will fail if any differences
              are detected or the extra parameters cannot be checked. If this
              setting is set to "no", the module will only use the domain name
              in determining whether to make a configuration change.
        required: false
        choices: ["yes", "no"]
        default: "no"
        version_added: "2.0"
    service_account_email:
        description:
            - The e-mail address for a service account with access to Google
              Cloud DNS.
        required: false
        default: null
        version_added: "2.0"
    pem_file:
        description:
            - The path to the PEM or JSON file with the service account's
              private key.
        required: false
        default: null
        version_added: "2.0"
    project_id:
        description:
            - The Google Cloud Platform project ID to use.
        required: false
        default: null
        version_added: "2.0"
'''

EXAMPLES = '''
# Basic zone creation example.
- name: Create a basic zone with the minimum number of parameters.
  gcdns_zone: zone=foo.com
  
# Zone removal example.
- name: Remove a zone.
  gcdns_zone: zone=foo.com
              state=absent

# Zone creation using module-based GCE authentication.
- name: Using the module's GCE authentication options.
  gcdns_zone: zone=foo.com
              service_account_email=unique-email@developer.gserviceaccount.com
              pem_file=/path/to/pem_file
              project_id=project-id

# Zone creation with description
- name: Creating a zone with a description/
  gcdns_zone: zone=bar.com
              description="This is an awesome zone"

# Zone creation that ignores extra parameters
# Assuming the above example ran, this example will report as OK
# with no changes.
- name: Creating a zone, and ignoring differences in extra parameters
  gcdns_zone: zone=bar.com
              description="Actually, this zone isn't that great..."
              require_extra=no

# Zone creation that requires matching extra parameters
# Assuming the above example ran, this example will report as failed.
- name: Creating a zone, and requiring that extra parameters by the same
  gcdns_zone: zone=bar.com
              description="Actually, this zone isn't that great..."
              require_extra=yes
'''



from pprint import pprint

try:
    from libcloud.dns.types import Provider
    from libcloud.dns.providers import get_driver
    from libcloud.common.google import InvalidRequestError, ResourceExistsError
    from libcloud.common.google import ResourceNotFoundError
    PROVIDER = Provider.GOOGLE
    HAS_LIBCLOUD = True
except ImportError:
    HAS_LIBCLOUD = False



def create_zone(module, gcdns, zone):
    """Creates a new zone."""

    description   = module.params['description']
    extra         = dict(description = description)
    require_extra = module.boolean(module.params['require_extra'])
    zone_name     = module.params['zone']

    # Google Cloud DNS wants the trailing dot on the domain name.
    if zone_name[-1] != '.':
        zone_name = zone_name + '.'

    # If we got a zone back, then the domain exists.
    if zone is not None and not require_extra:
        # We don't care about the extra parameters. The zone we want to
        # create already exists, so we're done.
        return False
    elif zone is not None and require_extra:
        # We care about the extra parameters. We need to check if they match.
        if zone.extra['description'] != description:
            module.fail_json(msg='Existing zone description differs and cannot be updated', changed=False)

        # The extra params match, so we're done here.
        return False

    # We didn't get a zone back, so it doesn't exist. Let's create it!
    try:
        if not module.check_mode:
            gcdns.create_zone(domain=zone_name, extra=extra)

        return True

    except ResourceExistsError:
        # The zone already exists. We checked for this already, so either
        # Google is lying, or someone was a ninja and created the zone
        # within milliseconds of us checking for its existence.
        if require_extra:
            module.fail_json(msg='The zone already exists, but params could not be verified', changed=False)
        else:
            return False

    except InvalidRequestError, error:
        # This error can have multiple causes.

        # The zone name or a parameter might be completely invalid.
        if error.code == 'invalid':
            module.fail_json(msg='The zone name, or a parameter, was invalid', changed=False)

        # Google Cloud DNS will refuse to create zones with certain domain
        # names, such as TLDs, ccTLDs, or special domain names such as
        # example.com.
        if error.code == 'managedZoneDnsNameNotAvailable':
            module.fail_json(msg='The zone name is reserved', changed=False)

        # Something else failed. I don't know what that could be, so I'll
        # treat it as a generic error.
        raise

def remove_zone(module, gcdns, zone):
    """Removes an existing zone, if present."""

    # If there's no zone, then we're obviously done.
    if zone is None:
        return False

    # An empty zone will have two resource records:
    #   1. An NS record with a list of authoritative name servers
    #   2. An SOA record
    # If any additional resource records are present, Google Cloud DNS will
    # refuse to remove the zone.
    if len(zone.list_records()) > 2:
        module.fail_json(msg='Cannot remove non-empty zone: %s' % zone.domain, changed=False)

    try:
        if not module.check_mode:
            gcdns.delete_zone(zone)

        return True

    except ResourceNotFoundError:
        # When we performed our check, the zone existed. It may have been
        # deleted by something else. It's gone, so whatever.
        return False

    except InvalidRequestError, error:
        # When we performed our check, the zone existed and was empty. In the
        # milliseconds between the check and the removal command, records were
        # added to the zone.
        if error.code == 'containerNotEmpty':
            module.fail_json(msg='Cannot remove non-empty zone: %s' % zone.domain, changed=False)

        # Something else broke. We'll treat it as a generic error.
        raise



def _get_zone(gcdns, zone_name):
    """Gets the zone ID for a given domain name."""

    # To create a zone, we need to supply a zone name. However, to delete a
    # zone, we need to supply a zone ID. Zone ID's are often based on zone
    # names, but that's not guaranteed, so we'll iterate through the list of
    # zones to see if we can find a matching name.
    available_zones = gcdns.iterate_zones()
    found_zone      = None

    for zone in available_zones:
        if zone.domain == zone_name:
            found_zone = zone
            break

    return found_zone

def _unexpected_error_msg(error):
    """Create an error string based on passed in error."""

    return 'Unexpected response: ' + pprint.pformat(vars(error))



def main():
    """Main function"""

    module = AnsibleModule(
        argument_spec = dict(
            state                 = dict(required=False, default='present', choices=['present', 'absent'], type='str'),
            zone                  = dict(required=True, type='str'),
            description           = dict(required=False, default='', type='str'),
            require_extra         = dict(required=False, default=False, choices=BOOLEANS, type='str'),
            service_account_email = dict(required=False, default=None, type='str'),
            pem_file              = dict(required=False, default=None, type='str'),
            project_id            = dict(required=False, default=None, type='str'),
        ),
        supports_check_mode = True
    )

    zone_name = module.params['zone']
    state     = module.params['state']

    json_output = dict(
        state                 = state,
        zone                  = zone_name,
        description           = module.params['description'],
        require_extra         = module.boolean(module.params['require_extra']),
        service_account_email = module.params['service_account_email'],
        pem_file              = module.params['pem_file'],
        project_id            = module.params['project_id']
    )

    # Technically, libcloud 0.15.0 is the minimum required version, but libcloud
    # 0.16.0 introduced ResourceExistsError, which we use, so I'm considering
    # that to be the minimum acceptable version.
    if not HAS_LIBCLOUD:
        module.fail_json(msg='libcloud with Google Cloud DNS support (0.16.0+) is required for this module', changed=False)

    # Google Cloud DNS wants the trailing dot on the domain name.
    if zone_name[-1] != '.':
        zone_name = zone_name + '.'

    # Build a connection object that was can use to connect with Google
    # Cloud DNS.
    gcdns = gce_connect(module, provider=PROVIDER)

    # We need to check if the zone we're attempting to create already exists.
    zone = _get_zone(gcdns, zone_name)

    try:
        if state == 'present':
            changed = create_zone(module, gcdns, zone)
        elif state == 'absent':
            changed = remove_zone(module, gcdns, zone)
        else:
            module.fail_json(msg='Unknown state : %s' % state, changed=False)
    except Exception, error:
        module.fail_json(msg=_unexpected_error_msg(error), changed=False)

    module.exit_json(changed=changed, **json_output)

from ansible.module_utils.basic import *
from ansible.module_utils.gce import *
if __name__ == '__main__':
    main()
