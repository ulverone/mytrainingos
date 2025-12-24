/**
 * FIT File Parser for MyTrainingOS
 * Parses Garmin FIT files to extract activity data
 */

class FITParser {
    constructor() {
        this.FIT_HEADER_SIZE = 14;
        this.DEFINITION_MESSAGE = 0x40;
        this.DATA_MESSAGE = 0x00;
        
        // Field definitions for common message types
        this.fieldDefs = {};
        this.localMessageTypes = {};
        
        // Sport types mapping
        this.sportTypes = {
            0: 'generic',
            1: 'running',
            2: 'cycling',
            5: 'swimming',
            10: 'fitness_equipment',
            11: 'swimming', // lap swimming
            17: 'cycling', // indoor cycling
            18: 'running', // treadmill
        };
        
        // Sub-sport types
        this.subSportTypes = {
            0: 'generic',
            1: 'treadmill',
            2: 'street',
            3: 'trail',
            4: 'track',
            5: 'spin',
            6: 'indoor_cycling',
            7: 'road',
            8: 'mountain',
            14: 'open_water',
            17: 'lap_swimming',
            23: 'virtual_activity',
            58: 'navigate',
        };
    }

    /**
     * Parse a FIT file from ArrayBuffer
     * @param {ArrayBuffer} buffer - The FIT file data
     * @returns {Object} Parsed activity data
     */
    async parse(buffer) {
        const dataView = new DataView(buffer);
        const activity = {
            sport: 'unknown',
            subSport: 'unknown',
            startTime: null,
            totalTime: 0,
            totalDistance: 0,
            totalCalories: 0,
            avgHeartRate: null,
            maxHeartRate: null,
            avgPower: null,
            normalizedPower: null,
            avgSpeed: null,
            avgCadence: null,
            records: [],
            laps: [],
            sessions: []
        };

        try {
            // Validate FIT header
            const headerSize = dataView.getUint8(0);
            const protocolVersion = dataView.getUint8(1);
            const dataSize = dataView.getUint32(4, true);

            // Check for .FIT signature
            const signature = String.fromCharCode(
                dataView.getUint8(8),
                dataView.getUint8(9),
                dataView.getUint8(10),
                dataView.getUint8(11)
            );

            if (signature !== '.FIT') {
                throw new Error('Invalid FIT file signature');
            }

            // Parse messages
            let offset = headerSize;
            const endOffset = headerSize + dataSize;

            while (offset < endOffset) {
                const result = this.parseMessage(dataView, offset, activity);
                offset = result.offset;
            }

            // Calculate derived metrics
            this.calculateDerivedMetrics(activity);

            return activity;
        } catch (error) {
            console.error('FIT parsing error:', error);
            throw error;
        }
    }

    parseMessage(dataView, offset, activity) {
        const recordHeader = dataView.getUint8(offset);
        offset++;

        const isDefinition = (recordHeader & 0x40) !== 0;
        const localMessageType = recordHeader & 0x0F;
        const hasDevData = (recordHeader & 0x20) !== 0;

        if (isDefinition) {
            // Definition message
            offset++; // reserved byte
            const architecture = dataView.getUint8(offset);
            offset++;
            const isLittleEndian = architecture === 0;
            
            const globalMsgNum = isLittleEndian 
                ? dataView.getUint16(offset, true) 
                : dataView.getUint16(offset, false);
            offset += 2;
            
            const numFields = dataView.getUint8(offset);
            offset++;

            const fields = [];
            for (let i = 0; i < numFields; i++) {
                fields.push({
                    num: dataView.getUint8(offset),
                    size: dataView.getUint8(offset + 1),
                    type: dataView.getUint8(offset + 2)
                });
                offset += 3;
            }

            // Handle developer fields if present
            if (hasDevData) {
                const numDevFields = dataView.getUint8(offset);
                offset++;
                for (let i = 0; i < numDevFields; i++) {
                    offset += 3; // Skip developer field definition
                }
            }

            this.localMessageTypes[localMessageType] = {
                globalMsgNum,
                fields,
                isLittleEndian
            };
        } else {
            // Data message
            const msgDef = this.localMessageTypes[localMessageType];
            if (msgDef) {
                const values = {};
                for (const field of msgDef.fields) {
                    values[field.num] = this.readFieldValue(dataView, offset, field, msgDef.isLittleEndian);
                    offset += field.size;
                }

                // Process message based on global message number
                this.processMessage(msgDef.globalMsgNum, values, activity);
            }
        }

        return { offset };
    }

    readFieldValue(dataView, offset, field, isLittleEndian) {
        try {
            switch (field.size) {
                case 1:
                    return dataView.getUint8(offset);
                case 2:
                    return dataView.getUint16(offset, isLittleEndian);
                case 4:
                    // Check if it's a signed or unsigned type
                    if (field.type === 0x85 || field.type === 0x84) { // signed
                        return dataView.getInt32(offset, isLittleEndian);
                    }
                    return dataView.getUint32(offset, isLittleEndian);
                default:
                    // For strings or larger values, return raw bytes
                    const bytes = [];
                    for (let i = 0; i < field.size; i++) {
                        bytes.push(dataView.getUint8(offset + i));
                    }
                    return bytes;
            }
        } catch (e) {
            return null;
        }
    }

    processMessage(globalMsgNum, values, activity) {
        switch (globalMsgNum) {
            case 0: // file_id
                break;
            case 18: // session
                this.processSession(values, activity);
                break;
            case 19: // lap
                this.processLap(values, activity);
                break;
            case 20: // record
                this.processRecord(values, activity);
                break;
            case 21: // event
                break;
            case 23: // device_info
                break;
        }
    }

    processSession(values, activity) {
        // Field numbers from FIT SDK
        const session = {
            startTime: this.convertTimestamp(values[253] || values[2]),
            totalTime: (values[7] || 0) / 1000, // ms to seconds
            totalDistance: (values[9] || 0) / 100, // cm to meters
            avgHeartRate: values[16] || null,
            maxHeartRate: values[17] || null,
            avgPower: values[20] || null,
            normalizedPower: values[34] || null,
            avgSpeed: values[14] ? (values[14] / 1000) * 3.6 : null, // m/ms to km/h
            avgCadence: values[18] || null,
            totalCalories: values[11] || 0,
            sport: this.sportTypes[values[5]] || 'unknown',
            subSport: this.subSportTypes[values[6]] || 'unknown'
        };

        activity.sessions.push(session);
        
        // Update activity with session data
        if (!activity.startTime) activity.startTime = session.startTime;
        activity.totalTime += session.totalTime;
        activity.totalDistance += session.totalDistance;
        activity.totalCalories += session.totalCalories;
        activity.sport = session.sport;
        activity.subSport = session.subSport;
        
        if (session.avgHeartRate) activity.avgHeartRate = session.avgHeartRate;
        if (session.maxHeartRate) activity.maxHeartRate = session.maxHeartRate;
        if (session.avgPower) activity.avgPower = session.avgPower;
        if (session.normalizedPower) activity.normalizedPower = session.normalizedPower;
        if (session.avgSpeed) activity.avgSpeed = session.avgSpeed;
        if (session.avgCadence) activity.avgCadence = session.avgCadence;
    }

    processLap(values, activity) {
        const lap = {
            startTime: this.convertTimestamp(values[253] || values[2]),
            totalTime: (values[7] || values[8] || 0) / 1000,
            totalDistance: (values[9] || 0) / 100,
            avgHeartRate: values[15] || null,
            maxHeartRate: values[16] || null,
            avgPower: values[19] || null,
            avgSpeed: values[13] ? (values[13] / 1000) * 3.6 : null,
            avgCadence: values[17] || null
        };
        
        activity.laps.push(lap);
    }

    processRecord(values, activity) {
        const record = {
            timestamp: this.convertTimestamp(values[253]),
            heartRate: values[3] || null,
            power: values[7] || null,
            speed: values[6] ? (values[6] / 1000) * 3.6 : null, // m/ms to km/h
            cadence: values[4] || null,
            distance: values[5] ? values[5] / 100 : null, // cm to m
            altitude: values[2] ? (values[2] / 5) - 500 : null, // Convert to meters
            latitude: values[0] ? values[0] * (180 / 2147483648) : null,
            longitude: values[1] ? values[1] * (180 / 2147483648) : null
        };
        
        activity.records.push(record);
    }

    convertTimestamp(fitTimestamp) {
        if (!fitTimestamp) return null;
        // FIT epoch is Dec 31, 1989
        const FIT_EPOCH = 631065600;
        return new Date((fitTimestamp + FIT_EPOCH) * 1000);
    }

    calculateDerivedMetrics(activity) {
        const records = activity.records.filter(r => r.power);
        
        if (records.length > 0) {
            // Calculate Normalized Power (NP)
            // 30-second rolling average of power^4, then ^0.25
            if (!activity.normalizedPower && records.length > 30) {
                const windowSize = 30; // 30 seconds
                const powerValues = records.map(r => r.power || 0);
                const rollingPower = [];
                
                for (let i = windowSize - 1; i < powerValues.length; i++) {
                    let sum = 0;
                    for (let j = i - windowSize + 1; j <= i; j++) {
                        sum += powerValues[j];
                    }
                    rollingPower.push(sum / windowSize);
                }
                
                if (rollingPower.length > 0) {
                    const fourthPower = rollingPower.map(p => Math.pow(p, 4));
                    const avgFourth = fourthPower.reduce((a, b) => a + b, 0) / fourthPower.length;
                    activity.normalizedPower = Math.round(Math.pow(avgFourth, 0.25));
                }
            }

            // Calculate average power if not set
            if (!activity.avgPower) {
                const validPower = records.filter(r => r.power && r.power > 0);
                if (validPower.length > 0) {
                    activity.avgPower = Math.round(
                        validPower.reduce((sum, r) => sum + r.power, 0) / validPower.length
                    );
                }
            }
        }

        // Calculate average HR if not set
        if (!activity.avgHeartRate) {
            const validHR = activity.records.filter(r => r.heartRate && r.heartRate > 0);
            if (validHR.length > 0) {
                activity.avgHeartRate = Math.round(
                    validHR.reduce((sum, r) => sum + r.heartRate, 0) / validHR.length
                );
            }
        }

        // Calculate average speed for running if not set
        if (!activity.avgSpeed && activity.records.length > 0) {
            const validSpeed = activity.records.filter(r => r.speed && r.speed > 0);
            if (validSpeed.length > 0) {
                activity.avgSpeed = validSpeed.reduce((sum, r) => sum + r.speed, 0) / validSpeed.length;
            }
        }

        // For swimming, calculate pace from distance and time
        if (activity.sport === 'swimming' && activity.totalDistance > 0 && activity.totalTime > 0) {
            // Pace in min/100m
            activity.avgPace = (activity.totalTime / 60) / (activity.totalDistance / 100);
        }

        // For running, calculate pace
        if (activity.sport === 'running' && activity.totalDistance > 0 && activity.totalTime > 0) {
            // Pace in min/km
            activity.avgPace = (activity.totalTime / 60) / (activity.totalDistance / 1000);
        }
    }
}

// Export for use
window.FITParser = FITParser;
