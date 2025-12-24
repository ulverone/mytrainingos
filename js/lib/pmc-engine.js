/**
 * PMC Engine for MyTrainingOS
 * Calculates CTL, ATL, TSB using TrainingPeaks exponential decay formulas
 */

class PMCEngine {
    constructor() {
        // Time constants (in days)
        this.CTL_DECAY = 42; // Chronic Training Load decay constant
        this.ATL_DECAY = 7;  // Acute Training Load decay constant

        // Pre-calculate decay factors
        this.ctlDecay = Math.exp(-1 / this.CTL_DECAY);
        this.atlDecay = Math.exp(-1 / this.ATL_DECAY);

        // Daily TSS data storage
        this.dailyTSS = new Map(); // date string -> tss value
        this.pmcData = new Map(); // date string -> {ctl, atl, tsb}
    }

    /**
     * Add or update TSS for a specific date
     */
    addTSS(date, tss) {
        const dateStr = this.formatDate(date);
        const existing = this.dailyTSS.get(dateStr) || 0;
        this.dailyTSS.set(dateStr, existing + tss);
    }

    /**
     * Set total TSS for a specific date (replaces existing)
     */
    setDailyTSS(date, tss) {
        const dateStr = this.formatDate(date);
        this.dailyTSS.set(dateStr, tss);
    }

    /**
     * Calculate PMC values using exponential weighted moving average
     * TrainingPeaks formula:
     * CTL_today = CTL_yesterday × e^(-1/42) + TSS_today × (1 - e^(-1/42))
     * ATL_today = ATL_yesterday × e^(-1/7) + TSS_today × (1 - e^(-1/7))
     * TSB_today = CTL_yesterday - ATL_yesterday
     */
    calculate(startDate = null, endDate = null) {
        // Sort dates
        const dates = Array.from(this.dailyTSS.keys()).sort();

        if (dates.length === 0) {
            return [];
        }

        // Determine date range
        const firstDate = startDate ? this.formatDate(startDate) : dates[0];
        const lastDate = endDate ? this.formatDate(endDate) : this.formatDate(new Date());

        // Generate all dates in range
        const allDates = this.generateDateRange(firstDate, lastDate);

        // Initialize values
        let ctl = 0;
        let atl = 0;

        // Calculate factors
        const ctlFactor = 1 - this.ctlDecay;
        const atlFactor = 1 - this.atlDecay;

        const results = [];

        for (const dateStr of allDates) {
            const tss = this.dailyTSS.get(dateStr) || 0;

            // Store previous CTL and ATL for TSB calculation
            // TSB is calculated BEFORE applying today's TSS
            const tsb = ctl - atl;

            // Update CTL and ATL with today's TSS
            ctl = ctl * this.ctlDecay + tss * ctlFactor;
            atl = atl * this.atlDecay + tss * atlFactor;

            const pmcEntry = {
                date: dateStr,
                tss: tss,
                ctl: Math.round(ctl * 10) / 10,
                atl: Math.round(atl * 10) / 10,
                tsb: Math.round(tsb * 10) / 10
            };

            this.pmcData.set(dateStr, pmcEntry);
            results.push(pmcEntry);
        }

        return results;
    }

    /**
     * Calculate Ramp Rate (change in CTL per week)
     */
    calculateRampRate(days = 7) {
        const today = this.formatDate(new Date());
        const weekAgo = this.formatDate(new Date(Date.now() - days * 24 * 60 * 60 * 1000));

        const todayPMC = this.pmcData.get(today);
        const weekAgoPMC = this.pmcData.get(weekAgo);

        if (!todayPMC || !weekAgoPMC) {
            return 0;
        }

        return Math.round((todayPMC.ctl - weekAgoPMC.ctl) * 10) / 10;
    }

    /**
     * Get current PMC values
     */
    getCurrentPMC() {
        const today = this.formatDate(new Date());

        // Recalculate from earliest date if needed
        if (this.pmcData.size === 0 && this.dailyTSS.size > 0) {
            const dates = Array.from(this.dailyTSS.keys()).sort();
            this.calculate(dates[0], today);
        }

        // Get today's PMC or fallback to latest available
        let pmc = this.pmcData.get(today);

        if (!pmc && this.pmcData.size > 0) {
            // Get the most recent PMC data if today is not available
            const dates = Array.from(this.pmcData.keys()).sort();
            pmc = this.pmcData.get(dates[dates.length - 1]);
        }

        pmc = pmc || { ctl: 0, atl: 0, tsb: 0 };

        return {
            ctl: pmc.ctl,
            atl: pmc.atl,
            tsb: pmc.tsb,
            rampRate: this.calculateRampRate()
        };
    }

    /**
     * Get PMC history for charting
     */
    getHistory(days = 90) {
        const endDate = new Date();
        const startDate = new Date(Date.now() - days * 24 * 60 * 60 * 1000);

        // Recalculate
        this.calculate(startDate, endDate);

        const results = [];
        const current = new Date(startDate);

        while (current <= endDate) {
            const dateStr = this.formatDate(current);
            const pmc = this.pmcData.get(dateStr);

            if (pmc) {
                results.push(pmc);
            }

            current.setDate(current.getDate() + 1);
        }

        return results;
    }

    /**
     * Get weekly summaries
     */
    getWeeklySummaries(weeks = 12) {
        const summaries = [];
        const now = new Date();

        for (let w = 0; w < weeks; w++) {
            const weekEnd = new Date(now);
            weekEnd.setDate(weekEnd.getDate() - (7 * w));

            // Get Monday of that week
            const weekStart = new Date(weekEnd);
            const day = weekStart.getDay();
            const diff = weekStart.getDate() - day + (day === 0 ? -6 : 1);
            weekStart.setDate(diff);

            // Calculate weekly totals
            let weeklyTSS = 0;
            let activities = 0;

            const current = new Date(weekStart);
            while (current <= weekEnd && current <= now) {
                const dateStr = this.formatDate(current);
                const tss = this.dailyTSS.get(dateStr) || 0;
                if (tss > 0) {
                    weeklyTSS += tss;
                    activities++;
                }
                current.setDate(current.getDate() + 1);
            }

            // Get PMC values at week end
            const pmcEnd = this.pmcData.get(this.formatDate(weekEnd > now ? now : weekEnd));

            summaries.push({
                weekStart: this.formatDate(weekStart),
                weekEnd: this.formatDate(weekEnd > now ? now : weekEnd),
                weekNumber: this.getWeekNumber(weekStart),
                year: weekStart.getFullYear(),
                totalTSS: Math.round(weeklyTSS),
                activities: activities,
                avgDailyTSS: activities > 0 ? Math.round(weeklyTSS / 7) : 0,
                ctl: pmcEnd ? pmcEnd.ctl : 0,
                atl: pmcEnd ? pmcEnd.atl : 0,
                tsb: pmcEnd ? pmcEnd.tsb : 0
            });
        }

        return summaries.reverse();
    }

    /**
     * Interpret TSB status
     */
    getTSBStatus(tsb) {
        if (tsb > 5) {
            return { status: 'good', label: 'Pronto', description: 'Buona forma, pronto per gare/sforzi intensi' };
        } else if (tsb >= -10) {
            return { status: 'normal', label: 'OK', description: 'Stato di allenamento normale' };
        } else {
            return { status: 'tired', label: 'Affaticato', description: 'Affaticamento accumulato, considera recupero' };
        }
    }

    /**
     * Interpret Ramp Rate
     */
    getRampRateStatus(rampRate) {
        if (rampRate > 10) {
            return { status: 'warning', label: 'Attenzione', description: 'Rischio sovrallenamento' };
        } else if (rampRate >= 3 && rampRate <= 8) {
            return { status: 'good', label: 'Ideale', description: 'Progressione ottimale' };
        } else if (rampRate >= 0) {
            return { status: 'normal', label: 'Stabile', description: 'Mantenimento fitness' };
        } else {
            return { status: 'recovery', label: 'Recupero', description: 'Fase di scarico' };
        }
    }

    /**
     * Generate date range between two dates
     */
    generateDateRange(startDate, endDate) {
        const dates = [];
        const current = new Date(startDate);
        const end = new Date(endDate);

        while (current <= end) {
            dates.push(this.formatDate(current));
            current.setDate(current.getDate() + 1);
        }

        return dates;
    }

    /**
     * Format date as YYYY-MM-DD
     */
    formatDate(date) {
        if (typeof date === 'string') return date;
        const d = new Date(date);
        return d.toISOString().split('T')[0];
    }

    /**
     * Get ISO week number
     */
    getWeekNumber(date) {
        const d = new Date(date);
        d.setHours(0, 0, 0, 0);
        d.setDate(d.getDate() + 4 - (d.getDay() || 7));
        const yearStart = new Date(d.getFullYear(), 0, 1);
        return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
    }

    /**
     * Clear all data
     */
    clear() {
        this.dailyTSS.clear();
        this.pmcData.clear();
    }

    /**
     * Export data for storage
     */
    export() {
        return {
            dailyTSS: Object.fromEntries(this.dailyTSS),
            lastCalculated: new Date().toISOString()
        };
    }

    /**
     * Import data from storage
     */
    import(data) {
        if (data.dailyTSS) {
            this.dailyTSS = new Map(Object.entries(data.dailyTSS));
            this.calculate();
        }
    }
}

// Export for use
window.PMCEngine = PMCEngine;
