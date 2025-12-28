/**
 * MyTrainingOS - Main Application
 * Training management app with PMC calculations
 */

class App {
    constructor() {
        this.db = null;
        this.fitParser = new FITParser();
        this.tssCalculator = null;
        this.pmcEngine = new PMCEngine();
        this.pmcChart = null;
        this.activities = [];
        this.currentView = 'dashboard';
        this.currentMonth = new Date();
        this.settings = {
            ftp: 300,
            runThreshold: '4:16',
            swimThreshold: '1:40'
        };
    }

    async init() {
        // Initialize database
        this.db = new Database();
        await this.db.init();

        // Load settings
        await this.loadSettings();

        // Initialize TSS calculator with settings
        this.tssCalculator = new TSSCalculator({
            ftp: this.settings.ftp,
            runThreshold: TSSCalculator.parsePace(this.settings.runThreshold),
            swimThreshold: TSSCalculator.parsePace(this.settings.swimThreshold)
        });

        // Try to load pre-imported activities from JSON file
        await this.loadPreImportedActivities();

        // Load activities
        await this.loadActivities();

        // Setup event listeners
        this.setupNavigation();
        this.setupImport();
        this.setupCalendar();
        this.setupSettings();
        this.setupFilters();

        // Update display
        this.updateDate();
        this.updateDashboard();
        this.updateCalendar();
        this.updateActivitiesTable();

        // Load Oura data if available
        await this.loadOuraData();

        // Resize handler
        window.addEventListener('resize', () => {
            if (this.pmcChart) this.pmcChart.resize();
        });
    }

    async loadSettings() {
        const saved = await this.db.getAllSettings();
        if (saved.ftp) this.settings.ftp = saved.ftp;
        if (saved.runThreshold) this.settings.runThreshold = saved.runThreshold;
        if (saved.swimThreshold) this.settings.swimThreshold = saved.swimThreshold;

        // Update form
        document.getElementById('ftp').value = this.settings.ftp;
        document.getElementById('runThreshold').value = this.settings.runThreshold;
        document.getElementById('swimThreshold').value = this.settings.swimThreshold;
    }

    async loadPreImportedActivities() {
        try {
            const response = await fetch('data/activities.json');
            if (response.ok) {
                const data = await response.json();
                console.log(`Found ${data.count} pre-imported activities (exported: ${data.exportDate})`);

                // Check if we need to reimport based on export date or count
                const existingCount = await this.db.getActivityCount();
                const lastImportDate = localStorage.getItem('lastImportDate');

                // Reimport if: server has newer export OR server has more activities
                const serverExportDate = data.exportDate || '';
                const needsReimport = !lastImportDate ||
                    serverExportDate > lastImportDate ||
                    existingCount < data.count;

                if (needsReimport) {
                    console.log(`Reimporting: lastImport=${lastImportDate}, serverExport=${serverExportDate}, existing=${existingCount}, new=${data.count}`);
                    // Clear existing activities and reimport all
                    await this.db.clearActivities();
                    for (const activity of data.activities) {
                        await this.db.addActivity(activity);
                    }
                    localStorage.setItem('lastImportDate', serverExportDate);
                    console.log('Import complete!');
                } else {
                    console.log('Activities already up to date');
                }
            }
        } catch (e) {
            console.log('No pre-imported activities found:', e.message);
        }
    }


    async loadOuraData() {
        try {
            const response = await fetch('data/oura.json');
            if (!response.ok) {
                console.log('No Oura data file found');
                return;
            }

            const data = await response.json();

            // Use the pre-aggregated daily section which has all metrics
            if (data.daily && data.daily.length > 0) {

                // Calculate personal baselines from all historical data
                const calcStats = (values) => {
                    if (values.length === 0) return { avg: 0, stdev: 0 };
                    const avg = values.reduce((a, b) => a + b, 0) / values.length;
                    const variance = values.reduce((sum, v) => sum + Math.pow(v - avg, 2), 0) / values.length;
                    return { avg, stdev: Math.sqrt(variance) };
                };

                const getValues = (key) => data.daily
                    .filter(d => d[key] !== undefined && d[key] !== null)
                    .map(d => d[key]);

                // Calculate personal ranges for each metric
                const personalRanges = {};
                const metrics = ['sleepScore', 'readinessScore', 'hrv', 'recoveryIndex',
                    'lowestHR', 'restingHR', 'hrvBalance', 'efficiency', 'deepSleep', 'totalSleep'];

                metrics.forEach(m => {
                    const stats = calcStats(getValues(m));
                    personalRanges[m] = {
                        avg: stats.avg,
                        stdev: stats.stdev,
                        optimal: stats.avg + stats.stdev * 0.5,  // Above avg + 0.5 stdev
                        warning: stats.avg - stats.stdev,        // Below avg - 1 stdev
                        danger: stats.avg - stats.stdev * 1.5    // Below avg - 1.5 stdev
                    };
                });

                // Get today's or most recent data
                const today = new Date().toISOString().split('T')[0];
                let todayData = data.daily.find(d => d.date === today);

                if (!todayData) {
                    todayData = data.daily.find(d => d.sleepScore !== undefined);
                }

                if (todayData) {
                    // Show Oura section
                    const ouraSection = document.getElementById('oura-section');
                    if (ouraSection) {
                        ouraSection.style.display = 'block';
                    }

                    // Show date
                    const dateEl = document.getElementById('oura-date');
                    if (dateEl && todayData.date) {
                        const d = new Date(todayData.date);
                        dateEl.textContent = `(${d.toLocaleDateString('it-IT')})`;
                    }

                    // Helper to set value and status based on personal ranges
                    const setMetricPersonal = (id, value, metricKey, inverted = false) => {
                        const el = document.getElementById(id);
                        if (el && value !== undefined) {
                            el.textContent = value;

                            const parent = el.closest('.oura-metric') || el.closest('.oura-stat');
                            const range = personalRanges[metricKey];

                            if (parent && range) {
                                parent.classList.remove('warning', 'danger', 'optimal');

                                if (inverted) {
                                    // For metrics where lower is better (e.g., lowestHR for athletes)
                                    if (value <= range.avg - range.stdev * 0.5) {
                                        parent.classList.add('optimal');
                                    } else if (value > range.avg + range.stdev) {
                                        parent.classList.add('danger');
                                    } else if (value > range.avg + range.stdev * 0.5) {
                                        parent.classList.add('warning');
                                    }
                                } else {
                                    // Normal: higher is better
                                    if (value >= range.optimal) {
                                        parent.classList.add('optimal');
                                    } else if (value < range.danger) {
                                        parent.classList.add('danger');
                                    } else if (value < range.warning) {
                                        parent.classList.add('warning');
                                    }
                                }

                                // Update range display text
                                const rangeEl = parent.querySelector('.metric-range, .stat-range');
                                if (rangeEl) {
                                    rangeEl.textContent = `Media: ${range.avg.toFixed(0)} (tuo range)`;
                                }
                            }
                        }
                    };

                    // Helper to set progress bar relative to personal range
                    const setFillPersonal = (id, value, metricKey) => {
                        const el = document.getElementById(id);
                        const range = personalRanges[metricKey];
                        if (el && value !== undefined && range) {
                            // Show fill as percentage of max historical + some headroom
                            const max = range.avg + range.stdev * 2;
                            el.style.width = `${Math.min(100, (value / max) * 100)}%`;
                        }
                    };

                    // Main metrics with personal ranges
                    setMetricPersonal('oura-sleep', todayData.sleepScore, 'sleepScore');
                    setFillPersonal('fill-sleep', todayData.sleepScore, 'sleepScore');

                    setMetricPersonal('oura-readiness', todayData.readinessScore, 'readinessScore');
                    setFillPersonal('fill-readiness', todayData.readinessScore, 'readinessScore');

                    // HRV with ms suffix
                    if (todayData.hrv !== undefined) {
                        document.getElementById('oura-hrv').textContent = `${todayData.hrv} ms`;
                        const hrvParent = document.getElementById('metric-hrv');
                        const hrvRange = personalRanges.hrv;
                        hrvParent.classList.remove('warning', 'danger', 'optimal');

                        if (todayData.hrv >= hrvRange.optimal) {
                            hrvParent.classList.add('optimal');
                        } else if (todayData.hrv < hrvRange.danger) {
                            hrvParent.classList.add('danger');
                        } else if (todayData.hrv < hrvRange.warning) {
                            hrvParent.classList.add('warning');
                        }

                        const hrvRangeEl = hrvParent.querySelector('.metric-range');
                        if (hrvRangeEl) {
                            hrvRangeEl.textContent = `Media: ${hrvRange.avg.toFixed(0)} ms (tuo range)`;
                        }
                        setFillPersonal('fill-hrv', todayData.hrv, 'hrv');
                    }

                    setMetricPersonal('oura-recovery', todayData.recoveryIndex, 'recoveryIndex');
                    setFillPersonal('fill-recovery', todayData.recoveryIndex, 'recoveryIndex');

                    // Secondary metrics with personal ranges
                    // Lowest HR: lower is better for athletes (inverted)
                    setMetricPersonal('oura-lowesthr', todayData.lowestHR, 'lowestHR', true);
                    setMetricPersonal('oura-restinghr', todayData.restingHR, 'restingHR');
                    setMetricPersonal('oura-hrvbalance', todayData.hrvBalance, 'hrvBalance');
                    setMetricPersonal('oura-efficiency', todayData.efficiency, 'efficiency');
                    setMetricPersonal('oura-deepsleep', todayData.deepSleep, 'deepSleep');
                    setMetricPersonal('oura-totalsleep', todayData.totalSleep, 'totalSleep');

                    // Generate sparklines (last 7 days)
                    const generateSparkline = (svgId, metricKey, days = 7) => {
                        const svg = document.getElementById(svgId);
                        if (!svg) return;

                        // Get last N days of data
                        const recentData = data.daily
                            .filter(d => d[metricKey] !== undefined)
                            .slice(0, days)
                            .reverse();

                        if (recentData.length < 2) return;

                        const values = recentData.map(d => d[metricKey]);
                        const min = Math.min(...values);
                        const max = Math.max(...values);
                        const range = max - min || 1;

                        // Generate path points
                        const points = values.map((v, i) => {
                            const x = (i / (values.length - 1)) * 100;
                            const y = 30 - ((v - min) / range) * 25;
                            return `${x},${y}`;
                        });

                        // Create line path
                        const linePath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                        linePath.setAttribute('d', `M ${points.join(' L ')}`);

                        // Create area path (for gradient fill)
                        const areaPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                        areaPath.setAttribute('class', 'area');
                        areaPath.setAttribute('d', `M 0,30 L ${points.join(' L ')} L 100,30 Z`);

                        svg.innerHTML = '';
                        svg.appendChild(areaPath);
                        svg.appendChild(linePath);
                    };

                    // Generate all sparklines
                    generateSparkline('spark-sleep', 'sleepScore');
                    generateSparkline('spark-readiness', 'readinessScore');
                    generateSparkline('spark-hrv', 'hrv');
                    generateSparkline('spark-recovery', 'recoveryIndex');

                    // Calculate and show trends
                    const calcTrend = (metricKey) => {
                        const recentData = data.daily
                            .filter(d => d[metricKey] !== undefined)
                            .slice(0, 7);

                        if (recentData.length < 2) return { arrow: '→', class: 'stable', diff: 0 };

                        const today = recentData[0][metricKey];
                        const yesterday = recentData[1][metricKey];
                        const diff = today - yesterday;

                        if (diff > 3) return { arrow: '↑', class: 'up', diff };
                        if (diff < -3) return { arrow: '↓', class: 'down', diff };
                        return { arrow: '→', class: 'stable', diff };
                    };

                    const setTrend = (id, metricKey) => {
                        const el = document.getElementById(id);
                        if (!el) return;
                        const trend = calcTrend(metricKey);
                        el.textContent = trend.arrow;
                        el.className = `metric-trend ${trend.class}`;
                    };

                    setTrend('trend-sleep', 'sleepScore');
                    setTrend('trend-readiness', 'readinessScore');
                    setTrend('trend-hrv', 'hrv');
                    setTrend('trend-recovery', 'recoveryIndex');

                    // Check for out-of-range alerts
                    const warnings = document.querySelectorAll('.oura-metric.warning, .oura-stat.warning').length;
                    const dangers = document.querySelectorAll('.oura-metric.danger, .oura-stat.danger').length;

                    if (warnings > 0 || dangers > 0) {
                        const alertBanner = document.getElementById('oura-alerts');
                        const alertText = document.getElementById('alert-text');

                        if (alertBanner && alertText) {
                            const messages = [];
                            if (dangers > 0) messages.push(`${dangers} in pericolo`);
                            if (warnings > 0) messages.push(`${warnings} sotto la media`);
                            alertText.textContent = messages.join(', ');
                            alertBanner.style.display = 'flex';

                            // Dismiss button
                            const dismissBtn = document.getElementById('alert-dismiss');
                            if (dismissBtn) {
                                dismissBtn.onclick = () => alertBanner.style.display = 'none';
                            }
                        }
                    }

                    console.log('Oura data loaded with personal ranges:', todayData);
                    console.log('Personal baselines:', personalRanges);
                }
            }

            this.ouraData = data;

        } catch (error) {
            console.log('Could not load Oura data:', error.message);
        }
    }

    async loadActivities() {
        this.activities = await this.db.getAllActivities();

        // Rebuild PMC data
        this.pmcEngine.clear();

        // Group activities by date
        const dailyTSS = new Map();
        this.activities.forEach(a => {
            const date = new Date(a.startTime).toISOString().split('T')[0];
            const existing = dailyTSS.get(date) || 0;
            dailyTSS.set(date, existing + (a.tss || 0));
        });

        // Add to PMC engine
        dailyTSS.forEach((tss, date) => {
            this.pmcEngine.setDailyTSS(date, tss);
        });

        // Calculate PMC
        if (dailyTSS.size > 0) {
            const dates = Array.from(dailyTSS.keys()).sort();
            this.pmcEngine.calculate(dates[0], new Date());
        }

        // Update activity count
        document.getElementById('activityCount').textContent = this.activities.length;
    }

    setupNavigation() {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const view = item.dataset.view;
                this.switchView(view);
            });
        });
    }

    switchView(view) {
        // Update nav
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.querySelector(`[data-view="${view}"]`).classList.add('active');

        // Update views
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        document.getElementById(`${view}-view`).classList.add('active');

        this.currentView = view;

        // Initialize PMC chart if needed
        if (view === 'pmc' && !this.pmcChart) {
            const canvas = document.getElementById('pmcChart');
            this.pmcChart = new PMCChart(canvas);
            this.updatePMCChart(90);
            this.setupChartControls();
        }
    }

    setupChartControls() {
        document.querySelectorAll('.btn-range').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.btn-range').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const days = parseInt(btn.dataset.range);
                this.updatePMCChart(days);
            });
        });
    }

    updatePMCChart(days) {
        const data = this.pmcEngine.getHistory(days);
        if (this.pmcChart && data.length > 0) {
            this.pmcChart.setData(data);
        }
    }

    setupImport() {
        const importBtn = document.getElementById('importBtn');
        const dropzone = document.getElementById('dropzone');
        const fileInput = document.getElementById('fileInput');
        const browseBtn = document.getElementById('browseBtn');
        const modal = document.getElementById('importModal');

        importBtn.addEventListener('click', () => modal.classList.add('active'));

        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.modal').forEach(m => m.classList.remove('active'));
            });
        });

        browseBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (e) => this.handleFiles(e.target.files));

        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });

        dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));

        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            this.handleFiles(e.dataTransfer.files);
        });
    }

    async handleFiles(files) {
        const fitFiles = Array.from(files).filter(f => f.name.endsWith('.fit'));

        if (fitFiles.length === 0) {
            alert('Nessun file .fit trovato');
            return;
        }

        const progress = document.getElementById('importProgress');
        const progressFill = document.getElementById('importProgressFill');
        const status = document.getElementById('importStatus');

        progress.classList.add('active');

        for (let i = 0; i < fitFiles.length; i++) {
            const file = fitFiles[i];
            const percent = ((i + 1) / fitFiles.length) * 100;
            progressFill.style.width = `${percent}%`;
            status.textContent = `Importando ${file.name}...`;

            try {
                await this.importFITFile(file);
            } catch (error) {
                console.error(`Error importing ${file.name}:`, error);
            }
        }

        status.textContent = `Importati ${fitFiles.length} file!`;

        setTimeout(() => {
            progress.classList.remove('active');
            document.getElementById('importModal').classList.remove('active');
            progressFill.style.width = '0%';
        }, 1500);

        // Reload and update
        await this.loadActivities();
        this.updateDashboard();
        this.updateCalendar();
        this.updateActivitiesTable();
        if (this.pmcChart) this.updatePMCChart(90);
    }

    async importFITFile(file) {
        const buffer = await file.arrayBuffer();
        const activity = await this.fitParser.parse(buffer);

        // Calculate TSS
        const tssResult = this.tssCalculator.calculate(activity);

        // Create activity record
        const record = {
            id: this.db.generateActivityId(activity),
            filename: file.name,
            sport: activity.sport,
            subSport: activity.subSport,
            startTime: activity.startTime?.toISOString() || new Date().toISOString(),
            duration: activity.totalTime,
            distance: activity.totalDistance,
            calories: activity.totalCalories,
            avgHR: activity.avgHeartRate,
            maxHR: activity.maxHeartRate,
            avgPower: activity.avgPower,
            normalizedPower: activity.normalizedPower,
            avgSpeed: activity.avgSpeed,
            avgPace: activity.avgPace,
            avgCadence: activity.avgCadence,
            tss: tssResult.tss,
            tssType: tssResult.type,
            IF: tssResult.IF,
            laps: activity.laps,
            recordsCount: activity.records.length
        };

        await this.db.addActivity(record);
    }

    updateDate() {
        const now = new Date();
        const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
        document.getElementById('currentDate').textContent = now.toLocaleDateString('it-IT', options);
    }

    updateDashboard() {
        const pmc = this.pmcEngine.getCurrentPMC();

        // PMC cards
        document.getElementById('ctl-value').textContent = pmc.ctl.toFixed(1);
        document.getElementById('atl-value').textContent = pmc.atl.toFixed(1);
        document.getElementById('tsb-value').textContent = pmc.tsb.toFixed(1);
        document.getElementById('ramp-value').textContent = pmc.rampRate.toFixed(1);

        // TSB status
        const tsbStatus = this.pmcEngine.getTSBStatus(pmc.tsb);
        const tsbStatusEl = document.getElementById('tsb-status');
        tsbStatusEl.textContent = tsbStatus.label;
        tsbStatusEl.className = 'card-status ' + tsbStatus.status;

        // Weekly stats
        this.updateWeeklyStats();
        this.updateSportBreakdown();
        this.updateRecentActivities();
    }

    updateWeeklyStats() {
        const now = new Date();
        const monday = new Date(now);
        const day = monday.getDay();
        monday.setDate(monday.getDate() - (day === 0 ? 6 : day - 1));
        monday.setHours(0, 0, 0, 0);

        const weekActivities = this.activities.filter(a => new Date(a.startTime) >= monday);

        const totalTSS = weekActivities.reduce((sum, a) => sum + (a.tss || 0), 0);
        const totalHours = weekActivities.reduce((sum, a) => sum + (a.duration || 0), 0) / 3600;
        const totalDistance = weekActivities.reduce((sum, a) => sum + (a.distance || 0), 0) / 1000;

        document.getElementById('weekly-tss').textContent = Math.round(totalTSS);
        document.getElementById('weekly-count').textContent = weekActivities.length;
        document.getElementById('weekly-hours').textContent = totalHours.toFixed(1);
        document.getElementById('weekly-distance').textContent = totalDistance.toFixed(1) + ' km';
    }

    updateSportBreakdown() {
        const now = new Date();
        const monday = new Date(now);
        const day = monday.getDay();
        monday.setDate(monday.getDate() - (day === 0 ? 6 : day - 1));
        monday.setHours(0, 0, 0, 0);

        const weekActivities = this.activities.filter(a => new Date(a.startTime) >= monday);

        const swimTSS = weekActivities.filter(a => a.sport === 'swimming').reduce((s, a) => s + (a.tss || 0), 0);
        const bikeTSS = weekActivities.filter(a => a.sport === 'cycling').reduce((s, a) => s + (a.tss || 0), 0);
        const runTSS = weekActivities.filter(a => a.sport === 'running').reduce((s, a) => s + (a.tss || 0), 0);

        const maxTSS = Math.max(swimTSS, bikeTSS, runTSS, 50);

        document.getElementById('swim-progress').style.width = `${(swimTSS / maxTSS) * 100}%`;
        document.getElementById('bike-progress').style.width = `${(bikeTSS / maxTSS) * 100}%`;
        document.getElementById('run-progress').style.width = `${(runTSS / maxTSS) * 100}%`;

        document.getElementById('swim-tss').textContent = Math.round(swimTSS);
        document.getElementById('bike-tss').textContent = Math.round(bikeTSS);
        document.getElementById('run-tss').textContent = Math.round(runTSS);
    }

    updateRecentActivities() {
        const recent = this.activities.slice(0, 5);
        const container = document.getElementById('recent-activities-list');

        if (recent.length === 0) {
            container.innerHTML = '<p class="empty-state">Importa file FIT per visualizzare le attività</p>';
            return;
        }

        container.innerHTML = recent.map(a => this.renderActivityItem(a)).join('');

        container.querySelectorAll('.activity-item').forEach((item, i) => {
            item.addEventListener('click', () => this.showActivityDetail(recent[i]));
        });
    }

    renderActivityItem(activity) {
        const sportIcon = this.getSportIcon(activity.sport);
        const sportClass = this.getSportClass(activity.sport);
        const date = new Date(activity.startTime);
        const duration = this.formatDuration(activity.duration);
        const distance = activity.distance ? (activity.distance / 1000).toFixed(2) + ' km' : '';

        return `
            <div class="activity-item">
                <div class="activity-sport ${sportClass}">${sportIcon}</div>
                <div class="activity-info">
                    <div class="activity-title">${this.getSportName(activity.sport)}</div>
                    <div class="activity-meta">${date.toLocaleDateString('it-IT')} • ${duration} • ${distance}</div>
                </div>
                <div class="activity-tss">
                    <div class="activity-tss-value">${activity.tss || 0}</div>
                    <div class="activity-tss-label">${activity.tssType || 'TSS'}</div>
                </div>
            </div>
        `;
    }

    getSportIcon(sport) {
        const icons = { swimming: '🏊‍♂️', cycling: '🚴‍♂️', running: '🏃‍♂️' };
        return icons[sport] || '🏋️';
    }

    getSportClass(sport) {
        const classes = { swimming: 'swim', cycling: 'bike', running: 'run' };
        return classes[sport] || '';
    }

    getSportName(sport) {
        const names = { swimming: 'Nuoto', cycling: 'Ciclismo', running: 'Corsa' };
        return names[sport] || 'Altro';
    }

    formatDuration(seconds) {
        if (!seconds) return '0:00';
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        return h > 0 ? `${h}h ${m}m` : `${m} min`;
    }

    formatLocalDate(date) {
        const d = new Date(date);
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    showActivityDetail(activity) {
        const modal = document.getElementById('activityModal');
        const body = document.getElementById('modalBody');

        const date = new Date(activity.startTime);
        const lapsHtml = (activity.laps || []).map((lap, i) => `
            <tr>
                <td>Lap ${i + 1}</td>
                <td>${this.formatDuration(lap.totalTime)}</td>
                <td>${lap.totalDistance ? (lap.totalDistance / 1000).toFixed(2) + ' km' : '-'}</td>
                <td>${lap.avgHeartRate || '-'}</td>
                <td>${lap.avgPower || '-'}</td>
            </tr>
        `).join('');

        body.innerHTML = `
            <h2>${this.getSportIcon(activity.sport)} ${this.getSportName(activity.sport)}</h2>
            <p style="color: var(--text-muted); margin-bottom: 20px;">
                ${date.toLocaleDateString('it-IT', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
            </p>
            <div class="pmc-cards" style="grid-template-columns: repeat(4, 1fr); margin-bottom: 24px;">
                <div class="pmc-card"><div class="card-label">Durata</div><div class="card-value" style="font-size: 1.5rem;">${this.formatDuration(activity.duration)}</div></div>
                <div class="pmc-card"><div class="card-label">Distanza</div><div class="card-value" style="font-size: 1.5rem;">${activity.distance ? (activity.distance / 1000).toFixed(2) : 0} km</div></div>
                <div class="pmc-card"><div class="card-label">${activity.tssType || 'TSS'}</div><div class="card-value" style="font-size: 1.5rem; color: var(--accent-purple);">${activity.tss || 0}</div></div>
                <div class="pmc-card"><div class="card-label">IF</div><div class="card-value" style="font-size: 1.5rem;">${activity.IF || '-'}</div></div>
            </div>
            <h3 style="margin-bottom: 16px;">Metriche</h3>
            <div class="weekly-stats" style="margin-bottom: 24px;">
                <div class="weekly-stat"><span class="stat-label">FC Media</span><span class="stat-value">${activity.avgHR || '-'}</span></div>
                <div class="weekly-stat"><span class="stat-label">FC Max</span><span class="stat-value">${activity.maxHR || '-'}</span></div>
                <div class="weekly-stat"><span class="stat-label">Potenza Media</span><span class="stat-value">${activity.avgPower || '-'}</span></div>
                <div class="weekly-stat"><span class="stat-label">NP</span><span class="stat-value">${activity.normalizedPower || '-'}</span></div>
            </div>
            ${lapsHtml ? `
                <h3 style="margin-bottom: 16px;">Laps (${activity.laps?.length || 0})</h3>
                <div class="activities-table-container">
                    <table class="activities-table">
                        <thead><tr><th>Lap</th><th>Tempo</th><th>Distanza</th><th>FC</th><th>Potenza</th></tr></thead>
                        <tbody>${lapsHtml}</tbody>
                    </table>
                </div>
            ` : ''}
        `;

        modal.classList.add('active');
    }

    setupCalendar() {
        document.getElementById('prevMonth').addEventListener('click', () => {
            this.currentMonth.setMonth(this.currentMonth.getMonth() - 1);
            this.updateCalendar();
        });

        document.getElementById('nextMonth').addEventListener('click', () => {
            this.currentMonth.setMonth(this.currentMonth.getMonth() + 1);
            this.updateCalendar();
        });
    }

    updateCalendar() {
        const year = this.currentMonth.getFullYear();
        const month = this.currentMonth.getMonth();

        document.getElementById('currentMonth').textContent =
            this.currentMonth.toLocaleDateString('it-IT', { month: 'long', year: 'numeric' });

        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const startDay = (firstDay.getDay() + 6) % 7; // Monday = 0

        const grid = document.getElementById('calendar-grid');
        grid.innerHTML = '';

        const today = new Date();
        today.setHours(0, 0, 0, 0);

        // Collect all days for weekly TSS calculation
        let allDays = [];

        // Previous month days
        const prevMonth = new Date(year, month, 0);
        for (let i = startDay - 1; i >= 0; i--) {
            const day = prevMonth.getDate() - i;
            allDays.push({ date: new Date(year, month - 1, day), isOtherMonth: true, isToday: false });
        }

        // Current month days
        for (let day = 1; day <= lastDay.getDate(); day++) {
            const date = new Date(year, month, day);
            const isToday = date.getTime() === today.getTime();
            allDays.push({ date, isOtherMonth: false, isToday });
        }

        // Next month days
        const totalCells = startDay + lastDay.getDate();
        const remainingCells = 7 - (totalCells % 7);
        if (remainingCells < 7) {
            for (let day = 1; day <= remainingCells; day++) {
                allDays.push({ date: new Date(year, month + 1, day), isOtherMonth: true, isToday: false });
            }
        }

        // Render days with weekly TSS
        for (let i = 0; i < allDays.length; i++) {
            const { date, isOtherMonth, isToday } = allDays[i];
            grid.appendChild(this.createCalendarDay(date, isOtherMonth, isToday));

            // Every 7 days (end of week), add TSS total
            if ((i + 1) % 7 === 0) {
                const weekStart = i - 6;
                let weekTSS = 0;

                for (let j = weekStart; j <= i; j++) {
                    const dateStr = this.formatLocalDate(allDays[j].date);
                    const dayActivities = this.activities.filter(a => {
                        const actDate = new Date(a.startTime);
                        return this.formatLocalDate(actDate) === dateStr;
                    });
                    weekTSS += dayActivities.reduce((sum, a) => sum + (a.tss || 0), 0);
                }

                const tssDiv = document.createElement('div');
                tssDiv.className = 'week-tss';
                tssDiv.innerHTML = `<span class="week-tss-value">${Math.round(weekTSS)}</span>`;
                grid.appendChild(tssDiv);
            }
        }
    }

    createCalendarDay(date, isOtherMonth, isToday = false) {
        const div = document.createElement('div');
        div.className = 'calendar-day' + (isOtherMonth ? ' other-month' : '') + (isToday ? ' today' : '');

        // Use local date format (YYYY-MM-DD) to avoid timezone issues
        const dateStr = this.formatLocalDate(date);
        const dayActivities = this.activities.filter(a => {
            const actDate = new Date(a.startTime);
            return this.formatLocalDate(actDate) === dateStr;
        });

        const totalTSS = dayActivities.reduce((sum, a) => sum + (a.tss || 0), 0);

        div.innerHTML = `
            <div class="day-number">${date.getDate()}</div>
            <div class="day-activities">
                ${dayActivities.map(a => `<span class="day-dot ${this.getSportClass(a.sport)}"></span>`).join('')}
            </div>
            ${totalTSS > 0 ? `<div class="day-tss">${totalTSS} TSS</div>` : ''}
        `;

        if (dayActivities.length > 0) {
            div.style.cursor = 'pointer';
            div.addEventListener('click', () => {
                if (dayActivities.length === 1) {
                    this.showActivityDetail(dayActivities[0]);
                } else {
                    // Multiple activities - show day summary modal
                    this.showDayActivities(date, dayActivities);
                }
            });
        }

        return div;
    }

    showDayActivities(date, activities) {
        const modal = document.getElementById('activityModal');
        const body = document.getElementById('modalBody');

        const dateStr = date.toLocaleDateString('it-IT', {
            weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
        });
        const totalTSS = activities.reduce((sum, a) => sum + (a.tss || 0), 0);

        body.innerHTML = `
            <h2>📅 ${dateStr}</h2>
            <p style="color: var(--text-muted); margin-bottom: 20px;">
                ${activities.length} attività • ${totalTSS} TSS totali
            </p>
            <div class="activities-list" id="day-activities-list">
                ${activities.map((a, i) => `
                    <div class="activity-item" data-index="${i}">
                        <div class="activity-sport ${this.getSportClass(a.sport)}">${this.getSportIcon(a.sport)}</div>
                        <div class="activity-info">
                            <div class="activity-title">${this.getSportName(a.sport)}</div>
                            <div class="activity-meta">${this.formatDuration(a.duration)} • ${a.distance ? (a.distance / 1000).toFixed(2) + ' km' : ''}</div>
                        </div>
                        <div class="activity-tss">
                            <div class="activity-tss-value">${a.tss || 0}</div>
                            <div class="activity-tss-label">${a.tssType || 'TSS'}</div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;

        // Add click handlers to each activity
        body.querySelectorAll('.activity-item').forEach((item, i) => {
            item.addEventListener('click', () => {
                this.showActivityDetail(activities[i]);
            });
        });

        modal.classList.add('active');
    }

    updateActivitiesTable() {
        const tbody = document.getElementById('activities-tbody');

        if (this.activities.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Nessuna attività</td></tr>';
            return;
        }

        tbody.innerHTML = this.activities.map(a => {
            const date = new Date(a.startTime);
            const dayName = date.toLocaleDateString('it-IT', { weekday: 'short' });
            return `
                <tr>
                    <td>${dayName} ${date.toLocaleDateString('it-IT')}</td>
                    <td>${this.getSportIcon(a.sport)} ${this.getSportName(a.sport)}</td>
                    <td>${this.formatDuration(a.duration)}</td>
                    <td>${a.distance ? (a.distance / 1000).toFixed(2) + ' km' : '-'}</td>
                    <td><strong>${a.tss || 0}</strong></td>
                    <td>${a.IF || '-'}</td>
                    <td><button class="btn-secondary" data-id="${a.id}">📊</button></td>
                </tr>
            `;
        }).join('');

        tbody.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', () => {
                const activity = this.activities.find(a => a.id === btn.dataset.id);
                if (activity) this.showActivityDetail(activity);
            });
        });
    }

    setupFilters() {
        document.getElementById('sportFilter').addEventListener('change', (e) => {
            const filter = e.target.value;
            const rows = document.querySelectorAll('#activities-tbody tr');

            rows.forEach(row => {
                if (filter === 'all') {
                    row.style.display = '';
                } else {
                    const sportCell = row.cells[1]?.textContent.toLowerCase();
                    const match = sportCell && sportCell.includes(this.getSportName(filter).toLowerCase());
                    row.style.display = match ? '' : 'none';
                }
            });
        });
    }

    setupSettings() {
        document.getElementById('saveSettings').addEventListener('click', async () => {
            this.settings.ftp = parseInt(document.getElementById('ftp').value) || 300;
            this.settings.runThreshold = document.getElementById('runThreshold').value || '4:16';
            this.settings.swimThreshold = document.getElementById('swimThreshold').value || '1:40';

            await this.db.saveSetting('ftp', this.settings.ftp);
            await this.db.saveSetting('runThreshold', this.settings.runThreshold);
            await this.db.saveSetting('swimThreshold', this.settings.swimThreshold);

            this.tssCalculator.updateSettings({
                ftp: this.settings.ftp,
                runThreshold: TSSCalculator.parsePace(this.settings.runThreshold),
                swimThreshold: TSSCalculator.parsePace(this.settings.swimThreshold)
            });

            alert('Impostazioni salvate!');
        });

        document.getElementById('clearData').addEventListener('click', async () => {
            if (confirm('Sei sicuro di voler cancellare tutti i dati?')) {
                await this.db.clearAll();
                this.activities = [];
                this.pmcEngine.clear();
                this.updateDashboard();
                this.updateCalendar();
                this.updateActivitiesTable();
                document.getElementById('activityCount').textContent = '0';
                alert('Dati cancellati!');
            }
        });

        document.getElementById('exportData').addEventListener('click', async () => {
            const data = await this.db.exportData();
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `mytrainingos_export_${new Date().toISOString().split('T')[0]}.json`;
            a.click();
            URL.revokeObjectURL(url);
        });

        document.getElementById('recalculateTSS').addEventListener('click', async () => {
            const confirm42 = confirm('Vuoi ricalcolare i TSS degli ultimi 42 giorni con le nuove impostazioni?');
            if (!confirm42) return;

            // Save settings first
            this.settings.ftp = parseInt(document.getElementById('ftp').value) || 300;
            this.settings.runThreshold = document.getElementById('runThreshold').value || '4:16';
            this.settings.swimThreshold = document.getElementById('swimThreshold').value || '1:40';

            await this.db.saveSetting('ftp', this.settings.ftp);
            await this.db.saveSetting('runThreshold', this.settings.runThreshold);
            await this.db.saveSetting('swimThreshold', this.settings.swimThreshold);

            // Update TSS calculator
            this.tssCalculator.updateSettings({
                ftp: this.settings.ftp,
                runThreshold: TSSCalculator.parsePace(this.settings.runThreshold),
                swimThreshold: TSSCalculator.parsePace(this.settings.swimThreshold)
            });

            // Get activities from last 42 days
            const cutoffDate = new Date();
            cutoffDate.setDate(cutoffDate.getDate() - 42);

            let recalculated = 0;
            for (const activity of this.activities) {
                const actDate = new Date(activity.startTime);
                if (actDate >= cutoffDate) {
                    // Recalculate TSS
                    const tssResult = this.tssCalculator.recalculate(activity);
                    if (tssResult) {
                        activity.tss = tssResult.tss;
                        activity.tssType = tssResult.type;
                        activity.IF = tssResult.IF;
                        await this.db.updateActivity(activity);
                        recalculated++;
                    }
                }
            }

            // Reload and update - FORCE PMC recalculation
            this.pmcEngine.clear(); // Clear old PMC data
            await this.loadActivities(); // This rebuilds PMC from scratch
            this.updateDashboard();
            this.updateCalendar();
            this.updateActivitiesTable();
            if (this.pmcChart) this.updatePMCChart(90);

            alert(`Ricalcolati ${recalculated} allenamenti degli ultimi 42 giorni!`);
        });
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    window.app = new App();
    window.app.init().catch(console.error);
});
