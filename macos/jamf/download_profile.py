#!/usr/bin/env python

from __future__ import print_function
import base64, json, getopt, os, sys
import xml.dom.minidom

try:
    import urllib.parse as urllibquote
    import urllib.request as urllibreq
except:
    import urllib as urllibquote
    import urllib2 as urllibreq

def usage(err = None):
    if err:
        print(err, file = sys.stderr)
        print('', file = sys.stderr)
        
    print ("""Usage: %s --server=url --name=profile --user=username [ --password=password ]
    --server=https://instance.jamfcloud.com    : JAMF server URL
    --name='Defender onboarding settings'      : macOS Configuration Profile
    --user=admin                               : JAMF user name
    --password=12345                           : JAMF password
    --help (or -h): Print out this help page and exit

This tool downloads specified profile from JAMF server to stdout
""" % sys.argv[0], file=sys.stderr)

def query_jamf_profile(url, user, password, name):
    credentials = base64.b64encode('{}:{}'.format(user, password).encode('ISO-8859-1'))
    url = '{}/JSSResource/osxconfigurationprofiles/name/{}'.format(url, urllibquote.quote(name))

    req = urllibreq.Request(url)
    req.add_header('Accept', 'application/json')
    req.add_header('authorization', 'Basic ' + credentials.decode())

    return urllibreq.urlopen(req).read()

url = None
user = None
password = None
name = None

try:
    opts, args = getopt.getopt(sys.argv[1:], 'hs:u:p:n:', ['help', 'server=', 'user=', 'password=', 'name='])

    for k, v in opts:
        if k == '-s' or k == '--server':
            url = v

        if k == '-u' or k == '--user':
            user = v

        if k == '-p' or k == '--password':
            password = v

        if k == '-n' or k == '--name':
            name = v

        if k == '-h' or k == '--help':
            usage()
            exit(0)

except getopt.GetoptError as e:
    usage(e)
    exit(2)

if not url:
    usage('No server URL specified')
    exit(1)

if not user:
    usage('No user specified')
    exit(1)

if not name:
    usage('No profile name specified')
    exit(1)

if not password:
    import getpass
    password = getpass.getpass('JAMF Password: ')

content = query_jamf_profile(url, user, password, name)
data = json.loads(content)
payloads = data['os_x_configuration_profile']['general']['payloads']
dom = xml.dom.minidom.parseString(payloads)
print(dom.toprettyxml())

