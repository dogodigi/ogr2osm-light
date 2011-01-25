#!/usr/bin/python
# -*- coding: utf-8 -*-

""" ogr2osm light
 python ogr2osm-l.py [filename]

 This is a stripped version of ogr2osm. It currently simply takes a filename and converts it to a .osm file containing nodes and ways

 Why this simplicity?
 Because it is almost impossible to maintain the complexity and validate stuff anywhere else then in one of the (pretty well maintained) OSM-editors
 The goal of this script is to create spaghetti that can be imported into one of the editors where it can be further processed and checked.
 Thanks to Iván Sánchez Ortega, 2009 <ivan@sanchezortega.es> for the initial stuff! Your beer will be waiting on the first time we meet.

 requirements: osgeo/ogr python bindings
"""


import sys
import getopt
from SimpleXMLWriter import XMLWriter

try:
	from osgeo import ogr
except:
	import ogr

try:
	from osgeo import osr
except:
	import osr

# Fetch command line parameters: file and source projection
try:
	(opts, args) = getopt.getopt(sys.argv[1:], "e:p:hvdt:a", ["epsg","proj4","help","verbose","debug-tags","attribute-stats","translation"])
except getopt.GetoptError:
	print __doc__
	sys.exit(2)
for opt, arg in opts:
	if opt in ("-h", "--help"):
		print __doc__
		sys.exit()
	elif opt in ("-p", "--proj4"):
		sourceProj4 = arg
		useProj4 = True
		useEPSG = False
		detectProjection = False
	elif opt in ("-e", "--epsg"):
		try:
			sourceEPSG = int(arg)
		except:
			print "Error: EPSG code must be numeric (e.g. '4326' instead of 'epsg:4326')"
			sys.exit(1)
		detectProjection = False
		useEPSG = True
		useProj4 = False
	elif opt in ("-v", "--verbose"):
		showProgress=True
	elif opt in ("-d", "--debug-tags"):
		debugTags=True
	elif opt in ("-a", "--attribute-stats"):
		attributeStats=True
		attributeStatsTable = {}
	elif opt in ("-t", "--translation"):
		translationMethod = arg
	else:
		print "Unknown option " + opt

file = args[0]

poDS = None
poDriver = None

poDS = ogr.Open( file, False ) #open datasource readonly, this prevents issues with read only datasets
if poDS is None:
	#sorry, cannot recognize this datasource
	print( "FAILURE:\n"
	"Unable to open datasource `%s' with the following drivers." % file )

	for iDriver in range(ogr.GetDriverCount()):
    		print( "  -> %s" % ogr.GetDriver(iDriver).GetName() )
	sys.exit() #halt

poDriver = poDS.GetDriver()

#create output filename
slashPosition = file.rfind('/')

if slashPosition != -1:
	outputFile = file[slashPosition+1:]
else:
	outputFile = file

outputFile = poDS.GetName() + '.osm'

dataSource = poDS; 

if dataSource is None:
	print 'Could not open ' + file
	sys.exit(1) #halt


print "Processing " + file + " (" + dataSource.GetDriver().GetName() + ") into " + outputFile

nodeIDsByXY  = {}
ways = {}
nodes = {}

elementIdCounter = -1

def addNode(x,y):
	"Given x,y, returns the ID of an existing node there, or creates it and returns the new ID. Node will be updated with the optional tags."
	global elementIdCounter, nodes, nodeIDsByXY
	
	if (x,y) in nodeIDsByXY:
		# Node already exists, merge tags
		#print
		#print "Warning, node already exists"
		nodeID = nodeIDsByXY[(x,y)]
		return nodeID
	else:
		# Allocate a new node
		nodeID = elementIdCounter
		elementIdCounter = elementIdCounter - 1
		
		nodeIDsByXY[(x,y)] = nodeID
		nodes[nodeID] = (x,y)
		return nodeID
	
def convertGeometry(geometry):
	"Given a linear geometry, will add or get nodeID's from the nodecollection and return a way object"
	
	result = []
	for k in range(0,geometry.GetPointCount()):
		(x,y,z) = geometry.GetPoint(k)
		node = addNode(x,y)
		result.append(node)
	return result


# Let's dive into the OGR data source and fetch the features

for i in range(dataSource.GetLayerCount()):
	layer = dataSource.GetLayer(i)
	layer.ResetReading()
	
	spatialRef = None
	spatialRef = layer.GetSpatialRef()

	if spatialRef == None:	# No source proj specified yet? Then default to do no reprojection.
		# Some python magic: skip reprojection altogether by using a dummy lamdba funcion. Otherwise, the lambda will be a call to the OGR reprojection stuff.
		reproject = lambda(geometry): None
	else:
		destSpatialRef = osr.SpatialReference()
		destSpatialRef.ImportFromEPSG(4326)	# Destionation projection will *always* be EPSG:4326, WGS84 lat-lon
		coordTrans = osr.CoordinateTransformation(spatialRef,destSpatialRef)
		reproject = lambda(geometry): geometry.Transform(coordTrans)
		

	for j in range(layer.GetFeatureCount()):
		feature = layer.GetNextFeature()
		geometry = feature.GetGeometryRef()
		
		# Do the reprojection (or pass if no reprojection is neccesary, see the lambda function definition)
		reproject(geometry)
		
		geometryType = geometry.GetGeometryType()
		subGeometries = []


		if geometry.GetGeometryCount() == 0:
			subGeometries = [geometry]
		else:	
			for k in range(geometry.GetGeometryCount()):
				subGeometries.append(geometry.GetGeometryRef(k))
		
		for geometry in subGeometries:
			if geometry.GetDimension() == 0:
				# 0-D = point
				if showProgress: sys.stdout.write(',')
				x = geometry.GetX()
				y = geometry.GetY()
				nodeID = addNode(x,y)
				
			elif geometry.GetDimension() == 1 or geometry.GetDimension() == 2:
				# linestring
				geomID = elementIdCounter
				elementIdCounter = elementIdCounter - 1
				way = convertGeometry(geometry)
				ways[geomID] = way

print "Generating OSM XML..."
w = XMLWriter(open(outputFile,'w'))
w.start("osm", version='0.6', generator='ogr2osm')

print "Generating "+ str(len(nodes)) + " nodes."
for (nodeID,(x,y)) in nodes.items():
	w.start("node", visible="true", id=str(nodeID), lat=str(y), lon=str(x))
	w.end("node")

print "Generating "+ str(len(ways)) + " ways."
for key in ways.keys():
	w.start('way', id=str(key), action='modify', visible='true')
	for node in ways[key]:
		w.element('nd',ref=str(node))
	w.end('way')		
print "All done. Enjoy your data!"
w.end("osm")
