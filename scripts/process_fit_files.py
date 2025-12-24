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
            'avg_cadence': None,
        }
        
        hr_values = []
        power_values = []
        cadence_values = []
        
        for record in fitfile.get_messages():
            if record.name == 'session':
                for field in record.fields:
                    if field.name == 'sport':
                        activity['sport'] = str(field.value)
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
                    elif field.name == 'training_stress_score':
                        activity['tss'] = round(field.value, 1) if field.value else None
            
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
        
        # Estimate TSS if not provided
        if not activity['tss'] and activity['duration']:
            activity['tss'] = estimate_tss(activity)
        
        return activity
        
    except Exception as e:
        print(f"   ⚠️ Error parsing FIT: {e}")
        return None


def estimate_tss(activity):
    """
    Estimate TSS based on available data.
    Uses hrTSS formula if HR data available, otherwise duration-based estimate.
    """
    duration_hours = activity['duration'] / 3600
    
    # If we have power data, use simple power-based TSS
    if activity['normalized_power'] or activity['avg_power']:
        np = activity['normalized_power'] or activity['avg_power']
        # Assume FTP of 250W for cycling, adjust as needed
        ftp = 250
        intensity_factor = np / ftp
        tss = (duration_hours * np * intensity_factor) / (ftp * 3600) * 100
        return round(min(tss * 36, 500), 1)  # Cap at 500
    
    # HR-based TSS estimation
    if activity['avg_hr']:
        # Assume LTHR of 165, adjust as needed
        lthr = 165
        hr_ratio = activity['avg_hr'] / lthr
        # Simplified hrTSS formula
        tss = duration_hours * hr_ratio * hr_ratio * 100
        return round(min(tss, 500), 1)
    
    # Duration-based fallback
    sport = (activity['sport'] or '').lower()
    if 'running' in sport:
        tss = duration_hours * 80  # Running is high stress
    elif 'cycling' in sport:
        tss = duration_hours * 60
    elif 'swimming' in sport:
        tss = duration_hours * 70
    else:
        tss = duration_hours * 50  # Default moderate
    
    return round(min(tss, 500), 1)


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
