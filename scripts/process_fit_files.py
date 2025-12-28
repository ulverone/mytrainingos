#!/usr/bin/env python3
"""
Process Garmin FIT files and calculate training metrics.
Extracts data from .zip files, calculates TSS, and outputs to JSON.
"""

import os
import sys
import json
import zipfile
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# Try to import fitparse
try:
    from fitparse import FitFile
except ImportError:
    print("⚠️ fitparse not installed, installing...")
    os.system("pip install fitparse")
    from fitparse import FitFile


def extract_fit_from_zip(zip_path):
    """Extract .fit file from a zip archive."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            for name in z.namelist():
                if name.lower().endswith('.fit'):
                    return z.read(name)
    except Exception as e:
        print(f"   ⚠️ Error extracting {zip_path}: {e}")
    return None


def parse_fit_file(fit_data):
    """Parse FIT file and extract key metrics."""
    try:
        fitfile = FitFile(fit_data)
        
        activity = {
            'sport': None,
            'start_time': None,
            'duration': 0,
            'distance': 0,
            'calories': 0,
            'avg_hr': None,
            'max_hr': None,
            'avg_power': None,
            'max_power': None,
            'normalized_power': None,
            'tss': None,
            'elevation_gain': 0,
            'elevation_gain': 0,
            'avg_cadence': None,
            'avg_speed': None,
        }
        
        hr_values = []
        power_values = []
        cadence_values = []
        
        for record in fitfile.get_messages():
            if record.name == 'session':
                for field in record.fields:
                    if field.name == 'sport':
                        activity['sport'] = get_sport_label(field.value)
                    elif field.name == 'start_time':
                        activity['start_time'] = field.value.isoformat() if field.value else None
                    elif field.name == 'total_elapsed_time':
                        activity['duration'] = int(field.value) if field.value else 0
                    elif field.name == 'total_distance':
                        activity['distance'] = round(field.value / 1000, 2) if field.value else 0
                    elif field.name == 'total_calories':
                        activity['calories'] = int(field.value) if field.value else 0
                    elif field.name == 'avg_heart_rate':
                        activity['avg_hr'] = int(field.value) if field.value else None
                    elif field.name == 'max_heart_rate':
                        activity['max_hr'] = int(field.value) if field.value else None
                    elif field.name == 'avg_power':
                        activity['avg_power'] = int(field.value) if field.value else None
                    elif field.name == 'max_power':
                        activity['max_power'] = int(field.value) if field.value else None
                    elif field.name == 'normalized_power':
                        activity['normalized_power'] = int(field.value) if field.value else None
                    elif field.name == 'total_ascent':
                        activity['elevation_gain'] = int(field.value) if field.value else 0
                    elif field.name == 'avg_cadence':
                        activity['avg_cadence'] = int(field.value) if field.value else None
                    elif field.name == 'enhanced_avg_speed' or field.name == 'avg_speed':
                        activity['avg_speed'] = float(field.value) if field.value else None
                    elif field.name == 'training_stress_score':
                        # Valid TSS from device usually preferred, but user reported issues.
                        # Using our formula for consistency unless 0.
                        val = field.value
                        activity['tss'] = round(val, 1) if val and val > 10 else None
            
            # Collect record data for calculations
            elif record.name == 'record':
                for field in record.fields:
                    if field.name == 'heart_rate' and field.value:
                        hr_values.append(field.value)
                    elif field.name == 'power' and field.value:
                        power_values.append(field.value)
                    elif field.name == 'cadence' and field.value:
                        cadence_values.append(field.value)
        
        # Calculate averages if not in session
        if not activity['avg_hr'] and hr_values:
            activity['avg_hr'] = int(sum(hr_values) / len(hr_values))
        if not activity['max_hr'] and hr_values:
            activity['max_hr'] = max(hr_values)
        if not activity['avg_power'] and power_values:
            activity['avg_power'] = int(sum(power_values) / len(power_values))
        if not activity['max_power'] and power_values:
            activity['max_power'] = max(power_values)
        if not activity['avg_cadence'] and cadence_values:
            activity['avg_cadence'] = int(sum(cadence_values) / len(cadence_values))
            
        # Backfill avg_speed if missing (m/s)
        if not activity['avg_speed'] and activity['distance'] and activity['duration']:
            # distance is in km, convert to meters for m/s
            activity['avg_speed'] = (activity['distance'] * 1000) / activity['duration']
        
        # Estimate TSS if not provided
        if not activity['tss'] and activity['duration']:
            activity['tss'] = estimate_tss(activity)
        
        return activity
        
    except Exception as e:
        print(f"   ⚠️ Error parsing FIT: {e}")
        return None


# User settings
USER_CYCLING_FTP = 250  # Watts
USER_RUNNING_FTP = 380  # Running Critical Power (Watts)
USER_LTHR = 165         # LTHR (bpm)
USER_RUN_THRESHOLD_PACE = "4:30"  # min/km
USER_SWIM_THRESHOLD_PACE = "1:45" # min/100m

# Activity type mapping (FIT sport -> Italian label)
SPORT_MAPPING = {
    'running': 'Corsa',
    'cycling': 'Ciclismo',
    'swimming': 'Nuoto',
    'lap_swimming': 'Nuoto',
    'training': 'Allenamento',
    'strength_training': 'Forza',
    'hiking': 'Escursionismo',
    'walking': 'Camminata',
    'soccer': 'Calcio',
    'tennis': 'Tennis',
    'basketball': 'Basket',
    'generic': 'Altro'
}

def parse_pace_to_speed(pace_str, dist_unit_meters=1000):
    """
    Convert pace string (mm:ss per unit) to speed (m/s).
    Example: '4:30' min/km -> 270s/km -> 1000/270 = 3.7 m/s
    Example: '1:45' min/100m -> 105s/100m -> 100/105 = 0.95 m/s
    """
    try:
        parts = pace_str.split(':')
        seconds = int(parts[0]) * 60 + int(parts[1])
        if seconds == 0: return 0
        return dist_unit_meters / seconds
    except:
        return 0

def get_sport_label(sport_raw):
    """Normalize and translate sport label."""
    if not sport_raw:
        return 'Altro'
    
    raw = str(sport_raw).lower()
    
    # Direct match
    if raw in SPORT_MAPPING:
        return SPORT_MAPPING[raw]
    
    # Substring match
    for key, label in SPORT_MAPPING.items():
        if key in raw:
            return label
            
    return 'Altro'

def estimate_tss(activity):
    """
    Estimate TSS based on sport-specific algorithms (Power, rTSS, sTSS).
    """
    duration_seconds = activity['duration']
    duration_hours = duration_seconds / 3600
    sport = (activity['sport'] or '').lower()
    
    # 1. SWIMMING (sTSS) - Based on Normalized Swim Speed (using Avg Speed for now)
    if 'nuoto' in sport or 'swimming' in sport:
        # Calculate threshold speed (m/s)
        thresh_speed = parse_pace_to_speed(USER_SWIM_THRESHOLD_PACE, 100) # m/s (based on 100m)
        
        avg_speed = activity.get('avg_speed', 0)
        
        # If no speed, try to calc from dist/time
        if not avg_speed and activity['distance'] and activity['duration']:
            avg_speed = activity['distance'] / activity['duration']
            
        if avg_speed and thresh_speed > 0:
            # IF = SwimSpeed / ThresholdSpeed (Intensity Factor)
            # Normalized Swim Speed is roughly Avg Speed for continuous swims
            intensity_factor = avg_speed / thresh_speed
            
            # sTSS = IF^3 * hours * 100
            stss = (intensity_factor ** 3) * duration_hours * 100
            return round(min(stss, 600), 1)
            
    # 2. CYCLING & RUNNING with Power (TSS)
    if activity['normalized_power'] or activity['avg_power']:
        np = activity['normalized_power'] or activity['avg_power']
        
        ftp = USER_CYCLING_FTP
        if 'corsa' in sport or 'running' in sport:
            ftp = USER_RUNNING_FTP
        
        intensity_factor = np / ftp
        tss = (duration_seconds * np * intensity_factor) / (ftp * 3600) * 100
        return round(min(tss, 600), 1)
        
    # 3. RUNNING without Power (rTSS) - Based on NGP (using Avg Speed/Grade normalized)
    if 'corsa' in sport or 'running' in sport:
        # Calculate threshold speed (m/s)
        thresh_speed = parse_pace_to_speed(USER_RUN_THRESHOLD_PACE, 1000) # m/s
        
        avg_speed = activity.get('avg_speed', 0)
        if not avg_speed and activity['distance'] and activity['duration']:
            avg_speed = activity['distance'] / activity['duration']
            
        if avg_speed and thresh_speed > 0:
            # Simple rTSS estimation using speed ratio (NGP approx)
            # IF = AvgSpeed / ThresholdSpeed
            # Real rTSS uses NGP, but we fallback to avg speed
            intensity_factor = avg_speed / thresh_speed
            
            # rTSS = IF^2 * hours * 100
            rtss = (intensity_factor ** 2) * duration_hours * 100
            return round(min(rtss, 600), 1)

    # 4. HR-BASED CALCULATION (Fallback)
    if activity['avg_hr']:
        hr_ratio = activity['avg_hr'] / USER_LTHR
        tss = duration_hours * (hr_ratio * hr_ratio) * 100
        return round(min(tss, 600), 1)
    
    # 5. DURATION-BASED FALLBACK
    if 'corsa' in sport or 'running' in sport:
        tss = duration_hours * 60
    elif 'ciclismo' in sport or 'cycling' in sport:
        tss = duration_hours * 50
    elif 'nuoto' in sport or 'swimming' in sport:
        tss = duration_hours * 45
    else:
        tss = duration_hours * 40
    
    return round(min(tss, 600), 1)


def calculate_performance_metrics(activities):
    """Calculate CTL, ATL, TSB from activity history."""
    # Sort by date
    sorted_activities = sorted(
        [a for a in activities if a.get('start_time')],
        key=lambda x: x['start_time']
    )
    
    if not sorted_activities:
        return {'ctl': 0, 'atl': 0, 'tsb': 0, 'daily_tss': {}}
    
    # Aggregate TSS by day
    daily_tss = defaultdict(float)
    for act in sorted_activities:
        try:
            date = act['start_time'][:10]
            daily_tss[date] += act.get('tss', 0) or 0
        except:
            continue
    
    # Calculate CTL (42-day) and ATL (7-day) exponential averages
    dates = sorted(daily_tss.keys())
    if not dates:
        return {'ctl': 0, 'atl': 0, 'tsb': 0, 'daily_tss': {}}
    
    # Fill in missing dates
    start = datetime.fromisoformat(dates[0])
    end = datetime.fromisoformat(dates[-1])
    all_dates = []
    current = start
    while current <= end:
        all_dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    
    # Calculate exponential moving averages
    ctl = 0  # Chronic Training Load (42-day)
    atl = 0  # Acute Training Load (7-day)
    
    ctl_decay = 2 / (42 + 1)
    atl_decay = 2 / (7 + 1)
    
    ctl_history = []
    atl_history = []
    
    for date in all_dates:
        tss = daily_tss.get(date, 0)
        ctl = ctl * (1 - ctl_decay) + tss * ctl_decay
        atl = atl * (1 - atl_decay) + tss * atl_decay
        ctl_history.append({'date': date, 'ctl': round(ctl, 1), 'atl': round(atl, 1), 'tsb': round(ctl - atl, 1)})
    
    # Return latest values
    latest = ctl_history[-1] if ctl_history else {'ctl': 0, 'atl': 0, 'tsb': 0}
    
    return {
        'ctl': latest['ctl'],
        'atl': latest['atl'],
        'tsb': latest['tsb'],
        'history': ctl_history[-90:],  # Last 90 days
        'daily_tss': dict(list(daily_tss.items())[-42:])  # Last 42 days
    }


def main():
    """Main processing function."""
    print("🏃 Processing FIT files...")
    
    activities_dir = Path("data/activities")
    output_file = Path("data/workouts.json")
    
    if not activities_dir.exists():
        print("❌ No activities directory found")
        return False
    
    zip_files = list(activities_dir.glob("*.zip"))
    print(f"📁 Found {len(zip_files)} activity files")
    
    if not zip_files:
        print("⚠️ No ZIP files to process")
        return True
    
    # Load existing data if available
    existing_data = {}
    if output_file.exists():
        try:
            with open(output_file, 'r') as f:
                existing = json.load(f)
                existing_data = {a['id']: a for a in existing.get('activities', [])}
        except:
            pass
    
    activities = []
    processed = 0
    skipped = 0
    errors = 0
    
    for i, zip_path in enumerate(zip_files):
        activity_id = zip_path.stem
        
        # Skip if already processed
        if activity_id in existing_data:
            activities.append(existing_data[activity_id])
            skipped += 1
            continue
        
        if (i + 1) % 50 == 0:
            print(f"   Processing {i+1}/{len(zip_files)}...")
        
        fit_data = extract_fit_from_zip(zip_path)
        if not fit_data:
            errors += 1
            continue
        
        activity = parse_fit_file(fit_data)
        if activity:
            activity['id'] = activity_id
            activities.append(activity)
            processed += 1
        else:
            errors += 1
    
    # Calculate performance metrics
    print("📊 Calculating performance metrics...")
    perf = calculate_performance_metrics(activities)
    
    # Prepare output
    output = {
        'last_updated': datetime.now().isoformat(),
        'total_activities': len(activities),
        'performance': {
            'ctl': perf['ctl'],
            'atl': perf['atl'],
            'tsb': perf['tsb'],
            'form': 'Fresh' if perf['tsb'] > 10 else ('Optimal' if perf['tsb'] > -10 else 'Fatigued')
        },
        'history': perf.get('history', []),
        'daily_tss': perf.get('daily_tss', {}),
        'activities': sorted(activities, key=lambda x: x.get('start_time', ''), reverse=True)[:100]  # Last 100
    }
    
    # Save output
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    
    # Also generate activities.json in the format the web app expects (camelCase keys)
    activities_output_file = Path("data/activities.json")
    web_activities = []
    for act in activities:
        web_act = {
            'id': act.get('id'),
            'sport': act.get('sport'),
            'startTime': act.get('start_time'),
            'duration': act.get('duration', 0),
            'distance': (act.get('distance', 0) or 0) * 1000,  # Convert km back to meters for app
            'avgHR': act.get('avg_hr'),
            'maxHR': act.get('max_hr'),
            'avgPower': act.get('avg_power'),
            'normalizedPower': act.get('normalized_power'),
            'avgSpeed': act.get('avg_speed'),
            'calories': act.get('calories'),
            'laps': [],
            'tss': act.get('tss'),
            'tssType': 'hrTSS' if not act.get('normalized_power') and act.get('avg_hr') else 'TSS',
            # IF calculated later based on sport
            'IF': None,
            'filename': f"{act.get('id')}.fit"
        }
        web_activities.append(web_act)
    
    # Sort by date descending
    web_activities_sorted = sorted(web_activities, key=lambda x: x.get('startTime') or '', reverse=True)
    
    # Update IF calculation logic for export
    for act in web_activities_sorted:
        if act.get('avgPower'):
            sport_key = (act.get('sport') or '').lower()
            ftp = USER_RUNNING_FTP if 'corsa' in sport_key else USER_CYCLING_FTP
            act['IF'] = round((act.get('normalizedPower') or act.get('avgPower')) / ftp, 2)
    
    activities_output = {
        'exportDate': datetime.now().isoformat(),
        'count': len(web_activities_sorted),
        'activities': web_activities_sorted
    }
    
    with open(activities_output_file, 'w') as f:
        json.dump(activities_output, f, indent=2, default=str)
    
    print(f"📱 Generated activities.json with {len(web_activities_sorted)} activities for web app")
    
    print(f"""
✅ Processing Complete!
   📥 Processed: {processed} new activities
   ⏭️ Skipped: {skipped} (already processed)
   ⚠️ Errors: {errors}
   
📊 Performance Metrics:
   CTL (Fitness): {perf['ctl']}
   ATL (Fatigue): {perf['atl']}
   TSB (Form): {perf['tsb']}
""")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
