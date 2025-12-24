/**
 * TSS Calculator for MyTrainingOS
 * Calculates Training Stress Scores using TrainingPeaks formulas
 */

class TSSCalculator {
    constructor(settings = {}) {
        // Default thresholds
        this.ftp = settings.ftp || 300; // Functional Threshold Power (W)
        this.runThreshold = settings.runThreshold || 256; // Threshold pace in seconds/km (4:16)
        this.swimThreshold = settings.swimThreshold || 100; // Threshold pace in seconds/100m (1:40)

        // Heart rate zones (backup calculation)
        this.lthr = settings.lthr || 155; // Lactate Threshold Heart Rate
    }

    /**
     * Update threshold settings
     */
    updateSettings(settings) {
        if (settings.ftp) this.ftp = settings.ftp;
        if (settings.runThreshold) this.runThreshold = settings.runThreshold;
        if (settings.swimThreshold) this.swimThreshold = settings.swimThreshold;
        if (settings.lthr) this.lthr = settings.lthr;
    }

    /**
     * Calculate TSS based on activity sport type
     */
    calculate(activity) {
        switch (activity.sport) {
            case 'cycling':
                return this.calculateCyclingTSS(activity);
            case 'running':
                return this.calculateRunningTSS(activity);
            case 'swimming':
                return this.calculateSwimmingTSS(activity);
            default:
                // Fallback to HR-based TSS
                return this.calculateHRBasedTSS(activity);
        }
    }

    /**
     * Recalculate TSS for a stored activity (uses different field names)
     */
    recalculate(activity) {
        // Map stored fields to expected format
        const mapped = {
            sport: activity.sport,
            totalTime: activity.duration,
            totalDistance: activity.distance,
            normalizedPower: activity.normalizedPower,
            avgPower: activity.avgPower,
            avgHeartRate: activity.avgHR
        };
        return this.calculate(mapped);
    }

    /**
     * Calculate Cycling TSS (with power)
     * TSS = (duration_seconds × NP × IF) / (FTP × 3600) × 100
     * where IF = NP / FTP
     */
    calculateCyclingTSS(activity) {
        const duration = activity.totalTime; // in seconds
        const np = activity.normalizedPower || activity.avgPower;

        if (!np || !duration) {
            // Fallback to HR-based if no power
            return this.calculateHRBasedTSS(activity);
        }

        const IF = np / this.ftp;
        const tss = (duration * np * IF) / (this.ftp * 3600) * 100;

        return {
            tss: Math.round(tss),
            type: 'TSS',
            IF: Math.round(IF * 100) / 100,
            np: Math.round(np),
            method: 'power'
        };
    }

    /**
     * Calculate Running TSS (rTSS)
     * Based on normalized graded pace
     * IF = ThresholdPace / ActualPace (faster = higher IF)
     * rTSS = (duration_seconds × IF² × 100) / 3600
     */
    calculateRunningTSS(activity) {
        const duration = activity.totalTime; // in seconds
        const distance = activity.totalDistance; // in meters

        if (!duration || !distance || distance < 100) {
            return this.calculateHRBasedTSS(activity);
        }

        // Calculate pace in seconds/km
        const paceSecsPerKm = (duration / (distance / 1000));

        // Intensity Factor: threshold pace / actual pace
        // Lower paceSecsPerKm (faster) = higher IF
        const IF = this.runThreshold / paceSecsPerKm;

        // rTSS formula (TrainingPeaks style)
        // rTSS = (duration_hours × IF² × 100)
        const durationHours = duration / 3600;
        const rtss = durationHours * Math.pow(IF, 2) * 100;

        return {
            tss: Math.round(rtss),
            type: 'rTSS',
            IF: Math.round(IF * 100) / 100,
            pace: this.formatPace(paceSecsPerKm),
            paceSeconds: paceSecsPerKm,
            method: 'pace'
        };
    }

    /**
     * Calculate Swimming TSS (sTSS)
     * sTSS = IF³ × duration_hours × 100
     */
    calculateSwimmingTSS(activity) {
        const duration = activity.totalTime; // in seconds
        const distance = activity.totalDistance; // in meters

        if (!duration || !distance || distance < 25) {
            return this.calculateHRBasedTSS(activity);
        }

        // Calculate pace in seconds per 100m
        const pacePer100m = (duration / (distance / 100));

        // IF = threshold / actual (faster = higher IF)
        const IF = this.swimThreshold / pacePer100m;

        // sTSS = IF³ × hours × 100
        const durationHours = duration / 3600;
        const stss = Math.pow(IF, 3) * durationHours * 100;

        return {
            tss: Math.round(stss),
            type: 'sTSS',
            IF: Math.round(IF * 100) / 100,
            pace: this.formatSwimPace(pacePer100m),
            paceSeconds: pacePer100m,
            method: 'pace'
        };
    }

    /**
     * Calculate HR-based TSS (hrTSS) as fallback
     * Uses TRIMP-style calculation with heart rate
     */
    calculateHRBasedTSS(activity) {
        const duration = activity.totalTime;
        const avgHR = activity.avgHeartRate;

        if (!duration || !avgHR) {
            // Ultimate fallback: estimate based on duration
            return {
                tss: Math.round(duration / 60), // ~1 TSS per minute
                type: 'TSS',
                IF: 0.7,
                method: 'duration_estimate'
            };
        }

        // Heart rate reserve method
        const restingHR = 50; // Assumed resting HR
        const maxHR = 220 - 47; // Estimated max HR for 47yo

        // TRIMP-style HR factor
        const hrReserve = (avgHR - restingHR) / (maxHR - restingHR);
        const IF = avgHR / this.lthr;

        // hrTSS formula
        const durationHours = duration / 3600;
        const hrTss = durationHours * Math.pow(IF, 2) * 100;

        return {
            tss: Math.round(hrTss),
            type: 'hrTSS',
            IF: Math.round(IF * 100) / 100,
            avgHR: avgHR,
            method: 'heart_rate'
        };
    }

    /**
     * Determine training zone based on intensity
     */
    getZone(IF) {
        if (IF < 0.55) return { zone: 1, name: 'Recupero', color: '#a0aec0' };
        if (IF < 0.75) return { zone: 2, name: 'Fondo', color: '#48bb78' };
        if (IF < 0.90) return { zone: 3, name: 'Tempo', color: '#ecc94b' };
        if (IF < 1.05) return { zone: 4, name: 'Soglia', color: '#ed8936' };
        return { zone: 5, name: 'VO2max', color: '#f56565' };
    }

    /**
     * Format pace as mm:ss/km
     */
    formatPace(secondsPerKm) {
        const minutes = Math.floor(secondsPerKm / 60);
        const seconds = Math.round(secondsPerKm % 60);
        return `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }

    /**
     * Format swim pace as mm:ss/100m
     */
    formatSwimPace(secondsPer100m) {
        const minutes = Math.floor(secondsPer100m / 60);
        const seconds = Math.round(secondsPer100m % 60);
        return `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }

    /**
     * Parse pace string to seconds
     */
    static parsePace(paceString) {
        const parts = paceString.split(':');
        if (parts.length !== 2) return null;
        return parseInt(parts[0]) * 60 + parseInt(parts[1]);
    }
}

// Export for use
window.TSSCalculator = TSSCalculator;
