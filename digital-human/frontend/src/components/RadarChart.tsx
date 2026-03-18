/** 雷达图组件 */
import { Radar, RadarChart as RechartsRadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from "recharts";

interface EvaluationDimension {
  name: string;
  score: number;
  description: string;
}

interface RadarChartProps {
  dimensions: EvaluationDimension[];
}

export function RadarChart({ dimensions }: RadarChartProps) {
  // 转换数据格式
  const data = dimensions.map((dim) => ({
    dimension: dim.name,
    score: dim.score,
    fullMark: 100,
  }));

  return (
    <ResponsiveContainer width="100%" height={400}>
      <RechartsRadarChart data={data}>
        <PolarGrid stroke="rgba(255, 255, 255, 0.2)" />
        <PolarAngleAxis
          dataKey="dimension"
          tick={{ fill: "#f1f5f9", fontSize: 14 }}
          tickLine={{ stroke: "rgba(255, 255, 255, 0.3)" }}
        />
        <PolarRadiusAxis
          angle={90}
          domain={[0, 100]}
          tick={{ fill: "#94a3b8", fontSize: 12 }}
          tickLine={{ stroke: "rgba(255, 255, 255, 0.2)" }}
        />
        <Radar
          name="评分"
          dataKey="score"
          stroke="rgba(59, 130, 246, 0.8)"
          fill="rgba(59, 130, 246, 0.3)"
          fillOpacity={0.6}
        />
      </RechartsRadarChart>
    </ResponsiveContainer>
  );
}
