import React from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import { TrendingUp, TrendingDown, Activity, Award } from 'lucide-react';
import type { ForecastAnalysis } from '../../types/api';
import './ForecastChart.css';

interface ForecastChartProps {
  forecast: ForecastAnalysis;
}

export const ForecastChart: React.FC<ForecastChartProps> = ({ forecast }) => {
  const {
    projected_timeline,
    trend_direction,
    health_score,
    projected_total_events_90d,
    maintenance_verdict_signal,
  } = forecast;

  const getTrendBadge = (trend: string) => {
    switch (trend) {
      case 'ACCELERATING':
        return { label: 'ACCELERATING', icon: TrendingUp, className: 'trend-accelerating' };
      case 'DECLINING':
        return { label: 'DECLINING', icon: TrendingDown, className: 'trend-declining' };
      default:
        return { label: 'STABLE', icon: Activity, className: 'trend-stable' };
    }
  };

  const trendInfo = getTrendBadge(trend_direction);
  const TrendIcon = trendInfo.icon;

  // Custom Tooltip component
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="chart-custom-tooltip">
          <p className="tooltip-date">Week of {label}</p>
          <p className="tooltip-projected">
            <strong>Projected Activity:</strong> {data.projected_events} events
          </p>
          <p className="tooltip-interval">
            <strong>90% Confidence Interval:</strong> [{data.confidence_lower} - {data.confidence_upper}]
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="forecast-chart-card">
      {/* Header Stat Pills */}
      <div className="forecast-stats-row">
        <div className="stat-pill health-pill">
          <Award className="stat-icon" />
          <div className="stat-content">
            <span className="stat-label">Health Score</span>
            <span className="stat-value">{health_score.toFixed(1)} / 100</span>
          </div>
        </div>

        <div className={`stat-pill trend-pill ${trendInfo.className}`}>
          <TrendIcon className="stat-icon" />
          <div className="stat-content">
            <span className="stat-label">90-Day Trend</span>
            <span className="stat-value">{trendInfo.label}</span>
          </div>
        </div>

        <div className="stat-pill events-pill">
          <Activity className="stat-icon" />
          <div className="stat-content">
            <span className="stat-label">Projected 90d Events</span>
            <span className="stat-value">{projected_total_events_90d}</span>
          </div>
        </div>

        <div className="stat-pill signal-pill">
          <span className="stat-label">Signal</span>
          <span className="stat-value signal-text">{maintenance_verdict_signal}</span>
        </div>
      </div>

      {/* Chart Legend */}
      <div className="chart-legend-row">
        <div className="legend-item">
          <span className="legend-line-indicator" />
          <span>Projected Weekly Activity</span>
        </div>
        <div className="legend-item">
          <span className="legend-band-indicator" />
          <span>90% Forecast Confidence Interval Band</span>
        </div>
      </div>

      {/* Recharts Forecast Graph */}
      <div className="chart-container">
        {projected_timeline && projected_timeline.length > 0 ? (
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart
              data={projected_timeline}
              margin={{ top: 15, right: 15, left: -20, bottom: 0 }}
            >
              <defs>
                <linearGradient id="confidenceBandGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#5a7bb0" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#5a7bb0" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis
                dataKey="week_start"
                tick={{ fontSize: 11, fill: '#64748b' }}
                tickLine={false}
              />
              <YAxis tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              
              {/* Shaded Confidence Interval Upper Band */}
              <Area
                type="monotone"
                dataKey="confidence_upper"
                stroke="#95b2d0"
                strokeDasharray="2 2"
                strokeWidth={1}
                fill="url(#confidenceBandGrad)"
                name="Confidence Upper Bound"
              />
              
              {/* Mask out lower bound area so only [lower - upper] range is shaded */}
              <Area
                type="monotone"
                dataKey="confidence_lower"
                stroke="#95b2d0"
                strokeDasharray="2 2"
                strokeWidth={1}
                fill="#ffffff"
                name="Confidence Lower Bound"
              />

              {/* Projected Events Line */}
              <Line
                type="monotone"
                dataKey="projected_events"
                stroke="#5a7bb0"
                strokeWidth={3}
                dot={{ r: 4, fill: '#5a7bb0', strokeWidth: 2, stroke: '#ffffff' }}
                activeDot={{ r: 6, fill: '#3f668d' }}
                name="Projected Activity"
              />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="empty-chart-msg">
            No projected weekly series available for this repository.
          </div>
        )}
      </div>
    </div>
  );
};
