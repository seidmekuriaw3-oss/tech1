from flask import Blueprint, render_template, request, jsonify
from routes.shared import get_lang
import math
import datetime

islamic_bp = Blueprint('islamic', __name__)

KAABA_LAT = 21.4225
KAABA_LNG = 39.8262

def _julian_date(year, month, day):
    if month <= 2:
        year -= 1
        month += 12
    A = math.floor(year / 100.0)
    B = 2 - A + math.floor(A / 4.0)
    return math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + B - 1524.5

def _sun_position(jd):
    D = jd - 2451545.0
    g = math.radians(357.529 + 0.98560028 * D)
    q = 280.459 + 0.98564736 * D
    L = math.radians(q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    e = math.radians(23.439 - 0.00000036 * D)
    RA = math.atan2(math.cos(e) * math.sin(L), math.cos(L)) / math.pi * 12
    d = math.asin(math.sin(e) * math.sin(L))
    EqT = q / 15.0 - RA
    return d, EqT

def _compute_prayer_times(lat, lng, date, fajr_angle=19.5, isha_angle=17.5):
    jd = _julian_date(date.year, date.month, date.day) - lng / (15.0 * 24.0)
    decl, eqt = _sun_position(jd)
    lat_r = math.radians(lat)

    def time_diff(angle):
        cos_val = (-math.sin(math.radians(angle)) - math.sin(lat_r) * math.sin(decl)) / (math.cos(lat_r) * math.cos(decl))
        if cos_val < -1:
            return 12.0
        if cos_val > 1:
            return 0.0
        return math.acos(cos_val) / math.pi * 12.0

    midday = 12.0 - eqt - lng / 15.0

    fajr_t   = midday - time_diff(fajr_angle)
    sunrise_t = midday - time_diff(0.833)
    dhuhr_t  = midday
    asr_shadow = 1
    asr_angle = math.degrees(math.atan(1.0 / (asr_shadow + math.tan(abs(lat_r - decl)))))
    asr_t    = midday + time_diff(90 - asr_angle)
    maghrib_t = midday + time_diff(0.833)
    isha_t   = midday + time_diff(isha_angle)

    def fmt(t):
        t = t % 24
        h = int(t)
        m = int(round((t - h) * 60))
        if m == 60:
            h += 1
            m = 0
        return f"{h:02d}:{m:02d}"

    return {
        "Fajr":    fmt(fajr_t),
        "Dhuhr":   fmt(dhuhr_t),
        "Asr":     fmt(asr_t),
        "Maghrib": fmt(maghrib_t),
        "Isha":    fmt(isha_t),
    }


@islamic_bp.route('/islamic')
def islamic_suite():
    lang = get_lang()
    return render_template('customer/islamic.html', lang=lang)


@islamic_bp.route('/api/prayer-times')
def prayer_times_api():
    try:
        lat = float(request.args.get('lat', 0))
        lng = float(request.args.get('lng', 0))
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return jsonify({'error': 'Invalid coordinates'}), 400
        today = datetime.date.today()
        times = _compute_prayer_times(lat, lng, today)
        return jsonify({
            'success': True,
            'date': today.isoformat(),
            'times': times,
            'lat': lat,
            'lng': lng
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@islamic_bp.route('/api/qibla-direction')
def qibla_direction_api():
    try:
        lat = float(request.args.get('lat', 0))
        lng = float(request.args.get('lng', 0))
        lat_r = math.radians(lat)
        lng_r = math.radians(lng)
        kaaba_lat_r = math.radians(KAABA_LAT)
        kaaba_lng_r = math.radians(KAABA_LNG)
        d_lng = kaaba_lng_r - lng_r
        x = math.sin(d_lng) * math.cos(kaaba_lat_r)
        y = math.cos(lat_r) * math.sin(kaaba_lat_r) - math.sin(lat_r) * math.cos(kaaba_lat_r) * math.cos(d_lng)
        bearing = (math.degrees(math.atan2(x, y)) + 360) % 360
        return jsonify({'success': True, 'bearing': round(bearing, 2)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
