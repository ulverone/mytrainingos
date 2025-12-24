#!/usr/bin/env python3
"""
Bulk FIT File Importer for MyTrainingOS
Parses FIT files and creates a JSON database for the web app to load
"""

import os
import sys
import json
import struct
from datetime import datetime, timedelta
from pathlib import Path

# FIT file constants
FIT_EPOCH = datetime(1989, 12, 31, 0, 0, 0)

class FITParser:
    def __init__(self):
        self.sport_types = {
            0: 'generic', 1: 'running', 2: 'cycling', 5: 'swimming',
            10: 'fitness_equipment', 11: 'swimming', 17: 'cycling', 18: 'running'
        }
        self.local_messages = {}
    
    def parse(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
            return self._parse_fit(data, filepath)
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
            return None
    
    def _parse_fit(self, data, filepath):
        activity = {
            'filename': os.path.basename(filepath),
            'sport': 'unknown',
            'startTime': None,
            'duration': 0,
            'distance': 0,
            'avgHR': None,
            'maxHR': None,
            'avgPower': None,
            'normalizedPower': None,
            'avgSpeed': None,
            'calories': 0,
            'laps': []
        }
        
        if len(data) < 14:
            return None
            
        # Read header
        header_size = data[0]
        signature = data[8:12]
        
        if signature != b'.FIT':
            return None
        
        data_size = struct.unpack('<I', data[4:8])[0]
        offset = header_size
        end_offset = header_size + data_size
        
        power_values = []
        hr_values = []
        
        while offset < end_offset and offset < len(data):
            try:
                record_header = data[offset]
                offset += 1
                
                is_definition = (record_header & 0x40) != 0
                local_msg_type = record_header & 0x0F
                
                if is_definition:
                    offset = self._parse_definition(data, offset, local_msg_type)
                else:
                    result = self._parse_data(data, offset, local_msg_type)
                    if result:
                        offset = result['offset']
                        self._process_message(result, activity, power_values, hr_values)
                    else:
                        break
            except:
                break
        
        # Calculate derived metrics
        if power_values:
            activity['avgPower'] = int(sum(power_values) / len(power_values))
            # Simple NP approximation
            if len(power_values) > 30:
                rolling = []
                for i in range(29, len(power_values)):
                    avg = sum(power_values[i-29:i+1]) / 30
                    rolling.append(avg ** 4)
                if rolling:
                    activity['normalizedPower'] = int((sum(rolling) / len(rolling)) ** 0.25)
        
        if hr_values:
            activity['avgHR'] = int(sum(hr_values) / len(hr_values))
            activity['maxHR'] = max(hr_values)
        
        return activity
    
    def _parse_definition(self, data, offset, local_msg_type):
        if offset + 5 > len(data):
            return offset
            
        offset += 1  # reserved
        architecture = data[offset]
        offset += 1
        little_endian = architecture == 0
        
        if little_endian:
            global_msg = struct.unpack('<H', data[offset:offset+2])[0]
        else:
            global_msg = struct.unpack('>H', data[offset:offset+2])[0]
        offset += 2
        
        num_fields = data[offset]
        offset += 1
        
        fields = []
        for _ in range(num_fields):
            if offset + 3 > len(data):
                break
            fields.append({
                'num': data[offset],
                'size': data[offset + 1],
                'type': data[offset + 2]
            })
            offset += 3
        
        self.local_messages[local_msg_type] = {
            'global': global_msg,
            'fields': fields,
            'little_endian': little_endian
        }
        
        return offset
    
    def _parse_data(self, data, offset, local_msg_type):
        if local_msg_type not in self.local_messages:
            return None
            
        msg_def = self.local_messages[local_msg_type]
        values = {}
        
        for field in msg_def['fields']:
            if offset + field['size'] > len(data):
                return None
            
            try:
                if field['size'] == 1:
                    values[field['num']] = data[offset]
                elif field['size'] == 2:
                    fmt = '<H' if msg_def['little_endian'] else '>H'
                    values[field['num']] = struct.unpack(fmt, data[offset:offset+2])[0]
                elif field['size'] == 4:
                    fmt = '<I' if msg_def['little_endian'] else '>I'
                    values[field['num']] = struct.unpack(fmt, data[offset:offset+4])[0]
            except:
                pass
            offset += field['size']
        
        return {
            'offset': offset,
            'global': msg_def['global'],
            'values': values
        }
    
    def _process_message(self, result, activity, power_values, hr_values):
        global_msg = result['global']
        values = result['values']
        
        # Session message (18)
        if global_msg == 18:
            if 253 in values or 2 in values:
                ts = values.get(253, values.get(2, 0))
                if ts and ts < 0xFFFFFFFF:
                    activity['startTime'] = (FIT_EPOCH + timedelta(seconds=ts)).isoformat()
            if 7 in values:
                activity['duration'] = values[7] / 1000
            if 9 in values:
                activity['distance'] = values[9] / 100
            if 16 in values and values[16] < 255:
                activity['avgHR'] = values[16]
            if 17 in values and values[17] < 255:
                activity['maxHR'] = values[17]
            if 20 in values and values[20] < 65535:
                activity['avgPower'] = values[20]
            if 34 in values and values[34] < 65535:
                activity['normalizedPower'] = values[34]
            if 5 in values:
                activity['sport'] = self.sport_types.get(values[5], 'unknown')
            if 11 in values:
                activity['calories'] = values[11]
        
        # Record message (20)
        elif global_msg == 20:
            if 3 in values and 0 < values[3] < 255:
                hr_values.append(values[3])
            if 7 in values and 0 < values[7] < 65535:
                power_values.append(values[7])

class TSSCalculator:
    def __init__(self, ftp=300, run_threshold=256, swim_threshold=100):
        self.ftp = ftp
        self.run_threshold = run_threshold  # seconds per km
        self.swim_threshold = swim_threshold  # seconds per 100m
    
    def calculate(self, activity):
        sport = activity.get('sport', 'unknown')
        
        if sport == 'cycling':
            return self._cycling_tss(activity)
        elif sport == 'running':
            return self._running_tss(activity)
        elif sport == 'swimming':
            return self._swimming_tss(activity)
        else:
            return self._hr_tss(activity)
    
    def _cycling_tss(self, activity):
        duration = activity.get('duration', 0)
        np = activity.get('normalizedPower') or activity.get('avgPower')
        
        if not np or not duration:
            return self._hr_tss(activity)
        
        IF = np / self.ftp
        tss = (duration * np * IF) / (self.ftp * 3600) * 100
        
        return {
            'tss': round(tss),
            'type': 'TSS',
            'IF': round(IF, 2)
        }
    
    def _running_tss(self, activity):
        duration = activity.get('duration', 0)
        distance = activity.get('distance', 0)
        
        if not duration or not distance or distance < 100:
            return self._hr_tss(activity)
        
        pace_per_km = duration / (distance / 1000)
        IF = self.run_threshold / pace_per_km
        hours = duration / 3600
        rtss = hours * (IF ** 2) * 100
        
        return {
            'tss': round(rtss),
            'type': 'rTSS',
            'IF': round(IF, 2)
        }
    
    def _swimming_tss(self, activity):
        duration = activity.get('duration', 0)
        distance = activity.get('distance', 0)
        
        if not duration or not distance or distance < 25:
            return self._hr_tss(activity)
        
        pace_per_100m = duration / (distance / 100)
        IF = self.swim_threshold / pace_per_100m
        hours = duration / 3600
        # Use IF^2 like running (IF^3 underestimates for slower paces)
        stss = (IF ** 2) * hours * 100
        
        return {
            'tss': round(stss),
            'type': 'sTSS',
            'IF': round(IF, 2)
        }
    
    def _hr_tss(self, activity):
        duration = activity.get('duration', 0)
        sport = activity.get('sport', 'unknown')
        hours = duration / 3600
        
        # Gym/weights activities have lower TSS than cardio
        if sport == 'fitness_equipment' or sport == 'generic':
            tss_per_hour = 25  # Pesi/palestra
        else:
            tss_per_hour = 40  # Other cardio activities
        
        return {
            'tss': round(hours * tss_per_hour),
            'type': 'hrTSS',
            'IF': 0.5 if sport == 'fitness_equipment' else 0.7
        }

def main():
    fit_dir = Path('/Users/marco/.gemini/antigravity/scratch/garmin_analyzer/fit_files')
    output_file = Path('/Users/marco/.gemini/antigravity/scratch/mytrainingos/data/activities.json')
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    parser = FITParser()
    tss_calc = TSSCalculator(ftp=300, run_threshold=256, swim_threshold=100)
    
    fit_files = sorted(fit_dir.glob('*.fit'))
    total = len(fit_files)
    
    print(f"Trovati {total} file FIT")
    print("Parsing in corso...")
    
    activities = []
    errors = 0
    
    for i, fit_file in enumerate(fit_files, 1):
        if i % 50 == 0:
            print(f"  Processati {i}/{total}...")
        
        activity = parser.parse(str(fit_file))
        if activity and activity.get('startTime'):
            # Calculate TSS
            tss_result = tss_calc.calculate(activity)
            activity['tss'] = tss_result['tss']
            activity['tssType'] = tss_result['type']
            activity['IF'] = tss_result['IF']
            
            # Generate ID
            activity['id'] = f"{activity['sport']}_{activity['startTime']}_{i}"
            
            activities.append(activity)
        else:
            errors += 1
    
    # Sort by date (newest first)
    activities.sort(key=lambda x: x.get('startTime', ''), reverse=True)
    
    # Save to JSON
    with open(output_file, 'w') as f:
        json.dump({
            'exportDate': datetime.now().isoformat(),
            'count': len(activities),
            'activities': activities
        }, f, indent=2)
    
    print(f"\n✅ Completato!")
    print(f"   Attività importate: {len(activities)}")
    print(f"   Errori: {errors}")
    print(f"   File salvato: {output_file}")
    
    # Calculate PMC
    daily_tss = {}
    for a in activities:
        date = a['startTime'][:10]
        daily_tss[date] = daily_tss.get(date, 0) + a['tss']
    
    # Calculate current CTL/ATL
    ctl_decay = 0.9762  # e^(-1/42)
    atl_decay = 0.8681  # e^(-1/7)
    ctl = 0
    atl = 0
    
    dates = sorted(daily_tss.keys())
    if dates:
        # Fill in missing days
        start = datetime.strptime(dates[0], '%Y-%m-%d')
        end = datetime.now()
        current = start
        
        while current <= end:
            date_str = current.strftime('%Y-%m-%d')
            tss = daily_tss.get(date_str, 0)
            
            ctl = ctl * ctl_decay + tss * (1 - ctl_decay)
            atl = atl * atl_decay + tss * (1 - atl_decay)
            
            current += timedelta(days=1)
        
        tsb = ctl - atl
        
        print(f"\n📊 PMC Attuale:")
        print(f"   CTL (Fitness): {ctl:.1f}")
        print(f"   ATL (Fatica): {atl:.1f}")
        print(f"   TSB (Forma): {tsb:.1f}")

if __name__ == '__main__':
    main()
