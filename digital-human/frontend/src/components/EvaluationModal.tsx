/** 评价模态框组件 */
import { useEffect } from "react";
import type { EvaluationResult } from "../types";
import { RadarChart } from "./RadarChart";
import "./EvaluationModal.css";

interface EvaluationModalProps {
  evaluationResult: EvaluationResult;
  onClose: () => void;
}

export function EvaluationModal({ evaluationResult, onClose }: EvaluationModalProps) {
  // 阻止背景滚动
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "unset";
    };
  }, []);

  // 处理ESC键关闭
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("keydown", handleEscape);
    };
  }, [onClose]);

  return (
    <div className="evaluation-modal-overlay" onClick={onClose}>
      <div className="evaluation-modal" onClick={(e) => e.stopPropagation()}>
        <div className="evaluation-modal-header">
          <h2>面试评价结果</h2>
          <button className="evaluation-modal-close" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="evaluation-modal-content">
          {/* 雷达图 */}
          <div className="evaluation-radar-section">
            <h3>多维度评价</h3>
            <div className="radar-chart-container">
              <RadarChart dimensions={evaluationResult.dimensions} />
            </div>
            
            {/* 维度详情 */}
            <div className="dimensions-details">
              {evaluationResult.dimensions.map((dim, index) => (
                <div key={index} className="dimension-item">
                  <div className="dimension-header">
                    <span className="dimension-name">{dim.name}</span>
                    <span className="dimension-score">{dim.score}分</span>
                  </div>
                  <p className="dimension-description">{dim.description}</p>
                </div>
              ))}
            </div>
          </div>

          {/* 面试总结 */}
          <div className="evaluation-summary-section">
            <h3>面试总结</h3>
            <div className="evaluation-text-content">
              {evaluationResult.summary}
            </div>
          </div>

          {/* 改进建议 */}
          <div className="evaluation-suggestions-section">
            <h3>改进建议</h3>
            <div className="evaluation-text-content">
              {evaluationResult.suggestions}
            </div>
          </div>
        </div>

        <div className="evaluation-modal-footer">
          <button className="evaluation-modal-button" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
