import config
import numpy as np
from .forms import InputForm
from app import app
from flask import render_template, request, redirect, url_for

import folium
from geopy.distance import EARTH_RADIUS
from geopy.geocoders import GoogleV3

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from photodb import Photo

from shapely import wkb

from routedb import RouteDB, Node, Waypoint
from route_optimizer import RoutingGraph

from collections import defaultdict

colors = [
    "#7fc97f",
    "#beaed4",
    "#fdc086",
    "#ffff99",
    "#386cb0",
    "#f0027f",
    "#bf5b17",
    "#666666",
]

geolocator = GoogleV3()

engine = create_engine('postgresql://localhost/photodb')
Session = sessionmaker(bind=engine)
session = Session()

db = RouteDB('postgresql://localhost/routesc')


def ll2wkt(lat, lon):
    return 'POINT({} {})'.format(lon, lat)


def wkb2ll(b):
    loc = wkb.loads(b)
    return loc.x, loc.y



@app.route('/', methods=['GET','POST'])
@app.route('/index', methods=['GET','POST'])
def input():
    form = InputForm(request.form)

    if request.method == 'POST' and form.validate():
        return redirect(url_for('output',
                        address1=form.address1.data,
                        address2=form.address2.data))

    return render_template("index.html", map_name='map.html', form=form)


#conversion = dict(mi=1609.34, km=1000)

@app.route('/output', methods=['GET','POST'])
def output():
    form = InputForm(request.form)
    address1 = request.args.get('address1')
    address2 = request.args.get('address2')
    #units = request.args.get('units')

    #distance_meters = conversion[units]*distance

    loc1 = geolocator.geocode(address1)
    loc2 = geolocator.geocode(address2)

    latlon1 = np.array([loc1.latitude, loc1.longitude])
    latlon2 = np.array([loc2.latitude, loc2.longitude])
    latlon_center = 0.5*(latlon1 + latlon2)

    bmap = folium.Map(
        location=tuple(latlon_center),
        zoom_start=14
    )

    bmap.simple_marker(location=latlon1)
    bmap.simple_marker(location=latlon2)

    point1 = ll2wkt(*latlon1)
    point2 = ll2wkt(*latlon2)

    query = session.query(Photo)

    for photo in query:
        color = colors[photo.label % len(colors)]
        bmap.circle_marker(
            location=wkb2ll(bytes(photo.location.data)),
            popup='<img src={url} width=200 height=200>'.format(url=photo.url),
            fill_color=color,
            line_color=color,
            radius=20
        )

    ####################
    # find optimal route

    db = RouteDB('postgresql:///scenicsf')

    try:
        node1 = db.nearest_rnodes(loc1.latitude, loc1.longitude, 500).first()
        node2 = db.nearest_rnodes(loc2.latitude, loc2.longitude, 500).first()
    except:
        raise # TODO

    waypoints = defaultdict(list)

    for wp in db.get_waypoints(node1, node2):
        waypoints[wp.way_id].append(wp)

    G = RoutingGraph()

    for way_id, wps in waypoints.items():
        G.add_way(wps)

    nodes, edges = G.get_optimal_path(node1.id, node2.id)

    for edge in edges:
        nodes = (
            db.session.query(Node.loc)
            .join(Waypoint)
            .filter((Waypoint.way_id == edge['way_id']) &
                    (Waypoint.idx >= edge['i']) &
                    (Waypoint.idx <= edge['j'])))
        
        xy = []
        for node in nodes:
            loc = wkb.loads(bytes(node.loc.data))
            xy.append((loc.y, loc.x))
            
        bmap.line(xy)
        
    map_name = 'map-output.html'
    map_path = '{}/templates/{}'.format(config.base_url, map_name)
    bmap.create_map(path=map_path)

    return render_template("index.html", map_name=map_name, form=form)
