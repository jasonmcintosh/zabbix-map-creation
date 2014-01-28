#!/usr/bin/python
# -*- coding: utf-8 -*-
# Volker Fröhlich, 2013
# volker27@gmx.at

"""
Creates a Zabbix map from a Dot file
zbximage and hostname are custom attributes that can be attached to nodes.
Nodes with a hostname attribute are considered Zabbix hosts and looked up
for. Other nodes are treated as images. zbximage and label can be used there.
Edges have their color and label attributes considered.

This script is meant as an example only!
"""

# Curly brace edge notation requires a patched networkx module
# https://github.com/networkx/networkx/issues/923

import networkx as nx
import optparse
import sys
from zabbix_api import ZabbixAPI
parser = optparse.OptionParser()
parser.add_option('--username', help="Username", default="admin")
parser.add_option('--password', help="Password", default="zabbix")
parser.add_option('--host', help="Host To talk to the web api", default="localhost")
parser.add_option('--path', help="Path", default="/zabbix/")
parser.add_option('--mapfile', help=".dot graphviz file for imput", default="data.dot")
parser.add_option('--mapname', help="Map name to put into zabbix")
(options,args)=parser.parse_args()

if not options.mapname:
	print "Must have a map name!"
	sys.exit(-1)

width = 1920 
height = 1280

ELEMENT_TYPE_HOST = 0
ELEMENT_TYPE_MAP = 1
ELEMENT_TYPE_TRIGGER = 2
ELEMENT_TYPE_HOSTGROUP = 3
ELEMENT_TYPE_IMAGE = 4

ADVANCED_LABELS = 1
LABEL_TYPE_LABEL = 0

#TODO: Available images should be read via the API instead
#icons = {
    #"router": 130,
    #"cloud": 26,
    #"desktop": 27,
    #"laptop": 28,
    #"server": 106,
    #"database": 20,
    #"sat": 30,
    #"tux": 31,
    #"default": 40,
    #"house":34
#}

colors = {
    "purple": "FF00FF",
    "green": "00FF00",
    "default": "00FF00",
}

def icons_get():
    icons = {}
    iconsData = zapi.icons.get({"output":["imageid","name"]})
	for icon in iconsData[result]:
		icons[icon["name"]] = icon["imageid"]

def api_connect():
    zapi = ZabbixAPI(server=options.host, path=options.path, log_level=1)
    zapi.login(options.username, options.password)
    return zapi

def host_lookup(hostname):
    hostid = zapi.host.get({"filter": {"host": hostname}})
    if hostid:
        return str(hostid[0]['hostid'])

################################################################

# Convert your dot file to a graph
G=nx.read_dot(options.mapfile)

# Use an algorithm of your choice to layout the nodes in x and y
pos = nx.graphviz_layout(G)

# Find maximum coordinate values of the layout to scale it better to the desired output size
#TODO: The scaling could probably be solved within Graphviz
# The origin is different between Zabbix (top left) and Graphviz (bottom left)
# Join the temporary selementid necessary for links and the coordinates to the node data
poslist=list(pos.values())
maxpos=map(max, zip(*poslist))
    
for host, coordinates in pos.iteritems():
   pos[host] = [int(coordinates[0]*width/maxpos[0]*0.65-coordinates[0]*0.1), int((height-coordinates[1]*height/maxpos[1])*0.65+coordinates[1]*0.1)]
nx.set_node_attributes(G,'coordinates',pos)

selementids = dict(enumerate(G.nodes_iter(), start=1))
selementids = dict((v,k) for k,v in selementids.iteritems())
nx.set_node_attributes(G,'selementid',selementids)

# Prepare map information
map_params = {
    "name": options.mapname,
    "label_format": ADVANCED_LABELS,
    "label_type_image": LABEL_TYPE_LABEL,
    "width": width,
    "height": height
}
element_params=[]
link_params=[]

zapi = api_connect()

# Prepare node information
for node, data in G.nodes_iter(data=True):
    # Generic part
    map_element = {}
    map_element.update({
            "selementid": data['selementid'],
            "x": data['coordinates'][0],
            "y": data['coordinates'][1],
            "use_iconmap": 0,
            })

    if "hostname" in data:
        map_element.update({
                "elementtype": ELEMENT_TYPE_HOST,
                "elementid": host_lookup(data['hostname'].strip('"')),
                "iconid_off": icons['server'],
                })
    else:
        map_element.update({
            "elementtype": ELEMENT_TYPE_IMAGE,
            "elementid": 0,
        })
    # Labels are only set for images
    # elementid is necessary, due to ZBX-6844
    # If no image is set, a default image is used
    if "label" in data:
        map_element.update({
            "label": data['label'].strip('"')
        })
    if "zbximage" in data:
        map_element.update({
            "iconid_off": icons[data['zbximage'].strip('"')],
        })
    elif "hostname" not in data and "zbximage" not in data:
        map_element.update({
            "iconid_off": icons['default'],
        })

    element_params.append(map_element)

# Prepare edge information -- Iterate through edges to create the Zabbix links,
# based on selementids
nodenum = nx.get_node_attributes(G,'selementid')
for nodea, nodeb, data in G.edges_iter(data=True):
    link = {}
    link.update({
        "selementid1": nodenum[nodea],
        "selementid2": nodenum[nodeb],
        })

    if "color" in data:
        color =  colors[data['color'].strip('"')]
        link.update({
            "color": color
        })
    else:
        link.update({
            "color": colors['default']
        })

    if "label" in data:
        label =  data['label'].strip('"')
        link.update({
            "label": label,
        })

    link_params.append(link)

# Join the prepared information
map_params["selements"] = element_params
map_params["links"] = link_params
    
# Get rid of an existing map of that name and create a new one
del_mapid = zapi.map.get({"filter": {"name": options.mapname}})
if del_mapid:
    zapi.map.delete([del_mapid[0]['sysmapid']])

map=zapi.map.create(map_params)
