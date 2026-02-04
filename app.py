from flask import Flask, request, redirect, render_template, send_from_directory, make_response, jsonify
from flask_caching import Cache
from bs4 import BeautifulSoup
import datetime as dt
import httpx
import re

app = Flask(__name__)
app.json.sort_keys = False
app.config['CACHE_TYPE'] = 'SimpleCache'
app.config['CACHE_DEFAULT_TIMEOUT'] = 44444
cache = Cache(app)

def isValidDay(day):
    t=dt.date.today()
    return t<=day<=t+dt.timedelta(days=31)

@app.route("/")
def index():
    t=dt.date.today()
    return render_template("index.html", today=str(t), dayafter=str(t+dt.timedelta(days=2)), later=str(t+dt.timedelta(days=31)))

@app.route("/today")
def index_today():
    t=dt.date.today()
    return index_day(t.year,t.month,t.day)

@app.route("/tomorrow")
def index_tomorrow():
    t=dt.date.today()+dt.timedelta(days=1)
    return index_day(t.year,t.month,t.day)

@app.route('/<int:y>-<int:m>-<int:d>')
def index_day(y,m,d):
    day=dt.date(y,m,d)
    if not (isValidDay(day)):
        q=request.query_string.decode('utf-8')
        if (q): q="?"+q
        return redirect("today"+q)
    return render_template("list.html", day=str(day))

@app.route('/<int:space>')
@cache.cached(timeout=86400)
def index_space(space):
    return render_template("space.html", data=s(space))

@app.route('/<int:space>.json')
@cache.cached(timeout=86400)
def s(space):
    return httpx.post("https://25live.collegenet.com/25live/data/louisville/run/spaces.json?request_method=get",headers={"Content-Type":"application/json","Accept-Encoding":"gzip"},json={"mapxml":{"scope":"extended","space_id":space}}).json().get("spaces",[]).get("space",[])

@app.route('/<int:y>-<int:m>-<int:d>.json')
@cache.cached(timeout=300)
def all(y,m,d):
    day=dt.date(y,m,d)
    if (not isValidDay(day)):
        return "invalid"
    weekday=str(day.weekday())
    sday=str(day)
    spaces=dict()
    data=httpx.get(f"https://25live.collegenet.com/25live/data/louisville/run/home/calendar/calendardata.json?obj_cache_accl=0&page=1&compsubject=event&events_query_id=939025&start_dt={sday}&end_dt={sday}",timeout=44).json()
    food=set()
    for event in data["root"]["events"][0].get("rsrv",[]):
        food.add(event["event_id"])
    data=httpx.get(f"https://25live.collegenet.com/25live/data/louisville/run/availability/availabilitydata.json?obj_cache_accl=0&comptype=availability&compsubject=location&page_size=999&spaces_query_id=667440&include=closed+blackouts+pending+related+empty+requests+draft&start_dt={sday}",timeout=44).json()
    for space in data.get('subjects', []):
        spaces[space['itemName']] = {
            "i":space['itemId'],
            "l":sorted([{
                "s":round(float(item['start'])*60)-480,
                "e":round(float(item['end'])*60)-480,
                "n":item['itemName'],
                **({"i":item['itemId']} if item['itemId'] != 0 else {}),
                **({"t":"food"} if item['itemId'] in food
                else {"t":"exam"} if item.get('event_type_id') == 139
                else {"t":"booked"} if item.get('event_type_id') == 143
                else {"t":"class"} if item.get('event_type_id') == 172
                else {})
            } for item in space.get('items', [])], key=lambda x:x["s"])
        }
    return spaces
