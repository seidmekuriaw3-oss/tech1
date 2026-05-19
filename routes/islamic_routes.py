from flask import Blueprint, render_template, request, jsonify, Response
from routes.shared import get_lang
import math
import datetime
import io
import csv
import calendar as cal_module

islamic_bp = Blueprint('islamic', __name__)

DEFAULT_LAT = 8.9806
DEFAULT_LNG = 38.7578
KAABA_LAT   = 21.4225
KAABA_LNG   = 39.8262

HIJRI_MONTHS = [
    'Muharram', 'Safar', 'Rabi al-Awwal', 'Rabi al-Thani',
    'Jumada al-Awwal', 'Jumada al-Thani', 'Rajab', "Sha'ban",
    'Ramadan', 'Shawwal', "Dhul Qi'dah", 'Dhul Hijjah'
]

ISLAMIC_HOLIDAYS = [
    (1,  1,  'Islamic New Year',       '🌙'),
    (1,  10, 'Day of Ashura',          '🤲'),
    (3,  12, "Mawlid al-Nabi",         '⭐'),
    (7,  27, "Isra and Mi'raj",        '🌃'),
    (8,  15, "Laylat al-Bara'ah",      '🌕'),
    (9,  1,  'Start of Ramadan',       '🌙'),
    (9,  27, 'Laylat al-Qadr',         '✨'),
    (10, 1,  'Eid al-Fitr',            '🎉'),
    (12, 9,  'Day of Arafah',          '🕋'),
    (12, 10, 'Eid al-Adha',            '🐑'),
]


def _julian_date(year, month, day):
    if month <= 2:
        year -= 1
        month += 12
    A = math.floor(year / 100.0)
    B = 2 - A + math.floor(A / 4.0)
    return math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + B - 1524.5


def _sun_position(jd):
    D  = jd - 2451545.0
    g  = math.radians(357.529 + 0.98560028 * D)
    q  = 280.459 + 0.98564736 * D
    L  = math.radians(q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    e  = math.radians(23.439 - 0.00000036 * D)
    RA = math.atan2(math.cos(e) * math.sin(L), math.cos(L)) / math.pi * 12
    d  = math.asin(math.sin(e) * math.sin(L))
    EqT = q / 15.0 - RA
    return d, EqT


def _compute_prayer_times(lat, lng, date, fajr_angle=19.5, isha_angle=17.5):
    jd     = _julian_date(date.year, date.month, date.day) - lng / (15.0 * 24.0)
    decl, eqt = _sun_position(jd)
    lat_r  = math.radians(lat)
    midday = 12.0 - eqt - lng / 15.0

    def time_diff(angle):
        cos_val = (
            -math.sin(math.radians(angle))
            - math.sin(lat_r) * math.sin(decl)
        ) / (math.cos(lat_r) * math.cos(decl))
        cos_val = max(-1.0, min(1.0, cos_val))
        return math.acos(cos_val) / math.pi * 12.0

    asr_angle = math.degrees(math.atan(1.0 / (1 + math.tan(abs(lat_r - decl)))))

    def fmt(t):
        t = t % 24
        h = int(t)
        m = int(round((t - h) * 60))
        if m == 60:
            h += 1
            m = 0
        h = h % 24
        return f"{h:02d}:{m:02d}"

    return {
        'Fajr':    fmt(midday - time_diff(fajr_angle)),
        'Dhuhr':   fmt(midday),
        'Asr':     fmt(midday + time_diff(90 - asr_angle)),
        'Maghrib': fmt(midday + time_diff(0.833)),
        'Isha':    fmt(midday + time_diff(isha_angle)),
    }


def _gregorian_to_hijri(year, month, day):
    if month <= 2:
        y, m = year - 1, month + 12
    else:
        y, m = year, month
    A  = int(y / 100)
    B  = 2 - A + int(A / 4)
    jd = int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + day + B - 1524
    l  = jd - 1948440 + 10632
    n  = int((l - 1) / 10631)
    l  = l - 10631 * n + 354
    j  = (int((10985 - l) / 5316) * int(50 * l / 17719)
          + int(l / 5670) * int(43 * l / 15238))
    l  = (l - int((30 - j) / 15) * int(17719 * j / 50)
          - int(j / 16) * int(15238 * j / 43) + 29)
    hm = int(24 * l / 709)
    hd = l - int(709 * hm / 24)
    hy = 30 * n + j - 30
    return int(hy), int(hm), int(hd)


def _hijri_to_gregorian(hy, hm, hd):
    n  = hd + int(29.5001 * (hm - 1) + 0.99)
    q  = int((hy - 1) / 30)
    r  = (hy - 1) % 30
    a  = int((11 * r + 3) / 30)
    w  = int(r / 2)
    q1 = int(q / 4)
    b  = int(r / 4)
    nd = n + a + w - b + q * 10631 + 1948440 - 385 + q1 * 10
    jd = int(nd) + int(3 * (int((nd + 184) / 36525) + 1) / 4) - 38
    l  = jd + 68569
    n2 = int(4 * l / 146097)
    l  = l - int((146097 * n2 + 3) / 4)
    i  = int(4000 * (l + 1) / 1461001)
    l  = l - int(1461 * i / 4) + 31
    j2 = int(80 * l / 2447)
    gd = l - int(2447 * j2 / 80)
    l  = int(j2 / 11)
    gm = j2 + 2 - 12 * l
    gy = 100 * (n2 - 49) + i + l
    return int(gy), int(gm), int(gd)


def _upcoming_holidays(count=10):
    today = datetime.date.today()
    hy0, _, _ = _gregorian_to_hijri(today.year, today.month, today.day)
    results = []
    for delta_year in range(0, 3):
        for hm, hd, name, icon in ISLAMIC_HOLIDAYS:
            try:
                gy, gm, gd = _hijri_to_gregorian(hy0 + delta_year, hm, hd)
                gdate = datetime.date(gy, gm, gd)
            except Exception:
                continue
            days_away = (gdate - today).days
            if days_away >= 0:
                hy_c, hm_c, hd_c = _gregorian_to_hijri(gy, gm, gd)
                results.append({
                    'name':      name,
                    'icon':      icon,
                    'gregorian': gdate.strftime('%d %b %Y'),
                    'hijri':     f"{hd_c} {HIJRI_MONTHS[hm_c-1]} {hy_c} AH",
                    'days_away': days_away,
                    'is_today':  days_away == 0,
                })
    results.sort(key=lambda x: x['days_away'])
    seen, unique = set(), []
    for r in results:
        k = r['name'] + r['gregorian']
        if k not in seen:
            seen.add(k)
            unique.append(r)
    return unique[:count]


def _safe_coords(lat_str, lng_str):
    try:
        lat = float(lat_str) if lat_str else DEFAULT_LAT
        lng = float(lng_str) if lng_str else DEFAULT_LNG
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            lat, lng = DEFAULT_LAT, DEFAULT_LNG
        if lat == 0.0 and lng == 0.0:
            lat, lng = DEFAULT_LAT, DEFAULT_LNG
        return lat, lng
    except (TypeError, ValueError):
        return DEFAULT_LAT, DEFAULT_LNG


@islamic_bp.route('/islamic')
def islamic_suite():
    lang  = get_lang()
    today = datetime.date.today()
    hy, hm, hd = _gregorian_to_hijri(today.year, today.month, today.day)
    is_ramadan     = (hm == 9)
    force_ramadan  = request.args.get('ramadan') == '1'
    ramadan_active = is_ramadan or force_ramadan
    hijri_today = {
        'day':       hd,
        'month':     HIJRI_MONTHS[hm - 1],
        'month_num': hm,
        'year':      hy,
        'full':      f"{hd} {HIJRI_MONTHS[hm-1]} {hy} AH",
    }
    holidays = _upcoming_holidays(10)
    return render_template(
        'customer/islamic.html',
        lang=lang,
        hijri_today=hijri_today,
        holidays=holidays,
        ramadan_active=ramadan_active,
    )


@islamic_bp.route('/api/islamic/prayer-times')
def prayer_times_api():
    try:
        lat, lng = _safe_coords(
            request.args.get('lat'),
            request.args.get('lng')
        )
        today = datetime.date.today()
        times = _compute_prayer_times(lat, lng, today)
        hy, hm, hd = _gregorian_to_hijri(today.year, today.month, today.day)
        return jsonify({
            'success':    True,
            'date':       today.isoformat(),
            'times':      times,
            'lat':        lat,
            'lng':        lng,
            'hijri':      f"{hd} {HIJRI_MONTHS[hm-1]} {hy} AH",
            'is_ramadan': hm == 9,
            'fallback':   (lat == DEFAULT_LAT and lng == DEFAULT_LNG),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@islamic_bp.route('/api/islamic/qibla-direction')
def qibla_direction_api():
    try:
        lat, lng = _safe_coords(
            request.args.get('lat'),
            request.args.get('lng')
        )
        lat_r      = math.radians(lat)
        lng_r      = math.radians(lng)
        klat_r     = math.radians(KAABA_LAT)
        klng_r     = math.radians(KAABA_LNG)
        d_lng      = klng_r - lng_r
        x          = math.sin(d_lng) * math.cos(klat_r)
        y          = math.cos(lat_r) * math.sin(klat_r) - math.sin(lat_r) * math.cos(klat_r) * math.cos(d_lng)
        bearing    = (math.degrees(math.atan2(x, y)) + 360) % 360
        return jsonify({'success': True, 'bearing': round(bearing, 2)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@islamic_bp.route('/api/islamic/monthly-prayer-times')
def monthly_prayer_times():
    try:
        lat, lng = _safe_coords(
            request.args.get('lat'),
            request.args.get('lng')
        )
        today  = datetime.date.today()
        year   = int(request.args.get('year',  today.year))
        month  = int(request.args.get('month', today.month))
        days_in_month = cal_module.monthrange(year, month)[1]
        result = []
        for d in range(1, days_in_month + 1):
            date  = datetime.date(year, month, d)
            times = _compute_prayer_times(lat, lng, date)
            hy, hm, hd = _gregorian_to_hijri(date.year, date.month, date.day)
            result.append({
                'day':         d,
                'weekday':     date.strftime('%a'),
                'hijri_day':   hd,
                'hijri_month': HIJRI_MONTHS[hm - 1],
                'times':       times,
            })
        return jsonify({'success': True, 'days': result, 'month': month, 'year': year})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@islamic_bp.route('/api/islamic/prayer-schedule-csv')
def prayer_schedule_csv():
    try:
        lat, lng = _safe_coords(
            request.args.get('lat'),
            request.args.get('lng')
        )
        today  = datetime.date.today()
        year   = int(request.args.get('year',  today.year))
        month  = int(request.args.get('month', today.month))
        days_in_month = cal_module.monthrange(year, month)[1]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Date', 'Hijri Date', 'Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha'])
        for d in range(1, days_in_month + 1):
            date  = datetime.date(year, month, d)
            times = _compute_prayer_times(lat, lng, date)
            hy, hm, hd = _gregorian_to_hijri(date.year, date.month, date.day)
            writer.writerow([
                date.strftime('%d %b %Y'),
                f"{hd} {HIJRI_MONTHS[hm-1]} {hy}",
                times['Fajr'], times['Dhuhr'], times['Asr'],
                times['Maghrib'], times['Isha'],
            ])
        output.seek(0)
        month_name = datetime.date(year, month, 1).strftime('%B_%Y')
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="prayer_times_{month_name}.csv"'}
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
