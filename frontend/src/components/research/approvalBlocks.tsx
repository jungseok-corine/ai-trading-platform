// C-2.30: 승인 카드 공용 UI 조각 (안전 고지 블록 + 원본 JSON 접기).
import { useState } from "react";

export function WillHappenBlock({ items }: { items: readonly string[] }) {
  return (
    <div className="approval-block">
      <strong>승인하면 이렇게 됩니다</strong>
      <ul className="approval-list">
        {items.map((s) => (
          <li key={s}>✅ {s}</li>
        ))}
      </ul>
    </div>
  );
}

export function WillNotHappenBlock({ items }: { items: readonly string[] }) {
  return (
    <div className="approval-block safe">
      <strong>승인해도 일어나지 않는 일</strong>
      <ul className="approval-list">
        {items.map((s) => (
          <li key={s}>🚫 {s}</li>
        ))}
      </ul>
    </div>
  );
}

// raw JSON은 기본으로 숨기고 "원본 보기"로만 펼친다 (모바일에서 과도한 노출 방지).
export function RawJsonDetails({ label, data }: { label: string; data: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="raw-json">
      <button className="link-button" onClick={() => setOpen((o) => !o)}>
        {open ? "원본 숨기기" : `원본 보기 (${label})`}
      </button>
      {open && <pre className="raw-json-pre">{JSON.stringify(data, null, 2)}</pre>}
    </div>
  );
}
