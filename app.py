import sys
from dash import Dash, dcc, html, dash_table
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
from datetime import date
from dash.dependencies import Input, Output
import geopandas as gpd
import psycopg2
from psycopg2 import OperationalError
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import sqlalchemy as db
import dash_leaflet as dl
import dash_leaflet.express as dlx
from dash_extensions.javascript import assign
import json
from env import sqlPassword
from shapely.geometry import shape


def create_connection(db_name, db_user, db_password, db_host, db_port):
    connection = None
    try:
        connection = psycopg2.connect(
            database=db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port,
        )
        print("Connection to PostgreSQL DB successful")
    except OperationalError as e:
        print(f"The error '{e}' occurred")
    return connection

connection = create_connection(
    "gina", "dba", sqlPassword, "pancake.x.gina.alaska.edu", "5432"
)
connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

with open("/Users/ojlarson/Documents/Dash/assets/Alaska_Borough_and_Census_Ar.geojson") as f:
    geojson = json.load(f)
geobuf = dlx.geojson_to_geobuf(geojson)

point_to_layer = assign("""function(feature, latlng, context) {
    options={
        radius:4,
        fillColor: "red",
        color: "#000",
        fillOpacity: 1,
        weight: 1
    };
    return L.circleMarker(latlng, options);}""")

app = Dash(external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = html.Div(
    [
        dbc.Row(
            [
                dbc.Col(
                    [
                    html.H1("Fire Point Statistics by Borough")
                    ], width={"size": 6, "offset": 1}
                ),
                dbc.Col(
                    [
                        dcc.DatePickerRange(
                        id='my-date-picker-range',
                        min_date_allowed=date(2022, 1, 1),
                        max_date_allowed=date(2022, 12, 31),
                        initial_visible_month=date(2022, 4, 1),
                        end_date=date(2022, 4, 25),
                        start_date=date(2022, 4, 20)
                        ),
                        html.Br(),        
                        html.Div(id = 'output-container-date-picker-range'),
                        html.Br()
                    ], width={"size": 4}
                ),
            ]
        ),
        dbc.Row(
            [
                dbc.Col(
                    dl.Map(
                        [
                            dl.LayersControl(
                                [
                                    dl.BaseLayer(
                                        dl.TileLayer(),
                                        name="OpenStreetMaps",
                                        checked=True,
                                    ),
                                    dl.BaseLayer(
                                        dl.TileLayer(
                                            url="https://www.ign.es/wmts/mapa-raster?request=getTile&layer=MTN&TileMatrixSet=GoogleMapsCompatible&TileMatrix={z}&TileCol={x}&TileRow={y}&format=image/jpeg",
                                            attribution="IGN",
                                        ),
                                        name="IGN",
                                        checked=False,
                                    ),
                                    dl.Overlay(
                                        dl.GeoJSON(data=geobuf, format="geobuf", options={"style":{"color":"red", "fill":False, "weight":1}}, id="boroughs", zoomToBoundsOnClick=True),
                                        name="Boroughs",
                                        checked=True
                                    ),
                                    dl.Overlay(
                                        dl.GeoJSON(options=dict(pointToLayer=point_to_layer),
                                             id='firePoints', hideout=dict(circleOptions=dict(color="red"))),
                                        name="Fire Points",
                                        checked=True
                                    ),
                                ],
                            ),
                            dl.FeatureGroup([
                                dl.EditControl(id="edit_control")
                            ])
                        ],
                        id="leaflet_map",
                        zoom=4,
                        center=(64, -152),
                        style={'width': '100%', 'height': '60vh', 'margin': "auto", "display": "block"},
                        
                    ),
                width={"size": 6, "offset": 1}),
                dbc.Col(dash_table.DataTable(
                    id='stats',
                    columns=[{'name': "Borough", 'id': "Borough"}, {'name': "# of fire points", 'id': "# of fire points"}]
                    ), width = 2, align = "top"),
            ]
        ),
        dbc.Row(
            html.Div(id="outPut")
        )

    ]
    
)

@app.callback(
    Output('output-container-date-picker-range', 'children'),
    Input('my-date-picker-range', 'start_date'),
    Input('my-date-picker-range', 'end_date'))
def update_output(start_date, end_date):
    #string_prefix = 'You have selected: '
    if start_date is not None:
        start_date_object = date.fromisoformat(start_date)
        start_date_string = start_date_object.strftime('%B %d, %Y')
        string_prefix = 'Start Date: ' + start_date_string + ' | '
    if end_date is not None:
        end_date_object = date.fromisoformat(end_date)
        end_date_string = end_date_object.strftime('%B %d, %Y')
        string_prefix = string_prefix + 'End Date: ' + end_date_string
    if len(string_prefix) == len('You have selected: '):
        return 'Select a date to see it displayed here'
    else:
        return string_prefix

@app.callback(
    Output('stats', 'data'),
    Input('my-date-picker-range', 'start_date'),
    Input('my-date-picker-range', 'end_date'))
def update_table(start_date, end_date):
    cursor = connection.cursor()
    boroughQuery = """
        select
        boroughs.communityn,
        count(firepoints.shape)
        from alaska_borough_and_census_area_boundaries as boroughs
        join viirs_active_fire_detections as firepoints
        on ST_Contains(boroughs.shape, firepoints.shape)
        where firepoints.utcobstime >= (%s) and firepoints.utcobstime <= (%s)
        group by boroughs.communityn
        """
    times = (start_date, end_date)
    cursor.execute(boroughQuery, times)
    results = cursor.fetchall()
    stats = pd.DataFrame(results, columns=["Borough", "# of fire points"])
    return (stats.to_dict('records'))
@app.callback(
    Output('firePoints', 'data'),
    Input('my-date-picker-range', 'start_date'),
    Input('my-date-picker-range', 'end_date'))
def plot_points(start_date, end_date):
    cursor = connection.cursor()
    ptsQuery = """
    SELECT
    json_build_object(
        'type', 'FeatureCollection',
        'features', json_agg(ST_AsGeoJSON(t.*)::json)
    )
    FROM (
        SELECT
        firepoints.shape, firepoints.utcobstime, boroughs.communityn
        FROM alaska_borough_and_census_area_boundaries as boroughs
        JOIN viirs_active_fire_detections as firepoints
        ON ST_Contains(boroughs.shape, firepoints.shape)
        WHERE firepoints.utcobstime >= (%s) and firepoints.utcobstime <= (%s)
    ) AS t
    """
    times = (start_date, end_date)
    cursor.execute(ptsQuery, times)
    results = cursor.fetchall()
    fireDataCall = results[0][0]
    return fireDataCall

@app.callback(
    Output("leaflet_map", "bounds"),
    Input("boroughs", "click_feature"))
def map_click(feature):
    if feature is not None:
        return feature["bounds"]

@app.callback(Output("firePoints", "children"), Input("firePoints", "click_feature"))
def map_click(feature):
    if feature is not None:
        dt = feature['properties']['utcobstime']
        latlon = feature['geometry']['coordinates']
        return [dl.Popup(children=[
            html.Div([
                html.P([html.B(f"Date: "), f"{dt[:10]}"]),
                html.P([html.B(f"Time: "), f"{dt[11:]} UTC"]),
                html.P(f"{str(latlon[0])[:8]}, {str(latlon[1])[:6]}")
            ])
        ])]

@app.callback(Output("boroughs", "children"), Input("boroughs", "hover_feature"))
def map_hover(feature):
    print(feature)
    if feature is not None:
        return [dl.Tooltip(children=f"{feature['properties']['CommunityN']}")]

@app.callback(Output("outPut", "children"), Input("edit_control", "geojson"))
def draw(gjson):
    return str(gjson)

if __name__ == '__main__':
    app.run_server(debug=True)