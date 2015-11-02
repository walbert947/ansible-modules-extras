#!/usr/bin/python
# -*- coding: utf-8 -*-

# pylint: disable=bad-whitespace,line-too-long,unused-wildcard-import,wildcard-import


"""
Copyright (C) 2015 CallFire Inc.

This file is part of Ansible.

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
module: gcdns_record
short_description: Creates or removes records in Google Cloud DNS
description:
    - Creates or removes records in Google Cloud DNS.
version_added: "2.0"
author: "William Albert (@walbert947) <walbert@callfire.com>"
requirements:
    - "python >= 2.6"
    - "apache-libcloud >= 0.16.0"
options:
    state:
        description:
            - Whether the given resource record should or should not be present.
        required: false
        choices: [ "present", "absent" ]
        default: "present"
    record:
        description:
            - The fully-qualified DNS name of the resource record.
        required: true
        aliases: [ "name" ]
    zone:
        description:
            - The DNS domain name of the zone for the resource record.
        required: true
    type:
        description:
            - The type of resource record to add (A, MX, CNAME, ...).
            - See U(https://cloud.google.com/dns/what-is-cloud-dns#supported_record_types)
              for the record types that Google Cloud DNS supports.
            - "Note: NAPTR records are not supported by this module."
        required: true
    values:
        description:
            - The values to use for the resource record. All resource records
              that include DNS domain names in the value field (e.g., CNAME,
              PTR, and SRV records) must include a trailing dot.
            - Valid values will differ depending on the record type. See
              U(https://cloud.google.com/dns/what-is-cloud-dns#supported_record_types)
              for a list of example values for each record type. Values are
              located inside the 'rrdatas' section.
            - For resource records that have the same name but different
              values (e.g., multiple MX records, or multiple A records for use
              with round-robin DNS), the must be defined as multiple list
              entries in a single record.
            - If the state is 'absent' and overwrite is 'yes', this parameter
              will be ignored and can simply be provided with an empty list.
        required: true
    ttl:
        description:
            - The amount of time, in seconds, that a resource record will
              remain cached by a caching nameserver.
        required: false
        default: 300
    overwrite:
        description:
            - Whether an attempt to overwrite an existing record should succeed
              or fail. The behavior of this option depends on the state.
            - If the state is 'present' and overwrite is set to 'yes', this
              module will replace an existing resource record of the same name
              with the provided values. If the state is 'present' and overwrite
              is set to 'no', this module will fail if there exists a resource
              record with the same name and type, but different data.
            - If the state is 'absent' and overwrite is set to 'yes', this
              module will remove the given resource record unconditionally.
              If the state is 'absent' and overwrite is set to 'no', this
              module will fail if the provided values do not match exactly
              with the existing resource record's values.
        required: false
        choices: ["yes", "no"]
        default: "no"
    service_account_email:
        description:
            - The e-mail address for a service account with access to Google
              Cloud DNS.
        required: false
        default: null
    pem_file:
        description:
            - The path to the PEM or JSON file with the service account's
              private key.
        required: false
        default: null
    project_id:
        description:
            - The Google Cloud Platform project ID to use.
        required: false
        default: null
'''

EXAMPLES = '''
# Create a simple A record.
- name: Add an A record to the zone foo.com
  gcdns_record:
    record: foo.com
    zone: foo.com
    type: A
    values: [1.2.3.4]

# Remove a simple A record.
- name: Remove an A record from the zone foo.com
  gcdns_record:
    state: absent
    record: old.foo.com
    zone: foo.com
    type: A
    values: [9.8.7.6]

# Create a CNAME record.
- name: Add a CNAME record to the zone foo.com
  gcdns_record:
    record: www.foo.com
    zone: foo.com
    type: A
    values: ['foo.com.']  # Note the trailing dot

# Create an MX record with a custom TTL.
- name: Remove an MX record from the zone foo.com
  gcdns_record:
    state: absent
    record: foo.com
    zone: foo.com
    type: MX
    ttl: 3600
    values: ['10 mail.foo.com.']  # Note the trailing dot

# Create multiple A records with the same name.
- name: Add multiple A records with the same name to the zone foo.com
  gcdns_record:
    record: time.foo.com
    zone: foo.com
    type: A
    values:
      - 10.1.2.3
      - 10.4.5.6
      - 10.7.8.9
      - 192.168.5.10

# Change the value of an existing record.
- name: Remove an A record from the zone foo.com
  gcdns_record:
    record: mail.foo.com
    zone: foo.com
    type: A
    overwrite: yes
    values: [5.6.7.8]
'''



from pprint import pprint

try:
    from libcloud.dns.types import Provider
    from libcloud.dns.providers import get_driver
    from libcloud.dns.types import RecordDoesNotExistError
    from libcloud.common.google import InvalidRequestError
    PROVIDER = Provider.GOOGLE
    HAS_LIBCLOUD = True
except ImportError:
    HAS_LIBCLOUD = False



def create_record(module, gcdns, zone, record, ):
    """Creates or overwrites a resource record."""

    overwrite   = module.boolean(module.params['overwrite'])
    record_name = module.params['record']
    record_type = module.params['type']
    ttl         = module.params['ttl']
    values      = module.params['values']
    data        = dict(ttl = ttl, rrdatas = values)

    # Google Cloud DNS wants the trailing dot on all DNS names.
    if record_name[-1] != '.':
        record_name = record_name + '.'

    # If we found a record, we need to investigate.
    if record is not None:
        # The record exists; does it match the record we want to create?
        matches = True
        if ttl != record.data['ttl'] or values != record.data['rrdatas']:
            matches = False

        # If the record matches, we obviously don't have to change anything.
        if matches:
            return False

        # The record doesn't match, so we need to check if we can overwrite it.
        if not overwrite:
            module.fail_json(msg='This record already exists, and overwrite protection is enabled', changed=False)

    # The record either doesn't exist, or it exists and we can overwrite it.
    if not module.check_mode:
        if record is None:
            # There's no existing record, so we'll just create it.
            try:
                gcdns.create_record(record_name, zone, record_type, data)
            except InvalidRequestError, error:
                # We probably got this error because the value is invalid for
                # the given record type (e.g., "www.example.com." as a value
                # for an 'A' record).
                if error.code == 'invalid':
                    module.fail_json(msg='The value is invalid for the given type',  changed=False)

                # Some other error? We'll treat it as a generic error.
                raise
        else:
            # Google Cloud DNS doesn't support updating a record in place,
            # so if the record already exists, we need to delete it and
            # recreate it using the new information.
            gcdns.delete_record(record)

            try:
                gcdns.create_record(record_name, zone, record_type, data)
            except Exception:
                # Something blew up when creating the record. This will usually
                # be a result of invalid value data in the new record.
                # Unfortunately, we already changed the state of the record by
                # deleting the old one, we we'll try to roll back before
                # failing out.
                try:
                    gcdns.create_record(record.name, record.zone, record.type, record.data)
                    module.fail_json(msg='The attempt to overwrite the record failed due to an error, and the existing record was restored.', changed=False)
                except Exception:
                    # We deleted the old record, couldn't create the new record,
                    # and couldn't roll back. That really sucks.
                    module.fail_json(msg='The attempt to overwrite the record failed due to an error, and the existing record was lost.', changed=True)

    return True

def remove_record(module, gcdns, record):
    """Remove a resource record."""

    overwrite = module.boolean(module.params['overwrite'])
    ttl       = module.params['ttl']
    values    = module.params['values']

    # If there is no record, we're obviously done.
    if record is None:
        return False

    # If there is an existing record, do our values match the values of the
    # existing record?
    if not overwrite:
        if values != record.data['rrdatas'] or ttl != record.data['ttl']:
            module.fail_json(msg='Overwrite protection is enabled, and the given values do not match the existing values', changed=False)

    # If we got to this point, we're okay to delete the record.
    if not module.check_mode:
        gcdns.delete_record(record)

    return True



def _get_record(gcdns, zone, record_type, record_name):
    """Gets the record object for a given FQDN."""

    # The record ID is a combination of its type and FQDN. For example, the
    # ID of an A record for www.example.com would be 'A:www.example.com.'
    record_id = "%s:%s" % (record_type, record_name)

    try:
        return gcdns.get_record(zone.id, record_id)
    except RecordDoesNotExistError:
        return None

def _get_zone(gcdns, zone_name):
    """Gets the zone object for a given domain name."""

    # To create a zone, we need to supply a domain name. However, to find a
    # zone, we need to supply a zone ID. Zone ID's are often based on domain
    # names, but that's not guaranteed, so we'll iterate through the list of
    # zones to see if we can find a matching domain name.
    available_zones = gcdns.iterate_zones()
    found_zone = None

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
            state                 = dict(default='present', choices=['present', 'absent'], type='str'),
            record                = dict(required=True, type='str', aliases=['name']),
            zone                  = dict(required=True, type='str'),
            type                  = dict(required=True, type='str'),
            values                = dict(required=True, type='list'),
            ttl                   = dict(default=300, type='int'),
            overwrite             = dict(default=False, choices=BOOLEANS, type='str'),
            service_account_email = dict(default=None, type='str'),
            pem_file              = dict(default=None, type='str'),
            project_id            = dict(default=None, type='str'),
        ),
        supports_check_mode = True
    )

    record_name = module.params['record']
    record_type = module.params['type']
    state       = module.params['state']
    ttl         = module.params['ttl']
    zone_name   = module.params['zone']

    json_output = dict(
        state                 = state,
        record                = record_name,
        zone                  = zone_name,
        type                  = record_type,
        values                = module.params['values'],
        ttl                   = ttl,
        overwrite             = module.boolean(module.params['overwrite']),
        service_account_email = module.params['service_account_email'],
        pem_file              = module.params['pem_file'],
        project_id            = module.params['project_id']
    )

    # Technically, libcloud 0.15.0 is the minimum required version, but libcloud
    # 0.16.0 introduced ResourceExistsError, which we use, so I'm considering
    # that to be the minimum acceptable version.
    if not HAS_LIBCLOUD:
        module.fail_json(msg='libcloud with Google Cloud DNS support (0.16.0+) is required for this module', changed=False)

    # Google Cloud DNS wants the trailing dot on all DNS names.
    if zone_name[-1] != '.':
        zone_name = zone_name + '.'
    if record_name[-1] != '.':
        record_name = record_name + '.'

    # Build a connection object that was can use to connect with Google
    # Cloud DNS.
    gcdns = gce_connect(module, provider=PROVIDER)

    # We need to ensure that Google Cloud DNS supports the type of record
    # the user wants to create. I'm doing the check here rather than in a
    # 'choices' parameter because the list of supported record types is
    # large and subject to change.
    if record_type not in gcdns.RECORD_TYPE_MAP.keys():
        module.fail_json(msg='Record type is not supported', changed=False)

    # A negative TTL is just crazy talk.
    if ttl < 0:
        module.fail_json(msg='TTL cannot be less than zero', changed=False)

    # We need to check that the zone we're creating a record for actually
    # exists.
    zone = _get_zone(gcdns, zone_name)
    if zone is None:
        module.fail_json(msg='The zone was not found: %s' % zone_name, changed=False)

    # We also need to check if the record we want to create or remove actually
    # exists.
    try:
        record = _get_record(gcdns, zone, record_type, record_name)
    except InvalidRequestError:
        # We gave Google Cloud DNS an invalid DNS record name.
        module.fail_json(msg='The record name is invalid: %s' % record_name, changed=False)

    try:
        if state == 'present':
            changed = create_record(module, gcdns, zone, record)
        elif state == 'absent':
            changed = remove_record(module, gcdns, record)
        else:
            module.fail_json(msg='Unknown state : %s' % state, changed=False)
    except Exception, error:
        module.fail_json(msg=_unexpected_error_msg(error), changed=False)

    module.exit_json(changed=changed, **json_output)

from ansible.module_utils.basic import *
from ansible.module_utils.gce import *
if __name__ == '__main__':
    main()
