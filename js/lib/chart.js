/**
 * Simple Chart Library for MyTrainingOS
 * Canvas-based PMC chart with CTL, ATL, TSB, and TSS
 */

class PMCChart {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.data = [];
        this.padding = { top: 40, right: 60, bottom: 50, left: 60 };
        this.colors = {
            ctl: '#3b82f6',
            atl: '#ec4899',
            tsb: '#f59e0b',
            tss: '#8b5cf6',
            grid: '#27272a',
            text: '#a1a1aa',
            bg: '#1e1e2a'
        };
        this.setupCanvas();
    }

    setupCanvas() {
        const rect = this.canvas.parentElement.getBoundingClientRect();
        this.canvas.width = rect.width;
        this.canvas.height = rect.height - 20;
        this.width = this.canvas.width;
        this.height = this.canvas.height;
        this.chartWidth = this.width - this.padding.left - this.padding.right;
        this.chartHeight = this.height - this.padding.top - this.padding.bottom;
    }

    setData(pmcData) {
        this.data = pmcData;
        this.render();
    }

    render() {
        if (!this.data.length) return;
        this.ctx.clearRect(0, 0, this.width, this.height);
        this.ctx.fillStyle = this.colors.bg;
        this.ctx.fillRect(0, 0, this.width, this.height);

        const { minCTL, maxCTL, minTSB, maxTSB, maxTSS } = this.getDataRange();

        this.drawGrid(minCTL, maxCTL);
        this.drawTSSBars(maxTSS);
        this.drawTSBArea(minTSB, maxTSB);
        this.drawLine('ctl', this.colors.ctl, minCTL, maxCTL);
        this.drawLine('atl', this.colors.atl, minCTL, maxCTL);
        this.drawAxes();
        this.drawLabels(minCTL, maxCTL, minTSB, maxTSB);
    }

    getDataRange() {
        const ctlValues = this.data.map(d => d.ctl);
        const atlValues = this.data.map(d => d.atl);
        const tsbValues = this.data.map(d => d.tsb);
        const tssValues = this.data.map(d => d.tss);

        const allLoadValues = [...ctlValues, ...atlValues];
        const minCTL = Math.min(...allLoadValues) - 5;
        const maxCTL = Math.max(...allLoadValues) + 10;
        const minTSB = Math.min(...tsbValues) - 5;
        const maxTSB = Math.max(...tsbValues) + 5;
        const maxTSS = Math.max(...tssValues, 50);

        return { minCTL, maxCTL, minTSB, maxTSB, maxTSS };
    }

    drawGrid(min, max) {
        this.ctx.strokeStyle = this.colors.grid;
        this.ctx.lineWidth = 1;

        const steps = 5;
        const range = max - min;

        for (let i = 0; i <= steps; i++) {
            const y = this.padding.top + (this.chartHeight * i / steps);
            this.ctx.beginPath();
            this.ctx.moveTo(this.padding.left, y);
            this.ctx.lineTo(this.width - this.padding.right, y);
            this.ctx.stroke();
        }
    }

    drawTSSBars(maxTSS) {
        const barWidth = (this.chartWidth / this.data.length) * 0.6;

        this.data.forEach((d, i) => {
            if (d.tss > 0) {
                const x = this.padding.left + (i / (this.data.length - 1)) * this.chartWidth;
                const barHeight = (d.tss / maxTSS) * (this.chartHeight * 0.3);
                const y = this.height - this.padding.bottom - barHeight;

                this.ctx.fillStyle = this.colors.tss + '40';
                this.ctx.fillRect(x - barWidth / 2, y, barWidth, barHeight);
            }
        });
    }

    drawTSBArea(min, max) {
        const range = max - min;
        const zeroline = this.padding.top + ((max - 0) / range) * this.chartHeight;

        this.ctx.beginPath();
        this.ctx.moveTo(this.padding.left, zeroline);

        this.data.forEach((d, i) => {
            const x = this.padding.left + (i / (this.data.length - 1)) * this.chartWidth;
            const y = this.padding.top + ((max - d.tsb) / range) * this.chartHeight;
            this.ctx.lineTo(x, y);
        });

        this.ctx.lineTo(this.width - this.padding.right, zeroline);
        this.ctx.closePath();

        const gradient = this.ctx.createLinearGradient(0, this.padding.top, 0, this.height - this.padding.bottom);
        gradient.addColorStop(0, this.colors.tsb + '30');
        gradient.addColorStop(0.5, this.colors.tsb + '10');
        gradient.addColorStop(1, this.colors.tsb + '30');

        this.ctx.fillStyle = gradient;
        this.ctx.fill();
    }

    drawLine(key, color, min, max) {
        const range = max - min;
        this.ctx.strokeStyle = color;
        this.ctx.lineWidth = 2;
        this.ctx.beginPath();

        this.data.forEach((d, i) => {
            const x = this.padding.left + (i / (this.data.length - 1)) * this.chartWidth;
            const y = this.padding.top + ((max - d[key]) / range) * this.chartHeight;

            if (i === 0) this.ctx.moveTo(x, y);
            else this.ctx.lineTo(x, y);
        });

        this.ctx.stroke();
    }

    drawAxes() {
        this.ctx.strokeStyle = this.colors.text;
        this.ctx.lineWidth = 1;

        // Y-axis
        this.ctx.beginPath();
        this.ctx.moveTo(this.padding.left, this.padding.top);
        this.ctx.lineTo(this.padding.left, this.height - this.padding.bottom);
        this.ctx.stroke();

        // X-axis
        this.ctx.beginPath();
        this.ctx.moveTo(this.padding.left, this.height - this.padding.bottom);
        this.ctx.lineTo(this.width - this.padding.right, this.height - this.padding.bottom);
        this.ctx.stroke();
    }

    drawLabels(minCTL, maxCTL, minTSB, maxTSB) {
        this.ctx.font = '11px Inter, sans-serif';
        this.ctx.fillStyle = this.colors.text;
        this.ctx.textAlign = 'right';

        // Y-axis labels (CTL/ATL)
        const steps = 5;
        const range = maxCTL - minCTL;
        for (let i = 0; i <= steps; i++) {
            const value = maxCTL - (range * i / steps);
            const y = this.padding.top + (this.chartHeight * i / steps);
            this.ctx.fillText(Math.round(value).toString(), this.padding.left - 8, y + 4);
        }

        // X-axis labels (dates)
        this.ctx.textAlign = 'center';
        const labelInterval = Math.max(1, Math.floor(this.data.length / 8));

        this.data.forEach((d, i) => {
            if (i % labelInterval === 0 || i === this.data.length - 1) {
                const x = this.padding.left + (i / (this.data.length - 1)) * this.chartWidth;
                const date = new Date(d.date);
                const label = `${date.getDate()}/${date.getMonth() + 1}`;
                this.ctx.fillText(label, x, this.height - this.padding.bottom + 20);
            }
        });
    }

    resize() {
        this.setupCanvas();
        this.render();
    }
}

window.PMCChart = PMCChart;
