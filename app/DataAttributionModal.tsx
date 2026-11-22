"use client";

import React, { useEffect } from "react";

interface DataAttributionModalProps {
  isOpen: boolean;
  onClose: () => void;
}

/**
 * 画面右下「ℹ️ データ出典・注記」ボタンから開くモーダル。
 * ODPTチャレンジ2026のクレジット表記、PLATEAU等のデータ出典、および未着色建物の注記を表示する。
 */
export function DataAttributionModal({ isOpen, onClose }: DataAttributionModalProps) {
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "rgba(0, 0, 0, 0.65)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "rgba(15, 23, 42, 0.96)",
          color: "#ffffff",
          border: "1px solid rgba(56, 189, 248, 0.3)",
          borderRadius: 10,
          boxShadow: "0 24px 48px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 255, 255, 0.05)",
          width: "100%",
          maxWidth: 600,
          maxHeight: "85vh",
          display: "flex",
          flexDirection: "column",
          fontFamily: "sans-serif",
          fontSize: 12.5,
          lineHeight: 1.6,
        }}
      >
        {/* ヘッダー */}
        <div
          style={{
            padding: "14px 18px",
            borderBottom: "1px solid rgba(255, 255, 255, 0.1)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "rgba(30, 41, 59, 0.5)",
            borderTopLeftRadius: 10,
            borderTopRightRadius: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 18 }}>ℹ️</span>
            <div>
              <div style={{ fontSize: 15, fontWeight: "bold", color: "#ffffff" }}>
                データ出典・利用注記
              </div>
              <div style={{ fontSize: 11, color: "#e2e8f0" }}>
                Project PLATEAU × 公共交通オープンデータチャレンジ2026
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="閉じる"
            style={{
              background: "rgba(255, 255, 255, 0.1)",
              border: "none",
              color: "#cbd5e1",
              fontSize: 16,
              width: 28,
              height: 28,
              borderRadius: 6,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            ✕
          </button>
        </div>

        {/* 本文 */}
        <div style={{ padding: "16px 20px", overflowY: "auto", display: "flex", flexDirection: "column", gap: 14 }}>
          <div
            style={{
              background: "rgba(56, 189, 248, 0.08)",
              border: "1px solid rgba(56, 189, 248, 0.25)",
              borderRadius: 6,
              padding: "10px 12px",
            }}
          >
            <div style={{ fontWeight: "bold", color: "#7dd3fc", marginBottom: 4 }}>
              ■ バス運行頻度・時刻表データ（ODPTチャレンジ2026）
            </div>
            <div style={{ color: "#ffffff", fontSize: 12 }}>
              本アプリは、公共交通オープンデータセンター（ODPT）「公共交通オープンデータチャレンジ2026」にて提供される
              <strong>神奈川中央交通</strong>のバス時刻表情報（odpt:BusTimetable）およびバス停情報（odpt:BusstopPole）を加工・集計して利用しています。
            </div>
            <div style={{ marginTop: 6, fontSize: 11.5, color: "#e0f2fe" }}>
              ※江ノ電バスおよびコミュニティバス等については、ODPT一般公開データに時刻表が含まれないため、国土数値情報の位置基準（設定により除外可）として扱っています。位置・時刻表と一部誤差が生じる場合があります。
            </div>
          </div>

          <div>
            <div style={{ fontWeight: "bold", color: "#38bdf8", marginBottom: 6 }}>
              ■ 白い建物（未着色）について
            </div>
            <div
              style={{
                background: "rgba(30, 41, 59, 0.55)",
                border: "1px solid rgba(255, 255, 255, 0.14)",
                borderRadius: 6,
                padding: "9px 12px",
                fontSize: 12,
                color: "#ffffff",
              }}
            >
              白い建物は住宅系以外・用途不明・未評価です。読み込み中、通信失敗、道路網データ未収録の場合も白く表示されます。
            </div>
          </div>

          <div>
            <div style={{ fontWeight: "bold", color: "#38bdf8", marginBottom: 6 }}>
              ■ 3D都市モデル・地図・基盤データ出典
            </div>
            <ul style={{ margin: 0, paddingLeft: 18, color: "#ffffff", fontSize: 12, display: "flex", flexDirection: "column", gap: 4 }}>
              <li>3D都市モデル・オルソ画像・地形：Project PLATEAU（国土交通省、藤沢市 14205）</li>
              <li>バス停・鉄道駅位置データ：国土数値情報（バス停留所データ P11・鉄道データ N02、令和4年度）</li>
              <li>歩行道路網・背景地図：OpenStreetMap contributors</li>
              <li>標高・勾配計算：国土地理院 数値標高モデル（DEM5A）</li>
              <li>シェアサイクル（オプション）：ODPT GBFSデータ（OpenStreet株式会社 / 公共交通オープンデータ協議会）</li>
            </ul>
          </div>
        </div>

        {/* フッター */}
        <div
          style={{
            padding: "10px 18px",
            borderTop: "1px solid rgba(255, 255, 255, 0.1)",
            display: "flex",
            justifyContent: "flex-end",
            background: "rgba(30, 41, 59, 0.4)",
            borderBottomLeftRadius: 10,
            borderBottomRightRadius: 10,
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: "6px 14px",
              background: "rgba(56, 189, 248, 0.2)",
              border: "1px solid rgba(56, 189, 248, 0.5)",
              borderRadius: 4,
              color: "#38bdf8",
              fontSize: 12,
              cursor: "pointer",
              fontWeight: "bold",
            }}
          >
            閉じる
          </button>
        </div>
      </div>
    </div>
  );
}
