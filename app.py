from flask import Flask, request, redirect, render_template, send_from_directory, make_response, jsonify
from flask_caching import Cache
from bs4 import BeautifulSoup
import datetime as dt
import requests
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

@app.route('/event/<int:event>')
@cache.cached(timeout=600)
def index_event(event):
    return render_template("event.html", data=e(event))

@app.route('/<int:space>.json')
@cache.cached(timeout=86400)
def s(space):
    return requests.post("https://25live.collegenet.com/25live/data/louisville/run/spaces.json?request_method=get",headers={"Content-Type":"application/json","Accept-Encoding":"gzip"},json={"mapxml":{"scope":"extended","space_id":space}}).json().get("spaces",[]).get("space",[])

@app.route('/event/<int:event>.json')
@cache.cached(timeout=600)
def e(event):
    return requests.post("https://25live.collegenet.com/25live/data/louisville/run/events.json?request_method=get",headers={"Content-Type":"application/json","Accept-Encoding":"gzip"},json={"mapxml":{"scope":"extended","event_id":event}}).json().get("events",[]).get("event",[])

@app.route('/<int:y>-<int:m>-<int:d>.json')
@cache.cached(timeout=300)
def all(y,m,d):
    day=dt.date(y,m,d)
    if (not isValidDay(day)):
        return "invalid"
    weekday=str(day.weekday())
    sday=str(day)
    spaces=dict()
    for restaurant, schedules in dining_data().items():
        schedule = []
        current_range = None
        for period in schedules:
            if period != "Standard":
                if "-" in period:
                    s,e = [dt.date(day.year,*map(int, p.split("/"))) for p in period.split("-")]
                    if s <= day <= e:
                        current_range = period
                        break
                else:
                    d = dt.date(day.year,*map(int, period.split("/")))
                    if d == day:
                        current_range = period
                        break
        else: current_range = "Standard"
        for weekdays, meals in schedules[current_range].items():
            if weekday in weekdays.split(","):
                for meal, times in meals.items():
                    schedule.append({
                        "s":int(times.split("-")[0]),
                        "e":int(times.split("-")[1]),
                        "n":meal
                    })
        spaces[restaurant] = {
            "l":sorted(schedule, key=lambda x:x["s"])
        }
    data=requests.get(f"https://25live.collegenet.com/25live/data/louisville/run/home/calendar/calendardata.json?obj_cache_accl=0&page=1&compsubject=event&events_query_id=939025&start_dt={sday}&end_dt={sday}").json()
    food=set()
    for event in data["root"]["events"][0].get("rsrv", []):
        food.add(event["event_id"])
    data=requests.get(f"https://25live.collegenet.com/25live/data/louisville/run/availability/availabilitydata.json?obj_cache_accl=0&comptype=availability&compsubject=location&page_size=400&spaces_query_id=667440&include=closed+blackouts+pending+related+empty+requests+draft&start_dt={sday}").json()
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

# [{ periodId : '2230', name : 'Breakfast' }, { periodId : '3180', name : 'Light Lunch' }, { periodId : '2232', name : 'Lunch' }, { periodId : '2233', name : 'Dinner' }]
@app.route('/dining.json')
@cache.cached(timeout=44444)
def dining_data():
    data = cache.get("dining")
    if data: return data

    base = "https://louisville.campusdish.com/LocationsAndMenus/Belknap/"
    locations = dict()
    for location in re.findall(r':"/LocationsAndMenus/Belknap/([^",]+)', requests.get(base).text):
        locations[location] = dict()
        soup = BeautifulSoup(requests.get(base+location).text, 'html.parser')

        schedule_dates = []
        dates = soup.select_one(".location__scheduledates")
        if dates: schedule_dates.append(dates.text.strip().replace(" ",""))
        else: schedule_dates.append("Standard")
        for timePeriod in soup.select("a.additionalschedule"):
            match = re.search(r"(\d+/\d+-\d+/\d+)", timePeriod.text)
            if not match: match = re.search(r"(\d+/\d+)", timePeriod.text)
            if match: schedule_dates.append(match.group(1))
            else: schedule_dates.append("Standard")

        timeframes = [ul for ul in soup.find_all("div",class_="location__hours") if not ul.find("a.additionalschedule")]
        for timeframe, date_range in zip(timeframes, schedule_dates):
            meal_by_day = dict()
            for meal_period in timeframe.find_all("li"):
                period = meal_period.find("div", class_="mealPeriod")
                if period:
                    period_range = period.text.strip()
                    for time_entry in meal_period.find_all("li"):
                        day = time_entry.find("span", class_="location__day")
                        times = time_entry.find("span", class_="location__times")
                        if day and times:
                            day_range = day.text.strip().replace("Mon","0").replace("Tue","1").replace("Wed","2").replace("Thu","3").replace("Fri","4").replace("Sat","5").replace("Sun","6")
                            d = []
                            for wd in day_range.split(", "):
                                if "-" in wd:
                                    s,e = map(int, wd.split("-"))
                                    d.extend(map(str, (range(s,e+1))))
                                else:
                                    d.append(wd)
                            day_range = ",".join(d)
                            time_range = times.text.strip()
                            if "-" in time_range:
                                s,e = [int((dt.datetime.strptime(t, "%I:%M%p")-dt.datetime.strptime("8:00AM", "%I:%M%p")).total_seconds()/60) for t in time_range.split(" - ")]
                                if s < 0: s = 0
                                if e < 0 or e > 900: e = 900
                                time_range = str(s)+"-"+str(e)
                            else: continue
                            if day_range not in meal_by_day: meal_by_day[day_range]=dict()
                            meal_by_day[day_range][period_range] = time_range
            locations[location][date_range] = meal_by_day
    cache.set("dining", locations)
    return locations
